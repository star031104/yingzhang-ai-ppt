"""Outline planning core: evidence-bound deterministic plan, model enhancement and persistence."""

import copy
import hashlib
import json
import re
from pathlib import Path

from app.api.dependencies import project_or_404
from app.db.models import (
    DeckSpecRecord,
    LicensedAsset,
    SlideCandidate,
    SlideEditMessage,
    SlideSpecRecord,
    SlideVersion,
)
from app.intelligence.embeddings import build_embedding_retriever
from app.intelligence.knowledge_base import build_knowledge_base
from app.intelligence.retrieval import retrieval_query, section_relevance_async
from app.personalization import service as personal
from app.personalization.runtime import assert_current, generation_snapshot, guarded_generation
from app.personalization.runtime import lock as personal_lock
from app.presentation_intelligence.art_director import build_design_system
from app.presentation_intelligence.assets import bind_source_figures, normalize_visual_intent
from app.presentation_intelligence.layout_planner import plan_deck_layouts
from app.presentation_intelligence.planner import evidence_bindings, plan_deck
from app.presentation_intelligence.research_assets import build_research_manifest
from app.presentation_intelligence.style_contract import build_style_contract
from app.skills.manager import resolve_skill_context
from app.skills.project import set_project_skills
from app.sources import build_brief_source, load_sources
from app.templates.layout_library import attach_reference_layouts, load_reference_layout_library
from app.workflows import model_planning
from app.workflows.outline_repair import repair_outline_from_builtin
from app.workflows.planning_brief import PlanRequest, enriched_instructions, professional_brief
from fastapi import HTTPException
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session


@guarded_generation
async def _plan_project_core(project_id: str, body: PlanRequest, db: Session):
    project = project_or_404(project_id, db)
    stored_sources = load_sources(project_id, db)
    def usable_source_text(section: dict) -> bool:
        text = re.sub(r"\s+", " ", str(section.get("text", ""))).strip()
        if not text or re.fullmatch(r"图片尺寸\s*\d+\s*[×x]\s*\d+", text, flags=re.IGNORECASE):
            return False
        return bool(re.search(r"[\u3400-\u9fffA-Za-z]{2,}", text))

    if stored_sources and not any(
        usable_source_text(section)
        for source in stored_sources
        for section in source.get("sections", [])
    ):
        raise HTTPException(422, "上传材料中没有可读取的正文。请补充可读取的文档或文字识别结果，再生成基于材料的演示。")
    brief = professional_brief(body)
    instructions = enriched_instructions(body)
    snapshot = None
    from app.db.models import PersonalBinding
    if body.personalization_mode == "profile":
        if not body.profile_id:
            raise HTTPException(422, "请选择个人档案")
        with personal_lock:
            snapshot = generation_snapshot.get()
            if not snapshot or snapshot.get("profileId") != body.profile_id:
                snapshot = personal.bind(db, project_id, body.profile_id, body.preset, body.profile_revision)
        generation_snapshot.set(snapshot)
        brief = personal.compile_brief(brief, snapshot, body.instructions)
        if snapshot.get("preferences", {}).get("review_mode") == "samples-first":
            body.approval_mode = True
    else:
        db.execute(delete(PersonalBinding).where(PersonalBinding.project_id == project_id))
        db.commit()
        generation_snapshot.set(None)
    sources = stored_sources or [build_brief_source(body.title, instructions)]
    selected_skills = set_project_skills(project_id, body.skill_ids, db)
    # Persist the project selection before the awaited model calls. Keeping this
    # DELETE transaction open locks SQLite writers, including job progress ticks.
    db.commit()
    relevance, retrieval_info = None, {"strategy": "bm25", "dense": False}
    retriever = build_embedding_retriever(db)
    if retriever is not None:
        # Dense relevance only refines record selection when an embedding model is routed.
        relevance, retrieval_info = await section_relevance_async(
            sources, retrieval_query(body.title, body.preset, instructions), retriever
        )
        relevance = relevance if retrieval_info.get("dense") else None
    plan = plan_deck(
        sources, body.title, body.preset, body.slide_count, instructions, brief=brief,
        relevance=relevance,
    )
    builtin_plan = copy.deepcopy(plan)
    baseline_plan = plan_deck(sources, body.title, body.preset, body.slide_count, instructions,
                              brief=professional_brief(body), relevance=relevance) if snapshot and (snapshot.get("preferences") or snapshot.get("examples") or snapshot.get("reference")) else None
    baseline_model = None
    if baseline_plan:
        baseline_plan, baseline_model = await model_planning.enhance_plan_with_routed_model(
            baseline_plan, sources, body.title, body.preset, instructions, selected_skills, db, professional_brief(body)
        )
        assert_current()
    plan, model_run = await model_planning.enhance_plan_with_routed_model(
        plan, sources, body.title, body.preset, instructions, selected_skills, db, brief
    )
    assert_current()
    outline_content_qa = repair_outline_from_builtin(plan, builtin_plan, sources)
    if model_run is not None:
        model_run["automaticContentRepair"] = outline_content_qa
    plan["outlineContentQA"] = outline_content_qa
    if baseline_plan:
        from app.validation.quality import validate_deck
        ordinary_quality = validate_deck(baseline_plan["slides"], sources)
        personal_quality = validate_deck(plan["slides"], sources)
        from app.personalization.comparison import compare_quality
        regression_reasons = compare_quality(ordinary_quality, personal_quality)
        personal_plan = copy.deepcopy(plan)
        if regression_reasons:
            plan = copy.deepcopy(baseline_plan)
        plan["personalizationContentQA"] = {"baselineBlockingErrors": ordinary_quality.get("blockingErrors", 0),
            "personalBlockingErrors": personal_quality.get("blockingErrors", 0), "fellBack": bool(regression_reasons),
            "reasons": regression_reasons,
            "scope": "两路使用相同模型配置完成成稿；事实、覆盖和结构指标对照，主观质量需盲评"}
    from app.presentation_intelligence.result_coverage import complete_primary_results
    result_repairs = complete_primary_results(plan, sources)
    if result_repairs:
        for slide in plan["slides"]:
            slide["evidenceBindings"] = evidence_bindings(plan["evidence"], slide.get("sourceRefs", []))
        model_run["primaryResultRepairs"] = result_repairs
    source_figures = bind_source_figures(plan, sources)
    normalize_visual_intent(plan)
    design_system = build_design_system(body.preset, selected_skills, brief)
    base_design_system = build_design_system(body.preset, selected_skills, professional_brief(body))
    design_system = personal.compile_design(design_system, snapshot, explicit_style=bool(selected_skills or body.brand_name or re.search(r"字体|配色|颜色|版式|视觉|样式|风格|留白|密度|字号", body.instructions)))
    # One fixed style schema per deck; page selection is scored against it.
    design_system["styleContract"] = build_style_contract(design_system, body.preset, brief)
    reference_layouts = attach_reference_layouts(
        plan["slides"], load_reference_layout_library(db, selected_skills, snapshot)
    )
    layout_planning = plan_deck_layouts(
        plan["slides"], body.preset, brief, design_system.get("referenceGrammar", {})
    )
    layout_planning["referenceLayouts"] = reference_layouts
    plan["layoutPlanning"] = layout_planning
    plan["narrative"]["visualRhythm"] = layout_planning["familySequence"]
    research_manifest = build_research_manifest(sources, plan["slides"], brief)
    plan["researchManifest"] = research_manifest
    for slide in plan["slides"]:
        slide["designSystem"] = design_system
        if snapshot and snapshot.get("preferences"):
            slide["personalizationBaseline"] = base_design_system
    if baseline_plan:
        from app.personalization.comparison import record_comparison
        for compared, compared_brief, compared_design in ((baseline_plan, professional_brief(body), base_design_system), (personal_plan, brief, design_system)):
            bind_source_figures(compared, sources)
            normalize_visual_intent(compared)
            plan_deck_layouts(compared["slides"], body.preset, compared_brief, compared_design.get("referenceGrammar", {}))
        for baseline_slide in baseline_plan["slides"]:
            baseline_slide["designSystem"] = copy.deepcopy(base_design_system)
        for personal_slide in personal_plan["slides"]:
            personal_slide["designSystem"] = copy.deepcopy(design_system)
            personal_slide["personalizationBaseline"] = copy.deepcopy(base_design_system)
        record_comparison(db, project_id, snapshot, baseline_plan, personal_plan, baseline_model, model_run, regression_reasons)
    old_slide_ids = list(db.scalars(
        select(SlideSpecRecord.id).where(SlideSpecRecord.project_id == project_id)
    ))
    if old_slide_ids:
        db.execute(update(LicensedAsset).where(LicensedAsset.slide_id.in_(old_slide_ids)).values(slide_id=None))
        db.execute(delete(SlideCandidate).where(SlideCandidate.slide_id.in_(old_slide_ids)))
        db.execute(delete(SlideVersion).where(SlideVersion.slide_id.in_(old_slide_ids)))
        db.execute(delete(SlideEditMessage).where(SlideEditMessage.slide_id.in_(old_slide_ids)))
    db.execute(delete(SlideSpecRecord).where(SlideSpecRecord.project_id == project_id))
    db.execute(delete(DeckSpecRecord).where(DeckSpecRecord.project_id == project_id))
    hashes = [source["sha256"] for source in sources]
    db.add(
        DeckSpecRecord(
            project_id=project_id,
            narrative=plan["narrative"],
            design_system=design_system,
            reproducibility={
                "promptVersion": "outline-v5.0-small-model-contracts",
                "intelligenceVersion": "yingzhang-v6-deterministic-small-model-orchestration",
                "sourceHash": hashlib.sha256("".join(hashes).encode()).hexdigest(),
                "inputMode": "materials" if stored_sources else "brief",
                "model": model_run,
                "orchestration": plan.get("orchestration", {}),
                "retrieval": {
                    "strategy": "page-contract-bounded-evidence-window",
                    "contextLimit": (plan.get("orchestration", {}).get("policy") or {}).get("context_limit", 0),
                    "ranking": retrieval_info,
                },
                "proposalValidation": plan.get("proposalValidation"),
                "sourceFigureBindings": source_figures,
                "layoutPlanning": layout_planning,
                "researchManifest": research_manifest,
                "brandKit": design_system.get("brandKit", {}),
                "personalization": personal.describe(snapshot),
                "personalizationContentQA": plan.get("personalizationContentQA"),
                "outlineContentQA": plan.get("outlineContentQA"),
                "visualSkillRuntime": [
                    {"id": item["id"], "scriptsExecuted": item["scriptsExecuted"]}
                    for item in resolve_skill_context(selected_skills)
                ],
                "request": {
                    "title": body.title,
                    "instructions": body.instructions,
                    "profileId": snapshot["profileId"] if snapshot else None,
                    "preset": body.preset,
                    "slideCount": body.slide_count,
                    "skillIds": [row.id for row in selected_skills],
                    "approvalMode": body.approval_mode,
                    "imageMode": body.image_mode,
                    "professionalBrief": professional_brief(body),
                    "inputMode": "materials" if stored_sources else "brief",
                },
                "gates": {
                    "enabled": body.approval_mode,
                    "outline": "pending" if body.approval_mode else "approved",
                    "sample": "pending" if body.approval_mode else "approved",
                },
            },
        )
    )
    for slide in plan["slides"]:
        db.add(
            SlideSpecRecord(
                id=slide["id"], project_id=project_id, position=slide["position"], spec=slide
            )
        )
        db.add(SlideVersion(slide_id=slide["id"], version=1, spec=slide, reason="initial outline"))
    path = Path(project.artifact_path) / "plan" / "deck-spec.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    evidence_path = Path(project.artifact_path) / "analysis" / "evidence-graph.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(
        json.dumps(plan["evidence"], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    architecture_path = Path(project.artifact_path) / "analysis" / "content-architecture.json"
    architecture_path.write_text(
        json.dumps({
            "narrative": plan.get("narrative", {}),
            "materialAnalysis": plan.get("materialAnalysis", {}),
            "pageContracts": plan.get("pageContracts", []),
            "presenterPreparation": plan.get("presenterPreparation", {}),
            "layoutPlanning": layout_planning,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    knowledge_path = Path(project.artifact_path) / "analysis" / "knowledge-base.json"
    knowledge_path.write_text(
        json.dumps(build_knowledge_base(sources, plan["evidence"]), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    research_path = Path(project.artifact_path) / "analysis" / "research-manifest.json"
    research_path.write_text(
        json.dumps(research_manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    orchestration_path = Path(project.artifact_path) / "analysis" / "orchestration-contract.json"
    orchestration_path.write_text(
        json.dumps(plan.get("orchestration", {}), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    speech = [f"# {body.title}｜演讲稿\n"]
    for slide in plan["slides"]:
        intent = slide.get("speakerIntent", {})
        speech.extend([
            f"## 第 {slide['position']} 页｜{slide['content']['title']}",
            slide.get("message", ""),
            *[f"- {point}" for point in intent.get("talkingPoints", [])],
            f"\n过渡：{intent.get('transition', '继续下一页')}\n",
        ])
    (Path(project.artifact_path) / "plan" / "speech.md").write_text(
        "\n".join(speech), encoding="utf-8"
    )
    db.commit()
    return plan


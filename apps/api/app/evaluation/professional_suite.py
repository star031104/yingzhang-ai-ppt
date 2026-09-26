import hashlib
from pathlib import Path

from sqlalchemy import func, select

from app.db.models import (
    DeckSpecRecord,
    DeliveryVerification,
    ExportRecord,
    PersonalBinding,
    SlideSpecRecord,
    SlideVersion,
)
from app.evaluation.fingerprints import export_source_fingerprint
from app.professional.delivery import audit_delivery_profile

FIXED_CASES = [
    {"id": "long-title-zh", "label": "中文长标题边界", "dimension": "readability"},
    {"id": "multilingual-fonts", "label": "中英数字混排字体", "dimension": "fundamentals"},
    {"id": "dense-data", "label": "高密度数据与原生表格", "dimension": "visualDesign"},
    {"id": "company-template", "label": "企业母版与主题往返", "dimension": "fidelity"},
    {"id": "source-completeness", "label": "关键主张与来源覆盖", "dimension": "completeness"},
    {"id": "layout-contract", "label": "页面构图规划契约", "dimension": "layout"},
    {"id": "narrative-rhythm", "label": "全稿版式与叙事节奏", "dimension": "rhythm"},
    {"id": "accessibility", "label": "可访问性与媒体说明", "dimension": "accessibility"},
    {"id": "brand-consistency", "label": "品牌系统一致性", "dimension": "brand"},
    {"id": "research-governance", "label": "调研来源与素材许可治理", "dimension": "research"},
    {"id": "cross-platform", "label": "跨演示软件交付兼容", "dimension": "delivery"},
]


def build_evaluation_metrics(
    project, db, quality: dict, imported_analysis: dict | None = None
) -> dict:
    slide_count = (
        db.scalar(
            select(func.count())
            .select_from(SlideSpecRecord)
            .where(SlideSpecRecord.project_id == project.id)
        )
        or 0
    )
    edit_count = (
        db.scalar(
            select(func.count())
            .select_from(SlideVersion)
            .join(SlideSpecRecord, SlideVersion.slide_id == SlideSpecRecord.id)
            .where(SlideSpecRecord.project_id == project.id,
                   SlideVersion.reason.not_in(["generated", "initial outline", "narration-generated", "powerpoint-effects"]),
                   ~SlideVersion.reason.like("%regenerat%"))
        )
        or 0
    )
    selected = sum((row.spec.get("visualIntent") or {}).get("variantSelectionSource") == "user"
                   for row in db.scalars(select(SlideSpecRecord).where(SlideSpecRecord.project_id == project.id)))
    exports = list(db.scalars(select(ExportRecord).where(ExportRecord.project_id == project.id)))
    current_pptx = max((row for row in exports
                        if row.format == "pptx" and Path(row.artifact_path).is_file()),
                       key=lambda row: row.created_at, default=None)
    deck = db.get(DeckSpecRecord, project.id)
    slide_specs = list(
        db.scalars(
            select(SlideSpecRecord)
            .where(SlideSpecRecord.project_id == project.id)
            .order_by(SlideSpecRecord.position)
        )
    )
    slides = [row.spec for row in slide_specs]
    reproducibility = (deck.reproducibility or {}) if deck else {}
    request = reproducibility.get("request", {})
    explicit_visual = bool(
        request.get("skillIds") or (request.get("professionalBrief") or {}).get("brandName")
    )
    binding = db.get(PersonalBinding, project.id)
    native_reference = (
        (binding.snapshot or {}).get("reference") if binding and not explicit_visual else None
    )
    current_fingerprint = export_source_fingerprint(slides, native_reference)
    export_matches_current = bool(
        current_pptx
        and (current_pptx.report or {}).get("sourceFingerprint") == current_fingerprint
    )
    if not export_matches_current:
        current_pptx = None
    verified_software = []
    if current_pptx:
        current_hash = hashlib.sha256(Path(current_pptx.artifact_path).read_bytes()).hexdigest()
        accepted = db.scalars(select(DeliveryVerification).where(
            DeliveryVerification.project_id == project.id,
            DeliveryVerification.file_hash == current_hash,
            DeliveryVerification.status == "accepted",
        )).all()
        # User-uploaded PDFs only report a claimed origin. They can support a
        # human review but cannot establish which application rendered them.
        verified_software = sorted({
            row.software for row in accepted
            if (row.report or {}).get("humanVerified") is True
            and not (row.report or {}).get("manualUpload")
        })
    audit = quality.get("professionalAudit", {})
    dimensions = audit.get("dimensions", {})
    maturity = quality.get("visualMaturity", {})
    accessibility = quality.get("accessibility", {})
    brand_kit = ((deck.design_system or {}).get("brandKit") or {}) if deck else {}
    research_manifest = Path(project.artifact_path) / "analysis" / "research-manifest.json"
    delivery_audits = {
        software: audit_delivery_profile(slides, software)
        for software in verified_software
    }
    delivery_score = min(
        (report.get("score", 0) for report in delivery_audits.values()),
        default=0,
    )
    delivery_success = bool(
        quality.get("passed")
        and len(verified_software) >= 2
        and delivery_score >= 80
    )
    case_results = []
    for case in FIXED_CASES:
        status = "verified"
        reason = ""
        if case["id"] == "company-template":
            if not imported_analysis:
                status, reason, passed = "not-applicable", "未导入企业模板", False
            else:
                passed = imported_analysis.get("masterCount", 0) >= 1
        elif case["id"] == "dense-data":
            passed = dimensions.get("visualDesign", 0) >= 78
        elif case["id"] == "source-completeness":
            passed = dimensions.get("completeness", 0) >= 78
        elif case["id"] == "layout-contract":
            passed = bool(slides) and all(bool(slide.get("layoutPlan")) for slide in slides)
        elif case["id"] == "narrative-rhythm":
            passed = (
                maturity.get("narrativeRhythm", 0) >= 75
                and maturity.get("silhouetteDiversity", 0) >= 70
            )
        elif case["id"] == "accessibility":
            passed = bool(accessibility.get("passed")) and accessibility.get("score", 0) >= 78
        elif case["id"] == "brand-consistency":
            passed = brand_kit.get("score", 0) >= 70
        elif case["id"] == "research-governance":
            passed = research_manifest.is_file() and bool(reproducibility.get("researchManifest"))
        elif case["id"] == "cross-platform":
            if len(verified_software) < 2:
                status, reason, passed = "not-verified", "需在至少两种演示软件中确认当前导出文件", False
            else:
                passed = delivery_score >= 80
                if not passed:
                    reason = "至少一种已验收软件存在不兼容对象，请查看交付兼容明细"
        else:
            passed = dimensions.get(case["dimension"], dimensions.get("fundamentals", 0)) >= 78
        case_results.append({**case, "passed": passed, "status": "passed" if passed else (status if status != "verified" else "failed"), "reason": reason})
    applicable = [item for item in case_results if item["status"] in {"passed", "failed"}]
    return {
        "suite": "professional-fixed-v2",
        "professionalScore": audit.get("overall", 0),
        "dimensions": dimensions,
        "slideCount": slide_count,
        "pageEditCount": edit_count,
        "editsPerSlide": round(edit_count / max(1, slide_count), 2),
        "deliverySuccess": delivery_success,
        "exportMatchesCurrentSlides": export_matches_current,
        "deliveryVerifiedWith": verified_software,
        "deliveryCompatibility": delivery_audits,
        "userSelectionRate": round(selected / max(1, slide_count), 3),
        "fixedCasesPassed": sum(item["status"] == "passed" for item in applicable),
        "fixedCasesTotal": len(applicable),
        "fixedCasesNotApplicable": sum(item["status"] == "not-applicable" for item in case_results),
        "fixedCasesNotVerified": sum(item["status"] == "not-verified" for item in case_results),
        "cases": case_results,
        "benchmarkFamilies": {
            "academic": ["source-completeness", "dense-data", "accessibility"],
            "business": ["brand-consistency", "layout-contract", "cross-platform"],
            "product": ["narrative-rhythm", "layout-contract", "multilingual-fonts"],
            "pitch": ["narrative-rhythm", "brand-consistency", "readability"],
            "training": ["accessibility", "source-completeness", "cross-platform"],
        },
    }

from app.db.models import DeckSpecRecord, SlideSpecRecord
from app.db.session import SessionLocal
from app.presentation_intelligence.brand_kit import audit_brand_application, compile_brand_kit
from app.presentation_intelligence.layout_planner import plan_deck_layouts
from app.presentation_intelligence.research_assets import (
    build_research_manifest,
    normalize_openalex,
    normalize_openverse,
)
from app.professional.delivery import audit_delivery_profile
from app.professional.governance import approval_state, can, permission_model
from app.professional.observability import append_stage_trace
from app.professional.review_diff import diff_slide_specs
from app.validation.visual_regression import compare_images, compare_render_roots
from PIL import Image


def _slide(position: int, role: str = "content") -> dict:
    return {
        "id": f"slide-{position}",
        "position": position,
        "role": role,
        "purpose": "证明核心判断",
        "message": "这是本页唯一结论",
        "content": {"title": "核心判断", "bullets": ["准确率达到 92%", "交付时间缩短 30%"]},
        "visualIntent": {"archetypeCandidates": ["metric-wall", "split", "cards"]},
        "assetBindings": [],
    }


def test_layout_planner_creates_canvas_contract_and_avoids_repetition():
    slides = [_slide(1, "data"), _slide(2, "data"), _slide(3, "conclusion")]
    summary = plan_deck_layouts(slides, "academic", {"audience": "专家"})
    assert summary["version"] == "layout-planning-v1"
    assert summary["uniqueSilhouettes"] >= 2
    assert all(slide["layoutPlan"]["regions"] for slide in slides)
    assert slides[0]["layoutPlan"]["typography"]["bodyMinPt"] >= 16


def test_brand_research_trace_diff_and_delivery_contracts():
    slide = _slide(1)
    design = {
        "palette": {"primary": "#625bf6"},
        "typography": {"fontFamily": "Arial"},
        "brand": {"name": "映章"},
    }
    kit = compile_brand_kit(design, [])
    slide["designSystem"] = {**design, "brandKit": kit}
    assert audit_brand_application([slide], kit)["score"] >= 80

    works = normalize_openalex(
        {
            "results": [
                {
                    "id": "https://openalex.org/W1",
                    "title": "Agentic slides",
                    "publication_year": 2026,
                    "doi": "https://doi.org/10.1/x",
                    "primary_location": {"source": {"display_name": "Journal"}},
                    "authorships": [],
                }
            ]
        }
    )
    images = normalize_openverse(
        {
            "results": [
                {
                    "id": "image-1",
                    "title": "Abstract",
                    "license": "cc0",
                    "url": "https://example.test/image.jpg",
                    "thumbnail": "https://example.test/thumb.jpg",
                    "creator": "A",
                    "foreign_landing_url": "https://example.test/source",
                }
            ]
        }
    )
    manifest = build_research_manifest([], [slide], {"audience": "专家"})
    assert works[0]["provider"] == "openalex"
    assert images[0]["approvedLicense"] is True
    assert manifest["providers"][0]["id"] == "openalex"

    trace = append_stage_trace({}, "planning", "正在规划", 0.35)
    assert trace["trace"][-1]["stage"] == "planning"
    changed = {**slide, "message": "已经更新的唯一结论"}
    review = diff_slide_specs(slide, changed)
    assert "message" in review["changedFields"]
    delivery = audit_delivery_profile([slide], "powerpoint-macos")
    assert delivery["profile"] == "powerpoint-macos"
    assert can("reviewer", "approve") is True
    assert can("viewer", "publish") is False
    assert permission_model()["approvalStages"] == ["content", "design", "final"]
    assert approval_state([{"stage": "final", "status": "approved"}])["readyToPublish"] is True


def test_professional_platform_endpoint_exposes_all_priorities(client):
    project = client.post("/api/v1/projects", json={"name": "Professional platform"}).json()
    response = client.get(f"/api/v1/projects/{project['id']}/professional-platform")
    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == "professional-platform-v1"
    assert set(payload) >= {"p0", "p1", "p2"}
    assert payload["p1"]["governance"]["version"] == "project-governance-v1"
    assert payload["p2"]["deliveryProfiles"]["wps"]["profile"] == "wps"


def test_visual_regression_detects_pixel_drift(tmp_path):
    baseline = tmp_path / "baseline"
    current = tmp_path / "current"
    baseline.mkdir()
    current.mkdir()
    Image.new("RGB", (40, 30), "white").save(baseline / "slide-01.png")
    Image.new("RGB", (40, 30), "white").save(current / "slide-01.png")
    assert (
        compare_images(baseline / "slide-01.png", current / "slide-01.png")["differenceRatio"] == 0
    )
    Image.new("RGB", (40, 30), "black").save(current / "slide-01.png")
    report = compare_render_roots(baseline, current, threshold=0.03)
    assert report["passed"] is False
    assert report["slides"][0]["differenceRatio"] == 1


def test_canvas_layout_is_versioned_and_bounds_checked(client):
    project = client.post("/api/v1/projects", json={"name": "Canvas layout"}).json()
    spec = _slide(1)
    spec["layoutPlan"] = {
        "version": "composition-plan-v1",
        "regions": [
            {"id": "primary", "x": 0, "y": 2, "w": 7, "h": 8, "priority": 90},
            {"id": "support", "x": 7.5, "y": 2, "w": 4.5, "h": 8, "priority": 70},
        ],
    }
    with SessionLocal() as db:
        db.add(
            DeckSpecRecord(
                project_id=project["id"], narrative={}, design_system={}, reproducibility={}
            )
        )
        db.add(SlideSpecRecord(id=spec["id"], project_id=project["id"], position=1, spec=spec))
        db.commit()
    response = client.put(
        f"/api/v1/projects/{project['id']}/slides/{spec['id']}/layout",
        json={
            "focal_point": "left",
            "regions": [
                {"id": "primary", "x": 0, "y": 2, "w": 5, "h": 8, "priority": 90, "locked": False},
                {
                    "id": "support",
                    "x": 5.5,
                    "y": 2,
                    "w": 6.5,
                    "h": 8,
                    "priority": 70,
                    "locked": True,
                },
            ],
        },
    )
    assert response.status_code == 200
    assert response.json()["layoutPlan"]["manualOverride"] is True
    assert response.json()["version"] == 2
    invalid = client.put(
        f"/api/v1/projects/{project['id']}/slides/{spec['id']}/layout",
        json={
            "focal_point": "right",
            "regions": [{"id": "primary", "x": 10, "y": 2, "w": 4, "h": 4}],
        },
    )
    assert invalid.status_code == 422


def test_slide_version_routes_enforce_project_ownership(client):
    owner = client.post("/api/v1/projects", json={"name": "Slide owner"}).json()
    outsider = client.post("/api/v1/projects", json={"name": "Other project"}).json()
    spec = _slide(1)
    spec["id"] = "ownership-slide"
    with SessionLocal() as db:
        db.add(
            SlideSpecRecord(
                id=spec["id"], project_id=owner["id"], position=1, spec=spec
            )
        )
        db.commit()

    prefix = f"/api/v1/projects/{outsider['id']}/slides/{spec['id']}"
    assert client.get(f"{prefix}/versions").status_code == 404
    assert client.get(f"{prefix}/versions/diff?from_version=1&to_version=2").status_code == 404
    assert client.post(f"{prefix}/rollback/1").status_code == 404
    assert client.put(
        f"{prefix}/layout",
        json={"regions": [{"id": "primary", "x": 0, "y": 0, "w": 4, "h": 4}]},
    ).status_code == 404

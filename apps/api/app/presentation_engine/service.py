import copy
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from app.personalization.runtime import assert_current, generation_snapshot, lock


class EngineError(RuntimeError):
    pass


class PresentationEngine:
    def __init__(self):
        self.cli = Path("packages/presentation-engine/src/cli.mjs").resolve()

    def run(self, command: str, slides: list[dict], output: Path) -> None:
        if generation_snapshot.get():
            assert_current()
            output.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix=".personal-render-", dir=output.parent) as folder:
                staged = Path(folder) / output.name
                if command == "assemble" and output.is_dir():
                    shutil.copytree(output, staged)
                self._run(command, slides, staged)
                with lock:
                    assert_current()
                    if output.is_dir():
                        shutil.rmtree(output)
                    elif output.exists():
                        output.unlink()
                    staged.replace(output)
            return
        with lock:
            assert_current()
        self._run(command, slides, output)
        assert_current()

    def _run(self, command: str, slides: list[dict], output: Path) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        spec_path = output.parent / "slides.input.json"
        spec_path.write_text(json.dumps(slides, ensure_ascii=False, indent=2), encoding="utf-8")
        result = subprocess.run(
            ["node", str(self.cli), command, str(spec_path), str(output)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
            check=False,
        )
        if result.returncode:
            raise EngineError(result.stderr.strip() or result.stdout.strip())
        if command == "build" and any(slide.get("personalizationBaseline") for slide in slides):
            self._compare_personal_style(slides, output)

    def _compare_personal_style(self, slides, output):
        from app.validation.render_safety import safe_render_candidate
        baseline = copy.deepcopy(slides)
        for slide in baseline:
            original = slide.pop("personalizationBaseline", None)
            if original:
                slide["designSystem"] = original
        dimensions = ("overall", "geometry", "readability", "contentFit", "semanticFit", "hierarchy", "visualEvidence")
        with tempfile.TemporaryDirectory(prefix=".style-baseline-", dir=output.parent) as folder:
            root = Path(folder) / "rendered"
            self._run("build", baseline, root)
            assembled = copy.deepcopy(slides)
            for index, slide in enumerate(assembled):
                page = output / "slides" / str(slide["position"])
                ordinary_page = root / "slides" / str(slide["position"])
                chosen = json.loads((page / "current.json").read_text(encoding="utf-8"))
                ordinary = json.loads((ordinary_page / "current.json").read_text(encoding="utf-8"))
                actual_score, baseline_score = chosen["scoreDetail"], ordinary["scoreDetail"]
                protected = (slide.get("visualIntent") or {}).get("variantSelectionSource") in {"user", "critic"}
                accepted = safe_render_candidate(actual_score) and all(actual_score.get(key, 0) >= baseline_score.get(key, 0) for key in dimensions)
                if not protected and safe_render_candidate(baseline_score) and not accepted:
                    shutil.rmtree(page)
                    shutil.copytree(ordinary_page, page)
                    chosen = ordinary
                    slide["designSystem"] = baseline[index]["designSystem"]
                chosen["designSystem"] = slide.get("designSystem", {})
                chosen["personalizationQA"] = {"baselinePassed": safe_render_candidate(baseline_score),
                    "personalPassed": safe_render_candidate(actual_score), "accepted": accepted,
                    "protectedSelection": protected, "dimensions": list(dimensions)}
                (page / "current.json").write_text(json.dumps(chosen, ensure_ascii=False, indent=2), encoding="utf-8")
                slide.setdefault("visualIntent", {})["selectedVariant"] = chosen["variant"]
            self._run("assemble", assembled, output)

    def export_pdf(self, html: Path, output: Path) -> None:
        result = subprocess.run(
            ["node", str(self.cli), "pdf", str(html), str(output)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
            check=False,
        )
        if result.returncode:
            raise EngineError(result.stderr.strip() or result.stdout.strip())


presentation_engine = PresentationEngine()

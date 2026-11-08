import json
import sys
import zipfile

import pymupdf
import pytest
from app.config import settings
from app.documents import parse_source
from app.documents.backends import normalize_math, trigger_reason
from app.documents.latex_math import LatexError, attach_slide_math, to_linear, to_mathml, to_omml
from app.powerpoint.equations import convert_slide_xml, inject_native_equations

SLIDE = (
    '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:cSld><p:spTree><p:sp><p:txBody>'
    '<a:p><a:r><a:rPr lang="zh-CN" sz="2000"/><a:t>总损失 $$L=\\frac{1}{N}\\sum_{i=1}^{N} e_i^2$$ 越小越好</a:t></a:r></a:p>'
    '<a:p><a:r><a:rPr sz="1800"/><a:t>$$\\unsupported{x}$$</a:t></a:r></a:p>'
    "</p:txBody></p:sp></p:spTree></p:cSld></p:sld>"
)


def test_latex_subset_to_mathml_omml_and_linear():
    mathml = to_mathml(r"\frac{a}{b}+\sqrt[3]{x}+\sum_{i=1}^{n} x_i")
    assert "<mfrac>" in mathml and "<mroot>" in mathml and "<munderover>" in mathml
    omml = to_omml(r"\left( \alpha^2 \right) \leq \hat{y}")
    assert "<m:d>" in omml and "<m:sSup>" in omml and "<m:acc>" in omml and "≤" in omml
    assert to_linear(r"E=mc^2") == "E = mc²"
    with pytest.raises(LatexError):
        to_mathml(r"\begin{matrix}a\end{matrix}")


def test_attach_slide_math_only_keeps_supported_formulas():
    slide = {"content": {"title": "t", "bullets": ["$$x^2$$ 与 $$\\weird{y}$$"]}}
    assert attach_slide_math(slide) == 1
    assert slide["math"][0]["latex"] == "x^2" and slide["math"][0]["mathml"].startswith("<math")


def test_pptx_post_processor_writes_native_equation_with_readable_fallback():
    data, count = convert_slide_xml(SLIDE.encode())
    text = data.decode()
    assert count == 1
    assert 'mc:Choice Requires="a14"' in text and "<m:nary>" in text and "<m:f>" in text
    assert "1/N∑ᵢ₌₁ᴺ" in text  # fallback is readable Unicode, not LaTeX
    assert "越小越好" in text and "总损失" in text
    assert "$$\\unsupported{x}$$" in text  # unsupported formulas are left untouched
    linear, _ = convert_slide_xml(SLIDE.encode(), "linear")
    assert "<m:oMath>" not in linear.decode() and "1/N" in linear.decode()


def test_inject_native_equations_rewrites_pptx(tmp_path):
    target = tmp_path / "deck.pptx"
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("ppt/slides/slide1.xml", SLIDE)
        archive.writestr("[Content_Types].xml", "<Types/>")
    result = inject_native_equations(target)
    assert result["equations"] == 1
    with zipfile.ZipFile(target) as archive:
        assert "<m:oMath>" in archive.read("ppt/slides/slide1.xml").decode()
        assert archive.read("[Content_Types].xml") == b"<Types/>"


def test_normalize_math_and_trigger_policy(monkeypatch):
    assert normalize_math("能量 $E=mc^2$ 与 $5 元") == "能量 $$E=mc^2$$ 与 $5 元"
    assert normalize_math("$$\n\\frac{a}{b}\n$$") == "$$\\frac{a}{b}$$"
    monkeypatch.setattr(settings, "document_parser", "builtin")
    assert trigger_reason([{"code": "ocr-required"}], "") is None
    monkeypatch.setattr(settings, "document_parser", "mineru")
    monkeypatch.setattr(settings, "document_parser_policy", "auto")
    assert trigger_reason([{"code": "ocr-required"}], "") == "scanned-or-table-pages"
    assert trigger_reason([], "正文") is None
    assert trigger_reason([], "∑ x ≤ y ≈ z") == "formulas"


def _pdf_bytes(text: str) -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    return document.tobytes()


def test_external_parser_command_replaces_weak_pdf_text(tmp_path, monkeypatch):
    script = tmp_path / "fake_parser.py"
    script.write_text(
        "import json,sys,pathlib\n"
        "out=pathlib.Path(sys.argv[2])/'doc'/'auto'; out.mkdir(parents=True)\n"
        "(out/'doc.md').write_text('# Results\\n\\nAccuracy reached 92% with loss $L=\\\\frac{1}{N}$ on 100 samples.\\n\\n"
        "| Model | Accuracy |\\n| --- | --- |\\n| Ours | 92% |\\n| Baseline | 71% |\\n', encoding='utf-8')\n"
        "(out/'doc_content_list.json').write_text(json.dumps([{'type':'text','text':'Results','page_idx':0}]), encoding='utf-8')\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "document_parser", "command")
    monkeypatch.setattr(settings, "document_parser_policy", "always")
    monkeypatch.setattr(settings, "document_parser_command", f"{sys.executable} {script} {{input}} {{output}}")
    parsed = parse_source("paper.pdf", _pdf_bytes("scan"), "application/pdf")
    codes = {item["code"] for item in parsed["readingWarnings"]}
    assert "external-parser" in codes
    assert parsed["sections"][0]["title"] == "Results" and parsed["sections"][0]["page"] == 1
    assert "$$L=\\frac{1}{N}$$" in parsed["sections"][0]["text"]
    assert parsed["tables"] and parsed["tables"][0]["section"] == parsed["sections"][0]["id"]


def test_external_parser_failure_keeps_builtin(monkeypatch):
    monkeypatch.setattr(settings, "document_parser", "command")
    monkeypatch.setattr(settings, "document_parser_policy", "always")
    monkeypatch.setattr(settings, "document_parser_command", "definitely-not-installed-parser {input} {output}")
    parsed = parse_source("paper.pdf", _pdf_bytes("Revenue grew 12% in the pilot region this year."), "application/pdf")
    assert "external-parser-failed" in {item["code"] for item in parsed["readingWarnings"]}
    assert "Revenue grew 12%" in json.dumps(parsed["sections"])


def test_document_parser_status_endpoint(client):
    status = client.get("/api/v1/document-parser").json()
    assert status["backend"] in {"builtin", "mineru", "paddleocr-vl", "command"}
    assert "mineru" in status["presets"]


def test_engine_renders_mathml_and_exports_native_equation(tmp_path):
    from app.presentation_engine.service import presentation_engine
    from app.presentation_intelligence.art_director import build_design_system

    slide = {"id": "eq", "position": 1, "role": "method", "message": "目标函数",
             "content": {"title": "模型目标函数", "bullets": ["总损失为 $$L=\\frac{1}{N}\\sum_{i=1}^{N} e_i^2$$ 的均方形式", "收敛速度与 $$\\sqrt{n}$$ 成正比"]},
             "visualIntent": {}, "designSystem": build_design_system("academic", [], {})}
    presentation_engine.run("build", [slide], tmp_path / "rendered")
    current = json.loads((tmp_path / "rendered" / "slides" / "1" / "current.json").read_text(encoding="utf-8"))
    assert not current["scoreDetail"]["needsReview"], current["scoreDetail"]["issues"]
    html = (tmp_path / "rendered" / "slides" / "1.html").read_text(encoding="utf-8")
    assert html.count("<math") == 2 and "data-pptx-text" in html
    slide["visualIntent"]["selectedVariant"] = current["variant"]
    presentation_engine.run("pptx", [slide], tmp_path / "deck.pptx", scene_root=tmp_path / "rendered")
    with zipfile.ZipFile(tmp_path / "deck.pptx") as archive:
        xml = archive.read("ppt/slides/slide1.xml").decode()
    assert xml.count("<m:oMath>") == 2
    report = json.loads((tmp_path / "deck.export.json").read_text(encoding="utf-8"))
    assert report["nativeEquations"]["equations"] == 2

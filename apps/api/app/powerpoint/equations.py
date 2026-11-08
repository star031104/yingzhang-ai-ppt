"""Turn ``$$…$$`` formulas in an exported PPTX into native, editable PowerPoint equations.

The scene compiler writes formulas as plain text runs. This post-processor finds
those runs in every slide and replaces each formula with the structure PowerPoint
itself saves for equations::

    <mc:AlternateContent>
      <mc:Choice Requires="a14"><a14:m><m:oMathPara>…OMML…</m:oMathPara></a14:m></mc:Choice>
      <mc:Fallback><a:r>…plain LaTeX text…</a:r></mc:Fallback>
    </mc:AlternateContent>

Readers without Office 2010 math support (older LibreOffice builds) show the
fallback text, so nothing is lost. Formulas outside the supported LaTeX subset are
left untouched.
"""

from __future__ import annotations

import copy
import io
import re
import zipfile
from pathlib import Path

from lxml import etree

from app.documents.latex_math import LatexError, math_segments, to_linear, to_omml

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "a14": "http://schemas.microsoft.com/office/drawing/2010/main",
}
SLIDE_RE = re.compile(r"^ppt/slides/slide\d+\.xml$")


def _q(prefix: str, name: str) -> str:
    return f"{{{NS[prefix]}}}{name}"


def _math_element(latex: str, size: int | None, template_rpr, display: bool) -> etree._Element:
    """Inline formulas use ``a14:m/m:oMath``; a formula alone in its paragraph uses ``m:oMathPara``."""
    omml = to_omml(latex, size)
    fallback_rpr = etree.tostring(template_rpr).decode() if template_rpr is not None else "<a:rPr/>"
    body = (
        f'<m:oMathPara><m:oMathParaPr><m:jc m:val="left"/></m:oMathParaPr>{omml}</m:oMathPara>' if display else omml
    )
    xml = (
        f'<mc:AlternateContent xmlns:mc="{NS["mc"]}" xmlns:a="{NS["a"]}" xmlns:a14="{NS["a14"]}" xmlns:m="{NS["m"]}">'
        f'<mc:Choice Requires="a14"><a14:m>{body}</a14:m></mc:Choice>'
        f"<mc:Fallback><a:r>{fallback_rpr}<a:t>{_xml_text(to_linear(latex))}</a:t></a:r></mc:Fallback></mc:AlternateContent>"
    )
    return etree.fromstring(xml)


def _xml_text(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _convert_paragraph(paragraph: etree._Element, mode: str = "native") -> int:
    runs = paragraph.findall("a:r", NS)
    if not runs:
        return 0
    text = "".join((run.findtext("a:t", default="", namespaces=NS) or "") for run in runs)
    if "$$" not in text:
        return 0
    segments = math_segments(text)
    if not any(kind == "math" for kind, _ in segments):
        return 0
    template_rpr = runs[0].find("a:rPr", NS)
    size = int(template_rpr.get("sz")) if template_rpr is not None and template_rpr.get("sz", "").isdigit() else None
    built = []
    converted = 0
    display = len([item for item in segments if item[0] == "math" or item[1].strip()]) == 1
    for kind, value in segments:
        if kind == "math":
            try:
                if mode == "linear":
                    value = to_linear(value)
                    converted += 1
                else:
                    built.append(_math_element(value, size, template_rpr, display))
                    converted += 1
                    continue
            except (LatexError, etree.XMLSyntaxError):
                value = f"$${value}$$"
        if not value:
            continue
        run = etree.Element(_q("a", "r"))
        if template_rpr is not None:
            run.append(copy.deepcopy(template_rpr))
        node = etree.SubElement(run, _q("a", "t"))
        node.text = value
        built.append(run)
    if not converted:
        return 0
    anchor = runs[0]
    index = list(paragraph).index(anchor)
    for run in runs:
        paragraph.remove(run)
    for offset, element in enumerate(built):
        paragraph.insert(index + offset, element)
    return converted


def _ensure_ignorable(root: etree._Element) -> etree._Element:
    """Declare mc/a14/m on the slide root so the a14 requirement resolves."""
    if root.nsmap.get("a14") == NS["a14"] and root.nsmap.get("mc") == NS["mc"]:
        return root
    nsmap = dict(root.nsmap)
    nsmap.update({"mc": NS["mc"], "a14": NS["a14"], "m": NS["m"]})
    replacement = etree.Element(root.tag, nsmap=nsmap, attrib=dict(root.attrib))
    for child in root:
        replacement.append(child)
    ignorable = replacement.get(_q("mc", "Ignorable"), "")
    if "a14" not in ignorable.split():
        replacement.set(_q("mc", "Ignorable"), (ignorable + " a14").strip())
    return replacement


def convert_slide_xml(data: bytes, mode: str = "native") -> tuple[bytes, int]:
    root = etree.fromstring(data)
    count = 0
    for paragraph in list(root.iter(_q("a", "p"))):
        count += _convert_paragraph(paragraph, mode)
    if not count:
        return data, 0
    if mode != "linear":
        root = _ensure_ignorable(root)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True), count


def inject_native_equations(pptx: Path, mode: str = "native") -> dict:
    """Rewrite ``pptx`` in place; returns ``{"equations": n, "slides": [...], "mode": mode}``.

    ``mode="linear"`` writes readable Unicode text (``L = 1/N ∑ᵢ₌₁ᴺ …``) instead of OMML,
    for decks whose target viewer lacks Office equation support.
    """
    with zipfile.ZipFile(pptx) as archive:
        entries = [(info, archive.read(info.filename)) for info in archive.infolist()]
    total, slides = 0, []
    rewritten = []
    for info, data in entries:
        if SLIDE_RE.match(info.filename) and b"$$" in data:
            data, count = convert_slide_xml(data, mode)
            if count:
                total += count
                slides.append(info.filename)
        rewritten.append((info, data))
    if not total:
        return {"equations": 0, "slides": [], "mode": mode}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for info, data in rewritten:
            archive.writestr(info, data)
    pptx.write_bytes(buffer.getvalue())
    return {"equations": total, "slides": slides, "mode": mode}

"""Preserve document order, heading ancestry and the meaning of table cells."""
import io
import re
from datetime import date, datetime
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from PIL import Image


def cell_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value).strip()


def table_record(rows: list, *, table_id: str, document: str, section: str,
                 caption: str = "", page: int | None = None, row_offset: int = 0) -> dict:
    values = [[cell_text(cell) for cell in row] for row in rows]
    values = [row for row in values if any(row)]
    # PDF table detectors often return a merged title row before the real
    # column headers.  Using that row as the header produced statements such
    # as ``项目：：第 1 年；：第 2 年``; the presentation engine could neither
    # reconstruct a native table nor build a chart from those anonymous
    # columns.  Keep the raw rows for provenance, but locate the first row
    # that actually describes at least two columns for semantic statements.
    header_index = 0
    if len(values) >= 2:
        first_nonempty = sum(bool(cell) for cell in values[0])
        second_nonempty = sum(bool(cell) for cell in values[1])
        if first_nonempty <= 1 and second_nonempty >= 2:
            header_index = 1
    headers = values[header_index] if values else []
    statements = []
    for index, row in enumerate(values[header_index + 1:], 1):
        fields = []
        for column in range(1, max(len(row), len(headers))):
            header = headers[column] if column < len(headers) else f"列{column + 1}"
            value = row[column] if column < len(row) else ""
            unit_match = re.search(r"[（(]\s*(%|秒|毫秒|分钟|小时|元|万元|亿元|ms|个|人)\s*[）)]", header)
            unit = unit_match.group(1) if unit_match else ""
            label = header[:unit_match.start()].strip() if unit_match else header
            if value and unit and re.fullmatch(r"[-+−]?\d[\d,]*(?:\.\d+)?", value):
                value += unit
            fields.append(f"{label}：{value or '未提供'}")
        subject = row[0] or f"数据行 {index + row_offset}"
        statements.append(f"{subject}：{'；'.join(fields)}" if fields else subject)
    return {"id": table_id, "document": document, "section": section, "page": page,
            "caption": caption, "headers": headers, "rows": values, "rowStatements": statements,
            "headerRowIndex": header_index, "rowCount": len(statements),
            "sourceRef": {"document": document, "section": section, "page": page}}


def table_text(table: dict) -> str:
    return "\n\n".join(filter(None, [table.get("caption"), *table.get("rowStatements", [])]))


def parse_docx_structure(name: str, data: bytes, asset_dir: Path | None) -> tuple[list, list, list]:
    document = Document(io.BytesIO(data))
    sections, tables, figures, ancestry = [], [], [], []
    current = None
    children = list(document.element.body)

    def begin(title: str, level: int = 1):
        nonlocal current
        while ancestry and ancestry[-1][0] >= level:
            ancestry.pop()
        ancestry.append((level, title))
        current = {"id": f"S{len(sections) + 1:03d}", "title": title, "text": "", "page": None,
                   "headingLevel": level, "headingPath": [item[1] for item in ancestry], "blocks": []}
        sections.append(current)

    for index, child in enumerate(children):
        if child.tag == qn("w:p"):
            paragraph = Paragraph(child, document)
            text = paragraph.text.strip()
            style = paragraph.style.name if paragraph.style else ""
            match = re.search(r"(?:Heading|标题)\s*([1-9])", style, re.IGNORECASE)
            outline = child.find("./" + qn("w:pPr") + "/" + qn("w:outlineLvl"))
            level = int(match[1]) if match else int(outline.get(qn("w:val"))) + 1 if outline is not None else None
            if text and (level or style.lower() == "title"):
                begin(text, level or 0)
                continue
            if current is None:
                begin(document.core_properties.title or Path(name).stem)
            if text:
                current["blocks"].append({"type": "caption" if re.match(r"^(?:图|表|Figure|Table)\s*\d", text, re.IGNORECASE) else "paragraph", "text": text})
            for blip in child.iter(qn("a:blip")):
                rid = blip.get(qn("r:embed"))
                part = document.part.related_parts.get(rid)
                if not part:
                    continue
                try:
                    with Image.open(io.BytesIO(part.blob)) as image:
                        width, height = image.size
                except (OSError, ValueError):
                    continue
                caption = ""
                for neighbor in children[index + 1:index + 3]:
                    if neighbor.tag == qn("w:p"):
                        candidate = Paragraph(neighbor, document).text.strip()
                        if re.match(r"^(?:图|Figure)\s*\d", candidate, re.IGNORECASE):
                            caption = candidate
                            break
                path = None
                figure_id = f"FIG-DOCX-{len(figures) + 1:03d}"
                if asset_dir is not None:
                    asset_dir.mkdir(parents=True, exist_ok=True)
                    target = asset_dir / f"{figure_id}{Path(str(part.partname)).suffix}"
                    target.write_bytes(part.blob)
                    path = str(target.resolve())
                figures.append({"id": figure_id, "document": name, "section": current["id"], "page": None,
                                "path": path, "width": width, "height": height, "caption": caption,
                                "kind": "diagram" if re.search(r"架构|流程|框架|architecture|workflow", caption, re.IGNORECASE) else "figure",
                                "provenance": f"{name} · {current['title']}" + (f" · {caption}" if caption else "")})
                current["blocks"].append({"type": "figure", "figureId": figure_id, "text": caption})
        elif child.tag == qn("w:tbl"):
            if current is None:
                begin(Path(name).stem)
            previous = current["blocks"][-1] if current["blocks"] else {}
            caption = previous.get("text", "") if previous.get("type") == "caption" else current["title"]
            table = table_record([[cell.text for cell in row.cells] for row in Table(child, document).rows],
                                 table_id=f"TABLE-DOCX-{len(tables) + 1:03d}", document=name,
                                 section=current["id"], caption=caption)
            tables.append(table)
            current["blocks"].append({"type": "table", "tableId": table["id"], "text": table_text(table)})
    for section in sections:
        section["text"] = "\n\n".join(block["text"] for block in section["blocks"] if block.get("text"))
    return sections, figures, tables

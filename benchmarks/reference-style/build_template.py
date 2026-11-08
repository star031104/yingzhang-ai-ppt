"""Deterministically build a synthetic enterprise PPTX template for the reference-style benchmark.

Nothing here comes from a real company: the brand ("北辰示例集团"), colours and copy
are invented. The template has a branded master (colour band + footer rule), named
layouts for cover, section, content, comparison and closing pages, and six example
slides whose fonts and colours the reference analyzer should learn.

Usage: python benchmarks/reference-style/build_template.py <output.pptx>
"""

from __future__ import annotations

import sys
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Emu, Pt

BRAND = "北辰示例集团"
FONT = "Source Han Sans SC"
PRIMARY = RGBColor(0x0B, 0x5C, 0xAD)
ACCENT = RGBColor(0xF2, 0x9F, 0x05)
INK = RGBColor(0x1C, 0x24, 0x33)
LAYOUT_NAMES = {
    0: "封面 Cover",
    1: "正文 Content",
    2: "章节 Section",
    4: "对比 Comparison",
    5: "结束 Closing",
}
EXAMPLES = [
    (0, "北辰示例集团 2026 年度经营汇报", ["示例数据 · 仅用于模板基准"]),
    (2, "第一部分 经营概览", []),
    (1, "核心经营指标保持稳健", ["收入同比增长 12%", "毛利率提升到 41%", "客户续约率达到 93%"]),
    (4, "两种渠道策略对比", ["直销：客单价高、周期长", "伙伴：覆盖广、毛利低"]),
    (1, "下一步行动建议", ["优先扩大伙伴渠道试点", "第三季度复盘试点结果"]),
    (5, "谢谢", ["欢迎提问"]),
]


def _style_runs(shape, size: int, color: RGBColor, bold: bool = False) -> None:
    for paragraph in shape.text_frame.paragraphs:
        for run in paragraph.runs:
            run.font.name = FONT
            run.font.size = Pt(size)
            run.font.bold = bold
            run.font.color.rgb = color


def build(output: Path) -> Path:
    deck = Presentation()
    deck.slide_width, deck.slide_height = Emu(12192000), Emu(6858000)
    master = deck.slide_master
    # python-pptx cannot add shapes to a master directly: draw them on a scratch slide,
    # move their XML into the master shape tree, then drop the scratch slide.
    scratch = deck.slides.add_slide(deck.slide_layouts[6])
    for name, color, box in (
        ("Brand Band", PRIMARY, (0, 0, 12192000, 228600)),
        ("Footer Rule", ACCENT, (457200, 6400800, 11277600, 22860)),
    ):
        shape = scratch.shapes.add_shape(MSO_SHAPE.RECTANGLE, *(Emu(value) for value in box))
        shape.fill.solid()
        shape.fill.fore_color.rgb = color
        shape.line.fill.background()
        shape.name = name
        master.shapes._spTree.append(shape._element)
    slide_id = deck.slides._sldIdLst[-1]
    deck.part.drop_rel(slide_id.rId)
    deck.slides._sldIdLst.remove(slide_id)
    for index, name in LAYOUT_NAMES.items():
        deck.slide_layouts[index].name = name
    for layout_index, title, bullets in EXAMPLES:
        slide = deck.slides.add_slide(deck.slide_layouts[layout_index])
        slide.shapes.title.text = title
        _style_runs(slide.shapes.title, 40 if layout_index in {0, 2, 5} else 32, PRIMARY, bold=True)
        body = next((shape for shape in slide.placeholders if shape.placeholder_format.idx == 1), None)
        if body is not None and bullets:
            body.text_frame.text = bullets[0]
            for item in bullets[1:]:
                body.text_frame.add_paragraph().text = item
            _style_runs(body, 20, INK)
    output.parent.mkdir(parents=True, exist_ok=True)
    deck.save(output)
    return output


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "template.pptx")
    print(build(target))

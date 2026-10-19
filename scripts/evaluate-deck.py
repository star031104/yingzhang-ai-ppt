"""Evaluate a deck offline with PPTEval, PaperQuiz and render review.

Deterministic by default (no network). Examples:

  python scripts/evaluate-deck.py benchmarks/data-dashboard/fixture.md --preset data
  python scripts/evaluate-deck.py material.pdf --deck slides.json --pptx deck.pptx --kinds ppteval,quiz,render
  python scripts/evaluate-deck.py material.md --model qwen-plus --base-url https://example/v1 \\
      --api-key-env EVAL_API_KEY --vision-model qwen-vl-max
"""

import argparse
import asyncio
import json
import mimetypes
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.documents import parse_source
from app.evaluation.judges import judge_from_settings
from app.evaluation.runner import KINDS, run_evaluations
from app.presentation_intelligence.planner import plan_deck
from app.validation.quality import validate_deck


def load_deck(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    slides = payload.get("slides") if isinstance(payload, dict) else payload
    if not isinstance(slides, list) or not all(isinstance(item, dict) for item in slides):
        raise SystemExit("--deck 必须是页面规格数组，或包含 slides 数组的 JSON 对象")
    for index, slide in enumerate(slides, 1):
        slide.setdefault("position", index)
        slide.setdefault("content", {})
    return slides


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PPTEval / PaperQuiz / 渲染复核的离线评测")
    parser.add_argument("sources", nargs="+", type=Path, help="材料文件（md、txt、pdf、docx 等）")
    parser.add_argument("--deck", type=Path, help="页面规格 JSON；省略时按材料规划一份基准演示")
    parser.add_argument("--preset", default="business", help="省略 --deck 时的规划预设")
    parser.add_argument("--slides", type=int, default=8, help="省略 --deck 时的规划页数")
    parser.add_argument("--pptx", type=Path, help="导出的 PPTX，用于渲染复核")
    parser.add_argument("--kinds", default="", help="逗号分隔：ppteval,quiz,render（默认 ppteval,quiz；给出 --pptx 时加 render）")
    parser.add_argument("--questions", type=int, default=18, help="测验题目数量")
    parser.add_argument("--model", help="文本评审 / 出题模型 ID（OpenAI 兼容接口）")
    parser.add_argument("--vision-model", help="视觉评审模型 ID")
    parser.add_argument("--base-url", help="OpenAI 兼容接口地址")
    parser.add_argument("--api-key-env", default="EVAL_API_KEY", help="保存密钥的环境变量名")
    parser.add_argument("--out", type=Path, help="完整结果 JSON 输出路径")
    parser.add_argument("--work-dir", type=Path, help="渲染页面输出目录（默认临时目录）")
    return parser


async def evaluate(args: argparse.Namespace) -> dict:
    sources = []
    for path in args.sources:
        if not path.is_file():
            raise SystemExit(f"找不到材料文件：{path}")
        media_type = mimetypes.guess_type(path.name)[0] or "text/markdown"
        sources.append(parse_source(path.name, path.read_bytes(), media_type))
    slides = load_deck(args.deck) if args.deck else plan_deck(sources, args.sources[0].stem, args.preset, args.slides)["slides"]
    kinds = [item.strip() for item in args.kinds.split(",") if item.strip()] or (
        ["ppteval", "quiz", "render"] if args.pptx else ["ppteval", "quiz"]
    )
    unknown = sorted(set(kinds) - set(KINDS))
    if unknown:
        raise SystemExit(f"未知评测类型：{', '.join(unknown)}")
    text_judge = vision_judge = None
    if args.model or args.vision_model:
        if not args.base_url:
            raise SystemExit("使用模型时必须提供 --base-url")
        api_key = os.environ.get(args.api_key_env)
        if args.model:
            text_judge = judge_from_settings(args.base_url, api_key, args.model, False)
        if args.vision_model:
            vision_judge = judge_from_settings(args.base_url, api_key, args.vision_model, True)
    report = validate_deck(slides, sources)
    with tempfile.TemporaryDirectory(prefix="yingzhang-eval-") as temporary:
        work = args.work_dir or Path(temporary)
        results = await run_evaluations(
            kinds, slides=slides, sources=sources, quality_report=report, output_root=work,
            pptx=args.pptx, text_judge=text_judge, vision_judge=vision_judge, max_questions=args.questions,
        )
    return results


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    results = asyncio.run(evaluate(args))
    if args.out:
        args.out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"kinds": results["kinds"], "summary": results["summary"],
                      "missingFacts": (results.get("quiz") or {}).get("missingFacts", [])[:5]},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

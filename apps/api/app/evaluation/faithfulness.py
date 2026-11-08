"""Per-claim source-seeking faithfulness and figure-claim alignment.

Each audience-visible claim (title, message, bullet) is searched for in the source
material with BM25; the best chunk is then checked deterministically:

* ``supported``   – lexical support and every number/unit of the claim is present
* ``partial``     – lexical support, but at least one number is missing or a
                    qualifier of the chunk ("不含", "试点" ...) is dropped
* ``unsupported`` – no chunk carries enough of the claim

An optional text judge re-grades only the uncertain claims (``partial`` and
``unsupported``) with the retrieved chunk, so model cost is bounded and the
deterministic verdict remains the merge-gate signal.

Figure-claim alignment checks that a source figure placed on a slide comes from a
section that actually supports the slide's claims (UniPPTEval's figure–claim
alignment, computed without a vision model).
"""

from __future__ import annotations

import re
from typing import Any

from app.evaluation.common import NAVIGATION_ROLES, parse_json_object, short, tokens
from app.evaluation.quiz import number_keys
from app.intelligence.bm25 import BM25Index

VERSION = "faithfulness-v1"
QUALIFIERS = ("不含", "不包括", "除外", "仅", "试点", "样本", "预计", "预测", "估算", "假设", "口径", "同比", "环比", "约")
MIN_SUPPORT = 0.34


def _real_sources(sources: list[dict]) -> list[dict]:
    return [source for source in sources if not source.get("synthetic")]


def source_chunks(sources: list[dict]) -> list[dict]:
    chunks = []
    for source in _real_sources(sources):
        for section in source.get("sections", []):
            text = f"{section.get('title', '')}\n{section.get('text', '')}".strip()
            if not text:
                continue
            # Long sections are windowed so one claim is matched against a local span.
            paragraphs = [part for part in re.split(r"\n{2,}", text) if part.strip()] or [text]
            window: list[str] = []
            for paragraph in paragraphs:
                window.append(paragraph)
                if sum(len(item) for item in window) >= 900:
                    chunks.append(_chunk(source, section, "\n".join(window)))
                    window = window[-1:]
            if window:
                chunks.append(_chunk(source, section, "\n".join(window)))
    return chunks


def _chunk(source: dict, section: dict, text: str) -> dict:
    return {
        "document": source.get("name"),
        "section": section.get("id"),
        "page": section.get("page"),
        "title": section.get("title", ""),
        "text": text,
    }


def slide_claims(slide: dict) -> list[dict]:
    """Audience-visible claims; navigation pages and bare titles without facts are skipped."""
    if slide.get("role") in NAVIGATION_ROLES:
        return []
    content = slide.get("content") or {}
    claims = []
    message = str(slide.get("message") or "").strip()
    # Short label-like messages ("研究结论、贡献与局限") carry no checkable fact.
    if message and message != str(content.get("title", "")).strip() and (len(message) > 14 or number_keys(message)):
        claims.append({"kind": "message", "text": message})
    for index, bullet in enumerate(content.get("bullets") or []):
        text = str(bullet).strip()
        if len(text) >= 6:
            claims.append({"kind": "bullet", "index": index, "text": text})
    title = str(content.get("title", "")).strip()
    if title and number_keys(title):
        claims.append({"kind": "title", "text": title})
    return claims


def grade_claim(claim: str, chunk: dict | None) -> dict:
    if not chunk:
        numbers = sorted(f"{value:g}{unit}" for value, unit in number_keys(claim))
        return {"verdict": "unsupported", "support": 0.0, "missingNumbers": numbers}
    claim_tokens = tokens(claim)
    chunk_tokens = tokens(chunk["text"])
    support = len(claim_tokens & chunk_tokens) / max(1, len(claim_tokens))
    claim_numbers = {key for key in number_keys(claim) if not (key[1] == "" and 1900 <= key[0] <= 2100)}
    chunk_numbers = number_keys(chunk["text"])
    chunk_values = {value for value, _ in chunk_numbers}
    missing = sorted(
        f"{value:g}{unit}" for value, unit in claim_numbers
        if (value, unit) not in chunk_numbers and not (unit == "" and value in chunk_values)
    )
    dropped = [word for word in QUALIFIERS if word in chunk["text"] and word not in claim and _near_numbers(chunk["text"], word, claim_numbers)]
    if support < MIN_SUPPORT and not (claim_numbers and not missing):
        verdict = "unsupported"
    elif missing:
        verdict = "unsupported" if len(missing) == len(claim_numbers) and support < 0.5 else "partial"
    elif dropped:
        verdict = "partial"
    else:
        verdict = "supported"
    return {"verdict": verdict, "support": round(support, 3), "missingNumbers": missing, "droppedQualifiers": dropped[:3]}


def _near_numbers(text: str, word: str, numbers: set[tuple[float, str]], window: int = 40) -> bool:
    """A qualifier only matters when it sits next to one of the claim's numbers."""
    if not numbers:
        return False
    for match in re.finditer(re.escape(word), text):
        span = text[max(0, match.start() - window): match.end() + window]
        if {value for value, _ in number_keys(span)} & {value for value, _ in numbers}:
            return True
    return False


def seek_sources(claims: list[dict], chunks: list[dict], index: BM25Index | None = None, top_k: int = 3) -> list[dict]:
    index = index or BM25Index([chunk["text"] for chunk in chunks])
    results = []
    for claim in claims:
        scored = sorted(
            ((index.score(claim["text"], position), position) for position in range(len(chunks))),
            reverse=True,
        )[:top_k]
        best = None
        best_grade = grade_claim(claim["text"], None)
        rank = {"supported": 2, "partial": 1, "unsupported": 0}
        for score, position in scored:
            if score <= 0:
                continue
            graded = grade_claim(claim["text"], chunks[position])
            if (rank[graded["verdict"]], graded["support"]) > (rank[best_grade["verdict"]], best_grade["support"]):
                best, best_grade = chunks[position], graded
        results.append({
            **claim,
            **best_grade,
            "source": None if not best else {
                "document": best["document"], "section": best["section"], "page": best["page"],
                "excerpt": short(best["text"], 220),
            },
            "_chunk": best["text"] if best else "",
        })
    return results


def figure_alignment(slide: dict, graded: list[dict], sources: list[dict]) -> list[dict]:
    figures = [item for item in slide.get("assetBindings") or [] if item.get("type") == "source-image"]
    if not figures:
        return []
    page_text: dict[object, str] = {}
    for source in _real_sources(sources):
        for section in source.get("sections", []):
            page = section.get("page")
            page_text[page] = page_text.get(page, "") + f" {section.get('title', '')} {section.get('text', '')}"
    claim_pages = {item["source"]["page"] for item in graded if item.get("source") and item["verdict"] != "unsupported"}
    slide_tokens = tokens(" ".join(item["text"] for item in graded) or str((slide.get("content") or {}).get("title", "")))
    rows = []
    for figure in figures:
        page = figure.get("sourcePage")
        caption = " ".join(str(figure.get(name) or "") for name in ("caption", "alt"))
        nearby = tokens(caption + " " + page_text.get(page, "")[:2400])
        overlap = len(slide_tokens & nearby) / max(1, len(slide_tokens))
        aligned = (page is not None and page in claim_pages) or overlap >= 0.25
        rows.append({
            "figure": short(caption or figure.get("sourceFigureId") or "原文图", 80),
            "page": page,
            "aligned": aligned,
            "overlap": round(overlap, 3),
        })
    return rows


JUDGE_PROMPT = """你是事实核查员。逐条判断“页面主张”能否由给出的“原文片段”直接支持。
只能使用原文片段，不得使用常识补全。数字、单位、时间范围和限定条件必须一致。
verdict 只能是 supported（完全支持）、partial（部分支持或遗漏限定条件）、unsupported（原文没有或矛盾）。
只返回 JSON：{"claims":[{"id":"c1","verdict":"supported","reason":"简短原因"}]}
"""


async def _judge_uncertain(judge, uncertain: list[dict]) -> int:
    if not judge or not uncertain:
        return 0
    payload = [
        {"id": f"c{index}", "claim": item["text"], "excerpt": short(item.get("_chunk") or "（未检索到原文）", 700)}
        for index, item in enumerate(uncertain)
    ]
    import json

    raw = await judge.complete(JUDGE_PROMPT + json.dumps(payload, ensure_ascii=False), max_tokens=1600)
    verdicts = parse_json_object(raw).get("claims") or []
    changed = 0
    by_id = {f"c{index}": item for index, item in enumerate(uncertain)}
    for verdict in verdicts:
        if not isinstance(verdict, dict):
            continue
        item = by_id.get(str(verdict.get("id")))
        value = str(verdict.get("verdict") or "")
        if item is None or value not in {"supported", "partial", "unsupported"}:
            continue
        # The judge may upgrade lexical misses, but never overrules a missing number.
        if item.get("missingNumbers") and value == "supported":
            value = "partial"
        if value != item["verdict"]:
            changed += 1
        item["judgeVerdict"] = value
        item["judgeReason"] = short(verdict.get("reason") or "", 160)
        item["verdict"] = value
    return changed


async def evaluate_faithfulness(
    slides: list[dict], sources: list[dict], *, judge=None, max_judged: int = 24
) -> dict[str, Any]:
    chunks = source_chunks(sources)
    if not chunks:
        return {"version": VERSION, "status": "no-sources", "mode": "rules", "slides": [], "claims": 0}
    index = BM25Index([chunk["text"] for chunk in chunks])
    per_slide = []
    all_claims: list[dict] = []
    for slide in slides:
        claims = slide_claims(slide)
        graded = seek_sources(claims, chunks, index)
        all_claims.extend(graded)
        per_slide.append({"slide": slide, "claims": graded})
    mode = "rules"
    judge_error = None
    uncertain = [item for item in all_claims if item["verdict"] != "supported"][:max_judged]
    if judge and uncertain:
        try:
            await _judge_uncertain(judge, uncertain)
            mode = "rules+judge"
        except Exception as exc:  # noqa: BLE001 - judges are optional
            judge_error = short(str(exc), 200)
    slides_out = []
    figure_rows = []
    for entry in per_slide:
        slide, graded = entry["slide"], entry["claims"]
        figures = figure_alignment(slide, graded, sources)
        figure_rows.extend(figures)
        counts = {name: sum(1 for item in graded if item["verdict"] == name) for name in ("supported", "partial", "unsupported")}
        slides_out.append({
            "position": slide.get("position"),
            "title": short((slide.get("content") or {}).get("title", ""), 60),
            "claims": [{key: value for key, value in item.items() if not key.startswith("_")} for item in graded],
            "counts": counts,
            "score": _score(counts),
            "figures": figures,
        })
    totals = {name: sum(item["counts"][name] for item in slides_out) for name in ("supported", "partial", "unsupported")}
    claim_count = sum(totals.values())
    aligned = [row for row in figure_rows if row["aligned"]]
    return {
        "version": VERSION,
        "status": "completed",
        "mode": mode,
        "judgeError": judge_error,
        "claims": claim_count,
        "counts": totals,
        "faithfulness": _score(totals),
        "strictFaithfulness": round(totals["supported"] / claim_count, 3) if claim_count else None,
        "figureClaimAlignment": round(len(aligned) / len(figure_rows), 3) if figure_rows else None,
        "unsupported": [
            {"position": item["position"], "text": claim["text"], "missingNumbers": claim.get("missingNumbers", [])}
            for item in slides_out for claim in item["claims"] if claim["verdict"] == "unsupported"
        ][:20],
        "slides": slides_out,
    }


def _score(counts: dict[str, int]) -> float | None:
    total = sum(counts.values())
    if not total:
        return None
    return round((counts["supported"] + 0.5 * counts["partial"]) / total, 3)

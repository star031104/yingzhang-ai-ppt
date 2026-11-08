"""Rehearsal: per-slide time budget and evidence-grounded audience questions.

* **Pacing** – the requested duration is split across pages by role and by how
  much the presenter has to say (title, conclusion, bullets and talking points), so
  a dense data page gets more time than a section divider. Every page gets a start
  time, a budget and a "compress" hint when its speaking load exceeds the budget.
* **Q&A** – likely audience questions are generated from the deck and answered
  only from the source evidence: the definition behind each number, stated
  limitations, method choice and material facts that the deck left out. Each
  answer carries its source location. An optional model only rephrases questions;
  it never writes answers.
"""

from __future__ import annotations

import re
from typing import Any

from app.evaluation.common import NAVIGATION_ROLES, short, tokens
from app.evaluation.quiz import missing_source_facts, number_keys
from app.intelligence.evidence import extract_evidence_graph

VERSION = "rehearsal-v1"
ROLE_WEIGHT = {
    "cover": 0.5, "agenda": 0.6, "section": 0.35, "questions": 0.6, "conclusion": 1.2, "data": 1.25,
    "comparison": 1.2, "evidence": 1.2, "method": 1.15, "architecture": 1.15, "insight": 1.1,
}
CHARS_PER_MINUTE = 240  # typical Chinese presentation speaking rate


def _speaking_chars(slide: dict) -> int:
    content = slide.get("content") or {}
    intent = slide.get("speakerIntent") or {}
    parts = [str(content.get("title", "")), str(slide.get("message", "")), *map(str, content.get("bullets") or []),
             *map(str, intent.get("talkingPoints") or [])]
    return len(re.sub(r"\s+", "", "".join(dict.fromkeys(parts))))


def pacing_plan(slides: list[dict], duration_minutes: float | None) -> dict[str, Any]:
    if not slides:
        return {"totalSeconds": 0, "pages": []}
    loads = [_speaking_chars(slide) for slide in slides]
    natural = [max(20.0, load / CHARS_PER_MINUTE * 60) for load in loads]
    total = float(duration_minutes) * 60 if duration_minutes else sum(natural)
    weights = [ROLE_WEIGHT.get(slide.get("role"), 1.0) * (0.6 + 0.4 * min(2.5, load / max(1, sum(loads) / len(loads))))
               for slide, load in zip(slides, loads, strict=True)]
    scale = total / sum(weights)
    pages, clock = [], 0.0
    for slide, weight, need in zip(slides, weights, natural, strict=True):
        budget = max(15.0, weight * scale)
        pages.append({
            "position": slide.get("position"),
            "slideId": slide.get("id"),
            "title": short((slide.get("content") or {}).get("title", ""), 40),
            "startSeconds": round(clock),
            "budgetSeconds": round(budget),
            "naturalSeconds": round(need),
            "pressure": "compress" if need > budget * 1.25 else "expand" if need < budget * 0.45 and slide.get("role") not in NAVIGATION_ROLES else "ok",
        })
        clock += budget
    return {
        "totalSeconds": round(clock),
        "requestedSeconds": round(total) if duration_minutes else None,
        "naturalSeconds": round(sum(natural)),
        "pages": pages,
    }


def _source_sentence(evidence: dict, number: tuple[float, str]) -> dict | None:
    for fact in evidence.get("facts", []):
        if number in number_keys(fact.get("claim", "")):
            return fact
    return None


def _best_fact(evidence: dict, text: str, kinds: set[str]) -> dict | None:
    wanted = tokens(text)
    best, best_score = None, 0.0
    for fact in evidence.get("facts", []):
        if fact.get("kind") not in kinds:
            continue
        overlap = len(wanted & tokens(fact.get("claim", ""))) / max(1, len(wanted))
        if overlap > best_score:
            best, best_score = fact, overlap
    return best if best_score >= 0.12 else None


def audience_questions(slides: list[dict], sources: list[dict], limit: int = 12) -> list[dict]:
    real = [source for source in sources if not source.get("synthetic")]
    if not real:
        return []
    evidence = extract_evidence_graph(real)
    questions: list[dict] = []
    seen: set[str] = set()

    def add(kind: str, position, question: str, fact: dict | None, answer: str | None = None) -> None:
        key = re.sub(r"\s+", "", question)
        if key in seen or (fact is None and answer is None):
            return
        seen.add(key)
        questions.append({
            "kind": kind, "position": position, "question": question,
            "answer": answer or short(fact["claim"], 220),
            "sourceRef": (fact or {}).get("sourceRef"),
        })

    for slide in slides:
        if slide.get("role") in NAVIGATION_ROLES:
            continue
        position = slide.get("position")
        text = " ".join([str(slide.get("message", "")), *map(str, (slide.get("content") or {}).get("bullets") or [])])
        for number in list(number_keys(text))[:2]:
            fact = _source_sentence(evidence, number)
            if fact:
                value = f"{number[0]:g}{number[1]}"
                add("definition", position, f"第 {position} 页的 {value} 是怎么算出来的？口径和时间范围是什么？", fact)
        if slide.get("role") in {"method", "architecture"}:
            fact = _best_fact(evidence, text, {"claim", "metric"})
            add("method", position, f"为什么选择第 {position} 页的这种方法？有没有对比过其他做法？", fact)
    for fact in evidence.get("facts", []):
        if fact.get("kind") == "constraint":
            add("limitation", None, "这个结论有什么前提或局限？", fact)
            if sum(1 for item in questions if item["kind"] == "limitation") >= 2:
                break
    for item in missing_source_facts(real, slides, limit=3):
        add("omitted", None, f"材料里提到“{short(item['claim'], 40)}”，为什么演示里没有讲？", None,
            answer=f"原文：{short(item['claim'], 200)}。如被问到，可说明它与本次主线的关系，或补充为备用页。")
        if item.get("sourceRef"):
            questions[-1]["sourceRef"] = item["sourceRef"]
    order = {"definition": 0, "limitation": 1, "method": 2, "omitted": 3}
    questions.sort(key=lambda item: (order.get(item["kind"], 9), item["position"] or 999))
    return questions[:limit]


def build_rehearsal(slides: list[dict], sources: list[dict], duration_minutes: float | None) -> dict[str, Any]:
    pacing = pacing_plan(slides, duration_minutes)
    questions = audience_questions(slides, sources)
    compress = [page["position"] for page in pacing["pages"] if page["pressure"] == "compress"]
    return {
        "version": VERSION,
        "durationMinutes": duration_minutes,
        "pacing": pacing,
        "questions": questions,
        "advice": [
            *([f"第 {', '.join(map(str, compress[:6]))} 页讲稿超出时间预算，可把细节移到备用页或问答"] if compress else []),
            *(["整套讲稿自然时长明显长于计划时长，建议减少页数或精简讲稿"]
              if pacing.get("requestedSeconds") and pacing["naturalSeconds"] > pacing["requestedSeconds"] * 1.3 else []),
        ],
    }


def rehearsal_markdown(title: str, rehearsal: dict) -> str:
    lines = [f"# {title}｜排练卡", ""]
    total = rehearsal["pacing"]["totalSeconds"]
    lines.append(f"总时长约 {total // 60} 分 {total % 60} 秒")
    lines.append("")
    lines.append("| 页 | 开始 | 预算 | 标题 | 提示 |")
    lines.append("| --- | --- | --- | --- | --- |")
    hints = {"compress": "压缩", "expand": "可展开", "ok": ""}
    for page in rehearsal["pacing"]["pages"]:
        start = page["startSeconds"]
        lines.append(f"| {page['position']} | {start // 60:02d}:{start % 60:02d} | {page['budgetSeconds']} 秒 | {page['title']} | {hints[page['pressure']]} |")
    if rehearsal["questions"]:
        lines.extend(["", "## 可能的提问", ""])
        for index, item in enumerate(rehearsal["questions"], 1):
            ref = item.get("sourceRef") or {}
            where = f"（{ref.get('document', '')} {ref.get('section', '')}）" if ref else ""
            lines.append(f"{index}. **{item['question']}**  ")
            lines.append(f"   答：{item['answer']}{where}")
    return "\n".join(lines) + "\n"

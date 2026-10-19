"""PaperQuiz-style information retention: questions from the sources, answers from slides only.

Adapted from Paper2Poster's PaperQuiz. Questions are generated from the source material
(an LLM when configured, otherwise numeric claims and key sentences of the evidence graph),
then answered using nothing but the audience-visible slide text. Accuracy measures how much
of the source the deck retains, and each answer must be supported by a cited slide
(evidence fidelity), so a model answering from world knowledge does not count.
"""

import json
import re

from app.evaluation.common import parse_json_object, short, slide_segments, tokens
from app.intelligence.evidence import METRIC_RE, extract_evidence_graph, split_sentences

VERSION = "paperquiz-v1"
UNANSWERED = "无法从页面回答"
_NUMBER = re.compile(r"[-+−]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")


def metric_spans(text: str) -> list[tuple[int, int, str]]:
    """Numeric mentions as (start, end, compact raw); "100 synthetic" is not "100 s"."""
    spans = []
    for match in METRIC_RE.finditer(text or ""):
        start, end = match.start(), match.end()
        raw = match.group()
        if re.search(r"[A-Za-z]$", raw) and re.match(r"[A-Za-z]", text[end:end + 1]):
            number = _NUMBER.search(raw)
            if not number:
                continue
            end = start + number.end()
            raw = raw[: number.end()]
        spans.append((start, end, re.sub(r"\s+", "", raw.strip())))
    return spans


def number_keys(text: str) -> set[tuple[float, str]]:
    """Normalized (value, unit) pairs so that 12% == 12.0 % and 18,400 == 18400."""
    keys = set()
    for _, _, compact in metric_spans(text):
        number = _NUMBER.search(compact)
        if not number:
            continue
        try:
            value = float(number.group().replace(",", "").replace("−", "-"))
        except ValueError:
            continue
        unit = compact[number.end():].lower()
        keys.add((abs(value), unit))
    return keys


def _is_year(raw: str) -> bool:
    return bool(re.fullmatch(r"(?:19|20)\d{2}", raw))


def _real_sources(sources: list[dict]) -> list[dict]:
    return [source for source in sources if not source.get("synthetic")]


def _section_meta(sources: list[dict]) -> dict[tuple[str, str], dict]:
    return {
        (source["name"], section["id"]): section
        for source in sources for section in source.get("sections", [])
    }


def rule_questions(sources: list[dict], max_detail: int = 10, max_concept: int = 8) -> list[dict]:
    graph = extract_evidence_graph(sources)
    sections = _section_meta(sources)
    detail: list[dict] = []
    for fact in graph["facts"]:
        if fact["kind"] != "metric":
            continue
        ref = fact["sourceRef"]
        section = sections.get((ref["document"], ref["section"]), {})
        importance = float(section.get("importance") or 0.5)
        for start, end, raw in metric_spans(fact["claim"]):
            if _is_year(raw) or not _NUMBER.search(raw):
                continue
            masked = fact["claim"][:start] + "____" + fact["claim"][end:]
            detail.append({
                "type": "detail",
                "question": f"根据材料：“{short(masked, 160)}”空缺处的数值是多少？",
                "expected": raw,
                "context": fact["claim"][:start] + " " + fact["claim"][end:],
                "sourceRef": ref,
                "factId": fact["id"],
                "importance": round(importance + (0.15 if "%" in raw else 0) + (0.1 if start < 40 else 0), 3),
            })
    concept: list[dict] = []
    for source in sources:
        for section in source.get("sections", []):
            understanding = section.get("understanding") or {}
            candidates = [understanding.get("mainPoint"), *(understanding.get("limitations") or [])[:1]]
            if not candidates[0]:
                candidates[0] = next((item for item in split_sentences(section.get("text", "")) if len(item) >= 12), "")
            for index, statement in enumerate(item for item in candidates if item):
                statement = str(statement).strip()
                if len(statement) < 12 or len(tokens(statement)) < 3:
                    continue
                title = short(section.get("title") or section["id"], 40)
                question = (
                    f"关于「{title}」，材料的核心观点是什么？" if index == 0
                    else f"关于「{title}」，材料指出了哪些限制或前提？"
                )
                concept.append({
                    "type": "concept",
                    "question": question,
                    "expected": short(statement, 240),
                    "sourceRef": {"document": source["name"], "section": section["id"], "page": section.get("page")},
                    "importance": round(float(section.get("importance") or 0.5) - 0.1 * index, 3),
                })

    def pick(items: list[dict], limit: int) -> list[dict]:
        # Highest importance first, but spread across sections before repeating one.
        ordered = sorted(items, key=lambda item: -item["importance"])
        chosen: list[dict] = []
        used_sections: set = set()
        seen_expected: set = set()
        for spread in (True, False):
            for item in ordered:
                key = (item["sourceRef"]["document"], item["sourceRef"]["section"])
                if len(chosen) >= limit:
                    return chosen
                if item in chosen or item["expected"] in seen_expected or (spread and key in used_sections):
                    continue
                chosen.append(item)
                used_sections.add(key)
                seen_expected.add(item["expected"])
        return chosen

    questions = pick(detail, max_detail) + pick(concept, max_concept)
    for index, item in enumerate(questions, 1):
        item["id"] = f"q{index}"
    return questions


def _source_excerpt(sources: list[dict], limit: int = 9000) -> str:
    records = []
    queues = [list(source.get("sections", [])) for source in sources]
    names = [source["name"] for source in sources]
    total = 0
    while any(queues) and total < limit:
        for name, queue in zip(names, queues):
            if not queue:
                continue
            section = queue.pop(0)
            text = short(section.get("text", ""), 900)
            record = {"document": name, "section": section["id"], "title": section.get("title"), "text": text}
            total += len(text) + 40
            records.append(record)
            if total >= limit:
                break
    return json.dumps(records, ensure_ascii=False)


async def model_questions(judge, sources: list[dict], max_detail: int, max_concept: int) -> list[dict]:
    known = {(source["name"], section["id"]): section for source in sources for section in source.get("sections", [])}
    prompt = (
        "你是考试命题人。只根据下列材料出题，用于检验一份演示文稿保留了多少材料信息。\n"
        f"请出 {max_detail} 道 detail 题（考查具体数值、名称、结果）和 {max_concept} 道 concept 题"
        "（考查核心观点、方法、结论或限制）。每题必须能从材料中找到唯一答案，答案简短。\n"
        f"材料：{_source_excerpt(sources)}\n"
        "只输出 JSON：{\"questions\":[{\"type\":\"detail 或 concept\",\"question\":\"中文问题\","
        "\"answer\":\"标准答案\",\"document\":\"文档名\",\"section\":\"章节编号\",\"importance\":1-3}]}"
    )
    payload = parse_json_object(await judge.complete(prompt, max_tokens=3200))
    questions = []
    counts = {"detail": 0, "concept": 0}
    limits = {"detail": max_detail, "concept": max_concept}
    for entry in payload.get("questions", []) if isinstance(payload.get("questions"), list) else []:
        if not isinstance(entry, dict):
            continue
        kind = str(entry.get("type", "")).strip().lower()
        question, answer = short(entry.get("question"), 240), short(entry.get("answer"), 240)
        if kind not in counts or not question or not answer or counts[kind] >= limits[kind]:
            continue
        if kind == "detail" and not number_keys(answer) and len(tokens(answer)) < 1:
            continue
        key = (str(entry.get("document", "")), str(entry.get("section", "")))
        if key not in known:
            key = next(iter(known), ("", ""))
        try:
            importance = max(1, min(3, int(entry.get("importance", 2))))
        except (TypeError, ValueError):
            importance = 2
        counts[kind] += 1
        questions.append({
            "type": kind, "question": question, "expected": answer, "context": question,
            "sourceRef": {"document": key[0], "section": key[1], "page": known.get(key, {}).get("page")},
            "importance": round(importance / 3, 3),
        })
    for index, item in enumerate(questions, 1):
        item["id"] = f"q{index}"
    return questions


def _slide_units(slides: list[dict]) -> list[tuple[int, str]]:
    units = []
    for slide in slides:
        for segment in slide_segments(slide):
            for sentence in split_sentences(segment) or [segment]:
                units.append((int(slide.get("position", 0)), sentence))
    return units


def _overlap(reference: set[str], candidate: set[str]) -> float:
    return len(reference & candidate) / max(1, len(reference))


def _detail_supported(expected: str, text: str) -> bool:
    keys = number_keys(expected)
    return bool(keys) and keys <= number_keys(text)


def _concept_supported(expected: str, text: str, threshold: float = 0.45) -> bool:
    reference = tokens(expected)
    return bool(reference) and _overlap(reference, tokens(text)) >= threshold


def lexical_answer(question: dict, slides: list[dict], units: list[tuple[int, str]] | None = None) -> dict:
    """Answer one question from slide text only, using lexical and numeric matching."""
    units = units if units is not None else _slide_units(slides)
    if question["type"] == "detail":
        context = tokens(question.get("context") or question["question"])
        best = None
        for position, text in units:
            if not number_keys(text):
                continue
            score = _overlap(context, tokens(text)) + (0.5 if _detail_supported(question["expected"], text) else 0)
            if best is None or score > best[0]:
                best = (score, position, text)
        if not best or best[0] < 0.2:
            return {"answer": UNANSWERED, "supportedBySlide": None}
        _, position, text = best
        if _detail_supported(question["expected"], text) and best[0] >= 0.7:
            return {"answer": question["expected"], "supportedBySlide": position, "evidence": short(text, 160)}
        values = [raw for _, _, raw in metric_spans(text)]
        return {"answer": values[0] if values else UNANSWERED, "supportedBySlide": None, "evidence": short(text, 160)}
    reference = tokens(question["expected"])
    by_slide: dict[int, list[str]] = {}
    for position, text in units:
        by_slide.setdefault(position, []).append(text)
    best = None
    for position, texts in by_slide.items():
        joined = " ".join(texts)
        score = _overlap(reference, tokens(joined))
        if best is None or score > best[0]:
            best = (score, position, max(texts, key=lambda item: _overlap(reference, tokens(item))))
    if not best or best[0] < 0.45:
        return {"answer": UNANSWERED, "supportedBySlide": None}
    return {"answer": short(best[2], 200), "supportedBySlide": best[1], "evidence": short(best[2], 160)}


async def model_answers(judge, questions: list[dict], slides: list[dict]) -> dict[str, dict]:
    pages = [{"page": int(slide.get("position", 0)), "text": short("\n".join(slide_segments(slide)), 900)} for slide in slides]
    asked = [{"id": item["id"], "question": item["question"]} for item in questions]
    prompt = (
        "你只能依据下面演示文稿页面上的文字回答问题，禁止使用常识或其他知识。"
        f"如果页面上没有答案，answer 填“{UNANSWERED}”，slide 填 null。\n"
        f"页面：{json.dumps(pages, ensure_ascii=False)}\n问题：{json.dumps(asked, ensure_ascii=False)}\n"
        "只输出 JSON：{\"answers\":[{\"id\":\"题号\",\"answer\":\"简短答案\",\"slide\":给出答案的页码或 null}]}"
    )
    payload = parse_json_object(await judge.complete(prompt, max_tokens=2400))
    answers = {}
    for entry in payload.get("answers", []) if isinstance(payload.get("answers"), list) else []:
        if isinstance(entry, dict) and entry.get("id"):
            try:
                slide = int(entry["slide"]) if entry.get("slide") not in (None, "", "null") else None
            except (TypeError, ValueError):
                slide = None
            answers[str(entry["id"])] = {"answer": short(entry.get("answer") or UNANSWERED, 200), "slide": slide}
    return answers


def grade(question: dict, answer: str, cited_slide_text: str | None) -> bool:
    """Correct only when the answer matches and the cited slide actually supports it."""
    if not answer or answer == UNANSWERED or cited_slide_text is None:
        return False
    if question["type"] == "detail":
        expected_numbers = number_keys(question["expected"])
        if expected_numbers:
            return expected_numbers <= number_keys(answer) and expected_numbers <= number_keys(cited_slide_text)
        return _concept_supported(question["expected"], answer, 0.6) and _concept_supported(
            question["expected"], cited_slide_text, 0.6)
    return _concept_supported(question["expected"], answer, 0.35) and _concept_supported(
        question["expected"], cited_slide_text, 0.3)


def missing_source_facts(sources: list[dict], slides: list[dict], limit: int = 10) -> list[dict]:
    """Important source metrics whose values appear nowhere in the deck."""
    deck_numbers = set().union(*(number_keys("\n".join(slide_segments(slide))) for slide in slides)) if slides else set()
    sections = _section_meta(sources)
    graph = extract_evidence_graph(sources)
    missing = []
    for fact in graph["facts"]:
        if fact["kind"] != "metric":
            continue
        values = [raw for _, _, raw in metric_spans(fact["claim"]) if not _is_year(raw)]
        absent = [value for value in values if number_keys(value) and not number_keys(value) <= deck_numbers]
        if not absent:
            continue
        ref = fact["sourceRef"]
        importance = float(sections.get((ref["document"], ref["section"]), {}).get("importance") or 0.5)
        missing.append({
            "claim": short(fact["claim"], 200), "missingValues": absent[:4], "sourceRef": ref,
            "importance": round(importance, 3),
        })
    missing.sort(key=lambda item: (-item["importance"], -len(item["missingValues"])))
    return missing[:limit]


def _ratio(items: list[dict]) -> float | None:
    return round(sum(item["correct"] for item in items) / len(items) * 100, 1) if items else None


async def evaluate_quiz(
    slides: list[dict],
    sources: list[dict],
    *,
    judge=None,
    max_detail: int = 10,
    max_concept: int = 8,
) -> dict:
    sources = _real_sources(sources)
    if not sources or not any(source.get("sections") for source in sources):
        return {"version": VERSION, "status": "no-sources", "message": "项目没有上传材料，无法从材料出题",
                "questions": [], "retention": None, "missingFacts": [], "errors": []}
    errors: list[str] = []
    generator = "rule"
    questions: list[dict] = []
    if judge:
        try:
            questions = await model_questions(judge, sources, max_detail, max_concept)
            generator = "llm" if len(questions) >= 3 else "rule"
        except Exception as exc:  # noqa: BLE001 - provider failures fall back to rules
            errors.append(short(f"模型出题失败：{exc}", 200))
    if generator == "rule":
        questions = rule_questions(sources, max_detail, max_concept)
    by_position = {int(slide.get("position", 0)): "\n".join(slide_segments(slide)) for slide in slides}
    answerer = "lexical"
    model_result: dict[str, dict] = {}
    if judge and questions:
        try:
            model_result = await model_answers(judge, questions, slides)
            answerer = "llm" if model_result else "lexical"
        except Exception as exc:  # noqa: BLE001
            errors.append(short(f"模型答题失败：{exc}", 200))
    units = _slide_units(slides)
    trace = []
    for item in questions:
        if answerer == "llm":
            reply = model_result.get(item["id"], {"answer": UNANSWERED, "slide": None})
            answer, slide = reply["answer"], reply["slide"]
        else:
            reply = lexical_answer(item, slides, units)
            answer, slide = reply["answer"], reply["supportedBySlide"]
        correct = grade(item, answer, by_position.get(slide) if slide is not None else None)
        trace.append({
            "id": item["id"], "type": item["type"], "question": item["question"],
            "expected": item["expected"], "answer": answer,
            "supportedBySlide": slide if correct else None,
            "citedSlide": slide, "correct": correct,
            "sourceRef": item.get("sourceRef"), "importance": item.get("importance"),
        })
    detail = [item for item in trace if item["type"] == "detail"]
    concept = [item for item in trace if item["type"] == "concept"]
    missed = sorted((item for item in trace if not item["correct"]), key=lambda item: -(item["importance"] or 0))
    return {
        "version": VERSION,
        "status": "completed" if trace else "no-questions",
        "generator": generator,
        "answerer": answerer,
        "model": getattr(judge, "model_id", None) if generator == "llm" or answerer == "llm" else None,
        "questionCount": len(trace),
        "retention": _ratio(trace),
        "detailRetention": _ratio(detail),
        "conceptRetention": _ratio(concept),
        "detailCount": len(detail),
        "conceptCount": len(concept),
        "questions": trace,
        "missedQuestions": [
            {"id": item["id"], "type": item["type"], "question": item["question"], "expected": item["expected"],
             "sourceRef": item["sourceRef"]}
            for item in missed[:8]
        ],
        "missingFacts": missing_source_facts(sources, slides),
        "errors": errors,
    }

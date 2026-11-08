"""Three-level source knowledge base: card → facts → chunks.

UniPPTAgent's narrative agent works from a layered knowledge base instead of raw
text. YingZhang builds the same three levels deterministically from parsed
sources and the evidence graph:

* **card**   – one short, bounded overview of every document: kind, outline,
               headline metrics and stated limitations. It fits in any model
               context (default ≤ 2,400 characters) and is what a planner reads
               first.
* **facts**  – atomic, source-bound sentences from the evidence graph (claims,
               metrics, constraints) with their source location.
* **chunks** – retrieval passages with heading paths, used for BM25/dense search.

Every fact and chunk keeps ``document/section/page`` so anything a model picks
from the card can be traced back down to the original text.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.intelligence.content_selection import section_understanding
from app.intelligence.evidence import extract_evidence_graph

VERSION = "knowledge-base-v1"


def _outline(source: dict, limit: int = 12) -> list[str]:
    outline = []
    for section in source.get("sections", []):
        level = int(section.get("headingLevel") or 1)
        if level > 2:
            continue
        title = re.sub(r"\s+", " ", str(section.get("title", ""))).strip()
        if title and title not in outline:
            outline.append(("  " if level == 2 else "") + title[:40])
        if len(outline) >= limit:
            break
    return outline


def build_card(sources: list[dict], evidence: dict, limit: int = 2400) -> dict[str, Any]:
    facts = evidence.get("facts", [])
    documents = []
    for source in sources:
        name = source.get("name")
        own = [fact for fact in facts if (fact.get("sourceRef") or {}).get("document") == name]
        metrics = [fact["claim"] for fact in own if fact.get("kind") == "metric"]
        constraints = [fact["claim"] for fact in own if fact.get("kind") == "constraint"]
        main_points = []
        for section in source.get("sections", [])[:40]:
            point = section_understanding(section).get("mainPoint")
            if point and len(point) >= 10 and point not in main_points:
                main_points.append(point)
        documents.append({
            "name": name,
            "kind": source.get("kind") or source.get("documentType") or "document",
            "sections": len(source.get("sections", [])),
            "tables": len(source.get("tables", [])),
            "figures": len(source.get("figures", [])),
            "outline": _outline(source),
            "headlineMetrics": [item[:120] for item in metrics[:5]],
            "keyFindings": [item[:120] for item in main_points[:4]],
            "limitations": [item[:120] for item in constraints[:3]],
            "readingWarnings": [str(item.get("message", item))[:80] for item in (source.get("readingWarnings") or [])[:2]],
        })
    card = {"documents": documents, "keywords": evidence.get("keywords", [])[:12]}
    # Shrink lists until the card fits the budget; never emit truncated JSON.
    for key, minimum in (("keyFindings", 1), ("outline", 4), ("headlineMetrics", 2), ("limitations", 1), ("readingWarnings", 0)):
        while len(json.dumps(card, ensure_ascii=False)) > limit and any(len(doc[key]) > minimum for doc in documents):
            for doc in documents:
                if len(doc[key]) > minimum:
                    doc[key].pop()
    while len(json.dumps(card, ensure_ascii=False)) > limit and len(documents) > 1:
        documents.pop()
        card["omittedDocuments"] = card.get("omittedDocuments", 0) + 1
    return card


def build_knowledge_base(sources: list[dict], evidence: dict | None = None, *, card_limit: int = 2400) -> dict[str, Any]:
    from app.intelligence.retrieval import _chunks

    real = [source for source in sources if not source.get("synthetic")] or sources
    evidence = evidence or extract_evidence_graph(real)
    facts = [
        {
            "id": fact["id"],
            "claim": fact["claim"],
            "kind": fact.get("kind", "claim"),
            "sourceRef": fact.get("sourceRef"),
            "metricIds": fact.get("metricIds", []),
        }
        for fact in evidence.get("facts", [])
    ]
    chunks = [
        {
            "id": f"C{index + 1:04d}",
            "document": chunk["document"],
            "section": chunk["section"],
            "page": chunk.get("page"),
            "title": chunk.get("title"),
            "headingPath": chunk.get("headingPath", []),
            "part": chunk.get("part"),
            "chars": len(chunk.get("text", "")),
        }
        for index, chunk in enumerate(_chunks(real))
    ]
    card = build_card(real, evidence, card_limit)
    return {
        "version": VERSION,
        "card": card,
        "facts": facts,
        "chunks": chunks,
        "stats": {
            "documents": len(real),
            "facts": len(facts),
            "metricFacts": sum(1 for fact in facts if fact["kind"] == "metric"),
            "constraints": sum(1 for fact in facts if fact["kind"] == "constraint"),
            "chunks": len(chunks),
            "cardChars": len(json.dumps(card, ensure_ascii=False)),
        },
    }


def card_prompt(knowledge: dict) -> str:
    """Compact card text for prompts (data, never instructions)."""
    return json.dumps(knowledge.get("card", {}), ensure_ascii=False, separators=(",", ":"))

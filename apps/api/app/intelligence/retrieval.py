"""Hybrid source retrieval: BM25 (+ optional dense vectors) fused with RRF.

The synchronous :func:`retrieve_source_context` is lexical only and fully
deterministic. :func:`retrieve_source_context_async` additionally asks an
:class:`~app.intelligence.embeddings.EmbeddingRetriever` for dense similarities
and falls back to BM25 when vectors are unavailable.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.intelligence.bm25 import BM25Index, rank_order, reciprocal_rank_fusion, tokenize
from app.intelligence.content_selection import concise_source_context, query_terms
from app.intelligence.evidence import split_sentences

if TYPE_CHECKING:
    from app.intelligence.embeddings import EmbeddingRetriever

DOMAIN_TERMS = {
    "academic": "摘要 背景 问题 相关工作 方法 模型 架构 算法 实现 数据集 指标 实验 结果 对比 消融 局限 结论",
    "conference": "摘要 背景 问题 方法 贡献 实验 结果 局限 结论",
    "business": "目标 市场 用户 收入 成本 增长 风险 策略 路线图 结论",
    "strategy": "现状 目标 洞察 取舍 战略 举措 风险 路线图",
    "executive": "结论 指标 差距 风险 决策 行动 负责人 时间",
    "review": "目标 结果 指标 差距 原因 经验 行动",
    "product": "用户 痛点 场景 产品 功能 方案 架构 数据 指标 路线图",
    "pitch": "愿景 市场 痛点 产品 商业模式 增长 壁垒 团队 融资",
    "marketing": "受众 洞察 定位 创意 渠道 预算 指标 计划",
    "sales": "客户 痛点 方案 价值 案例 实施 报价 下一步",
    "teaching": "目标 概念 原理 示例 步骤 练习 总结",
    "training": "目标 认知 方法 示例 练习 行动 总结",
    "public": "背景 政策 现状 问题 举措 成效 计划",
    "keynote": "观点 故事 案例 转折 启发 行动",
    "portfolio": "背景 挑战 过程 方案 作品 结果 复盘",
}
IMPORTANT_HEADING = re.compile(
    r"abstract|摘要|introduction|背景|problem|问题|method|方法|architecture|架构|"
    r"experiment|result|evaluation|实验|结果|消融|ablation|limitation|局限|conclusion|结论",
    re.IGNORECASE,
)


def _terms(text: str) -> set[str]:
    return query_terms(text)


def _chunks(sources: list[dict], size: int = 1800) -> list[dict]:
    chunks: list[dict] = []
    for source_index, source in enumerate(sources):
        for section_index, section in enumerate(source.get("sections", [])):
            sentences = split_sentences(section.get("text", "")) or [section.get("text", "")]
            bucket: list[str] = []
            length = 0
            part = 1
            for sentence in sentences:
                if bucket and length + len(sentence) > size:
                    chunks.append({
                        "document": source["name"], "section": section["id"],
                        "title": section.get("title", "正文"), "page": section.get("page"),
                        "text": " ".join(bucket), "part": part,
                        "order": (source_index, section_index, part),
                        "sourceHash": source.get("sha256") or source["name"],
                    })
                    bucket = bucket[-1:]
                    length = sum(map(len, bucket))
                    part += 1
                bucket.append(sentence)
                length += len(sentence)
            if bucket:
                chunks.append({
                    "document": source["name"], "section": section["id"],
                    "title": section.get("title", "正文"), "page": section.get("page"),
                    "text": " ".join(bucket), "part": part,
                    "order": (source_index, section_index, part),
                    "sourceHash": source.get("sha256") or source["name"],
                })
    return chunks


RELEVANCE_SCALE = 10.0
METRIC_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:%|倍|ms|秒|分钟|GB|MB)")


def retrieval_query(title: str, preset: str, instructions: str) -> str:
    return f"{title} {instructions} {DOMAIN_TERMS.get(preset, '')}"


def rank_chunks(chunks: list[dict], query: str, dense: list[float] | None = None) -> list[dict]:
    """Score chunks in place (BM25 ⊕ dense via RRF, then structural boosts) and rank them."""
    total = len(chunks)
    if not total:
        return []
    # Headings are repeated so that a matching section title outweighs a passing mention.
    index = BM25Index([tokenize(f"{chunk['title']} {chunk['title']} {chunk['text']}") for chunk in chunks])
    lexical = index.scores(tokenize(query))
    rankings = [[item for item in rank_order(lexical) if lexical[item] > 0]]
    if dense and len(dense) == total:
        rankings.append([item for item in rank_order(dense) if dense[item] > 0])
    fused = reciprocal_rank_fusion(rankings, total)
    top = max(fused) or 1.0
    for position, chunk in enumerate(chunks):
        haystack = f"{chunk['title']} {chunk['text']}".lower()
        heading_boost = 4 if IMPORTANT_HEADING.search(chunk["title"]) else 0
        metric_boost = 2 if METRIC_RE.search(haystack) else 0
        edge_boost = 2 if position < min(3, total) or position >= max(0, total - 3) else 0
        chunk["lexicalScore"] = round(lexical[position], 4)
        if dense and len(dense) == total:
            chunk["denseScore"] = round(dense[position], 4)
        chunk["relevance"] = fused[position] / top
        chunk["score"] = RELEVANCE_SCALE * chunk["relevance"] + heading_boost + metric_boost + edge_boost
    return sorted(chunks, key=lambda item: (-item["score"], item["order"]))


def _assemble(ranked: list[dict], title: str, instructions: str, limit: int) -> str:
    # Cover each uploaded document before spending the remainder on highly ranked passages.
    by_document = {}
    for chunk in ranked:
        by_document.setdefault(chunk["document"], chunk)
    by_section = {}
    for chunk in ranked:
        by_section.setdefault((chunk["document"], chunk["section"]), chunk)
    priority = [*by_document.values(), *by_section.values(), *ranked]
    selected, seen, used = [], set(), 0
    for chunk in priority:
        key = (chunk["document"], chunk["section"], chunk["part"])
        if key in seen:
            continue
        seen.add(key)
        page = f"｜第{chunk['page']}页" if chunk.get("page") else ""
        header = f"\n【资料：{chunk['document']}｜{chunk['section']}｜{chunk['title']}{page}｜片段{chunk['part']}】\n"
        remaining_documents = max(1, len(by_document) - len({item[0] for item in selected}))
        budget = min(len(chunk["text"]), max(0, (limit - used) // remaining_documents - len(header)))
        text = concise_source_context(chunk, budget, f"{title} {instructions}")
        if not text or used + len(header) + len(text) > limit:
            continue
        selected.append((chunk["document"], chunk["order"], header + text))
        used += len(header) + len(text)
    return "".join(item[2] for item in sorted(selected, key=lambda item: item[1]))


def retrieve_source_context(
    sources: list[dict], title: str, preset: str, instructions: str, limit: int = 48000
) -> str:
    """Deterministic lexical (BM25) retrieval with per-document coverage guarantees."""
    ranked = rank_chunks(_chunks(sources), retrieval_query(title, preset, instructions))
    return _assemble(ranked, title, instructions, limit)


async def rank_source_chunks_async(
    sources: list[dict], query: str, retriever: EmbeddingRetriever | None = None
) -> tuple[list[dict], dict]:
    """Rank chunks with dense vectors when a retriever is available; never raises for provider faults."""
    chunks = _chunks(sources)
    info = {"strategy": "bm25", "dense": False, "chunks": len(chunks)}
    dense = None
    if retriever is not None and chunks:
        try:
            dense = await retriever.similarities(query, chunks)
            info.update({"strategy": "hybrid-bm25-dense-rrf", "dense": True,
                         "embeddingRequests": retriever.requests, "cacheHits": retriever.cache_hits})
        except Exception as exc:  # noqa: BLE001 - any provider fault degrades to BM25
            info["denseError"] = str(exc)[:180] or type(exc).__name__
            dense = None
    return rank_chunks(chunks, query, dense), info


async def retrieve_source_context_async(
    sources: list[dict], title: str, preset: str, instructions: str, limit: int = 48000,
    retriever: EmbeddingRetriever | None = None,
) -> str:
    ranked, _info = await rank_source_chunks_async(
        sources, retrieval_query(title, preset, instructions), retriever
    )
    return _assemble(ranked, title, instructions, limit)


async def section_relevance_async(
    sources: list[dict], query: str, retriever: EmbeddingRetriever | None = None
) -> tuple[dict[tuple[str, str], float], dict]:
    """Best fused relevance (0–1) per (document, section) for planning-time record selection."""
    ranked, info = await rank_source_chunks_async(sources, query, retriever)
    relevance: dict[tuple[str, str], float] = {}
    for chunk in ranked:
        key = (chunk["document"], chunk["section"])
        relevance[key] = max(relevance.get(key, 0.0), float(chunk.get("relevance", 0.0)))
    return relevance, info

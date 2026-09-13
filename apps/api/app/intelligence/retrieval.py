import re

from app.intelligence.content_selection import concise_source_context, query_terms
from app.intelligence.evidence import split_sentences

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
                })
    return chunks


def retrieve_source_context(
    sources: list[dict], title: str, preset: str, instructions: str, limit: int = 48000
) -> str:
    chunks = _chunks(sources)
    query_terms = _terms(f"{title} {instructions} {DOMAIN_TERMS.get(preset, '')}")
    total = max(1, len(chunks))
    for index, chunk in enumerate(chunks):
        haystack = f"{chunk['title']} {chunk['text']}".lower()
        overlap = sum(1 + min(haystack.count(term), 3) * 0.3 for term in query_terms if term in haystack)
        heading_boost = 4 if IMPORTANT_HEADING.search(chunk["title"]) else 0
        metric_boost = 2 if re.search(r"\d+(?:\.\d+)?\s*(?:%|倍|ms|秒|分钟|GB|MB)", haystack) else 0
        edge_boost = 2 if index < min(3, total) or index >= max(0, total - 3) else 0
        chunk["score"] = overlap + heading_boost + metric_boost + edge_boost
    ranked = sorted(chunks, key=lambda item: (-item["score"], item["order"]))
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

"""Scored semantic-role classification for source sections.

Each candidate role accumulates evidence from three deterministic signals:

* regex hits in the heading (strong) and the body (weak, capped);
* BM25 similarity between the section and a short prototype description of
  the role, which covers non-academic vocabulary (pitch, sales, teaching …);
* position priors (background early, conclusion late, results in the second half).

The highest score wins and the margin to the runner-up becomes a confidence
value, so low-confidence sections can be surfaced instead of silently guessed.
"""

from __future__ import annotations

import re
from functools import lru_cache

from app.intelligence.bm25 import BM25Index, tokenize

ROLE_PATTERNS = [
    ("problem", re.compile(r"problem|challenge|motivation|痛点|问题|挑战|动机|缺口|风险", re.IGNORECASE)),
    ("method", re.compile(r"method|approach|algorithm|方法|方案|算法|流程|构建|产品服务|功能模块|市场营销|推广|运营", re.IGNORECASE)),
    ("architecture", re.compile(r"architecture|framework|system|架构|框架|系统|技术路线|产品概况|角色协同", re.IGNORECASE)),
    ("comparison", re.compile(r"comparison|baseline|related work|对比|基线|相关工作|国内外|竞品|竞争|行业分析", re.IGNORECASE)),
    ("insight", re.compile(r"ablation|analysis|error|消融|洞察|误差|讨论|局限|风险对冲", re.IGNORECASE)),
    ("data", re.compile(r"experiment|result|evaluation|metric|实验|结果|评估|指标|性能|财务|现金流|销售预测|收入|资金|资本结构", re.IGNORECASE)),
    ("evidence", re.compile(r"evidence|proof|case|证据|案例|数据集|团队|组织|公司管理", re.IGNORECASE)),
    ("conclusion", re.compile(r"conclusion|discussion|limitation|future|结论|讨论|局限|展望|创新", re.IGNORECASE)),
    ("background", re.compile(r"abstract|introduction|background|摘要|引言|背景|现状|意义", re.IGNORECASE)),
]

# Prototype descriptions: what a section serving the role usually talks about.
ROLE_PROTOTYPES = {
    "background": "背景 现状 引言 意义 摘要 概述 行业趋势 宏观环境 政策环境 发展历程 机遇 愿景 使命 市场规模 时机 学习目标 导入 "
                  "introduction background overview context trend vision",
    "problem": "问题 痛点 挑战 动机 缺口 需求 瓶颈 难点 不足 困境 诉求 用户痛点 客户痛点 研究问题 误区 用户画像 "
               "problem challenge pain point need gap bottleneck",
    "method": "方法 方案 流程 步骤 举措 策略 实施 执行 运营 推广 营销 渠道 打法 操作 练习 教学方法 "
              "技术实现 算法 method approach process step strategy execution channel",
    "architecture": "架构 框架 系统 模块 平台 技术路线 产品功能 组成 结构 体系 整体设计 部署 数据流 核心概念 定义 知识体系 "
                    "architecture framework system module platform product feature design",
    "comparison": "对比 比较 竞品 竞争 基线 优劣 差异 替代方案 定位 取舍 相关工作 国内外研究 "
                  "comparison competitor baseline versus alternative benchmark",
    "insight": "洞察 分析 发现 原因 启示 经验 教训 复盘 误差 消融 讨论 归因 关键判断 "
               "insight analysis finding lesson cause implication",
    "data": "数据 结果 指标 实验 评估 性能 收入 营收 增长 财务 预算 成本 利润 销量 转化率 留存率 "
            "业绩 现金流 准确率 商业模式 盈利模式 定价 报价 data result metric revenue growth kpi accuracy",
    "evidence": "证据 案例 客户案例 客户证言 团队 成员 组织 资质 实践 示例 作品 证明 引用 用户反馈 合作伙伴 "
                "case evidence team example testimonial portfolio partner",
    "conclusion": "结论 总结 展望 下一步 建议 行动 未来工作 里程碑 路线图 呼吁 决策 融资需求 "
                  "conclusion summary next step recommendation roadmap future",
}
ROLE_ORDER = [role for role, _ in ROLE_PATTERNS]
METRIC_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:%|倍|ms|秒|分钟|GB|MB)")
TITLE_HIT = 6.0
BODY_HIT = 0.5
TITLE_PROTOTYPE = 2.0
BODY_PROTOTYPE = 1.0
MINIMUM_SCORE = 0.9


@lru_cache(maxsize=1)
def _prototype_index() -> BM25Index:
    return BM25Index([ROLE_PROTOTYPES[role] for role in ROLE_ORDER])


def _saturated(scores: list[float], scale: float) -> list[float]:
    """Map raw BM25 scores to 0–1 without inflating weak matches (no max-normalisation)."""
    return [min(1.0, value / scale) for value in scores]


def _position_prior(role: str, relative: float) -> float:
    if role == "background":
        return 0.6 * max(0.0, 1 - relative * 2.5)
    if role == "conclusion":
        return 0.6 * max(0.0, relative * 2.5 - 1.5)
    if role in {"data", "insight"}:
        return 0.3 * max(0.0, relative - 0.4)
    if role == "problem":
        return 0.3 * max(0.0, 1 - relative * 3)
    return 0.0


def classify_section(
    section: dict, position: int | None = None, total: int | None = None, labels: set[str] | None = None
) -> dict:
    """Return ``{"role", "confidence", "signal", "scores"}`` for one source section."""
    explicit = str(section.get("semanticRole") or "").strip()
    if explicit and (labels is None or explicit in labels):
        return {"role": explicit, "confidence": 1.0, "signal": "explicit", "scores": {explicit: 1.0}}
    title = str(section.get("title", ""))
    body = str(section.get("text", ""))[:1000]
    scores = dict.fromkeys(ROLE_ORDER, 0.0)
    title_hits = set()
    for order, (role, pattern) in enumerate(ROLE_PATTERNS):
        if pattern.search(title):
            title_hits.add(role)
            # Earlier patterns stay preferred on a tie, as in the former first-match rule.
            scores[role] += TITLE_HIT + (len(ROLE_PATTERNS) - order) * 0.05
        body_hits = len({match.group().lower() for match in pattern.finditer(body)})
        scores[role] += min(3, body_hits) * BODY_HIT
    index = _prototype_index()
    title_similarity = _saturated(index.scores(tokenize(title)), 3.0) if title.strip() else [0.0] * len(ROLE_ORDER)
    body_similarity = _saturated(index.scores(tokenize(body)), 6.0) if body.strip() else [0.0] * len(ROLE_ORDER)
    for order, role in enumerate(ROLE_ORDER):
        scores[role] += TITLE_PROTOTYPE * title_similarity[order] + BODY_PROTOTYPE * body_similarity[order]
    if METRIC_RE.search(body):
        scores["data"] += 0.8
    if position is not None and total and total > 2:
        relative = position / max(1, total - 1)
        for role in ROLE_ORDER:
            scores[role] += _position_prior(role, relative)
    ranked = sorted(scores.items(), key=lambda item: (-item[1], ROLE_ORDER.index(item[0])))
    (best, top), (_runner, second) = ranked[0], ranked[1]
    if top < MINIMUM_SCORE:
        # Nothing points to a specific job: "content" is a guess, so confidence stays below 0.5.
        return {"role": "content", "confidence": round(0.45 * top / MINIMUM_SCORE, 3),
                "signal": "fallback", "scores": {key: round(value, 3) for key, value in ranked[:3]}}
    confidence = (top - second) / top if top > 0 else 0.0
    best_index = ROLE_ORDER.index(best)
    signal = "title" if best in title_hits else "title-prototype" if title_similarity[best_index] else "body"
    return {"role": best, "confidence": round(min(1.0, 0.35 + confidence), 3), "signal": signal,
            "scores": {key: round(value, 3) for key, value in ranked[:3]}}

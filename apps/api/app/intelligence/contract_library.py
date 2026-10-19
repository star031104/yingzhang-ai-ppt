"""Structured page-contract libraries, one per presentation preset.

A contract states the single communication job of a page (``responsibility``),
its semantic ``role``, optional source ``keywords`` that favour matching
sections, and the record roles it may draw on (``targets``, defaulting to the
role itself). Academic and business-plan decks keep their phase libraries; all
other presets share one planning algorithm driven by the entries below.
"""

from __future__ import annotations

PHASE_LABELS = {
    "context": "第一部分｜研究背景与目标",
    "method": "第二部分｜技术方案与系统实现",
    "evaluation": "第三部分｜实验设计与结果验证",
}

ACADEMIC_CONTRACT_LIBRARY = {
    "context": [
        {"role": "background", "responsibility": "用事实说明研究背景、现实场景与研究价值", "targets": ["background"]},
        {"role": "comparison", "responsibility": "比较现有研究并明确仍未解决的技术缺口", "targets": ["comparison", "background"]},
        {"role": "problem", "responsibility": "把研究问题拆成目标、任务边界与可验证贡献", "targets": ["problem", "architecture", "conclusion"]},
        {"role": "evidence", "responsibility": "交代研究对象、关键概念与材料来源", "targets": ["evidence", "background"]},
        {"role": "insight", "responsibility": "解释问题成因以及现有方案失效的关键环节", "targets": ["insight", "problem"]},
        {"role": "content", "responsibility": "建立后续技术方案需要回答的研究假设", "targets": ["problem", "content"]},
    ],
    "method": [
        {"role": "architecture", "responsibility": "用总体框架串联研究输入、关键模块与输出", "targets": ["architecture"]},
        {"role": "method", "responsibility": "说明关键数据、知识或材料的构建流程", "targets": ["method", "evidence"]},
        {"role": "method", "responsibility": "解释核心方法一的输入、处理步骤与输出", "targets": ["method"]},
        {"role": "method", "responsibility": "解释核心方法二的算法机制与关键实现", "targets": ["method"]},
        {"role": "architecture", "responsibility": "展示系统架构、模块协作与数据流转", "targets": ["architecture", "method"]},
        {"role": "evidence", "responsibility": "说明证据如何检索、对齐并支撑最终结论", "targets": ["evidence", "method"]},
        {"role": "content", "responsibility": "展示关键工程实现、接口与异常处理策略", "targets": ["architecture", "content"]},
        {"role": "method", "responsibility": "解释提示设计、任务拆解或推理约束", "targets": ["method"]},
        {"role": "architecture", "responsibility": "说明从离线构建到在线分析的完整运行链路", "targets": ["architecture", "method"]},
        {"role": "insight", "responsibility": "归纳技术方案中最关键的设计取舍", "targets": ["insight", "method"]},
    ],
    "evaluation": [
        {"role": "data", "responsibility": "交代实验环境、数据集、基线和评价指标", "targets": ["data", "evidence"]},
        {"role": "data", "responsibility": "呈现第一项核心任务的完整实验结果与含义", "targets": ["data"]},
        {"role": "data", "responsibility": "呈现第二项核心任务的完整实验结果与含义", "targets": ["data"]},
        {"role": "comparison", "responsibility": "用基线对比证明方法带来的真实改进", "targets": ["comparison", "data"]},
        {"role": "insight", "responsibility": "通过消融或误差分析解释结果为何成立", "targets": ["insight", "data"]},
        {"role": "data", "responsibility": "呈现第三项任务或综合任务的实验结果", "targets": ["data"]},
        {"role": "evidence", "responsibility": "用案例验证结果的可解释性与可追溯性", "targets": ["evidence", "data"]},
        {"role": "insight", "responsibility": "评估系统效率、质量、成本与适用边界", "targets": ["insight", "data"]},
        {"role": "comparison", "responsibility": "综合比较各任务表现并指出主要差异", "targets": ["comparison", "data"]},
        {"role": "insight", "responsibility": "把实验发现转化为可信的研究结论与局限", "targets": ["insight", "conclusion"]},
    ],
}

BUSINESS_PLAN_CONTRACT_LIBRARY = [
    {"role": "background", "responsibility": "项目缘起、公共价值与目标场景", "targets": ["background", "content"], "keywords": ["项目背景", "项目应用前景"], "phase": "opportunity"},
    {"role": "problem", "responsibility": "目标用户的核心痛点与现有服务断点", "targets": ["problem", "background"], "keywords": ["社会角度", "市场角度", "痛点"], "phase": "opportunity"},
    {"role": "data", "responsibility": "政策、行业与市场机会的量化依据", "targets": ["data", "background"], "keywords": ["政策角度", "商机分析", "行业分析"], "phase": "opportunity"},
    {"role": "comparison", "responsibility": "竞品格局、替代方案与未满足需求", "targets": ["comparison", "problem"], "keywords": ["竞争环境", "竞品分析"], "phase": "opportunity"},
    {"role": "architecture", "responsibility": "项目价值主张与闭环解决方案", "targets": ["architecture", "method"], "keywords": ["项目应用前景", "产品概况", "产品服务"], "phase": "solution"},
    {"role": "method", "responsibility": "产品服务、核心功能与用户路径", "targets": ["method", "content"], "keywords": ["产品服务", "功能模块"], "phase": "solution"},
    {"role": "method", "responsibility": "关键技术、AI 能力与知识服务实现", "targets": ["method", "architecture"], "keywords": ["关键技术", "技术实现", "技术优势", "RAG", "推荐"], "phase": "solution"},
    {"role": "architecture", "responsibility": "多角色协同、业务流程与服务闭环", "targets": ["architecture", "method"], "keywords": ["功能模块", "献血者端", "护士端", "管理员端"], "phase": "solution"},
    {"role": "architecture", "responsibility": "系统架构、数据层与部署保障", "targets": ["architecture", "method"], "keywords": ["架构设计", "调用关系", "数据层", "部署"], "phase": "solution"},
    {"role": "comparison", "responsibility": "功能创新、技术壁垒与差异化优势", "targets": ["comparison", "method"], "keywords": ["技术优势", "竞品分析", "创新"], "phase": "solution"},
    {"role": "method", "responsibility": "市场营销、用户增长与渠道策略", "targets": ["method", "content"], "keywords": ["市场营销策略", "推广", "渠道"], "phase": "execution"},
    {"role": "evidence", "responsibility": "团队分工、组织机制与执行能力", "targets": ["evidence", "content"], "keywords": ["创业团队", "团队简介", "团队成员", "组织架构", "公司管理"], "phase": "execution"},
    {"role": "data", "responsibility": "商业模式、收入来源与关键假设", "targets": ["data", "content"], "keywords": ["销售预测", "收入", "增值服务"], "phase": "execution"},
    {"role": "data", "responsibility": "财务预测、现金流与增长路径", "targets": ["data"], "keywords": ["财务预测", "现金流量", "资产负债"], "phase": "execution"},
    {"role": "data", "responsibility": "资本结构、资金需求与资金用途", "targets": ["data", "content"], "keywords": ["资本结构", "资金分配", "投资者需求"], "phase": "execution"},
    {"role": "insight", "responsibility": "主要风险、应对措施与阶段里程碑", "targets": ["insight", "problem", "conclusion"], "keywords": ["风险分析", "风险对冲", "应对措施"], "phase": "execution"},
]


def _c(role: str, responsibility: str, *keywords: str) -> dict:
    return {"role": role, "responsibility": responsibility, "keywords": list(keywords)}


# The ``business`` entry is the historical general-purpose library and is kept verbatim.
PRESET_CONTRACT_LIBRARIES: dict[str, dict] = {
    "business": {
        "cover": "封面与核心主张",
        "agenda": {"responsibility": "受众阅读路线", "title": "汇报路线", "bullets": ["问题与目标", "方案与证据", "结论与行动"]},
        "body": [
            _c("background", "交代受众背景与核心矛盾"), _c("problem", "明确要解决的问题与成功标准"),
            _c("insight", "提炼最关键的事实与洞察"), _c("architecture", "展示总体方案与工作机制"),
            _c("method", "说明关键举措、流程与责任分工"), _c("data", "用数据验证方案价值"),
            _c("comparison", "呈现选择、取舍与风险"),
        ],
        "conclusion": {"responsibility": "结论、行动与下一步", "title": "结论与下一步"},
    },
    "strategy": {
        "cover": "封面与战略主张",
        "agenda": {"responsibility": "战略推演路线", "title": "汇报路线", "bullets": ["现状与目标", "洞察与取舍", "举措与路线图"]},
        "body": [
            _c("background", "研判外部环境与业务现状", "现状", "环境", "行业"),
            _c("problem", "明确战略目标与需要回答的关键问题", "目标", "问题"),
            _c("insight", "提炼驱动判断的关键洞察", "洞察", "趋势"),
            _c("comparison", "比较战略选项并说明取舍依据", "选项", "取舍", "竞争"),
            _c("architecture", "呈现战略框架与能力布局", "战略", "框架"),
            _c("method", "拆解关键举措、责任与节奏", "举措", "实施"),
            _c("data", "测算预期价值与资源投入", "预测", "投入", "财务", "指标"),
            _c("insight", "识别主要风险与应对预案", "风险"),
        ],
        "conclusion": {"responsibility": "战略建议、路线图与决策请求", "title": "战略建议与路线图"},
    },
    "executive": {
        "cover": "封面与决策主题",
        "agenda": {"responsibility": "决策简报结构", "title": "简报结构", "bullets": ["核心判断", "指标与差距", "决策与行动"]},
        "body": [
            _c("insight", "先给出核心判断与决策要点", "结论", "摘要", "判断"),
            _c("data", "关键指标表现与目标达成", "指标", "业绩", "数据"),
            _c("comparison", "目标与实际的差距及原因", "差距", "对比"),
            _c("problem", "需要管理层关注的问题与风险", "问题", "风险"),
            _c("method", "可选方案与推荐行动", "方案", "举措", "建议"),
            _c("evidence", "支撑判断的关键事实", "案例", "证据"),
        ],
        "conclusion": {"responsibility": "决策请求、负责人与时间表", "title": "决策请求与行动计划"},
    },
    "review": {
        "cover": "封面与复盘主题",
        "agenda": {"responsibility": "复盘路线", "title": "复盘路线", "bullets": ["目标与结果", "差距与原因", "经验与行动"]},
        "body": [
            _c("background", "回顾周期目标与关键背景", "目标", "背景"),
            _c("data", "呈现结果与关键指标达成", "结果", "指标", "数据", "业绩"),
            _c("comparison", "对照目标找出差距", "差距", "对比", "同比", "环比"),
            _c("insight", "分析原因并提炼经验教训", "原因", "经验", "教训", "复盘"),
            _c("problem", "暴露的问题与风险", "问题", "风险"),
            _c("method", "改进举措与责任分工", "改进", "举措", "计划"),
        ],
        "conclusion": {"responsibility": "下一阶段目标与行动", "title": "下一阶段行动"},
    },
    "product": {
        "cover": "封面与产品主张",
        "agenda": {"responsibility": "发布路线", "title": "发布路线", "bullets": ["用户与痛点", "产品与能力", "价值与路线图"]},
        "body": [
            _c("problem", "目标用户、使用场景与核心痛点", "用户", "痛点", "场景"),
            _c("background", "市场与行业机会", "市场", "行业", "背景"),
            _c("architecture", "产品定位与整体方案", "产品", "定位", "方案"),
            _c("method", "核心功能与使用流程", "功能", "流程", "体验"),
            _c("architecture", "技术架构与关键能力", "架构", "技术"),
            _c("data", "用数据证明产品价值", "数据", "指标", "测试"),
            _c("comparison", "与竞品的差异化优势", "竞品", "对比", "优势"),
        ],
        "conclusion": {"responsibility": "发布计划与产品路线图", "title": "发布计划与路线图"},
    },
    "pitch": {
        "cover": "封面与公司愿景",
        "agenda": {"responsibility": "路演逻辑", "title": "路演逻辑", "bullets": ["痛点与市场", "产品与模式", "增长与壁垒", "团队与融资"]},
        "body": [
            _c("problem", "真实痛点与未被满足的需求", "痛点", "问题", "需求"),
            _c("background", "市场规模与进入时机", "市场", "规模", "行业"),
            _c("architecture", "产品与解决方案", "产品", "方案"),
            _c("data", "商业模式与收入来源", "商业模式", "收入", "盈利"),
            _c("data", "增长数据与关键里程碑", "增长", "用户", "里程碑"),
            _c("comparison", "竞争格局与核心壁垒", "竞争", "竞品", "壁垒", "优势"),
            _c("evidence", "团队背景与执行能力", "团队", "成员"),
        ],
        "conclusion": {"responsibility": "融资需求、资金用途与下一步", "title": "融资需求与资金用途"},
    },
    "marketing": {
        "cover": "封面与传播主张",
        "agenda": {"responsibility": "提案路线", "title": "提案路线", "bullets": ["受众与洞察", "定位与创意", "渠道与预算"]},
        "body": [
            _c("background", "市场环境与传播目标", "背景", "目标", "市场"),
            _c("problem", "目标受众与沟通难点", "受众", "用户", "人群"),
            _c("insight", "消费者洞察", "洞察"),
            _c("architecture", "品牌定位与核心创意", "定位", "创意", "概念"),
            _c("method", "渠道策略与执行排期", "渠道", "传播", "排期", "执行"),
            _c("data", "预算分配与效果指标", "预算", "指标", "KPI"),
            _c("evidence", "参考案例与过往成效", "案例"),
        ],
        "conclusion": {"responsibility": "执行计划与下一步", "title": "执行计划与下一步"},
    },
    "sales": {
        "cover": "封面与客户价值主张",
        "agenda": {"responsibility": "方案沟通路线", "title": "方案路线", "bullets": ["客户痛点", "方案与价值", "案例与合作"]},
        "body": [
            _c("problem", "客户现状与业务痛点", "客户", "痛点", "现状"),
            _c("architecture", "解决方案整体设计", "方案", "解决方案"),
            _c("method", "实施路径与服务保障", "实施", "交付", "服务"),
            _c("data", "量化价值与投资回报", "价值", "回报", "ROI", "收益"),
            _c("evidence", "成功案例与客户证言", "案例", "客户"),
            _c("comparison", "方案对比与选择理由", "对比", "优势"),
            _c("data", "报价与合作模式", "报价", "价格", "费用"),
        ],
        "conclusion": {"responsibility": "合作建议与下一步", "title": "合作建议与下一步"},
    },
    "teaching": {
        "cover": "封面与课程主题",
        "agenda": {"responsibility": "课堂结构", "title": "课堂结构", "bullets": ["学习目标", "概念与原理", "示例与练习"]},
        "body": [
            _c("background", "学习目标与课程导入", "目标", "导入", "背景"),
            _c("architecture", "核心概念与知识框架", "概念", "定义", "框架"),
            _c("method", "原理讲解与推导", "原理", "推导"),
            _c("evidence", "典型示例与解析", "示例", "例题", "案例"),
            _c("method", "操作步骤与要点", "步骤", "方法"),
            _c("problem", "常见误区与难点", "误区", "难点", "问题"),
            _c("insight", "课堂练习与思考", "练习", "思考"),
        ],
        "conclusion": {"responsibility": "课堂总结与课后任务", "title": "课堂总结"},
    },
    "training": {
        "cover": "封面与培训主题",
        "agenda": {"responsibility": "工作坊流程", "title": "工作坊流程", "bullets": ["目标与问题", "方法与示例", "练习与行动"]},
        "body": [
            _c("background", "培训目标与学员收获", "目标", "收获"),
            _c("problem", "工作中的典型问题", "问题", "挑战", "痛点"),
            _c("architecture", "核心认知与方法框架", "认知", "框架", "模型"),
            _c("method", "方法工具与操作步骤", "方法", "工具", "步骤"),
            _c("evidence", "实战示例与案例拆解", "示例", "案例"),
            _c("insight", "练习与讨论", "练习", "讨论", "演练"),
        ],
        "conclusion": {"responsibility": "行动计划与要点回顾", "title": "行动计划与要点回顾"},
    },
    "public": {
        "cover": "封面与工作主题",
        "agenda": {"responsibility": "汇报结构", "title": "汇报结构", "bullets": ["背景与现状", "举措与成效", "问题与计划"]},
        "body": [
            _c("background", "政策背景与工作要求", "政策", "背景", "要求"),
            _c("problem", "存在问题与短板", "问题", "短板", "困难"),
            _c("method", "主要举措与工作机制", "举措", "措施", "机制"),
            _c("data", "工作成效与量化数据", "成效", "成果", "数据"),
            _c("evidence", "典型案例与经验", "案例", "经验", "典型"),
            _c("insight", "形势研判与风险", "研判", "风险", "形势"),
        ],
        "conclusion": {"responsibility": "下一步工作计划", "title": "下一步工作计划"},
    },
    "keynote": {
        "cover": "封面与演讲主题",
        "agenda": {"responsibility": "演讲脉络", "title": "演讲脉络", "bullets": ["观点", "故事与转折", "启发与行动"]},
        "body": [
            _c("background", "引入话题与时代背景", "背景", "趋势"),
            _c("insight", "核心观点", "观点", "判断"),
            _c("evidence", "故事与案例", "故事", "案例"),
            _c("problem", "冲突与转折", "挑战", "冲突", "转折"),
            _c("data", "支撑观点的关键数据", "数据"),
            _c("insight", "启发与思考", "启发", "思考", "启示"),
        ],
        "conclusion": {"responsibility": "号召与行动", "title": "行动号召"},
    },
    "portfolio": {
        "cover": "封面与作品主题",
        "agenda": {"responsibility": "案例脉络", "title": "案例脉络", "bullets": ["背景与挑战", "过程与方案", "作品与结果"]},
        "body": [
            _c("background", "项目背景与个人角色", "背景", "项目", "角色"),
            _c("problem", "挑战与目标", "挑战", "目标", "问题"),
            _c("method", "设计过程与方法", "过程", "方法", "调研"),
            _c("architecture", "方案与关键决策", "方案", "设计", "决策"),
            _c("evidence", "作品呈现", "作品", "展示"),
            _c("data", "结果与影响", "结果", "数据", "影响"),
            _c("insight", "复盘与成长", "复盘", "反思", "经验"),
        ],
        "conclusion": {"responsibility": "总结与展望", "title": "总结与展望"},
    },
}
SUPPLEMENTARY_CONTRACTS = {
    "evidence": "用材料中的案例与证据支撑核心判断",
    "content": "解释材料中的关键内容及其意义",
    "data": "补充另一组结果，保留其独立来源和统计口径",
}
ACADEMIC_PRESETS = {"academic", "conference"}


def preset_library(preset: str) -> dict:
    """Library for a non-academic preset; unknown presets use the general business library."""
    return PRESET_CONTRACT_LIBRARIES.get(preset) or PRESET_CONTRACT_LIBRARIES["business"]


def allowed_roles(preset: str) -> set[str]:
    """All roles a deck of this preset may legitimately contain."""
    navigation = {"cover", "agenda", "section", "questions", "conclusion"}
    if preset in ACADEMIC_PRESETS:
        roles = {item["role"] for phase in ACADEMIC_CONTRACT_LIBRARY.values() for item in phase}
        roles |= {item["role"] for item in BUSINESS_PLAN_CONTRACT_LIBRARY}
    else:
        roles = {item["role"] for item in preset_library(preset)["body"]}
        roles |= set(SUPPLEMENTARY_CONTRACTS)
    # Generic narrative roles stay available so the model can refine a page's job.
    return roles | navigation | {"background", "problem", "insight", "comparison", "method", "architecture", "data", "evidence", "content"}


def general_contracts(preset: str, slide_count: int, records: list[dict]) -> list[dict]:
    """Build page contracts for every non-academic preset from its library."""
    library = preset_library(preset)
    contracts = [{"role": "cover", "responsibility": library["cover"], "targets": ["background"], "phase": "opening"}]
    if slide_count >= 8:
        contracts.append({"role": "agenda", "responsibility": library["agenda"]["responsibility"], "targets": [], "phase": "opening"})
    body_count = max(0, slide_count - len(contracts) - 1)
    available = {record["role"] for record in records} - {"conclusion"}
    titles = " ".join(str(record["section"].get("title", "")) for record in records).lower()

    def relevant_entry(entry: dict) -> bool:
        return entry["role"] in available or any(keyword.lower() in titles for keyword in entry.get("keywords", []))

    body = library["body"]
    relevant = [entry for entry in body if relevant_entry(entry)]
    if "evidence" in available and not any(entry["role"] == "evidence" for entry in relevant):
        relevant.append(_c("evidence", SUPPLEMENTARY_CONTRACTS["evidence"]))
    sequence = relevant or list(body)
    if relevant and body_count > len(sequence):
        data_count = sum(record["role"] == "data" for record in records)
        extra = min(data_count - 1, body_count - len(sequence))
        sequence = [*sequence, *[_c("data", SUPPLEMENTARY_CONTRACTS["data"])] * max(0, extra)]
    if "content" in available:
        content = _c("content", SUPPLEMENTARY_CONTRACTS["content"])
        sequence = [*sequence, content] if relevant else [content]
    # Short decks must retain results; a fixed prefix used to omit all data pages.
    if body_count < len(sequence) and any(entry["role"] == "data" for entry in sequence) and not any(
        entry["role"] == "data" for entry in sequence[:body_count]
    ):
        data_contract = next(entry for entry in sequence if entry["role"] == "data")
        sequence = sequence[:max(0, body_count - 1)] + [data_contract]
    cycled = (sequence * ((body_count // max(1, len(sequence))) + 1))[:body_count]
    for entry in cycled:
        contract = {"role": entry["role"], "responsibility": entry["responsibility"], "targets": [entry["role"]], "phase": "body"}
        if entry.get("keywords"):
            contract["keywords"] = list(entry["keywords"])
        contracts.append(contract)
    contracts.append({"role": "conclusion", "responsibility": library["conclusion"]["responsibility"], "targets": ["conclusion"], "phase": "closing"})
    return contracts[:slide_count]

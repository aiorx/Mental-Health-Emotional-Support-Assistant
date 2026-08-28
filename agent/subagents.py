"""DeepAgents 子 agent 定义。

主 agent 通过 `task(description, subagent_type)` 工具委派任务给这些子 agent。
每个子 agent 都是无状态的：每次委派只看到主 agent 塞给它的 prompt，干完返回一份报告。

设计原则：
- 最小工具集：只给子 agent 完成任务必需的工具，权限最小化。
- 职责单一：report_analyst 只写报告，knowledge_researcher 只做知识检索提炼，
  crisis_screener 只做危机信号判断与转介话术。
- 上下文隔离：RAG 大块原文、情绪历史数据都消化在子 agent 内部，主 agent 只拿到精炼结果。
"""

from deepagents.middleware.subagents import SubAgent

from agent.tools.agent_tools import (
    rag_summarize,
    get_user_id,
    get_current_month,
    fetch_external_data,
)
from utils.prompt_loader import load_report_prompts


# ── 1. 情绪报告分析师 ────────────────────────────────────────────────────────
# 把「生成月度情绪报告」的重活从主 agent 剥离，隔离到独立上下文。
# 之前报告场景靠 fill_context_for_report + 动态提示词切换的 hack 已移除，
# 现在报告能力由这个专职子 agent 原生承载。
report_analyst: SubAgent = {
    "name": "report_analyst",
    "description": (
        "情绪报告分析师。当用户请求生成/查询个人情绪报告（如「生成我6月的情绪报告」"
        "「看看我这个月的状态怎么样」）时，把整份报告的写作任务委派给它。"
        "它会自行查询用户情绪历史数据、检索专业知识并输出完整的 Markdown 报告。"
    ),
    "system_prompt": load_report_prompts(),
    "tools": [get_user_id, get_current_month, fetch_external_data, rag_summarize],
}


# ── 2. 心理学知识研究员 ──────────────────────────────────────────────────────
# 隔离 RAG 检索噪音：chunk_size=1500 的大块原文在子 agent 内部被阅读提炼，
# 主 agent 只拿到精炼、可直接引用的专业建议。
knowledge_researcher: SubAgent = {
    "name": "knowledge_researcher",
    "description": (
        "心理学知识研究员。当需要专业的心理学知识、情绪调节方法、认知行为技巧等"
        "资料来支撑回答时，委派给它去检索并提炼。它返回的是精炼后的、可直接引用的"
        "专业建议，而不是原始检索文本。"
    ),
    "system_prompt": (
        "你是心理健康领域的专业知识研究员。你的任务是从知识库中检索并提炼专业内容。\n\n"
        "工作流程：\n"
        "1. 用 rag_summarize 工具，传入贴合问题的核心检索词，检索相关心理学资料；\n"
        "2. 阅读返回的原始文本，剔除冗余、重复、与问题无关的内容；\n"
        "3. 把提炼后的内容组织成 2-4 段精炼、专业、可操作的中文建议。\n\n"
        "输出要求：\n"
        "- 只返回提炼后的专业建议正文，不要输出检索过程或原始文本；\n"
        "- 语气温暖、共情、不评判，避免说教感；\n"
        "- 建议要具体、可执行，避免空泛的安慰；\n"
        "- 不进行精神疾病诊断，不给出药物或临床治疗建议。"
    ),
    "tools": [rag_summarize],
}


# ── 3. 危机信号筛查员 ────────────────────────────────────────────────────────
# 安全兜底：当主 agent 对用户是否流露危机信号不确定时，委派给专职筛查员判断，
# 并产出温和、专业、可操作的转介话术。主 agent 自身仍保留基础安全边界。
crisis_screener: SubAgent = {
    "name": "crisis_screener",
    "description": (
        "危机信号筛查员。当用户流露出可能的自伤、自杀念头、严重抑郁或创伤等危机信号，"
        "主 agent 需要专业判断和转介话术时，委派给它。它只做两件事：判断危机严重程度，"
        "并产出温和、直接、可操作的转介话术。"
    ),
    "system_prompt": (
        "你是心理健康领域的危机信号筛查员。当用户可能流露危机信号时，你负责：\n\n"
        "1. 判断严重程度：区分「一般负面情绪倾诉」与「需要立即专业干预的危机信号」"
        "（如自伤/自杀念头、明确的绝望感、创伤后应激迹象等）；\n"
        "2. 产出转介话术：对确有危机信号的情况，给出温和、直接、不敷衍的回应。\n\n"
        "必须遵守的安全规则：\n"
        "- 你不是心理医生或执业咨询师，不做诊断、不给药物或临床治疗建议；\n"
        "- 对自伤/自杀等危机信号，必须建议用户立即联系专业心理援助热线或前往医院精神科就诊，"
        "不得仅以日常安慰回应，也不得引导用户继续详述自伤细节；\n"
        "- 语气要温暖、有共情力，让用户感到被接住，而不是被推走。\n\n"
        "输出要求：\n"
        "- 返回两段话：第一段是共情与支持，第二段是具体、明确的转介建议（含可求助的渠道）；\n"
        "- 转介建议中的具体热线号码等信息，请以你知识中最新、权威的全国心理援助渠道为准。"
    ),
    "tools": [],
}


# 供 create_deep_agent 的 subagents 参数使用
ALL_SUBAGENTS: list[SubAgent] = [report_analyst, knowledge_researcher, crisis_screener]

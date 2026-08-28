import sqlite3

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from deepagents.middleware import SummarizationMiddleware
from langchain.agents.middleware import TodoListMiddleware
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from agent.base_agent import BaseAgent
from model.factory import chat_model
from utils.path_tool import get_abs_path
from utils.prompt_loader import load_system_prompts
from agent.tools.agent_tools import (
    rag_summarize,
    get_weather,
    get_user_location,
    get_user_id,
    fetch_external_data,
    get_current_month,
    log_mood,
)
from agent.tools.middleware import monitor_tool, log_before_model
from agent.subagents import ALL_SUBAGENTS
from agent.context import RuntimeContext

# ── 心理陪伴场景定制：write_todos 计划粒度说明 ────────────────────────────────
# 完整替换 TodoListMiddleware 默认的 WRITE_TODOS_SYSTEM_PROMPT，用中文对齐本场景，
# 让模型在「生成月度情绪报告」这类多步任务上列出的计划符合本系统的工具链路。
TODO_SYSTEM_PROMPT = """## `write_todos` 工具（心理健康陪伴场景）

你有一个 `write_todos` 工具，用于在多步骤任务中规划和管理你的工作步骤。它帮你把复杂目标拆解成小步骤并跟踪进度。

### 何时使用
- 当用户请求涉及多个步骤时（例如：生成月度情绪报告、查询并分析情绪历史、结合天气与知识库给出综合建议），先用 `write_todos` 列一个清晰计划。
- 简单的倾诉陪伴、单点提问、纯闲聊，**不要**使用此工具，直接温暖地回应即可。写 todo 消耗时间与 token，只在真正需要时才用。

### 本场景的典型步骤粒度（供参考，不必照搬）
- 获取用户 ID（get_user_id）
- 获取目标月份（get_current_month，或用户明确指定的月份）
- 检索该月情绪记录（fetch_external_data）
- 检索相关专业知识（rag_summarize）
- 综合分析并输出报告 / 建议

### 使用规则
- 每完成一步，**立即**把该 todo 标记为 `completed`，不要把多步攒在一起再批量标记。
- 正在执行的步骤标记为 `in_progress`；除非全部完成，否则至少保留一个 `in_progress`。
- 过程中若发现新的必要步骤，随时更新 todo 列表（新增、删除不再相关的项）。
- `write_todos` 每次更新会**整体替换** todo 列表，因此同一轮内不要并行调用多次。

### 收尾
当你完成所有工作后，在最后一次 `write_todos` 调用**之后**的消息里给出最终回答——回答的主体是用户要的内容（数据、报告、建议），而不是「任务已完成」这类确认语。"""


class DeepAgent(BaseAgent):
    """基于 LangChain DeepAgents 的 harness agent。

    相比原 ReactAgent 的差异：
    - 使用 create_deep_agent 构建，挂载 TodoListMiddleware 提供 planning 能力；
    - 通过 subagents 提供 multi-agent 能力：report_analyst（情绪报告）、
      knowledge_researcher（知识提炼）、crisis_screener（危机筛查）；
    - 移除 fill_context_for_report + 动态提示词切换的报告 hack，报告能力由子 agent 原生承载。
    """

    def __init__(self):
        # 用项目根解析 checkpoint 路径：本地（Windows）与容器（/app）都能正确命中，
        # 避免写死 /app/... 导致本地无法运行。
        checkpoint_path = get_abs_path("data/external/checkpoint.db")
        self.checkpoint = SqliteSaver(
            sqlite3.connect(checkpoint_path, check_same_thread=False)
        )

        # 文件持久化：把 agent 的文件读写锚定到 data/agent_files/。
        # FilesystemBackend 默认 virtual_mode=True，会拦截路径穿越（..、~）与
        # 越界绝对路径，agent 只能在这个目录内读写，碰不到 .env、源代码等。
        # 注意：FilesystemBackend 不支持 execute 工具（需 SandboxBackend），
        # 因此 shell 执行能力在此后端下不可用，进一步降低了风险。
        agent_files_dir = get_abs_path("data/agent_files")
        self.backend = FilesystemBackend(root_dir=agent_files_dir, virtual_mode=True)

        # 摘要压缩：当对话 token 数达到阈值时，自动把旧消息摘要压缩并落盘到
        # backend 的 conversation_history/ 目录，只保留最近 keep 条消息，
        # 避免长对话 token 无限膨胀（此前 95 条消息稀释 system prompt 的根因）。
        summarization = SummarizationMiddleware(
            model=chat_model,
            backend=self.backend,
            trigger=("tokens", 8000),
            keep=("messages", 20),
        )

        self.agent = create_deep_agent(
            model=chat_model,
            system_prompt=load_system_prompts(),
            tools=[
                rag_summarize,
                get_user_id,
                get_user_location,
                get_weather,
                fetch_external_data,
                get_current_month,
                log_mood,
            ],
            # 三个专职子 agent，主 agent 通过 task 工具委派
            subagents=ALL_SUBAGENTS,
            # 自我进化 skills：从 backend root 下的 /skills 目录加载技能。
            # 每个技能是一个含 SKILL.md 的目录，agent 可按需 read_file 读取完整指令，
            # 也可用 write_file 自行沉淀新技能（实现自我进化闭环）。
            skills=["/skills"],
            # 用户偏好记忆：加载持久化行为规范，agent 可 edit_file 沉淀用户偏好。
            memory=["/memory/AGENTS.md"],
            # TodoListMiddleware 提供 planning，summarization 提供上下文压缩，
            # monitor_tool/log_before_model 提供可观测性。
            middleware=[
                TodoListMiddleware(system_prompt=TODO_SYSTEM_PROMPT),
                summarization,
                monitor_tool,
                log_before_model,
            ],
            checkpointer=self.checkpoint,
            backend=self.backend,
            # 运行时上下文：注入用户身份等不可变信息，供工具读取
            context_schema=RuntimeContext,
            # 人工介入：对「保存情绪记录」这个有副作用的动作，执行前暂停等用户审批。
            interrupt_on={"log_mood": True},
        )

    def execute_stream(self, query: str, config=None, context: RuntimeContext | None = None):
        """流式执行，产出 dict 事件流。

        事件结构：
            {"type": "text",  "content": str}         —— 模型回复文本增量
            {"type": "todos", "todos": list}          —— write_todos 更新后的计划列表（仅变化时推送）
            {"type": "interrupt", "payload": dict}    —— 人工介入请求（如 log_mood 待审批），流在此暂停

        context: 运行时上下文（当前用户 ID、城市、月份），注入后供工具读取。
        """
        self.checkpoint.setup()
        input_dict = {"messages": [HumanMessage(content=query)]}

        stream_kwargs = {"config": config, "stream_mode": "values"}
        if context is not None:
            stream_kwargs["context"] = context

        last_todos = None
        for chunk in self.agent.stream(input_dict, **stream_kwargs):
            # 人工介入：遇到中断，把审批请求抛给前端并停住
            if "__interrupt__" in chunk:
                interrupt_payload = chunk["__interrupt__"][0].value
                yield {"type": "interrupt", "payload": interrupt_payload}
                return

            # 计划：仅当 todos 相对上一轮发生变化时推送，避免每个 state 快照都重复
            todos = chunk.get("todos")
            if todos is not None and todos != last_todos:
                last_todos = todos
                yield {"type": "todos", "todos": todos}

            # 文本：只取模型的回复（AIMessage），跳过工具返回的 ToolMessage，
            # 避免把 "Updated todo list to [...]" 等工具内部文字泄露给前端。
            latest_message = chunk["messages"][-1]
            if isinstance(latest_message, AIMessage) and latest_message.content:
                yield {"type": "text", "content": latest_message.content.strip() + "\n"}

    def resume_stream(self, decisions: list[dict], config=None, context: RuntimeContext | None = None):
        """从人工介入中断点恢复执行，产出与 execute_stream 相同的事件流。

        decisions 形如 [{"type": "approve"}] 或 [{"type": "reject", "message": "..."}]，
        与中断请求里的 action_requests 一一对应。
        """
        stream_kwargs = {"config": config, "stream_mode": "values"}
        if context is not None:
            stream_kwargs["context"] = context

        last_todos = None
        for chunk in self.agent.stream(
            Command(resume={"decisions": decisions}),
            **stream_kwargs,
        ):
            # 恢复后仍可能再次触发中断（例如又调用了 log_mood）
            if "__interrupt__" in chunk:
                interrupt_payload = chunk["__interrupt__"][0].value
                yield {"type": "interrupt", "payload": interrupt_payload}
                return

            todos = chunk.get("todos")
            if todos is not None and todos != last_todos:
                last_todos = todos
                yield {"type": "todos", "todos": todos}

            latest_message = chunk["messages"][-1]
            if isinstance(latest_message, AIMessage) and latest_message.content:
                yield {"type": "text", "content": latest_message.content.strip() + "\n"}

    def chat(self, message: str) -> str:
        """非流式：返回完整回复（聚合所有 text 事件）"""
        parts = []
        for event in self.execute_stream(message):
            if event["type"] == "text":
                parts.append(event["content"])
        return "".join(parts).strip()

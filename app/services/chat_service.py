import json
from collections import defaultdict

from agent.deep_agent import DeepAgent
from agent.context import RuntimeContext
from agent.tools.agent_tools import summarize_and_save_session


class ChatService:
    def __init__(self):
        self.agent = DeepAgent()
        # 内存消息缓存：{session_id: [messages...]}
        # 注意：重启服务后丢失，生产环境应持久化到数据库
        self._session_messages: dict[str, list[dict]] = defaultdict(list)

    @staticmethod
    def _context_for(session_id: str) -> RuntimeContext:
        """由 session_id（即用户 ID）构造运行时上下文，注入 agent。

        前端选定用户后，session_id 就是该用户的 ID，这里把它作为
        user_id 注入，使 get_user_id 等工具返回真实用户，而非随机值。
        """
        return RuntimeContext(user_id=session_id)

    def chat(self, message: str, session_id: str) -> str:
        """非流式：返回完整回复（聚合所有文本事件，忽略计划事件）"""
        config = {"configurable": {"thread_id": session_id}}
        text_parts = []
        for event in self.agent.execute_stream(message, config):
            if event.get("type") == "text":
                text_parts.append(event["content"])

        full_reply = "".join(text_parts).strip()

        # 保存本轮对话到内存缓存
        self._session_messages[session_id].append({"role": "user", "content": message})
        self._session_messages[session_id].append({"role": "assistant", "content": full_reply})

        return full_reply

    def chat_stream(self, message: str, session_id: str):
        """流式：生成 SSE 事件流，推送「文本增量」「计划更新」「人工介入」三类事件

        SSE 事件结构：
            {"session_id":..., "type":"text",      "delta":"...", "done":false}
            {"session_id":..., "type":"todos",     "todos":[...], "done":false}
            {"session_id":..., "type":"interrupt", "payload":{...},"done":false}
            {"session_id":..., "delta":"", "done":true}   # 结束标记
        """
        config = {"configurable": {"thread_id": session_id}}
        context = self._context_for(session_id)

        # 先记录用户消息
        self._session_messages[session_id].append({"role": "user", "content": message})

        response_chunks = []
        for event in self.agent.execute_stream(message, config, context=context):
            if event.get("type") == "text":
                chunk = event["content"]
                response_chunks.append(chunk)
                data = json.dumps({
                    "session_id": session_id,
                    "type": "text",
                    "delta": chunk,
                    "done": False,
                }, ensure_ascii=False)
                yield f"data: {data}\n\n"

            elif event.get("type") == "todos":
                data = json.dumps({
                    "session_id": session_id,
                    "type": "todos",
                    "todos": event["todos"],
                    "done": False,
                }, ensure_ascii=False)
                yield f"data: {data}\n\n"

            elif event.get("type") == "interrupt":
                data = json.dumps({
                    "session_id": session_id,
                    "type": "interrupt",
                    "payload": event["payload"],
                    "done": False,
                }, ensure_ascii=False)
                yield f"data: {data}\n\n"
                # 中断发生：流在此暂停，等待前端调用 /chat/resume 恢复
                return

        # 记录 AI 回复
        full_reply = "".join(response_chunks).strip()
        self._session_messages[session_id].append({"role": "assistant", "content": full_reply})

        # 发送结束标记
        yield f"data: {json.dumps({'session_id': session_id, 'delta': '', 'done': True})}\n\n"

    def resume_stream(self, session_id: str, decisions: list[dict]):
        """从人工介入中断点恢复，继续产出 SSE 事件流"""
        config = {"configurable": {"thread_id": session_id}}
        context = self._context_for(session_id)

        response_chunks = []
        for event in self.agent.resume_stream(decisions, config, context=context):
            if event.get("type") == "text":
                chunk = event["content"]
                response_chunks.append(chunk)
                data = json.dumps({
                    "session_id": session_id,
                    "type": "text",
                    "delta": chunk,
                    "done": False,
                }, ensure_ascii=False)
                yield f"data: {data}\n\n"

            elif event.get("type") == "todos":
                data = json.dumps({
                    "session_id": session_id,
                    "type": "todos",
                    "todos": event["todos"],
                    "done": False,
                }, ensure_ascii=False)
                yield f"data: {data}\n\n"

            elif event.get("type") == "interrupt":
                data = json.dumps({
                    "session_id": session_id,
                    "type": "interrupt",
                    "payload": event["payload"],
                    "done": False,
                }, ensure_ascii=False)
                yield f"data: {data}\n\n"
                return

        full_reply = "".join(response_chunks).strip()
        self._session_messages[session_id].append({"role": "assistant", "content": full_reply})
        yield f"data: {json.dumps({'session_id': session_id, 'delta': '', 'done': True})}\n\n"

    def get_session_messages(self, session_id: str) -> list[dict]:
        """获取指定 session 的历史消息"""
        return self._session_messages.get(session_id, [])

    def clear_session(self, session_id: str) -> bool:
        """清空指定 session 的历史消息（内存缓存 + LangGraph checkpoint）

        同时删除 checkpoint 是必要的：否则同一 thread_id 的历史会无限累积，
        把 system prompt 里的规划/流程指令稀释掉，导致模型在多步任务上不再调用 write_todos。
        """
        cleared = False
        if session_id in self._session_messages:
            del self._session_messages[session_id]
            cleared = True

        try:
            self.agent.checkpoint.delete_thread(session_id)
            cleared = True
        except Exception:
            # 删除 checkpoint 失败不阻断前端清空内存的语义
            pass

        return cleared

    @staticmethod
    def save_session(messages: list[dict], user_id: str) -> dict:
        """保存对话并生成情绪记录"""
        return summarize_and_save_session(messages=messages, user_id=user_id)

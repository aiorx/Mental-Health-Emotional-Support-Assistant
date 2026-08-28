"""
Streamlit 前端 - 心理健康情感支持助手

架构说明：
    Streamlit (本文件)  <-->  HTTP 请求  <-->  FastAPI 后端 (app/main.py)

交互流程：
    1. 进入 app 先选择用户 ID，选定后进入聊天界面
    2. 侧边栏展示当前用户的历史情绪记录（按月分组）
    3. 对话流式响应走 SSE，支持计划展示与人工介入审批

运行方式：
    # 先启动 FastAPI 后端（假设端口 8000）
    uvicorn app.main:app --reload --port 8000

    # 再启动 Streamlit 前端
    streamlit run app.py
"""

import os
import time

import requests
import streamlit as st

# ── 配置 ─────────────────────────────────────────────────────────────────────
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

# 可选用户 ID 列表（与后端 records.csv 中的用户对应）
USER_IDS = [str(i) for i in range(1001, 1011)]


# ── 页面配置 ─────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="心理健康情感支持助手",
    page_icon="🧠",
    layout="centered",
    initial_sidebar_state="expanded",
)

# 轻量视觉优化：统一字体、卡片圆角、侧边栏留白
st.markdown(
    """
    <style>
    .block-container { padding-top: 2rem; }
    div[data-testid="stSidebarContent"] { padding: 1.2rem 1rem; }
    div[data-testid="stMetric"] {
        background: #f8f9fb; border-radius: 12px; padding: 0.8rem 1rem;
    }
    h1, h2, h3 { letter-spacing: 0.2px; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ── Session State 初始化 ─────────────────────────────────────────────────────
if "selected_user_id" not in st.session_state:
    st.session_state["selected_user_id"] = None   # None = 尚未选定用户

if "session_id" not in st.session_state:
    st.session_state["session_id"] = ""

if "messages" not in st.session_state:
    st.session_state["messages"] = []

if "pending_approval" not in st.session_state:
    st.session_state["pending_approval"] = None


# ── 辅助函数 ─────────────────────────────────────────────────────────────────
def send_chat_message(message: str, session_id: str):
    """调用 /chat/stream，逐条 yield 事件（text / todos / interrupt）"""
    response = requests.post(
        f"{API_BASE_URL}/chat/stream",
        json={"session_id": session_id, "message": message},
        stream=True,
        timeout=120,
    )
    if response.status_code != 200:
        error_detail = response.json().get("detail", "未知错误")
        raise Exception(f"API 请求失败: {error_detail}")

    for line in response.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        import json
        try:
            data = json.loads(line[6:])
        except json.JSONDecodeError:
            continue

        event_type = data.get("type", "text")
        if event_type == "todos":
            yield {"type": "todos", "todos": data.get("todos", [])}
        elif event_type == "interrupt":
            yield {"type": "interrupt", "payload": data.get("payload", {})}
        elif data.get("delta"):
            yield {"type": "text", "content": data["delta"]}

        if data.get("done"):
            break


def send_resume_message(session_id: str, decisions: list):
    """调用 /chat/resume，提交审批决策并续跑，事件结构同上"""
    response = requests.post(
        f"{API_BASE_URL}/chat/resume",
        json={"session_id": session_id, "decisions": decisions},
        stream=True,
        timeout=120,
    )
    if response.status_code != 200:
        error_detail = response.json().get("detail", "未知错误")
        raise Exception(f"恢复请求失败: {error_detail}")

    for line in response.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        import json
        try:
            data = json.loads(line[6:])
        except json.JSONDecodeError:
            continue

        event_type = data.get("type", "text")
        if event_type == "todos":
            yield {"type": "todos", "todos": data.get("todos", [])}
        elif event_type == "interrupt":
            yield {"type": "interrupt", "payload": data.get("payload", {})}
        elif data.get("delta"):
            yield {"type": "text", "content": data["delta"]}

        if data.get("done"):
            break


def fetch_user_history_api(user_id: str):
    """调用 /chat/history/{user_id}，返回按月份分组的情绪记录"""
    response = requests.get(
        f"{API_BASE_URL}/chat/history/{user_id}",
        timeout=10,
    )
    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise Exception(response.json().get("detail", "查询失败"))
    return response.json()


def clear_session_api(session_id: str):
    """调用 DELETE /chat/{session_id}，清空会话"""
    response = requests.delete(
        f"{API_BASE_URL}/chat/{session_id}",
        timeout=10,
    )
    if response.status_code != 200:
        raise Exception(response.json().get("detail", "清空失败"))
    return True


def render_todo_panel(todos: list[dict]):
    """渲染「助手计划」折叠面板：展示任务清单与进度勾选"""
    if not todos:
        return
    _status_icon = {"pending": "⬜", "in_progress": "🔵", "completed": "✅"}
    _plan_lines = [
        f"{_status_icon.get(t.get('status'), '⬜')} {t.get('content', '')}"
        for t in todos
    ]
    st.chat_message("assistant").expander("📋 助手计划").markdown(
        "\n".join(_plan_lines)
    )


def mood_emoji(score) -> str:
    """根据情绪评分返回可视化 emoji"""
    try:
        s = float(score)
    except (TypeError, ValueError):
        return "❓"
    if s <= 3:
        return "😞"
    if s <= 5:
        return "😐"
    if s <= 7:
        return "🙂"
    return "😊"


# ══════════════════════════════════════════════════════════════════════════════
# 阶段一：选择用户（尚未选定身份时显示欢迎页）
# ══════════════════════════════════════════════════════════════════════════════
if st.session_state["selected_user_id"] is None:
    st.markdown("<br>", unsafe_allow_html=True)
    _, center, _ = st.columns([1, 2, 1])
    with center:
        st.markdown("## 🧠 心理健康情感支持助手")
        st.caption("一个安全倾诉的空间 · 请先选择你的身份")

        st.markdown(
            """
            <div style="background:#f8f9fb;border-radius:14px;padding:1.2rem 1.4rem;
                        margin:1rem 0;">
                <p style="color:#4a5568;margin:0;">进入前，请选择你的用户 ID。
                系统会根据你的身份加载对应的情绪档案与对话历史。</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        selected = st.selectbox("当前用户 ID", options=USER_IDS, key="user_picker")

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("进入助手 →", use_container_width=True, type="primary"):
            st.session_state["selected_user_id"] = selected
            st.session_state["session_id"] = selected   # 用户 ID 即会话 ID
            st.session_state["messages"] = []           # 切换用户时清空对话
            st.session_state["pending_approval"] = None
            st.rerun()

        st.markdown(
            """
            <p style="color:#a0aec0;font-size:0.85rem;margin-top:1.5rem;text-align:center;">
            ⚠️ 本助手仅供情感支持与心理知识参考，不构成专业心理诊断或治疗建议。</p>
            """,
            unsafe_allow_html=True,
        )

    st.stop()


# ══════════════════════════════════════════════════════════════════════════════
# 阶段二：聊天界面（已选定用户）
# ══════════════════════════════════════════════════════════════════════════════
current_uid = st.session_state["selected_user_id"]


# ── 侧边栏：当前用户信息 + 历史记录 + 操作 ───────────────────────────────────
with st.sidebar:
    st.header("🧠 心理陪伴助手")

    # 当前用户
    st.markdown(f"**当前用户：** `{current_uid}`")

    # 切换用户
    if st.button("🔄 切换用户", use_container_width=True):
        st.session_state["selected_user_id"] = None
        st.session_state["messages"] = []
        st.session_state["pending_approval"] = None
        st.rerun()

    st.divider()

    # 历史情绪记录
    st.subheader("📖 历史情绪记录")
    history = fetch_user_history_api(current_uid)
    if history is None:
        st.caption("暂无情绪记录，和助手聊聊后即可生成。")
    else:
        months = history.get("months", [])
        records_by_month = history.get("records_by_month", {})
        for month in reversed(months):   # 最新月份在上
            records = records_by_month.get(month, [])
            with st.expander(f"📅 {month}（{len(records)} 条）"):
                for r in records:
                    emoji = mood_emoji(r.get("mood_score"))
                    score = r.get("mood_score", "-")
                    tags = r.get("mood_tags", "-")
                    t = r.get("record_time", "-")[-5:]   # 只取 HH:MM
                    st.markdown(f"{emoji} **{score}/10** · {tags}")
                    st.caption(f"🕒 {t} · {r.get('event_note', '')}")
                    st.markdown("---")

    st.divider()

    # 清空对话
    if st.button("🗑️ 清空本次对话", use_container_width=True):
        try:
            clear_session_api(st.session_state["session_id"])
        except Exception:
            pass
        st.session_state["messages"] = []
        st.session_state["pending_approval"] = None
        st.rerun()

    st.divider()
    st.caption(
        "⚠️ 本助手仅供情感支持与心理知识参考，不构成专业心理诊断或治疗建议。"
        "如有严重心理困扰，请及时寻求专业心理咨询师的帮助。"
    )


# ── 主区：标题 + 历史消息 ─────────────────────────────────────────────────────
st.markdown(f"### 🧠 你好，用户 {current_uid}")
st.caption("一个安全倾诉的空间 · 随时和我聊聊你的感受")

# 渲染历史消息
for message in st.session_state["messages"]:
    st.chat_message(message["role"]).write(message["content"])
    if message.get("role") == "assistant" and message.get("todos"):
        render_todo_panel(message["todos"])


# ── 人工介入审批 ─────────────────────────────────────────────────────────────
if st.session_state.get("pending_approval"):
    approval = st.session_state["pending_approval"]
    action_requests = approval.get("action_requests", [])
    if action_requests:
        action = action_requests[0]
        tool_name = action.get("name", "")
        args = action.get("args", {})

        # 仅对 log_mood 做情绪记录确认的友好文案
        if tool_name == "log_mood":
            score = args.get("mood_score", "-")
            st.chat_message("assistant").markdown(
                f"### 💭 我注意到你想记录此刻的情绪\n\n"
                f"这是我从对话中感受到的，帮你整理成了一条记录：\n\n"
                f"- 😊 **情绪评分**：{score} / 10\n"
                f"- 🏷️ **情绪标签**：{args.get('mood_tags', '-')}\n"
                f"- 😴 **睡眠时长**：{args.get('sleep_hours', '-')} 小时\n"
                f"- 📝 **事件备注**：{args.get('event_note', '-')}\n\n"
                f"**是否把它保存到你的情绪档案？**"
            )
        else:
            st.chat_message("assistant").warning(
                f"⏸️ 助手想执行「{tool_name}」，需要你的确认：\n\n"
                f"参数：{args}"
            )

        col1, col2 = st.columns(2)
        if col1.button("✅ 保存记录", use_container_width=True, type="primary"):
            with st.spinner("正在保存…"):
                try:
                    resume_gen = send_resume_message(
                        st.session_state["session_id"],
                        [{"type": "approve"}],
                    )
                    chunks = [
                        item.get("content", "")
                        for item in resume_gen
                        if item.get("type") == "text"
                    ]
                    st.session_state["messages"].append(
                        {"role": "assistant", "content": "".join(chunks).strip()}
                    )
                except Exception as e:
                    st.error(f"❌ 恢复失败：{e}")
                finally:
                    st.session_state["pending_approval"] = None
                    st.rerun()

        if col2.button("❌ 暂不记录", use_container_width=True):
            with st.spinner("正在继续…"):
                try:
                    resume_gen = send_resume_message(
                        st.session_state["session_id"],
                        [{"type": "reject", "message": "用户暂不保存这条情绪记录"}],
                    )
                    chunks = [
                        item.get("content", "")
                        for item in resume_gen
                        if item.get("type") == "text"
                    ]
                    st.session_state["messages"].append(
                        {"role": "assistant", "content": "".join(chunks).strip()}
                    )
                except Exception as e:
                    st.error(f"❌ 恢复失败：{e}")
                finally:
                    st.session_state["pending_approval"] = None
                    st.rerun()


# ── 对话输入 ─────────────────────────────────────────────────────────────────
prompt = st.chat_input("有什么想聊的，随时告诉我…")

if prompt:
    st.chat_message("user").write(prompt)
    st.session_state["messages"].append({"role": "user", "content": prompt})

    with st.spinner("助手思考中…"):
        try:
            stream_generator = send_chat_message(
                message=prompt,
                session_id=st.session_state["session_id"],
            )

            response_chunks = []
            todo_snapshots = []
            interrupt_holder = []   # 用列表承载中断 payload，避免闭包 nonlocal 问题

            def _capture_and_display(gen):
                for item in gen:
                    if item.get("type") == "todos":
                        todo_snapshots.append(item.get("todos", []))
                        continue
                    if item.get("type") == "interrupt":
                        interrupt_holder.append(item.get("payload", {}))
                        continue
                    chunk = item.get("content", "")
                    response_chunks.append(chunk)
                    for char in chunk:
                        time.sleep(0.01)
                        yield char

            st.chat_message("assistant").write_stream(
                _capture_and_display(stream_generator)
            )

            full_response = "".join(response_chunks)

            assistant_msg = {"role": "assistant", "content": full_response}
            if todo_snapshots:
                assistant_msg["todos"] = todo_snapshots[-1]
            st.session_state["messages"].append(assistant_msg)

            if interrupt_holder:
                st.session_state["pending_approval"] = interrupt_holder[0]

        except Exception as e:
            st.error(f"❌ 请求失败：{e}")
            st.session_state["messages"].append(
                {"role": "assistant", "content": f"请求失败: {e}"}
            )

    st.rerun()

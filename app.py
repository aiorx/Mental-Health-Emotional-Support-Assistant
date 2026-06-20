import time

import streamlit as st

from agent.react_agent import ReactAgent
from agent.tools.agent_tools import summarize_and_save_session

# ── 页面配置 ──────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="心理健康情感支持助手",
    page_icon="🧠",
    layout="centered",
)

st.title("🧠 心理健康情感支持助手")
st.caption("一个安全倾诉的空间 · 基于 RAG + ReAct Agent 构建")
st.divider()

# ── Session State 初始化 ──────────────────────────────────────────────────────
if "agent" not in st.session_state:
    st.session_state["agent"] = ReactAgent()

if "message" not in st.session_state:
    st.session_state["message"] = []

if "current_user_id" not in st.session_state:
    st.session_state["current_user_id"] = "1001"

# ── 侧边栏 ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 设置")

    # 用户 ID 选择
    user_id = st.selectbox(
        "当前用户",
        options=[str(i) for i in range(1001, 1011)],
        index=int(st.session_state["current_user_id"]) - 1001,
        key="user_select",
    )
    st.session_state["current_user_id"] = user_id

    st.divider()
    st.subheader("💾 保存本次对话")
    st.caption("点击下方按钮，AI 将自动提取本次对话中的情绪信息并保存到你的情绪档案。")

    if st.button("📝 保存并生成情绪记录", use_container_width=True):
        messages = st.session_state.get("message", [])
        if not messages:
            st.warning("当前没有对话记录，请先和助手聊聊。")
        else:
            with st.spinner("AI 正在分析本次对话情绪..."):
                result = summarize_and_save_session(
                    messages=messages,
                    user_id=st.session_state["current_user_id"],
                )

            if result.get("saved"):
                st.success("✅ 情绪记录已保存！")
                st.markdown(f"""
| 项目 | 内容 |
|------|------|
| 情绪评分 | {result.get('mood_score', '-')} / 10 |
| 情绪标签 | {result.get('mood_tags', '-')} |
| 睡眠时长 | {result.get('sleep_hours', '-')} h |
| 事件摘要 | {result.get('event_note', '-')} |
""")
                st.info(f"**对话摘要：** {result.get('chat_summary', '')}")
            else:
                st.error(f"❌ 保存失败：{result.get('error', '未知错误')}")

    st.divider()
    if st.button("🗑️ 清空本次对话", use_container_width=True):
        st.session_state["message"] = []
        st.session_state["agent"] = ReactAgent()
        st.rerun()

    st.divider()
    st.caption(
        "⚠️ 本助手仅供情感支持与心理知识参考，不构成专业心理诊断或治疗建议。"
        "如有严重心理困扰，请及时寻求专业心理咨询师的帮助。"
    )

# ── 渲染历史消息 ──────────────────────────────────────────────────────────────
for message in st.session_state["message"]:
    st.chat_message(message["role"]).write(message["content"])

# ── 对话输入 ──────────────────────────────────────────────────────────────────
prompt = st.chat_input("有什么想聊的，随时告诉我…")

if prompt:
    st.chat_message("user").write(prompt)
    st.session_state["message"].append({"role": "user", "content": prompt})

    response_chunks = []

    with st.spinner("助手思考中…"):
        res_stream = st.session_state["agent"].execute_stream(prompt)

        def _capture(generator, cache_list):
            for chunk in generator:
                cache_list.append(chunk)
                for char in chunk:
                    time.sleep(0.01)
                    yield char

        st.chat_message("assistant").write_stream(
            _capture(res_stream, response_chunks)
        )

    full_response = "".join(response_chunks)
    st.session_state["message"].append(
        {"role": "assistant", "content": full_response}
    )
    st.rerun()
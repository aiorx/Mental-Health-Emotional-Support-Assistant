import csv
import json
import os
import random
import re
from datetime import datetime

from langchain_core.tools import tool

from rag.rag_service import RagSummarizeService
from utils.config_handler import agent_conf
from utils.logger_handler import logger
from utils.path_tool import get_abs_path

# ── 内存缓存（避免重复读取 CSV） ──────────────────────────────────────────────
_mood_cache: dict = {}

user_ids = ["1001", "1002", "1003", "1004", "1005",
            "1006", "1007", "1008", "1009", "1010"]

month_arr = ["2025-01", "2025-02", "2025-03", "2025-04", "2025-05", "2025-06", "2025-07", "2025-08", "2025-09", "2025-10", "2025-11", "2025-12"]

rag = RagSummarizeService()


# ─────────────────────────────────────────────────────────────────────────────
# 内部辅助函数
# ─────────────────────────────────────────────────────────────────────────────

def _data_path() -> str:
    return get_abs_path(agent_conf["external_data_path"])


def _invalidate_cache():
    """写入 CSV 后清空内存缓存，确保下次读取拿到最新数据"""
    global _mood_cache
    _mood_cache = {}


def _ensure_csv_header(path: str):
    """如果文件不存在或为空，写入 CSV 表头"""
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "user_id", "mood_score", "mood_tags",
                "event_note", "sleep_hours", "time", "chat_summary"
            ])


def _load_mood_data() -> dict:
    """将 CSV 加载到内存字典，结构：{user_id: {YYYY-MM: [records...]}}"""
    global _mood_cache
    if _mood_cache:
        return _mood_cache

    path = _data_path()
    if not os.path.exists(path):
        logger.warning(f"[_load_mood_data] 情绪记录文件不存在：{path}")
        return {}

    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            uid = row["user_id"].strip()
            month = row["time"].strip()[:7]          # 取 YYYY-MM 部分

            _mood_cache.setdefault(uid, {})
            _mood_cache[uid].setdefault(month, [])
            _mood_cache[uid][month].append({
                "情绪评分":  row["mood_score"].strip(),
                "情绪标签":  row["mood_tags"].strip(),
                "事件备注":  row["event_note"].strip(),
                "睡眠时长":  row["sleep_hours"].strip(),
                "记录时间":  row["time"].strip(),
                "对话摘要":  row.get("chat_summary", "").strip(),
            })

    return _mood_cache


def _write_mood_row(user_id: str, mood_score: int, mood_tags: str,
                    event_note: str, sleep_hours: float,
                    chat_summary: str = "") -> None:
    """追加一行情绪记录到 CSV"""
    path = _data_path()
    _ensure_csv_header(path)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(path, "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            user_id, mood_score, mood_tags,
            event_note, sleep_hours, now, chat_summary
        ])
    _invalidate_cache()
    logger.info(f"[_write_mood_row] 用户 {user_id} 情绪记录已写入 CSV")


# ─────────────────────────────────────────────────────────────────────────────
# Agent 工具（供 ReAct Agent 调用）
# ─────────────────────────────────────────────────────────────────────────────

@tool(description=(
    "从心理健康知识库检索专业参考资料。"
    "入参 query 为检索词（贴合用户问题的核心关键词）；"
    "返回与情绪管理、心理调适、认知行为等相关的专业内容。"
))
def rag_summarize(query: str) -> str:
    return rag.rag_summarize(query)


@tool(description=(
    "获取指定城市的当前天气，用于分析天气对情绪的潜在影响。"
    "入参 city 为城市名称字符串；返回包含温度、湿度、AQI 等信息的字符串。"
))
def get_weather(city: str) -> str:
    # TODO: 替换为真实天气 API（如 OpenWeatherMap）
    return (
        f"城市 {city} 天气：晴，气温 26°C，湿度 50%，"
        f"南风 1 级，AQI 21（优），最近 6 小时降雨概率极低"
    )


@tool(description="获取用户所在城市名称，用于查询当地天气，以纯字符串形式返回。")
def get_user_location() -> str:
    return random.choice(["深圳", "合肥", "杭州", "北京", "成都"])


@tool(description=(
    "获取当前用户的唯一标识 ID，以纯字符串形式返回。"
    "在需要查询或保存用户专属记录前调用。"
))
def get_user_id() -> str:
    return random.choice(user_ids)


@tool(description="获取当前月份，格式固定为 YYYY-MM，以纯字符串形式返回。")
def get_current_month() -> str:
    return random.choice(month_arr)
    # return datetime.now().strftime("%Y-%m")


@tool(description=(
    "查询用户指定月份的情绪历史记录。"
    "入参：user_id（用户 ID 字符串）、month（YYYY-MM 格式月份字符串）；"
    "返回该月所有情绪记录的列表字符串，未找到则返回空字符串。"
))
def fetch_external_data(user_id: str, month: str) -> str:
    data = _load_mood_data()
    records = data.get(user_id, {}).get(month, [])
    if not records:
        logger.warning(f"[fetch_external_data] 未找到 {user_id} 在 {month} 的记录")
        return ""
    return str(records)


@tool(description=(
    "记录用户本次情绪状态到历史档案。"
    "入参：\n"
    "  - user_id: 用户 ID\n"
    "  - mood_score: 情绪评分 1-10（整数，1 最差，10 最好）\n"
    "  - mood_tags: 情绪标签，逗号分隔（如 '焦虑,疲惫' 或 '平静,满足'）\n"
    "  - event_note: 今日主要事件或感受的一句话描述\n"
    "  - sleep_hours: 昨晚睡眠时长（小时，浮点数，未提及填 7.0）\n"
    "  - chat_summary: 根据本次对话内容自动生成的摘要（模型自行提炼）\n"
    "返回：保存成功或失败的说明字符串。"
))
def log_mood(
    user_id: str,
    mood_score: int,
    mood_tags: str,
    event_note: str,
    sleep_hours: float = 7.0,
    chat_summary: str = "",
) -> str:
    try:
        _write_mood_row(user_id, mood_score, mood_tags,
                        event_note, sleep_hours, chat_summary)
        return (
            f"✅ 情绪记录已保存｜"
            f"评分：{mood_score}/10｜标签：{mood_tags}｜"
            f"睡眠：{sleep_hours}h"
        )
    except Exception as e:
        logger.error(f"[log_mood] 写入失败：{e}")
        return f"❌ 记录失败：{str(e)}"


@tool(description=(
    "无入参，无返回值。"
    "调用后触发中间件为报告生成场景注入上下文，驱动后续 Prompt 切换为报告模式。"
    "生成月度情绪报告前必须首先调用此工具。"
))
def fill_context_for_report():
    return "fill_context_for_report 已调用"


# ─────────────────────────────────────────────────────────────────────────────
# 非工具函数：供 app.py 侧边栏"保存本次对话"按钮调用
# ─────────────────────────────────────────────────────────────────────────────

def summarize_and_save_session(
    messages: list[dict],
    user_id: str,
) -> dict:
    """
    用大模型对本次对话进行摘要，自动提取情绪信息并写入 CSV。

    参数：
        messages : st.session_state["message"] 的消息列表
                   每个元素格式为 {"role": "user"/"assistant", "content": "..."}
        user_id  : 当前用户 ID

    返回：
        包含提取字段的字典，供前端展示确认信息。
    """
    from model.factory import chat_model

    if not messages:
        return {"error": "对话记录为空，无法保存"}

    # 只保留 user / assistant 两种角色的消息，拼成对话文本
    conv_lines = [
        f"{'用户' if m['role'] == 'user' else '助手'}：{m['content']}"
        for m in messages
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]
    conv_text = "\n".join(conv_lines)

    summary_prompt = f"""以下是一段用户与心理健康支持助手的完整对话记录：

{conv_text}

请仔细分析对话内容，以 JSON 格式输出以下字段（仅输出 JSON，不要包含其他文字或 markdown 代码块）：
{{
  "mood_score": <1-10 的整数，1 最差 10 最好，根据用户整体情绪状态判断>,
  "mood_tags": "<逗号分隔的情绪标签，从以下词汇中选取最贴切的 2-4 个：焦虑、压力、低落、疲惫、平静、满足、愉快、孤独、愤怒、担忧、希望、感激>",
  "event_note": "<用一句话概括用户本次倾诉的核心困扰或主要话题>",
  "sleep_hours": <用户提及的睡眠小时数（浮点数），未提及填 7.0>,
  "chat_summary": "<用 2-3 句话总结本次对话的主要内容和结论>"
}}"""

    try:
        response = chat_model.invoke(summary_prompt)
        raw = response.content.strip()
        # 去除可能存在的 markdown 代码块标记
        raw = re.sub(r"```json\s*|\s*```", "", raw).strip()
        extracted = json.loads(raw)
    except Exception as e:
        logger.error(f"[summarize_and_save_session] LLM 摘要解析失败：{e}")
        extracted = {
            "mood_score": 5,
            "mood_tags": "未知",
            "event_note": "对话摘要解析失败",
            "sleep_hours": 7.0,
            "chat_summary": conv_text[:80] + "...",
        }

    try:
        _write_mood_row(
            user_id=user_id,
            mood_score=int(extracted.get("mood_score", 5)),
            mood_tags=extracted.get("mood_tags", ""),
            event_note=extracted.get("event_note", ""),
            sleep_hours=float(extracted.get("sleep_hours", 7.0)),
            chat_summary=extracted.get("chat_summary", ""),
        )
        extracted["saved"] = True
    except Exception as e:
        logger.error(f"[summarize_and_save_session] CSV 写入失败：{e}")
        extracted["saved"] = False
        extracted["error"] = str(e)

    return extracted


if __name__ == "__main__":
    print(rag_summarize("如何缓解工作焦虑"))
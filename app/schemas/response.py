from pydantic import BaseModel
from typing import Optional


class ChatResponse(BaseModel):
    """对话响应"""
    session_id: str
    reply: str


class ChatStreamChunk(BaseModel):
    """流式对话的单个 chunk"""
    session_id: str
    delta: str          # 本次增量文本
    done: bool = False  # 是否结束


class SaveSessionResponse(BaseModel):
    """保存情绪记录响应"""
    saved: bool
    mood_score: Optional[int] = None
    mood_tags: Optional[str] = None
    sleep_hours: Optional[float] = None
    event_note: Optional[str] = None
    chat_summary: Optional[str] = None
    error: Optional[str] = None


class MoodRecord(BaseModel):
    """单条情绪记录"""
    mood_score: str
    mood_tags: str
    event_note: str
    sleep_hours: str
    record_time: str
    chat_summary: str


class QueryRecordsResponse(BaseModel):
    """查询情绪记录响应"""
    user_id: str
    month: str
    records: list[MoodRecord]


class UserHistoryResponse(BaseModel):
    """用户全部情绪历史记录响应（按月份分组）"""
    user_id: str
    months: list[str]                 # 月份列表，如 ["2025-01", "2025-02"]
    records_by_month: dict[str, list[MoodRecord]]  # 月份 -> 该月记录列表


class ErrorResponse(BaseModel):
    """统一错误响应"""
    detail: str

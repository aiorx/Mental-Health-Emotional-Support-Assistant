from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from schemas.request import ChatRequest, SaveSessionRequest, QueryRecordsRequest, ResumeRequest
from schemas.response import (
    ChatResponse,
    SaveSessionResponse,
    QueryRecordsResponse,
    UserHistoryResponse,
    MoodRecord,
    ErrorResponse,
)
from services.chat_service import ChatService
from agent.tools.agent_tools import _load_mood_data

router = APIRouter(
    prefix="/chat",
    tags=["chat"],
)

chat_service = ChatService()


# ── 非流式对话 ────────────────────────────────────────────────────────────────
@router.post(
    "/",
    response_model=ChatResponse,
    responses={500: {"model": ErrorResponse}},
)
def chat(req: ChatRequest):
    """接收用户消息，返回完整 AI 回复"""
    try:
        reply = chat_service.chat(
            message=req.message,
            session_id=req.session_id,
        )
        return ChatResponse(session_id=req.session_id, reply=reply)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 流式对话（SSE） ───────────────────────────────────────────────────────────
@router.post(
    "/stream",
    responses={500: {"model": ErrorResponse}},
)
def chat_stream(req: ChatRequest):
    """接收用户消息，以 SSE 流式返回 AI 回复"""
    try:
        stream = chat_service.chat_stream(
            message=req.message,
            session_id=req.session_id,
        )
        return StreamingResponse(stream, media_type="text/event-stream")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 人工介入审批后恢复执行 ────────────────────────────────────────────────────
@router.post(
    "/resume",
    responses={500: {"model": ErrorResponse}},
)
def resume_stream(req: ResumeRequest):
    """用户对中断的关键动作做出审批后，从断点恢复执行"""
    try:
        stream = chat_service.resume_stream(
            session_id=req.session_id,
            decisions=req.decisions,
        )
        return StreamingResponse(stream, media_type="text/event-stream")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 保存对话并生成情绪记录 ────────────────────────────────────────────────────
@router.post(
    "/session/save",
    response_model=SaveSessionResponse,
    responses={400: {"model": ErrorResponse}},
)
def save_session(req: SaveSessionRequest):
    """保存指定 session 的对话记录，AI 自动分析情绪并写入档案"""
    # 从 checkpoint / session 中获取历史消息
    messages = chat_service.get_session_messages(req.session_id)
    if not messages:
        raise HTTPException(status_code=400, detail="该 session 没有对话记录")

    result = chat_service.save_session(messages=messages, user_id=req.user_id)
    return SaveSessionResponse(
        saved=result.get("saved", False),
        mood_score=result.get("mood_score"),
        mood_tags=result.get("mood_tags"),
        sleep_hours=result.get("sleep_hours"),
        event_note=result.get("event_note"),
        chat_summary=result.get("chat_summary"),
        error=result.get("error"),
    )


# ── 查询用户情绪记录 ──────────────────────────────────────────────────────────
@router.post(
    "/records",
    response_model=QueryRecordsResponse,
    responses={404: {"model": ErrorResponse}},
)
def query_records(req: QueryRecordsRequest):
    """查询指定用户某月的情绪历史记录"""
    data = _load_mood_data()
    records = data.get(req.user_id, {}).get(req.month, [])
    if not records:
        raise HTTPException(
            status_code=404,
            detail=f"未找到用户 {req.user_id} 在 {req.month} 的记录",
        )

    return QueryRecordsResponse(
        user_id=req.user_id,
        month=req.month,
        records=[
            MoodRecord(
                mood_score=r["情绪评分"],
                mood_tags=r["情绪标签"],
                event_note=r["事件备注"],
                sleep_hours=r["睡眠时长"],
                record_time=r["记录时间"],
                chat_summary=r.get("对话摘要", ""),
            )
            for r in records
        ],
    )


# ── 查询用户全部情绪历史记录 ──────────────────────────────────────────────────
@router.get(
    "/history/{user_id}",
    response_model=UserHistoryResponse,
    responses={404: {"model": ErrorResponse}},
)
def user_history(user_id: str):
    """返回指定用户的全部情绪记录，按月份分组，供前端侧边栏展示"""
    data = _load_mood_data()
    months_map = data.get(user_id, {})
    if not months_map:
        raise HTTPException(
            status_code=404,
            detail=f"未找到用户 {user_id} 的情绪记录",
        )

    months = sorted(months_map.keys())
    records_by_month = {}
    for month in months:
        records_by_month[month] = [
            MoodRecord(
                mood_score=r["情绪评分"],
                mood_tags=r["情绪标签"],
                event_note=r["事件备注"],
                sleep_hours=r["睡眠时长"],
                record_time=r["记录时间"],
                chat_summary=r.get("对话摘要", ""),
            )
            for r in months_map[month]
        ]

    return UserHistoryResponse(
        user_id=user_id,
        months=months,
        records_by_month=records_by_month,
    )


# ── 清空 session ──────────────────────────────────────────────────────────────
@router.delete(
    "/{session_id}",
    responses={404: {"model": ErrorResponse}},
)
def clear_session(session_id: str):
    """清空指定 session 的历史消息"""
    if chat_service.clear_session(session_id):
        return {"message": f"Session {session_id} 已清空"}
    raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")

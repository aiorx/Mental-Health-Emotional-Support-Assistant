from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """对话请求"""
    session_id: str = Field(..., description="会话 ID，用于维持多轮对话上下文")
    message: str = Field(..., min_length=1, description="用户发送的消息")


class SaveSessionRequest(BaseModel):
    """保存对话并生成情绪记录请求"""
    session_id: str = Field(..., description="会话 ID")
    user_id: str = Field(..., description="用户 ID")


class QueryRecordsRequest(BaseModel):
    """查询用户情绪记录请求"""
    user_id: str = Field(..., description="用户 ID")
    month: str = Field(..., description="月份，格式 YYYY-MM", pattern=r"^\d{4}-\d{2}$")


class ResumeRequest(BaseModel):
    """人工介入审批后恢复执行请求"""
    session_id: str = Field(..., description="会话 ID")
    decisions: list[dict] = Field(..., description="审批决策列表，如 [{'type':'approve'}] 或 [{'type':'reject','message':'...'}]")

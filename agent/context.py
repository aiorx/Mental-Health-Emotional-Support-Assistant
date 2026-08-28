"""运行时上下文 schema。

用于在每次对话执行时，把「当前是谁、在哪、什么月份」等运行期信息注入 agent，
供 get_user_id / get_user_location / get_current_month 等工具读取，
解决此前工具随机返回用户 ID 导致情绪记录写错用户档案的上下文断裂问题。
"""

from pydantic import BaseModel, Field


class RuntimeContext(BaseModel):
    """一次对话运行期的不可变上下文。

    字段均可选：未注入时工具会回退到随机值（兼容无前端的直接调用场景）。
    """

    user_id: str | None = Field(default=None, description="当前用户 ID，前端登录时确定")
    city: str | None = Field(default=None, description="用户所在城市")
    month: str | None = Field(default=None, description="当前月份，格式 YYYY-MM")

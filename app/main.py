import sys
import os

# 确保项目根目录在 sys.path 中，这样 `from agent.xxx` 能正确解析
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.chat import router as chat_router

app = FastAPI(
    title="Mental Health Emotional Support Assistant",
    description="个人智能体尝试",
    version="1.0.0",
)

# ── CORS（前端独立部署时必填，允许浏览器跨域请求） ───────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],           # 生产环境改为具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 注册路由 ─────────────────────────────────────────────────────────────────
app.include_router(chat_router)


@app.get("/health")
def health():
    return {
        "status": "success",
        "message": "Server is running"
    }

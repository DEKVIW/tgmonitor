"""
FastAPI 应用主入口
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.models.config import settings
from app.api import auth, messages, statistics, admin
from app.schemas.admin import SystemConfigResponse
import logging

# 配置日志
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL))
logger = logging.getLogger(__name__)

# 创建 FastAPI 应用
app = FastAPI(
    title="TG频道监控 API",
    description="Telegram 频道消息监控系统 API",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# 配置 CORS
# 从环境变量获取前端URL，如果没有则使用默认值
frontend_url = settings.FRONTEND_URL if hasattr(settings, 'FRONTEND_URL') and settings.FRONTEND_URL else "http://localhost:3000"
allowed_origins = [
    frontend_url,
    "http://localhost:3000",
    "http://localhost:5173",  # Vite 默认端口
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(auth.router)
app.include_router(messages.router)
app.include_router(statistics.router)
app.include_router(admin.router)


@app.get("/", summary="API 根路径")
async def root():
    """API 根路径，返回 API 信息"""
    return {
        "message": "TG频道监控 API",
        "version": "1.0.0",
        "docs": "/api/docs",
        "redoc": "/api/redoc"
    }


@app.get("/api/health", summary="健康检查")
async def health_check():
    """健康检查端点"""
    return {"status": "healthy"}


@app.get("/api/config/public", response_model=SystemConfigResponse, summary="获取公开系统配置")
async def get_public_config():
    """
    获取公开的系统配置（无需认证）
    
    用于前端判断是否启用游客模式
    """
    return SystemConfigResponse(
        public_dashboard_enabled=settings.PUBLIC_DASHBOARD_ENABLED
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


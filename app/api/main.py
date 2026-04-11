"""
FastAPI 应用主入口
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.models.config import settings
from app.api import admin, admin_accounts_runtime, admin_backups, admin_extras_runtime, admin_resource_ops, auth_runtime_v2, messages_runtime, resource_ops_public, statistics
from app.api import admin_security, security
from app.schemas.admin_models import PublicSystemConfigResponse
from app.services.account_service import bootstrap_account_storage
from app.services.backup_scheduler import start_backup_scheduler, stop_backup_scheduler
from app.services.dedup_scheduler import start_dedup_scheduler, stop_dedup_scheduler
from app.services.link_check_scheduler import start_link_check_scheduler, stop_link_check_scheduler
from app.services.system_config_service import get_public_system_config_values
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
app.include_router(auth_runtime_v2.router)
app.include_router(messages_runtime.router)
app.include_router(statistics.router)
app.include_router(admin.router)
app.include_router(admin_accounts_runtime.router)
app.include_router(admin_security.router)
app.include_router(admin_backups.router)
app.include_router(admin_extras_runtime.router)
app.include_router(admin_resource_ops.router)
app.include_router(security.router)
app.include_router(resource_ops_public.router)


@app.on_event("startup")
async def startup_runtime_services() -> None:
    bootstrap_account_storage()
    start_backup_scheduler()
    start_dedup_scheduler()
    start_link_check_scheduler()


@app.on_event("shutdown")
async def shutdown_runtime_services() -> None:
    stop_backup_scheduler()
    stop_dedup_scheduler()
    stop_link_check_scheduler()


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


@app.get("/api/config/public", response_model=PublicSystemConfigResponse, summary="获取公开系统配置")
async def get_public_config():
    """
    获取公开的系统配置（无需认证）
    
    用于前端判断是否启用游客模式
    """
    return PublicSystemConfigResponse(**get_public_system_config_values())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


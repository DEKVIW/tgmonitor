# 配置文件
# 这里只写骨架，后续再补充具体实现

from pydantic_settings import BaseSettings
from dotenv import load_dotenv
from typing import Optional

load_dotenv()  # 加载 .env 文件

class Settings(BaseSettings):
    # Telegram API 配置
    TELEGRAM_API_ID: int
    TELEGRAM_API_HASH: str

    # 数据库配置（同步 + 可选异步）
    DATABASE_URL: str
    DATABASE_URL_ASYNC: Optional[str] = None

    # 默认频道配置
    DEFAULT_CHANNELS: str

    # 日志级别
    LOG_LEVEL: str = "INFO"

    # Docker 环境标识
    DOCKER_ENV: str = "false"

    # 新增密钥
    SECRET_SALT: str
    PUBLIC_ADS_ENABLED: bool = False
    PUBLIC_FEED_TOP_AD_HTML_DESKTOP: str = ""
    PUBLIC_FEED_TOP_AD_HTML_MOBILE: str = ""
    PUBLIC_FEED_INLINE_AD_HTML_DESKTOP: str = ""
    PUBLIC_FEED_INLINE_AD_HTML_MOBILE: str = ""
    PUBLIC_FEED_INLINE_EVERY_N: int = 8
    UMAMI_ENABLED: bool = False
    UMAMI_SCRIPT_URL: str = ""
    UMAMI_WEBSITE_ID: str = ""
    UMAMI_HOST_URL: str = ""
    UMAMI_SHARE_URL: str = ""
    
    # 前端URL（用于CORS配置）
    FRONTEND_URL: Optional[str] = "http://localhost:3000"

    # 游客模式配置（允许未登录用户访问消息列表）
    PUBLIC_DASHBOARD_ENABLED: bool = False

    # 链接检测默认配置
    LINK_CHECK_DEFAULT_MAX_CONCURRENT: int = 5
    LINK_CHECK_MAX_ALLOWED_CONCURRENT: int = 10
    LINK_CHECK_MAX_ALLOWED_LINKS: int = 1000
    LINK_CHECK_POLL_INTERVAL_SECONDS: int = 2

    # 监控服务配置
    MONITOR_CHANNEL_REFRESH_INTERVAL_SECONDS: int = 60
    MONITOR_DB_WRITE_MAX_RETRIES: int = 3
    MONITOR_DB_WRITE_RETRY_DELAY_SECONDS: float = 1.0

    class Config:
        env_file = ".env"  # 指定 .env 文件
        env_file_encoding = "utf-8"

settings = Settings() 

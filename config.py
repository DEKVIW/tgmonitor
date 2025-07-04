# 配置文件
# 这里只写骨架，后续再补充具体实现

from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()  # 加载 .env 文件

class Settings(BaseSettings):
    # Telegram API 配置
    TELEGRAM_API_ID: int
    TELEGRAM_API_HASH: str

    # 数据库配置
    DATABASE_URL: str

    # 默认频道配置
    DEFAULT_CHANNELS: str

    # 日志级别
    LOG_LEVEL: str = "INFO"

    # Docker 环境标识
    DOCKER_ENV: str = "false"

    # 新增密钥
    SECRET_SALT: str

    class Config:
        env_file = ".env"  # 指定 .env 文件
        env_file_encoding = "utf-8"

settings = Settings() 
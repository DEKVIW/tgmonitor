from sqlalchemy import Column, Integer, String, DateTime, JSON, ARRAY, create_engine
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
from config import settings

Base = declarative_base()

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, nullable=False)
    title = Column(String)
    description = Column(String)
    links = Column(JSON)  # 存储各种网盘链接
    tags = Column(ARRAY(String))  # 标签数组
    source = Column(String)  # 来源
    channel = Column(String)  # 频道
    group_name = Column(String)  # 群组
    bot = Column(String)  # 机器人
    created_at = Column(DateTime, default=datetime.utcnow)
    netdisk_types = Column(JSON, default=list)  # 存储网盘类型数组，兼容SQLite和其他数据库

class Credential(Base):
    __tablename__ = "credentials"
    id = Column(Integer, primary_key=True, index=True)
    api_id = Column(String, nullable=False)
    api_hash = Column(String, nullable=False)

class DedupStats(Base):
    __tablename__ = "dedup_stats"
    id = Column(Integer, primary_key=True)
    run_time = Column(DateTime, nullable=False)
    inserted = Column(Integer, nullable=False)
    deleted = Column(Integer, nullable=False)

class Channel(Base):
    __tablename__ = "channels"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, nullable=False)

# 数据库连接配置
DATABASE_URL = settings.DATABASE_URL

# 创建数据库引擎，指定时区
engine = create_engine(DATABASE_URL, connect_args={"options": "-c timezone=Asia/Shanghai"})

# 创建所有表
def create_tables():
    Base.metadata.create_all(bind=engine) 
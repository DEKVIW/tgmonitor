from sqlalchemy import Column, Integer, String, DateTime, JSON, ARRAY, create_engine
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

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

# 数据库连接配置
DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/tg_monitor"

# 创建数据库引擎
engine = create_engine(DATABASE_URL)

# 创建所有表
def create_tables():
    Base.metadata.create_all(bind=engine) 
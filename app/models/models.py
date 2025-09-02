from sqlalchemy import Column, Integer, String, DateTime, JSON, ARRAY, create_engine, Float, Boolean, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
from app.models.config import settings

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
    netdisk_types = Column(JSONB, default=list)  # 存储网盘类型数组，兼容SQLite和其他数据库

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

# 新增：链接检测统计表
class LinkCheckStats(Base):
    __tablename__ = "link_check_stats"
    
    id = Column(Integer, primary_key=True, index=True)
    check_time = Column(DateTime, nullable=False, index=True)  # 检测时间，加索引便于查询
    total_messages = Column(Integer, nullable=False)            # 检测消息总数
    total_links = Column(Integer, nullable=False)               # 检测链接总数
    valid_links = Column(Integer, nullable=False)               # 有效链接数
    invalid_links = Column(Integer, nullable=False)             # 无效链接数
    deleted_messages = Column(Integer, default=0)               # 删除消息数（暂时为0）
    updated_messages = Column(Integer, default=0)               # 更新消息数（暂时为0）
    netdisk_stats = Column(JSON)                                # 各网盘统计
    check_duration = Column(Float)                              # 检测耗时（秒）
    status = Column(String(50), default='completed')           # 检测状态
    created_at = Column(DateTime, default=datetime.utcnow)     # 创建时间

# 新增：链接检测详情表
class LinkCheckDetails(Base):
    __tablename__ = "link_check_details"
    
    id = Column(Integer, primary_key=True, index=True)
    check_time = Column(DateTime, nullable=False, index=True)  # 检测时间，关联stats表
    message_id = Column(Integer, nullable=False, index=True)   # 消息ID，关联messages表
    netdisk_type = Column(String(50), index=True)              # 网盘类型，便于统计
    url = Column(Text)                                          # 链接URL
    is_valid = Column(Boolean, nullable=False)                 # 是否有效
    response_time = Column(Float)                              # 响应时间
    error_reason = Column(String(200))                         # 错误原因
    action_taken = Column(String(50), default='none')         # 采取的行动（暂时为'none'）
    created_at = Column(DateTime, default=datetime.utcnow)     # 创建时间

# 数据库连接配置
DATABASE_URL = settings.DATABASE_URL

# 创建数据库引擎，添加连接池配置和时区设置
engine = create_engine(
    DATABASE_URL, 
    connect_args={"options": "-c timezone=Asia/Shanghai"},
    pool_size=5,           # 连接池大小
    max_overflow=10,       # 最大溢出连接
    pool_timeout=30,       # 连接超时时间（秒）
    pool_recycle=3600,     # 连接回收时间（1小时）
    pool_pre_ping=True,    # 连接前ping测试
    echo=False,            # 关闭SQL日志
    pool_reset_on_return='commit'  # 连接返回时重置
)

# 创建所有表
def create_tables():
    Base.metadata.create_all(bind=engine) 
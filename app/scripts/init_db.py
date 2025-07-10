from app.models.models import create_tables, Channel, engine
from sqlalchemy.orm import Session
from app.models.config import settings

def init_channels():
    # 从配置中获取默认频道列表
    default_channels = settings.DEFAULT_CHANNELS.split(',')
    
    # 创建数据库会话
    with Session(engine) as session:
        # 检查每个频道是否已存在
        for username in default_channels:
            username = username.strip()
            if not username:
                continue
                
            # 检查频道是否已存在
            existing = session.query(Channel).filter_by(username=username).first()
            if not existing:
                # 创建新频道记录
                channel = Channel(username=username)
                session.add(channel)
                print(f"添加频道: {username}")
        
        # 提交更改
        session.commit()

if __name__ == "__main__":
    print("正在创建表...")
    create_tables()
    print("正在初始化频道...")
    init_channels()
    print("初始化完成！") 
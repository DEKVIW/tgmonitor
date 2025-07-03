from models import Message, engine
from sqlalchemy.orm import Session
import json

def migrate_netdisk_types():
    with Session(engine) as session:
        messages = session.query(Message).all()
        updated = 0
        for msg in messages:
            if msg.links and (not msg.netdisk_types or len(msg.netdisk_types) == 0):
                # 提取links的key作为网盘类型
                netdisk_types = list(msg.links.keys())
                msg.netdisk_types = netdisk_types
                updated += 1
        session.commit()
        print(f"已更新 {updated} 条历史消息的 netdisk_types 字段")

if __name__ == "__main__":
    migrate_netdisk_types() 
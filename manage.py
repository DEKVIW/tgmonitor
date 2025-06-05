import sys
from sqlalchemy.orm import Session
from models import Channel, Message, engine
from sqlalchemy import update, delete
import ast
from datetime import datetime, timedelta
import json

def list_channels():
    with Session(engine) as session:
        chans = session.query(Channel).all()
        print("当前频道列表：")
        for chan in chans:
            print(f"- {chan.username}")

def add_channel(username):
    with Session(engine) as session:
        if session.query(Channel).filter_by(username=username).first():
            print("频道已存在！")
        else:
            session.add(Channel(username=username))
            session.commit()
            print(f"已添加频道：{username}")

def del_channel(username):
    with Session(engine) as session:
        chan = session.query(Channel).filter_by(username=username).first()
        if chan:
            session.delete(chan)
            session.commit()
            print(f"已删除频道：{username}")
        else:
            print("频道不存在！")

def edit_channel(old_name, new_name):
    with Session(engine) as session:
        chan = session.query(Channel).filter_by(username=old_name).first()
        if chan:
            chan.username = new_name
            session.commit()
            print(f"已将频道 {old_name} 修改为 {new_name}")
        else:
            print("原频道不存在！")

def fix_tags():
    with Session(engine) as session:
        msgs = session.query(Message).all()
        fixed = 0
        for msg in msgs:
            if msg.tags is not None and not isinstance(msg.tags, list):
                try:
                    tags_fixed = ast.literal_eval(msg.tags)
                    if isinstance(tags_fixed, list):
                        session.execute(update(Message).where(Message.id==msg.id).values(tags=tags_fixed))
                        fixed += 1
                except Exception as e:
                    print(f"ID={msg.id} tags修复失败: {e}")
        session.commit()
        print(f"已修复tags字段脏数据条数: {fixed}")

def dedup_links():
    """改进的去重逻辑，保留最新消息，添加详细日志"""
    with Session(engine) as session:
        # 1. 记录去重前的统计信息
        total_before = session.query(Message).count()
        print(f"\n去重前总消息数: {total_before}")
        
        # 2. 按时间正序获取所有消息
        all_msgs = session.query(Message).order_by(Message.timestamp.asc()).all()
        print(f"开始处理 {len(all_msgs)} 条消息...")
        
        link_to_id = {}  # 存储链接到消息ID的映射
        id_to_delete = set()  # 存储需要删除的消息ID
        preserved_messages = set()  # 存储保留的消息ID
        
        # 3. 遍历消息并记录详细日志
        for msg in all_msgs:
            if not msg.links:
                continue
                
            # 4. 遍历消息中的所有链接
            for url in msg.links.values():
                if url in link_to_id:
                    # 如果链接已存在，删除旧消息
                    old_id = link_to_id[url]
                    if old_id not in preserved_messages:
                        id_to_delete.add(old_id)
                    # 更新为新消息
                    link_to_id[url] = msg.id
                    preserved_messages.add(msg.id)
                else:
                    # 如果链接不存在，记录链接和消息ID的映射
                    link_to_id[url] = msg.id
                    preserved_messages.add(msg.id)
        
        # 5. 执行删除操作
        if id_to_delete:
            deleted_count = len(id_to_delete)
            print(f"\n发现 {deleted_count} 条重复消息需要删除")
            
            # 记录要删除的消息详情
            for msg_id in id_to_delete:
                msg = session.query(Message).get(msg_id)
                if msg:
                    print(f"将删除消息 ID: {msg_id}")
                    print(f"时间: {msg.timestamp}")
                    print(f"标题: {msg.title}")
                    print(f"链接: {msg.links}")
                    print("---")
            
            session.execute(delete(Message).where(Message.id.in_(id_to_delete)))
            session.commit()
            
            # 6. 记录去重后的统计信息
            total_after = session.query(Message).count()
            print(f"\n去重后总消息数: {total_after}")
            print(f"已删除 {deleted_count} 条重复消息")
            
            # 7. 记录详细日志
            log_entry = {
                "timestamp": datetime.now(),
                "before_count": total_before,
                "after_count": total_after,
                "deleted_count": deleted_count,
                "operation": "dedup"
            }
            
            # 保存到日志文件
            with open("data/dedup.log", "a") as f:
                f.write(json.dumps(log_entry) + "\n")
        else:
            print("\n没有需要删除的重复消息")

def print_help():
    print("""用法:
  python manage.py --list-channels
  python manage.py --add-channel 频道名
  python manage.py --del-channel 频道名
  python manage.py --edit-channel 旧频道名 新频道名
  python manage.py --fix-tags
  python manage.py --dedup-links
""")

if __name__ == "__main__":
    if "--list-channels" in sys.argv:
        list_channels()
    elif "--add-channel" in sys.argv:
        idx = sys.argv.index("--add-channel")
        if len(sys.argv) > idx + 1:
            add_channel(sys.argv[idx + 1])
        else:
            print("请提供要添加的频道名")
    elif "--del-channel" in sys.argv:
        idx = sys.argv.index("--del-channel")
        if len(sys.argv) > idx + 1:
            del_channel(sys.argv[idx + 1])
        else:
            print("请提供要删除的频道名")
    elif "--edit-channel" in sys.argv:
        idx = sys.argv.index("--edit-channel")
        if len(sys.argv) > idx + 2:
            edit_channel(sys.argv[idx + 1], sys.argv[idx + 2])
        else:
            print("请提供旧频道名和新频道名")
    elif "--fix-tags" in sys.argv:
        fix_tags()
    elif "--dedup-links" in sys.argv:
        dedup_links()
    else:
        print_help() 
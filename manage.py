import sys
from sqlalchemy.orm import Session
from models import Channel, Message, engine
from sqlalchemy import update, delete
import ast
from datetime import datetime, timedelta

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
    with Session(engine) as session:
        all_msgs = session.query(Message).order_by(Message.timestamp.desc()).all()
        link_to_id = {}
        id_to_delete = set()
        for msg in all_msgs:
            if not msg.links:
                continue
            for url in msg.links.values():
                if url in link_to_id:
                    id_to_delete.add(msg.id)
                else:
                    link_to_id[url] = msg.id
        if id_to_delete:
            session.execute(delete(Message).where(Message.id.in_(id_to_delete)))
            session.commit()
            print(f"已删除重复网盘链接的旧消息条目: {len(id_to_delete)}")
        else:
            print("没有需要删除的重复网盘链接消息。")

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
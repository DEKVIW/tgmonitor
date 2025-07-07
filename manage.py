import sys
from sqlalchemy.orm import Session
from models import Channel, Message, engine, DedupStats
from sqlalchemy import update, delete
import ast
from datetime import datetime, timedelta
import json
from collections import defaultdict
from sqlalchemy import text

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

def print_help():
    print("""用法:
  python manage.py --list-channels
  python manage.py --add-channel 频道名
  python manage.py --del-channel 频道名
  python manage.py --edit-channel 旧频道名 新频道名
  python manage.py --fix-tags
  python manage.py --dedup-links-fast [batch_size]
  python manage.py --dedup-links
""")

def extract_urls(links):
    urls = []
    if isinstance(links, str):
        # 兼容老数据
        urls.append(links)
    elif isinstance(links, dict):
        for v in links.values():
            urls.extend(extract_urls(v))
    elif isinstance(links, list):
        for item in links:
            if isinstance(item, dict) and 'url' in item:
                urls.append(item['url'])
            else:
                urls.extend(extract_urls(item))
    return urls

if __name__ == "__main__":
    if "--list-channels" in sys.argv:
        list_channels()
    elif "--add-channel" in sys.argv:
        idx = sys.argv.index("--add-channel")
        if len(sys.argv) > idx + 1:
            for name in sys.argv[idx + 1:]:
                add_channel(name.strip())
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
        # 检查并修复tags字段脏数据
        with Session(engine) as session:
            msgs = session.query(Message).all()
            fixed = 0
            for msg in msgs:
                # 如果tags不是list类型，尝试修正
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
    elif "--dedup-links-fast" in sys.argv:
        # 分批流式去重，降低内存占用
        batch_size = 5000
        idx = sys.argv.index("--dedup-links-fast")
        if len(sys.argv) > idx + 1 and sys.argv[idx+1].isdigit():
            batch_size = int(sys.argv[idx+1])
        from sqlalchemy import select, text
        from sqlalchemy.orm import sessionmaker
        SessionLocal = sessionmaker(bind=engine)
        link_to_id = {}
        id_to_delete = set()
        with SessionLocal() as session:
            query = session.query(Message).order_by(Message.timestamp.desc())
            for msg in query.yield_per(batch_size):
                links = msg.links
                if isinstance(links, str):
                    try:
                        links = json.loads(links)
                    except Exception:
                        continue
                if not links:
                    continue
                urls = extract_urls(links)
                for url in urls:
                    if not isinstance(url, str):
                        continue
                    url = url.strip().lower()
                    if url in link_to_id:
                        old_id = link_to_id[url]
                        if msg.timestamp < session.get(Message, old_id).timestamp:
                            # Older message, mark for deletion
                            id_to_delete.add(msg.id)
                        else:
                            id_to_delete.add(old_id)
                            link_to_id[url] = msg.id
                    else:
                        link_to_id[url] = msg.id
            if id_to_delete:
                session.execute(delete(Message).where(Message.id.in_(id_to_delete)))
                # 记录去重统计
                session.add(DedupStats(
                    run_time=datetime.now(),
                    inserted=len(link_to_id),
                    deleted=len(id_to_delete)
                ))
                session.commit()
                print(f"已删除重复链接消息条数: {len(id_to_delete)} 并写入统计")
                # 自动清理10小时前的去重统计数据
                session.execute(text("DELETE FROM dedup_stats WHERE run_time < NOW() - INTERVAL '10 hours'"))
                session.commit()
                print("已自动清理10小时之前的去重统计数据")
            else:
                print("没有重复链接需要删除。")

    elif "--dedup-links" in sys.argv:
        # 升级去重逻辑：相同链接且时间间隔5分钟内，优先保留网盘链接多的，否则保留最新的
        with Session(engine) as session:
            all_msgs = session.query(Message).order_by(Message.timestamp.desc()).all()
            link_to_id = {}  # {url: 最新消息id}
            id_to_delete = set()
            id_to_msg = {}  # {id: msg对象}
            for msg in all_msgs:
                links = msg.links
                if isinstance(links, str):
                    try:
                        links = json.loads(links)
                    except Exception as e:
                        print(f"ID={msg.id} links解析失败: {e}")
                        continue
                if not links:
                    continue
                for url in extract_urls(links):
                    if not isinstance(url, str):
                        continue
                    url = url.strip().lower()
                    if url in link_to_id:
                        old_id = link_to_id[url]
                        old_msg = id_to_msg[old_id]
                        time_diff = abs((msg.timestamp - old_msg.timestamp).total_seconds())
                        if time_diff < 300: # 修改为5分钟 (300秒)
                            # 5分钟内，优先保留links多的
                            if len(extract_urls(links)) > len(extract_urls(old_msg.links)):
                                id_to_delete.add(old_id)
                                link_to_id[url] = msg.id
                                id_to_msg[msg.id] = msg
                            else:
                                id_to_delete.add(msg.id)
                        else:
                            # 超过5分钟，保留最新的
                            id_to_delete.add(msg.id)
                    else:
                        link_to_id[url] = msg.id
                        id_to_msg[msg.id] = msg
            if id_to_delete:
                session.execute(delete(Message).where(Message.id.in_(id_to_delete)))
                session.commit()
                print(f"已删除重复网盘链接的旧消息条目: {len(id_to_delete)}")
                # 自动清理10小时前的去重统计数据
                session.execute(text("DELETE FROM dedup_stats WHERE run_time < NOW() - INTERVAL '10 hours'"))
                session.commit()
                print("已自动清理10小时之前的去重统计数据")
            else:
                print("没有需要删除的重复网盘链接消息。")
    else:
        print_help() 
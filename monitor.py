from telethon import TelegramClient, events
from sqlalchemy.orm import Session
from models import Message, engine, Channel, Credential
import datetime
import json
import re
import sys
from config import settings

def get_api_credentials():
    """获取 API 凭据，优先使用数据库中的凭据"""
    with Session(engine) as session:
        # 尝试从数据库获取凭据
        cred = session.query(Credential).first()
        if cred:
            return int(cred.api_id), cred.api_hash
    # 如果数据库中没有凭据，使用 .env 中的配置
    return settings.TELEGRAM_API_ID, settings.TELEGRAM_API_HASH

def get_channels():
    """获取频道列表，合并数据库和 .env 中的频道"""
    channels = set()
    
    # 从数据库获取频道
    with Session(engine) as session:
        db_channels = [c.username for c in session.query(Channel).all()]
        channels.update(db_channels)
    
    # 从 .env 获取默认频道
    if hasattr(settings, 'DEFAULT_CHANNELS'):
        env_channels = [c.strip() for c in settings.DEFAULT_CHANNELS.split(',') if c.strip()]
        channels.update(env_channels)
        
        # 将 .env 中的频道添加到数据库
        with Session(engine) as session:
            for username in env_channels:
                if username not in db_channels:
                    channel = Channel(username=username)
                    session.add(channel)
            session.commit()
    
    return list(channels)

# 获取 API 凭据
api_id, api_hash = get_api_credentials()

# session 文件名
client = TelegramClient('newquark_session', api_id, api_hash)

# 获取频道列表
channel_usernames = get_channels()

def parse_message(text):
    """解析消息内容，提取标题、描述、链接等信息（更健壮，支持一行多网盘名链接提取和全局标签提取）"""
    lines = text.split('\n')
    title = ''
    description = ''
    links = {}
    tags = []
    source = ''
    channel = ''
    group = ''
    bot = ''
    current_section = None
    desc_lines = []

    # 网盘关键字与显示名映射
    netdisk_map = [
        (['quark', '夸克'], '夸克网盘'),
        (['aliyundrive', 'aliyun', '阿里', 'alipan'], '阿里云盘'),
        (['baidu', 'pan.baidu'], '百度网盘'),
        (['115.com', '115网盘', '115pan'], '115网盘'),
        (['cloud.189', '天翼', '189.cn'], '天翼云盘'),
        (['123pan', '123.yun'], '123云盘'),
        (['ucdisk', 'uc网盘', 'ucloud', 'drive.uc.cn'], 'UC网盘'),
        (['xunlei', 'thunder', '迅雷'], '迅雷'),
    ]

    # 1. 标题提取：优先"名称："，否则第一行直接当title
    if lines and lines[0].strip():
        if lines[0].startswith('名称：'):
            title = lines[0].replace('名称：', '').strip()
        else:
            title = lines[0].strip()

    # 2. 遍历其余行，提取描述、链接、标签等
    for idx, line in enumerate(lines[1:] if title else lines):
        line = line.strip()
        if not line:
            continue
        # 兼容多种标签前缀
        if line.startswith('🏷 标签：') or line.startswith('标签：'):
            tags.extend([tag.strip('#') for tag in line.replace('🏷 标签：', '').replace('标签：', '').split() if tag.strip('#')])
            continue
        if line.startswith('描述：'):
            current_section = 'description'
            desc_lines.append(line.replace('描述：', '').strip())
        elif line.startswith('链接：'):
            current_section = 'links'
            url = line.replace('链接：', '').strip()
            if not url:
                continue  # 跳过空链接
            # 智能识别网盘名
            found = False
            for keys, name in netdisk_map:
                if any(k in url.lower() for k in keys):
                    links[name] = url
                    found = True
                    break
            if not found:
                links['其他'] = url
        elif line.startswith('🎉 来自：'):
            source = line.replace('🎉 来自：', '').strip()
        elif line.startswith('📢 频道：'):
            channel = line.replace('📢 频道：', '').strip()
        elif line.startswith('👥 群组：'):
            group = line.replace('👥 群组：', '').strip()
        elif line.startswith('🤖 投稿：'):
            bot = line.replace('🤖 投稿：', '').strip()
        elif current_section == 'description':
            desc_lines.append(line)
        else:
            desc_lines.append(line)

    # 3. 全局正则提取所有"网盘名：链接"对，并从描述中移除
    desc_text = '\n'.join(desc_lines)
    # 支持"网盘名：链接"对，允许多个，支持中文冒号和英文冒号
    pattern = re.compile(r'([\u4e00-\u9fa5A-Za-z0-9#]+)[：:](https?://[^\s]+)')
    matches = pattern.findall(desc_text)
    for key, url in matches:
        # 智能识别网盘名
        found = False
        for keys, name in netdisk_map:
            if any(k in url.lower() or k in key for k in keys):
                links[name] = url
                found = True
                break
        if not found:
            links[key.strip()] = url
    # 从描述中移除所有"网盘名：链接"对
    desc_text = pattern.sub('', desc_text)
    # 4. 额外全局提取裸链接（http/https），也归类到links
    url_pattern = re.compile(r'(https?://[^\s]+)')
    for url in url_pattern.findall(desc_text):
        found = False
        for keys, name in netdisk_map:
            if any(k in url.lower() for k in keys):
                links[name] = url
                found = True
                break
        if not found:
            links['其他'] = url
    # 从描述中移除裸链接
    desc_text = url_pattern.sub('', desc_text)
    # 5. 全局正则提取所有#标签，并从描述中移除
    tag_pattern = re.compile(r'#([\u4e00-\u9fa5A-Za-z0-9_]+)')
    found_tags = tag_pattern.findall(desc_text)
    if found_tags:
        tags.extend(found_tags)
        desc_text = tag_pattern.sub('', desc_text)
    # 去重
    tags = list(set(tags))
    # 移除所有网盘名关键词
    netdisk_names = ['夸克', '迅雷', '百度', 'UC', '阿里', '天翼', '115', '123云盘']
    netdisk_name_pattern = re.compile(r'(' + '|'.join(netdisk_names) + r')')
    desc_text = netdisk_name_pattern.sub('', desc_text)
    # 6. 最终description，去除无意义符号行
    desc_lines_final = [line for line in desc_text.strip().split('\n') if line.strip() and not re.fullmatch(r'[.。·、,，-]+', line.strip())]
    description = '\n'.join(desc_lines_final)

    return {
        'title': title,
        'description': description,
        'links': links,
        'tags': tags,
        'source': source,
        'channel': channel,
        'group_name': group,
        'bot': bot
    }

@client.on(events.NewMessage(chats=channel_usernames))
async def handler(event):
    message = event.raw_text
    timestamp = datetime.datetime.now()
    
    # 解析消息
    parsed_data = parse_message(message)
    
    # 只保存包含网盘链接的消息
    if parsed_data['links']:
        with Session(engine) as session:
            new_message = Message(
                timestamp=timestamp,
                **parsed_data
            )
            session.add(new_message)
            session.commit()
        print(f"[{timestamp}] 新消息已保存到数据库")
    else:
        print(f"[{timestamp}] 过滤掉无网盘链接的消息")

print(f"✅ 正在监听 Telegram 频道：{channel_usernames} ...")

if __name__ == "__main__":
    client.start()
    client.run_until_disconnected() 
from telethon import TelegramClient, events
from sqlalchemy.orm import Session
from app.models.models import Message, engine, Channel, Credential
import datetime
import json
import re
import sys
from app.models.config import settings
import asyncio
from telethon.tl.types import MessageEntityTextUrl, MessageEntityUrl, KeyboardButtonUrl
from urllib.parse import unquote, urlparse
from urlextract import URLExtract  # 新增
from app.models.db import async_session

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

# 新增：全面提取所有链接的函数
def extract_all_urls(text, msg_obj=None):
    extractor = URLExtract()
    all_urls = set()
    if msg_obj is not None:
        # 实体链接
        for ent, text_part in msg_obj.get_entities_text():
            if isinstance(ent, MessageEntityTextUrl):
                decoded_url = unquote(ent.url)
                all_urls.add(decoded_url)
            elif isinstance(ent, MessageEntityUrl):
                decoded_url = unquote(text_part)
                all_urls.add(decoded_url)
        # 按钮链接
        if getattr(msg_obj, 'reply_markup', None):
            for row in msg_obj.reply_markup.rows:
                for button in row.buttons:
                    if isinstance(button, KeyboardButtonUrl):
                        decoded_url = unquote(button.url)
                        all_urls.add(decoded_url)
        # 网页预览链接
        if getattr(msg_obj, 'media', None) and hasattr(msg_obj.media, 'webpage'):
            webpage = msg_obj.media.webpage
            if hasattr(webpage, 'url') and webpage.url:
                decoded_url = unquote(webpage.url)
                all_urls.add(decoded_url)
    # 裸链兜底
    for line in text.split('\n'):
        for url in extractor.find_urls(line):
            decoded_url = unquote(url)
            all_urls.add(decoded_url)
    return all_urls

def parse_message(text, msg_obj=None):
    original_lines = text.split('\n')
    lines_to_process = []
    title = ''
    description = ''
    tags = []
    source = ''
    channel = ''
    group = ''
    bot = ''
    desc_lines_buffer = []
    last_label = None
    label_pattern = re.compile(r'^(主链|备用|普码|高码|HDR|杜比|IQ|[\u4e00-\u9fa5A-Za-z0-9]+码)$')
    tag_pattern = re.compile(r'#([\u4e00-\u9fa5A-Za-z0-9_]+)')
    netdisk_map = [
        (['quark', '夸克'], '夸克网盘'),
        (['aliyundrive', 'aliyun', '阿里', 'alipan'], '阿里云盘'),
        (['baidu', 'pan.baidu'], '百度网盘'),
        (['115.com', '115网盘', '115pan', '115', '115cdn.com'], '115网盘'),
        (['cloud.189', '天翼', '189.cn'], '天翼云盘'),
        (['123pan.com', 'www.123pan.com', '123912.com', 'www.123912.com', '123'], '123云盘'),
        (['ucdisk', 'uc网盘', 'ucloud', 'drive.uc.cn'], 'UC网盘'),
        (['xunlei', 'thunder', '迅雷'], '迅雷'),
    ]
    # 1. 全量提取所有链接
    all_urls = extract_all_urls(text, msg_obj)
    # 2. 分类为网盘链接
    links = {}
    valid_labels = {
        '普码', '高码', '主链', '备用', '4K', 'HDR', 'SDR', '1080P', '4K 120FPS', '4K HDR', '4K HQ', '4K EDR', '4K DV', '4K SDR', '4K 60FPS', '4K 120FPS', '4K HQ 高码率', '前 42 集', 'ATVP', '1080P 5.96G', '4K HDR 60FPS', '4K HQ', '4K DV', '4K EDR', '4K 5.96G', '4K 14.9GB', '4K 8.5GB', '4K 24.1GB', '4K HDR&DV', '4K HDR', '4K 60FPS', '4K 120FPS', '4K HQ 高码率', '4K HQ', '4K DV', '4K EDR', '4K 5.96G', '4K 14.9GB', '4K 8.5GB', '4K 24.1GB', 'ATVP', '前 42 集', '主链', '备用',
        '大包', '大包2', '大包3', '大包4', '大包5',
        '1号文件夹', '2号文件夹', '3号文件夹', '4号文件夹', '5号文件夹',
        '备用链', '备用链接', '普码版', '高码版', '标准版', '高清版',
        '4K版', '1080P版', 'HDR版', '杜比版', '完整版', '精简版',
        '导演版', '加长版', '国语版', '粤语版', '英语版', '多语版',
        '无删减', '剧场版', '特别版', '典藏版', '豪华版'
    }
    for url in all_urls:
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        for keys, name in netdisk_map:
            if any(k in netloc for k in keys):
                # 标签提取逻辑
                label = None
                for i, line in enumerate(original_lines):
                    if url in line:
                        # 先尝试匹配有冒号的格式
                        label_match = re.match(r'^([\u4e00-\u9fa5A-Za-z0-9]+)[：:]', line.strip())
                        if label_match:
                            extracted_label = label_match.group(1)
                            # 优先最长匹配
                            matched_label = None
                            for valid_label in valid_labels:
                                if valid_label in extracted_label:
                                    if matched_label is None or len(valid_label) > len(matched_label):
                                        matched_label = valid_label
                            if matched_label:
                                label = matched_label
                                break
                        # 如果没有冒号，尝试匹配链接前的标签
                        else:
                            url_index = line.find(url)
                            if url_index > 0:
                                before_url = line[:url_index].strip()
                                for valid_label in valid_labels:
                                    if before_url.endswith(valid_label):
                                        label = valid_label
                                        break
                                if label:
                                    break
                        # 新增：上一行短标签智能识别
                        if not label and i > 0:
                            prev_line = original_lines[i-1].strip()
                            if len(prev_line) < 10:
                                for valid_label in valid_labels:
                                    if valid_label in prev_line:
                                        label = valid_label
                                        break
                        # 只要找到就break
                        if label:
                            break
                if name not in links:
                    links[name] = []
                if not any(item['url'] == url for item in links[name]):
                    links[name].append({'label': label, 'url': url})
                break
    # 其余业务逻辑保持不变（标题、描述、标签等）
    # 阶段1: 精确识别标题，并准备待处理行列表
    title_found_in_pass = False
    for i, line in enumerate(original_lines):
        stripped_line = line.strip()
        if not stripped_line:
            continue
        if stripped_line.startswith('名称：'):
            title = stripped_line.replace('名称：', '').strip()
            title_found_in_pass = True
            lines_to_process.extend(original_lines[:i])
            lines_to_process.extend(original_lines[i+1:])
            break
    if not title_found_in_pass and original_lines:
        first_meaningful_line_idx = -1
        for i, line in enumerate(original_lines):
            if line.strip():
                first_meaningful_line_idx = i
                break
        if first_meaningful_line_idx != -1:
            title = original_lines[first_meaningful_line_idx].strip()
            lines_to_process.extend(original_lines[:first_meaningful_line_idx])
            lines_to_process.extend(original_lines[first_meaningful_line_idx+1:])
        else:
            return {'title': '', 'description': '', 'links': {}, 'tags': [], 'source': '', 'channel': '', 'group_name': '', 'bot': ''}
    # 统一定义需要过滤的“杂项行”关键词及其对应字段
    skip_keywords = [
        ('🎉 来自', 'source'),
        ('📢 频道', 'channel'),
        ('👥 群组', 'group'),
        ('🤖 投稿', 'bot'),
        ('🔍 投稿/搜索', None),
        ('⚠️', None)
    ]
    skip_pattern = re.compile(r'^(%s)(：|:)?' % '|'.join(map(lambda x: re.escape(x[0]), skip_keywords)))
    keyword_field_map = {k: v for k, v in skip_keywords if v}
    extractor_tmp = URLExtract()
    for raw_line in lines_to_process:
        line = raw_line.strip()
        if not line:
            continue
        # 新增：只要行里含有任何形式的链接（包含不带 http/https 前缀的裸域名），整行跳过
        if re.search(r'https?://', line) or extractor_tmp.has_urls(line):
            continue
        # 新增：过滤包含 @xxx 的行
        if re.search(r'@[A-Za-z0-9_]+', line):
            continue
        cleaned_line_for_check = re.sub(r'^(?:\* |\- |\+ |> |>> |• |➤ |▪ |√ )+', '', line).strip()
        line_fully_handled = False
        m = skip_pattern.match(cleaned_line_for_check)
        if m:
            keyword = m.group(1)
            field = keyword_field_map.get(keyword)
            if field:
                value = cleaned_line_for_check.replace(keyword, '').replace('：', '').replace(':', '').strip()
                locals()[field] = value
            continue
        # 仅行首大小信息识别（允许emoji、空格、标点）
        if re.match(r'^[^\u4e00-\u9fa5A-Za-z0-9]*大小', cleaned_line_for_check):
            parts = re.split(r'大小[:：\s]*', cleaned_line_for_check, maxsplit=1)
            size_info = parts[1].strip() if len(parts) > 1 else ""
            if re.search(r'(\d+\s*(GB|MB|TB|KB|G|M|T|K|B|字节|左右|约|每集|单集))', size_info, re.IGNORECASE):
                desc_lines_buffer.append(cleaned_line_for_check)
            continue
        elif cleaned_line_for_check.startswith('链接：'):
            continue
        elif cleaned_line_for_check.startswith('描述区域'):
            continue
        elif label_pattern.match(cleaned_line_for_check):
            last_label = cleaned_line_for_check
            continue
        if line_fully_handled:
            continue
        cleaned_line = cleaned_line_for_check
        cleaned_line = re.sub(r'\bvia\s*\S+', '', cleaned_line, flags=re.IGNORECASE).strip()
        cleaned_line = re.sub(r'\bvia\s*$', '', cleaned_line, flags=re.IGNORECASE).strip() 
        found_tags_in_line = tag_pattern.findall(cleaned_line)
        if found_tags_in_line:
            tags.extend(found_tags_in_line)
            cleaned_line = tag_pattern.sub('', cleaned_line).strip()
        cleaned_line = re.sub(r'^.*(标签|投稿人|频道|搜索|机场)\s*[：:].*$', '', cleaned_line, flags=re.IGNORECASE).strip()
        if cleaned_line_for_check.startswith('分享：') or cleaned_line_for_check.startswith('网址：') \
            or cleaned_line_for_check.startswith('🌍') or cleaned_line_for_check.startswith('🔥'):
            continue
        cleaned_line = re.sub(r'[🔗\s]*链接[：:：]?\s*[^\s]+', '', cleaned_line).strip()
        if cleaned_line:
            filter_patterns = [
                r'.*🌍.*群主自用机场.*守候网络.*9折活动.*',
                r'.*🔥.*云盘播放神器.*VidHub.*',
                r'.*群主自用机场.*守候网络.*9折活动.*',
                r'.*云盘播放神器.*VidHub.*'
            ]
            should_filter = False
            for pattern in filter_patterns:
                if re.search(pattern, cleaned_line, re.IGNORECASE):
                    should_filter = True
                    break
            if not should_filter:
                desc_lines_buffer.append(cleaned_line)
    tags = list(set(tags))
    description = '\n'.join(desc_lines_buffer)
    # --- 新增：描述区净化，去除网盘名 ---
    netdisk_names = ['夸克', '迅雷', '百度', 'UC', '阿里', '天翼', '115', '123云盘']
    netdisk_name_pattern = re.compile(r'(' + '|'.join(netdisk_names) + r')')
    description = netdisk_name_pattern.sub('', description)
    # 链接相关的replace已不需要，直接删除
    description = re.sub(r'：\s*$', '', description, flags=re.MULTILINE)
    description = re.sub(r'：\s*\n', '\n', description, flags=re.MULTILINE)
    desc_lines_final = [line for line in description.strip().split('\n') if line.strip() and not re.fullmatch(r'[.。·、,，-]+', line.strip())]
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
    try:
        message = event.raw_text
        # 使用Telegram消息的原始时间，正确处理时区
        telegram_time = event.date
        monitor_time = datetime.datetime.now()
        
        # 正确处理时区转换
        if telegram_time.tzinfo is not None:
            # 如果telegram_time有时区信息，转换为本地时间
            # 假设Telegram时间是UTC，转换为北京时间（UTC+8）
            telegram_local_time = telegram_time.replace(tzinfo=None) + datetime.timedelta(hours=8)
        else:
            # 如果没有时区信息，直接使用
            telegram_local_time = telegram_time
        
        # 计算监控延迟
        delay_seconds = (monitor_time - telegram_local_time).total_seconds()
        
        print(f"[{monitor_time}] 收到新消息，开始解析... (延迟: {delay_seconds:.1f}秒)")
        
        # 解析消息
        try:
            parsed_data = parse_message(message, event.message) # Pass event.message to parse_message
        except Exception as parse_error:
            print(f"[{monitor_time}] 消息解析失败: {str(parse_error)}")
            print(f"[{monitor_time}] 原始消息: {message[:200]}...")  # 记录前200字符
            return
        
        # 只保存包含网盘链接的消息
        if parsed_data['links']:
            netdisk_types = list(parsed_data['links'].keys())
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    async with async_session() as session:
                        new_message = Message(
                            timestamp=telegram_local_time,  # 使用转换后的本地时间
                            **parsed_data,
                            netdisk_types=netdisk_types
                        )
                        session.add(new_message)
                        await session.commit()
                    print(f"[{monitor_time}] 新消息已保存到数据库 (尝试 {attempt + 1}/{max_retries}, 延迟: {delay_seconds:.1f}秒)")
                    break
                except Exception as db_error:
                    print(f"[{monitor_time}] 数据库写入失败 (尝试 {attempt + 1}/{max_retries}): {str(db_error)}")
                    if attempt == max_retries - 1:
                        print(f"[{monitor_time}] 数据库写入最终失败，消息丢失")
                        # 可以考虑写入本地文件作为备份
                        try:
                            with open('data/failed_messages.log', 'a', encoding='utf-8') as f:
                                f.write(f"[{monitor_time}] 失败消息: {message}\n")
                        except:
                            pass
                    else:
                        await asyncio.sleep(1)  # 用异步sleep替换阻塞sleep
        else:
            print(f"[{monitor_time}] 过滤掉无网盘链接的消息")
            
    except Exception as e:
        print(f"[{datetime.datetime.now()}] 消息处理发生未知错误: {str(e)}")
        # 记录原始消息到错误日志
        try:
            with open('data/error_messages.log', 'a', encoding='utf-8') as f:
                f.write(f"[{datetime.datetime.now()}] 错误: {str(e)}, 消息: {event.raw_text[:200]}...\n")
        except:
            pass

print(f"✅ 正在监听 Telegram 频道：{channel_usernames} ...")

# 添加连接状态监控
@client.on(events.Raw)
async def connection_handler(event):
    """监控连接状态"""
    if hasattr(event, 'connected'):
        if event.connected:
            print(f"[{datetime.datetime.now()}] ✅ Telegram连接已建立")
        else:
            print(f"[{datetime.datetime.now()}] ❌ Telegram连接已断开")

if __name__ == "__main__":
    try:
        # 使用已存在的 session 文件启动
        client.start()
        print(f"[{datetime.datetime.now()}] ✅ 监控服务启动成功")
        client.run_until_disconnected()
    except Exception as e:
        print(f"[{datetime.datetime.now()}] ❌ 启动失败: {str(e)}")
        print("请先手动运行一次程序进行登录：python monitor.py")
        sys.exit(1) 
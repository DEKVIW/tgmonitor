from telethon import TelegramClient, events
from sqlalchemy.orm import Session
from models import Message, engine, Channel, Credential
import datetime
import json
import re
import sys
from config import settings
import asyncio

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
    original_lines = text.split('\n')
    lines_to_process = []
    title = ''
    
    # 字段初始化
    description = ''
    links = {}
    tags = []
    source = ''
    channel = ''
    group = ''
    bot = ''
    
    desc_lines_buffer = [] 
    last_label = None

    # 区分词列表
    label_pattern = re.compile(r'^(主链|备用|普码|高码|HDR|杜比|IQ|[\u4e00-\u9fa5A-Za-z0-9]+码)$')

    # 标签正则表达式
    tag_pattern = re.compile(r'#([\u4e00-\u9fa5A-Za-z0-9_]+)')

    # 网盘关键字与显示名映射
    netdisk_map = [
        (['quark', '夸克'], '夸克网盘'),
        (['aliyundrive', 'aliyun', '阿里', 'alipan'], '阿里云盘'),
        (['baidu', 'pan.baidu'], '百度网盘'),
        (['115.com', '115网盘', '115pan', '115'], '115网盘'),
        (['cloud.189', '天翼', '189.cn'], '天翼云盘'),
        (['123pan.com', 'www.123pan.com', '123912.com', 'www.123912.com', '123'], '123云盘'),
        (['ucdisk', 'uc网盘', 'ucloud', 'drive.uc.cn'], 'UC网盘'),
        (['xunlei', 'thunder', '迅雷'], '迅雷'),
    ]

    # --- 阶段1: 精确识别标题，并准备待处理行列表 ---
    title_found_in_pass = False
    for i, line in enumerate(original_lines):
        stripped_line = line.strip()
        if not stripped_line:
            continue

        if stripped_line.startswith('名称：'):
            title = stripped_line.replace('名称：', '').strip()
            title_found_in_pass = True
            # 将标题前的内容（如果有的话）添加到待处理列表，并将其从描述中剥离
            lines_to_process.extend(original_lines[:i]) # 标题前的内容
            lines_to_process.extend(original_lines[i+1:]) # 标题后的内容
            break

    # 如果没有找到明确的"名称："标题行，则将第一行作为标题，其余作为待处理内容
    if not title_found_in_pass and original_lines:
        # 找出第一条非空行作为标题
        first_meaningful_line_idx = -1
        for i, line in enumerate(original_lines):
            if line.strip():
                first_meaningful_line_idx = i
                break
        
        if first_meaningful_line_idx != -1:
            title = original_lines[first_meaningful_line_idx].strip()
            # 将标题行从待处理列表中移除，后续会作为description进行处理
            lines_to_process.extend(original_lines[:first_meaningful_line_idx])
            lines_to_process.extend(original_lines[first_meaningful_line_idx+1:])
        else:
            # 消息完全为空的情况
            return {'title': '', 'description': '', 'links': {}, 'tags': [], 'source': '', 'channel': '', 'group_name': '', 'bot': ''}

    # --- 阶段2: 遍历待处理行，提取元数据并构建纯净描述 ---
    for raw_line in lines_to_process:
        line = raw_line.strip()
        if not line:
            continue

        # 移除常见的列表或引用符号，以便正确识别标签行
        cleaned_line_for_check = re.sub(r'^(?:\* |\- |\+ |> |>> |• |➤ |▪ |√ )+', '', line).strip()

        # 标记是否当前行已经被完全处理（作为元数据或链接），不需要进入 desc_lines_buffer
        line_fully_handled = False

        # 1. 处理明确的元数据行 (如果整行都是元数据)
        # 标签行 - 使用正则表达式匹配任何包含"标签"的行
        if re.search(r'^.*标签\s*[：:]', cleaned_line_for_check):
            # 提取标签内容，移除emoji和"标签："前缀
            tag_content = re.sub(r'^.*标签\s*[：:]', '', cleaned_line_for_check).strip()
            tags.extend([tag.strip('#') for tag in tag_content.split() if tag.strip('#')])
            continue

        # 大小信息行 (根据意义决定是否放入 desc_lines_buffer)
        elif cleaned_line_for_check.startswith('📁 大小：') or cleaned_line_for_check.startswith('大小：'):
            # 统一处理大小信息，无论是否有emoji
            size_info = cleaned_line_for_check.replace('📁 大小：', '').replace('大小：', '').strip()
            if re.search(r'(\d+\s*(GB|MB|TB|KB|G|M|T|K|B|字节|左右|约|每集|单集))', size_info, re.IGNORECASE):
                desc_lines_buffer.append(cleaned_line_for_check) # 有意义的才加入描述
            continue

        # 链接行 (以"链接："开头)
        elif cleaned_line_for_check.startswith('链接：'):
            url = cleaned_line_for_check.replace('链接：', '').strip()
            if url:
                found = False
                for keys, name in netdisk_map:
                    if any(k in url.lower() for k in keys):
                        links[f"{name}({last_label})" if last_label else name] = url
                        last_label = None
                        found = True
                        break
                if not found:
                    links['其他'] = url
            continue

        # 其他明确的元数据行
        elif cleaned_line_for_check.startswith('🎉 来自') or cleaned_line_for_check.startswith('🎉 来自：'):
            source = cleaned_line_for_check.replace('🎉 来自：', '').replace('🎉 来自', '').strip()
            continue
        elif cleaned_line_for_check.startswith('📢 频道') or cleaned_line_for_check.startswith('📢 频道：'):
            channel = cleaned_line_for_check.replace('📢 频道：', '').replace('📢 频道', '').strip()
            continue
        elif cleaned_line_for_check.startswith('👥 群组') or cleaned_line_for_check.startswith('👥 群组：'):
            group = cleaned_line_for_check.replace('👥 群组：', '').replace('👥 群组', '').strip()
            continue
        elif cleaned_line_for_check.startswith('🤖 投稿') or cleaned_line_for_check.startswith('🤖 投稿：'):
            bot = cleaned_line_for_check.replace('🤖 投稿：', '').replace('🤖 投稿', '').strip()
            continue
        elif cleaned_line_for_check.startswith('🔍 投稿/搜索') or cleaned_line_for_check.startswith('🔍 投稿/搜索：'):
            continue # 直接跳过
        elif cleaned_line_for_check.startswith('⚠️'): # 版权信息
            continue # 直接跳过
        elif cleaned_line_for_check.startswith('描述区域'): # 明确的"描述区域"字样
            continue # 直接跳过
        elif label_pattern.match(cleaned_line_for_check): # 区分词（普码、高码、主链等）作为独立行
            last_label = cleaned_line_for_check
            continue # 跳过，只作标记

        # 如果当前行已经被明确处理为元数据，则跳过后续处理
        if line_fully_handled:
            continue

        # --- 处理行内可能包含的元数据和清理，然后将剩余内容添加到描述 ---
        cleaned_line = cleaned_line_for_check

        # 1. 移除行内嵌入的"via"信息 (精确匹配，避免误删)
        cleaned_line = re.sub(r'\bvia\s*\S+', '', cleaned_line, flags=re.IGNORECASE).strip()
        cleaned_line = re.sub(r'\bvia\s*$', '', cleaned_line, flags=re.IGNORECASE).strip() 

        # 2. 移除行内嵌入的标签 (无论在哪里，都移除)
        found_tags_in_line = tag_pattern.findall(cleaned_line)
        if found_tags_in_line:
            tags.extend(found_tags_in_line)
            cleaned_line = tag_pattern.sub('', cleaned_line).strip()

        # 3. 移除行内嵌入的裸链接 (提取链接到links，然后从文本移除)
        url_matches = re.finditer(r'(https?://[^\s]+)', cleaned_line)
        for url_match in url_matches:
            url = url_match.group(1)
            found = False
            for keys, name in netdisk_map:
                if any(k in url.lower() for k in keys):
                    links[f"{name}({last_label})" if last_label else name] = url
                    last_label = None
                    found = True
                    break
            if not found:
                links['其他'] = url
            cleaned_line = cleaned_line.replace(url, '').strip()

        # 4. 移除行内嵌入的无意义大小信息
        cleaned_line = re.sub(r'(?:📁\s*)?大小\s*[：:]\s*(?:N|X|无|未知)', '', cleaned_line, flags=re.IGNORECASE).strip()
        
        # 5. 移除包含"标签"、"投稿人"、"频道"、"搜索"、"机场"的行（无论emoji和冒号中英文）
        cleaned_line = re.sub(r'^.*(标签|投稿人|频道|搜索|机场)\s*[：:].*$', '', cleaned_line, flags=re.IGNORECASE).strip()

        # 最后，如果清理后的行还有内容，就认为是描述
        if cleaned_line:
            # 过滤掉包含指定广告内容的行
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

    # 整合最终的描述和标签
    description = '\n'.join(desc_lines_buffer)

    # 移除所有网盘名关键词 (从最终的 description 文本中移除网盘名本身，避免重复)
    netdisk_names = ['夸克', '迅雷', '百度', 'UC', '阿里', '天翼', '115', '123云盘']
    netdisk_name_pattern = re.compile(r'(' + '|'.join(netdisk_names) + r')')
    description = netdisk_name_pattern.sub('', description)
    
    # 移除网盘名称后的冒号
    description = re.sub(r'：\s*$', '', description, flags=re.MULTILINE)  # 移除行尾冒号
    description = re.sub(r'：\s*\n', '\n', description, flags=re.MULTILINE)  # 移除行中冒号
    
    # 最终description，去除无意义符号行
    desc_lines_final = [line for line in description.strip().split('\n') if line.strip() and not re.fullmatch(r'[.。·、,，-]+', line.strip())]
    description = '\n'.join(desc_lines_final)

    tags = list(set(tags)) # 确保最终去重

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
            parsed_data = parse_message(message)
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
                    with Session(engine) as session:
                        new_message = Message(
                            timestamp=telegram_local_time,  # 使用转换后的本地时间
                            **parsed_data,
                            netdisk_types=netdisk_types
                        )
                        session.add(new_message)
                        session.commit()
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
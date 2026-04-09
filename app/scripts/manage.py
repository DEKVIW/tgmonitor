import sys
from sqlalchemy.orm import Session
from app.models.models import Channel, Message, engine, LinkCheckStats, LinkCheckDetails, Credential
from sqlalchemy import update
import ast
from datetime import datetime, timedelta
from collections import defaultdict
from sqlalchemy import text
import asyncio
import time
import signal
import os
from telethon import TelegramClient
from app.models.config import settings
import re

# 新增：导入链接检测模块
try:
    from .link_validator import LinkValidator
    LINK_VALIDATOR_AVAILABLE = True
except ImportError:
    try:
        from link_validator import LinkValidator
        LINK_VALIDATOR_AVAILABLE = True
    except ImportError:
        LINK_VALIDATOR_AVAILABLE = False
        print("⚠️  警告: link_validator.py 未找到，链接检测功能不可用")

def ensure_session_file(session_name):
    """确保指定的 session 文件存在，如果不存在则自动复制"""
    import os
    
    # 显示调试信息
    current_dir = os.getcwd()
    print(f"🔍 调试信息:")
    print(f"   - 当前工作目录: {current_dir}")
    
    # 使用绝对路径
    main_session = os.path.join(current_dir, 'tg_monitor_session.session')
    target_session = os.path.join(current_dir, f'{session_name}.session')
    
    print(f"   - 主 session 文件: {main_session}")
    print(f"   - 目标 session 文件: {target_session}")
    
    # 检查目标 session 是否存在
    if os.path.exists(target_session):
        target_size = os.path.getsize(target_session)
        print(f"   - 目标 session 已存在: ✅ (大小: {target_size} 字节)")
        return True
    
    # 检查主 session 是否存在
    if not os.path.exists(main_session):
        print(f"   - 主 session 不存在: ❌")
        print(f"❌ 主 session 文件 {main_session} 不存在")
        print("💡 请先运行监控服务或手动登录 Telegram")
        return False
    
    # 获取主session文件信息
    main_size = os.path.getsize(main_session)
    print(f"   - 主 session 存在: ✅ (大小: {main_size} 字节)")
    
    # 检查磁盘空间
    import shutil
    disk_usage = shutil.disk_usage(current_dir)
    free_space = disk_usage.free
    print(f"   - 可用磁盘空间: {free_space} 字节")
    
    if free_space < main_size * 2:  # 需要至少2倍空间用于复制
        print(f"❌ 磁盘空间不足，需要至少 {main_size * 2} 字节")
        return False
    
    # 自动复制 session 文件
    try:
        print(f"   - 开始复制文件...")
        shutil.copy2(main_session, target_session)
        
        # 验证复制结果
        if os.path.exists(target_session):
            target_size = os.path.getsize(target_session)
            if target_size == main_size:
                print(f"✅ 已成功复制 session 文件: {target_session}")
                print(f"   - 复制后大小: {target_size} 字节")
                return True
            else:
                print(f"❌ 复制后文件大小不匹配: 期望 {main_size} 字节，实际 {target_size} 字节")
                # 删除错误的文件
                os.remove(target_session)
                return False
        else:
            print(f"❌ 复制后目标文件不存在")
            return False
            
    except Exception as e:
        print(f"❌ 复制 session 文件失败: {e}")
        return False

# 全局变量用于中断处理
current_check_session = None
interrupted = False

# 新增：安全检测配置
SAFETY_CONFIG = {
    'max_links_per_check': 1000,  # 单次检测最大链接数
    'max_concurrent_global': 10,  # 全局最大并发数
    'require_confirmation': True,  # 是否需要用户确认
    'show_safety_warnings': True,  # 是否显示安全警告
}

def show_safety_warnings(url_count, max_concurrent):
    """显示安全警告信息"""
    print("\n" + "="*60)
    print("🚨 链接检测安全警告")
    print("="*60)
    print(f"📊 检测规模:")
    print(f"   - 链接数量: {url_count}")
    print(f"   - 最大并发: {max_concurrent}")
    print(f"   - 预计耗时: {url_count * 2 / max_concurrent:.1f} - {url_count * 4 / max_concurrent:.1f} 分钟")
    
    print(f"\n⚠️  风险提示:")
    print(f"   - 高频率请求可能触发网盘反爬虫机制")
    print(f"   - 可能导致IP被临时限制访问")
    print(f"   - 建议在非高峰期进行大规模检测")
    
    print(f"\n🛡️  安全措施:")
    print(f"   - 已启用网盘特定的请求限制")
    print(f"   - 随机延迟避免被识别为机器人")
    print(f"   - 错误计数保护机制")
    print(f"   - 支持 Ctrl+C 安全中断")
    
    print(f"\n💡 建议:")
    print(f"   - 首次检测建议使用较小的并发数 (3-5)")
    print(f"   - 观察检测结果后再调整参数")
    print(f"   - 如遇到大量错误，请降低并发数或暂停检测")
    print("="*60)

def confirm_large_check(url_count, max_concurrent):
    """确认大规模检测"""
    if not SAFETY_CONFIG['require_confirmation']:
        return True
    
    if url_count > 100 or max_concurrent > 5:
        show_safety_warnings(url_count, max_concurrent)
        
        while True:
            response = input(f"\n❓ 确认开始检测 {url_count} 个链接 (并发 {max_concurrent})? (y/N): ").strip().lower()
            if response in ['y', 'yes']:
                return True
            elif response in ['n', 'no', '']:
                print("❌ 检测已取消")
                return False
            else:
                print("请输入 y 或 n")
    
    return True

def check_safety_limits(url_count, max_concurrent):
    """检查安全限制"""
    if url_count > SAFETY_CONFIG['max_links_per_check']:
        print(f"❌ 链接数量 ({url_count}) 超过安全限制 ({SAFETY_CONFIG['max_links_per_check']})")
        print(f"💡 建议分批检测或调整 SAFETY_CONFIG['max_links_per_check']")
        return False
    
    if max_concurrent > SAFETY_CONFIG['max_concurrent_global']:
        print(f"❌ 并发数 ({max_concurrent}) 超过安全限制 ({SAFETY_CONFIG['max_concurrent_global']})")
        print(f"💡 建议降低并发数或调整 SAFETY_CONFIG['max_concurrent_global']")
        return False
    
    return True

def signal_handler(signum, frame):
    """处理中断信号"""
    global interrupted
    print(f"\n⚠️  收到中断信号 ({signum})，正在安全退出...")
    interrupted = True
    
    if current_check_session:
        print("💾 正在保存已完成的检测结果...")
        try:
            current_check_session.commit()
            print("✅ 检测结果已保存")
        except Exception as e:
            print(f"❌ 保存失败: {e}")
    
    # 强制退出程序
    import os
    os._exit(0)

# 注册信号处理器
signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
signal.signal(signal.SIGTERM, signal_handler)  # 终止信号

async def list_channels_detailed():
    """显示当前监听频道列表，包含详细信息（异步版本）"""
    # 确保 session 文件存在
    if not ensure_session_file('tg_monitor_session_list'):
        print("显示简化版本...")
        list_channels_simple()
        return
    
    def get_api_credentials():
        with Session(engine) as session:
            cred = session.query(Credential).first()
            if cred:
                return int(cred.api_id), cred.api_hash
        return settings.TELEGRAM_API_ID, settings.TELEGRAM_API_HASH

    def get_channels():
        with Session(engine) as session:
            chans = session.query(Channel).all()
            return [chan.username for chan in chans]

    api_id, api_hash = get_api_credentials()
    channels = get_channels()
    
    if not channels:
        print("📭 当前没有监听任何频道")
        return
    
    # 分类频道
    standard_channels = []
    invite_channels = []
    
    for channel in channels:
        if channel.startswith('+'):
            invite_channels.append(channel)
        else:
            standard_channels.append(channel)
    
    print(f"📡 当前监听频道列表：")
    print(f"总数: {len(channels)} 个频道")
    print("=" * 50)
    
    # 创建Telegram客户端
    client = TelegramClient('tg_monitor_session_list', api_id, api_hash)
    
    try:
        await client.start()
        
        # 获取频道详细信息
        channel_info = {}
        print("🔍 正在获取频道详细信息...")
        
        for channel in channels:
            try:
                entity = await client.get_entity(f"https://t.me/{channel}")
                channel_info[channel] = {
                    'title': getattr(entity, 'title', '未知'),
                    'id': entity.id,
                    'username': getattr(entity, 'username', None)
                }
                print(f"  ✅ {channel} -> {getattr(entity, 'title', '未知')} (ID: {entity.id})")
            except Exception as e:
                channel_info[channel] = {
                    'title': '获取失败',
                    'id': '获取失败',
                    'username': None
                }
                print(f"  ❌ {channel} -> 获取失败: {str(e)}")
        
        print("\n" + "=" * 50)
        
        # 显示标准频道
        if standard_channels:
            print(f"📡 标准频道 ({len(standard_channels)}个):")
            print("序号  用户名               显示名称                   频道ID")
            print("----  -------------------  -------------------------  -----------")
            for i, channel in enumerate(standard_channels, 1):
                info = channel_info.get(channel, {})
                title = info.get('title', '未知')[:20]  # 限制标题长度
                channel_id = info.get('id', '未知')
                print(f"  {i:2d}  {channel:<18}  {title:<24}  {channel_id}")
        
        # 显示邀请链接哈希频道
        if invite_channels:
            print(f"\n🔗 邀请链接哈希频道 ({len(invite_channels)}个):")
            print("序号  邀请哈希              显示名称                   频道ID")
            print("----  -------------------  -------------------------  -----------")
            for i, channel in enumerate(invite_channels, 1):
                info = channel_info.get(channel, {})
                title = info.get('title', '未知')[:20]  # 限制标题长度
                channel_id = info.get('id', '未知')
                print(f"  {i:2d}  {channel:<18}  {title:<24}  {channel_id}")
        
        # 统计信息
        print(f"\n📊 统计信息:")
        print(f"  - 标准频道: {len(standard_channels)} 个 ({len(standard_channels)/len(channels)*100:.1f}%)")
        print(f"  - 邀请链接哈希: {len(invite_channels)} 个 ({len(invite_channels)/len(channels)*100:.1f}%)")
        print(f"  - 总频道数: {len(channels)} 个")
        
    except Exception as e:
        print(f"❌ 连接Telegram失败: {str(e)}")
        # 如果连接失败，显示简化版本
        list_channels_simple()
        
    finally:
        await client.disconnect()

def list_channels():
    """显示当前监听频道列表（简化版本）"""
    with Session(engine) as session:
        chans = session.query(Channel).all()
        
        if not chans:
            print("📭 当前没有监听任何频道")
            return
        
        # 分类频道
        standard_channels = []
        invite_channels = []
        
        for chan in chans:
            if chan.username.startswith('+'):
                invite_channels.append(chan)
            else:
                standard_channels.append(chan)
        
        print(f"📡 当前监听频道列表：")
        print(f"总数: {len(chans)} 个频道")
        print("=" * 50)
        
        # 显示标准频道
        if standard_channels:
            print(f"📡 标准频道 ({len(standard_channels)}个):")
            print("序号  用户名               显示名称                   频道ID")
            print("----  -------------------  -------------------------  -----------")
            for i, chan in enumerate(standard_channels, 1):
                print(f"  {i:2d}  {chan.username:<18}  {'待获取':<24}  {'待获取'}")
        
        # 显示邀请链接哈希频道
        if invite_channels:
            print(f"\n🔗 邀请链接哈希频道 ({len(invite_channels)}个):")
            print("序号  邀请哈希              显示名称                   频道ID")
            print("----  -------------------  -------------------------  -----------")
            for i, chan in enumerate(invite_channels, 1):
                print(f"  {i:2d}  {chan.username:<18}  {'待获取':<24}  {'待获取'}")
        
        # 统计信息
        print(f"\n📊 统计信息:")
        print(f"  - 标准频道: {len(standard_channels)} 个 ({len(standard_channels)/len(chans)*100:.1f}%)")
        print(f"  - 邀请链接哈希: {len(invite_channels)} 个 ({len(invite_channels)/len(chans)*100:.1f}%)")
        print(f"  - 总频道数: {len(chans)} 个")

def list_channels_simple():
    """显示当前监听频道列表（简化版本，无详细信息）"""
    with Session(engine) as session:
        chans = session.query(Channel).all()
        
        if not chans:
            print("📭 当前没有监听任何频道")
            return
        
        print("📡 当前频道列表：")
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
  python manage.py --check-links [hours] [max_concurrent]
  python manage.py --check-all-links [max_concurrent]
  python manage.py --check-period [period] [max_concurrent]
  python manage.py --link-stats
  python manage.py --show-invalid-links [check_time]
  python manage.py --show-interrupted
  python manage.py --clear-link-check-data
  python manage.py --clear-old-link-check-data [days]
  python manage.py --diagnose-channels
  python manage.py --test-monitor

📡 频道管理命令详细说明:
  --list-channels                             显示当前数据库中的所有频道列表
  --add-channel <频道名>                       添加新频道到监控列表
                                              示例: python manage.py --add-channel example_channel
  --del-channel <频道名>                       从监控列表中删除指定频道
                                              示例: python manage.py --del-channel example_channel
  --edit-channel <旧频道名> <新频道名>          修改频道用户名
                                              示例: python manage.py --edit-channel old_name new_name
  --diagnose-channels                         诊断所有频道的有效性
                                              - 检查频道是否存在且可访问
                                              - 显示频道详细信息 (ID、标题、参与者数量)
                                              - 识别无效频道并显示错误原因
                                              - 提供修复建议
  --test-monitor                              测试监控功能
                                              - 验证Telegram客户端连接
                                              - 测试事件处理器是否正常工作
                                              - 检查频道访问权限

🔗 链接检测命令说明:
  --check-links [hours] [max_concurrent]    检测指定时间范围内的链接 (默认24小时, 5并发)
  --check-all-links [max_concurrent]        检测所有历史链接 (默认5并发，需要确认)
  --check-period [period] [max_concurrent]  按时间段检测链接
  --link-stats                              显示链接检测统计信息
  --show-invalid-links [check_time]         显示失效链接详情 (可选指定检测时间)
  --show-interrupted                        显示中断的检测记录
  --clear-link-check-data                   清空所有链接检测数据
  --clear-old-link-check-data [days]        清空指定天数之前的检测数据 (默认30天)

📅 时间段检测格式:
  --check-period today                      检测今天
  --check-period yesterday                  检测昨天
  --check-period week                       检测最近7天
  --check-period month                      检测最近30天
  --check-period year                       检测最近365天
  --check-period 2024-01-15                检测指定日期
  --check-period 2024-01                   检测指定月份
  --check-period 2024                      检测指定年份
  --check-period 2024-01-15:2024-01-20     检测指定日期范围

🛡️ 安全机制:
  - 网盘特定限制: 不同网盘使用不同的并发数和延迟策略
  - 错误计数保护: 自动暂停错误过多的网盘检测
  - 随机延迟: 避免被识别为机器人
  - 用户确认: 大规模检测前需要用户确认
  - 安全中断: 支持 Ctrl+C 安全中断并保存结果

📊 网盘支持:
  - 百度网盘: 最大并发3, 延迟1-3秒
  - 夸克网盘: 最大并发5, 延迟0.5-2秒
  - 阿里云盘: 最大并发4, 延迟1-2.5秒
  - 115网盘: 最大并发2, 延迟2-4秒
  - 天翼云盘: 最大并发3, 延迟1-3秒
  - 123云盘: 最大并发3, 延迟1-2秒
  - UC网盘: 最大并发3, 延迟1-2秒
  - 迅雷网盘: 最大并发3, 延迟1-2秒

⚙️ 安全限制:
  - 单次检测最大链接数: 1000个
  - 全局最大并发数: 10个
  - 全量检测最大并发: 3个
  - 每个网盘最大错误数: 10个

🗂️ 数据管理:
  --clear-link-check-data                   清空所有检测数据 (需要确认)
  --clear-old-link-check-data 7             清空7天前的检测数据
  --clear-old-link-check-data 30            清空30天前的检测数据 (默认)

🔄 中断处理:
  - 检测过程中按 Ctrl+C 可以安全中断
  - 中断时会自动保存已完成的检测结果
  - 使用 --show-interrupted 查看中断记录
  - 可以重新运行检测命令完成剩余链接

💡 使用建议:
  - 首次使用建议从小规模开始 (如检测最近1小时)
  - 观察检测结果后再调整并发数
  - 如遇到大量错误，请降低并发数或暂停检测
  - 建议在非高峰期进行大规模检测
  - 定期清理旧的检测数据

📖 详细说明:
  更多详细信息请查看 README_LINK_CHECK.md 文件
""")

def is_invite_link_hash(channel_name):
    """判断是否为邀请链接哈希格式"""
    pattern = r'^\+[a-zA-Z0-9_-]{10,}$'
    return bool(re.match(pattern, channel_name))

async def diagnose_channels():
    """诊断每个频道是否可以正常访问"""
    
    # 确保 session 文件存在
    if not ensure_session_file('tg_monitor_session_diagnose'):
        print("❌ 无法进行频道诊断，缺少必要的 session 文件")
        return [], []
    
    def get_api_credentials():
        """获取 API 凭据"""
        with Session(engine) as session:
            cred = session.query(Credential).first()
            if cred:
                return int(cred.api_id), cred.api_hash
        return settings.TELEGRAM_API_ID, settings.TELEGRAM_API_HASH

    def get_channels():
        """获取频道列表"""
        channels = set()
        
        with Session(engine) as session:
            db_channels = [c.username for c in session.query(Channel).all()]
            channels.update(db_channels)
        
        if hasattr(settings, 'DEFAULT_CHANNELS'):
            env_channels = [c.strip() for c in settings.DEFAULT_CHANNELS.split(',') if c.strip()]
            channels.update(env_channels)
            
        return list(channels)
    
    # 获取凭据和频道列表
    api_id, api_hash = get_api_credentials()
    channel_usernames = get_channels()
    
    print(f"🔍 开始诊断 {len(channel_usernames)} 个频道...")
    print(f"频道列表: {channel_usernames}")
    print("-" * 50)
    
    # 创建客户端
    client = TelegramClient('tg_monitor_session_diagnose', api_id, api_hash)
    
    try:
        await client.start()
        print("✅ Telegram客户端连接成功")
        
        valid_channels = []
        invalid_channels = []
        
        # 统一检查所有频道（标准频道和邀请链接哈希）
        print(f"\n🔍 检查所有频道 ({len(channel_usernames)} 个):")
        for i, channel in enumerate(channel_usernames, 1):
            try:
                print(f"[{i}/{len(channel_usernames)}] 检查频道: {channel}")
                
                # 统一使用 get_entity 解析，无论是标准频道还是邀请链接哈希
                entity = await client.get_entity(f"https://t.me/{channel}")
                
                # 获取频道详细信息
                channel_info = await client.get_entity(entity)
                
                # 判断频道类型
                channel_type = 'invite_link' if is_invite_link_hash(channel) else 'standard'
                
                print(f"  ✅ 成功 - {channel_info.title}")
                print(f"     ID: {channel_info.id}")
                print(f"     类型: {channel_type}")
                print(f"     参与者数量: {getattr(channel_info, 'participants_count', '未知')}")
                
                valid_channels.append({
                    'username': channel,
                    'title': channel_info.title,
                    'id': channel_info.id,
                    'type': channel_type
                })
                
            except Exception as e:
                error_msg = str(e)
                print(f"  ❌ 失败 - {channel}")
                print(f"     错误: {error_msg}")
                
                invalid_channels.append({
                    'username': channel,
                    'error': error_msg,
                    'type': 'unknown'
                })
        
        print("\n" + "=" * 50)
        print("📊 诊断结果总结:")
        
        # 按类型分组显示有效频道
        standard_valid = [ch for ch in valid_channels if ch['type'] == 'standard']
        invite_valid = [ch for ch in valid_channels if ch['type'] == 'invite_link']
        
        print(f"✅ 有效频道 ({len(valid_channels)}个):")
        if standard_valid:
            print(f"  标准频道 ({len(standard_valid)}个):")
            for ch in standard_valid:
                print(f"    - {ch['username']} ({ch['title']}) - ID: {ch['id']}")
        
        if invite_valid:
            print(f"  邀请链接哈希频道 ({len(invite_valid)}个):")
            for ch in invite_valid:
                print(f"    - {ch['username']} ({ch['title']}) - ID: {ch['id']}")
            
        if invalid_channels:
            print(f"\n❌ 无效频道 ({len(invalid_channels)}个):")
            for ch in invalid_channels:
                print(f"   - {ch['username']}")
                print(f"     错误: {ch['error']}")
                
            print("\n🔧 建议修复方案:")
            print("1. 检查频道用户名或邀请链接是否正确")
            print("2. 确认你的账号是否有权限访问这些频道")
            print("3. 尝试手动加入这些频道")
            print("4. 使用 --del-channel 命令移除无效频道")
        
        # 返回结果
        return valid_channels, invalid_channels
        
    except Exception as e:
        print(f"❌ 客户端连接失败: {str(e)}")
        return [], []
        
    finally:
        await client.disconnect()

def clean_invalid_channels(invalid_channels):
    """从数据库中清理无效频道"""
    if not invalid_channels:
        print("✅ 没有需要清理的无效频道")
        return
        
    print(f"\n🧹 开始清理 {len(invalid_channels)} 个无效频道...")
    
    with Session(engine) as session:
        for ch in invalid_channels:
            try:
                channel_to_delete = session.query(Channel).filter(Channel.username == ch['username']).first()
                if channel_to_delete:
                    session.delete(channel_to_delete)
                    print(f"  🗑️  已从数据库删除: {ch['username']}")
                else:
                    print(f"  ⚠️  数据库中未找到: {ch['username']}")
            except Exception as e:
                print(f"  ❌ 删除失败 {ch['username']}: {str(e)}")
        
        try:
            session.commit()
            print("✅ 数据库清理完成")
        except Exception as e:
            print(f"❌ 数据库提交失败: {str(e)}")
            session.rollback()

async def test_event_handler():
    """测试修复后的事件处理器"""
    # 确保 session 文件存在
    if not ensure_session_file('tg_monitor_session_test'):
        print("❌ 无法进行测试，缺少必要的 session 文件")
        return
    
    def get_api_credentials():
        with Session(engine) as session:
            cred = session.query(Credential).first()
            if cred:
                return int(cred.api_id), cred.api_hash
        return settings.TELEGRAM_API_ID, settings.TELEGRAM_API_HASH

    def get_valid_channels():
        """只获取有效的频道"""
        channels = set()
        with Session(engine) as session:
            db_channels = [c.username for c in session.query(Channel).all()]
            channels.update(db_channels)
        return list(channels)
    
    api_id, api_hash = get_api_credentials()
    valid_channels = get_valid_channels()
    
    if not valid_channels:
        print("❌ 没有有效的频道可供监听")
        return
    
    print(f"🎯 测试监听 {len(valid_channels)} 个有效频道...")
    
    client = TelegramClient('tg_monitor_session_test', api_id, api_hash)
    
    try:
        await client.start()
        
        # 注册事件处理器
        from telethon import events
        
        @client.on(events.NewMessage(chats=valid_channels))
        async def test_handler(event):
            print(f"📨 收到来自 {event.chat.username or event.chat.title} 的消息")
        
        print("✅ 事件处理器注册成功，开始测试...")
        print("💡 发送一条消息到任何监听的频道进行测试")
        print("⏹️  按 Ctrl+C 停止测试")
        
        # 运行10秒进行测试
        await asyncio.sleep(10)
        
    except KeyboardInterrupt:
        print("\n⏹️  测试已停止")
    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")
    finally:
        await client.disconnect()

def parse_time_period(period_str):
    """解析时间段字符串，返回开始和结束时间"""
    from datetime import datetime, timedelta
    import re
    
    now = datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # 预定义时间段
    if period_str.lower() == "today":
        start_time = today
        end_time = today + timedelta(days=1)
        return start_time, end_time, f"今天 ({start_time.strftime('%Y-%m-%d')})"
    
    elif period_str.lower() == "yesterday":
        start_time = today - timedelta(days=1)
        end_time = today
        return start_time, end_time, f"昨天 ({start_time.strftime('%Y-%m-%d')})"
    
    elif period_str.lower() == "week":
        start_time = today - timedelta(days=7)
        end_time = today + timedelta(days=1)
        return start_time, end_time, f"最近7天 ({start_time.strftime('%Y-%m-%d')} 至 {today.strftime('%Y-%m-%d')})"
    
    elif period_str.lower() == "month":
        start_time = today - timedelta(days=30)
        end_time = today + timedelta(days=1)
        return start_time, end_time, f"最近30天 ({start_time.strftime('%Y-%m-%d')} 至 {today.strftime('%Y-%m-%d')})"
    
    elif period_str.lower() == "year":
        start_time = today - timedelta(days=365)
        end_time = today + timedelta(days=1)
        return start_time, end_time, f"最近365天 ({start_time.strftime('%Y-%m-%d')} 至 {today.strftime('%Y-%m-%d')})"
    
    # 指定日期范围 (YYYY-MM-DD:YYYY-MM-DD)
    elif ":" in period_str:
        try:
            start_date, end_date = period_str.split(":")
            start_time = datetime.strptime(start_date.strip(), "%Y-%m-%d")
            end_time = datetime.strptime(end_date.strip(), "%Y-%m-%d") + timedelta(days=1)
            return start_time, end_time, f"指定范围 ({start_date} 至 {end_date})"
        except ValueError:
            raise ValueError("日期范围格式错误，请使用 YYYY-MM-DD:YYYY-MM-DD")
    
    # 指定日期 (YYYY-MM-DD)
    elif re.match(r'^\d{4}-\d{2}-\d{2}$', period_str):
        try:
            start_time = datetime.strptime(period_str, "%Y-%m-%d")
            end_time = start_time + timedelta(days=1)
            return start_time, end_time, f"指定日期 ({period_str})"
        except ValueError:
            raise ValueError("日期格式错误，请使用 YYYY-MM-DD")
    
    # 指定月份 (YYYY-MM)
    elif re.match(r'^\d{4}-\d{2}$', period_str):
        try:
            year, month = period_str.split("-")
            start_time = datetime(int(year), int(month), 1)
            if int(month) == 12:
                end_time = datetime(int(year) + 1, 1, 1)
            else:
                end_time = datetime(int(year), int(month) + 1, 1)
            return start_time, end_time, f"指定月份 ({period_str})"
        except ValueError:
            raise ValueError("月份格式错误，请使用 YYYY-MM")
    
    # 指定年份 (YYYY)
    elif re.match(r'^\d{4}$', period_str):
        try:
            year = int(period_str)
            start_time = datetime(year, 1, 1)
            end_time = datetime(year + 1, 1, 1)
            return start_time, end_time, f"指定年份 ({period_str})"
        except ValueError:
            raise ValueError("年份格式错误，请使用 YYYY")
    
    else:
        raise ValueError(f"不支持的时间段格式: {period_str}")

def check_links_by_period(period_str, max_concurrent=5, show_invalid_details=True, max_invalid_show=10):
    """按时间段检测链接有效性"""
    if not LINK_VALIDATOR_AVAILABLE:
        print("❌ 链接检测功能不可用，请确保 link_validator.py 存在")
        return
    
    try:
        start_time, end_time, period_desc = parse_time_period(period_str)
    except ValueError as e:
        print(f"❌ 时间段格式错误: {e}")
        return
    
    print(f"🔍 开始检测 {period_desc} 的链接...")
    print(f"�� 时间范围: {start_time.strftime('%Y-%m-%d %H:%M:%S')} 至 {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 获取指定时间范围内的消息
    with Session(engine) as session:
        messages = session.query(Message).filter(
            Message.timestamp >= start_time,
            Message.timestamp < end_time,
            Message.links.isnot(None)
        ).all()
    
    if not messages:
        print("📭 没有找到需要检测的消息")
        return
    
    print(f"📋 找到 {len(messages)} 条消息需要检测")
    
    # 提取所有链接
    all_urls = []
    message_urls = {}  # {message_id: [urls]}
    
    for msg in messages:
        urls = extract_urls(msg.links)
        if urls:
            all_urls.extend(urls)
            message_urls[msg.id] = urls
    
    if not all_urls:
        print("📭 没有找到需要检测的链接")
        return
    
    print(f"🔗 共找到 {len(all_urls)} 个链接")
    
    # 安全检查
    if not check_safety_limits(len(all_urls), max_concurrent):
        return
    
    # 用户确认
    if not confirm_large_check(len(all_urls), max_concurrent):
        return
    
    # 开始检测
    async def run_check():
        global current_check_session, interrupted
        
        validator = LinkValidator()
        
        # 检查是否已中断
        if interrupted:
            print("❌ 检测已被中断")
            return
        
        print("🚀 开始链接检测...")
        print(f"⏱️  开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 显示检测进度
        print(f"📊 检测配置:")
        print(f"   - 链接总数: {len(all_urls)}")
        print(f"   - 最大并发: {max_concurrent}")
        print(f"   - 时间段: {period_desc}")
        
        results = await validator.check_multiple_links(all_urls, max_concurrent)
        
        # 检查是否已中断
        if interrupted:
            print("❌ 检测已被中断，正在保存已完成的结果...")
            # 保存部分结果
            check_time = datetime.now()
            with Session(engine) as session:
                current_check_session = session
                # 创建统计记录（标记为中断）
                summary = validator.get_summary(results)
                stats = LinkCheckStats(
                    check_time=check_time,
                    total_messages=len(messages),
                    total_links=len(all_urls),
                    valid_links=summary['valid_links'],
                    invalid_links=summary['invalid_links'],
                    netdisk_stats=summary['netdisk_stats'],
                    check_duration=0,  # 中断时无法准确计算
                    status='interrupted'
                )
                session.add(stats)
                session.commit()
                
                # 保存详细结果
                for result in results:
                    detail = LinkCheckDetails(
                        check_time=check_time,
                        message_id=0,
                        netdisk_type=result['netdisk_type'],
                        url=result['url'],
                        is_valid=result['is_valid'],
                        response_time=result['response_time'],
                        error_reason=result['error']
                    )
                    session.add(detail)
                
                session.commit()
                current_check_session = None
            
            print("✅ 已完成的检测结果已保存")
            print_detailed_report(results, summary, show_invalid_details, max_invalid_show, period_desc + " (中断)")
            return
        
        # 正常完成检测
        check_time = datetime.now()
        start_time_check = time.time()
        
        print(f"⏱️  结束时间: {check_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"⏱️  总耗时: {time.time() - start_time_check:.2f} 秒")
        
        with Session(engine) as session:
            current_check_session = session
            # 创建统计记录
            summary = validator.get_summary(results)
            stats = LinkCheckStats(
                check_time=check_time,
                total_messages=len(messages),
                total_links=len(all_urls),
                valid_links=summary['valid_links'],
                invalid_links=summary['invalid_links'],
                netdisk_stats=summary['netdisk_stats'],
                check_duration=time.time() - start_time_check,
                status='completed'
            )
            session.add(stats)
            session.commit()
            
            # 保存详细结果
            for result in results:
                detail = LinkCheckDetails(
                    check_time=check_time,
                    message_id=0,  # 暂时设为0，后续可以优化
                    netdisk_type=result['netdisk_type'],
                    url=result['url'],
                    is_valid=result['is_valid'],
                    response_time=result['response_time'],
                    error_reason=result['error']
                )
                session.add(detail)
            
            session.commit()
            current_check_session = None
        
        # 打印详细报告
        print_detailed_report(results, summary, show_invalid_details, max_invalid_show, period_desc)
    
    # 运行异步检测
    try:
        asyncio.run(run_check())
    except KeyboardInterrupt:
        print("\n⚠️  检测被用户中断")
    except Exception as e:
        print(f"❌ 检测过程中发生错误: {e}")
        if current_check_session:
            try:
                current_check_session.rollback()
                print("✅ 已回滚未完成的数据库操作")
            except:
                pass

def check_links(hours=24, max_concurrent=5, show_invalid_details=True, max_invalid_show=10):
    """检测指定时间范围内的链接有效性"""
    if not LINK_VALIDATOR_AVAILABLE:
        print("❌ 链接检测功能不可用，请确保 link_validator.py 存在")
        return
    
    print(f"🔍 开始检测过去 {hours} 小时的链接...")
    
    # 获取指定时间范围内的消息
    with Session(engine) as session:
        cutoff_time = datetime.now() - timedelta(hours=hours)
        messages = session.query(Message).filter(
            Message.timestamp >= cutoff_time,
            Message.links.isnot(None)
        ).all()
    
    if not messages:
        print("📭 没有找到需要检测的消息")
        return
    
    print(f"📋 找到 {len(messages)} 条消息需要检测")
    
    # 提取所有链接
    all_urls = []
    message_urls = {}  # {message_id: [urls]}
    
    for msg in messages:
        urls = extract_urls(msg.links)
        if urls:
            all_urls.extend(urls)
            message_urls[msg.id] = urls
    
    if not all_urls:
        print("📭 没有找到需要检测的链接")
        return
    
    print(f"🔗 共找到 {len(all_urls)} 个链接")
    
    # 安全检查
    if not check_safety_limits(len(all_urls), max_concurrent):
        return
    
    # 用户确认
    if not confirm_large_check(len(all_urls), max_concurrent):
        return
    
    # 开始检测
    async def run_check():
        validator = LinkValidator()
        
        print("🚀 开始链接检测...")
        print(f"⏱️  开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 显示检测进度
        print(f"📊 检测配置:")
        print(f"   - 链接总数: {len(all_urls)}")
        print(f"   - 最大并发: {max_concurrent}")
        print(f"   - 时间范围: 过去 {hours} 小时")
        
        results = await validator.check_multiple_links(all_urls, max_concurrent)
        
        # 保存检测结果
        check_time = datetime.now()
        start_time = time.time()
        
        print(f"⏱️  结束时间: {check_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"⏱️  总耗时: {time.time() - start_time:.2f} 秒")
        
        with Session(engine) as session:
            # 创建统计记录
            summary = validator.get_summary(results)
            stats = LinkCheckStats(
                check_time=check_time,
                total_messages=len(messages),
                total_links=len(all_urls),
                valid_links=summary['valid_links'],
                invalid_links=summary['invalid_links'],
                netdisk_stats=summary['netdisk_stats'],
                check_duration=time.time() - start_time,
                status='completed'
            )
            session.add(stats)
            session.commit()
            
            # 保存详细结果
            for result in results:
                detail = LinkCheckDetails(
                    check_time=check_time,
                    message_id=0,  # 暂时设为0，后续可以优化
                    netdisk_type=result['netdisk_type'],
                    url=result['url'],
                    is_valid=result['is_valid'],
                    response_time=result['response_time'],
                    error_reason=result['error']
                )
                session.add(detail)
            
            session.commit()
        
        # 打印详细报告
        print_detailed_report(results, summary, show_invalid_details, max_invalid_show)
    
    # 运行异步检测
    try:
        asyncio.run(run_check())
    except KeyboardInterrupt:
        print("\n⚠️  检测被用户中断")
    except Exception as e:
        print(f"❌ 检测过程中发生错误: {e}")

def check_all_links(max_concurrent=5, show_invalid_details=True, max_invalid_show=10):
    """检测所有历史链接"""
    global current_check_session, interrupted
    
    if not LINK_VALIDATOR_AVAILABLE:
        print("❌ 链接检测功能不可用，请确保 link_validator.py 存在")
        return
    
    print("🔍 开始检测所有历史链接...")
    
    # 获取所有有链接的消息
    with Session(engine) as session:
        messages = session.query(Message).filter(
            Message.links.isnot(None)
        ).all()
    
    if not messages:
        print("📭 没有找到需要检测的消息")
        return
    
    print(f"📋 找到 {len(messages)} 条消息需要检测")
    
    # 提取所有链接
    all_urls = []
    message_urls = {}  # {message_id: [urls]}
    
    for msg in messages:
        urls = extract_urls(msg.links)
        if urls:
            all_urls.extend(urls)
            message_urls[msg.id] = urls
    
    if not all_urls:
        print("📭 没有找到需要检测的链接")
        return
    
    print(f"🔗 共找到 {len(all_urls)} 个链接")
    
    # 安全检查 - 全量检测需要更严格的限制
    if len(all_urls) > SAFETY_CONFIG['max_links_per_check']:
        print(f"❌ 全量检测链接数量 ({len(all_urls)}) 超过安全限制 ({SAFETY_CONFIG['max_links_per_check']})")
        print(f"💡 建议使用时间段检测或分批检测:")
        print(f"   - python manage.py --check-period week 3")
        print(f"   - python manage.py --check-period month 3")
        print(f"   - python manage.py --check-links 24 3")
        return
    
    if max_concurrent > 3:  # 全量检测限制更严格的并发
        print(f"❌ 全量检测并发数 ({max_concurrent}) 过高，建议使用 3 或更少")
        max_concurrent = 3
        print(f"💡 已自动调整为 {max_concurrent}")
    
    # 用户确认 - 全量检测需要强制确认
    print("\n" + "="*60)
    print("🚨 全量检测警告")
    print("="*60)
    print(f"📊 检测规模:")
    print(f"   - 链接数量: {len(all_urls)}")
    print(f"   - 最大并发: {max_concurrent}")
    print(f"   - 预计耗时: {len(all_urls) * 3 / max_concurrent / 60:.1f} - {len(all_urls) * 5 / max_concurrent / 60:.1f} 小时")
    
    print(f"\n⚠️  风险提示:")
    print(f"   - 全量检测可能触发网盘反爬虫机制")
    print(f"   - 建议在非高峰期进行")
    print(f"   - 如遇到大量错误，请立即中断")
    
    while True:
        response = input(f"\n❓ 确认开始全量检测 {len(all_urls)} 个链接? (输入 'yes' 确认): ").strip().lower()
        if response == 'yes':
            break
        elif response in ['n', 'no', '']:
            print("❌ 检测已取消")
            return
        else:
            print("请输入 'yes' 确认或 'no' 取消")
    
    # 开始检测
    async def run_check():
        global current_check_session, interrupted
        
        validator = LinkValidator()
        
        # 检查是否已中断
        if interrupted:
            print("❌ 检测已被中断")
            return
        
        print("🚀 开始全量链接检测...")
        print(f"⏱️  开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 显示检测进度
        print(f"📊 检测配置:")
        print(f"   - 链接总数: {len(all_urls)}")
        print(f"   - 最大并发: {max_concurrent}")
        print(f"   - 检测范围: 所有历史链接")
        
        results = await validator.check_multiple_links(all_urls, max_concurrent)
        
        # 检查是否已中断
        if interrupted:
            print("❌ 检测已被中断，正在保存已完成的结果...")
            # 保存部分结果
            check_time = datetime.now()
            with Session(engine) as session:
                current_check_session = session
                # 创建统计记录（标记为中断）
                summary = validator.get_summary(results)
                stats = LinkCheckStats(
                    check_time=check_time,
                    total_messages=len(messages),
                    total_links=len(all_urls),
                    valid_links=summary['valid_links'],
                    invalid_links=summary['invalid_links'],
                    netdisk_stats=summary['netdisk_stats'],
                    check_duration=0,  # 中断时无法准确计算
                    status='interrupted'
                )
                session.add(stats)
                session.commit()
                
                # 保存详细结果
                for result in results:
                    detail = LinkCheckDetails(
                        check_time=check_time,
                        message_id=0,
                        netdisk_type=result['netdisk_type'],
                        url=result['url'],
                        is_valid=result['is_valid'],
                        response_time=result['response_time'],
                        error_reason=result['error']
                    )
                    session.add(detail)
                
                session.commit()
                current_check_session = None
            
            print("✅ 已完成的检测结果已保存")
            print_detailed_report(results, summary, show_invalid_details, max_invalid_show, "所有历史链接 (中断)")
            return
        
        # 正常完成检测
        check_time = datetime.now()
        start_time = time.time()
        
        print(f"⏱️  结束时间: {check_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"⏱️  总耗时: {time.time() - start_time:.2f} 秒")
        
        with Session(engine) as session:
            current_check_session = session
            # 创建统计记录
            summary = validator.get_summary(results)
            stats = LinkCheckStats(
                check_time=check_time,
                total_messages=len(messages),
                total_links=len(all_urls),
                valid_links=summary['valid_links'],
                invalid_links=summary['invalid_links'],
                netdisk_stats=summary['netdisk_stats'],
                check_duration=time.time() - start_time,
                status='completed'
            )
            session.add(stats)
            session.commit()
            
            # 保存详细结果
            for result in results:
                detail = LinkCheckDetails(
                    check_time=check_time,
                    message_id=0,  # 暂时设为0，后续可以优化
                    netdisk_type=result['netdisk_type'],
                    url=result['url'],
                    is_valid=result['is_valid'],
                    response_time=result['response_time'],
                    error_reason=result['error']
                )
                session.add(detail)
            
            session.commit()
            current_check_session = None
        
        # 打印详细报告
        print_detailed_report(results, summary, show_invalid_details, max_invalid_show, "所有历史链接")
    
    # 运行异步检测
    try:
        asyncio.run(run_check())
    except KeyboardInterrupt:
        print("\n⚠️  检测被用户中断")
    except Exception as e:
        print(f"❌ 检测过程中发生错误: {e}")
        if current_check_session:
            try:
                current_check_session.rollback()
                print("✅ 已回滚未完成的数据库操作")
            except:
                pass

def print_detailed_report(results, summary, show_invalid_details=True, max_invalid_show=10, period_desc=""):
    """打印详细的检测报告"""
    print("\n" + "="*80)
    print("📊 链接检测详细报告")
    if period_desc:
        print(f"📅 检测时段: {period_desc}")
    print("="*80)
    
    # 总体统计
    print(f"🔍 检测概况:")
    print(f"  - 总链接数: {summary['total_links']}")
    print(f"  - 有效链接: {summary['valid_links']} ✅")
    print(f"  - 无效链接: {summary['invalid_links']} ❌")
    print(f"  - 成功率: {summary['success_rate']:.1f}%")
    print(f"  - 平均响应时间: {summary['avg_response_time']:.2f}秒")
    
    # 按网盘类型统计
    print(f"\n📈 各网盘统计:")
    for netdisk, stats in summary['netdisk_stats'].items():
        success_rate = (stats['valid'] / stats['total'] * 100) if stats['total'] > 0 else 0
        status_icon = "✅" if success_rate >= 80 else "⚠️" if success_rate >= 50 else "❌"
        print(f"  {status_icon} {netdisk}: {stats['valid']}/{stats['total']} ({success_rate:.1f}%)")
    
    # 显示失效链接详情
    if show_invalid_details:
        invalid_results = [r for r in results if not r['is_valid']]
        if invalid_results:
            print(f"\n❌ 失效链接详情 (显示前{min(max_invalid_show, len(invalid_results))}个):")
            print("-" * 80)
            
            for i, result in enumerate(invalid_results[:max_invalid_show]):
                print(f"{i+1:2d}. {result['netdisk_type']}")
                print(f"    URL: {result['url']}")
                print(f"    错误: {result['error']}")
                if result['response_time']:
                    print(f"    响应时间: {result['response_time']:.2f}秒")
                print()
            
            if len(invalid_results) > max_invalid_show:
                print(f"... 还有 {len(invalid_results) - max_invalid_show} 个失效链接")
                print("💡 使用 --link-stats 查看完整统计信息")
    
    # 性能分析
    response_times = [r['response_time'] for r in results if r['response_time'] is not None]
    if response_times:
        fast_links = sum(1 for t in response_times if t < 2.0)
        slow_links = sum(1 for t in response_times if t > 5.0)
        
        print(f"\n⚡ 性能分析:")
        print(f"  - 快速响应 (<2秒): {fast_links} 个")
        print(f"  - 正常响应 (2-5秒): {len(response_times) - fast_links - slow_links} 个")
        print(f"  - 慢速响应 (>5秒): {slow_links} 个")
    
    print("="*80)
    print("�� 检测完成！结果已保存到数据库")

def show_link_stats():
    """显示链接检测统计信息"""
    with Session(engine) as session:
        # 获取最近的检测统计
        recent_stats = session.query(LinkCheckStats).order_by(
            LinkCheckStats.check_time.desc()
        ).limit(10).all()
        
        if not recent_stats:
            print("📭 没有找到链接检测记录")
            return
        
        print("📊 最近的链接检测统计:")
        print("=" * 60)
        
        for stats in recent_stats:
            success_rate = (stats.valid_links / stats.total_links * 100) if stats.total_links > 0 else 0
            status_icon = "✅" if stats.status == 'completed' else "⚠️" if stats.status == 'interrupted' else "❓"
            print(f"检测时间: {stats.check_time}")
            print(f"状态: {status_icon} {stats.status}")
            print(f"总链接数: {stats.total_links}, 有效: {stats.valid_links}, 无效: {stats.invalid_links}")
            print(f"成功率: {success_rate:.1f}%, 耗时: {stats.check_duration:.2f}秒")
            
            if stats.netdisk_stats:
                print("各网盘统计:")
                for netdisk, data in stats.netdisk_stats.items():
                    netdisk_rate = (data['valid'] / data['total'] * 100) if data['total'] > 0 else 0
                    print(f"  - {netdisk}: {data['valid']}/{data['total']} ({netdisk_rate:.1f}%)")
            
            print("-" * 40)
        
        # 询问是否查看失效链接详情
        print("\n💡 提示: 使用 --check-links 或 --check-all-links 进行新的检测")
        print("💡 使用 --show-invalid-links [check_time] 查看特定检测的失效链接")
        print("💡 使用 --show-interrupted 查看中断的检测记录")

def show_interrupted_checks():
    """显示中断的检测记录"""
    with Session(engine) as session:
        interrupted_stats = session.query(LinkCheckStats).filter(
            LinkCheckStats.status == 'interrupted'
        ).order_by(LinkCheckStats.check_time.desc()).all()
        
        if not interrupted_stats:
            print("📭 没有找到中断的检测记录")
            return
        
        print("⚠️  中断的检测记录:")
        print("=" * 60)
        
        for stats in interrupted_stats:
            success_rate = (stats.valid_links / stats.total_links * 100) if stats.total_links > 0 else 0
            print(f"检测时间: {stats.check_time}")
            print(f"总链接数: {stats.total_links}, 有效: {stats.valid_links}, 无效: {stats.invalid_links}")
            print(f"成功率: {success_rate:.1f}%")
            print(f"状态: 中断 (可能未完成所有链接检测)")
            print("-" * 40)
        
        print("💡 建议: 可以重新运行检测命令来完成剩余的链接检测")

def clear_link_check_data(confirm=False):
    """清空所有链接检测数据"""
    with Session(engine) as session:
        # 获取当前数据统计
        stats_count = session.query(LinkCheckStats).count()
        details_count = session.query(LinkCheckDetails).count()
        
        if stats_count == 0 and details_count == 0:
            print("📭 没有找到需要清空的检测数据")
            return
        
        print(f"📊 当前检测数据统计:")
        print(f"  - 统计记录: {stats_count} 条")
        print(f"  - 详情记录: {details_count} 条")
        
        if not confirm:
            print("\n⚠️  警告: 此操作将永久删除所有链接检测数据！")
            print("💡 包括:")
            print("  - 所有检测统计记录")
            print("  - 所有链接检测详情")
            print("  - 所有中断记录")
            
            response = input("\n确认要清空所有检测数据吗？(输入 'yes' 确认): ").strip().lower()
            if response != 'yes':
                print("❌ 操作已取消")
                return
        
        try:
            # 先删除详情记录（外键依赖）
            deleted_details = session.query(LinkCheckDetails).delete()
            print(f"✅ 已删除 {deleted_details} 条详情记录")
            
            # 再删除统计记录
            deleted_stats = session.query(LinkCheckStats).delete()
            print(f"✅ 已删除 {deleted_stats} 条统计记录")
            
            session.commit()
            print("🎉 所有链接检测数据已清空！")
            
        except Exception as e:
            session.rollback()
            print(f"❌ 清空数据失败: {e}")
            return

def clear_old_link_check_data(days=30, confirm=False):
    """清空指定天数之前的检测数据"""
    with Session(engine) as session:
        cutoff_time = datetime.now() - timedelta(days=days)
        
        # 获取要删除的数据统计
        old_stats = session.query(LinkCheckStats).filter(
            LinkCheckStats.check_time < cutoff_time
        ).all()
        
        old_details = session.query(LinkCheckDetails).filter(
            LinkCheckDetails.check_time < cutoff_time
        ).all()
        
        if not old_stats and not old_details:
            print(f"📭 没有找到 {days} 天前的检测数据")
            return
        
        print(f"📊 将删除 {days} 天前的检测数据:")
        print(f"  - 统计记录: {len(old_stats)} 条")
        print(f"  - 详情记录: {len(old_details)} 条")
        print(f"  - 删除时间范围: {cutoff_time.strftime('%Y-%m-%d %H:%M:%S')} 之前")
        
        if not confirm:
            response = input(f"\n确认要删除 {days} 天前的检测数据吗？(输入 'yes' 确认): ").strip().lower()
            if response != 'yes':
                print("❌ 操作已取消")
                return
        
        try:
            # 先删除详情记录
            deleted_details = session.query(LinkCheckDetails).filter(
                LinkCheckDetails.check_time < cutoff_time
            ).delete()
            print(f"✅ 已删除 {deleted_details} 条详情记录")
            
            # 再删除统计记录
            deleted_stats = session.query(LinkCheckStats).filter(
                LinkCheckStats.check_time < cutoff_time
            ).delete()
            print(f"✅ 已删除 {deleted_stats} 条统计记录")
            
            session.commit()
            print(f"🎉 {days} 天前的检测数据已清空！")
            
        except Exception as e:
            session.rollback()
            print(f"❌ 删除数据失败: {e}")
            return

def show_invalid_links(check_time_str=None, limit=20):
    """显示失效链接的详细信息"""
    with Session(engine) as session:
        if check_time_str:
            # 解析时间字符串
            try:
                check_time = datetime.fromisoformat(check_time_str.replace('Z', '+00:00'))
                details = session.query(LinkCheckDetails).filter(
                    LinkCheckDetails.check_time == check_time,
                    LinkCheckDetails.is_valid == False
                ).limit(limit).all()
            except ValueError:
                print("❌ 时间格式错误，请使用 ISO 格式 (如: 2024-01-01T12:00:00)")
                return
        else:
            # 获取最近的失效链接
            details = session.query(LinkCheckDetails).filter(
                LinkCheckDetails.is_valid == False
            ).order_by(LinkCheckDetails.check_time.desc()).limit(limit).all()
        
        if not details:
            print("📭 没有找到失效链接记录")
            return
        
        print(f"❌ 失效链接详情 (显示前{len(details)}个):")
        print("=" * 80)
        
        current_check_time = None
        for i, detail in enumerate(details, 1):
            if detail.check_time != current_check_time:
                current_check_time = detail.check_time
                print(f"\n🔍 检测时间: {detail.check_time}")
                print("-" * 40)
            
            print(f"{i:2d}. {detail.netdisk_type}")
            print(f"    URL: {detail.url}")
            print(f"    错误: {detail.error_reason}")
            if detail.response_time:
                print(f"    响应时间: {detail.response_time:.2f}秒")
            print()

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
        # 使用异步版本获取详细信息
        import asyncio
        try:
            asyncio.run(list_channels_detailed())
        except Exception as e:
            print(f"❌ 获取详细信息失败: {str(e)}")
            print("显示简化版本...")
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
    elif "--dedup-links-fast" in sys.argv or "--dedup-links" in sys.argv:
        from app.services.dedup_runtime_service import run_dedup_now

        if "--dedup-links-fast" in sys.argv:
            idx = sys.argv.index("--dedup-links-fast")
            if len(sys.argv) > idx + 1 and sys.argv[idx + 1].isdigit():
                print("提示: 新版统一去重已不再使用 batch_size 参数，将按后台去重计划执行。")

        result = run_dedup_now(updated_by="cli")
        if result.get("success"):
            print(
                f"去重完成：扫描 {result.get('scanned_messages', 0)} 条消息，"
                f"删除 {result.get('deleted_count', 0)} 条，"
                f"耗时 {result.get('duration_seconds', 0)} 秒。"
            )
        else:
            print(f"去重失败: {result.get('error') or 'unknown error'}")
    elif "--check-links" in sys.argv:
        # 链接检测功能
        hours = 24  # 默认检测24小时
        max_concurrent = 5  # 默认最大并发5
        
        idx = sys.argv.index("--check-links")
        if len(sys.argv) > idx + 1:
            try:
                hours = int(sys.argv[idx + 1])
            except ValueError:
                print("❌ 时间范围必须是数字")
                sys.exit(1)
        
        if len(sys.argv) > idx + 2:
            try:
                max_concurrent = int(sys.argv[idx + 2])
            except ValueError:
                print("❌ 并发数必须是数字")
                sys.exit(1)
        
        check_links(hours, max_concurrent)
        
    elif "--check-all-links" in sys.argv:
        # 检测所有历史链接
        max_concurrent = 5  # 默认最大并发5
        
        idx = sys.argv.index("--check-all-links")
        if len(sys.argv) > idx + 1:
            try:
                max_concurrent = int(sys.argv[idx + 1])
            except ValueError:
                print("❌ 并发数必须是数字")
                sys.exit(1)
        
        check_all_links(max_concurrent)
        
    elif "--check-period" in sys.argv:
        # 按时间段检测链接
        max_concurrent = 5  # 默认最大并发5
        
        idx = sys.argv.index("--check-period")
        if len(sys.argv) > idx + 1:
            period_str = sys.argv[idx + 1]
            
            # 检查是否有并发数参数
            if len(sys.argv) > idx + 2:
                try:
                    max_concurrent = int(sys.argv[idx + 2])
                except ValueError:
                    print("❌ 并发数必须是数字")
                    sys.exit(1)
            
            check_links_by_period(period_str, max_concurrent)
        else:
            print("请提供时间段参数 (如: today, yesterday, week, month, year, YYYY-MM-DD, YYYY-MM, YYYY, YYYY-MM-DD:YYYY-MM-DD)")
        
    elif "--link-stats" in sys.argv:
        # 显示链接检测统计
        show_link_stats()
        
    elif "--show-invalid-links" in sys.argv:
        # 显示失效链接详情
        idx = sys.argv.index("--show-invalid-links")
        if len(sys.argv) > idx + 1:
            show_invalid_links(sys.argv[idx + 1])
        else:
            show_invalid_links()
        
    elif "--show-interrupted" in sys.argv:
        # 显示中断的检测记录
        show_interrupted_checks()
        
    elif "--clear-link-check-data" in sys.argv:
        # 清空所有链接检测数据
        clear_link_check_data()

    elif "--clear-old-link-check-data" in sys.argv:
        # 清空指定天数之前的检测数据
        days = 30  # 默认30天
        idx = sys.argv.index("--clear-old-link-check-data")
        if len(sys.argv) > idx + 1 and sys.argv[idx+1].isdigit():
            days = int(sys.argv[idx+1])
        clear_old_link_check_data(days)
        
    elif "--diagnose-channels" in sys.argv:
        # 诊断频道
        asyncio.run(diagnose_channels())
        
    elif "--test-monitor" in sys.argv:
        # 测试事件处理器
        asyncio.run(test_event_handler())
        
    else:
        print_help() 

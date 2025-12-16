"""
频道管理服务
复用 app/scripts/manage.py 中的逻辑
"""

import os
import shutil
import asyncio
from typing import List, Dict, Any, Tuple
from telethon import TelegramClient, events
from sqlalchemy.orm import Session
from app.models.models import Channel, Credential, engine
from app.models.config import settings
import logging

logger = logging.getLogger(__name__)


def is_invite_link_hash(channel_name: str) -> bool:
    """判断是否为邀请链接哈希格式"""
    import re
    pattern = r'^\+[a-zA-Z0-9_-]{10,}$'
    return bool(re.match(pattern, channel_name))


def ensure_session_file(session_name: str) -> bool:
    """确保指定的 session 文件存在，如果不存在则自动复制"""
    main_session = 'tg_monitor_session.session'
    target_session = f'{session_name}.session'
    
    if os.path.exists(target_session):
        return True
    
    if not os.path.exists(main_session):
        logger.error(f"主 session 文件 {main_session} 不存在")
        return False
    
    try:
        shutil.copy2(main_session, target_session)
        return True
    except Exception as e:
        logger.error(f"复制 session 文件失败: {e}")
        return False


def get_api_credentials() -> Tuple[int, str]:
    """获取 API 凭据"""
    with Session(engine) as session:
        cred = session.query(Credential).first()
        if cred:
            return int(cred.api_id), cred.api_hash
    return settings.TELEGRAM_API_ID, settings.TELEGRAM_API_HASH


def get_channels() -> List[str]:
    """获取频道列表"""
    channels = set()
    
    with Session(engine) as session:
        db_channels = [c.username for c in session.query(Channel).all()]
        channels.update(db_channels)
    
    if hasattr(settings, 'DEFAULT_CHANNELS'):
        env_channels = [c.strip() for c in settings.DEFAULT_CHANNELS.split(',') if c.strip()]
        channels.update(env_channels)
    
    return list(channels)


async def diagnose_channels() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    诊断每个频道是否可以正常访问
    
    Returns:
        (valid_channels, invalid_channels) 元组
    """
    if not ensure_session_file('tg_monitor_session_diagnose'):
        logger.error("无法进行频道诊断，缺少必要的 session 文件")
        return [], []
    
    api_id, api_hash = get_api_credentials()
    channel_usernames = get_channels()
    
    if not channel_usernames:
        return [], []
    
    client = TelegramClient('tg_monitor_session_diagnose', api_id, api_hash)
    
    try:
        await client.start()
        logger.info("Telegram客户端连接成功")
        
        valid_channels = []
        invalid_channels = []
        
        for i, channel in enumerate(channel_usernames, 1):
            try:
                entity = await client.get_entity(f"https://t.me/{channel}")
                channel_info = await client.get_entity(entity)
                
                channel_type = 'invite_link' if is_invite_link_hash(channel) else 'standard'
                
                valid_channels.append({
                    'username': channel,
                    'title': getattr(channel_info, 'title', '未知'),
                    'id': channel_info.id,
                    'type': channel_type,
                    'participants_count': getattr(channel_info, 'participants_count', None)
                })
                
            except Exception as e:
                error_msg = str(e)
                logger.error(f"频道 {channel} 诊断失败: {error_msg}")
                
                invalid_channels.append({
                    'username': channel,
                    'error': error_msg,
                    'type': 'unknown'
                })
        
        return valid_channels, invalid_channels
        
    except Exception as e:
        logger.error(f"客户端连接失败: {str(e)}")
        return [], []
        
    finally:
        await client.disconnect()


async def test_monitor() -> Dict[str, Any]:
    """
    测试监控功能
    
    Returns:
        测试结果字典
    """
    if not ensure_session_file('tg_monitor_session_test'):
        return {
            "success": False,
            "error": "无法进行测试，缺少必要的 session 文件"
        }
    
    api_id, api_hash = get_api_credentials()
    
    with Session(engine) as session:
        db_channels = [c.username for c in session.query(Channel).all()]
    
    if not db_channels:
        return {
            "success": False,
            "error": "没有有效的频道可供监听"
        }
    
    client = TelegramClient('tg_monitor_session_test', api_id, api_hash)
    
    try:
        await client.start()
        
        # 注册事件处理器
        message_received = False
        
        @client.on(events.NewMessage(chats=db_channels))
        async def test_handler(event):
            nonlocal message_received
            message_received = True
        
        # 等待5秒进行测试
        await asyncio.sleep(5)
        
        await client.disconnect()
        
        return {
            "success": True,
            "channels_tested": len(db_channels),
            "message_received": message_received,
            "message": "测试完成，事件处理器已注册"
        }
        
    except Exception as e:
        logger.error(f"测试失败: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }
    finally:
        try:
            await client.disconnect()
        except:
            pass


from __future__ import annotations

import asyncio
import datetime
import logging
import sys
import warnings
from pathlib import Path
from typing import Any, Dict, List, Tuple

from telethon import TelegramClient, events
from sqlalchemy.orm import Session

from app.core.monitor_observability import MonitorMetrics, log_monitor_event
from app.core.monitor_parser import parse_message_content, parse_message_records
from app.models.config import settings
from app.models.db import async_session
from app.models.models import Credential, Message, engine, ensure_message_monitor_source_columns
from app.services.channel_registry import (
    get_runtime_channel_metadata,
    get_runtime_channels,
)
from app.services.resource_ops import (
    ensure_message_link_refs_for_message_ids,
)
from app.services.channel_daily_stats_service import (
    accumulate_channel_daily_stats_for_message_ids,
)
from app.services.system_config_service import get_monitor_runtime_config

warnings.filterwarnings(
    "ignore",
    message=".*async sessions support is an experimental feature.*",
    category=UserWarning,
)
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL, "INFO"))
logger = logging.getLogger(__name__)
monitor_metrics = MonitorMetrics(logger)

FAILED_MESSAGES_LOG = Path("data/failed_messages.log")
ERROR_MESSAGES_LOG = Path("data/error_messages.log")


def get_api_credentials() -> Tuple[int, str]:
    """获取 API 凭据，优先使用数据库中的凭据。"""
    with Session(engine) as session:
        credential = session.query(Credential).first()
        if credential:
            return int(credential.api_id), credential.api_hash
    return settings.TELEGRAM_API_ID, settings.TELEGRAM_API_HASH

def get_channels() -> List[str]:
    """获取运行时频道列表，仅从数据库读取。"""
    return get_runtime_channels()


def get_channel_runtime_metadata() -> Dict[str, Dict[str, Any]]:
    return get_runtime_channel_metadata()



def is_invite_link_hash(channel_name: str) -> bool:
    """判断是否为邀请链接哈希格式。"""
    import re

    return bool(re.match(r"^\+[a-zA-Z0-9_-]{10,}$", channel_name))


async def build_channel_id_mapping(
    tg_client: TelegramClient,
    channels: List[str] | None = None,
    runtime_metadata: Dict[str, Dict[str, Any]] | None = None,
) -> Tuple[List[int], Dict[str, Dict[str, Any]]]:
    """构建所有频道到真实 ID 的映射。"""
    resolved_channels = channels if channels is not None else get_channels()
    resolved_ids: List[int] = []
    resolved_info: Dict[str, Dict[str, Any]] = {}

    print(f"🔍 开始解析 {len(resolved_channels)} 个频道到ID...")
    for channel in resolved_channels:
        try:
            entity = await tg_client.get_entity(f"https://t.me/{channel}")
            metadata = (runtime_metadata or {}).get(channel) or {}
            resolved_ids.append(entity.id)
            resolved_info[channel] = {
                "id": entity.id,
                "title": getattr(entity, "title", "N/A"),
                "username": getattr(entity, "username", None),
                "type": "invite_link" if is_invite_link_hash(channel) else "standard",
                "parser_profile": metadata.get("parser_profile"),
                "config_id": metadata.get("config_id"),
                "channel_key": channel,
            }
            print(f"✅ 解析频道: {channel} -> ID: {entity.id}, Title: {getattr(entity, 'title', 'N/A')}")
        except Exception as exc:
            monitor_metrics.record_failure("channel_resolve", channel=channel, error=str(exc))
            print(f"❌ 解析失败: {channel}: {exc}")

    print(f"✅ 成功解析 {len(resolved_ids)} 个频道ID")
    return resolved_ids, resolved_info


async def refresh_channel_mapping(force: bool = False) -> bool:
    """定时刷新监听频道，保证后台改动无需重启即可生效。"""
    global channel_signature

    latest_channels = get_channels()
    runtime_metadata = get_channel_runtime_metadata()
    latest_signature = tuple(sorted(latest_channels))
    active_signature = tuple(sorted(channel_info.keys()))
    if not force and latest_signature == channel_signature and active_signature == latest_signature:
        return False

    ids, info = await build_channel_id_mapping(client, latest_channels, runtime_metadata=runtime_metadata)
    channel_usernames.clear()
    channel_usernames.extend(latest_channels)
    channel_ids.clear()
    channel_ids.extend(ids)
    channel_info.clear()
    channel_info.update(info)
    channel_id_to_name.clear()
    channel_id_to_name.update({item["id"]: channel for channel, item in info.items()})
    channel_signature = latest_signature

    monitor_metrics.record_refresh(
        configured=len(latest_channels),
        active=len(channel_ids),
        changed=bool(force or latest_signature != active_signature),
    )
    print(f"[{datetime.datetime.now()}] refreshed monitored channels: {len(channel_ids)}")
    return True


async def channel_refresh_loop() -> None:
    """定时刷新频道映射。"""
    while True:
        try:
            monitor_runtime_config = get_monitor_runtime_config()
            interval_seconds = max(
                10,
                int(monitor_runtime_config["monitor_channel_refresh_interval_seconds"] or 60),
            )
            await asyncio.sleep(interval_seconds)
            await refresh_channel_mapping()
        except Exception as refresh_error:
            monitor_metrics.record_failure("channel_refresh", error=str(refresh_error))
            print(f"[{datetime.datetime.now()}] channel refresh failed: {refresh_error}")


api_id, api_hash = get_api_credentials()
ensure_message_monitor_source_columns()
client = TelegramClient("tg_monitor_session", api_id, api_hash)
channel_usernames = get_channels()
channel_ids: List[int] = []
channel_info: Dict[str, Dict[str, Any]] = {}
channel_id_to_name: Dict[int, str] = {}
channel_signature = tuple(sorted(channel_usernames))


async def parse_message(
    text: str,
    msg_obj: Any = None,
    channel_name: str | None = None,
    channel_id: int | None = None,
) -> Dict[str, Any]:
    parsed_data, _ = await parse_message_content(
        text,
        msg_obj=msg_obj,
        channel_name=channel_name,
        channel_id=channel_id,
    )
    return parsed_data



def get_event_channel_id(event: Any) -> int | None:
    peer_id = getattr(getattr(event, "message", None), "peer_id", None)
    return getattr(peer_id, "channel_id", None) or getattr(peer_id, "chat_id", None)



def get_channel_name_by_id(chat_id: int | None) -> str | None:
    """根据聊天 ID 获取频道名称。"""
    if chat_id is None:
        return None
    return channel_id_to_name.get(chat_id)



def _to_local_telegram_time(telegram_time: datetime.datetime) -> datetime.datetime:
    if telegram_time.tzinfo is not None:
        return telegram_time.replace(tzinfo=None) + datetime.timedelta(hours=8)
    return telegram_time



def _append_local_log(path: Path, content: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as file_obj:
            file_obj.write(content)
    except Exception:
        pass


@client.on(events.NewMessage())
async def handler(event: Any) -> None:
    try:
        incoming_chat_id = get_event_channel_id(event)
        if incoming_chat_id is None or incoming_chat_id not in channel_ids:
            monitor_metrics.increment("messages_skipped_unmonitored")
            return

        chat = await event.get_chat()
        channel_name = get_channel_name_by_id(incoming_chat_id)
        if not channel_name:
            await refresh_channel_mapping(force=True)
            channel_name = get_channel_name_by_id(incoming_chat_id)
            if not channel_name:
                monitor_metrics.record_failure("channel_lookup", chat_id=incoming_chat_id)
                print(f"[DEBUG] 无法获取频道名称，ID: {incoming_chat_id}")
                return

        message_text = event.raw_text or ""
        telegram_local_time = _to_local_telegram_time(event.date)
        monitor_time = datetime.datetime.now()
        delay_seconds = (monitor_time - telegram_local_time).total_seconds()
        channel_runtime_info = channel_info.get(channel_name) or {}
        chat_title = getattr(chat, "title", None) or channel_runtime_info.get("title") or channel_name or "Unknown"

        print(
            f"[{monitor_time}] 收到来自 {chat_title}({channel_name}) 的新消息，开始解析... "
            f"(延迟: {delay_seconds:.1f}秒)"
        )

        try:
            parser_profile = (channel_info.get(channel_name) or {}).get("parser_profile")
            parsed_records, diagnostics = await parse_message_records(
                message_text,
                msg_obj=event.message,
                channel_name=channel_name,
                channel_id=incoming_chat_id,
                parser_profile=parser_profile,
            )
            parsed_records = [record for record in parsed_records if record.get("links")]
            monitor_metrics.record_parse(diagnostics, has_links=bool(parsed_records))
        except Exception as parse_error:
            monitor_metrics.record_failure("parse", channel=channel_name, error=str(parse_error))
            log_monitor_event(
                logger,
                "parse_error",
                level=logging.WARNING,
                channel=channel_name,
                chat_id=incoming_chat_id,
                error=str(parse_error),
            )
            print(f"[{monitor_time}] 消息解析失败: {parse_error}")
            print(f"[{monitor_time}] 原始消息: {message_text[:200]}...")
            _append_local_log(
                ERROR_MESSAGES_LOG,
                f"[{monitor_time}] parse_error={parse_error} channel={channel_name} message={message_text[:500]}\n",
            )
            return

        if not parsed_records:
            monitor_metrics.increment("messages_filtered_no_links")
            log_monitor_event(
                logger,
                "message_filtered",
                channel=channel_name,
                reason="no_netdisk_links",
                delay_seconds=f"{delay_seconds:.1f}",
                raw_url_count=diagnostics.raw_url_count,
                resolved_url_count=diagnostics.resolved_url_count,
                redirect_resolved_count=diagnostics.redirect_resolved_count,
                raw_url_samples="|".join(diagnostics.raw_url_samples),
                resolved_url_samples="|".join(diagnostics.resolved_url_samples),
            )
            print(f"[{monitor_time}] 过滤掉无网盘链接的消息")
            return

        saved_netdisk_types = sorted(
            {
                netdisk_type
                for record in parsed_records
                for netdisk_type in record.get("links", {}).keys()
            }
        )
        monitor_runtime_config = get_monitor_runtime_config()
        max_retries = max(1, int(monitor_runtime_config["monitor_db_write_max_retries"] or 3))
        retry_delay_seconds = float(monitor_runtime_config["monitor_db_write_retry_delay_seconds"] or 1.0)
        for attempt in range(max_retries):
            try:
                async with async_session() as session:
                    try:
                        created_messages: list[Message] = []
                        monitor_channel_config_id = channel_runtime_info.get("config_id")
                        monitor_chat_id = int(incoming_chat_id) if incoming_chat_id is not None else None
                        monitor_channel_key = str(channel_runtime_info.get("channel_key") or channel_name or "").strip() or None
                        monitor_channel_title = str(chat_title).strip() or None
                        monitor_message_id = getattr(event.message, "id", None)
                        for parsed_data in parsed_records:
                            new_message = Message(
                                timestamp=telegram_local_time,
                                monitor_channel_config_id=int(monitor_channel_config_id) if monitor_channel_config_id else None,
                                monitor_chat_id=monitor_chat_id,
                                monitor_channel_key=monitor_channel_key,
                                monitor_channel_title=monitor_channel_title,
                                monitor_message_id=int(monitor_message_id) if monitor_message_id is not None else None,
                                **parsed_data,
                                netdisk_types=list(parsed_data["links"].keys()),
                            )
                            session.add(new_message)
                            created_messages.append(new_message)
                        await session.flush()
                        new_message_ids = [
                            int(new_message.id)
                            for new_message in created_messages
                            if getattr(new_message, "id", None) is not None
                        ]
                        if new_message_ids:
                            try:
                                async with session.begin_nested():
                                    await session.run_sync(
                                        lambda sync_session: ensure_message_link_refs_for_message_ids(sync_session, new_message_ids)
                                    )
                            except Exception as resource_index_error:
                                log_monitor_event(
                                    logger,
                                    "resource_index_sync_failed",
                                    level=logging.WARNING,
                                    channel=channel_name,
                                    error=str(resource_index_error),
                                    affected_messages=len(new_message_ids),
                                )
                                print(
                                    f"[{monitor_time}] 资源索引即时同步失败，已保留消息入库，将由读取修复/手动补录兜底: "
                                    f"{resource_index_error}"
                                )
                        if new_message_ids:
                            try:
                                async with session.begin_nested():
                                    await session.run_sync(
                                        lambda sync_session: accumulate_channel_daily_stats_for_message_ids(
                                            sync_session,
                                            new_message_ids,
                                        )
                                    )
                            except Exception as channel_daily_stats_error:
                                log_monitor_event(
                                    logger,
                                    "channel_daily_stats_sync_failed",
                                    level=logging.WARNING,
                                    channel=channel_name,
                                    error=str(channel_daily_stats_error),
                                    affected_messages=len(new_message_ids),
                                )
                                print(
                                    f"[{monitor_time}] channel_daily_stats 鍚屾澶辫触锛屼絾涓嶄細褰卞搷娑堟伅鍏ュ簱: "
                                    f"{channel_daily_stats_error}"
                                )
                        await session.commit()
                    except Exception:
                        await session.rollback()
                        raise

                monitor_metrics.increment("messages_saved", len(parsed_records))
                log_monitor_event(
                    logger,
                    "message_saved",
                    channel=channel_name,
                    delay_seconds=f"{delay_seconds:.1f}",
                    netdisk_types=",".join(saved_netdisk_types),
                    saved_records=len(parsed_records),
                )
                print(
                    f"[{monitor_time}] 新消息已保存到数据库 "
                    f"(尝试 {attempt + 1}/{max_retries}, 共 {len(parsed_records)} 条, 延迟: {delay_seconds:.1f}秒)"
                )
                break
            except Exception as db_error:
                monitor_metrics.record_failure("db_write", channel=channel_name, error=str(db_error))
                log_monitor_event(
                    logger,
                    "db_write_retry",
                    level=logging.WARNING,
                    channel=channel_name,
                    attempt=attempt + 1,
                    error=str(db_error),
                )
                print(f"[{monitor_time}] 数据库写入失败 (尝试 {attempt + 1}/{max_retries}): {db_error}")
                if attempt == max_retries - 1:
                    print(f"[{monitor_time}] 数据库写入最终失败，消息丢失")
                    _append_local_log(
                        FAILED_MESSAGES_LOG,
                        f"[{monitor_time}] channel={channel_name} message={message_text}\n",
                    )
                else:
                    await asyncio.sleep(retry_delay_seconds)
    except Exception as exc:
        monitor_metrics.record_failure("handler", error=str(exc))
        log_monitor_event(logger, "handler_error", level=logging.WARNING, error=str(exc))
        print(f"[{datetime.datetime.now()}] 消息处理发生未知错误: {exc}")
        raw_text = getattr(event, "raw_text", "") or ""
        _append_local_log(
            ERROR_MESSAGES_LOG,
            f"[{datetime.datetime.now()}] error={exc} message={raw_text[:500]}\n",
        )


print(f"✅ 正在监听 Telegram 频道：{len(channel_usernames)} 个频道...")


@client.on(events.Raw)
async def connection_handler(event: Any) -> None:
    """监控连接状态。"""
    if hasattr(event, "connected"):
        if event.connected:
            print(f"[{datetime.datetime.now()}] ✅ Telegram连接已建立")
        else:
            print(f"[{datetime.datetime.now()}] ❌ Telegram连接已断开")


if __name__ == "__main__":
    try:
        client.start()
        print(f"[{datetime.datetime.now()}] ✅ 监控服务启动成功")

        loop = client.loop
        print("🔍 正在构建频道ID映射...")
        loop.run_until_complete(refresh_channel_mapping(force=True))
        loop.create_task(channel_refresh_loop())
        print(f"✅ 频道ID映射构建完成: {len(channel_ids)} 个频道")

        client.run_until_disconnected()
    except Exception as exc:
        print(f"[{datetime.datetime.now()}] ❌ 启动失败: {exc}")
        print("请先手动运行一次程序进行登录：python -m app.core.monitor")
        sys.exit(1)

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any, Iterable

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.models import (
    Channel,
    LearningChannelConfig,
    LearningResourceCategory,
    LearningResourceItem,
    LearningResourceItemCategory,
    LearningResourceLink,
    LearningResourceTransferJob,
    LinkTarget,
    Message,
    MessageLinkRef,
    PanTransferAccount,
    PanTransferBatch,
    PanTransferBatchItem,
    ensure_runtime_storage_tables,
)
from app.services.pan_transfer.common import normalize_relative_path, sanitize_path_segment, utcnow
from app.services.pan_transfer.constants import normalize_transfer_platform
from app.services.pan_transfer.queue import refresh_pan_transfer_batch_summary
from app.utils.channel_utils import normalize_channel_username


LEARNING_STATUS_PENDING = "pending"
LEARNING_STATUS_TRANSFERRING = "transferring"
LEARNING_STATUS_PUBLISHED = "published"
LEARNING_STATUS_FAILED = "failed"
LEARNING_JOB_QUEUED = "queued"
LEARNING_JOB_TRANSFERRING = "transferring"
LEARNING_JOB_PUBLISHED = "published"
LEARNING_JOB_FAILED = "failed"
LEARNING_JOB_PAUSED = "paused"

_URL_TAG_RE = re.compile(r"^(?:https?://|www\.|https?$)", re.IGNORECASE)
_SPACE_RE = re.compile(r"\s+")
_TITLE_NOISE_RE = re.compile(r"[\[\]【】()（）{}<>《》:：,，.!！?？/\\|_+−\-·•]+")


def normalize_learning_title(value: Any) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).strip().lower()
    normalized = _TITLE_NOISE_RE.sub(" ", normalized)
    normalized = _SPACE_RE.sub("", normalized)
    return normalized[:255] or "未命名资源"


def _display_title(message: Message) -> str:
    title = str(message.title or "").strip()
    if title:
        return title[:255]
    description = str(message.description or "").strip()
    return (description.splitlines()[0].strip() if description else "未命名资源")[:255]


def _clean_tag(value: Any) -> str:
    return str(value or "").strip().lstrip("#").strip()[:120]


def classify_learning_message(message: Message) -> dict[str, Any]:
    """Return an explainable top-level category for a learning resource."""
    title = _display_title(message)
    title_lower = title.lower()

    for raw_tag in list(message.tags or []):
        tag = _clean_tag(raw_tag)
        if not tag or _URL_TAG_RE.match(tag):
            continue
        if "国考" in tag or "省考" in tag:
            return {"name": "国省考", "source": "tag", "confidence": "high"}
        if any(token in tag for token in ("人教版", "小学", "初中", "高中", "小初高")):
            return {"name": "小初高", "source": "tag", "confidence": "high"}
        if tag in {"浙江", "讲义"}:
            continue
        if any(token in tag for token in ("教师", "教资", "师范")):
            return {"name": "教师类", "source": "tag", "confidence": "high"}
        return {"name": tag, "source": "tag", "confidence": "medium"}

    title_rules = (
        (("教师资格", "教资", "教师招聘", "特岗教师", "教师编", "教招"), "教师类"),
        (("国考", "省考", "公务员", "行测", "申论"), "国省考"),
        (("考研", "研究生", "考研英语", "考研数学", "考研政治"), "考研"),
        (("小学", "初中", "高中", "中考", "高考", "人教版", "高中物理", "讲义"), "小初高"),
        (("四六级", "英语四级", "英语六级"), "英语考试"),
        (("计算机", "编程", "python", "java", "前端", "后端"), "计算机"),
    )
    for tokens, category in title_rules:
        if any(token.lower() in title_lower for token in tokens):
            return {"name": category, "source": "title_rule", "confidence": "medium"}
    return {"name": "待分类", "source": "fallback", "confidence": "low"}


def _category_slug(name: str) -> str:
    slug = re.sub(r"[^\w\u4e00-\u9fff]+", "-", name.strip().lower()).strip("-")
    return (slug or "uncategorized")[:160]


def _get_or_create_category(
    session: Session,
    *,
    name: str,
    operator: str | None,
) -> LearningResourceCategory:
    slug = _category_slug(name)
    category = session.query(LearningResourceCategory).filter(LearningResourceCategory.slug == slug).first()
    if category is None:
        category = LearningResourceCategory(
            name=name[:120],
            slug=slug,
            directory_name=sanitize_path_segment(name, fallback="待分类", max_length=96),
            directory_status="pending",
            created_by=operator,
            updated_by=operator,
        )
        session.add(category)
        session.flush()
    return category


def get_learning_channel_config(session: Session, channel_key: str) -> LearningChannelConfig | None:
    normalized = normalize_channel_username(channel_key)
    return (
        session.query(LearningChannelConfig)
        .filter(LearningChannelConfig.channel_key == normalized)
        .first()
    )


def is_learning_channel_enabled(session: Session, channel_key: str) -> bool:
    config = get_learning_channel_config(session, channel_key)
    return bool(config and config.is_enabled)


def _resolve_learning_account(
    session: Session,
    *,
    config: LearningChannelConfig,
) -> PanTransferAccount | None:
    account = session.get(PanTransferAccount, int(config.target_account_id)) if config.target_account_id else None
    if account is None:
        account = (
            session.query(PanTransferAccount)
            .filter(
                PanTransferAccount.platform == "quark",
                PanTransferAccount.is_enabled.is_(True),
            )
            .order_by(PanTransferAccount.is_default.desc(), PanTransferAccount.id.asc())
            .first()
        )
    if account is None or not bool(account.is_enabled):
        return None
    try:
        return account if normalize_transfer_platform(str(account.platform or "")) == "quark" else None
    except ValueError:
        return None


def _resource_category_link(
    session: Session,
    *,
    resource_id: int,
    category_id: int,
) -> LearningResourceItemCategory:
    row = (
        session.query(LearningResourceItemCategory)
        .filter(
            LearningResourceItemCategory.resource_id == resource_id,
            LearningResourceItemCategory.category_id == category_id,
        )
        .first()
    )
    if row is None:
        row = LearningResourceItemCategory(
            resource_id=resource_id,
            category_id=category_id,
            is_primary=True,
        )
        session.add(row)
    else:
        row.is_primary = True
    session.flush()
    return row


def _build_learning_paths(
    *,
    account: PanTransferAccount,
    config: LearningChannelConfig,
    category: LearningResourceCategory,
    title: str,
) -> dict[str, str | None]:
    root = normalize_relative_path(str(config.save_root or account.default_save_root or ""))
    category_root = normalize_relative_path("/".join(part for part in (root, category.directory_name) if part))
    folder_name = sanitize_path_segment(title, fallback="未命名资源", max_length=96)
    return {
        "staging_root": category_root,
        "staging_folder_name": folder_name,
        "resolved_path": normalize_relative_path("/".join(part for part in (category_root, folder_name) if part)),
        "transfer_layout": "independent",
        "batch_folder_name": None,
        "share_target_mode": "resource_dir",
    }


def _source_fingerprint(target: LinkTarget) -> str:
    value = str(target.normalized_url_hash or target.normalized_url or target.original_url or "").strip()
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _find_quark_refs(session: Session, message_id: int) -> list[tuple[MessageLinkRef, LinkTarget]]:
    rows = (
        session.query(MessageLinkRef, LinkTarget)
        .join(LinkTarget, LinkTarget.id == MessageLinkRef.link_target_id)
        .filter(MessageLinkRef.message_id == int(message_id))
        .order_by(MessageLinkRef.link_index.asc(), MessageLinkRef.id.asc())
        .all()
    )
    result: list[tuple[MessageLinkRef, LinkTarget]] = []
    for ref, target in rows:
        try:
            if normalize_transfer_platform(str(target.platform or ref.provider_label or "")) != "quark":
                continue
        except ValueError:
            continue
        result.append((ref, target))
    return result


def _create_learning_batch(
    session: Session,
    *,
    config: LearningChannelConfig,
    jobs: list[tuple[LearningResourceTransferJob, LearningResourceItem, LearningResourceCategory, PanTransferAccount, LinkTarget, Message]],
) -> PanTransferBatch:
    batch = PanTransferBatch(
        batch_type="learning_resources",
        source_scope="learning_channel",
        status="running",
        created_by="tg-monitor",
        total_message_count=len({int(job.source_message_id) for job, *_ in jobs}),
        total_link_target_count=len(jobs),
        started_at=utcnow(),
        request_json={
            "channel_key": str(config.channel_key or ""),
            "target_account_id": int(jobs[0][3].id),
            "save_root": str(config.save_root or jobs[0][3].default_save_root or ""),
            "category_ids": sorted({int(category.id) for _, _, category, *_ in jobs}),
        },
        result_json={},
    )
    session.add(batch)
    session.flush()

    for job, resource, category, account, target, message in jobs:
        item = PanTransferBatchItem(
            batch_id=int(batch.id),
            link_target_id=int(target.id),
            target_account_id=int(account.id),
            platform="quark",
            short_title=resource.display_title,
            original_url=str(target.original_url or ""),
            source_message_count=1,
            source_ref_count=1,
            latest_message_title=resource.display_title,
            latest_message_time=message.timestamp,
            latest_link_health="unknown",
            transfer_status="queued",
            share_status="pending",
            validation_status="pending",
            replacement_status="replaced",
            max_attempts=3,
            extra_json={
                "learning_resource_job_id": int(job.id),
                "learning_channel_key": str(config.channel_key or ""),
                "skip_link_replacement": True,
                "source_message_snapshot": {
                    "title": resource.display_title,
                    "description": str(message.description or ""),
                    "tags": list(message.tags or []),
                },
                "resolved_paths": _build_learning_paths(
                    account=account,
                    config=config,
                    category=category,
                    title=resource.display_title,
                ),
                "path_strategy": {
                    "transfer_layout": "independent",
                    "item_folder_mode": "original",
                    "share_target_mode": "resource_dir",
                },
            },
        )
        session.add(item)
        session.flush()
        job.batch_id = int(batch.id)
        job.batch_item_id = int(item.id)
        job.status = LEARNING_JOB_QUEUED
        resource.status = LEARNING_STATUS_TRANSFERRING
        session.add_all([job, resource])
    session.flush()
    refresh_pan_transfer_batch_summary(session, batch_id=int(batch.id))
    return batch


def enqueue_learning_resources_for_message_ids(
    session: Session,
    message_ids: Iterable[int],
    *,
    operator: str = "tg-monitor",
) -> dict[str, int]:
    ensure_runtime_storage_tables()
    normalized_ids = sorted({int(message_id) for message_id in message_ids if int(message_id) > 0})
    if not normalized_ids:
        return {"messages": 0, "resources": 0, "jobs": 0, "skipped": 0}

    messages = session.query(Message).filter(Message.id.in_(normalized_ids)).all()
    jobs_by_channel: dict[str, list[tuple[LearningResourceTransferJob, LearningResourceItem, LearningResourceCategory, PanTransferAccount, LinkTarget, Message]]] = {}
    processed_messages = 0
    skipped = 0
    configs_by_key: dict[str, LearningChannelConfig | None] = {}

    for message in messages:
        channel_key = str(message.monitor_channel_key or "").strip()
        if not channel_key:
            skipped += 1
            continue
        try:
            channel_key = normalize_channel_username(channel_key)
        except ValueError:
            skipped += 1
            continue
        if channel_key not in configs_by_key:
            configs_by_key[channel_key] = get_learning_channel_config(session, channel_key)
        config = configs_by_key[channel_key]
        if config is None or not bool(config.is_enabled):
            skipped += 1
            continue
        account = _resolve_learning_account(session, config=config)
        root = normalize_relative_path(str(config.save_root or (account.default_save_root if account else "") or ""))
        if account is None or not root:
            config.last_error_message = "学习资料自动转存未配置可用的夸克账号或保存根目录"
            session.add(config)
            skipped += 1
            continue

        quark_refs = _find_quark_refs(session, int(message.id))
        if not quark_refs:
            skipped += 1
            continue
        processed_messages += 1
        title = _display_title(message)
        normalized_title = normalize_learning_title(title)
        classification = classify_learning_message(message)
        category = _get_or_create_category(
            session,
            name=str(classification["name"]),
            operator=operator,
        )
        resource = (
            session.query(LearningResourceItem)
            .filter(
                LearningResourceItem.source_channel_key == channel_key,
                LearningResourceItem.normalized_title == normalized_title,
            )
            .first()
        )
        source_at = message.timestamp or message.created_at or utcnow()
        if resource is None:
            resource = LearningResourceItem(
                display_title=title,
                normalized_title=normalized_title,
                status=LEARNING_STATUS_PENDING,
                primary_category_id=int(category.id),
                source_channel_key=channel_key,
                first_source_message_id=int(message.id),
                latest_source_message_id=int(message.id),
                latest_source_at=source_at,
                classification_source=str(classification["source"]),
                classification_confidence=str(classification["confidence"]),
                created_by=operator,
                updated_by=operator,
            )
            session.add(resource)
            session.flush()
        elif resource.latest_source_at is None or source_at >= resource.latest_source_at:
            resource.display_title = title
            resource.latest_source_message_id = int(message.id)
            resource.latest_source_at = source_at
            resource.primary_category_id = int(category.id)
            resource.classification_source = str(classification["source"])
            resource.classification_confidence = str(classification["confidence"])
            resource.updated_by = operator
            session.add(resource)
        _resource_category_link(
            session,
            resource_id=int(resource.id),
            category_id=int(category.id),
        )

        for ref, target in quark_refs:
            fingerprint = _source_fingerprint(target)
            link = (
                session.query(LearningResourceLink)
                .filter(
                    LearningResourceLink.resource_id == int(resource.id),
                    LearningResourceLink.url_fingerprint == fingerprint,
                )
                .first()
            )
            if link is not None and link.status == "published" and link.share_url:
                continue
            published_link = (
                session.query(LearningResourceLink)
                .filter(
                    LearningResourceLink.resource_id == int(resource.id),
                    LearningResourceLink.id != int(link.id) if link is not None else True,
                    LearningResourceLink.is_primary.is_(True),
                    LearningResourceLink.status == "published",
                    LearningResourceLink.share_url.isnot(None),
                )
                .first()
            )
            if link is None:
                link = LearningResourceLink(
                    resource_id=int(resource.id),
                    platform="quark",
                    source_url=str(target.original_url or ref.target_url or ""),
                    url_fingerprint=fingerprint,
                    target_account_id=int(account.id),
                    source_link_target_id=int(target.id),
                    is_primary=published_link is None,
                    is_enabled=True,
                    status="pending",
                )
                session.add(link)
                session.flush()
            else:
                link.target_account_id = int(account.id)
                link.is_enabled = True
                link.status = "pending"
                link.last_error_message = None
                session.add(link)
            job = (
                session.query(LearningResourceTransferJob)
                .filter(
                    LearningResourceTransferJob.resource_id == int(resource.id),
                    LearningResourceTransferJob.source_link_target_id == int(target.id),
                )
                .first()
            )
            if job is not None and job.status in {LEARNING_JOB_QUEUED, LEARNING_JOB_TRANSFERRING}:
                continue
            if job is None:
                job = LearningResourceTransferJob(
                    resource_id=int(resource.id),
                    source_message_id=int(message.id),
                    source_link_target_id=int(target.id),
                    target_account_id=int(account.id),
                    category_id=int(category.id),
                    status=LEARNING_JOB_QUEUED,
                )
                session.add(job)
                session.flush()
            else:
                job.source_message_id = int(message.id)
                job.target_account_id = int(account.id)
                job.category_id = int(category.id)
                job.status = LEARNING_JOB_QUEUED
                job.last_error_message = None
                session.add(job)
            jobs_by_channel.setdefault(channel_key, []).append((job, resource, category, account, target, message))
            if published_link is None and resource.status != LEARNING_STATUS_HIDDEN:
                resource.status = LEARNING_STATUS_TRANSFERRING
            session.add(resource)

        config.last_processed_message_id = max(int(config.last_processed_message_id or 0), int(message.id))
        session.add(config)

    for channel_key, jobs in jobs_by_channel.items():
        if jobs:
            _create_learning_batch(session, config=configs_by_key[channel_key], jobs=jobs)
    return {
        "messages": processed_messages,
        "resources": len({int(job[1].id) for jobs in jobs_by_channel.values() for job in jobs}),
        "jobs": sum(len(jobs) for jobs in jobs_by_channel.values()),
        "skipped": skipped,
    }


def sync_learning_resource_after_transfer(
    session: Session,
    *,
    item: PanTransferBatchItem,
    success: bool,
    error_message: str | None = None,
) -> None:
    job_id = dict(item.extra_json or {}).get("learning_resource_job_id")
    if not job_id:
        return
    job = session.get(LearningResourceTransferJob, int(job_id))
    if job is None:
        return
    resource = session.get(LearningResourceItem, int(job.resource_id))
    link = (
        session.query(LearningResourceLink)
        .filter(
            LearningResourceLink.resource_id == int(job.resource_id),
            LearningResourceLink.source_link_target_id == int(job.source_link_target_id),
        )
        .first()
    )
    if success:
        job.status = LEARNING_JOB_PUBLISHED
        job.attempt_count = max(1, int(job.attempt_count or 0) + 1)
        job.last_error_message = None
        if link is not None:
            link.share_url = str(item.new_share_url or "") or None
            link.status = "published" if link.share_url else "failed"
            link.is_enabled = bool(link.share_url)
            link.is_primary = bool(link.share_url)
            link.last_error_message = None if link.share_url else "转存完成但未生成分享链接"
            session.add(link)
            if link.share_url:
                session.query(LearningResourceLink).filter(
                    LearningResourceLink.resource_id == int(job.resource_id),
                    LearningResourceLink.id != int(link.id),
                ).update({"is_primary": False, "is_enabled": False}, synchronize_session=False)
        if resource is not None:
            resource.status = LEARNING_STATUS_PUBLISHED if link is not None and link.share_url else LEARNING_STATUS_FAILED
            if resource.status == LEARNING_STATUS_PUBLISHED:
                resource.last_published_at = utcnow()
            resource.updated_by = "tg-worker"
            session.add(resource)
        job.status = LEARNING_JOB_PUBLISHED if resource is None or resource.status == LEARNING_STATUS_PUBLISHED else LEARNING_JOB_FAILED
    else:
        retry_waiting = str(item.transfer_status or "") == "retry_wait"
        job.status = LEARNING_JOB_QUEUED if retry_waiting else LEARNING_JOB_FAILED
        job.attempt_count = max(1, int(job.attempt_count or 0) + 1)
        job.last_error_message = str(error_message or "学习资料转存失败")[:2000]
        if link is not None:
            link.status = "failed"
            link.last_error_message = job.last_error_message
            session.add(link)
        if resource is not None and not retry_waiting:
            fallback_link = (
                session.query(LearningResourceLink)
                .filter(
                    LearningResourceLink.resource_id == int(resource.id),
                    LearningResourceLink.id != int(link.id) if link is not None else True,
                    LearningResourceLink.is_primary.is_(True),
                    LearningResourceLink.is_enabled.is_(True),
                    LearningResourceLink.status == "published",
                    LearningResourceLink.share_url.isnot(None),
                )
                .first()
            )
            resource.status = LEARNING_STATUS_PUBLISHED if fallback_link is not None else LEARNING_STATUS_FAILED
            resource.updated_by = "tg-worker"
            session.add(resource)
    session.add(job)
    session.flush()


def retry_learning_resource(session: Session, resource_id: int) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    resource = session.get(LearningResourceItem, int(resource_id))
    if resource is None:
        raise LookupError("学习资料不存在")
    job = (
        session.query(LearningResourceTransferJob)
        .filter(LearningResourceTransferJob.resource_id == int(resource.id))
        .order_by(LearningResourceTransferJob.id.desc())
        .first()
    )
    if job is None or not job.batch_item_id:
        raise ValueError("该资源没有可重试的转存任务")
    item = session.get(PanTransferBatchItem, int(job.batch_item_id))
    if item is None:
        raise ValueError("转存任务条目不存在")
    item.transfer_status = "queued"
    item.next_retry_at = None
    item.locked_by = None
    item.locked_at = None
    item.started_at = None
    item.finished_at = None
    item.error_message = None
    item.share_status = "shared" if item.new_share_url else "pending"
    item.validation_status = "pending"
    item.replacement_status = "replaced" if dict(item.extra_json or {}).get("skip_link_replacement") else "pending"
    session.add(item)
    batch = session.get(PanTransferBatch, int(item.batch_id))
    if batch is not None:
        batch.status = "running"
        batch.finished_at = None
        batch.started_at = batch.started_at or utcnow()
        session.add(batch)
    job.status = LEARNING_JOB_QUEUED
    job.last_error_message = None
    resource.status = LEARNING_STATUS_TRANSFERRING
    session.add_all([job, resource])
    session.flush()
    refresh_pan_transfer_batch_summary(session, batch_id=int(item.batch_id))
    return {"resource_id": int(resource.id), "job_id": int(job.id), "status": str(job.status)}


def pause_learning_channel_tasks(session: Session, channel_key: str) -> int:
    normalized = normalize_channel_username(channel_key)
    resource_ids = [
        int(value)
        for (value,) in session.query(LearningResourceItem.id)
        .filter(LearningResourceItem.source_channel_key == normalized)
        .all()
    ]
    if not resource_ids:
        return 0
    jobs = session.query(LearningResourceTransferJob).filter(
        LearningResourceTransferJob.resource_id.in_(resource_ids),
        LearningResourceTransferJob.status.in_([LEARNING_JOB_QUEUED, LEARNING_JOB_TRANSFERRING]),
    ).all()
    for job in jobs:
        if job.batch_item_id:
            item = session.get(PanTransferBatchItem, int(job.batch_item_id))
            if item is not None and item.transfer_status == "queued":
                item.transfer_status = "paused"
                session.add(item)
        job.status = LEARNING_JOB_PAUSED
        session.add(job)
    session.flush()
    return len(jobs)


def resume_learning_channel_tasks(session: Session, channel_key: str) -> int:
    normalized = normalize_channel_username(channel_key)
    resource_ids = [
        int(value)
        for (value,) in session.query(LearningResourceItem.id)
        .filter(LearningResourceItem.source_channel_key == normalized)
        .all()
    ]
    if not resource_ids:
        return 0
    jobs = session.query(LearningResourceTransferJob).filter(
        LearningResourceTransferJob.resource_id.in_(resource_ids),
        LearningResourceTransferJob.status == LEARNING_JOB_PAUSED,
    ).all()
    for job in jobs:
        if job.batch_item_id:
            item = session.get(PanTransferBatchItem, int(job.batch_item_id))
            if item is not None and item.transfer_status == "paused":
                item.transfer_status = "queued"
                session.add(item)
        job.status = LEARNING_JOB_QUEUED
        session.add(job)
    session.flush()
    return len(jobs)


def list_public_learning_categories(session: Session) -> list[dict[str, Any]]:
    ensure_runtime_storage_tables()
    rows = (
        session.query(LearningResourceCategory)
        .join(LearningResourceItemCategory, LearningResourceItemCategory.category_id == LearningResourceCategory.id)
        .join(LearningResourceItem, LearningResourceItem.id == LearningResourceItemCategory.resource_id)
        .filter(
            LearningResourceCategory.is_enabled.is_(True),
            LearningResourceCategory.show_in_tabs.is_(True),
            LearningResourceItem.status == LEARNING_STATUS_PUBLISHED,
        )
        .distinct()
        .order_by(LearningResourceCategory.sort_order.asc(), LearningResourceCategory.id.asc())
        .all()
    )
    return [
        {
            "id": int(row.id),
            "name": str(row.name or ""),
            "slug": str(row.slug or ""),
            "sort_order": int(row.sort_order or 0),
            "resource_count": int(
                session.query(LearningResourceItemCategory)
                .join(LearningResourceItem, LearningResourceItem.id == LearningResourceItemCategory.resource_id)
                .filter(
                    LearningResourceItemCategory.category_id == int(row.id),
                    LearningResourceItem.status == LEARNING_STATUS_PUBLISHED,
                )
                .count()
            ),
        }
        for row in rows
    ]


def list_public_learning_resources(
    session: Session,
    *,
    category_slug: str | None = None,
    search: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    ensure_runtime_storage_tables()
    query = (
        session.query(LearningResourceItem, LearningResourceCategory, LearningResourceLink, Message)
        .join(LearningResourceCategory, LearningResourceCategory.id == LearningResourceItem.primary_category_id, isouter=True)
        .join(
            LearningResourceLink,
            (LearningResourceLink.resource_id == LearningResourceItem.id)
            & LearningResourceLink.is_primary.is_(True)
            & LearningResourceLink.is_enabled.is_(True)
            & (LearningResourceLink.status == "published")
            & LearningResourceLink.share_url.isnot(None),
        )
        .join(Message, Message.id == LearningResourceItem.latest_source_message_id, isouter=True)
        .filter(LearningResourceItem.status == LEARNING_STATUS_PUBLISHED)
    )
    if category_slug and category_slug not in {"all", ""}:
        query = query.filter(LearningResourceCategory.slug == str(category_slug).strip())
    if search and search.strip():
        keyword = f"%{search.strip()}%"
        query = query.filter(
            or_(LearningResourceItem.display_title.ilike(keyword), LearningResourceItem.normalized_title.ilike(keyword))
        )
    rows = query.order_by(
        LearningResourceItem.latest_source_at.desc().nullslast(),
        LearningResourceItem.updated_at.desc(),
        LearningResourceItem.id.desc(),
    ).limit(max(1, min(int(limit or 200), 500))).all()
    return [
        {
            "id": int(item.id),
            "display_title": str(item.display_title or ""),
            "category": {
                "id": int(category.id),
                "name": str(category.name or ""),
                "slug": str(category.slug or ""),
            }
            if category is not None
            else None,
            "tags": [str(tag).strip() for tag in list(message.tags or []) if str(tag).strip()] if message else [],
            "share_url": str(link.share_url or ""),
            "platform": str(link.platform or "quark"),
            "updated_at": item.latest_source_at or item.updated_at,
            "created_at": item.created_at,
        }
        for item, category, link, message in rows
    ]


def list_admin_learning_items(session: Session, *, search: str | None = None, limit: int = 300) -> list[dict[str, Any]]:
    ensure_runtime_storage_tables()
    query = session.query(LearningResourceItem).order_by(
        LearningResourceItem.latest_source_at.desc().nullslast(),
        LearningResourceItem.id.desc(),
    )
    if search and search.strip():
        query = query.filter(LearningResourceItem.display_title.ilike(f"%{search.strip()}%"))
    rows = query.limit(max(1, min(int(limit or 300), 500))).all()
    result: list[dict[str, Any]] = []
    for row in rows:
        category = session.get(LearningResourceCategory, row.primary_category_id) if row.primary_category_id else None
        link = (
            session.query(LearningResourceLink)
            .filter(
                LearningResourceLink.resource_id == int(row.id),
                LearningResourceLink.is_primary.is_(True),
            )
            .order_by(LearningResourceLink.id.desc())
            .first()
        )
        result.append({
            "id": int(row.id),
            "display_title": str(row.display_title or ""),
            "status": str(row.status or ""),
            "category": {"id": int(category.id), "name": str(category.name or ""), "slug": str(category.slug or "")} if category else None,
            "share_url": str(link.share_url or "") if link else None,
            "latest_source_at": row.latest_source_at,
            "updated_at": row.updated_at,
        })
    return result


def list_learning_admin_overview(session: Session) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    configs = {str(row.channel_key): row for row in session.query(LearningChannelConfig).all()}
    channels = []
    for channel in session.query(Channel).order_by(Channel.id.asc()).all():
        try:
            key = normalize_channel_username(channel.username)
        except ValueError:
            key = str(channel.username or "").strip()
        if not key:
            continue
        config = configs.get(key)
        channels.append({
            "channel_id": int(channel.id),
            "channel_key": key,
            "channel_title": str((config.channel_title if config else None) or key),
            "config_id": int(config.id) if config else None,
            "is_enabled": bool(config.is_enabled) if config else False,
            "target_account_id": int(config.target_account_id) if config and config.target_account_id else None,
            "save_root": str(config.save_root or "") if config else "",
            "backfill_policy": str(config.backfill_policy or "new_messages_only") if config else "new_messages_only",
            "last_processed_message_id": int(config.last_processed_message_id) if config and config.last_processed_message_id else None,
            "last_error_message": str(config.last_error_message or "") if config else None,
        })
    accounts = [
        {
            "id": int(row.id),
            "platform": str(row.platform or ""),
            "account_name": str(row.account_name or ""),
            "default_save_root": str(row.default_save_root or ""),
            "is_enabled": bool(row.is_enabled),
        }
        for row in session.query(PanTransferAccount)
        .filter(PanTransferAccount.platform == "quark")
        .order_by(PanTransferAccount.is_default.desc(), PanTransferAccount.id.asc())
        .all()
    ]
    categories = [
        {
            "id": int(row.id),
            "name": str(row.name or ""),
            "slug": str(row.slug or ""),
            "directory_name": str(row.directory_name or ""),
            "is_enabled": bool(row.is_enabled),
            "show_in_tabs": bool(row.show_in_tabs),
            "sort_order": int(row.sort_order or 0),
        }
        for row in session.query(LearningResourceCategory)
        .order_by(LearningResourceCategory.sort_order.asc(), LearningResourceCategory.id.asc())
        .all()
    ]
    return {"channels": channels, "accounts": accounts, "categories": categories}


def update_learning_channel_config(
    session: Session,
    *,
    channel_id: int,
    payload: dict[str, Any],
    operator: str,
) -> dict[str, Any]:
    ensure_runtime_storage_tables()
    channel = session.get(Channel, int(channel_id))
    if channel is None:
        raise LookupError("监听频道不存在")
    channel_key = normalize_channel_username(channel.username)
    config = get_learning_channel_config(session, channel_key)
    if config is None:
        config = LearningChannelConfig(channel_key=channel_key, created_by=operator)
        session.add(config)
        session.flush()
    account_id = payload.get("target_account_id")
    if account_id is not None:
        account = session.get(PanTransferAccount, int(account_id))
        if account is None or not bool(account.is_enabled) or str(account.platform or "") != "quark":
            raise ValueError("必须选择已启用的夸克网盘账号")
        config.target_account_id = int(account.id)
    elif config.target_account_id is None:
        account = _resolve_learning_account(session, config=config)
        if account is not None:
            config.target_account_id = int(account.id)
    if "save_root" in payload and payload.get("save_root") is not None:
        config.save_root = normalize_relative_path(str(payload.get("save_root") or ""))
    if "is_enabled" in payload:
        config.is_enabled = bool(payload.get("is_enabled"))
    if config.is_enabled:
        account = _resolve_learning_account(session, config=config)
        if account is None:
            raise ValueError("开启前必须配置已启用的夸克网盘账号")
        if not normalize_relative_path(str(config.save_root or account.default_save_root or "")):
            raise ValueError("开启前必须配置保存根目录")
    config.channel_title = str(payload.get("channel_title") or channel.username)[:255]
    config.backfill_policy = "new_messages_only"
    config.transfer_policy = "quark_only"
    config.auto_create_category_dirs = True
    config.updated_by = operator
    config.last_error_message = None
    session.add(config)
    if not config.is_enabled:
        pause_learning_channel_tasks(session, channel_key)
    else:
        resume_learning_channel_tasks(session, channel_key)
    session.flush()
    return {
        "channel_id": int(channel.id),
        "channel_key": channel_key,
        "config_id": int(config.id),
        "is_enabled": bool(config.is_enabled),
        "target_account_id": int(config.target_account_id) if config.target_account_id else None,
        "save_root": str(config.save_root or ""),
    }


__all__ = [
    "classify_learning_message",
    "enqueue_learning_resources_for_message_ids",
    "get_learning_channel_config",
    "is_learning_channel_enabled",
    "list_admin_learning_items",
    "list_learning_admin_overview",
    "list_public_learning_categories",
    "list_public_learning_resources",
    "pause_learning_channel_tasks",
    "resume_learning_channel_tasks",
    "retry_learning_resource",
    "sync_learning_resource_after_transfer",
    "update_learning_channel_config",
]

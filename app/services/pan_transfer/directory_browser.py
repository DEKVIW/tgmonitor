from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.models import PanTransferAccount
from app.services.link_check.constants import PLATFORM_QUARK

from .constants import normalize_transfer_platform
from .providers import decrypt_account_credential, get_pan_transfer_provider


async def list_pan_transfer_directories(
    session: Session,
    *,
    account_id: int,
    parent_id: str = "0",
) -> list[dict[str, Any]]:
    account = session.get(PanTransferAccount, int(account_id))
    if account is None:
        raise LookupError("网盘账号不存在")
    if not bool(account.is_enabled):
        raise ValueError("网盘账号已停用")
    platform = normalize_transfer_platform(str(account.platform or ""))
    if platform != PLATFORM_QUARK:
        raise ValueError("当前目录选择器只支持夸克网盘")
    provider = get_pan_transfer_provider(platform)
    directories = await provider.list_directories(
        credential_value=decrypt_account_credential(account),
        parent_id=str(parent_id or "0"),
    )
    return sorted(directories, key=lambda item: str(item.get("name") or "").lower())


__all__ = ["list_pan_transfer_directories"]

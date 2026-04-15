from __future__ import annotations

from app.models.models import PanTransferAccount
from app.services.secret_codec import decrypt_secret

from ..constants import SUPPORTED_TRANSFER_PLATFORMS
from .baidu import BaiduPanTransferProvider
from .base import (
    PanTransferAccountValidationResult,
    PanTransferDeleteResult,
    PanTransferProvider,
    PanTransferProviderError,
    PanTransferShareResult,
    PanTransferTransferResult,
)
from .quark import QuarkPanTransferProvider


_PROVIDERS: dict[str, PanTransferProvider] = {
    provider.platform: provider
    for provider in (
        BaiduPanTransferProvider(),
        QuarkPanTransferProvider(),
    )
}


def get_pan_transfer_provider(platform: str) -> PanTransferProvider:
    provider = _PROVIDERS.get(str(platform or "").strip())
    if provider is None:
        raise ValueError(f"unsupported transfer platform: {platform}")
    return provider


def decrypt_account_credential(account: PanTransferAccount) -> str:
    return decrypt_secret(
        str(account.credential_encrypted or ""),
        error_message=f"Unable to decrypt credential for account {account.account_name}",
    )


__all__ = [
    "PanTransferAccountValidationResult",
    "PanTransferDeleteResult",
    "PanTransferProvider",
    "PanTransferProviderError",
    "PanTransferShareResult",
    "PanTransferTransferResult",
    "SUPPORTED_TRANSFER_PLATFORMS",
    "decrypt_account_credential",
    "get_pan_transfer_provider",
]

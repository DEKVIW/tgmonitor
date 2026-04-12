from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class PanTransferProviderError(Exception):
    message: str
    retryable: bool = True
    payload: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message


@dataclass(slots=True)
class PanTransferAccountValidationResult:
    ok: bool
    detail_message: str
    remote_user: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PanTransferExecutionResult:
    new_share_url: str
    share_title: str | None = None
    share_passcode: str | None = None
    staging_root: str | None = None
    staging_folder_name: str | None = None
    staging_folder_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


class PanTransferProvider:
    platform: str = ""

    async def validate_account(self, *, credential_value: str, account_name: str) -> PanTransferAccountValidationResult:
        raise NotImplementedError

    async def transfer_and_share(
        self,
        *,
        credential_value: str,
        account_name: str,
        original_url: str,
        original_passcode: str | None,
        staging_root: str,
        staging_folder_name: str,
        share_mode: str,
        share_passcode: str | None,
        share_expire_days: int | None,
        title_hint: str | None,
    ) -> PanTransferExecutionResult:
        raise NotImplementedError

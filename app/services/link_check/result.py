from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

STATUS_VALID = "valid"
STATUS_INVALID = "invalid"
STATUS_UNCERTAIN = "uncertain"
STATUS_RATE_LIMITED = "rate_limited"
STATUS_FORMAT_ERROR = "format_error"
STATUS_UNSUPPORTED = "unsupported"
STATUS_REQUIRES_CODE = "requires_code"

CONSERVATIVE_VALID_STATUSES = {
    STATUS_VALID,
    STATUS_UNCERTAIN,
    STATUS_RATE_LIMITED,
    STATUS_REQUIRES_CODE,
}
RETRYABLE_STATUSES = {STATUS_UNCERTAIN}

REASON_VALID = "链接有效"
REASON_INVALID = "网盘链接失效"
REASON_TIMEOUT = "网络超时"
REASON_NETWORK = "网络错误"
REASON_HTTP = "状态码错误"
REASON_EXCEPTION = "检测异常"
REASON_FORMAT = "格式错误"
REASON_LIMIT = "网盘限制"
REASON_REQUIRES_CODE = "需要提取码"
REASON_UNSUPPORTED = "暂不支持检测"


@dataclass(frozen=True, slots=True)
class LinkTarget:
    original_url: str
    resolved_url: str
    netdisk_type: str


@dataclass(slots=True)
class LinkCheckResult:
    url: str
    netdisk_type: str
    is_valid: bool
    status: str
    response_time: Optional[float] = None
    status_code: Optional[int] = None
    error: Optional[str] = None
    reason: Optional[str] = None
    resolved_url: Optional[str] = None
    checker: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)

    def clone_for_input(self, url: str) -> "LinkCheckResult":
        return LinkCheckResult(
            url=url,
            netdisk_type=self.netdisk_type,
            is_valid=self.is_valid,
            status=self.status,
            response_time=self.response_time,
            status_code=self.status_code,
            error=self.error,
            reason=self.reason,
            resolved_url=self.resolved_url,
            checker=self.checker,
            meta=dict(self.meta),
        )

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "url": self.url,
            "netdisk_type": self.netdisk_type,
            "is_valid": self.is_valid,
            "status": self.status,
            "status_code": self.status_code,
            "response_time": self.response_time,
            "error": self.error,
            "reason": self.reason,
            "resolved_url": self.resolved_url,
            "checker": self.checker,
        }
        if self.meta:
            payload["meta"] = dict(self.meta)
        return payload

from __future__ import annotations

import json
import os
import unittest

os.environ.setdefault("TELEGRAM_API_ID", "1")
os.environ.setdefault("TELEGRAM_API_HASH", "hash")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/testdb")
os.environ.setdefault("DEFAULT_CHANNELS", "")
os.environ.setdefault("SECRET_SALT", "test-salt")

from app.core.monitor_parser import parse_message_content
from app.services.link_check.checkers.cmcc import CMCCChecker, _encrypt_payload
from app.services.link_check.checkers.uc import UCChecker
from app.services.link_check.checkers.xunlei import XunleiChecker
from app.services.link_check.constants import PLATFORM_UC, PLATFORM_XUNLEI
from app.services.link_check.platforms import PLATFORM_139
from app.services.link_check.result import (
    LinkTarget,
    STATUS_INVALID,
    STATUS_RATE_LIMITED,
    STATUS_REQUIRES_CODE,
    STATUS_VALID,
)
from app.services.link_check.validator import LinkValidator


class _FakeResponse:
    def __init__(
        self,
        *,
        status: int = 200,
        body: str = "",
        url: str = "https://example.com",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status = status
        self._body = body
        self.url = url
        self.headers = headers or {"Content-Type": "application/json"}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def text(self, errors: str = "ignore") -> str:
        return self._body


class _FakeSession:
    def __init__(self, *responses: _FakeResponse) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str, dict]] = []

    def _next(self, method: str, url: str, kwargs: dict) -> _FakeResponse:
        self.calls.append((method, url, kwargs))
        if not self._responses:
            raise AssertionError("No fake response queued")
        return self._responses.pop(0)

    def get(self, url: str, **kwargs) -> _FakeResponse:
        return self._next("GET", url, kwargs)

    def post(self, url: str, **kwargs) -> _FakeResponse:
        return self._next("POST", url, kwargs)


class Phase3LinkCheckerTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_validator_detects_phase3_platforms(self) -> None:
        validator = LinkValidator()

        self.assertEqual(validator.get_netdisk_type("https://drive.uc.cn/s/abc123"), PLATFORM_UC)
        self.assertEqual(validator.get_netdisk_type("https://pan.xunlei.com/s/abc123"), PLATFORM_XUNLEI)
        self.assertEqual(
            validator.get_netdisk_type("https://yun.139.com/shareweb/#/w/i/abc123"),
            PLATFORM_139,
        )
        self.assertEqual(
            validator.get_netdisk_type(
                "https://example.com/jump?u="
                "https%3A%2F%2Fyun.139.com%2Fshareweb%2F%23%2Fw%2Fi%2Fabc123"
            ),
            PLATFORM_139,
        )

    async def test_uc_checker_returns_requires_code_for_protected_share(self) -> None:
        checker = UCChecker(timeout=1)
        session = _FakeSession(
            _FakeResponse(
                status=200,
                body="<html><body>\u8bf7\u8f93\u5165\u63d0\u53d6\u7801</body></html>",
                url="https://drive.uc.cn/s/abc123",
                headers={"Content-Type": "text/html"},
            )
        )

        result = await checker.check(
            LinkTarget(
                original_url="https://drive.uc.cn/s/abc123",
                resolved_url="https://drive.uc.cn/s/abc123",
                netdisk_type=PLATFORM_UC,
            ),
            session,
        )

        self.assertEqual(result.status, STATUS_REQUIRES_CODE)
        self.assertTrue(result.is_valid)

    async def test_xunlei_checker_returns_invalid_for_expired_share(self) -> None:
        checker = XunleiChecker(timeout=1)
        session = _FakeSession(
            _FakeResponse(
                status=200,
                body=json.dumps(
                    {
                        "share_status": "EXPIRED",
                        "share_status_text": "\u94fe\u63a5\u5df2\u5931\u6548",
                    }
                ),
            )
        )

        result = await checker.check(
            LinkTarget(
                original_url="https://pan.xunlei.com/s/abc123",
                resolved_url="https://pan.xunlei.com/s/abc123",
                netdisk_type=PLATFORM_XUNLEI,
            ),
            session,
        )

        self.assertEqual(result.status, STATUS_INVALID)
        self.assertFalse(result.is_valid)

    async def test_xunlei_checker_returns_rate_limited_for_risk_response(self) -> None:
        checker = XunleiChecker(timeout=1)
        session = _FakeSession(
            _FakeResponse(
                status=403,
                body=json.dumps({"error_code": 9, "message": "captcha required"}),
            )
        )

        result = await checker.check(
            LinkTarget(
                original_url="https://pan.xunlei.com/s/abc123",
                resolved_url="https://pan.xunlei.com/s/abc123",
                netdisk_type=PLATFORM_XUNLEI,
            ),
            session,
        )

        self.assertEqual(result.status, STATUS_RATE_LIMITED)
        self.assertTrue(result.is_valid)

    async def test_cmcc_checker_returns_valid_for_success_payload(self) -> None:
        checker = CMCCChecker(timeout=1)
        encrypted_body = _encrypt_payload(
            {
                "resultCode": "0",
                "desc": "ok",
                "data": {"linkID": "abc123"},
            }
        )
        session = _FakeSession(_FakeResponse(status=200, body=encrypted_body))

        result = await checker.check(
            LinkTarget(
                original_url="https://yun.139.com/shareweb/#/w/i/abc123",
                resolved_url="https://yun.139.com/shareweb/#/w/i/abc123",
                netdisk_type=PLATFORM_139,
            ),
            session,
        )

        self.assertEqual(result.status, STATUS_VALID)
        self.assertTrue(result.is_valid)

    async def test_cmcc_checker_returns_requires_code_when_password_missing(self) -> None:
        checker = CMCCChecker(timeout=1)
        encrypted_body = _encrypt_payload(
            {
                "resultCode": "201",
                "desc": "\u8bf7\u8f93\u5165\u63d0\u53d6\u7801",
                "data": None,
            }
        )
        session = _FakeSession(_FakeResponse(status=200, body=encrypted_body))

        result = await checker.check(
            LinkTarget(
                original_url="https://caiyun.139.com/m/i?abc123",
                resolved_url="https://caiyun.139.com/m/i?abc123",
                netdisk_type=PLATFORM_139,
            ),
            session,
        )

        self.assertEqual(result.status, STATUS_REQUIRES_CODE)
        self.assertTrue(result.is_valid)

    async def test_monitor_parser_collects_139_links(self) -> None:
        parsed, diagnostics = await parse_message_content(
            "Example title\nhttps://yun.139.com/shareweb/#/w/i/abc123",
            channel_name="test-channel",
        )

        self.assertEqual(parsed["title"], "Example title")
        self.assertIn(PLATFORM_139, parsed["links"])
        self.assertEqual(
            parsed["links"][PLATFORM_139][0]["url"],
            "https://yun.139.com/shareweb/#/w/i/abc123",
        )
        self.assertGreaterEqual(diagnostics.extracted_link_count, 1)


if __name__ == "__main__":
    unittest.main()

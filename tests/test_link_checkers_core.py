from __future__ import annotations

import json
import os
import unittest

os.environ.setdefault("TELEGRAM_API_ID", "1")
os.environ.setdefault("TELEGRAM_API_HASH", "hash")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/testdb")
os.environ.setdefault("DEFAULT_CHANNELS", "")
os.environ.setdefault("SECRET_SALT", "test-salt")

from app.services.link_check.checkers.baidu import BaiduChecker
from app.services.link_check.checkers.pan115 import Pan115Checker
from app.services.link_check.checkers.pan123 import Pan123Checker
from app.services.link_check.checkers.quark import QuarkChecker
from app.services.link_check.checkers.tianyi import TianyiChecker
from app.services.link_check.constants import PLATFORM_115, PLATFORM_123, PLATFORM_BAIDU, PLATFORM_QUARK, PLATFORM_TIANYI
from app.services.link_check.result import LinkTarget, STATUS_UNCERTAIN, STATUS_VALID


class _FakeResponse:
    def __init__(self, *, status: int = 200, body: str = "", headers: dict[str, str] | None = None) -> None:
        self.status = status
        self._body = body
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


class CoreLinkCheckerTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_quark_checker_accepts_ok_payload_with_zero_status(self) -> None:
        checker = QuarkChecker(timeout=1)
        session = _FakeSession(
            _FakeResponse(
                status=200,
                body=json.dumps(
                    {
                        "status": 0,
                        "code": 0,
                        "message": "ok",
                        "data": {"stoken": "token-123"},
                    }
                ),
            ),
            _FakeResponse(
                status=200,
                body=json.dumps(
                    {
                        "status": 0,
                        "code": 0,
                        "message": "ok",
                        "data": {"list": [{"fid": "1"}]},
                    }
                ),
            ),
        )

        result = await checker.check(
            LinkTarget(
                original_url="https://pan.quark.cn/s/abc123",
                resolved_url="https://pan.quark.cn/s/abc123",
                netdisk_type=PLATFORM_QUARK,
            ),
            session,
        )

        self.assertEqual(result.status, STATUS_VALID)
        self.assertTrue(result.is_valid)

    async def test_baidu_checker_keeps_full_surl_for_share_init_links(self) -> None:
        checker = BaiduChecker(timeout=1)
        session = _FakeSession(
            _FakeResponse(
                status=200,
                body=json.dumps({"errno": 0, "randsk": "cookie-123"}),
            ),
            _FakeResponse(
                status=200,
                body=json.dumps({"errno": 0}),
            ),
        )

        result = await checker.check(
            LinkTarget(
                original_url="https://pan.baidu.com/share/init?surl=kq2X2n1Yn_to_ZS41qYJFw&pwd=t6ic",
                resolved_url="https://pan.baidu.com/share/init?surl=kq2X2n1Yn_to_ZS41qYJFw&pwd=t6ic",
                netdisk_type=PLATFORM_BAIDU,
            ),
            session,
        )

        self.assertTrue(result.is_valid)
        self.assertIn("surl=kq2X2n1Yn_to_ZS41qYJFw", session.calls[0][1])

    async def test_baidu_checker_treats_errno_minus_one_as_uncertain(self) -> None:
        checker = BaiduChecker(timeout=1)
        session = _FakeSession(
            _FakeResponse(status=200, body=json.dumps({"errno": -1})),
            _FakeResponse(status=200, body=json.dumps({"errno": -1})),
        )

        result = await checker.check(
            LinkTarget(
                original_url="https://pan.baidu.com/s/1abcde?pwd=6666",
                resolved_url="https://pan.baidu.com/s/1abcde?pwd=6666",
                netdisk_type=PLATFORM_BAIDU,
            ),
            session,
        )

        self.assertEqual(result.status, STATUS_UNCERTAIN)
        self.assertTrue(result.is_valid)

    async def test_tianyi_checker_accepts_share_id_payload(self) -> None:
        checker = TianyiChecker(timeout=1)
        session = _FakeSession(
            _FakeResponse(
                status=200,
                body=json.dumps(
                    {
                        "shareId": "123456",
                        "res_message": "ok",
                    }
                ),
            )
        )

        result = await checker.check(
            LinkTarget(
                original_url="https://cloud.189.cn/t/Q3UnyyJFvmii",
                resolved_url="https://cloud.189.cn/t/Q3UnyyJFvmii",
                netdisk_type=PLATFORM_TIANYI,
            ),
            session,
        )

        self.assertEqual(result.status, STATUS_VALID)
        self.assertTrue(result.is_valid)

    async def test_pan123_checker_accepts_ok_message_as_valid(self) -> None:
        checker = Pan123Checker(timeout=1)
        session = _FakeSession(
            _FakeResponse(
                status=200,
                body=json.dumps(
                    {
                        "code": 1000,
                        "message": "ok",
                        "data": {},
                    }
                ),
            )
        )

        result = await checker.check(
            LinkTarget(
                original_url="https://www.123684.com/s/u9izjv-7olWv",
                resolved_url="https://www.123684.com/s/u9izjv-7olWv",
                netdisk_type=PLATFORM_123,
            ),
            session,
        )

        self.assertEqual(result.status, STATUS_VALID)
        self.assertTrue(result.is_valid)

    async def test_pan115_checker_falls_back_to_uncertain_for_non_invalid_payload(self) -> None:
        checker = Pan115Checker(timeout=1)
        session = _FakeSession(
            _FakeResponse(
                status=200,
                body=json.dumps(
                    {
                        "state": False,
                        "errno": 911,
                        "error": "",
                    }
                ),
            )
        )

        result = await checker.check(
            LinkTarget(
                original_url="https://115cdn.com/s/swftgr33zrk?password=t58d",
                resolved_url="https://115cdn.com/s/swftgr33zrk?password=t58d",
                netdisk_type=PLATFORM_115,
            ),
            session,
        )

        self.assertEqual(result.status, STATUS_UNCERTAIN)
        self.assertTrue(result.is_valid)


if __name__ == "__main__":
    unittest.main()

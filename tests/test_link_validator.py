from __future__ import annotations

import os
import unittest

os.environ.setdefault("TELEGRAM_API_ID", "1")
os.environ.setdefault("TELEGRAM_API_HASH", "hash")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/testdb")
os.environ.setdefault("DEFAULT_CHANNELS", "")
os.environ.setdefault("SECRET_SALT", "test-salt")

from app.services.link_check.cache import LINK_RESULT_CACHE
from app.services.link_check.constants import PLATFORM_BAIDU
from app.services.link_check.checkers.base import BaseChecker
from app.services.link_check.checkers.baidu import _extract_share_id
from app.services.link_check.checkers.quark import _extract_resource_id
from app.services.link_check.result import (
    LinkCheckResult,
    LinkTarget,
    STATUS_INVALID,
    STATUS_REQUIRES_CODE,
    STATUS_UNCERTAIN,
    STATUS_VALID,
)
from app.services.link_check.validator import LinkValidator


class _FakeResolver:
    def guess_platform(self, url: str) -> str:
        return PLATFORM_BAIDU

    async def resolve(self, url: str, http_session) -> str:
        return url


class _FakeChecker:
    checker_name = "fake"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_concurrency_limit(self) -> int:
        return 5

    async def check(self, target: LinkTarget, http_session) -> LinkCheckResult:
        self.calls.append(target.resolved_url)
        status = STATUS_REQUIRES_CODE if "need-code" in target.resolved_url else STATUS_VALID
        return LinkCheckResult(
            url=target.original_url,
            netdisk_type=target.netdisk_type,
            is_valid=True,
            status=status,
            response_time=0.01,
            reason="链接有效" if status == STATUS_VALID else "需要提取码",
            resolved_url=target.resolved_url,
            checker="fake",
        )


class _FakeRegistry:
    def __init__(self, checker: _FakeChecker) -> None:
        self._checker = checker

    def get_checker(self, platform: str) -> _FakeChecker:
        return self._checker


class _ExplodingChecker(BaseChecker):
    checker_name = "exploding"

    def __init__(self) -> None:
        super().__init__(PLATFORM_BAIDU, timeout=1)

    async def check(self, target: LinkTarget, http_session) -> LinkCheckResult:
        raise IndexError("boom")


class _FakeHistoryProvider:
    def __init__(self, results: dict[str, LinkCheckResult] | None = None) -> None:
        self.results = results or {}
        self.calls: list[list[str]] = []

    def get_recent_results(self, urls) -> dict[str, LinkCheckResult]:
        url_list = list(urls)
        self.calls.append(url_list)
        return {url: self.results[url] for url in url_list if url in self.results}


class LinkValidatorTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        LINK_RESULT_CACHE.clear()

    def test_get_netdisk_type_detects_embedded_redirect_target(self) -> None:
        validator = LinkValidator()
        url = (
            "https://weibo.cn/sinaurl?u="
            "https%3A%2F%2Fpan.baidu.com%2Fs%2F1w-6cKgTyfGfJ3p2XkgPAHQ%3Fpwd%3D6666"
        )
        self.assertEqual(validator.get_netdisk_type(url), PLATFORM_BAIDU)

    async def test_check_multiple_links_reuses_duplicate_targets_and_preserves_order(self) -> None:
        validator = LinkValidator()
        fake_checker = _FakeChecker()
        validator.resolver = _FakeResolver()
        validator.registry = _FakeRegistry(fake_checker)
        validator.history_provider = _FakeHistoryProvider()

        urls = [
            "https://pan.baidu.com/s/duplicate",
            "https://pan.baidu.com/s/duplicate",
            "https://pan.baidu.com/s/need-code",
        ]

        results = await validator.check_multiple_links_with_progress(urls, max_concurrent=3)

        self.assertEqual(len(results), 3)
        self.assertEqual(fake_checker.calls.count("https://pan.baidu.com/s/duplicate"), 1)
        self.assertEqual(results[0]["url"], "https://pan.baidu.com/s/duplicate")
        self.assertEqual(results[1]["url"], "https://pan.baidu.com/s/duplicate")
        self.assertEqual(results[2]["status"], STATUS_REQUIRES_CODE)
        self.assertTrue(all(result["is_valid"] for result in results))

    async def test_result_callback_receives_per_link_runtime_events(self) -> None:
        validator = LinkValidator()
        fake_checker = _FakeChecker()
        validator.resolver = _FakeResolver()
        validator.registry = _FakeRegistry(fake_checker)
        validator.history_provider = _FakeHistoryProvider()

        events: list[dict[str, object]] = []

        async def result_callback(event: dict[str, object]) -> None:
            events.append(event)

        results = await validator.check_multiple_links_with_progress(
            ["https://pan.baidu.com/s/runtime-1", "https://pan.baidu.com/s/runtime-2"],
            max_concurrent=2,
            result_callback=result_callback,
        )

        self.assertEqual(len(results), 2)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["source"], "network")
        self.assertEqual(events[-1]["checked"], 2)
        self.assertEqual(events[-1]["total"], 2)
        self.assertEqual(events[0]["platform"], PLATFORM_BAIDU)

    def test_summary_keeps_requires_code_links_in_valid_bucket(self) -> None:
        validator = LinkValidator()
        summary = validator.get_summary(
            [
                {"netdisk_type": PLATFORM_BAIDU, "is_valid": True, "status": STATUS_VALID, "response_time": 0.1},
                {
                    "netdisk_type": PLATFORM_BAIDU,
                    "is_valid": True,
                    "status": STATUS_REQUIRES_CODE,
                    "response_time": 0.2,
                },
            ]
        )

        self.assertEqual(summary["valid_links"], 2)
        self.assertEqual(summary["invalid_links"], 0)
        self.assertEqual(summary["status_counts"][STATUS_REQUIRES_CODE], 1)

    async def test_reuses_in_memory_cache_across_validator_instances(self) -> None:
        first_checker = _FakeChecker()
        first_validator = LinkValidator()
        first_validator.resolver = _FakeResolver()
        first_validator.registry = _FakeRegistry(first_checker)
        first_validator.history_provider = _FakeHistoryProvider()

        second_checker = _FakeChecker()
        second_validator = LinkValidator()
        second_validator.resolver = _FakeResolver()
        second_validator.registry = _FakeRegistry(second_checker)
        second_validator.history_provider = _FakeHistoryProvider()

        url = "https://pan.baidu.com/s/cache-hit"
        first_results = await first_validator.check_multiple_links_with_progress([url], max_concurrent=1)
        second_results = await second_validator.check_multiple_links_with_progress([url], max_concurrent=1)

        self.assertEqual(len(first_results), 1)
        self.assertEqual(len(second_results), 1)
        self.assertEqual(first_checker.calls.count(url), 1)
        self.assertEqual(second_checker.calls, [])

    async def test_skips_invalid_history_reuse_and_performs_live_check(self) -> None:
        validator = LinkValidator()
        fake_checker = _FakeChecker()
        validator.resolver = _FakeResolver()
        validator.registry = _FakeRegistry(fake_checker)
        validator.history_provider = _FakeHistoryProvider(
            {
                "https://pan.baidu.com/s/from-history": LinkCheckResult(
                    url="https://pan.baidu.com/s/from-history",
                    netdisk_type=PLATFORM_BAIDU,
                    is_valid=False,
                    status=STATUS_INVALID,
                    response_time=0.02,
                    error="历史失效",
                    reason="历史失效",
                    checker="history",
                )
            }
        )

        results = await validator.check_multiple_links_with_progress(
            ["https://pan.baidu.com/s/from-history"],
            max_concurrent=1,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], STATUS_VALID)
        self.assertTrue(results[0]["is_valid"])
        self.assertEqual(fake_checker.calls, ["https://pan.baidu.com/s/from-history"])

    def test_baidu_share_id_extraction_tracks_when_prefix_stripping_is_needed(self) -> None:
        self.assertEqual(
            _extract_share_id("https://pan.baidu.com/s/1AbCdEf1234?pwd=6666"),
            ("1AbCdEf1234", True),
        )
        self.assertEqual(
            _extract_share_id("https://pan.baidu.com/share/init?surl=kq2X2n1Yn_to_ZS41qYJFw&pwd=t6ic"),
            ("kq2X2n1Yn_to_ZS41qYJFw", False),
        )

    def test_quark_resource_extraction_handles_nested_share_paths(self) -> None:
        self.assertEqual(
            _extract_resource_id("https://pan.quark.cn/s/abc123"),
            ("abc123", ""),
        )
        self.assertEqual(
            _extract_resource_id("https://pan.quark.cn/s/abc123/folder?pwd=6666"),
            ("abc123", "6666"),
        )
        self.assertEqual(
            _extract_resource_id("https://pan.quark.cn/share/abc123"),
            ("", ""),
        )

    async def test_checker_exceptions_do_not_fail_the_whole_batch(self) -> None:
        validator = LinkValidator()
        validator.resolver = _FakeResolver()
        validator.registry = _FakeRegistry(_ExplodingChecker())
        validator.history_provider = _FakeHistoryProvider()

        results = await validator.check_multiple_links_with_progress(
            ["https://pan.baidu.com/s/exploding"],
            max_concurrent=1,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], STATUS_UNCERTAIN)
        self.assertTrue(results[0]["is_valid"])
        self.assertIn("IndexError", results[0]["error"])


if __name__ == "__main__":
    unittest.main()

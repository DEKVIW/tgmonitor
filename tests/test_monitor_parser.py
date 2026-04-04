from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from app.core.monitor_parser import (
    extract_embedded_redirect_targets,
    extract_redirect_urls_from_html,
    extract_redirect_urls_from_refresh_header,
    fetch_redirect_target,
    parse_message_content,
    parse_message_records,
)
from app.core.monitor_rules import load_monitor_rules


class _FakeResponse:
    def __init__(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        body: str = "",
        history: list["_FakeResponse"] | None = None,
    ) -> None:
        self.url = url
        self.headers = headers or {}
        self._body = body
        self.history = history or []

    async def text(self, errors: str = "ignore") -> str:
        return self._body


class _FakeRequestContext:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    async def __aenter__(self) -> _FakeResponse:
        return self._response

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


class _FakeSession:
    def __init__(self, head_response: _FakeResponse | None, get_response: _FakeResponse | None) -> None:
        self.head_response = head_response
        self.get_response = get_response
        self.calls: list[str] = []

    def head(self, url: str, allow_redirects: bool = True, max_redirects: int = 8):
        self.calls.append(f"head:{url}:{max_redirects}")
        if self.head_response is None:
            raise RuntimeError("head disabled")
        return _FakeRequestContext(self.head_response)

    def get(self, url: str, allow_redirects: bool = True, max_redirects: int = 8):
        self.calls.append(f"get:{url}:{max_redirects}")
        if self.get_response is None:
            raise RuntimeError("get disabled")
        return _FakeRequestContext(self.get_response)


class MonitorParserTestCase(unittest.TestCase):
    def test_extracts_embedded_redirect_target_without_network(self) -> None:
        rules = load_monitor_rules()
        url = (
            "https://weibo.cn/sinaurl?u="
            "https%3A%2F%2Fpan.baidu.com%2Fs%2F1w-6cKgTyfGfJ3p2XkgPAHQ%3Fpwd%3D6666"
        )
        targets = extract_embedded_redirect_targets(url, rules["redirect_query_keys"])
        self.assertIn("https://pan.baidu.com/s/1w-6cKgTyfGfJ3p2XkgPAHQ?pwd=6666", targets)

    def test_parse_message_content_resolves_redirect_and_extracts_tags(self) -> None:
        message = "\n".join(
            [
                "名称：北京事业单位系统班",
                "【北京】【事业单位】",
                (
                    "主链：https://weibo.cn/sinaurl?u="
                    "https%3A%2F%2Fpan.baidu.com%2Fs%2F1w-6cKgTyfGfJ3p2XkgPAHQ%3Fpwd%3D6666"
                ),
            ]
        )

        parsed, diagnostics = asyncio.run(parse_message_content(message, channel_name="test-channel"))

        self.assertEqual(parsed["title"], "北京事业单位系统班")
        self.assertIn("北京", parsed["tags"])
        self.assertIn("事业单位", parsed["tags"])
        self.assertIn("百度网盘", parsed["links"])

        link_item = parsed["links"]["百度网盘"][0]
        self.assertEqual(link_item["label"], "主链")
        self.assertEqual(
            link_item["url"],
            "https://pan.baidu.com/s/1w-6cKgTyfGfJ3p2XkgPAHQ?pwd=6666",
        )
        self.assertTrue(link_item["original_url"].startswith("https://weibo.cn/sinaurl"))
        self.assertGreaterEqual(diagnostics.redirect_resolved_count, 1)

    def test_parse_message_content_supports_channel_intermediate_domain_mapping(self) -> None:
        message = "\n".join(
            [
                "名称：网盘资源测试",
                "主链：https://jump.wpzyk.example/share/abc123",
            ]
        )
        rules = {
            "redirect_query_keys": [],
            "netdisk_map": [
                {"name": "百度网盘", "keys": ["pan.baidu.com"]},
            ],
            "profiles": {
                "default": {
                    "title_fields": ["名称", "标题"],
                    "metadata": {"source": ["来源"], "channel": ["频道"], "group": ["群组"], "bot": ["投稿"]},
                    "ignored_line_prefixes": [],
                    "valid_labels": ["主链"],
                    "regions": [],
                    "course_keywords": [],
                    "categories": [],
                    "filter_patterns": [],
                    "intermediate_netdisk_domains": {},
                },
                "wpzyk": {
                    "intermediate_netdisk_domains": {
                        "百度网盘": ["jump.wpzyk.example"],
                    },
                },
            },
            "channel_profiles": {"wpzyk": "wpzyk"},
        }

        with patch("app.core.monitor_parser.load_monitor_rules", return_value=rules), patch(
            "app.core.monitor_parser.resolve_message_urls",
            return_value=({"https://jump.wpzyk.example/share/abc123": "https://jump.wpzyk.example/share/abc123"}, 0),
        ):
            parsed, diagnostics = asyncio.run(parse_message_content(message, channel_name="wpzyk"))

        self.assertIn("百度网盘", parsed["links"])
        link_item = parsed["links"]["百度网盘"][0]
        self.assertEqual(link_item["label"], "主链")
        self.assertEqual(link_item["url"], "https://jump.wpzyk.example/share/abc123")
        self.assertEqual(diagnostics.raw_url_count, 1)
        self.assertEqual(diagnostics.resolved_url_count, 1)
        self.assertEqual(diagnostics.raw_url_samples, ["https://jump.wpzyk.example/share/abc123"])

    def test_parse_message_records_splits_shortlink_lines_with_message_hint(self) -> None:
        message = "\n".join(
            [
                "2026\u5e74CG\u7ed3\u6784\u5316\u9762\u8bd5\u5b66\u81f3\u8003\u524d\u73ed\u8bfe\u7a0b http://t.cn/AXInWTJ4",
                "2026\u4e86\u51e1\u65e5\u8bb0\u9762\u8bd5\u7cbe\u8bb2\u8bfe http://t.cn/AXInWTJ5",
                "\u5706\u5b50\u5b66\u59d0\u7ed3\u6784\u5316\u9762\u8bd5\u5fc5\u80cc\u7b54\u9898\u6bcd\u9898 http://t.cn/AXInWTJG",
                "BD #\u9762\u8bd5",
            ]
        )
        rules = {
            "redirect_query_keys": [],
            "netdisk_map": [
                {"name": "\u767e\u5ea6\u7f51\u76d8", "keys": ["pan.baidu.com"]},
            ],
            "profiles": {
                "default": {
                    "title_fields": ["\u540d\u79f0", "\u6807\u9898"],
                    "metadata": {
                        "source": ["\u6765\u6e90"],
                        "channel": ["\u9891\u9053"],
                        "group": ["\u7fa4\u7ec4"],
                        "bot": ["\u6295\u7a3f"],
                    },
                    "ignored_line_prefixes": [],
                    "valid_labels": ["\u4e3b\u94fe"],
                    "regions": [],
                    "course_keywords": ["\u9762\u8bd5"],
                    "categories": [],
                    "filter_patterns": [],
                    "intermediate_netdisk_domains": {},
                },
                "wpzyk_shortlinks": {
                    "line_message_mode": "per_link_line",
                },
            },
            "channel_profiles": {"wpzyk": "wpzyk_shortlinks"},
        }

        with patch("app.core.monitor_parser.load_monitor_rules", return_value=rules), patch(
            "app.core.monitor_parser.resolve_message_urls",
            return_value=(
                {
                    "http://t.cn/AXInWTJ4": "http://t.cn/AXInWTJ4",
                    "http://t.cn/AXInWTJ5": "http://t.cn/AXInWTJ5",
                    "http://t.cn/AXInWTJG": "http://t.cn/AXInWTJG",
                },
                0,
            ),
        ):
            parsed_records, diagnostics = asyncio.run(parse_message_records(message, channel_name="wpzyk"))

        self.assertEqual(len(parsed_records), 3)
        self.assertEqual(parsed_records[0]["title"], "2026\u5e74CG\u7ed3\u6784\u5316\u9762\u8bd5\u5b66\u81f3\u8003\u524d\u73ed\u8bfe\u7a0b")
        self.assertEqual(parsed_records[1]["title"], "2026\u4e86\u51e1\u65e5\u8bb0\u9762\u8bd5\u7cbe\u8bb2\u8bfe")
        self.assertEqual(
            parsed_records[2]["title"],
            "\u5706\u5b50\u5b66\u59d0\u7ed3\u6784\u5316\u9762\u8bd5\u5fc5\u80cc\u7b54\u9898\u6bcd\u9898",
        )
        for record, expected_url in zip(
            parsed_records,
            ["http://t.cn/AXInWTJ4", "http://t.cn/AXInWTJ5", "http://t.cn/AXInWTJG"],
        ):
            self.assertIn("\u767e\u5ea6\u7f51\u76d8", record["links"])
            self.assertEqual(record["links"]["\u767e\u5ea6\u7f51\u76d8"][0]["url"], expected_url)
            self.assertIn("\u9762\u8bd5", record["tags"])
        self.assertEqual(diagnostics.extracted_link_count, 3)

    def test_parse_course_list_records_merge_multi_platform_lines_and_keep_tags_clean(self) -> None:
        message = "\n".join(
            [
                "\u3010KK\u30112026\u5e74\u674e\u94c1\u6cb3\u5357\u4e8b\u8003\u5237\u9898 http://t.cn/quark1",
                "\u3010BD\u30112026\u5e74\u674e\u94c1\u6cb3\u5357\u4e8b\u8003\u5237\u9898 http://t.cn/baidu1",
                "#\u4e8b\u4e1a\u7f16",
            ]
        )
        rules = {
            "redirect_query_keys": [],
            "netdisk_map": [
                {"name": "\u767e\u5ea6\u7f51\u76d8", "keys": ["pan.baidu.com"]},
                {"name": "\u5938\u514b\u7f51\u76d8", "keys": ["pan.quark.cn"]},
            ],
            "profiles": {
                "default": {
                    "title_fields": ["\u540d\u79f0", "\u6807\u9898"],
                    "metadata": {
                        "source": ["\u6765\u6e90"],
                        "channel": ["\u9891\u9053"],
                        "group": ["\u7fa4\u7ec4"],
                        "bot": ["\u6295\u7a3f"],
                    },
                    "ignored_line_prefixes": [],
                    "valid_labels": ["\u4e3b\u94fe"],
                    "regions": ["\u6cb3\u5357"],
                    "course_keywords": ["\u4e8b\u4e1a\u7f16", "\u5237\u9898"],
                    "categories": [],
                    "filter_patterns": [],
                    "intermediate_netdisk_domains": {},
                },
                "course_list_default": {
                    "content_mode": "course_list",
                    "line_message_mode": "per_link_line",
                    "netdisk_hint_aliases": {
                        "\u5938\u514b\u7f51\u76d8": ["KK"],
                        "\u767e\u5ea6\u7f51\u76d8": ["BD"],
                    },
                },
            },
            "channel_profiles": {"wpzyk": "course_list_default"},
        }

        with patch("app.core.monitor_parser.load_monitor_rules", return_value=rules), patch(
            "app.core.monitor_parser.resolve_message_urls",
            return_value=(
                {
                    "http://t.cn/quark1": "http://t.cn/quark1",
                    "http://t.cn/baidu1": "http://t.cn/baidu1",
                },
                0,
            ),
        ):
            parsed_records, diagnostics = asyncio.run(parse_message_records(message, channel_name="wpzyk"))

        self.assertEqual(len(parsed_records), 1)
        record = parsed_records[0]
        self.assertEqual(record["title"], "2026\u5e74\u674e\u94c1\u6cb3\u5357\u4e8b\u8003\u5237\u9898")
        self.assertEqual(record["description"], "")
        self.assertIn("\u4e8b\u4e1a\u7f16", record["tags"])
        self.assertIn("\u6cb3\u5357", record["tags"])
        self.assertIn("\u5237\u9898", record["tags"])
        self.assertNotIn("KK", record["tags"])
        self.assertNotIn("BD", record["tags"])
        self.assertEqual(record["links"]["\u5938\u514b\u7f51\u76d8"][0]["url"], "http://t.cn/quark1")
        self.assertEqual(record["links"]["\u767e\u5ea6\u7f51\u76d8"][0]["url"], "http://t.cn/baidu1")
        self.assertEqual(diagnostics.extracted_link_count, 2)

    def test_parse_course_list_records_limit_keyword_tags_to_each_title(self) -> None:
        message = "\n".join(
            [
                "2026\u5c0f\u9a6c\u54e5\u5e7f\u4e1c\u4e8b\u4e1a\u5355\u4f4d\u9762\u8bd5\u8003\u60c5 http://t.cn/item1",
                "\u5706\u5b50\u5b66\u59d0\u7ed3\u6784\u5316\u9762\u8bd5\u5fc5\u80cc\u7b54\u9898\u6bcd\u9898 http://t.cn/item2",
                "BD #\u9762\u8bd5",
            ]
        )
        rules = {
            "redirect_query_keys": [],
            "netdisk_map": [
                {"name": "\u767e\u5ea6\u7f51\u76d8", "keys": ["pan.baidu.com"]},
            ],
            "profiles": {
                "default": {
                    "title_fields": ["\u540d\u79f0", "\u6807\u9898"],
                    "metadata": {
                        "source": ["\u6765\u6e90"],
                        "channel": ["\u9891\u9053"],
                        "group": ["\u7fa4\u7ec4"],
                        "bot": ["\u6295\u7a3f"],
                    },
                    "ignored_line_prefixes": [],
                    "valid_labels": ["\u4e3b\u94fe"],
                    "regions": ["\u5e7f\u4e1c"],
                    "course_keywords": ["\u9762\u8bd5", "\u4e8b\u4e1a\u5355\u4f4d"],
                    "categories": [],
                    "filter_patterns": [],
                    "intermediate_netdisk_domains": {},
                },
                "course_list_default": {
                    "content_mode": "course_list",
                    "line_message_mode": "per_link_line",
                    "netdisk_hint_aliases": {
                        "\u767e\u5ea6\u7f51\u76d8": ["BD"],
                    },
                },
            },
            "channel_profiles": {"wpzyk": "course_list_default"},
        }

        with patch("app.core.monitor_parser.load_monitor_rules", return_value=rules), patch(
            "app.core.monitor_parser.resolve_message_urls",
            return_value=(
                {
                    "http://t.cn/item1": "http://t.cn/item1",
                    "http://t.cn/item2": "http://t.cn/item2",
                },
                0,
            ),
        ):
            parsed_records, diagnostics = asyncio.run(parse_message_records(message, channel_name="wpzyk"))

        self.assertEqual(len(parsed_records), 2)
        first_record, second_record = parsed_records
        self.assertEqual(first_record["description"], "")
        self.assertEqual(second_record["description"], "")
        self.assertIn("\u9762\u8bd5", first_record["tags"])
        self.assertIn("\u5e7f\u4e1c", first_record["tags"])
        self.assertIn("\u4e8b\u4e1a\u5355\u4f4d", first_record["tags"])
        self.assertIn("\u9762\u8bd5", second_record["tags"])
        self.assertNotIn("\u5e7f\u4e1c", second_record["tags"])
        self.assertNotIn("\u4e8b\u4e1a\u5355\u4f4d", second_record["tags"])
        self.assertEqual(diagnostics.extracted_link_count, 2)

    def test_parse_message_content_uses_message_hint_for_unresolved_shortlink(self) -> None:
        message = "\n".join(
            [
                "2026\u5e74CG\u7ed3\u6784\u5316\u9762\u8bd5\u5b66\u81f3\u8003\u524d\u73ed\u8bfe\u7a0b http://t.cn/AXInWTJ4",
                "BD #\u9762\u8bd5",
            ]
        )
        rules = {
            "redirect_query_keys": [],
            "netdisk_map": [
                {"name": "\u767e\u5ea6\u7f51\u76d8", "keys": ["pan.baidu.com"]},
            ],
            "profiles": {
                "default": {
                    "title_fields": ["\u540d\u79f0", "\u6807\u9898"],
                    "metadata": {
                        "source": ["\u6765\u6e90"],
                        "channel": ["\u9891\u9053"],
                        "group": ["\u7fa4\u7ec4"],
                        "bot": ["\u6295\u7a3f"],
                    },
                    "ignored_line_prefixes": [],
                    "valid_labels": ["\u4e3b\u94fe"],
                    "regions": [],
                    "course_keywords": [],
                    "categories": [],
                    "filter_patterns": [],
                    "intermediate_netdisk_domains": {},
                },
            },
            "channel_profiles": {},
        }

        with patch("app.core.monitor_parser.load_monitor_rules", return_value=rules), patch(
            "app.core.monitor_parser.resolve_message_urls",
            return_value=({"http://t.cn/AXInWTJ4": "http://t.cn/AXInWTJ4"}, 0),
        ):
            parsed, _ = asyncio.run(parse_message_content(message, channel_name="wpzyk"))

        self.assertIn("\u767e\u5ea6\u7f51\u76d8", parsed["links"])
        self.assertEqual(parsed["links"]["\u767e\u5ea6\u7f51\u76d8"][0]["url"], "http://t.cn/AXInWTJ4")

    def test_parse_message_content_keeps_filter_behavior_without_hint_or_match(self) -> None:
        message = "2026\u5e74CG\u7ed3\u6784\u5316\u9762\u8bd5\u5b66\u81f3\u8003\u524d\u73ed\u8bfe\u7a0b http://t.cn/AXInWTJ4"
        rules = {
            "redirect_query_keys": [],
            "netdisk_map": [
                {"name": "\u767e\u5ea6\u7f51\u76d8", "keys": ["pan.baidu.com"]},
            ],
            "profiles": {
                "default": {
                    "title_fields": ["\u540d\u79f0", "\u6807\u9898"],
                    "metadata": {
                        "source": ["\u6765\u6e90"],
                        "channel": ["\u9891\u9053"],
                        "group": ["\u7fa4\u7ec4"],
                        "bot": ["\u6295\u7a3f"],
                    },
                    "ignored_line_prefixes": [],
                    "valid_labels": ["\u4e3b\u94fe"],
                    "regions": [],
                    "course_keywords": [],
                    "categories": [],
                    "filter_patterns": [],
                    "intermediate_netdisk_domains": {},
                },
            },
            "channel_profiles": {},
        }

        with patch("app.core.monitor_parser.load_monitor_rules", return_value=rules), patch(
            "app.core.monitor_parser.resolve_message_urls",
            return_value=({"http://t.cn/AXInWTJ4": "http://t.cn/AXInWTJ4"}, 0),
        ):
            parsed, _ = asyncio.run(parse_message_content(message, channel_name="wpzyk"))

        self.assertEqual(parsed["links"], {})

    def test_parse_movie_message_content_filters_promo_noise_and_uses_size_as_link_label(self) -> None:
        message = "\n".join(
            [
                "名称：妈咪别怕福星来了 (57集) 王博&咪咕 | 短剧",
                "描述：2026年04月04日最新热门抖音快手百度番茄红果等付费短剧推荐 / 每日同步更新！妈咪别怕，福星来了 王博 咪咕",
                "链接：https://pan.quark.cn/s/28854c048c71",
                "📁 大小：740.5 MB",
                "🏷 标签：#妈咪别怕福星来了 #短剧",
                "📢 频道：@NewQuark",
                "👥 群组：@Quark_Share_Group",
                "🤖 投稿：@QuarkRobot",
            ]
        )

        with patch(
            "app.core.monitor_parser.resolve_message_urls",
            return_value=({"https://pan.quark.cn/s/28854c048c71": "https://pan.quark.cn/s/28854c048c71"}, 0),
        ):
            parsed, diagnostics = asyncio.run(
                parse_message_content(message, channel_name="+eQXY7Ewx-4I4NDFl")
            )

        self.assertEqual(parsed["title"], "妈咪别怕福星来了 (57集)")
        self.assertEqual(parsed["description"], "主演: 王博 / 咪咕")
        self.assertEqual(parsed["tags"], ["短剧"])
        self.assertEqual(parsed["links"]["夸克网盘"][0]["label"], "740.5 MB")
        self.assertEqual(parsed["channel"], "@NewQuark")
        self.assertEqual(parsed["group_name"], "@Quark_Share_Group")
        self.assertEqual(parsed["bot"], "@QuarkRobot")
        self.assertEqual(diagnostics.extracted_link_count, 1)

    def test_parse_movie_message_content_assigns_variant_labels_for_multi_link_message(self) -> None:
        message = "\n".join(
            [
                "沧元图 前传·东宁府的夏天（2026）4K HQ 高码率 更至EP67",
                "- https://cloud.189.cn/t/bMZFBv3YNZja",
                "4K SDR 高码率 66集全",
                "https://cloud.189.cn/t/NnyERvruyYRj",
                "4K HQ 杜比视界 高码率 全66集 300G",
                "- https://cloud.189.cn/t/6JFjMbA3Ib6f",
                "🏷 标签：#沧元图 #国漫",
            ]
        )

        with patch(
            "app.core.monitor_parser.resolve_message_urls",
            return_value=(
                {
                    "https://cloud.189.cn/t/bMZFBv3YNZja": "https://cloud.189.cn/t/bMZFBv3YNZja",
                    "https://cloud.189.cn/t/NnyERvruyYRj": "https://cloud.189.cn/t/NnyERvruyYRj",
                    "https://cloud.189.cn/t/6JFjMbA3Ib6f": "https://cloud.189.cn/t/6JFjMbA3Ib6f",
                },
                0,
            ),
        ):
            parsed, diagnostics = asyncio.run(
                parse_message_content(message, channel_name="tianyirigeng")
            )

        self.assertEqual(parsed["title"], "沧元图 前传·东宁府的夏天（2026） 更至EP67")
        self.assertEqual(parsed["description"], "")
        self.assertEqual(parsed["tags"], ["沧元图", "国漫"])
        labels = [item["label"] for item in parsed["links"]["天翼云盘"]]
        self.assertEqual(labels[0], "4K HQ 高码率 更至EP67")
        self.assertEqual(labels[1], "4K SDR 高码率 66集全")
        self.assertEqual(labels[2], "4K HQ 杜比视界 高码率 全66集 300G")
        self.assertEqual(diagnostics.extracted_link_count, 3)

    def test_extract_redirect_urls_from_html_supports_relative_targets_and_anchor_links(self) -> None:
        html = """
        <html>
          <head>
            <meta http-equiv="refresh" content="0;url=/jump/final">
            <script>window.location.href='/script/final';</script>
          </head>
          <body>
            <a href="https://pan.baidu.com/s/abc123">open</a>
          </body>
        </html>
        """

        targets = extract_redirect_urls_from_html(html, base_url="https://t.cn/AXInWTJ4")

        self.assertIn("https://t.cn/jump/final", targets)
        self.assertIn("https://t.cn/script/final", targets)
        self.assertIn("https://pan.baidu.com/s/abc123", targets)

    def test_extract_redirect_urls_from_refresh_header_supports_relative_url(self) -> None:
        targets = extract_redirect_urls_from_refresh_header(
            "0; url=/jump/final",
            base_url="https://weibo.cn/sinaurl?u=abc",
        )

        self.assertEqual(targets, ["https://weibo.cn/jump/final"])

    def test_fetch_redirect_target_prefers_get_for_force_get_domains(self) -> None:
        session = _FakeSession(
            head_response=_FakeResponse("https://pan.baidu.com/s/from-head"),
            get_response=_FakeResponse(
                "https://t.cn/AXInWTJ4",
                headers={"Content-Type": "text/html"},
                body='<meta http-equiv="refresh" content="0;url=https://pan.baidu.com/s/final">',
            ),
        )

        final_url, html_targets = asyncio.run(
            fetch_redirect_target(
                "https://t.cn/AXInWTJ4",
                session,
                resolver_config={"force_get_domains": ["t.cn"], "max_redirect_hops": 6},
            )
        )

        self.assertEqual(final_url, "https://t.cn/AXInWTJ4")
        self.assertEqual(session.calls[0], "get:https://t.cn/AXInWTJ4:6")
        self.assertIn("https://pan.baidu.com/s/final", html_targets)


if __name__ == "__main__":
    unittest.main()

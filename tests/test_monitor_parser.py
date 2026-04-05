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
    resolve_netdisk_url,
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

    def test_parse_movie_message_content_omits_redundant_netdisk_alias_link_labels(self) -> None:
        message = "\n".join(
            [
                "测试影片 (2026)",
                "百度",
                "https://pan.baidu.com/s/test123?pwd=abcd",
                "迅雷",
                "https://pan.xunlei.com/s/test456#",
            ]
        )

        with patch(
            "app.core.monitor_parser.resolve_message_urls",
            return_value=(
                {
                    "https://pan.baidu.com/s/test123?pwd=abcd": "https://pan.baidu.com/s/test123?pwd=abcd",
                    "https://pan.xunlei.com/s/test456#": "https://pan.xunlei.com/s/test456#",
                },
                0,
            ),
        ):
            parsed, diagnostics = asyncio.run(parse_message_content(message, channel_name="gotopan"))

        self.assertEqual(parsed["links"]["百度网盘"][0]["label"], None)
        self.assertEqual(parsed["links"]["迅雷"][0]["label"], None)
        self.assertEqual(diagnostics.extracted_link_count, 2)

    def test_parse_movie_message_content_does_not_use_synopsis_sentence_as_link_label(self) -> None:
        message = "\n".join(
            [
                "名称：最强大脑 第十三季 最强大脑13 (2026)",
                "",
                "描述：《最强大脑第十三季》是江苏卫视推出的节目，于2026年1月16日起每周五晚20:20在该台首播。",
                "节目以“十三启新局，智弈聚锋芒”为主题，围绕计算精准度、推理能力和观察细微度三个维度设计挑战项目，提出“不止挑战极限，更要定义极限”的竞技目标。",
                "",
                "链接：https://pan.quark.cn/s/277e22f4db93",
                "",
                "🏷 标签：#真人秀 #最强大脑",
            ]
        )

        with patch(
            "app.core.monitor_parser.resolve_message_urls",
            return_value=({"https://pan.quark.cn/s/277e22f4db93": "https://pan.quark.cn/s/277e22f4db93"}, 0),
        ):
            parsed, diagnostics = asyncio.run(
                parse_message_content(message, channel_name="+eQXY7Ewx-4I4NDFl")
            )

        self.assertEqual(parsed["links"]["夸克网盘"][0]["label"], None)
        self.assertEqual(diagnostics.extracted_link_count, 1)

    def test_parse_movie_message_content_keeps_only_synopsis_when_explicit_intro_exists(self) -> None:
        message = "\n".join(
            [
                "🎬 申医生 (2026) 已更新",
                "",
                "🎭 类型：日韩剧",
                "⭐ TMDB评分：10.0/10",
                "📹 画质：1080p",
                "📺 质量：friDay WEB-DL AAC.2.0",
                "📼 集数：共 1 集",
                "📦 大小：4.75GB",
                "👤 分享：热心网友",
                "",
                "S01 E07 1080P friDay WEB-DL AAC.2.0 内封简繁字幕",
                "",
                "📖 简介：",
                "剧集讲述挑战神之领域的外科医师，爱上因事故而陷入脑昏迷的知名女星，以及她现在所爱的男人之间，交织着爱情与欲望、禁忌与牺牲的奇异爱情惊悚医疗剧。",
                "",
                "📢频道：123云盘资源收藏频道",
                "🚀社区：点击查看",
                "🏷️标签：#申医生 #日韩剧 #剧情",
            ]
        )

        with patch("app.core.monitor_parser.resolve_message_urls", return_value=({}, 0)):
            parsed, _ = asyncio.run(parse_message_content(message, channel_name="xx123pan"))

        self.assertEqual(
            parsed["description"],
            "剧集讲述挑战神之领域的外科医师，爱上因事故而陷入脑昏迷的知名女星，以及她现在所爱的男人之间，交织着爱情与欲望、禁忌与牺牲的奇异爱情惊悚医疗剧。",
        )
        self.assertNotIn("类型", parsed["description"])
        self.assertNotIn("TMDB评分", parsed["description"])
        self.assertNotIn("社区", parsed["description"])

    def test_parse_movie_message_content_falls_back_to_movie_metadata_when_synopsis_missing(self) -> None:
        message = "\n".join(
            [
                "🎥 过去，如今和之后 (2022)",
                "",
                "⭐️ 评分：6.8",
                "🏷 类型：剧情 / 历史",
                "👥 主演：Happy Salma / Laura Basuki / Ibnu Jamil",
                "🔖 标签: #过去如今和之后 #电影",
                "🤖 投稿：@tpbox_bot",
                "🔍 搜索：@sougou115",
                "✈️ 机场：红杏云 | 糖果云",
                "📺 公费服：蘑菇Emby媒体库",
            ]
        )

        with patch("app.core.monitor_parser.resolve_message_urls", return_value=({}, 0)):
            parsed, _ = asyncio.run(parse_message_content(message, channel_name="Lsp115"))

        self.assertEqual(
            parsed["description"],
            "评分: 6.8\n类型: 剧情 / 历史\n主演: Happy Salma / Laura Basuki / Ibnu Jamil",
        )
        self.assertNotIn("机场", parsed["description"])
        self.assertNotIn("公费服", parsed["description"])

    def test_parse_movie_message_content_stops_multiline_intro_before_download_section(self) -> None:
        message = "\n".join(
            [
                "【标题】：【电视剧】猎罪图鉴2-2024年剧情片",
                "",
                "【描述】：",
                "第二季也将承继“绘色显影，画见人心”这一故事内核，在对画像的勾描中使得复杂的人心显影，洞悉幽微人性、照见人间现实。",
                "在模拟画像师沈翊（檀健次 饰）、刑警队长杜城（金世佳 饰）等人组成的猎罪小分队的共同努力下，第二季的故事将继续拆解人性谜题，围猎罪案真凶。",
                "",
                "👇下载地址👇",
                "https://pan.xunlei.com/s/VObQ-UhSsYKeJvXg9AQx041JA1?pwd=dgwj#",
                "",
                "📂 类    型： #影视 #迅雷云盘",
                "🏷️ 标    签：#剧情 #悬疑 #犯罪",
                "🙍 来    自： 热心盘友",
                "📢 频    道： @gotopan",
                "👥 群    组： @panyouquan",
                "🤖 搜资源： @kksou_bot",
            ]
        )

        with patch(
            "app.core.monitor_parser.resolve_message_urls",
            return_value=({"https://pan.xunlei.com/s/VObQ-UhSsYKeJvXg9AQx041JA1?pwd=dgwj#": "https://pan.xunlei.com/s/VObQ-UhSsYKeJvXg9AQx041JA1?pwd=dgwj#"}, 0),
        ):
            parsed, _ = asyncio.run(parse_message_content(message, channel_name="gotopan"))

        self.assertEqual(
            parsed["description"],
            "第二季也将承继“绘色显影，画见人心”这一故事内核，在对画像的勾描中使得复杂的人心显影，洞悉幽微人性、照见人间现实。\n在模拟画像师沈翊（檀健次 饰）、刑警队长杜城（金世佳 饰）等人组成的猎罪小分队的共同努力下，第二季的故事将继续拆解人性谜题，围猎罪案真凶。",
        )
        self.assertNotIn("下载地址", parsed["description"])
        self.assertNotIn("来 自", parsed["description"])

    def test_parse_movie_message_content_filters_variant_and_promo_tail_from_description(self) -> None:
        message = "\n".join(
            [
                "神与律师事务所 (2026)",
                "1080p NF S01E01 - E08 内封简中 HiveWeb",
                "",
                "简介：「申二朗」律师在旧巫堂开设法律事务所后，开始看得见鬼魂。虽然外表沉稳可靠，但实际上胆小又有些冒失；然而在面对带着冤屈的鬼魂委托人时，却展现出谁也无法动摇的坚定气度。",
                "",
                "分享：Pluto",
                "大小：6GB",
                "链接：直达链接",
                "网址：神与律师事务所 (2026)",
                "",
                "标签：#剧情 #悬疑",
                "",
                "🔥： 阿里云盘播放神器: VidHub",
            ]
        )

        with patch("app.core.monitor_parser.resolve_message_urls", return_value=({}, 0)):
            parsed, _ = asyncio.run(parse_message_content(message, channel_name="bdwpzhpd"))

        self.assertEqual(
            parsed["description"],
            "「申二朗」律师在旧巫堂开设法律事务所后，开始看得见鬼魂。虽然外表沉稳可靠，但实际上胆小又有些冒失；然而在面对带着冤屈的鬼魂委托人时，却展现出谁也无法动摇的坚定气度。",
        )
        self.assertNotIn("1080p", parsed["description"])
        self.assertNotIn("VidHub", parsed["description"])
        self.assertNotIn("直达链接", parsed["description"])

    def test_parse_movie_message_content_filters_dmca_noise_inside_description_block(self) -> None:
        message = "\n".join(
            [
                "名称：测试电影 (2026)",
                "",
                "简介：这是第一段剧情简介。",
                "标签 ⚠️ 版权：版权反馈/DMCA",
                "链接：https://pan.quark.cn/s/testdmca123",
                "🏷 标签：#剧情",
            ]
        )

        with patch(
            "app.core.monitor_parser.resolve_message_urls",
            return_value=({"https://pan.quark.cn/s/testdmca123": "https://pan.quark.cn/s/testdmca123"}, 0),
        ):
            parsed, _ = asyncio.run(parse_message_content(message, channel_name="+eQXY7Ewx-4I4NDFl"))

        self.assertEqual(parsed["description"], "这是第一段剧情简介。")
        self.assertNotIn("DMCA", parsed["description"])
        self.assertNotIn("版权反馈", parsed["description"])

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

    def test_fetch_redirect_target_prefers_get_for_telegra_domain_by_default(self) -> None:
        session = _FakeSession(
            head_response=_FakeResponse("https://telegra.ph/sample-page"),
            get_response=_FakeResponse(
                "https://telegra.ph/sample-page",
                headers={"Content-Type": "text/html"},
                body='<a href="https://115cdn.com/s/sample123?password=abcd">查看链接</a>',
            ),
        )

        final_url, html_targets = asyncio.run(
            fetch_redirect_target(
                "https://telegra.ph/sample-page",
                session,
            )
        )

        self.assertEqual(final_url, "https://telegra.ph/sample-page")
        self.assertEqual(session.calls[0], "get:https://telegra.ph/sample-page:8")
        self.assertIn("https://115cdn.com/s/sample123?password=abcd", html_targets)

    def test_resolve_netdisk_url_extracts_115_link_from_telegra_page(self) -> None:
        session = _FakeSession(
            head_response=_FakeResponse("https://telegra.ph/sample-page"),
            get_response=_FakeResponse(
                "https://telegra.ph/sample-page",
                headers={"Content-Type": "text/html"},
                body='<a href="https://115cdn.com/s/sample123?password=abcd">查看链接</a>',
            ),
        )

        resolved_url = asyncio.run(
            resolve_netdisk_url(
                "https://telegra.ph/sample-page",
                [(["115cdn.com", "115.com"], "115网盘")],
                [],
                session,
            )
        )

        self.assertEqual(resolved_url, "https://115cdn.com/s/sample123?password=abcd")


if __name__ == "__main__":
    unittest.main()

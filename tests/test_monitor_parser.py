from __future__ import annotations

import asyncio
import unittest

from app.core.monitor_parser import extract_embedded_redirect_targets, parse_message_content
from app.core.monitor_rules import load_monitor_rules


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


if __name__ == "__main__":
    unittest.main()

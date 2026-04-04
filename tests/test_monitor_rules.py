from __future__ import annotations

import unittest

from app.core.monitor_rules import resolve_channel_profile


class MonitorRulesTestCase(unittest.TestCase):
    def test_channel_profile_merges_default_rules(self) -> None:
        rules = {
            "profiles": {
                "default": {
                    "title_fields": ["名称"],
                    "metadata": {"source": ["来源"], "bot": ["投稿"]},
                    "valid_labels": ["主链"],
                    "regions": ["北京"],
                },
                "custom": {
                    "title_fields": ["课程名"],
                    "metadata": {"source": ["作者"]},
                    "valid_labels": ["主链", "备用"],
                    "course_keywords": ["事业单位"],
                },
            },
            "channel_profiles": {"custom-channel": "custom"},
        }

        profile = resolve_channel_profile("custom-channel", rules)

        self.assertEqual(profile["title_fields"], ["课程名"])
        self.assertEqual(profile["metadata"]["source"], ["作者"])
        self.assertEqual(profile["metadata"]["bot"], ["投稿"])
        self.assertIn("备用", profile["valid_labels"])
        self.assertIn("事业单位", profile["course_keywords"])


if __name__ == "__main__":
    unittest.main()

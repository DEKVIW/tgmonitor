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
                    "intermediate_netdisk_domains": {"百度网盘": ["jump.example.com"]},
                },
                "custom": {
                    "title_fields": ["课程名"],
                    "metadata": {"source": ["作者"]},
                    "valid_labels": ["主链", "备用"],
                    "course_keywords": ["事业单位"],
                    "intermediate_netdisk_domains": {"夸克网盘": ["go.example.com"]},
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
        self.assertEqual(profile["intermediate_netdisk_domains"]["夸克网盘"], ["go.example.com"])
        self.assertEqual(profile["intermediate_netdisk_domains"]["百度网盘"], ["jump.example.com"])


    def test_channel_profile_can_match_by_channel_id(self) -> None:
        rules = {
            "profiles": {
                "default": {
                    "title_fields": ["名称"],
                    "metadata": {"source": ["来源"]},
                    "valid_labels": ["主链"],
                },
                "id-bound": {
                    "title_fields": ["课程名"],
                    "course_keywords": ["面试"],
                },
            },
            "channel_profiles": {"legacy-name": "legacy"},
            "channel_profile_ids": {"1730775689": "id-bound"},
        }

        profile = resolve_channel_profile("wpzyk-new-name", rules, channel_id=1730775689)

        self.assertEqual(profile["title_fields"], ["课程名"])
        self.assertIn("面试", profile["course_keywords"])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from app.services.resource_identity import compare_follow_candidate, parse_resource_identity


class ResourceIdentityParserTests(unittest.TestCase):
    def test_provider_label_cannot_override_real_message_title(self) -> None:
        identity = parse_resource_identity(
            "国剧 《黑岛监狱》（2026）剧情 / 悬疑 / 犯罪 夸克网盘",
            alternate_titles=["夸克网盘"],
        )

        self.assertEqual(identity.core_title, "黑岛监狱")
        self.assertFalse(identity.should_skip_ai)

    def test_standalone_provider_label_is_not_a_work(self) -> None:
        identity = parse_resource_identity("夸克网盘")

        self.assertIsNone(identity.core_title)
        self.assertTrue(identity.should_skip_ai)
        self.assertEqual(identity.reason, "link_platform_label")

    def test_generic_episode_words_do_not_become_identity_keys(self) -> None:
        identity = parse_resource_identity(
            "月鳞绮纪 更22集",
            alternate_titles=["集", "更新"],
        )

        self.assertNotIn("集", identity.aliases)
        self.assertNotIn("更新", identity.aliases)
        self.assertNotIn("集", identity.normalized_keys)
        self.assertNotIn("更新", identity.normalized_keys)

    def test_different_works_do_not_promote_by_episode_number(self) -> None:
        tracked = parse_resource_identity("大主宰 更95集")
        candidate = parse_resource_identity("斗破苍穹 更215集")

        decision = compare_follow_candidate(tracked, candidate)

        self.assertFalse(decision.is_same_work)
        self.assertFalse(decision.should_promote)

    def test_metadata_words_do_not_become_shared_aliases(self) -> None:
        tracked = parse_resource_identity(
            "尚公主 (2026) 更至04集 60帧 类型: 剧情/爱情/古装 主演: 孟子义/李昀锐"
        )
        candidate = parse_resource_identity(
            "嫁金钗 (2026) 更至16集 60帧 类型: 剧情/爱情/古装 主演: 田曦薇/闫桉"
        )

        self.assertEqual(tracked.core_title, "尚公主")
        self.assertEqual(candidate.core_title, "嫁金钗")
        self.assertNotIn("古装 主演", tracked.aliases)
        self.assertNotIn("古装 主演", candidate.aliases)
        self.assertNotIn("古装 主演", tracked.search_queries)
        self.assertFalse(compare_follow_candidate(tracked, candidate).is_same_work)

    def test_same_core_title_replaces_same_episode_source(self) -> None:
        tracked = parse_resource_identity("尚公主 (2026) 更至04集")
        candidate = parse_resource_identity("尚公主 2026 更新04集 60帧")

        decision = compare_follow_candidate(tracked, candidate)

        self.assertTrue(decision.is_same_work)
        self.assertFalse(decision.should_promote)
        self.assertTrue(decision.same_episode_replace)

    def test_same_core_title_promotes_newer_episode(self) -> None:
        tracked = parse_resource_identity("尚公主 (2026) 更至04集")
        candidate = parse_resource_identity("尚公主 2026 更新05集")

        decision = compare_follow_candidate(tracked, candidate)

        self.assertTrue(decision.is_same_work)
        self.assertTrue(decision.is_newer)
        self.assertTrue(decision.should_promote)

    def test_same_core_title_skips_older_episode(self) -> None:
        tracked = parse_resource_identity("尚公主 (2026) 更至04集")
        candidate = parse_resource_identity("尚公主 2026 更新03集")

        decision = compare_follow_candidate(tracked, candidate)

        self.assertTrue(decision.is_same_work)
        self.assertFalse(decision.should_promote)
        self.assertFalse(decision.same_episode_replace)

    def test_core_title_suffix_is_not_the_same_work(self) -> None:
        tracked = parse_resource_identity("尚公主 (2026) 更至04集")
        candidate = parse_resource_identity("尚公主外传 (2026) 更至08集")

        decision = compare_follow_candidate(tracked, candidate)

        self.assertFalse(decision.is_same_work)
        self.assertFalse(decision.should_promote)

    def test_same_core_title_with_different_year_is_not_the_same_work(self) -> None:
        tracked = parse_resource_identity("边水往事 (2024) 更至16集")
        candidate = parse_resource_identity("边水往事 (2026) 更至18集")

        decision = compare_follow_candidate(tracked, candidate)

        self.assertFalse(decision.is_same_work)
        self.assertFalse(decision.should_promote)


if __name__ == "__main__":
    unittest.main()

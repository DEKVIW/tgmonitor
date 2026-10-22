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


if __name__ == "__main__":
    unittest.main()

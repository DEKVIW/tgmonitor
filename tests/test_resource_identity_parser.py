from __future__ import annotations

import unittest

from app.services.resource_identity import parse_resource_identity


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


if __name__ == "__main__":
    unittest.main()

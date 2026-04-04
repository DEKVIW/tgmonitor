from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.services import user_service


class UserServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._original_file = user_service.USER_DATA_FILE
        self._tempdir = tempfile.TemporaryDirectory()
        user_service.USER_DATA_FILE = str(Path(self._tempdir.name) / "users.json")

    def tearDown(self) -> None:
        user_service.USER_DATA_FILE = self._original_file
        self._tempdir.cleanup()

    def test_preserves_last_admin(self) -> None:
        self.assertTrue(user_service.add_user("admin", "secret123", role="admin"))
        self.assertFalse(user_service.change_user_role("admin", "user"))
        self.assertFalse(user_service.remove_user("admin"))

    def test_bulk_remove_keeps_one_admin(self) -> None:
        self.assertTrue(user_service.add_user("admin", "secret123", role="admin"))
        self.assertTrue(user_service.add_user("alice", "secret123", role="admin"))
        self.assertTrue(user_service.add_user("bob", "secret123", role="user"))

        result = user_service.bulk_remove_users(["alice", "admin", "missing"])
        self.assertEqual(result["successes"], ["alice"])
        self.assertEqual({item["username"] for item in result["failures"]}, {"admin", "missing"})

        users = json.loads(Path(user_service.USER_DATA_FILE).read_text(encoding="utf-8"))
        self.assertIn("admin", users)
        self.assertIn("bob", users)


if __name__ == "__main__":
    unittest.main()

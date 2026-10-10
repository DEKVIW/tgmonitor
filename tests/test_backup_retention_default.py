from __future__ import annotations

import unittest

from app.models.models import BackupTarget
from app.schemas.backup_models import BackupTargetCreate


class BackupRetentionDefaultTests(unittest.TestCase):
    def test_new_backup_targets_keep_one_backup_by_default(self) -> None:
        target = BackupTargetCreate(name="test", local_dir="/tmp/backups")
        self.assertEqual(target.retention_count, 1)
        self.assertEqual(BackupTarget.retention_count.property.columns[0].default.arg, 1)


if __name__ == "__main__":
    unittest.main()

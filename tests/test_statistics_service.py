from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace

os.environ.setdefault("TELEGRAM_API_ID", "1")
os.environ.setdefault("TELEGRAM_API_HASH", "hash")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/testdb")
os.environ.setdefault("DEFAULT_CHANNELS", "")
os.environ.setdefault("SECRET_SALT", "test-salt")

from app.services.statistics_service import get_activity_heatmap


class _FakeExecuteResult:
    def __init__(self, rows) -> None:
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDb:
    def __init__(self, rows) -> None:
        self.rows = rows
        self.last_params = None

    def execute(self, statement, params=None):
        del statement
        self.last_params = params or {}
        return _FakeExecuteResult(self.rows)


class StatisticsServiceTestCase(unittest.TestCase):
    def test_get_activity_heatmap_fills_missing_hours_and_tracks_peak(self) -> None:
        today = datetime.now().date()
        start_date = today - timedelta(days=2)
        rows = [
            SimpleNamespace(date=start_date, hour=8, message_count=2),
            SimpleNamespace(date=today, hour=22, message_count=5),
        ]
        db = _FakeDb(rows)

        result = get_activity_heatmap(db, days=3)

        self.assertEqual(result["dates"], [start_date.isoformat(), (today - timedelta(days=1)).isoformat(), today.isoformat()])
        self.assertEqual(result["hours"], list(range(24)))
        self.assertEqual(len(result["cells"]), 72)
        self.assertEqual(result["max_count"], 5)
        self.assertEqual(
            db.last_params["start_time"],
            datetime.combine(start_date, datetime.min.time()),
        )

        cells = {
            (cell["date"], cell["hour"]): cell["message_count"]
            for cell in result["cells"]
        }
        self.assertEqual(cells[(start_date.isoformat(), 8)], 2)
        self.assertEqual(cells[(today.isoformat(), 22)], 5)
        self.assertEqual(cells[((today - timedelta(days=1)).isoformat(), 8)], 0)


if __name__ == "__main__":
    unittest.main()

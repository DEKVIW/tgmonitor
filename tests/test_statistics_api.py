from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("TELEGRAM_API_ID", "1")
os.environ.setdefault("TELEGRAM_API_HASH", "hash")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/testdb")
os.environ.setdefault("DEFAULT_CHANNELS", "")
os.environ.setdefault("SECRET_SALT", "test-salt")

from app.api import statistics as statistics_api


class StatisticsApiTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_get_activity_heatmap_public_guest_caps_days_to_seven(self) -> None:
        fake_db = object()
        payload = {
            "dates": ["2026-04-01", "2026-04-02"],
            "hours": list(range(24)),
            "cells": [
                {"date": "2026-04-01", "hour": 8, "message_count": 3},
            ],
            "max_count": 3,
        }
        with (
            patch("app.api.statistics.is_public_dashboard_enabled", return_value=True),
            patch("app.api.statistics.get_activity_heatmap", return_value=payload) as mocked_get_activity_heatmap,
        ):
            response = await statistics_api.get_activity_heatmap_api(
                days=14,
                db=fake_db,
                current_user=None,
            )

        mocked_get_activity_heatmap.assert_called_once_with(fake_db, days=7)
        self.assertEqual(response.max_count, 3)
        self.assertEqual(response.cells[0].message_count, 3)


if __name__ == "__main__":
    unittest.main()

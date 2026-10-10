from __future__ import annotations

from datetime import date, timedelta
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Query, Session

from app.services.resource_ops.workbench import (
    _build_workbench_candidate_target_ids,
    _load_workbench_candidate_rows,
)


class ResourceOpsWorkbenchQueryScopeTests(unittest.TestCase):
    def test_candidate_scope_keeps_recent_clicks_and_saved_profiles(self) -> None:
        engine = create_engine("sqlite://")
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE link_targets (id INTEGER PRIMARY KEY, platform TEXT NOT NULL)"))
            connection.execute(text("CREATE TABLE link_target_daily_stats (link_target_id INTEGER NOT NULL, stat_date DATE NOT NULL)"))
            connection.execute(text("CREATE TABLE resource_candidate_profiles (link_target_id INTEGER NOT NULL)"))
            connection.execute(
                text(
                    "INSERT INTO link_targets (id, platform) VALUES "
                    "(1, 'quark'), (2, 'baidu'), (3, 'quark'), (4, 'quark'), (5, 'baidu')"
                )
            )
            connection.execute(
                text("INSERT INTO link_target_daily_stats (link_target_id, stat_date) VALUES (:target, :day)"),
                [
                    {"target": 1, "day": date.today()},
                    {"target": 3, "day": date.today() - timedelta(days=31)},
                    {"target": 4, "day": date.today()},
                    {"target": 5, "day": date.today()},
                ],
            )
            connection.execute(
                text("INSERT INTO resource_candidate_profiles (link_target_id) VALUES (2), (4), (99)")
            )

        with Session(engine) as session:
            all_candidates = _build_workbench_candidate_target_ids(
                start=date.today() - timedelta(days=29),
                platform=None,
            )
            quark_candidates = _build_workbench_candidate_target_ids(
                start=date.today() - timedelta(days=29),
                platform="quark",
            )

            self.assertEqual(
                session.scalars(select(all_candidates.c.link_target_id).order_by(all_candidates.c.link_target_id)).all(),
                [1, 2, 4, 5],
            )
            self.assertEqual(
                session.scalars(select(quark_candidates.c.link_target_id).order_by(quark_candidates.c.link_target_id)).all(),
                [1, 4],
            )
        engine.dispose()

    def test_aggregates_are_scoped_to_candidate_ids_and_urls(self) -> None:
        class CapturingQuery(Query):
            def all(self):
                self.session.captured_workbench_sql = str(
                    self.statement.compile(dialect=postgresql.dialect())
                )
                return []

        engine = create_engine("sqlite://")
        session = Session(bind=engine, query_cls=CapturingQuery)
        with patch("app.services.resource_ops.workbench.ensure_runtime_storage_tables"):
            self.assertEqual(_load_workbench_candidate_rows(session), [])

        sql = session.captured_workbench_sql
        self.assertGreaterEqual(sql.count("workbench_candidate_target_ids"), 7)
        self.assertGreaterEqual(sql.count("workbench_candidate_urls"), 3)
        session.close()
        engine.dispose()


if __name__ == "__main__":
    unittest.main()

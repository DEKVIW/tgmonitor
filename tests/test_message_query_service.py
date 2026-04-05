from __future__ import annotations

import os
import unittest
from types import SimpleNamespace

from sqlalchemy.dialects import postgresql

os.environ.setdefault("TELEGRAM_API_ID", "1")
os.environ.setdefault("TELEGRAM_API_HASH", "hash")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/testdb")
os.environ.setdefault("DEFAULT_CHANNELS", "")
os.environ.setdefault("SECRET_SALT", "test-salt")

from app.models.models import Message
from app.services import message_query_service


def _compile_sql(expression) -> str:
    return str(
        expression.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


class FakeQuery:
    def __init__(self, records):
        self.records = list(records)
        self.filters = []
        self.order_by_args = ()
        self.offset_value = None
        self.limit_value = None

    def filter(self, *criteria):
        self.filters.extend(criteria)
        return self

    def order_by(self, *clauses):
        self.order_by_args = clauses
        return self

    def offset(self, value):
        self.offset_value = value
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def all(self):
        return list(self.records)

    def count(self):
        return len(self.records)


class FakeSession:
    def __init__(self, query):
        self.query_obj = query
        self.query_model = None

    def query(self, model):
        self.query_model = model
        return self.query_obj


class MessageQueryServiceTestCase(unittest.TestCase):
    def test_split_search_terms_trims_and_deduplicates(self) -> None:
        self.assertEqual(
            message_query_service._split_search_terms("  完美世界   完美世界  夸克 "),
            ["完美世界", "夸克"],
        )

    def test_build_search_match_condition_requires_all_terms(self) -> None:
        condition = message_query_service._build_search_match_condition(["完美", "世界"])
        compiled = _compile_sql(condition)

        self.assertIn(" AND ", compiled)
        self.assertIn("%完美%", compiled)
        self.assertIn("%世界%", compiled)

    def test_build_search_rank_expression_prioritizes_title_before_description(self) -> None:
        rank = message_query_service._build_search_rank_expression(["完美世界"])
        compiled = _compile_sql(rank)

        self.assertIn("10000", compiled)
        self.assertIn("3000", compiled)
        self.assertIn("1200", compiled)
        self.assertIn("500", compiled)
        self.assertIn("120", compiled)
        self.assertIn("80", compiled)
        self.assertIn("messages.title", compiled)
        self.assertIn("messages.description", compiled)

    def test_get_filtered_messages_orders_by_rank_then_timestamp_when_searching(self) -> None:
        fake_query = FakeQuery([SimpleNamespace(id=1), SimpleNamespace(id=2)])
        session = FakeSession(fake_query)

        messages, total, max_page = message_query_service.get_filtered_messages(
            db=session,
            search_query="完美世界",
            page=1,
            page_size=1,
        )

        self.assertIs(session.query_model, Message)
        self.assertEqual([message.id for message in messages], [1])
        self.assertEqual(total, 2)
        self.assertEqual(max_page, 2)
        self.assertEqual(fake_query.offset_value, 0)
        self.assertEqual(fake_query.limit_value, 2)
        self.assertEqual(len(fake_query.order_by_args), 2)
        self.assertIn("CASE", _compile_sql(fake_query.order_by_args[0]))
        self.assertIn("messages.timestamp DESC", _compile_sql(fake_query.order_by_args[1]))

    def test_get_filtered_messages_orders_by_timestamp_only_without_search(self) -> None:
        fake_query = FakeQuery([SimpleNamespace(id=1)])
        session = FakeSession(fake_query)

        messages, total, max_page = message_query_service.get_filtered_messages(
            db=session,
            search_query=None,
            page=1,
            page_size=10,
        )

        self.assertEqual([message.id for message in messages], [1])
        self.assertEqual(total, 1)
        self.assertEqual(max_page, 1)
        self.assertEqual(len(fake_query.order_by_args), 1)
        self.assertIn("messages.timestamp DESC", _compile_sql(fake_query.order_by_args[0]))


if __name__ == "__main__":
    unittest.main()

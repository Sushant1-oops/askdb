import math
import sqlite3
import unittest
from datetime import date, datetime
from decimal import Decimal

from config import Settings
from services.insight import heuristic_chart, validate_chart
from services.judge import compute_signals, parse_verdict
from services.llm_client import parse_json_object, strip_reasoning
from services.schema import ColumnInfo, ForeignKey, SchemaContext, TableInfo
from services.schema_linker import select_tables
from services.sql_generator import extract_sql, parse_generation
from services.sql_runtime import clean_db_error, dedupe_columns, json_safe, run_select
from services.errors import QueryExecutionError


class Runtime(unittest.TestCase):
    def test_json_safe(self):
        self.assertIsNone(json_safe(float("nan")))
        self.assertIsNone(json_safe(Decimal("NaN")))
        self.assertEqual(json_safe(Decimal("1.5")), 1.5)
        self.assertEqual(json_safe(2**60), str(2**60))
        self.assertEqual(json_safe(date(2024, 1, 2)), "2024-01-02")
        self.assertEqual(json_safe(datetime(2024, 1, 2, 3, 4)), "2024-01-02T03:04:00")
        self.assertEqual(json_safe(b"\x01\x02"), "0x0102")
        self.assertTrue(math.isfinite(json_safe(1e300)))

    def test_dedupe(self):
        self.assertEqual(dedupe_columns(["id", "id", "name", "id"]), ["id", "id_2", "name", "id_3"])

    def test_duplicate_columns_survive(self):
        c = sqlite3.connect(":memory:")
        c.executescript("create table a(id int); create table b(id int); insert into a values(1); insert into b values(2);")
        r = run_select(c, "select a.id, b.id from a, b", 10)
        self.assertEqual(r.rows, [{"id": 1, "id_2": 2}])

    def test_percent_and_colon_are_safe(self):
        c = sqlite3.connect(":memory:")
        r = run_select(c, "select 'a%b :x' as v", 10)
        self.assertEqual(r.rows[0]["v"], "a%b :x")

    def test_error_cleaning(self):
        e = Exception("(sqlite3.OperationalError) no such column: x\n[SQL: select x]\n(Background on this error at: https://sqlalche.me/e/20/e3q8)")
        self.assertEqual(clean_db_error(e), "no such column: x")
        with self.assertRaises(QueryExecutionError):
            run_select(sqlite3.connect(":memory:"), "select nope", 5)


def _schema(n_extra=0):
    s = SchemaContext("d", "sqlite")
    s.tables["customers"] = TableInfo("customers", columns=[ColumnInfo("customer_id", "INT", False, True), ColumnInfo("country", "TEXT")])
    s.tables["orders"] = TableInfo("orders", columns=[ColumnInfo("order_id", "INT", False, True), ColumnInfo("customer_id", "INT"), ColumnInfo("total_amount", "REAL")],
                                   foreign_keys=[ForeignKey(["customer_id"], "customers", ["customer_id"])])
    for i in range(n_extra):
        s.tables[f"misc_{i}"] = TableInfo(f"misc_{i}", columns=[ColumnInfo("blob", "TEXT")])
    return s


class Linker(unittest.TestCase):
    def test_small_schema_sent_whole(self):
        self.assertEqual(select_tables(_schema(), "anything"), ["customers", "orders"])

    def test_large_schema_picks_relevant_and_fk_neighbours(self):
        chosen = select_tables(_schema(30), "total amount of orders", max_tables=6)
        self.assertIn("orders", chosen)
        self.assertIn("customers", chosen)  
        self.assertLessEqual(len(chosen), 6)

    def test_plural_stemming(self):
        self.assertIn("customers", select_tables(_schema(30), "which customer is best", max_tables=5))


class Charts(unittest.TestCase):
    rows = [{"cat": "a", "n": 1}, {"cat": "b", "n": 2}, {"cat": "c", "n": 3}]

    def test_valid_spec_kept(self):
        spec = validate_chart({"type": "bar", "xKey": "cat", "yKeys": ["n"], "title": "T"}, ["cat", "n"], self.rows)
        self.assertEqual(spec["type"], "bar")

    def test_invalid_falls_back(self):
        spec = validate_chart({"type": "bar", "xKey": "zzz", "yKeys": ["n"]}, ["cat", "n"], self.rows)
        self.assertEqual(spec["xKey"], "cat")

    def test_non_numeric_y_rejected(self):
        spec = validate_chart({"type": "bar", "xKey": "n", "yKeys": ["cat"]}, ["cat", "n"], self.rows)
        self.assertEqual(spec["yKeys"], ["n"])

    def test_pie_with_many_slices_becomes_bar(self):
        rows = [{"c": str(i), "n": i} for i in range(12)]
        self.assertEqual(validate_chart({"type": "pie", "xKey": "c", "yKeys": ["n"]}, ["c", "n"], rows)["type"], "bar")

    def test_none_and_tiny_results(self):
        self.assertIsNone(validate_chart({"type": "none"}, ["cat", "n"], self.rows))
        self.assertIsNone(validate_chart({"type": "bar", "xKey": "cat", "yKeys": ["n"]}, ["cat", "n"], self.rows[:1]))

    def test_time_series_is_line(self):
        rows = [{"month": f"2024-0{i}", "rev": i * 10} for i in range(1, 6)]
        self.assertEqual(heuristic_chart(["month", "rev"], rows)["type"], "line")


class Judge(unittest.TestCase):
    def test_parse_variants(self):
        v = parse_verdict('```json\n{"verdict":"PASS","score":0.9,"issues":[]}\n```', "m")
        self.assertEqual((v.verdict, v.score), ("pass", 0.9))
        v = parse_verdict('{"score": 0.3}', "m")
        self.assertEqual(v.verdict, "fail")
        self.assertIsNone(parse_verdict("nothing", "m"))
        v = parse_verdict('{"verdict":"pass","score":5}', "m")
        self.assertEqual(v.score, 1.0)

    def test_needs_revision(self):
        v = parse_verdict('{"verdict":"pass","score":0.5}', "m")
        self.assertTrue(v.needs_revision(0.7))
        self.assertFalse(parse_verdict('{"verdict":"pass","score":0.9}', "m").needs_revision(0.7))

    def test_signals(self):
        r = {"columns": ["a", "b"], "rows": [{"a": 1, "b": None}, {"a": 1, "b": None}]}
        sig = " ".join(compute_signals(r))
        self.assertIn("'b' is NULL", sig)
        self.assertIn("duplicate", sig)


class Parsing(unittest.TestCase):
    def test_think_blocks(self):
        self.assertEqual(strip_reasoning("<think>hmm</think>{\"a\":1}"), '{"a":1}')
        self.assertEqual(strip_reasoning("<think>never closed"), "")
        self.assertEqual(parse_json_object('<think>x</think>text {"a": {"b": "}"}} tail'), {"a": {"b": "}"}})

    def test_extract_sql(self):
        self.assertEqual(extract_sql("Here: SELECT 1; -- done"), "SELECT 1")
        self.assertEqual(extract_sql("no sql here"), "")

    def test_generation_defaults(self):
        g = parse_generation('{"sql": "SELECT 1"}', "m", "sqlite")
        self.assertTrue(g.ok)
        g = parse_generation('{"status":"ok","sql":""}', "m", "sqlite")
        self.assertEqual(g.status, "unanswerable")


class SettingsTest(unittest.TestCase):
    def test_placeholder_key_is_not_configured(self):
        self.assertFalse(Settings(groq_api_key="gsk_your_key_here").llm_configured)
        self.assertTrue(Settings(groq_api_key="gsk_realkey").llm_configured)

    def test_restricted_pattern(self):
        r = Settings().restricted_column_re
        for bad in ("password", "password_hash", "api_key", "user_token", "ssn", "credit_card"):
            self.assertTrue(r.search(bad), bad)
        for good in ("passenger", "passport_country", "tokens_used", "created_at", "description"):
            self.assertFalse(r.search(good), good)



class SuggestionsTest(unittest.TestCase):
    def test_demo_schema_suggestions(self):
        import os, tempfile
        from services.sample_data import create_sample_db
        from services.suggestions import suggest_questions
        from tests.support import SqliteBackend
        with tempfile.TemporaryDirectory() as d:
            db = SqliteBackend(create_sample_db(os.path.join(d, "x.db")), Settings())
            qs = suggest_questions(db.get_schema("c"))
        self.assertTrue(3 <= len(qs) <= 6)
        self.assertTrue(any("orders" in q for q in qs))
        self.assertFalse(any("password" in q.lower() for q in qs))


if __name__ == "__main__":
    unittest.main()

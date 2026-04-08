import sqlite3
import unittest
from pathlib import Path

from core.database import initialize_database


class DatabaseInitializationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_path = Path("test_artifacts/database/portfolio.db")
        if self.database_path.exists():
            self.database_path.unlink()
        if self.database_path.parent.exists():
            for path in sorted(self.database_path.parent.glob("**/*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()

    def tearDown(self) -> None:
        if self.database_path.exists():
            self.database_path.unlink()
        if self.database_path.parent.exists():
            for path in sorted(self.database_path.parent.glob("**/*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()

    def test_initialize_database_creates_spec_tables_with_expected_columns(self) -> None:
        initialize_database(self.database_path)

        with sqlite3.connect(self.database_path) as connection:
            table_names = {
                row[0]
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            }
            macro_columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(macro_views)")
            }

        self.assertTrue(self.database_path.exists())
        self.assertEqual(
            table_names,
            {
                "board_memos",
                "cma_results",
                "macro_views",
                "meta_feedback",
                "portfolio_proposals",
                "risk_reports",
            },
        )
        self.assertEqual(
            macro_columns,
            {
                "id",
                "timestamp",
                "regime",
                "confidence",
                "composite_score",
                "recession_probability",
                "scores_json",
                "key_indicators_json",
            },
        )

    def test_initialize_database_is_idempotent_and_preserves_existing_rows(self) -> None:
        initialize_database(self.database_path)
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO macro_views (
                    timestamp,
                    regime,
                    confidence,
                    composite_score,
                    recession_probability,
                    scores_json,
                    key_indicators_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "2026-04-09T12:00:00Z",
                    "late_cycle",
                    "medium",
                    0.7,
                    0.3,
                    '{"growth": 1}',
                    '{"vix": 18.5}',
                ),
            )
            connection.commit()

        initialize_database(self.database_path)

        with sqlite3.connect(self.database_path) as connection:
            row_count = connection.execute("SELECT COUNT(*) FROM macro_views").fetchone()[0]

        self.assertEqual(row_count, 1)


if __name__ == "__main__":
    unittest.main()

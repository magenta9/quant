import json
import sqlite3
import unittest
from pathlib import Path

from core.contracts import (
    CROBacktestMetrics,
    CROConcentrationMetrics,
    CROExAnteMetrics,
    CROFactorTilts,
    CROIPSDiagnostic,
    CRORiskReportOutput,
    CMAMethodEstimate,
    PortfolioProposalOutput,
)
from core.database import SchemaDriftError, initialize_database, persist_cma_methods, persist_portfolio_stage


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

    def test_initialize_database_adds_missing_columns_to_partial_table(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                CREATE TABLE macro_views (
                    id INTEGER PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    regime TEXT NOT NULL
                )
                """
            )
            connection.commit()

        initialize_database(self.database_path)

        with sqlite3.connect(self.database_path) as connection:
            macro_columns = [
                row[1]
                for row in connection.execute("PRAGMA table_info(macro_views)")
            ]

        self.assertEqual(
            macro_columns,
            [
                "id",
                "timestamp",
                "regime",
                "confidence",
                "composite_score",
                "recession_probability",
                "scores_json",
                "key_indicators_json",
            ],
        )

    def test_initialize_database_repairs_nonempty_partial_table_when_additive_migration_is_safe(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                CREATE TABLE macro_views (
                    id INTEGER PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    regime TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO macro_views (timestamp, regime)
                VALUES ('2026-04-09T12:00:00Z', 'late_cycle')
                """
            )
            connection.commit()

        initialize_database(self.database_path)

        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT
                    timestamp,
                    regime,
                    confidence,
                    composite_score,
                    recession_probability,
                    scores_json,
                    key_indicators_json
                FROM macro_views
                """
            ).fetchone()

        self.assertEqual(
            row,
            (
                "2026-04-09T12:00:00Z",
                "late_cycle",
                None,
                None,
                None,
                "{}",
                "{}",
            ),
        )

    def test_initialize_database_fails_loudly_when_required_nonnullable_column_cannot_be_added(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                CREATE TABLE cma_results (
                    id INTEGER PRIMARY KEY,
                    asset_slug TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO cma_results (asset_slug)
                VALUES ('us_large_cap')
                """
            )
            connection.commit()

        with self.assertRaisesRegex(SchemaDriftError, "missing required columns"):
            initialize_database(self.database_path)

    def test_persist_cma_methods_preserves_null_expected_return_for_stub_rows(self) -> None:
        initialize_database(self.database_path)

        persist_cma_methods(
            self.database_path,
            asset_slug="us_large_cap",
            timestamp="2026-04-09T12:00:00Z",
            methods=(
                CMAMethodEstimate(name="historical_erp", expected_return=0.08, confidence=0.6),
                CMAMethodEstimate(
                    name="inverse_gordon",
                    expected_return=None,
                    confidence=None,
                    available=False,
                    rationale="Structured stub.",
                ),
            ),
        )

        with sqlite3.connect(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT method, expected_return, confidence
                FROM cma_results
                ORDER BY method
                """
            ).fetchall()

        self.assertEqual(
            rows,
            [
                ("historical_erp", 0.08, 0.6),
                ("inverse_gordon", None, None),
            ],
        )

    def test_persist_portfolio_stage_stores_full_json_payloads(self) -> None:
        initialize_database(self.database_path)

        proposal = PortfolioProposalOutput(
            timestamp="2026-04-09T12:00:00Z",
            method="max_sharpe",
            category="return_optimized",
            weights={"us_large_cap": 0.55, "cash": 0.45},
            expected_return=0.071,
            expected_volatility=0.102,
            sharpe_ratio=0.5,
            max_drawdown=None,
            effective_n=1.98,
            concentration=0.505,
            metadata={"constraint_projection_applied": True},
        )
        risk_report = CRORiskReportOutput(
            method="max_sharpe",
            ex_ante=CROExAnteMetrics(
                volatility=0.102,
                portfolio_return=0.071,
                sharpe=0.5,
                var_95=-0.097,
                cvar_95=-0.14,
            ),
            backtest=CROBacktestMetrics(
                annual_return=0.065,
                annual_vol=0.11,
                sharpe=0.41,
                max_drawdown=-0.19,
                calmar=0.34,
                sortino_ratio=0.55,
            ),
            concentration=CROConcentrationMetrics(
                effective_n=1.98,
                herfindahl=0.505,
                top5_concentration=1.0,
                max_weight=0.55,
            ),
            factor_tilts=CROFactorTilts(
                equity_beta=0.55,
                duration=0.0,
                credit_spread=0.0,
                dollar_exposure=1.0,
            ),
            ips_compliance=CROIPSDiagnostic(
                tracking_error=0.08,
                within_tracking_budget=False,
                asset_bounds_ok=True,
                passes=False,
                violations=("optimizer raw weights breached IPS bounds; deterministic projection applied before reporting",),
                warnings=("optimizer weights were clipped before final reporting",),
            ),
        )

        persist_portfolio_stage(
            self.database_path,
            proposals=(proposal,),
            risk_reports=((proposal.timestamp, risk_report),),
        )

        with sqlite3.connect(self.database_path) as connection:
            stored_proposal = connection.execute(
                """
                SELECT method, category, weights_json, expected_return, expected_vol
                FROM portfolio_proposals
                """
            ).fetchone()
            stored_risk_report = connection.execute(
                """
                SELECT method, ex_ante_json, ips_compliance_json
                FROM risk_reports
                """
            ).fetchone()

        self.assertEqual(stored_proposal[0], "max_sharpe")
        self.assertEqual(stored_proposal[1], "return_optimized")
        self.assertEqual(json.loads(stored_proposal[2]), {"cash": 0.45, "us_large_cap": 0.55})
        self.assertAlmostEqual(stored_proposal[3], 0.071, places=12)
        self.assertAlmostEqual(stored_proposal[4], 0.102, places=12)
        self.assertEqual(stored_risk_report[0], "max_sharpe")
        self.assertEqual(json.loads(stored_risk_report[1])["return"], 0.071)
        self.assertTrue(json.loads(stored_risk_report[2])["violations"])
        self.assertTrue(json.loads(stored_risk_report[2])["warnings"])


if __name__ == "__main__":
    unittest.main()

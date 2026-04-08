from __future__ import annotations

import sqlite3
from pathlib import Path

from core.utils import ensure_directory


SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS macro_views (
        id INTEGER PRIMARY KEY,
        timestamp TEXT NOT NULL,
        regime TEXT NOT NULL,
        confidence TEXT,
        composite_score REAL,
        recession_probability REAL,
        scores_json TEXT NOT NULL,
        key_indicators_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS cma_results (
        id INTEGER PRIMARY KEY,
        timestamp TEXT NOT NULL,
        asset_slug TEXT NOT NULL,
        method TEXT NOT NULL,
        expected_return REAL NOT NULL,
        confidence REAL,
        raw_output_json TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS portfolio_proposals (
        id INTEGER PRIMARY KEY,
        timestamp TEXT NOT NULL,
        method TEXT NOT NULL,
        category TEXT NOT NULL,
        weights_json TEXT NOT NULL,
        expected_return REAL,
        expected_vol REAL,
        sharpe_ratio REAL,
        max_drawdown REAL,
        effective_n REAL,
        review_score REAL,
        vote_points INTEGER,
        in_top5 BOOLEAN
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS risk_reports (
        id INTEGER PRIMARY KEY,
        timestamp TEXT NOT NULL,
        method TEXT NOT NULL,
        ex_ante_json TEXT,
        backtest_json TEXT,
        concentration_json TEXT,
        factor_tilts_json TEXT,
        ips_compliance_json TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS board_memos (
        id INTEGER PRIMARY KEY,
        timestamp TEXT NOT NULL,
        selected_ensemble TEXT,
        portfolio_summary_json TEXT,
        allocation_by_class_json TEXT,
        top_positions_json TEXT,
        memo_content TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS meta_feedback (
        id INTEGER PRIMARY KEY,
        timestamp TEXT NOT NULL,
        period_start TEXT,
        period_end TEXT,
        feedback_summary_json TEXT,
        changes_json TEXT,
        recommended_review BOOLEAN
    )
    """,
)


def initialize_database(database_path: str | Path = "database/portfolio.db") -> Path:
    resolved_path = Path(database_path)
    ensure_directory(resolved_path.parent)

    with sqlite3.connect(resolved_path) as connection:
        for statement in SCHEMA_STATEMENTS:
            connection.execute(statement)
        connection.commit()

    return resolved_path

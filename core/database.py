from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from core.utils import ensure_directory


@dataclass(frozen=True, slots=True)
class ColumnDefinition:
    name: str
    sql_type: str
    constraints: str = ""
    additive_repair_default: str | None = None

    @property
    def sql_fragment(self) -> str:
        if self.constraints:
            return f"{self.name} {self.sql_type} {self.constraints}".strip()
        return f"{self.name} {self.sql_type}"

    @property
    def requires_value(self) -> bool:
        return "NOT NULL" in self.constraints.upper()


class SchemaDriftError(RuntimeError):
    pass


TABLE_SCHEMAS: dict[str, tuple[ColumnDefinition, ...]] = {
    "macro_views": (
        ColumnDefinition("id", "INTEGER", "PRIMARY KEY"),
        ColumnDefinition("timestamp", "TEXT", "NOT NULL"),
        ColumnDefinition("regime", "TEXT", "NOT NULL"),
        ColumnDefinition("confidence", "TEXT"),
        ColumnDefinition("composite_score", "REAL"),
        ColumnDefinition("recession_probability", "REAL"),
        ColumnDefinition("scores_json", "TEXT", "NOT NULL", additive_repair_default="'{}'"),
        ColumnDefinition("key_indicators_json", "TEXT", "NOT NULL", additive_repair_default="'{}'"),
    ),
    "cma_results": (
        ColumnDefinition("id", "INTEGER", "PRIMARY KEY"),
        ColumnDefinition("timestamp", "TEXT", "NOT NULL"),
        ColumnDefinition("asset_slug", "TEXT", "NOT NULL"),
        ColumnDefinition("method", "TEXT", "NOT NULL"),
        ColumnDefinition("expected_return", "REAL"),
        ColumnDefinition("confidence", "REAL"),
        ColumnDefinition("raw_output_json", "TEXT"),
    ),
    "portfolio_proposals": (
        ColumnDefinition("id", "INTEGER", "PRIMARY KEY"),
        ColumnDefinition("timestamp", "TEXT", "NOT NULL"),
        ColumnDefinition("method", "TEXT", "NOT NULL"),
        ColumnDefinition("category", "TEXT", "NOT NULL"),
        ColumnDefinition("weights_json", "TEXT", "NOT NULL", additive_repair_default="'{}'"),
        ColumnDefinition("expected_return", "REAL"),
        ColumnDefinition("expected_vol", "REAL"),
        ColumnDefinition("sharpe_ratio", "REAL"),
        ColumnDefinition("max_drawdown", "REAL"),
        ColumnDefinition("effective_n", "REAL"),
        ColumnDefinition("review_score", "REAL"),
        ColumnDefinition("vote_points", "INTEGER"),
        ColumnDefinition("in_top5", "BOOLEAN"),
    ),
    "risk_reports": (
        ColumnDefinition("id", "INTEGER", "PRIMARY KEY"),
        ColumnDefinition("timestamp", "TEXT", "NOT NULL"),
        ColumnDefinition("method", "TEXT", "NOT NULL"),
        ColumnDefinition("ex_ante_json", "TEXT"),
        ColumnDefinition("backtest_json", "TEXT"),
        ColumnDefinition("concentration_json", "TEXT"),
        ColumnDefinition("factor_tilts_json", "TEXT"),
        ColumnDefinition("ips_compliance_json", "TEXT"),
    ),
    "board_memos": (
        ColumnDefinition("id", "INTEGER", "PRIMARY KEY"),
        ColumnDefinition("timestamp", "TEXT", "NOT NULL"),
        ColumnDefinition("selected_ensemble", "TEXT", "NOT NULL", additive_repair_default="''"),
        ColumnDefinition("ensemble_weights_json", "TEXT", "NOT NULL", additive_repair_default="'{}'"),
        ColumnDefinition("portfolio_summary_json", "TEXT", "NOT NULL", additive_repair_default="'{}'"),
        ColumnDefinition("allocation_by_class_json", "TEXT", "NOT NULL", additive_repair_default="'{}'"),
        ColumnDefinition("top_positions_json", "TEXT", "NOT NULL", additive_repair_default="'[]'"),
        ColumnDefinition("changes_json", "TEXT", "NOT NULL", additive_repair_default="'[]'"),
        ColumnDefinition("key_risks_json", "TEXT", "NOT NULL", additive_repair_default="'[]'"),
        ColumnDefinition("rebalancing_plan", "TEXT", "NOT NULL", additive_repair_default="''"),
        ColumnDefinition("ips_compliance_statement", "TEXT", "NOT NULL", additive_repair_default="''"),
        ColumnDefinition("memo_path", "TEXT"),
        ColumnDefinition("memo_content", "TEXT", "NOT NULL", additive_repair_default="''"),
    ),
    "meta_feedback": (
        ColumnDefinition("id", "INTEGER", "PRIMARY KEY"),
        ColumnDefinition("timestamp", "TEXT", "NOT NULL"),
        ColumnDefinition("period_start", "TEXT"),
        ColumnDefinition("period_end", "TEXT"),
        ColumnDefinition("feedback_summary_json", "TEXT"),
        ColumnDefinition("changes_json", "TEXT"),
        ColumnDefinition("recommended_review", "BOOLEAN"),
    ),
}


def initialize_database(database_path: str | Path = "database/portfolio.db") -> Path:
    resolved_path = Path(database_path)
    ensure_directory(resolved_path.parent)

    with sqlite3.connect(resolved_path) as connection:
        for table_name, columns in TABLE_SCHEMAS.items():
            _ensure_table_schema(connection, table_name, columns)
        connection.commit()

    return resolved_path


def persist_macro_view(database_path: str | Path, macro_view: object) -> None:
    payload = macro_view.to_dict()
    with sqlite3.connect(database_path) as connection:
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
                payload["timestamp"],
                payload["regime"],
                payload["confidence"],
                payload["composite_score"],
                payload["recession_probability"],
                json.dumps(payload["scores"], sort_keys=True),
                json.dumps(payload["key_indicators"], sort_keys=True),
            ),
        )
        connection.commit()


def persist_cma_methods(database_path: str | Path, asset_slug: str, timestamp: str, methods: tuple[object, ...]) -> None:
    rows = []
    for method in methods:
        payload = method.to_dict()
        rows.append(
            (
                timestamp,
                asset_slug,
                payload["name"],
                payload["expected_return"],
                payload["confidence"],
                json.dumps(payload, sort_keys=True),
            )
        )

    with sqlite3.connect(database_path) as connection:
        connection.executemany(
            """
            INSERT INTO cma_results (
                timestamp,
                asset_slug,
                method,
                expected_return,
                confidence,
                raw_output_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        connection.commit()


def persist_portfolio_proposal(database_path: str | Path, proposal: object) -> None:
    persist_portfolio_proposals(database_path, proposals=(proposal,))


def persist_portfolio_proposals(database_path: str | Path, *, proposals: tuple[object, ...]) -> None:
    rows = []
    for proposal in proposals:
        payload = proposal.to_dict()
        rows.append(
            (
                payload["timestamp"],
                payload["method"],
                payload["category"],
                json.dumps(payload["weights"], sort_keys=True),
                payload["expected_return"],
                payload["expected_volatility"],
                payload["sharpe_ratio"],
                payload["max_drawdown"],
                payload["effective_n"],
                None,
                None,
                None,
            )
        )

    with sqlite3.connect(database_path) as connection:
        connection.executemany(
            """
            INSERT INTO portfolio_proposals (
                timestamp,
                method,
                category,
                weights_json,
                expected_return,
                expected_vol,
                sharpe_ratio,
                max_drawdown,
                effective_n,
                review_score,
                vote_points,
                in_top5
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        connection.commit()


def persist_risk_report(database_path: str | Path, *, timestamp: str, risk_report: object) -> None:
    persist_risk_reports(database_path, risk_reports=((timestamp, risk_report),))


def persist_risk_reports(database_path: str | Path, *, risk_reports: tuple[tuple[str, object], ...]) -> None:
    rows = []
    for timestamp, risk_report in risk_reports:
        payload = risk_report.to_dict()
        rows.append(
            (
                timestamp,
                payload["method"],
                json.dumps(payload["ex_ante"], sort_keys=True),
                json.dumps(payload["backtest"], sort_keys=True),
                json.dumps(payload["concentration"], sort_keys=True),
                json.dumps(payload["factor_tilts"], sort_keys=True),
                json.dumps(payload["ips_compliance"], sort_keys=True),
            )
        )

    with sqlite3.connect(database_path) as connection:
        connection.executemany(
            """
            INSERT INTO risk_reports (
                timestamp,
                method,
                ex_ante_json,
                backtest_json,
                concentration_json,
                factor_tilts_json,
                ips_compliance_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        connection.commit()


def persist_board_memo(
    database_path: str | Path,
    *,
    timestamp: str,
    board_memo: object,
    memo_content: str,
    memo_path: str | Path | None = None,
) -> None:
    payload = board_memo.to_dict()
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO board_memos (
                timestamp,
                selected_ensemble,
                ensemble_weights_json,
                portfolio_summary_json,
                allocation_by_class_json,
                top_positions_json,
                changes_json,
                key_risks_json,
                rebalancing_plan,
                ips_compliance_statement,
                memo_path,
                memo_content
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp,
                payload["selected_ensemble"],
                json.dumps(payload["ensemble_weights"], sort_keys=True),
                json.dumps(payload["portfolio_summary"], sort_keys=True),
                json.dumps(payload["allocation_by_asset_class"], sort_keys=True),
                json.dumps(payload["top_positions"], sort_keys=True),
                json.dumps(payload["changes_since_last_review"], sort_keys=True),
                json.dumps(payload["key_risks_to_monitor"], sort_keys=True),
                payload["rebalancing_plan"],
                payload["ips_compliance_statement"],
                str(memo_path) if memo_path is not None else None,
                memo_content,
            ),
        )
        connection.commit()


def persist_governance_scores(
    database_path: str | Path,
    *,
    timestamp: str,
    tallies: tuple[object, ...],
    shortlist_methods: tuple[str, ...],
) -> None:
    shortlist_set = set(shortlist_methods)
    rows = [
        (
            tally.average_total_score,
            tally.total_vote_points,
            tally.method in shortlist_set,
            timestamp,
            tally.method,
        )
        for tally in tallies
    ]
    with sqlite3.connect(database_path) as connection:
        connection.executemany(
            """
            UPDATE portfolio_proposals
            SET review_score = ?, vote_points = ?, in_top5 = ?
            WHERE timestamp = ? AND method = ?
            """,
            rows,
        )
        connection.commit()


def persist_meta_feedback(
    database_path: str | Path,
    *,
    timestamp: str,
    period_start: str,
    period_end: str,
    feedback_summary: dict[str, object],
    changes: tuple[object, ...],
    recommended_review: bool,
) -> None:
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO meta_feedback (
                timestamp,
                period_start,
                period_end,
                feedback_summary_json,
                changes_json,
                recommended_review
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp,
                period_start,
                period_end,
                json.dumps(feedback_summary, sort_keys=True),
                json.dumps([change.to_dict() for change in changes], sort_keys=True),
                recommended_review,
            ),
        )
        connection.commit()


def persist_portfolio_stage(
    database_path: str | Path,
    *,
    proposals: tuple[object, ...],
    risk_reports: tuple[tuple[str, object], ...],
) -> None:
    proposal_rows = []
    for proposal in proposals:
        payload = proposal.to_dict()
        proposal_rows.append(
            (
                payload["timestamp"],
                payload["method"],
                payload["category"],
                json.dumps(payload["weights"], sort_keys=True),
                payload["expected_return"],
                payload["expected_volatility"],
                payload["sharpe_ratio"],
                payload["max_drawdown"],
                payload["effective_n"],
                None,
                None,
                None,
            )
        )

    risk_report_rows = []
    for timestamp, risk_report in risk_reports:
        payload = risk_report.to_dict()
        risk_report_rows.append(
            (
                timestamp,
                payload["method"],
                json.dumps(payload["ex_ante"], sort_keys=True),
                json.dumps(payload["backtest"], sort_keys=True),
                json.dumps(payload["concentration"], sort_keys=True),
                json.dumps(payload["factor_tilts"], sort_keys=True),
                json.dumps(payload["ips_compliance"], sort_keys=True),
            )
        )

    with sqlite3.connect(database_path) as connection:
        if proposal_rows:
            connection.executemany(
                """
                INSERT INTO portfolio_proposals (
                    timestamp,
                    method,
                    category,
                    weights_json,
                    expected_return,
                    expected_vol,
                    sharpe_ratio,
                    max_drawdown,
                    effective_n,
                    review_score,
                    vote_points,
                    in_top5
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                proposal_rows,
            )
        if risk_report_rows:
            connection.executemany(
                """
                INSERT INTO risk_reports (
                    timestamp,
                    method,
                    ex_ante_json,
                    backtest_json,
                    concentration_json,
                    factor_tilts_json,
                    ips_compliance_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                risk_report_rows,
            )
        connection.commit()


def _ensure_table_schema(
    connection: sqlite3.Connection,
    table_name: str,
    expected_columns: tuple[ColumnDefinition, ...],
) -> None:
    existing_columns = _table_columns(connection, table_name)
    if not existing_columns:
        connection.execute(_create_table_statement(table_name, expected_columns))
        return

    missing_columns = [column for column in expected_columns if column.name not in existing_columns]
    if not missing_columns:
        return

    row_count = connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
    unsafe_missing = [
        column.name
        for column in missing_columns
        if column.requires_value and column.additive_repair_default is None
    ]
    if row_count > 0 and unsafe_missing:
        raise SchemaDriftError(
            f"Table '{table_name}' is missing required columns {unsafe_missing}; "
            "automatic migration is unsafe with existing rows."
        )

    for column in missing_columns:
        connection.execute(_add_column_statement(table_name, column))


def _table_columns(connection: sqlite3.Connection, table_name: str) -> dict[str, sqlite3.Row]:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row[1]: row for row in rows}


def _create_table_statement(table_name: str, columns: tuple[ColumnDefinition, ...]) -> str:
    column_sql = ",\n        ".join(column.sql_fragment for column in columns)
    return f"""
    CREATE TABLE IF NOT EXISTS {table_name} (
        {column_sql}
    )
    """


def _add_column_statement(table_name: str, column: ColumnDefinition) -> str:
    if column.additive_repair_default is None:
        return f"ALTER TABLE {table_name} ADD COLUMN {column.sql_fragment}"
    constraints = column.constraints
    if constraints:
        constraints = f"{constraints} DEFAULT {column.additive_repair_default}"
    else:
        constraints = f"DEFAULT {column.additive_repair_default}"
    return f"ALTER TABLE {table_name} ADD COLUMN {column.name} {column.sql_type} {constraints}".strip()

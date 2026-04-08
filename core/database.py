from __future__ import annotations

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
        ColumnDefinition("expected_return", "REAL", "NOT NULL", additive_repair_default="0"),
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
        ColumnDefinition("selected_ensemble", "TEXT"),
        ColumnDefinition("portfolio_summary_json", "TEXT"),
        ColumnDefinition("allocation_by_class_json", "TEXT"),
        ColumnDefinition("top_positions_json", "TEXT"),
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

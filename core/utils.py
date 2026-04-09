from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


TRADING_DAYS_PER_YEAR = 252
WEEKS_PER_YEAR = 52
MONTHS_PER_YEAR = 12
QUARTERS_PER_YEAR = 4

ANNUALIZATION_FACTORS = {
    "daily": TRADING_DAYS_PER_YEAR,
    "weekly": WEEKS_PER_YEAR,
    "monthly": MONTHS_PER_YEAR,
    "quarterly": QUARTERS_PER_YEAR,
    "yearly": 1,
}


def ensure_directory(path: str | Path) -> Path:
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def write_json(path: str | Path, payload: object) -> Path:
    output_path = Path(path)
    ensure_directory(output_path.parent)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def write_markdown(path: str | Path, content: str) -> Path:
    output_path = Path(path)
    ensure_directory(output_path.parent)
    output_path.write_text(content, encoding="utf-8")
    return output_path


def generate_run_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"run-{timestamp}-{uuid4().hex[:8]}"

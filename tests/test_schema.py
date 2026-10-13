"""Stage-0 schema test: schema.sql must create the 4 core tables on a fresh DB."""

import sqlite3
from pathlib import Path

SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent
    / "src" / "plantvision" / "storage" / "schema.sql"
)

REQUIRED_TABLES = {"snapshot", "processing", "measurement", "model_version"}


def test_schema_tables(tmp_path: Path) -> None:
    """executescript the DDL into a temp SQLite DB and assert all 4 tables exist."""
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn = sqlite3.connect(tmp_path / "t.db")
    try:
        conn.executescript(sql)
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    finally:
        conn.close()
    table_names = {row[0] for row in rows}
    missing = REQUIRED_TABLES - table_names
    assert not missing, f"schema.sql missing tables: {sorted(missing)}"

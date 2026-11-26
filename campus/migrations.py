"""结构迁移：把 baseline-v1 的库升级到 v2，且保证可重复执行。

- 新库：schema.sql 已是 v2 结构，migrate() 只补写版本号；
- 旧库（v1）：students 加 grade、activities 重建以扩展 CHECK、补 emails 表；
- 版本记录在 schema_version 表，重复执行不会重复迁移。
"""
from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 2

_ACTIVITIES_V2 = """
CREATE TABLE activities_v2 (
    activity_id INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    category    TEXT NOT NULL,
    start_at    TEXT NOT NULL,
    location    TEXT NOT NULL,
    capacity    INTEGER NOT NULL CHECK (capacity > 0),
    policy_type TEXT NOT NULL CHECK (policy_type IN ('direct', 'review', 'grade_limited'))
);
"""

_EMAILS_V2 = """
CREATE TABLE IF NOT EXISTS emails (
    email_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id      TEXT NOT NULL REFERENCES students(student_id),
    activity_id     INTEGER NOT NULL REFERENCES activities(activity_id),
    registration_id INTEGER NOT NULL,
    to_addr         TEXT NOT NULL,
    subject         TEXT NOT NULL,
    body            TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('待发送', '已发送', '失败')),
    error           TEXT NOT NULL DEFAULT '',
    dedupe_key      TEXT NOT NULL UNIQUE,
    created_at      TEXT NOT NULL
);
"""

_VERSION_TABLE = "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone()
    return row is not None


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def current_version(conn: sqlite3.Connection) -> int:
    if not _table_exists(conn, "schema_version"):
        return 0
    row = conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
    return int(row["v"] or 0)


def migrate(conn: sqlite3.Connection) -> int:
    """把库升级到 SCHEMA_VERSION；返回升级后的版本。"""
    if not _table_exists(conn, "students"):
        return current_version(conn)

    if not _has_column(conn, "students", "grade"):
        _upgrade_v1_to_v2(conn)

    conn.execute(_VERSION_TABLE)
    if current_version(conn) != SCHEMA_VERSION:
        conn.execute("DELETE FROM schema_version")
        conn.execute(
            "INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,)
        )
    return SCHEMA_VERSION


def _upgrade_v1_to_v2(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("BEGIN")
        conn.execute(
            "ALTER TABLE students ADD COLUMN grade INTEGER NOT NULL DEFAULT 1"
            " CHECK (grade BETWEEN 1 AND 4)"
        )
        conn.execute(_ACTIVITIES_V2)
        conn.execute(
            "INSERT INTO activities_v2"
            " (activity_id, title, category, start_at, location, capacity, policy_type)"
            " SELECT activity_id, title, category, start_at, location, capacity, policy_type"
            " FROM activities"
        )
        conn.execute("DROP TABLE activities")
        conn.execute("ALTER TABLE activities_v2 RENAME TO activities")
        conn.execute(_EMAILS_V2)
        conn.execute("CREATE INDEX IF NOT EXISTS ix_emails_student ON emails(student_id)")
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")

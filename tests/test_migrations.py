"""change-v2 结构迁移：v1 旧库升级到 v2，且可重复执行。"""
import sqlite3

from app import create_app
from campus.migrations import SCHEMA_VERSION, current_version, migrate

V1_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE students (
    student_id TEXT PRIMARY KEY,
    name       TEXT NOT NULL
);

CREATE TABLE activities (
    activity_id INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    category    TEXT NOT NULL,
    start_at    TEXT NOT NULL,
    location    TEXT NOT NULL,
    capacity    INTEGER NOT NULL CHECK (capacity > 0),
    policy_type TEXT NOT NULL CHECK (policy_type IN ('direct', 'review'))
);

CREATE TABLE registrations (
    registration_id INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id     INTEGER NOT NULL REFERENCES activities(activity_id),
    student_id      TEXT NOT NULL REFERENCES students(student_id),
    status          TEXT NOT NULL CHECK (status IN ('待审核', '已通过', '已拒绝', '已取消')),
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE UNIQUE INDEX ux_registrations_active
    ON registrations(activity_id, student_id)
    WHERE status IN ('待审核', '已通过');

CREATE INDEX ix_registrations_activity_status
    ON registrations(activity_id, status);

CREATE TABLE messages (
    message_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id  TEXT NOT NULL REFERENCES students(student_id),
    activity_id INTEGER NOT NULL REFERENCES activities(activity_id),
    content     TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    is_read     INTEGER NOT NULL DEFAULT 0,
    dedupe_key  TEXT NOT NULL UNIQUE
);
"""


def _make_legacy_db(path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(V1_SCHEMA)
    conn.execute("INSERT INTO students (student_id, name) VALUES ('2023001', '张伟')")
    conn.execute(
        "INSERT INTO activities (title, category, start_at, location, capacity, policy_type)"
        " VALUES ('旧活动', '文艺', '2099-01-01 19:00', '礼堂', 10, 'direct')"
    )
    conn.execute(
        "INSERT INTO registrations (activity_id, student_id, status, created_at, updated_at)"
        " VALUES (1, '2023001', '已通过', '2026-01-01 00:00:00', '2026-01-01 00:00:00')"
    )
    conn.commit()
    conn.close()


def _open(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def test_legacy_v1_database_upgrades_to_v2(tmp_path):
    database = tmp_path / "legacy.db"
    _make_legacy_db(database)

    create_app(
        {
            "TESTING": True,
            "DATABASE": str(database),
            "FAILURE_LOG": str(tmp_path / "failures.log"),
            "SEED_ACTIVITIES": False,
        }
    )

    conn = _open(database)
    try:
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(students)")]
        assert "grade" in columns
        student = conn.execute(
            "SELECT * FROM students WHERE student_id = '2023001'"
        ).fetchone()
        assert student["grade"] == 1

        activity = conn.execute("SELECT * FROM activities WHERE activity_id = 1").fetchone()
        assert activity["title"] == "旧活动"

        registration = conn.execute("SELECT * FROM registrations").fetchone()
        assert registration["activity_id"] == 1
        assert registration["status"] == "已通过"

        assert current_version(conn) == SCHEMA_VERSION
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []

        conn.execute(
            "INSERT INTO activities (title, category, start_at, location, capacity, policy_type)"
            " VALUES ('新活动', '讲座', '2099-02-01 10:00', '201', 10, 'grade_limited')"
        )
        conn.commit()
    finally:
        conn.close()


def test_migration_is_idempotent(tmp_path):
    database = tmp_path / "legacy.db"
    _make_legacy_db(database)

    create_app(
        {
            "TESTING": True,
            "DATABASE": str(database),
            "FAILURE_LOG": str(tmp_path / "failures.log"),
            "SEED_ACTIVITIES": False,
        }
    )

    conn = _open(database)
    try:
        assert migrate(conn) == SCHEMA_VERSION
        assert migrate(conn) == SCHEMA_VERSION
        assert current_version(conn) == SCHEMA_VERSION
        assert conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0] == 1
    finally:
        conn.close()

from __future__ import annotations

import sqlite3

from .models import (
    STATUS_APPROVED,
    STATUS_PENDING,
    Activity,
    Message,
    Registration,
    now_text,
)


def _activity(row: sqlite3.Row | None) -> Activity | None:
    if row is None:
        return None
    return Activity(
        activity_id=row["activity_id"],
        title=row["title"],
        category=row["category"],
        start_at=row["start_at"],
        location=row["location"],
        capacity=row["capacity"],
        policy_type=row["policy_type"],
    )


def _registration(row: sqlite3.Row | None) -> Registration | None:
    if row is None:
        return None
    return Registration(
        registration_id=row["registration_id"],
        activity_id=row["activity_id"],
        student_id=row["student_id"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class ActivityRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get(self, activity_id: int) -> Activity | None:
        return _activity(
            self.conn.execute(
                "SELECT * FROM activities WHERE activity_id = ?", (activity_id,)
            ).fetchone()
        )

    def list(self, keyword: str | None = None) -> list[Activity]:
        sql = "SELECT * FROM activities"
        args: tuple = ()
        if keyword:
            sql += " WHERE title LIKE ? OR category LIKE ? OR location LIKE ?"
            like = f"%{keyword}%"
            args = (like, like, like)
        sql += " ORDER BY start_at ASC, activity_id DESC"
        return [_activity(row) for row in self.conn.execute(sql, args).fetchall()]

    def create(
        self,
        *,
        title: str,
        category: str,
        start_at: str,
        location: str,
        capacity: int,
        policy_type: str,
    ) -> int:
        cur = self.conn.execute(
            "INSERT INTO activities (title, category, start_at, location, capacity, policy_type)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (title, category, start_at, location, capacity, policy_type),
        )
        return int(cur.lastrowid)

    def update(
        self,
        activity_id: int,
        *,
        title: str,
        category: str,
        start_at: str,
        location: str,
        capacity: int,
        policy_type: str,
    ) -> None:
        self.conn.execute(
            "UPDATE activities SET title = ?, category = ?, start_at = ?, location = ?,"
            " capacity = ?, policy_type = ? WHERE activity_id = ?",
            (title, category, start_at, location, capacity, policy_type, activity_id),
        )

    def delete(self, activity_id: int) -> None:
        self.conn.execute("DELETE FROM activities WHERE activity_id = ?", (activity_id,))


class RegistrationRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get(self, registration_id: int) -> Registration | None:
        return _registration(
            self.conn.execute(
                "SELECT * FROM registrations WHERE registration_id = ?", (registration_id,)
            ).fetchone()
        )

    def find_active(self, activity_id: int, student_id: str) -> Registration | None:
        return _registration(
            self.conn.execute(
                "SELECT * FROM registrations WHERE activity_id = ? AND student_id = ?"
                " AND status IN (?, ?)",
                (activity_id, student_id, STATUS_PENDING, STATUS_APPROVED),
            ).fetchone()
        )

    def count_status(self, activity_id: int, status: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM registrations WHERE activity_id = ? AND status = ?",
            (activity_id, status),
        ).fetchone()
        return int(row["n"])

    def count_all(self, activity_id: int) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM registrations WHERE activity_id = ?", (activity_id,)
        ).fetchone()
        return int(row["n"])

    def create(self, activity_id: int, student_id: str, status: str) -> int:
        now = now_text()
        cur = self.conn.execute(
            "INSERT INTO registrations (activity_id, student_id, status, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (activity_id, student_id, status, now, now),
        )
        return int(cur.lastrowid)

    def update_status(self, registration_id: int, status: str) -> None:
        self.conn.execute(
            "UPDATE registrations SET status = ?, updated_at = ? WHERE registration_id = ?",
            (status, now_text(), registration_id),
        )

    def list_by_student(self, student_id: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT r.*, a.title, a.start_at, a.location, a.category, a.policy_type"
            " FROM registrations r JOIN activities a ON a.activity_id = r.activity_id"
            " WHERE r.student_id = ? ORDER BY r.registration_id DESC",
            (student_id,),
        ).fetchall()

    def list_pending(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT r.*, a.title, a.start_at, a.capacity, s.name,"
            " (SELECT COUNT(*) FROM registrations x WHERE x.activity_id = r.activity_id"
            "  AND x.status = ?) AS approved_count"
            " FROM registrations r"
            " JOIN activities a ON a.activity_id = r.activity_id"
            " JOIN students s ON s.student_id = r.student_id"
            " WHERE r.status = ? ORDER BY r.registration_id ASC",
            (STATUS_APPROVED, STATUS_PENDING),
        ).fetchall()


class MessageRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add(self, student_id: str, activity_id: int, content: str, dedupe_key: str) -> bool:
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO messages (student_id, activity_id, content, created_at, is_read, dedupe_key)"
            " VALUES (?, ?, ?, ?, 0, ?)",
            (student_id, activity_id, content, now_text(), dedupe_key),
        )
        return cur.rowcount > 0

    def list_by_student(self, student_id: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT m.*, a.title FROM messages m JOIN activities a ON a.activity_id = m.activity_id"
            " WHERE m.student_id = ? ORDER BY m.message_id DESC",
            (student_id,),
        ).fetchall()

    def unread_count(self, student_id: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM messages WHERE student_id = ? AND is_read = 0",
            (student_id,),
        ).fetchone()
        return int(row["n"])

    def mark_read(self, message_id: int, student_id: str) -> None:
        self.conn.execute(
            "UPDATE messages SET is_read = 1 WHERE message_id = ? AND student_id = ?",
            (message_id, student_id),
        )

    def mark_all_read(self, student_id: str) -> None:
        self.conn.execute(
            "UPDATE messages SET is_read = 1 WHERE student_id = ?", (student_id,)
        )

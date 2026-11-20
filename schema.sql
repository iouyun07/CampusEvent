PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS students (
    student_id TEXT PRIMARY KEY,
    name       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS activities (
    activity_id INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    category    TEXT NOT NULL,
    start_at    TEXT NOT NULL,               -- 'YYYY-MM-DD HH:MM'
    location    TEXT NOT NULL,
    capacity    INTEGER NOT NULL CHECK (capacity > 0),
    policy_type TEXT NOT NULL CHECK (policy_type IN ('direct', 'review'))
);

CREATE TABLE IF NOT EXISTS registrations (
    registration_id INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id     INTEGER NOT NULL REFERENCES activities(activity_id),
    student_id      TEXT NOT NULL REFERENCES students(student_id),
    status          TEXT NOT NULL CHECK (status IN ('待审核', '已通过', '已拒绝', '已取消')),
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

-- 同一学生对同一活动最多一条有效报名（待审核或已通过）
CREATE UNIQUE INDEX IF NOT EXISTS ux_registrations_active
    ON registrations(activity_id, student_id)
    WHERE status IN ('待审核', '已通过');

CREATE INDEX IF NOT EXISTS ix_registrations_activity_status
    ON registrations(activity_id, status);

CREATE TABLE IF NOT EXISTS messages (
    message_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id  TEXT NOT NULL REFERENCES students(student_id),
    activity_id INTEGER NOT NULL REFERENCES activities(activity_id),
    content     TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    is_read     INTEGER NOT NULL DEFAULT 0,
    dedupe_key  TEXT NOT NULL UNIQUE
);

from __future__ import annotations

from pathlib import Path

from flask import Flask

from campus import db
from campus.views import bp

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"

DEMO_STUDENTS = [
    ("2023001", "张伟"),
    ("2023002", "李娜"),
    ("2023003", "王强"),
]

DEMO_ACTIVITIES = [
    ("校园歌手大赛", "文艺", "2026-12-01 19:00", "大学生活动中心", 50, "direct"),
    ("编程马拉松", "科技", "2026-12-05 09:00", "图书馆报告厅", 30, "review"),
    ("篮球友谊赛", "体育", "2026-11-26 15:00", "东区篮球场", 20, "direct"),
]


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY="campus-event-dev-secret",
        DATABASE=str(INSTANCE_DIR / "campus_event.db"),
        FAILURE_LOG=str(INSTANCE_DIR / "notification_failures.log"),
        SEED_ACTIVITIES=True,
    )
    if test_config:
        app.config.update(test_config)

    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)

    conn = db.connect(app.config["DATABASE"])
    try:
        db.init_schema(conn, BASE_DIR / "schema.sql")
        seed_demo(conn, app.config["SEED_ACTIVITIES"])
    finally:
        conn.close()

    db.init_app(app)
    app.register_blueprint(bp)
    return app


def seed_demo(conn, with_activities: bool = True) -> None:
    if conn.execute("SELECT COUNT(*) FROM students").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO students (student_id, name) VALUES (?, ?)", DEMO_STUDENTS
        )
    if with_activities and conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO activities (title, category, start_at, location, capacity, policy_type)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            DEMO_ACTIVITIES,
        )


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=False)

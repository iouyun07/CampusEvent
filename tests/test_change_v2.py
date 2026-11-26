"""实验二 change-v2：CR-01 年级限定 / CR-02 模拟邮件 / 结构迁移。"""
import sqlite3

import pytest

from app import create_app
from campus.events import EVENT_APPROVED, EventBus, RegistrationEvent
from campus.mock_email import MockEmailSender
from campus.models import STATUS_APPROVED
from campus.migrations import migrate
from campus.notifications import EmailNotifier
from campus.repositories import (
    ActivityRepository,
    EmailRepository,
    RegistrationRepository,
)
from helpers import create_activity, latest_registration, login, register, status_of

STUDENT_GRADE2 = "2023001"  # 张伟，大二
STUDENT_GRADE3 = "2023002"  # 李娜，大三
STUDENT_GRADE1 = "2023003"  # 王强，大一


def _register_and_follow(client, activity_id):
    return client.post(f"/activities/{activity_id}/register", follow_redirects=True)


def _emails(conn):
    return conn.execute("SELECT * FROM emails ORDER BY email_id").fetchall()


# ---------------- CR-01 年级限定 ----------------

def test_cr1_01_grade2_can_register(client, conn):
    login(client, STUDENT_GRADE2)
    activity_id = create_activity(client, conn, title="年级限定-大二", policy="grade_limited")
    _register_and_follow(client, activity_id)

    row = latest_registration(conn, activity_id, STUDENT_GRADE2)
    assert row is not None
    assert row["status"] == STATUS_APPROVED


def test_cr1_02_grade3_can_register(client, conn):
    login(client, STUDENT_GRADE3)
    activity_id = create_activity(client, conn, title="年级限定-大三", policy="grade_limited")
    _register_and_follow(client, activity_id)

    row = latest_registration(conn, activity_id, STUDENT_GRADE3)
    assert row is not None
    assert row["status"] == STATUS_APPROVED


def test_cr1_03_grade1_denied_with_reason(client, conn):
    login(client, STUDENT_GRADE1)
    activity_id = create_activity(client, conn, title="年级限定-大一", policy="grade_limited")
    response = _register_and_follow(client, activity_id)

    assert "仅限" in response.get_data(as_text=True)
    assert latest_registration(conn, activity_id, STUDENT_GRADE1) is None


def test_cr1_04_grade4_denied_with_reason(client, conn):
    conn.execute(
        "INSERT OR REPLACE INTO students (student_id, name, grade) VALUES (?, ?, ?)",
        ("2023010", "赵四", 4),
    )
    conn.commit()
    login(client, "2023010")
    activity_id = create_activity(client, conn, title="年级限定-大四", policy="grade_limited")
    response = _register_and_follow(client, activity_id)

    assert "仅限" in response.get_data(as_text=True)
    assert latest_registration(conn, activity_id, "2023010") is None


def test_cr1_05_grade_limited_still_obeys_capacity(client, conn):
    """年级合格但名额已满时，仍走容量检查（复用父类逻辑）。"""
    login(client, STUDENT_GRADE2)
    activity_id = create_activity(
        client, conn, title="年级限定-满员", capacity=1, policy="grade_limited"
    )
    conn.execute(
        "INSERT INTO registrations (activity_id, student_id, status, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (activity_id, "2023002", STATUS_APPROVED, "2026-01-01 00:00:00", "2026-01-01 00:00:00"),
    )
    conn.commit()

    response = _register_and_follow(client, activity_id)
    assert "名额已满" in response.get_data(as_text=True)
    assert latest_registration(conn, activity_id, STUDENT_GRADE2) is None


# ---------------- CR-02 模拟邮件 ----------------

def test_cr2_01_direct_approved_sends_email_and_message(client, conn):
    login(client, STUDENT_GRADE2)
    activity_id = create_activity(client, conn, title="邮件-直接报名")
    _register_and_follow(client, activity_id)

    emails = _emails(conn)
    assert len(emails) == 1
    assert emails[0]["status"] == "已发送"
    assert emails[0]["to_addr"] == f"{STUDENT_GRADE2}@campus.example.com"
    assert "邮件-直接报名" in emails[0]["subject"]
    messages = conn.execute(
        "SELECT * FROM messages WHERE student_id = ?", (STUDENT_GRADE2,)
    ).fetchall()
    assert len(messages) == 1


def test_cr2_02_review_approve_and_reject_send_email(client, conn):
    login(client, STUDENT_GRADE2)
    activity_id = create_activity(client, conn, title="邮件-审核活动", policy="review")
    _register_and_follow(client, activity_id)

    registration = latest_registration(conn, activity_id, STUDENT_GRADE2)
    assert registration["status"] == "待审核"
    assert _emails(conn) == []

    client.post(
        f"/admin/approvals/{registration['registration_id']}/approve",
        follow_redirects=True,
    )
    emails = _emails(conn)
    assert len(emails) == 1
    assert emails[0]["status"] == "已发送"
    assert "已通过" in emails[0]["body"]

    login(client, STUDENT_GRADE3)
    activity_id2 = create_activity(client, conn, title="邮件-审核拒绝", policy="review")
    _register_and_follow(client, activity_id2)
    registration2 = latest_registration(conn, activity_id2, STUDENT_GRADE3)
    client.post(
        f"/admin/approvals/{registration2['registration_id']}/reject",
        follow_redirects=True,
    )
    emails = _emails(conn)
    assert len(emails) == 2
    assert "未通过" in emails[1]["body"]


def test_cr2_03_email_failure_keeps_registration(tmp_path):
    database = tmp_path / "fail.db"
    log = tmp_path / "failures.log"
    application = create_app(
        {
            "TESTING": True,
            "DATABASE": str(database),
            "FAILURE_LOG": str(log),
            "SEED_ACTIVITIES": False,
            "MOCK_EMAIL_FAIL_FOR": STUDENT_GRADE2,
        }
    )
    client = application.test_client()
    login(client, STUDENT_GRADE2)

    conn = sqlite3.connect(database)
    conn.row_factory = sqlite3.Row
    activity_id = create_activity(client, conn, title="邮件失败")
    _register_and_follow(client, activity_id)

    row = latest_registration(conn, activity_id, STUDENT_GRADE2)
    assert row["status"] == STATUS_APPROVED

    email = _emails(conn)[0]
    assert email["status"] == "失败"
    assert "模拟邮件发送失败" in email["error"]
    assert log.exists()
    assert "registration=" in log.read_text(encoding="utf-8")
    conn.close()


def test_cr2_04_duplicate_event_sends_once(app, conn):
    conn.execute("INSERT INTO students (student_id, name) VALUES (?, ?)", ("S1", "某生"))
    conn.execute(
        "INSERT INTO activities (title, category, start_at, location, capacity, policy_type)"
        " VALUES ('重复事件', '测试', '2099-01-01 10:00', '地点', 5, 'direct')"
    )
    conn.commit()

    activities = ActivityRepository(conn)
    registrations = RegistrationRepository(conn)
    activity = activities.get(1)
    registration_id = registrations.create(1, "S1", STATUS_APPROVED)
    registration = registrations.get(registration_id)

    sender = MockEmailSender()
    notifier = EmailNotifier(EmailRepository(conn), sender)
    event = RegistrationEvent(EVENT_APPROVED, registration, activity, "S1")
    notifier.handle(event)
    notifier.handle(event)

    assert len(_emails(conn)) == 1
    assert len(sender.outbox) == 1

from types import SimpleNamespace

import pytest

from campus.events import EVENT_APPROVED, EventBus, RegistrationEvent
from helpers import (
    cancel,
    create_activity,
    latest_registration,
    login,
    register,
    status_of,
)

STUDENT_A = "2023001"
STUDENT_B = "2023002"
STUDENT_C = "2023003"


# ---------------- C1 ----------------


def test_c1_admin_creates_direct_activity(client, conn):
    activity_id = create_activity(client, conn, title="讲座", capacity=2)
    row = conn.execute(
        "SELECT * FROM activities WHERE activity_id = ?", (activity_id,)
    ).fetchone()
    assert row["capacity"] == 2
    assert row["policy_type"] == "direct"
    page = client.get("/").get_data(as_text=True)
    assert "讲座" in page


# ---------------- C2 ----------------


def test_c2_direct_registration_is_approved_and_notified(client, conn):
    activity_id = create_activity(client, conn, title="直接报名活动", capacity=2)
    login(client, STUDENT_A)
    page = register(client, activity_id).get_data(as_text=True)
    assert "已通过" in page

    registration = latest_registration(conn, activity_id, STUDENT_A)
    assert registration["status"] == "已通过"

    message = conn.execute(
        "SELECT * FROM messages WHERE student_id = ?", (STUDENT_A,)
    ).fetchone()
    assert message is not None
    assert "已通过" in message["content"]
    assert "已通过" in client.get("/messages").get_data(as_text=True)


# ---------------- C3 ----------------


def test_c3_duplicate_registration_is_rejected(client, conn):
    activity_id = create_activity(client, conn, title="重复报名活动")
    login(client, STUDENT_A)
    register(client, activity_id)
    page = register(client, activity_id).get_data(as_text=True)
    assert "请勿重复报名" in page

    count = conn.execute(
        "SELECT COUNT(*) AS n FROM registrations WHERE activity_id = ?",
        (activity_id,),
    ).fetchone()["n"]
    assert count == 1


# ---------------- C4 ----------------


def test_c4_capacity_limit_rejects_extra_registration(client, conn):
    activity_id = create_activity(client, conn, title="限额活动", capacity=1)

    login(client, STUDENT_B)
    assert "已通过" in register(client, activity_id).get_data(as_text=True)

    login(client, STUDENT_C)
    page = register(client, activity_id).get_data(as_text=True)
    assert "名额已满" in page

    approved = conn.execute(
        "SELECT COUNT(*) AS n FROM registrations"
        " WHERE activity_id = ? AND status = '已通过'",
        (activity_id,),
    ).fetchone()["n"]
    assert approved == 1


# ---------------- C5 ----------------


def test_c5_review_registration_is_pending(client, conn):
    activity_id = create_activity(client, conn, title="审核活动", policy="review")
    login(client, STUDENT_A)
    page = register(client, activity_id).get_data(as_text=True)
    assert "待审核" in page

    registration = latest_registration(conn, activity_id, STUDENT_A)
    assert registration["status"] == "待审核"
    assert "审核活动" in client.get("/admin/approvals").get_data(as_text=True)


# ---------------- C6 ----------------


def test_c6_admin_approves_pending_registration(client, conn):
    activity_id = create_activity(client, conn, title="审批通过活动", policy="review")
    login(client, STUDENT_A)
    register(client, activity_id)
    registration = latest_registration(conn, activity_id, STUDENT_A)

    response = client.post(
        f"/admin/approvals/{registration['registration_id']}/approve",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert status_of(conn, registration["registration_id"]) == "已通过"

    contents = [
        row["content"]
        for row in conn.execute(
            "SELECT content FROM messages WHERE student_id = ?", (STUDENT_A,)
        )
    ]
    assert any("已通过" in text for text in contents)


# ---------------- C7 ----------------


def test_c7_admin_rejects_pending_registration(client, conn):
    activity_id = create_activity(client, conn, title="审批拒绝活动", policy="review")
    login(client, STUDENT_A)
    register(client, activity_id)
    registration = latest_registration(conn, activity_id, STUDENT_A)

    client.post(f"/admin/approvals/{registration['registration_id']}/reject")
    assert status_of(conn, registration["registration_id"]) == "已拒绝"

    contents = [
        row["content"]
        for row in conn.execute(
            "SELECT content FROM messages WHERE student_id = ?", (STUDENT_A,)
        )
    ]
    assert any("未通过审核" in text for text in contents)


# ---------------- C8 ----------------


def test_c8_approval_fails_when_capacity_full(client, conn):
    activity_id = create_activity(
        client, conn, title="满员审批活动", capacity=1, policy="review"
    )

    login(client, STUDENT_A)
    register(client, activity_id)
    first = latest_registration(conn, activity_id, STUDENT_A)
    client.post(f"/admin/approvals/{first['registration_id']}/approve")
    assert status_of(conn, first["registration_id"]) == "已通过"

    login(client, STUDENT_B)
    register(client, activity_id)
    second = latest_registration(conn, activity_id, STUDENT_B)

    response = client.post(
        f"/admin/approvals/{second['registration_id']}/approve",
        follow_redirects=True,
    )
    assert "名额已满" in response.get_data(as_text=True)
    assert status_of(conn, second["registration_id"]) == "待审核"

    approved = conn.execute(
        "SELECT COUNT(*) AS n FROM registrations"
        " WHERE activity_id = ? AND status = '已通过'",
        (activity_id,),
    ).fetchone()["n"]
    assert approved == 1


# ---------------- C9 ----------------


def test_c9_cancel_registration_updates_stats(client, conn):
    activity_id = create_activity(client, conn, title="取消活动", capacity=2)
    login(client, STUDENT_A)
    register(client, activity_id)
    registration = latest_registration(conn, activity_id, STUDENT_A)
    assert registration["status"] == "已通过"

    page = cancel(client, registration["registration_id"]).get_data(as_text=True)
    assert "已取消" in page
    assert status_of(conn, registration["registration_id"]) == "已取消"

    detail = client.get(f"/activities/{activity_id}").get_data(as_text=True)
    assert "已通过" in detail
    approved = conn.execute(
        "SELECT COUNT(*) AS n FROM registrations"
        " WHERE activity_id = ? AND status = '已通过'",
        (activity_id,),
    ).fetchone()["n"]
    assert approved == 0


def test_c9_cancel_pending_registration(client, conn):
    activity_id = create_activity(
        client, conn, title="取消待审核", capacity=2, policy="review"
    )
    login(client, STUDENT_A)
    register(client, activity_id)
    registration = latest_registration(conn, activity_id, STUDENT_A)
    assert registration["status"] == "待审核"

    cancel(client, registration["registration_id"])
    assert status_of(conn, registration["registration_id"]) == "已取消"

    remaining = conn.execute(
        "SELECT COUNT(*) AS n FROM registrations WHERE activity_id = ? AND status = '待审核'",
        (activity_id,),
    ).fetchone()["n"]
    assert remaining == 0


# ---------------- C10 ----------------


def test_c10_data_survives_restart(app, client, conn):
    from app import create_app

    activity_id = create_activity(
        client, conn, title="重启活动", capacity=2, policy="review"
    )
    login(client, STUDENT_A)
    register(client, activity_id)

    restarted = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "DATABASE": app.config["DATABASE"],
            "FAILURE_LOG": app.config["FAILURE_LOG"],
            "SEED_ACTIVITIES": False,
        }
    )
    restarted_client = restarted.test_client()
    login(restarted_client, STUDENT_A)

    assert "重启活动" in restarted_client.get("/").get_data(as_text=True)
    assert "待审核" in restarted_client.get("/my/registrations").get_data(as_text=True)
    assert "重启活动" in restarted_client.get("/messages").get_data(as_text=True)


# ---------------- 其他规则 ----------------


def test_cannot_register_after_activity_started(client, conn):
    activity_id = create_activity(
        client, conn, title="已开始活动", start_at="2000-01-01 10:00"
    )
    login(client, STUDENT_A)
    page = register(client, activity_id).get_data(as_text=True)
    assert "活动已开始" in page

    count = conn.execute(
        "SELECT COUNT(*) AS n FROM registrations WHERE activity_id = ?",
        (activity_id,),
    ).fetchone()["n"]
    assert count == 0


def test_delete_activity_with_registrations_is_rejected(client, conn):
    activity_id = create_activity(client, conn, title="有报名活动")
    login(client, STUDENT_A)
    register(client, activity_id)

    response = client.post(
        f"/admin/activities/{activity_id}/delete", follow_redirects=True
    )
    assert "不能删除" in response.get_data(as_text=True)

    still_there = conn.execute(
        "SELECT COUNT(*) AS n FROM activities WHERE activity_id = ?", (activity_id,)
    ).fetchone()["n"]
    assert still_there == 1


def test_delete_empty_activity_succeeds(client, conn):
    activity_id = create_activity(client, conn, title="空活动")
    response = client.post(
        f"/admin/activities/{activity_id}/delete", follow_redirects=True
    )
    assert "活动已删除" in response.get_data(as_text=True)
    gone = conn.execute(
        "SELECT COUNT(*) AS n FROM activities WHERE activity_id = ?", (activity_id,)
    ).fetchone()["n"]
    assert gone == 0


def test_notification_message_is_deduplicated(client, conn):
    activity_id = create_activity(client, conn, title="去重活动")
    login(client, STUDENT_A)
    register(client, activity_id)

    first = conn.execute(
        "SELECT COUNT(*) AS n FROM messages WHERE student_id = ?", (STUDENT_A,)
    ).fetchone()["n"]
    assert first == 1


def test_event_bus_logs_handler_failure(tmp_path):
    log_path = tmp_path / "failures.log"
    bus = EventBus(log_path)

    def broken_handler(event):
        raise RuntimeError("boom")

    bus.subscribe("*", broken_handler)
    event = RegistrationEvent(
        type=EVENT_APPROVED,
        registration=SimpleNamespace(registration_id=1, status="已通过"),
        activity=SimpleNamespace(activity_id=1, title="活动"),
        student_id=STUDENT_A,
    )
    bus.publish(event)

    assert log_path.exists()
    assert "boom" in log_path.read_text(encoding="utf-8")


def test_invalid_activity_form_shows_errors(client, conn):
    response = client.post(
        "/admin/activities/new",
        data={
            "title": "",
            "category": "",
            "start_at": "不是日期",
            "location": "",
            "capacity": "0",
            "policy_type": "unknown",
        },
    )
    assert response.status_code == 400
    page = response.get_data(as_text=True)
    assert "活动名称必填" in page
    assert "开始时间格式" in page
    count = conn.execute("SELECT COUNT(*) AS n FROM activities").fetchone()["n"]
    assert count == 0


def test_activity_detail_missing_returns_404(client):
    response = client.get("/activities/9999")
    assert response.status_code == 404


def test_messages_can_be_marked_read(client, conn):
    activity_id = create_activity(client, conn, title="消息活动")
    login(client, STUDENT_A)
    register(client, activity_id)
    message = conn.execute(
        "SELECT * FROM messages WHERE student_id = ?", (STUDENT_A,)
    ).fetchone()
    assert message["is_read"] == 0

    client.post(f"/messages/{message['message_id']}/read")
    row = conn.execute(
        "SELECT is_read FROM messages WHERE message_id = ?", (message["message_id"],)
    ).fetchone()
    assert row["is_read"] == 1

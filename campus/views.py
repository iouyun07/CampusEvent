from __future__ import annotations

from pathlib import Path

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from .capacity import CapacityChecker
from .db import get_db
from .events import EventBus
from .models import POLICY_LABELS
from .notifications import NotificationObserver
from .repositories import (
    ActivityRepository,
    MessageRepository,
    RegistrationRepository,
)
from .services import ActivityService, RegistrationService

bp = Blueprint("main", __name__)

DEFAULT_STUDENT = "2023001"


def _student_id() -> str:
    return session.get("student_id", DEFAULT_STUDENT)


def _ensure_student(conn, student_id: str) -> None:
    row = conn.execute(
        "SELECT 1 FROM students WHERE student_id = ?", (student_id,)
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO students (student_id, name) VALUES (?, ?)",
            (student_id, "演示学生"),
        )


def _ctx() -> dict:
    conn = get_db()
    activities = ActivityRepository(conn)
    registrations = RegistrationRepository(conn)
    messages = MessageRepository(conn)

    checker = CapacityChecker(registrations)
    bus = EventBus(Path(current_app.config["FAILURE_LOG"]))
    bus.subscribe("*", NotificationObserver(messages).handle)

    return {
        "conn": conn,
        "activities": activities,
        "registrations": registrations,
        "messages": messages,
        "checker": checker,
        "bus": bus,
        "registration_service": RegistrationService(
            conn, activities, registrations, messages, checker, bus
        ),
        "activity_service": ActivityService(conn, activities, registrations),
    }


@bp.before_request
def _prepare_session() -> None:
    if "student_id" not in session:
        session["student_id"] = DEFAULT_STUDENT
    _ensure_student(get_db(), session["student_id"])


def _unread() -> int:
    return MessageRepository(get_db()).unread_count(_student_id())


# ---------------- 学生端 ----------------


@bp.get("/")
def index():
    ctx = _ctx()
    keyword = (request.args.get("keyword") or "").strip()
    rows = []
    for activity in ctx["activities"].list(keyword):
        rows.append(
            {
                "activity": activity,
                "my": ctx["registrations"].find_active(activity.activity_id, _student_id()),
                "remaining": ctx["checker"].remaining(activity),
            }
        )
    return render_template("index.html", rows=rows, keyword=keyword, unread=_unread())


@bp.get("/activities/<int:activity_id>")
def activity_detail(activity_id: int):
    ctx = _ctx()
    activity = ctx["activities"].get(activity_id)
    if activity is None:
        return render_template("404.html"), 404
    mine = ctx["registrations"].find_active(activity_id, _student_id())
    history = ctx["registrations"].list_by_student(_student_id())
    history = [row for row in history if row["activity_id"] == activity_id]
    return render_template(
        "activity_detail.html",
        activity=activity,
        stats=ctx["activity_service"].stats(activity_id),
        mine=mine,
        history=history,
        unread=_unread(),
        policy_label=POLICY_LABELS.get(activity.policy_type, activity.policy_type),
    )


@bp.post("/activities/<int:activity_id>/register")
def register(activity_id: int):
    result = _ctx()["registration_service"].submit(activity_id, _student_id())
    flash(result.message or ("报名成功" if result.ok else "报名失败"), "ok" if result.ok else "error")
    return redirect(url_for("main.activity_detail", activity_id=activity_id))


@bp.post("/registrations/<int:registration_id>/cancel")
def cancel(registration_id: int):
    result = _ctx()["registration_service"].cancel(registration_id, _student_id())
    flash(result.message or ("已取消报名" if result.ok else "取消失败"), "ok" if result.ok else "error")
    return redirect(request.form.get("next") or url_for("main.my_registrations"))


@bp.get("/my/registrations")
def my_registrations():
    ctx = _ctx()
    rows = ctx["registrations"].list_by_student(_student_id())
    return render_template("my_registrations.html", rows=rows, unread=_unread())


@bp.get("/messages")
def messages():
    ctx = _ctx()
    rows = ctx["messages"].list_by_student(_student_id())
    return render_template("messages.html", rows=rows, unread=_unread())


@bp.post("/messages/<int:message_id>/read")
def read_message(message_id: int):
    _ctx()["messages"].mark_read(message_id, _student_id())
    return redirect(url_for("main.messages"))


@bp.post("/messages/read-all")
def read_all_messages():
    _ctx()["messages"].mark_all_read(_student_id())
    return redirect(url_for("main.messages"))


# ---------------- 管理端 ----------------


@bp.get("/admin")
def admin_index():
    ctx = _ctx()
    rows = []
    for activity in ctx["activities"].list():
        rows.append(
            {
                "activity": activity,
                "stats": ctx["activity_service"].stats(activity.activity_id),
                "total": ctx["registrations"].count_all(activity.activity_id),
            }
        )
    return render_template("admin_index.html", rows=rows, unread=_unread())


@bp.get("/admin/activities/new")
def activity_new():
    return render_template(
        "activity_form.html",
        activity=None,
        errors={},
        form={},
        unread=_unread(),
    )


@bp.post("/admin/activities/new")
def activity_create():
    result = _ctx()["activity_service"].create(request.form)
    if not result.ok:
        flash(result.message, "error")
        return render_template(
            "activity_form.html",
            activity=None,
            errors=result.errors,
            form=request.form,
            unread=_unread(),
        ), 400
    flash("活动创建成功", "ok")
    return redirect(url_for("main.admin_index"))


@bp.get("/admin/activities/<int:activity_id>/edit")
def activity_edit(activity_id: int):
    activity = _ctx()["activities"].get(activity_id)
    if activity is None:
        return render_template("404.html"), 404
    return render_template(
        "activity_form.html",
        activity=activity,
        errors={},
        form={
            "title": activity.title,
            "category": activity.category,
            "start_at": activity.start_at,
            "location": activity.location,
            "capacity": activity.capacity,
            "policy_type": activity.policy_type,
        },
        unread=_unread(),
    )


@bp.post("/admin/activities/<int:activity_id>/edit")
def activity_update(activity_id: int):
    result = _ctx()["activity_service"].update(activity_id, request.form)
    if not result.ok:
        flash(result.message, "error")
        activity = _ctx()["activities"].get(activity_id)
        return render_template(
            "activity_form.html",
            activity=activity,
            errors=result.errors,
            form=request.form,
            unread=_unread(),
        ), 400
    flash("活动已更新", "ok")
    return redirect(url_for("main.admin_index"))


@bp.post("/admin/activities/<int:activity_id>/delete")
def activity_delete(activity_id: int):
    result = _ctx()["activity_service"].delete(activity_id)
    flash(result.message or ("活动已删除" if result.ok else "删除失败"), "ok" if result.ok else "error")
    return redirect(url_for("main.admin_index"))


@bp.get("/admin/approvals")
def admin_approvals():
    ctx = _ctx()
    rows = ctx["registrations"].list_pending()
    return render_template("approvals.html", rows=rows, unread=_unread())


@bp.post("/admin/approvals/<int:registration_id>/approve")
def approve(registration_id: int):
    result = _ctx()["registration_service"].approve(registration_id)
    flash(result.message or ("已通过" if result.ok else "操作失败"), "ok" if result.ok else "error")
    return redirect(url_for("main.admin_approvals"))


@bp.post("/admin/approvals/<int:registration_id>/reject")
def reject(registration_id: int):
    result = _ctx()["registration_service"].reject(registration_id)
    flash(result.message or ("已拒绝" if result.ok else "操作失败"), "ok" if result.ok else "error")
    return redirect(url_for("main.admin_approvals"))

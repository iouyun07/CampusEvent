from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime

from .capacity import CapacityChecker
from .db import transaction
from .events import (
    EVENT_APPROVED,
    EVENT_CANCELLED,
    EVENT_REJECTED,
    EVENT_SUBMITTED,
    EventBus,
    RegistrationEvent,
)
from .models import (
    POLICY_LABELS,
    STATUS_APPROVED,
    STATUS_CANCELLED,
    STATUS_PENDING,
    STATUS_REJECTED,
)
from .policies import POLICIES, PolicyContext, RegistrationPolicy
from .repositories import (
    ActivityRepository,
    MessageRepository,
    RegistrationRepository,
)


@dataclass
class Result:
    ok: bool
    code: str = ""
    message: str = ""
    errors: dict[str, str] = field(default_factory=dict)
    data: object = None


class RegistrationService:
    def __init__(
        self,
        conn: sqlite3.Connection,
        activities: ActivityRepository,
        registrations: RegistrationRepository,
        messages: MessageRepository,
        checker: CapacityChecker,
        bus: EventBus,
        policies: dict[str, RegistrationPolicy] | None = None,
    ):
        self.conn = conn
        self.activities = activities
        self.registrations = registrations
        self.messages = messages
        self.checker = checker
        self.bus = bus
        self.policies = policies if policies is not None else POLICIES

    # ---------- 报名 ----------
    def submit(self, activity_id: int, student_id: str) -> Result:
        activity = self.activities.get(activity_id)
        if activity is None:
            return Result(False, "not_found", "活动不存在")
        if activity.has_started():
            return Result(False, "started", "活动已开始，不能再报名")
        if self.registrations.find_active(activity_id, student_id) is not None:
            return Result(False, "duplicate", "你已报名该活动，请勿重复报名")

        policy = self.policies.get(activity.policy_type)
        if policy is None:
            return Result(False, "policy_missing", "该活动未配置报名规则")

        outcome = policy.submit(PolicyContext(activity, student_id, self.checker))
        if not outcome.ok:
            return Result(False, outcome.code, outcome.message)

        try:
            with transaction(self.conn):
                registration_id = self.registrations.create(
                    activity_id, student_id, outcome.status or STATUS_PENDING
                )
        except sqlite3.IntegrityError:
            return Result(False, "duplicate", "你已报名该活动，请勿重复报名")

        registration = self.registrations.get(registration_id)
        event_type = (
            EVENT_APPROVED
            if registration.status == STATUS_APPROVED
            else EVENT_SUBMITTED
        )
        self._emit(event_type, registration, activity, student_id)
        return Result(True, data=registration)

    # ---------- 审批 ----------
    def approve(self, registration_id: int) -> Result:
        registration = self.registrations.get(registration_id)
        if registration is None:
            return Result(False, "not_found", "报名记录不存在")
        if registration.status != STATUS_PENDING:
            return Result(False, "invalid_status", "该报名已被处理")
        activity = self.activities.get(registration.activity_id)
        if activity is None:
            return Result(False, "not_found", "活动不存在")

        with transaction(self.conn, immediate=True):
            current = self.registrations.get(registration_id)
            if current is None or current.status != STATUS_PENDING:
                return Result(False, "invalid_status", "该报名已被处理")
            if not self.checker.has_room(activity):
                return Result(False, "capacity_full", "名额已满，无法通过该报名")
            self.registrations.update_status(registration_id, STATUS_APPROVED)

        updated = self.registrations.get(registration_id)
        self._emit(EVENT_APPROVED, updated, activity, updated.student_id)
        return Result(True, data=updated)

    def reject(self, registration_id: int) -> Result:
        registration = self.registrations.get(registration_id)
        if registration is None:
            return Result(False, "not_found", "报名记录不存在")
        if registration.status != STATUS_PENDING:
            return Result(False, "invalid_status", "该报名已被处理")
        activity = self.activities.get(registration.activity_id)

        with transaction(self.conn, immediate=True):
            current = self.registrations.get(registration_id)
            if current is None or current.status != STATUS_PENDING:
                return Result(False, "invalid_status", "该报名已被处理")
            self.registrations.update_status(registration_id, STATUS_REJECTED)

        updated = self.registrations.get(registration_id)
        if activity is not None:
            self._emit(EVENT_REJECTED, updated, activity, updated.student_id)
        return Result(True, data=updated)

    # ---------- 取消 ----------
    def cancel(self, registration_id: int, student_id: str | None = None) -> Result:
        registration = self.registrations.get(registration_id)
        if registration is None:
            return Result(False, "not_found", "报名记录不存在")
        if student_id is not None and registration.student_id != student_id:
            return Result(False, "forbidden", "只能取消自己的报名")
        if not registration.can_cancel():
            return Result(False, "invalid_status", "该报名当前不可取消")
        activity = self.activities.get(registration.activity_id)

        with transaction(self.conn, immediate=True):
            current = self.registrations.get(registration_id)
            if current is None or not current.can_cancel():
                return Result(False, "invalid_status", "该报名当前不可取消")
            self.registrations.update_status(registration_id, STATUS_CANCELLED)

        updated = self.registrations.get(registration_id)
        if activity is not None:
            self._emit(EVENT_CANCELLED, updated, activity, updated.student_id)
        return Result(True, data=updated)

    # ---------- 辅助 ----------
    def _emit(self, event_type: str, registration, activity, student_id: str) -> None:
        self.bus.publish(
            RegistrationEvent(
                type=event_type,
                registration=registration,
                activity=activity,
                student_id=student_id,
            )
        )


class ActivityService:
    def __init__(
        self,
        conn: sqlite3.Connection,
        activities: ActivityRepository,
        registrations: RegistrationRepository,
    ):
        self.conn = conn
        self.activities = activities
        self.registrations = registrations

    def _validate(self, form) -> tuple[dict, dict[str, str]]:
        data = {
            "title": (form.get("title") or "").strip(),
            "category": (form.get("category") or "").strip(),
            "start_at": (form.get("start_at") or "").strip(),
            "location": (form.get("location") or "").strip(),
            "capacity": (form.get("capacity") or "").strip(),
            "policy_type": (form.get("policy_type") or "").strip(),
        }
        errors: dict[str, str] = {}
        if not 1 <= len(data["title"]) <= 100:
            errors["title"] = "活动名称必填，长度 1-100"
        if not 1 <= len(data["category"]) <= 50:
            errors["category"] = "分类必填，长度 1-50"
        if not 1 <= len(data["location"]) <= 100:
            errors["location"] = "地点必填，长度 1-100"
        try:
            datetime.strptime(data["start_at"], "%Y-%m-%d %H:%M")
        except ValueError:
            errors["start_at"] = "开始时间格式应为 YYYY-MM-DD HH:MM"
        try:
            capacity = int(data["capacity"])
            if not 1 <= capacity <= 1000:
                raise ValueError
        except (TypeError, ValueError):
            errors["capacity"] = "名额必须为 1-1000 的整数"
            capacity = 0
        data["capacity"] = capacity
        if data["policy_type"] not in POLICY_LABELS:
            errors["policy_type"] = "请选择报名规则"
        return data, errors

    def create(self, form) -> Result:
        data, errors = self._validate(form)
        if errors:
            return Result(False, "invalid", "请检查表单", errors)
        with transaction(self.conn):
            activity_id = self.activities.create(**data)
        return Result(True, data=activity_id)

    def update(self, activity_id: int, form) -> Result:
        if self.activities.get(activity_id) is None:
            return Result(False, "not_found", "活动不存在")
        data, errors = self._validate(form)
        if errors:
            return Result(False, "invalid", "请检查表单", errors)
        with transaction(self.conn):
            self.activities.update(activity_id, **data)
        return Result(True, data=activity_id)

    def delete(self, activity_id: int) -> Result:
        activity = self.activities.get(activity_id)
        if activity is None:
            return Result(False, "not_found", "活动不存在")
        count = self.registrations.count_all(activity_id)
        if count:
            return Result(
                False,
                "has_registrations",
                f"该活动已有 {count} 条报名记录，不能删除；如不再举办请修改信息",
            )
        with transaction(self.conn):
            self.activities.delete(activity_id)
        return Result(True)

    def stats(self, activity_id: int) -> dict:
        activity = self.activities.get(activity_id)
        if activity is None:
            return {}
        approved = self.registrations.count_status(activity_id, STATUS_APPROVED)
        pending = self.registrations.count_status(activity_id, STATUS_PENDING)
        return {
            "approved": approved,
            "pending": pending,
            "remaining": max(activity.capacity - approved, 0),
        }

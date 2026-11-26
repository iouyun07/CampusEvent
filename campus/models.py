from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

STATUS_PENDING = "待审核"
STATUS_APPROVED = "已通过"
STATUS_REJECTED = "已拒绝"
STATUS_CANCELLED = "已取消"

ACTIVE_STATUSES = (STATUS_PENDING, STATUS_APPROVED)

POLICY_DIRECT = "direct"
POLICY_REVIEW = "review"
POLICY_GRADE = "grade_limited"
POLICY_LABELS = {
    POLICY_DIRECT: "直接报名",
    POLICY_REVIEW: "需审核",
    POLICY_GRADE: "年级限定",
}

GRADE_LABELS = {1: "大一", 2: "大二", 3: "大三", 4: "大四"}

REGISTRATION_STATUSES = (STATUS_PENDING, STATUS_APPROVED, STATUS_REJECTED, STATUS_CANCELLED)


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@dataclass(frozen=True)
class Student:
    student_id: str
    name: str
    grade: int = 1

    def grade_label(self) -> str:
        return GRADE_LABELS.get(self.grade, f"{self.grade} 年级")


@dataclass(frozen=True)
class Activity:
    activity_id: int
    title: str
    category: str
    start_at: str
    location: str
    capacity: int
    policy_type: str

    def has_started(self, now: str | None = None) -> bool:
        return (now or now_text()) >= self.start_at

    def is_direct(self) -> bool:
        return self.policy_type == POLICY_DIRECT


@dataclass(frozen=True)
class Registration:
    registration_id: int
    activity_id: int
    student_id: str
    status: str
    created_at: str
    updated_at: str

    def is_active(self) -> bool:
        return self.status in ACTIVE_STATUSES

    def can_cancel(self) -> bool:
        return self.status in ACTIVE_STATUSES


@dataclass(frozen=True)
class Message:
    message_id: int
    student_id: str
    activity_id: int
    content: str
    created_at: str
    is_read: bool
    dedupe_key: str


@dataclass(frozen=True)
class Email:
    email_id: int
    student_id: str
    activity_id: int
    registration_id: int
    to_addr: str
    subject: str
    body: str
    status: str
    error: str
    dedupe_key: str
    created_at: str

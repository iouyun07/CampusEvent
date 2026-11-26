from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from .capacity import CapacityChecker
from .models import (
    POLICY_DIRECT,
    POLICY_GRADE,
    POLICY_REVIEW,
    STATUS_APPROVED,
    STATUS_PENDING,
    Activity,
    Student,
)


@dataclass(frozen=True)
class PolicyResult:
    ok: bool
    status: str | None = None
    code: str = ""
    message: str = ""


@dataclass(frozen=True)
class PolicyContext:
    activity: Activity
    student_id: str
    checker: CapacityChecker
    student: Student | None = None


class RegistrationPolicy(ABC):
    """报名策略：只决定“提交后进入什么状态”，不直接写库。"""

    name: str

    @abstractmethod
    def submit(self, ctx: PolicyContext) -> PolicyResult:
        raise NotImplementedError


class DirectRegistrationPolicy(RegistrationPolicy):
    name = POLICY_DIRECT

    def submit(self, ctx: PolicyContext) -> PolicyResult:
        if not ctx.checker.has_room(ctx.activity):
            return PolicyResult(False, code="capacity_full", message="名额已满，报名失败")
        return PolicyResult(True, status=STATUS_APPROVED)


class ReviewRegistrationPolicy(RegistrationPolicy):
    name = POLICY_REVIEW

    def submit(self, ctx: PolicyContext) -> PolicyResult:
        return PolicyResult(True, status=STATUS_PENDING)


class GradeLimitedPolicy(DirectRegistrationPolicy):
    """年级限定的直接报名：先校验年级，再复用直接报名（含名额检查）。

    继承 DirectRegistrationPolicy 而不是复制一份容量逻辑，
    保证「名额检查」只有一处实现；年级规则单独可读、可替换 allowed_grades。
    """

    name = POLICY_GRADE
    allowed_grades = (2, 3)

    def submit(self, ctx: PolicyContext) -> PolicyResult:
        student = ctx.student
        if student is None:
            return PolicyResult(
                False, code="student_missing", message="无法确认学生年级，报名失败"
            )
        if student.grade not in self.allowed_grades:
            grades = "、".join(f"大{g}" for g in self.allowed_grades)
            return PolicyResult(
                False,
                code="grade_denied",
                message=f"该活动仅限{grades}学生报名，你当前为{student.grade_label()}",
            )
        return super().submit(ctx)


POLICIES: dict[str, RegistrationPolicy] = {
    POLICY_DIRECT: DirectRegistrationPolicy(),
    POLICY_REVIEW: ReviewRegistrationPolicy(),
    POLICY_GRADE: GradeLimitedPolicy(),
}

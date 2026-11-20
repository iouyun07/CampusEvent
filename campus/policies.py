from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from .capacity import CapacityChecker
from .models import (
    POLICY_DIRECT,
    POLICY_REVIEW,
    STATUS_APPROVED,
    STATUS_PENDING,
    Activity,
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


POLICIES: dict[str, RegistrationPolicy] = {
    POLICY_DIRECT: DirectRegistrationPolicy(),
    POLICY_REVIEW: ReviewRegistrationPolicy(),
}

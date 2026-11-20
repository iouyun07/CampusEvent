from __future__ import annotations

from .models import STATUS_APPROVED, Activity
from .repositories import RegistrationRepository


class CapacityChecker:
    """名额公共规则：只有“已通过”的报名占用名额。"""

    def __init__(self, registrations: RegistrationRepository):
        self.registrations = registrations

    def approved_count(self, activity_id: int) -> int:
        return self.registrations.count_status(activity_id, STATUS_APPROVED)

    def remaining(self, activity: Activity) -> int:
        return max(activity.capacity - self.approved_count(activity.activity_id), 0)

    def has_room(self, activity: Activity) -> bool:
        return self.approved_count(activity.activity_id) < activity.capacity

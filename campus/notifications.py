from __future__ import annotations

from .events import (
    EVENT_APPROVED,
    EVENT_CANCELLED,
    EVENT_REJECTED,
    EVENT_SUBMITTED,
    RegistrationEvent,
)
from .repositories import MessageRepository

_CONTENT = {
    EVENT_SUBMITTED: "你已提交「{title}」的报名，等待管理员审核。",
    EVENT_APPROVED: "你报名的「{title}」已通过。",
    EVENT_REJECTED: "你报名的「{title}」未通过审核。",
    EVENT_CANCELLED: "你已取消「{title}」的报名。",
}


class NotificationObserver:
    """观察者：把报名事件翻译成站内消息，按 dedupe_key 幂等写入。"""

    def __init__(self, messages: MessageRepository):
        self.messages = messages

    def handle(self, event: RegistrationEvent) -> None:
        template = _CONTENT.get(event.type)
        if template is None:
            return
        content = template.format(title=event.activity.title)
        dedupe_key = f"{event.type}:{event.registration.registration_id}:{event.registration.status}"
        self.messages.add(
            event.student_id, event.activity.activity_id, content, dedupe_key
        )

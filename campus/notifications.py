from __future__ import annotations

from pathlib import Path

from .events import (
    EVENT_APPROVED,
    EVENT_CANCELLED,
    EVENT_REJECTED,
    EVENT_SUBMITTED,
    RegistrationEvent,
)
from .mock_email import MockEmailSender
from .repositories import EmailRepository, MessageRepository

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


_EMAIL_SUBJECT = "报名结果通知：{title}"
_EMAIL_BODY = {
    EVENT_APPROVED: "你报名的「{title}」已通过，请按时参加。",
    EVENT_REJECTED: "你报名的「{title}」未通过审核。",
}


class EmailNotifier:
    """观察者：把通过/拒绝事件翻译成模拟邮件，按 dedupe_key 幂等发送。

    先占位（INSERT OR IGNORE）再发送：重复事件不会重复发信；
    发送异常只更新邮件状态与错误日志，不向上抛，也就不影响报名事务。
    """

    def __init__(
        self,
        emails: EmailRepository,
        sender: MockEmailSender,
        failure_log: str | Path | None = None,
    ):
        self.emails = emails
        self.sender = sender
        self.failure_log = Path(failure_log) if failure_log else None

    def handle(self, event: RegistrationEvent) -> None:
        body_template = _EMAIL_BODY.get(event.type)
        if body_template is None:
            return
        registration = event.registration
        subject = _EMAIL_SUBJECT.format(title=event.activity.title)
        body = body_template.format(title=event.activity.title)
        to_addr = f"{event.student_id}@campus.example.com"
        dedupe_key = f"email:{event.type}:{registration.registration_id}:{registration.status}"
        try:
            email_id = self.emails.add(
                student_id=event.student_id,
                activity_id=event.activity.activity_id,
                registration_id=registration.registration_id,
                to_addr=to_addr,
                subject=subject,
                body=body,
                dedupe_key=dedupe_key,
            )
            if not email_id:
                return
            try:
                self.sender.send(to_addr, subject, body)
            except Exception as exc:  # 发送失败：记录，不影响报名
                self.emails.mark_failed(email_id, str(exc))
                self._log_failure(event, exc)
            else:
                self.emails.mark_sent(email_id)
        except Exception as exc:  # 兜底：通知绝不向上抛
            self._log_failure(event, exc)

    def _log_failure(self, event: RegistrationEvent, exc: Exception) -> None:
        if self.failure_log is None:
            return
        try:
            with self.failure_log.open("a", encoding="utf-8") as fh:
                fh.write(
                    f"[{event.type}] registration={event.registration.registration_id}"
                    f" error={exc}\n"
                )
        except OSError:
            pass

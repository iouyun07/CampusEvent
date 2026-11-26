"""模拟邮件发送器：不联网，只记录调用结果；可对指定学生注入失败用于演示/测试。"""
from __future__ import annotations

from dataclasses import dataclass, field

from .models import now_text


@dataclass
class SentEmail:
    student_id: str
    to_addr: str
    subject: str
    body: str
    status: str
    at: str


class MockEmailSender:
    def __init__(self, fail_for: set[str] | None = None):
        self.fail_for = set(fail_for or ())
        self.outbox: list[SentEmail] = []

    def send(self, to_addr: str, subject: str, body: str) -> SentEmail:
        student_id = to_addr.split("@", 1)[0]
        if student_id in self.fail_for:
            record = SentEmail(student_id, to_addr, subject, body, "失败", now_text())
            self.outbox.append(record)
            raise RuntimeError(f"模拟邮件发送失败：{to_addr}")
        record = SentEmail(student_id, to_addr, subject, body, "已发送", now_text())
        self.outbox.append(record)
        return record

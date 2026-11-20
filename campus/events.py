from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .models import Activity, Registration

EVENT_SUBMITTED = "submitted"
EVENT_APPROVED = "approved"
EVENT_REJECTED = "rejected"
EVENT_CANCELLED = "cancelled"


@dataclass(frozen=True)
class RegistrationEvent:
    type: str
    registration: Registration
    activity: Activity
    student_id: str


Handler = Callable[[RegistrationEvent], None]


class EventBus:
    """进程内同步事件总线：订阅者异常互不影响，失败写日志留痕（R6）。"""

    def __init__(self, failure_log: Path | None = None):
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self.failure_log = failure_log

    def subscribe(self, event_type: str, handler: Handler) -> None:
        self._handlers[event_type].append(handler)

    def publish(self, event: RegistrationEvent) -> list[str]:
        failures: list[str] = []
        handlers = list(self._handlers.get(event.type, ())) + list(self._handlers.get("*", ()))
        for handler in handlers:
            try:
                handler(event)
            except Exception as exc:  # 通知失败不影响业务事务
                failures.append(f"{event.type}: {exc!r}")
        if failures and self.failure_log is not None:
            self.failure_log.parent.mkdir(parents=True, exist_ok=True)
            with self.failure_log.open("a", encoding="utf-8") as fh:
                for line in failures:
                    fh.write(line + "\n")
        return failures

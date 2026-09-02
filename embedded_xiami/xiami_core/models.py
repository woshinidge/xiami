from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


MessageType = Literal["private", "group", "system"]


@dataclass(frozen=True)
class MessageSegment:
    type: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AccountStatus:
    state: Literal["offline", "starting", "waiting_qr", "online", "error"]
    account: str = ""
    detail: str = ""
    logs: tuple[str, ...] = ()
    qr_hint: str = ""


@dataclass(frozen=True)
class XiamiMessage:
    message_type: MessageType
    sender: str
    text: str
    target: str = ""
    self_id: str = ""
    raw_message: str = ""
    segments: tuple[MessageSegment, ...] = ()
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class SendResult:
    ok: bool
    detail: str = ""
    message_id: str = ""

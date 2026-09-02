from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from xiami_core.models import MessageSegment, XiamiMessage


@dataclass(frozen=True)
class PluginEvent:
    type: str
    message: XiamiMessage | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def message_type(self) -> str:
        if self.message:
            return self.message.message_type
        return str(self.raw.get("message_type") or self.raw.get("detail_type") or "")

    @property
    def post_type(self) -> str:
        return str(self.raw.get("post_type") or self.type or "")

    @property
    def notice_type(self) -> str:
        return str(self.raw.get("notice_type") or "")

    @property
    def request_type(self) -> str:
        return str(self.raw.get("request_type") or "")

    @property
    def sub_type(self) -> str:
        return str(self.raw.get("sub_type") or "")

    @property
    def detail_type(self) -> str:
        return str(self.raw.get("detail_type") or "")

    @property
    def user_id(self) -> str:
        if self.message:
            return self.message.sender
        sender = self.raw.get("sender")
        if isinstance(sender, dict):
            value = sender.get("user_id") or sender.get("uin")
            if value:
                return str(value)
        value = self.raw.get("user_id") or self.raw.get("operator_id")
        return str(value or "")

    @property
    def operator_id(self) -> str:
        value = self.raw.get("operator_id")
        return str(value or "")

    @property
    def group_id(self) -> str:
        if self.message and self.message.message_type == "group":
            return self.message.target
        value = self.raw.get("group_id")
        return str(value or "")

    @property
    def target_id(self) -> str:
        value = self.raw.get("target_id")
        return str(value or "")

    @property
    def message_id(self) -> str:
        value = self.raw.get("message_id")
        return str(value or "")

    @property
    def flag(self) -> str:
        return str(self.raw.get("flag") or "")

    @property
    def comment(self) -> str:
        return str(self.raw.get("comment") or "")

    @property
    def text(self) -> str:
        return self.message.text if self.message else str(self.raw.get("raw_message") or "")

    @property
    def raw_message(self) -> str:
        if self.message:
            return self.message.raw_message or self.message.text
        return str(self.raw.get("raw_message") or self.raw.get("message") or "")

    @property
    def segments(self) -> tuple[MessageSegment, ...]:
        return self.message.segments if self.message else ()

    @property
    def is_private(self) -> bool:
        return self.message_type == "private"

    @property
    def is_group(self) -> bool:
        return self.message_type == "group"


def plugin_event_from_message(message: XiamiMessage) -> PluginEvent:
    return PluginEvent(type="message", message=message)


def plugin_event_from_onebot(payload: dict[str, Any], message: XiamiMessage | None = None) -> PluginEvent:
    event_type = str(payload.get("post_type") or "event")
    return PluginEvent(type=event_type, message=message, raw=payload.copy())

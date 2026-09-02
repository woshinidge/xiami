from __future__ import annotations

from typing import Any

from xiami_core.models import XiamiMessage
from xiami_core.onebot.message_segments import parse_onebot_segments, segments_to_text
from xiami_core.text_clean import clean_text


def parse_onebot_event(payload: dict[str, Any]) -> XiamiMessage | None:
    if payload.get("post_type") != "message":
        return None
    message_type = str(payload.get("message_type") or payload.get("detail_type") or "")
    if not message_type:
        message_type = "group" if _first_text(payload, "group_id", "group") else "private"
    raw_message = _raw_message(payload.get("message"), payload.get("raw_message"))
    segments = parse_onebot_segments(payload.get("message"), payload.get("raw_message"))
    text = clean_text(segments_to_text(segments, fallback=raw_message))
    self_id = clean_text(_first_text(payload, "self_id"))
    if message_type == "group" or _first_text(payload, "group_id", "group"):
        return XiamiMessage(
            message_type="group",
            sender=clean_text(_sender_id(payload)),
            target=clean_text(_first_text(payload, "group_id", "group")),
            text=text,
            self_id=self_id,
            raw_message=clean_text(raw_message),
            segments=segments,
        )
    return XiamiMessage(
        message_type="private",
        sender=clean_text(_sender_id(payload)),
        target=clean_text(_first_text(payload, "self_id", "target_id", "peer_id")),
        text=text,
        self_id=self_id,
        raw_message=clean_text(raw_message),
        segments=segments,
    )


def _raw_message(message: Any, raw_message: Any = None) -> str:
    if raw_message is not None:
        return str(raw_message or "")
    if isinstance(message, list):
        return ""
    return str(message or "")


def _sender_id(payload: dict[str, Any]) -> str:
    sender = payload.get("sender")
    if isinstance(sender, dict):
        value = sender.get("user_id") or sender.get("uin")
        if value:
            return str(value)
    return _first_text(payload, "user_id", "sender_id", "from_id")


def _first_text(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value is not None and value != "":
            return str(value)
    return ""

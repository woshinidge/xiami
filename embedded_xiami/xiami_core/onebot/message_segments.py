from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from xiami_core.models import MessageSegment

_CQ_PATTERN = re.compile(r"\[CQ:(?P<type>[a-zA-Z0-9_]+)(?P<params>(?:,[^\]]*)?)\]")


def parse_onebot_segments(message: Any, raw_message: Any = None) -> tuple[MessageSegment, ...]:
    if isinstance(message, list):
        segments: list[MessageSegment] = []
        for item in message:
            segment = _segment_from_object(item)
            if segment:
                segments.append(segment)
        return tuple(segments)
    if isinstance(message, str):
        return parse_cq_message(message)
    if raw_message is not None:
        return parse_cq_message(str(raw_message or ""))
    return ()


def parse_cq_message(message: str) -> tuple[MessageSegment, ...]:
    segments: list[MessageSegment] = []
    cursor = 0
    for match in _CQ_PATTERN.finditer(message):
        if match.start() > cursor:
            segments.append(MessageSegment("text", {"text": _cq_unescape(message[cursor : match.start()])}))
        params = _parse_cq_params(match.group("params") or "")
        segments.append(MessageSegment(match.group("type"), params))
        cursor = match.end()
    if cursor < len(message):
        segments.append(MessageSegment("text", {"text": _cq_unescape(message[cursor:])}))
    return tuple(segment for segment in segments if segment.type != "text" or segment.data.get("text"))


def segments_to_text(segments: Iterable[MessageSegment], fallback: str = "") -> str:
    parts: list[str] = []
    for segment in segments:
        if segment.type == "text":
            parts.append(str(segment.data.get("text", "")))
        elif segment.type == "at":
            qq = str(segment.data.get("qq") or "")
            parts.append(f"@{qq}" if qq else "[at]")
        elif segment.type == "image":
            parts.append("[图片]")
        elif segment.type == "face":
            parts.append("[表情]")
        elif segment.type == "reply":
            parts.append("[回复]")
        elif segment.type == "record":
            parts.append("[语音]")
        elif segment.type == "video":
            parts.append("[视频]")
        elif segment.type == "file":
            parts.append("[文件]")
        elif segment.type:
            parts.append(f"[{segment.type}]")
    text = "".join(parts)
    return text if text else fallback


def cq_text(text: str) -> str:
    return _cq_escape(text)


def cq_image(file: str) -> str:
    return f"[CQ:image,file={_cq_escape_param(file)}]"


def cq_at(user_id: str | int) -> str:
    return f"[CQ:at,qq={_cq_escape_param(str(user_id))}]"


def cq_reply(message_id: str | int) -> str:
    return f"[CQ:reply,id={_cq_escape_param(str(message_id))}]"


def segments_to_cq(segments: Iterable[MessageSegment]) -> str:
    parts: list[str] = []
    for segment in segments:
        if segment.type == "text":
            parts.append(cq_text(str(segment.data.get("text", ""))))
            continue
        params = ",".join(f"{key}={_cq_escape_param(str(value))}" for key, value in segment.data.items())
        suffix = f",{params}" if params else ""
        parts.append(f"[CQ:{segment.type}{suffix}]")
    return "".join(parts)


def _segment_from_object(item: object) -> MessageSegment | None:
    if not isinstance(item, dict):
        return None
    segment_type = str(item.get("type") or "").strip()
    if not segment_type:
        return None
    data = item.get("data") or {}
    return MessageSegment(segment_type, data.copy() if isinstance(data, dict) else {})


def _parse_cq_params(params: str) -> dict[str, str]:
    if params.startswith(","):
        params = params[1:]
    if not params:
        return {}
    result: dict[str, str] = {}
    for part in params.split(","):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        result[key] = _cq_unescape(value)
    return result


def _cq_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("[", "&#91;").replace("]", "&#93;")


def _cq_escape_param(text: str) -> str:
    return _cq_escape(text).replace(",", "&#44;")


def _cq_unescape(text: str) -> str:
    return text.replace("&#44;", ",").replace("&#91;", "[").replace("&#93;", "]").replace("&amp;", "&")

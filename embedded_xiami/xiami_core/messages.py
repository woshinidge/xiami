from __future__ import annotations

import json
import re
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from xiami_core.models import MessageType
from xiami_core.storage.paths import LOG_HOME, ensure_runtime_dirs
from xiami_core.text_clean import clean_text


MessageDirection = Literal["incoming", "outgoing", "plugin", "kernel"]
MessageStatus = Literal["ok", "failed"]


@dataclass(frozen=True)
class MessageRecord:
    direction: MessageDirection
    message_type: MessageType
    target: str
    sender: str = ""
    text: str = ""
    status: MessageStatus = "ok"
    detail: str = ""
    message_id: str = ""
    source: str = "ui"
    timestamp: datetime = field(default_factory=datetime.now)


class MessageStore:
    def __init__(self, path: Path | None = None, max_records: int = 500) -> None:
        ensure_runtime_dirs()
        self.path = path or LOG_HOME / "messages.jsonl"
        self.max_records = max_records
        self._lock = threading.Lock()

    def append(self, record: MessageRecord) -> MessageRecord:
        record = clean_message_record(record)
        line = json.dumps(_record_to_json(record), ensure_ascii=False) + "\n"
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as file:
                file.write(line)
        return record

    def recent(self, limit: int = 100) -> list[MessageRecord]:
        if not self.path.exists():
            return []
        records: list[MessageRecord] = []
        for line in self.path.read_text(encoding="utf-8", errors="replace").splitlines()[-self.max_records :]:
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            record = _record_from_json(data)
            if record:
                records.append(record)
        return records[-limit:]

    def clear(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text("", encoding="utf-8")

    def export_text(self, path: Path, records: list[MessageRecord] | None = None) -> Path:
        selected_records = records if records is not None else self.recent(self.max_records)
        lines = [format_message_record(record) for record in selected_records]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines), encoding="utf-8")
        return path


def format_message_record(record: MessageRecord) -> str:
    type_label = "群" if record.message_type == "group" else "好友"
    suffix = f" ({record.message_id})" if record.message_id else ""
    if record.direction == "incoming":
        target = record.target if record.message_type == "group" else record.sender
        return f"收到 [{type_label}] {target}/{record.sender} -> 我: {record.text}"
    if record.direction == "plugin":
        state = "成功" if record.status == "ok" else "失败"
        detail = record.text if record.status == "ok" else record.detail
        return f"插件回复{state} [{type_label}] -> {record.target}: {detail}{suffix}"
    if record.direction == "kernel":
        return f"内核接收 [{type_label}] {record.target}/{record.sender} -> 我: {record.text}"
    state = "成功" if record.status == "ok" else "失败"
    detail = record.text if record.status == "ok" else record.detail
    prefix = "真实发送" if record.status == "ok" else "发送"
    return f"{prefix}{state} [{type_label}] -> {record.target}: {detail}{suffix}"


def clean_message_record(record: MessageRecord) -> MessageRecord:
    return MessageRecord(
        direction=record.direction,
        message_type=record.message_type,
        target=clean_text(record.target),
        sender=clean_text(record.sender),
        text=clean_text(record.text),
        status=record.status,
        detail=clean_text(record.detail),
        message_id=clean_text(record.message_id),
        source=record.source,
        timestamp=record.timestamp,
    )


def conversation_key(record: MessageRecord) -> str:
    target = _conversation_target(record)
    return f"{record.message_type}:{target}"


def conversation_title(record: MessageRecord) -> str:
    label = "群" if record.message_type == "group" else "好友"
    target = _conversation_target(record)
    return f"{label} {target}"


def _conversation_target(record: MessageRecord) -> str:
    if record.message_type == "group":
        return _id_from_label(record.target) or _id_from_label(record.sender) or "未知群"
    if record.direction == "incoming":
        return _id_from_label(record.sender) or _id_from_label(record.target) or "未知好友"
    return _id_from_label(record.target) or _id_from_label(record.sender) or "未知好友"


def _id_from_label(value: str) -> str:
    value = str(value or "").strip()
    if not value:
        return ""
    matches = re.findall(r"\((\d{5,})\)", value)
    if matches:
        return matches[-1]
    return value


def _record_to_json(record: MessageRecord) -> dict[str, object]:
    data = asdict(record)
    data["timestamp"] = record.timestamp.isoformat(timespec="seconds")
    return data


def _record_from_json(data: object) -> MessageRecord | None:
    if not isinstance(data, dict):
        return None
    timestamp = data.get("timestamp")
    if isinstance(timestamp, str):
        try:
            parsed_time = datetime.fromisoformat(timestamp)
        except ValueError:
            parsed_time = datetime.now()
    else:
        parsed_time = datetime.now()
    try:
        return MessageRecord(
            direction=str(data.get("direction") or "incoming"),  # type: ignore[arg-type]
            message_type=str(data.get("message_type") or "private"),  # type: ignore[arg-type]
            target=str(data.get("target") or ""),
            sender=str(data.get("sender") or ""),
            text=str(data.get("text") or ""),
            status=str(data.get("status") or "ok"),  # type: ignore[arg-type]
            detail=str(data.get("detail") or ""),
            message_id=str(data.get("message_id") or ""),
            source=str(data.get("source") or "ui"),
            timestamp=parsed_time,
        )
    except TypeError:
        return None

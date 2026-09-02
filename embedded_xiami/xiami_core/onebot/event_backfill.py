from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from xiami_core.messages import MessageRecord, MessageStore
from xiami_core.storage.paths import LOG_HOME
from xiami_core.text_clean import clean_text


def backfill_messages_from_event_log(store: MessageStore | None = None, limit: int = 500) -> int:
    store = store or MessageStore()
    existing = {_record_key(record) for record in store.recent(limit)}
    added = 0
    for record in _records_from_event_log(limit):
        key = _record_key(record)
        if key in existing:
            continue
        store.append(record)
        existing.add(key)
        added += 1
    return added


def _records_from_event_log(limit: int) -> list[MessageRecord]:
    path = LOG_HOME / "onebot_events.jsonl"
    if not path.exists():
        return []
    records: list[MessageRecord] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict) or not entry.get("parsed"):
            continue
        record = _record_from_entry(entry)
        if record:
            records.append(record)
    return records


def _record_from_entry(entry: dict[str, Any]) -> MessageRecord | None:
    message_type = str(entry.get("parsed_type") or entry.get("message_type") or "")
    if message_type not in {"private", "group"}:
        return None
    sender = clean_text(entry.get("parsed_sender") or entry.get("user_id") or "")
    target = clean_text(entry.get("parsed_target") or entry.get("group_id") or "")
    text = clean_text(entry.get("parsed_text") or "")
    if not sender and not target and not text:
        return None
    timestamp = _parse_time(str(entry.get("time") or ""))
    return MessageRecord(
        direction="incoming",
        message_type=message_type,  # type: ignore[arg-type]
        target=target if message_type == "group" else sender,
        sender=sender,
        text=text,
        source="onebot_log",
        timestamp=timestamp,
    )


def _record_key(record: MessageRecord) -> tuple[str, str, str, str, str]:
    return (
        record.message_type,
        record.direction,
        record.target,
        record.sender,
        record.text,
    )


def _parse_time(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.now()

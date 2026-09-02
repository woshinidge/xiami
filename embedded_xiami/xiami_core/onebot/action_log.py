from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from xiami_core.storage.paths import LOG_HOME, ensure_runtime_dirs


ONEBOT_ACTION_LOG_FILE = LOG_HOME / "onebot_actions.jsonl"
_ACTION_LOG_LOCK = threading.Lock()


@dataclass(frozen=True)
class OneBotActionLogEntry:
    action: str
    ok: bool
    elapsed_ms: int
    message: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


def append_onebot_action_log(entry: OneBotActionLogEntry) -> None:
    ensure_runtime_dirs()
    payload = asdict(entry)
    payload["timestamp"] = entry.timestamp.isoformat(timespec="seconds")
    line = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
    with _ACTION_LOG_LOCK:
        ONEBOT_ACTION_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with ONEBOT_ACTION_LOG_FILE.open("a", encoding="utf-8") as file:
            file.write(line)


def load_onebot_action_logs(limit: int = 500) -> list[OneBotActionLogEntry]:
    if not ONEBOT_ACTION_LOG_FILE.exists():
        return []
    records: list[OneBotActionLogEntry] = []
    for line in ONEBOT_ACTION_LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]:
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        record = _entry_from_json(data)
        if record:
            records.append(record)
    return records


def compact_action_params(params: dict[str, Any], *, max_value_length: int = 120) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key, value in params.items():
        if key in {"message", "messages", "content"}:
            compact[key] = _short_text(value, max_value_length)
        else:
            compact[key] = value
    return compact


def _entry_from_json(data: object) -> OneBotActionLogEntry | None:
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
    params = data.get("params")
    if not isinstance(params, dict):
        params = {}
    return OneBotActionLogEntry(
        action=str(data.get("action") or ""),
        ok=bool(data.get("ok")),
        elapsed_ms=int(data.get("elapsed_ms") or 0),
        message=str(data.get("message") or ""),
        params=params,
        timestamp=parsed_time,
    )


def _short_text(value: Any, limit: int) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[:limit] + "...(truncated)"

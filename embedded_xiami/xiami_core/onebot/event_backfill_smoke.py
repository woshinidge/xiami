from __future__ import annotations

import json
from datetime import datetime

from xiami_core.testing import use_temp_xiami_home

use_temp_xiami_home()

from xiami_core.messages import MessageStore
from xiami_core.onebot.event_backfill import backfill_messages_from_event_log
from xiami_core.storage.paths import LOG_HOME


def main() -> int:
    _write_event("private", sender="10001", target="10000", text="hello private")
    _write_event("group", sender="10002", target="20001", text="hello group")
    store = MessageStore()
    added = backfill_messages_from_event_log(store)
    if added != 2:
        raise RuntimeError(f"unexpected backfill count: {added}")
    records = store.recent(10)
    summary = {(record.message_type, record.target, record.sender, record.text) for record in records}
    if ("private", "10001", "10001", "hello private") not in summary:
        raise RuntimeError(f"private backfill missing: {summary}")
    if ("group", "20001", "10002", "hello group") not in summary:
        raise RuntimeError(f"group backfill missing: {summary}")
    if backfill_messages_from_event_log(store) != 0:
        raise RuntimeError("backfill should be idempotent")
    print("event backfill smoke ok")
    return 0


def _write_event(message_type: str, *, sender: str, target: str, text: str) -> None:
    LOG_HOME.mkdir(parents=True, exist_ok=True)
    path = LOG_HOME / "onebot_events.jsonl"
    entry = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "ok": True,
        "post_type": "message",
        "message_type": message_type,
        "parsed": True,
        "parsed_type": message_type,
        "parsed_sender": sender,
        "parsed_target": target,
        "parsed_text": text,
    }
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(entry, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())

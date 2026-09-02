from __future__ import annotations

import json
from datetime import datetime

from xiami_core.testing import use_temp_xiami_home

use_temp_xiami_home()

from xiami_core.acceptance import acceptance_evidence_lines, format_acceptance, run_v1_acceptance
from xiami_core.contacts import Contact, ContactStore
from xiami_core.messages import MessageRecord, MessageStore
from xiami_core.storage.config import AppConfig, KernelConfig, save_config
from xiami_core.storage.paths import LOG_HOME


def main() -> int:
    save_config(AppConfig(kernel=KernelConfig(kind="Mock")))
    _write_event("private", sender="10001", target="10000", text="private event")
    _write_event("group", sender="10002", target="20001", text="group event")
    ContactStore().save(
        [
            Contact(kind="friend", id="10001", name="好友A"),
            Contact(kind="group", id="20001", name="群A"),
        ]
    )
    store = MessageStore()
    store.append(MessageRecord(direction="incoming", message_type="private", target="10001", sender="10001", text="private ui"))
    store.append(MessageRecord(direction="kernel", message_type="group", target="20001", sender="10002", text="group ui"))
    store.append(
        MessageRecord(
            direction="outgoing",
            message_type="private",
            target="10001",
            text="private send",
            status="ok",
            message_id="p1",
        )
    )
    store.append(
        MessageRecord(
            direction="outgoing",
            message_type="group",
            target="20001",
            text="group send",
            status="ok",
            message_id="g1",
        )
    )

    items = run_v1_acceptance()
    names = {item.name for item in items}
    required = {
        "desktop_core",
        "kernel_config",
        "plugin_loop",
        "onebot_event_log",
        "receive_private_event",
        "receive_group_event",
        "contacts_cache",
        "friend_contacts",
        "group_contacts",
        "ui_message_history",
        "ui_private_received",
        "ui_group_received",
        "send_private_ok",
        "send_group_ok",
    }
    missing = required - names
    if missing:
        raise RuntimeError(f"acceptance items missing: {sorted(missing)}")
    failed = [item for item in items if item.name in required and not item.ok]
    if failed:
        raise RuntimeError(f"acceptance required items failed: {failed}")
    report = format_acceptance(items)
    if (
        "Xiami v1 验收" not in report
        or "缺口摘要" not in report
        or "receive_private_event" not in report
        or "send_group_ok" not in report
        or "证据路径" not in report
        or "消息历史" not in report
        or "使用推荐真实内核" not in report
    ):
        raise RuntimeError(f"bad acceptance report: {report}")
    evidence = "\n".join(acceptance_evidence_lines())
    if "onebot_events.jsonl" not in evidence or "messages.jsonl" not in evidence:
        raise RuntimeError(f"bad acceptance evidence: {evidence}")
    print("acceptance smoke ok")
    return 0


def _write_event(message_type: str, *, sender: str, target: str, text: str) -> None:
    LOG_HOME.mkdir(parents=True, exist_ok=True)
    path = LOG_HOME / "onebot_events.jsonl"
    entry = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "ok": True,
        "post_type": "message",
        "message_type": message_type,
        "user_id": sender,
        "group_id": target if message_type == "group" else None,
        "parsed": True,
        "parsed_type": message_type,
        "parsed_sender": sender,
        "parsed_target": target,
        "parsed_text": text,
        "raw": "{}",
    }
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(entry, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

from xiami_core.testing import use_temp_xiami_home

use_temp_xiami_home()

from xiami_core.messages import MessageRecord, MessageStore, format_message_record


def main() -> int:
    store = MessageStore()
    store.append(MessageRecord(direction="incoming", message_type="private", target="10000", sender="10001", text="你好"))
    store.path.write_text(store.path.read_text(encoding="utf-8") + "{bad json}\n", encoding="utf-8")
    store.append(
        MessageRecord(
            direction="outgoing",
            message_type="group",
            target="20001",
            text="群消息",
            status="ok",
            message_id="42",
        )
    )
    records = store.recent(10)
    if len(records) != 2:
        raise RuntimeError(f"unexpected message record count: {records}")
    rendered = "\n".join(format_message_record(record) for record in records)
    if "你好" not in rendered or "群消息" not in rendered or "42" not in rendered:
        raise RuntimeError(f"message record render failed: {rendered}")
    export_path = store.path.with_suffix(".txt")
    store.export_text(export_path, records)
    if "群消息" not in export_path.read_text(encoding="utf-8"):
        raise RuntimeError("message export failed")
    store.clear()
    if store.recent(10):
        raise RuntimeError("message clear failed")
    print("messages smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

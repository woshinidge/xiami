from __future__ import annotations

import tempfile
from pathlib import Path

from xiami_core.models import SendResult
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.kv import PluginKVStore


def main() -> int:
    def send(target: str, text: str, message_type: str) -> SendResult:
        return SendResult(ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ctx = PluginContext(
            send_fn=send,
            data_root=root / "data",
            state_store=PluginKVStore(root / "state"),
            plugin_id="context_history",
            history_fn=lambda event, limit: [{"text": getattr(event, "text", ""), "limit": limit}],
        )

        sample_event = type("Event", (), {"text": "hello"})()
        if ctx.recent_messages(sample_event, 2) != [{"text": "hello", "limit": 2}]:
            raise RuntimeError("recent_messages did not call history_fn")
        if ctx.recent_messages(sample_event, 0):
            raise RuntimeError("recent_messages limit 0 should return empty list")
        child = ctx.for_plugin("child")
        if child.recent_messages(sample_event, 1) != [{"text": "hello", "limit": 1}]:
            raise RuntimeError("for_plugin did not keep history_fn")

        if ctx.append_state_list("items", "a", limit=2) != ["a"]:
            raise RuntimeError("append_state_list did not initialize list")
        ctx.append_state_list("items", "b", limit=2)
        if ctx.append_state_list("items", "c", limit=2) != ["b", "c"]:
            raise RuntimeError("append_state_list limit did not keep newest tail")
        if ctx.append_state_list("items", "c", unique=True, limit=2) != ["b", "c"]:
            raise RuntimeError("append_state_list unique duplicated value")

        if ctx.prepend_state_list("front", "a", limit=2) != ["a"]:
            raise RuntimeError("prepend_state_list did not initialize list")
        ctx.prepend_state_list("front", "b", limit=2)
        if ctx.prepend_state_list("front", "c", limit=2) != ["c", "b"]:
            raise RuntimeError("prepend_state_list limit did not keep newest head")

        first = ctx.append_state_record("records", {"action": "manual", "user_id": "10001"}, limit=2)
        second = ctx.append_state_record("records", action="approve", user_id="10002", limit=2)
        third = ctx.append_state_record("records", action="reject", user_id="10003", limit=2)
        if "time" not in first or "time" not in second or "time" not in third:
            raise RuntimeError("append_state_record did not fill time")

        records = ctx.get_state_list("records")
        if [item["user_id"] for item in records] != ["10002", "10003"]:
            raise RuntimeError(f"append_state_record did not trim records: {records!r}")
        recent = ctx.recent_state_records("records", limit=2)
        if [item["user_id"] for item in recent] != ["10003", "10002"]:
            raise RuntimeError(f"recent_state_records did not return newest first: {recent!r}")

        ctx.append_state_list("records", "not-a-record")
        if [item["user_id"] for item in ctx.recent_state_records("records", limit=3)] != ["10003", "10002"]:
            raise RuntimeError("recent_state_records did not skip non-dict values")

        ctx.clear_state_list("records")
        if ctx.get_state_list("records") != []:
            raise RuntimeError("clear_state_list did not clear list state")

    print("plugin context history smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

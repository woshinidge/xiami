from __future__ import annotations

import tempfile
from pathlib import Path

from xiami_core.models import SendResult
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.kv import PluginKVStore


def main() -> int:
    sent: list[tuple[str, str, str]] = []

    def send(target: str, text: str, message_type: str) -> SendResult:
        sent.append((target, text, message_type))
        return SendResult(ok=True, detail=f"{message_type}:{target}")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ctx = PluginContext(
            send_fn=send,
            data_root=root / "data",
            state_store=PluginKVStore(root / "state"),
            plugin_id="context_notify",
            config={
                "owner": "10000",
                "owners": ["10001"],
                "admins": "10002,10003",
                "global_admins": {"10003": True, "10004": True, "10005": False},
                "friend_notify_users": ["10006", "10002"],
                "alert_groups": {"20001": True, "20002": False, "20003": True},
            },
        )

        ctx.send_private_many(["10001", "10001", "10002"], "batch")
        ctx.send_group_many("20001, 20002", "group batch")
        ctx.notify_owners("owner notice")
        ctx.notify_admins("admin notice")
        ctx.notify_config_users("friend_notify_users", "friend review", include_admins=True)
        ctx.notify_config_groups("alert_groups", "group notice")

        expected = [
            ("10001", "batch", "private"),
            ("10002", "batch", "private"),
            ("20001", "group batch", "group"),
            ("20002", "group batch", "group"),
            ("10001", "owner notice", "private"),
            ("10000", "owner notice", "private"),
            ("10002", "admin notice", "private"),
            ("10003", "admin notice", "private"),
            ("10004", "admin notice", "private"),
            ("10001", "admin notice", "private"),
            ("10000", "admin notice", "private"),
            ("10006", "friend review", "private"),
            ("10002", "friend review", "private"),
            ("10003", "friend review", "private"),
            ("10004", "friend review", "private"),
            ("20001", "group notice", "group"),
            ("20003", "group notice", "group"),
        ]
        if sent != expected:
            raise RuntimeError(f"notify api sent unexpected messages: {sent!r}")

    print("plugin context notify smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

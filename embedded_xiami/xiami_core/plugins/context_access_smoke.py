from __future__ import annotations

import tempfile
from pathlib import Path

from xiami_core.models import SendResult, XiamiMessage
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.events import PluginEvent
from xiami_core.plugins.kv import PluginKVStore


def main() -> int:
    sent: list[tuple[str, str, str]] = []

    def send(target: str, text: str, message_type: str) -> SendResult:
        sent.append((target, text, message_type))
        return SendResult(ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ctx = PluginContext(
            send_fn=send,
            config={
                "owner": "10000",
                "admins": ["10001"],
                "group_admins": {"20001": ["10002"], 20002: ["10003"]},
            },
            data_root=root / "data",
            state_store=PluginKVStore(root / "state"),
            plugin_id="context_access",
        )

        owner_event = XiamiMessage(message_type="private", sender="10000", text="/admin")
        global_admin = XiamiMessage(message_type="group", sender="10001", target="20009", text="/admin")
        group_admin = XiamiMessage(message_type="group", sender="10002", target="20001", text="/admin")
        int_key_group_admin = XiamiMessage(message_type="group", sender="10003", target="20002", text="/admin")
        denied = XiamiMessage(message_type="group", sender="99999", target="20001", text="/admin")
        raw_event = PluginEvent(type="message", raw={"sender": {"user_id": 10002}, "group_id": 20001})

        if not ctx.is_owner(owner_event):
            raise RuntimeError("owner was not detected")
        if not ctx.is_admin(global_admin):
            raise RuntimeError("global admin was not detected")
        if not ctx.is_admin(group_admin):
            raise RuntimeError("group admin was not detected")
        if not ctx.is_admin(int_key_group_admin):
            raise RuntimeError("integer group_admin key was not detected")
        if not ctx.is_admin(raw_event):
            raise RuntimeError("raw PluginEvent admin was not detected")
        if ctx.is_admin(denied):
            raise RuntimeError("non-admin was treated as admin")
        if ctx.require_admin(denied):
            raise RuntimeError("require_admin allowed non-admin")
        if sent != [("20001", "权限不足", "group")]:
            raise RuntimeError(f"require_admin did not reply denial: {sent!r}")

        ok, remaining = ctx.check_cooldown("sign", 10, event=group_admin, now=1000.0)
        if not ok or remaining != 0:
            raise RuntimeError("first cooldown check should pass")
        ok, remaining = ctx.check_cooldown("sign", 10, event=group_admin, now=1004.0)
        if ok or round(remaining, 2) != 6.0:
            raise RuntimeError(f"cooldown should block with 6 seconds left: {ok}, {remaining}")
        if round(ctx.cooldown_remaining("sign", 10, event=group_admin, now=1005.0), 2) != 5.0:
            raise RuntimeError("cooldown_remaining returned wrong value")
        if not ctx.check_cooldown("sign", 10, event=owner_event, now=1005.0)[0]:
            raise RuntimeError("cooldown scope leaked across users")
        ctx.clear_cooldown("sign", event=group_admin)
        if ctx.cooldown_remaining("sign", 10, event=group_admin, now=1005.0) != 0:
            raise RuntimeError("clear_cooldown did not clear scoped key")
        ctx.touch_cooldown("manual", scope="global", now=2000.0)
        if round(ctx.cooldown_remaining("manual", 15, scope="global", now=2005.0), 2) != 10.0:
            raise RuntimeError("touch_cooldown did not store manual scope")

    print("plugin context access smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

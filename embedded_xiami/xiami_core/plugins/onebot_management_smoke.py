from __future__ import annotations

from typing import Any

from xiami_core.models import SendResult
from xiami_core.plugins.context import PluginContext


def main() -> int:
    calls: list[tuple[str, dict[str, Any]]] = []

    def send(_target: str, _text: str, _message_type: str) -> SendResult:
        return SendResult(ok=True)

    def onebot_call(action: str, params: dict[str, Any]) -> dict[str, Any]:
        calls.append((action, params))
        return {"ok": True, "data": {"action": action}}

    ctx = PluginContext(send_fn=send, onebot_call_fn=onebot_call)
    ctx.call_action("custom_action", value="x")
    ctx.call_onebot("custom_two", {"base": 1}, extra=2)
    ctx.send_like("10001", times=2)
    ctx.set_group_whole_ban("20001", True)
    ctx.set_group_admin("20001", "10001", enable=False)
    ctx.set_group_card("20001", "10001", "名片")
    ctx.set_group_name("20001", "群名")
    ctx.set_group_special_title("20001", "10001", "头衔", duration=60)
    ctx.set_group_leave("20001", is_dismiss=False)

    expected = [
        ("custom_action", {"value": "x"}),
        ("custom_two", {"base": 1, "extra": 2}),
        ("send_like", {"user_id": 10001, "times": 2}),
        ("set_group_whole_ban", {"group_id": 20001, "enable": True}),
        ("set_group_admin", {"group_id": 20001, "user_id": 10001, "enable": False}),
        ("set_group_card", {"group_id": 20001, "user_id": 10001, "card": "名片"}),
        ("set_group_name", {"group_id": 20001, "group_name": "群名"}),
        ("set_group_special_title", {"group_id": 20001, "user_id": 10001, "special_title": "头衔", "duration": 60}),
        ("set_group_leave", {"group_id": 20001, "is_dismiss": False}),
    ]
    if calls != expected:
        raise RuntimeError(f"unexpected OneBot calls: {calls!r}")

    print("plugin onebot management smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

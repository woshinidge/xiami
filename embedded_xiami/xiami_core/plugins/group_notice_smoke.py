from __future__ import annotations

from typing import Any

from xiami_core.models import SendResult
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.legacy import legacy_bot


def main() -> int:
    calls: list[tuple[str, dict[str, Any]]] = []

    def send(_target: str, _text: str, _message_type: str) -> SendResult:
        return SendResult(ok=True)

    def onebot_call(action: str, params: dict[str, Any]) -> dict[str, Any]:
        calls.append((action, params))
        return {"status": "ok", "retcode": 0, "data": []}

    ctx = PluginContext(send_fn=send, onebot_call_fn=onebot_call)
    ctx.set_group_notice("20001", "公告内容")
    ctx.get_group_notice("20001")

    bot = legacy_bot(ctx)
    bot.set_group_notice("20002", "旧公告", image="file:///tmp/a.png")
    bot.get_group_notice("20002")

    expected = [
        ("_send_group_notice", {"group_id": 20001, "content": "公告内容", "image": ""}),
        ("_get_group_notice", {"group_id": 20001}),
        ("_send_group_notice", {"group_id": 20002, "content": "旧公告", "image": "file:///tmp/a.png"}),
        ("_get_group_notice", {"group_id": 20002}),
    ]
    if calls != expected:
        raise RuntimeError(f"wrong group notice calls: {calls}")

    print("group notice smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

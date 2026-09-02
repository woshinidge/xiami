from __future__ import annotations

from typing import Any

from xiami_core.models import SendResult, XiamiMessage
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.events import PluginEvent


def _send(_target: str, _text: str, _message_type: str) -> SendResult:
    return SendResult(ok=True, detail="ok")


def main() -> int:
    calls: list[tuple[str, dict[str, Any]]] = []
    sent: list[tuple[str, str, str]] = []

    def send(target: str, text: str, message_type: str) -> SendResult:
        sent.append((target, text, message_type))
        return SendResult(ok=True, detail="ok")

    def onebot_call(action: str, params: dict[str, Any]) -> dict[str, Any]:
        calls.append((action, params))
        return {"status": "ok", "retcode": 0}

    ctx = PluginContext(send_fn=send, onebot_call_fn=onebot_call)
    ctx.send_private_image("10001", "file:///tmp/a.png")
    ctx.send_group_image("20001", "file:///tmp/a.png")
    ctx.upload_group_file("20001", "C:/tmp/report.txt")
    ctx.upload_group_file("20001", "https://example.com/docs/report-final.pdf", name="manual.pdf")
    group_event = XiamiMessage(message_type="group", sender="10001", target="20001", text="hello")
    private_event = XiamiMessage(message_type="private", sender="10002", target="313420054", text="hello")
    plugin_event = PluginEvent(type="message", message=group_event, raw={"message_id": 654})
    ctx.reply_image(group_event, "file:///tmp/reply.png")
    ctx.reply_at(group_event, "hello [x]")
    ctx.reply_to(group_event, "quoted", message_id=321)
    ctx.reply_at(private_event, "private")
    ctx.reply_to(plugin_event, "auto")
    cq = ctx.cq_text("a[b]&c") + ctx.cq_at("10001") + ctx.cq_reply("765")

    expected = [
        ("send_private_msg", {"user_id": 10001, "message": "[CQ:image,file=file:///tmp/a.png]"}),
        ("send_group_msg", {"group_id": 20001, "message": "[CQ:image,file=file:///tmp/a.png]"}),
        ("upload_group_file", {"group_id": 20001, "file": "C:/tmp/report.txt", "name": "report.txt"}),
        (
            "upload_group_file",
            {"group_id": 20001, "file": "https://example.com/docs/report-final.pdf", "name": "manual.pdf"},
        ),
        ("send_group_msg", {"group_id": 20001, "message": "[CQ:image,file=file:///tmp/reply.png]"}),
    ]
    if calls != expected:
        raise RuntimeError(f"wrong media calls: {calls!r}")
    expected_sent = [
        ("20001", "[CQ:at,qq=10001] hello &#91;x&#93;", "group"),
        ("20001", "[CQ:reply,id=321]quoted", "group"),
        ("10002", "private", "private"),
        ("20001", "[CQ:reply,id=654]auto", "group"),
    ]
    if sent != expected_sent:
        raise RuntimeError(f"wrong reply calls: {sent!r}")
    if cq != "a&#91;b&#93;&amp;c[CQ:at,qq=10001][CQ:reply,id=765]":
        raise RuntimeError(f"wrong cq helpers: {cq}")
    print("onebot media smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

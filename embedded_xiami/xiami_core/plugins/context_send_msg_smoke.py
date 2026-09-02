from __future__ import annotations

from xiami_core.models import MessageSegment, SendResult
from xiami_core.plugins.context import PluginContext


def main() -> int:
    sent: list[tuple[str, str, str]] = []

    def send(target: str, text: str, message_type: str) -> SendResult:
        sent.append((target, text, message_type))
        return SendResult(ok=True, message_id=str(len(sent)))

    ctx = PluginContext(send_fn=send)
    result = ctx.send_msg("private", "10001", "hello")
    if not result.ok or result.message_id != "1":
        raise RuntimeError(f"send_msg result missing SendResult fields: {result!r}")
    ctx.send_msg({"message_type": "group", "group_id": "20001", "message": "hi"})
    ctx.send_msg(user_id="10002", message=[{"type": "at", "data": {"qq": "10002"}}, " ok"])
    ctx.send_message(message_type="group", group_id="20002", message=MessageSegment("image", {"file": "file:///tmp/a.png"}))
    expected = [
        ("10001", "hello", "private"),
        ("20001", "hi", "group"),
        ("10002", "[CQ:at,qq=10002] ok", "private"),
        ("20002", "[CQ:image,file=file:///tmp/a.png]", "group"),
    ]
    if sent != expected:
        raise RuntimeError(f"send_msg sends mismatch: {sent!r}")
    try:
        ctx.send_msg("group", message="missing target")
    except ValueError as exc:
        if "group_id" not in str(exc):
            raise
    else:
        raise RuntimeError("send_msg accepted group message without target")
    print("plugin context send_msg smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

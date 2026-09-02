from __future__ import annotations

from typing import Any

from xiami_core.models import MessageSegment, SendResult, XiamiMessage
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.legacy import legacy_bot, legacy_event


def main() -> int:
    sent: list[tuple[str, str, str]] = []
    calls: list[tuple[str, dict[str, Any]]] = []

    def send(target: str, text: str, message_type: str) -> SendResult:
        sent.append((target, text, message_type))
        return SendResult(ok=True, message_id="42")

    def onebot_call(action: str, params: dict[str, Any]) -> dict[str, Any]:
        calls.append((action, params))
        return {"status": "ok", "retcode": 0, "data": {"action": action}}

    bot = legacy_bot(PluginContext(send_fn=send, onebot_call_fn=onebot_call))
    response = bot.send_msg("group", "20001", "hello")
    if response["data"]["message_id"] != 42:
        raise RuntimeError(f"send_msg response missing message_id: {response!r}")
    bot.send_msg({"message_type": "private", "user_id": "10001", "message": "hi"})
    bot.send_msg(user_id="10002", message=bot.cq_at("10002") + bot.cq_text(" ok"))
    bot.get_group_info("20001")
    bot.get_stranger_info("10001", no_cache=False)
    bot.send_poke("10001", group_id="20001")
    bot.send_group_forward_msg("20001", ["plain", ("B", "10002", "tuple hello")])
    bot.send_private_forward_msg("10001", [bot.forward_node("helper hello", name="Helper", uin="10003")])
    bot.get_image("abc.png")
    bot.get_record("abc.amr")
    bot.set_group_special_title("20001", "10001", "title", duration=60)
    bot.set_group_notice("20001", "notice")
    bot.get_group_honor_info("20001")
    bot.set_essence_msg("12345")
    bot.delete_essence_msg("12345")
    bot.call_api("custom_action", {"value": 1}, extra=2)

    expected_sent = [
        ("20001", "hello", "group"),
        ("10001", "hi", "private"),
        ("10002", "[CQ:at,qq=10002] ok", "private"),
    ]
    if sent != expected_sent:
        raise RuntimeError(f"legacy sends mismatch: {sent!r}")

    expected_calls = [
        ("get_group_info", {"group_id": 20001, "no_cache": True}),
        ("get_stranger_info", {"user_id": 10001, "no_cache": False}),
        ("send_poke", {"user_id": 10001, "group_id": 20001}),
        (
            "send_group_forward_msg",
            {
                "group_id": 20001,
                "messages": [
                    {"type": "node", "data": {"name": "Xiami", "uin": "0", "content": "plain"}},
                    {"type": "node", "data": {"name": "B", "uin": "10002", "content": "tuple hello"}},
                ],
            },
        ),
        (
            "send_private_forward_msg",
            {"user_id": 10001, "messages": [{"type": "node", "data": {"name": "Helper", "uin": "10003", "content": "helper hello"}}]},
        ),
        ("get_image", {"file": "abc.png"}),
        ("get_record", {"file": "abc.amr", "out_format": "mp3"}),
        ("set_group_special_title", {"group_id": 20001, "user_id": 10001, "special_title": "title", "duration": 60}),
        ("_send_group_notice", {"group_id": 20001, "content": "notice", "image": ""}),
        ("get_group_honor_info", {"group_id": 20001, "type": "all"}),
        ("set_essence_msg", {"message_id": 12345}),
        ("delete_essence_msg", {"message_id": 12345}),
        ("custom_action", {"value": 1, "extra": 2}),
    ]
    if calls != expected_calls:
        raise RuntimeError(f"legacy onebot calls mismatch: {calls!r}")

    event = legacy_event(
        XiamiMessage(
            message_type="group",
            sender="10003",
            target="20002",
            text="hello @10004",
            raw_message="hello[CQ:at,qq=10004][CQ:image,file=abc.png]",
            segments=(
                MessageSegment("text", {"text": "hello"}),
                MessageSegment("at", {"qq": "10004"}),
                MessageSegment("image", {"file": "abc.png"}),
            ),
        )
    )
    if not event.is_group() or event.group_id != "20002" or not event.has_at("10004"):
        raise RuntimeError(f"legacy event fields mismatch: {event.to_dict()!r}")
    if event.first_image() != "abc.png" or "hello" not in event.get_plain_text():
        raise RuntimeError(f"legacy event segments mismatch: {event.segments!r}")

    print("legacy api smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

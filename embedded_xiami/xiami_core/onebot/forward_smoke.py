from __future__ import annotations

from xiami_core.models import MessageSegment, XiamiMessage
from xiami_core.onebot.forward import forward_node, normalize_forward_messages


def main() -> int:
    message = XiamiMessage(message_type="private", sender="10002", target="313420054", text="from message")
    segment = MessageSegment(type="text", data={"text": "seg"})
    nodes = normalize_forward_messages(
        [
            "plain",
            {"name": "Dict", "uin": "10003", "content": "dict text"},
            ("Tuple", "10004", "tuple text"),
            message,
            forward_node([segment], name="Segment", uin="10005"),
            {"type": "node", "data": {"name": "Raw", "uin": "10006", "content": "raw"}},
        ]
    )
    expected = [
        {"type": "node", "data": {"name": "Xiami", "uin": "0", "content": "plain"}},
        {"type": "node", "data": {"name": "Dict", "uin": "10003", "content": "dict text"}},
        {"type": "node", "data": {"name": "Tuple", "uin": "10004", "content": "tuple text"}},
        {"type": "node", "data": {"name": "10002", "uin": "10002", "content": "from message"}},
        {"type": "node", "data": {"name": "Segment", "uin": "10005", "content": [{"type": "text", "data": {"text": "seg"}}]}},
        {"type": "node", "data": {"name": "Raw", "uin": "10006", "content": "raw"}},
    ]
    if nodes != expected:
        raise RuntimeError(f"wrong normalized forward nodes: {nodes}")

    print("forward smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

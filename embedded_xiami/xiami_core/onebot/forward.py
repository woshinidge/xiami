from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from xiami_core.models import MessageSegment, XiamiMessage


def forward_node(content: Any, name: str = "Xiami", uin: str | int = "0") -> dict[str, Any]:
    return {"type": "node", "data": {"name": str(name), "uin": str(uin), "content": _node_content(content)}}


def normalize_forward_messages(
    messages: Any,
    *,
    default_name: str = "Xiami",
    default_uin: str | int = "0",
) -> list[dict[str, Any]]:
    if isinstance(messages, (str, bytes, Mapping, XiamiMessage)):
        items = [messages]
    else:
        try:
            items = list(messages)
        except TypeError:
            items = [messages]
    return [_normalize_forward_item(item, default_name=default_name, default_uin=default_uin) for item in items]


def _normalize_forward_item(item: Any, *, default_name: str, default_uin: str | int) -> dict[str, Any]:
    if isinstance(item, XiamiMessage):
        return forward_node(item.raw_message or item.text, name=item.sender or default_name, uin=item.sender or default_uin)
    if isinstance(item, Mapping):
        node_type = item.get("type")
        data = item.get("data")
        if node_type == "node" and isinstance(data, Mapping):
            merged = dict(data)
            merged.setdefault("name", default_name)
            merged.setdefault("uin", str(default_uin))
            merged.setdefault("content", "")
            return {"type": "node", "data": merged}
        name = item.get("name") or item.get("nickname") or default_name
        uin = item.get("uin") or item.get("user_id") or item.get("sender") or default_uin
        content = item.get("content", item.get("message", item.get("text", "")))
        return forward_node(content, name=name, uin=uin)
    if isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)):
        if len(item) >= 3:
            return forward_node(item[2], name=str(item[0]), uin=item[1])
        if len(item) == 2:
            return forward_node(item[1], name=str(item[0]), uin=default_uin)
    return forward_node(str(item), name=default_name, uin=default_uin)


def _node_content(content: Any) -> Any:
    if isinstance(content, XiamiMessage):
        return content.raw_message or content.text
    if isinstance(content, MessageSegment):
        return {"type": content.type, "data": dict(content.data)}
    if isinstance(content, Sequence) and not isinstance(content, (str, bytes, bytearray)):
        return [_node_content(item) for item in content]
    if isinstance(content, Mapping):
        return dict(content)
    if isinstance(content, bytes):
        return content.decode("utf-8", errors="replace")
    return str(content)

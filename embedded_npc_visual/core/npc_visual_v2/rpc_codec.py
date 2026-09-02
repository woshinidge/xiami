from __future__ import annotations

from typing import Any, Dict

from .ast import (
    NpcComponentNode,
    NpcDocument,
    NpcLabelBlock,
    NpcSayBlock,
    SourceRef,
)


MAX_RPC_LABELS = 10000
MAX_RPC_SAY_BLOCKS = 50000
MAX_RPC_NODES = 250000
MAX_RPC_NODE_DEPTH = 32
MAX_RPC_ACT_LINES = 500000


class NpcRpcDocumentError(ValueError):
    pass


class _DecodeState:
    def __init__(self, source_text: str, file_key: str) -> None:
        self.source_text = source_text
        self.file_key = file_key
        self.say_blocks = 0
        self.nodes = 0
        self.act_lines = 0

    def source_ref(self, value: Any) -> SourceRef:
        if not isinstance(value, dict) or set(value) != {"start", "end", "line", "column"}:
            raise NpcRpcDocumentError("NPC RPC source reference is invalid")
        start = value.get("start")
        end = value.get("end")
        line = value.get("line")
        column = value.get("column")
        if (
            type(start) is not int or type(end) is not int or
            type(line) is not int or type(column) is not int or
            start < 0 or end < start or end > len(self.source_text) or
            line < 1 or column < 1
        ):
            raise NpcRpcDocumentError("NPC RPC source boundary is invalid")
        expected_line = self.source_text.count("\n", 0, start) + 1
        line_start = self.source_text.rfind("\n", 0, start) + 1
        expected_column = start - line_start + 1
        if line != expected_line or column != expected_column:
            raise NpcRpcDocumentError("NPC RPC source position is inconsistent")
        return SourceRef(
            file_key=self.file_key,
            start=start,
            end=end,
            line=line,
            column=column,
            raw=self.source_text[start:end],
        )

    def node(self, value: Any, depth: int = 0) -> NpcComponentNode:
        if depth > MAX_RPC_NODE_DEPTH:
            raise NpcRpcDocumentError("NPC RPC node nesting is too deep")
        if not isinstance(value, dict) or set(value) != {
            "id", "kind", "text", "raw", "source", "props", "children"
        }:
            raise NpcRpcDocumentError("NPC RPC node is invalid")
        node_id = value.get("id")
        kind = value.get("kind")
        text = value.get("text")
        raw = value.get("raw")
        props = value.get("props")
        children = value.get("children")
        if (
            not isinstance(node_id, str) or not node_id or len(node_id) > 1024 or
            not isinstance(kind, str) or not kind or len(kind) > 64 or
            not isinstance(text, str) or not isinstance(raw, str) or
            not isinstance(props, dict) or not isinstance(children, list)
        ):
            raise NpcRpcDocumentError("NPC RPC node fields are invalid")
        self.nodes += 1
        if self.nodes > MAX_RPC_NODES:
            raise NpcRpcDocumentError("NPC RPC returned too many nodes")
        normalized_props = _json_value(props, 0)
        decoded_children = [self.node(child, depth + 1) for child in children]
        return NpcComponentNode(
            id=node_id,
            kind=kind,
            text=text,
            raw=raw,
            source=self.source_ref(value.get("source")),
            props=normalized_props,
            children=decoded_children,
        )

    def say_block(self, value: Any) -> NpcSayBlock:
        if not isinstance(value, dict) or set(value) != {"id", "label", "source", "nodes"}:
            raise NpcRpcDocumentError("NPC RPC say block is invalid")
        block_id = value.get("id")
        label = value.get("label")
        nodes = value.get("nodes")
        if (
            not isinstance(block_id, str) or not block_id or len(block_id) > 1024 or
            not isinstance(label, str) or not label or len(label) > 1024 or
            not isinstance(nodes, list)
        ):
            raise NpcRpcDocumentError("NPC RPC say block fields are invalid")
        self.say_blocks += 1
        if self.say_blocks > MAX_RPC_SAY_BLOCKS:
            raise NpcRpcDocumentError("NPC RPC returned too many say blocks")
        return NpcSayBlock(
            id=block_id,
            label=label,
            source=self.source_ref(value.get("source")),
            nodes=[self.node(node) for node in nodes],
        )

    def label_block(self, value: Any) -> NpcLabelBlock:
        if not isinstance(value, dict) or set(value) != {
            "label", "source", "say_blocks", "act_lines", "openmerchant"
        }:
            raise NpcRpcDocumentError("NPC RPC label block is invalid")
        label = value.get("label")
        say_blocks = value.get("say_blocks")
        act_lines = value.get("act_lines")
        openmerchant = value.get("openmerchant")
        if (
            not isinstance(label, str) or not label or len(label) > 1024 or
            not isinstance(say_blocks, list) or not isinstance(act_lines, list) or
            any(not isinstance(line, str) for line in act_lines)
        ):
            raise NpcRpcDocumentError("NPC RPC label fields are invalid")
        self.act_lines += len(act_lines)
        if self.act_lines > MAX_RPC_ACT_LINES:
            raise NpcRpcDocumentError("NPC RPC returned too many action lines")
        return NpcLabelBlock(
            label=label,
            source=self.source_ref(value.get("source")),
            say_blocks=[self.say_block(block) for block in say_blocks],
            act_lines=list(act_lines),
            openmerchant=None if openmerchant is None else self.node(openmerchant),
        )


def _json_value(value: Any, depth: int) -> Any:
    if depth > 16:
        raise NpcRpcDocumentError("NPC RPC property nesting is too deep")
    if value is None or isinstance(value, (str, bool)) or type(value) in (int, float):
        return value
    if isinstance(value, list):
        if len(value) > 10000:
            raise NpcRpcDocumentError("NPC RPC property list is too large")
        return [_json_value(item, depth + 1) for item in value]
    if isinstance(value, dict):
        if len(value) > 1000 or any(not isinstance(key, str) for key in value):
            raise NpcRpcDocumentError("NPC RPC property mapping is invalid")
        return {key: _json_value(item, depth + 1) for key, item in value.items()}
    raise NpcRpcDocumentError("NPC RPC property contains an unsupported value")


def npc_document_from_rpc(payload: Any, source_text: str, file_key: str) -> NpcDocument:
    if not isinstance(source_text, str) or not isinstance(file_key, str) or not file_key:
        raise NpcRpcDocumentError("NPC RPC decode context is invalid")
    if not isinstance(payload, dict) or set(payload) != {"labels"}:
        raise NpcRpcDocumentError("NPC RPC document is invalid")
    labels = payload.get("labels")
    if not isinstance(labels, list) or len(labels) > MAX_RPC_LABELS:
        raise NpcRpcDocumentError("NPC RPC label count is invalid")
    state = _DecodeState(source_text, file_key)
    return NpcDocument(
        file_key=file_key,
        source_text=source_text,
        labels=[state.label_block(label) for label in labels],
    )


__all__ = ["NpcRpcDocumentError", "npc_document_from_rpc"]

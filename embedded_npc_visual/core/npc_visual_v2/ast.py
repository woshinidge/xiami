from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SourceRef:
    file_key: str
    start: int
    end: int
    line: int
    column: int
    raw: str


@dataclass
class NpcComponentNode:
    id: str
    kind: str
    text: str
    raw: str
    source: SourceRef
    props: dict[str, Any] = field(default_factory=dict)
    children: list["NpcComponentNode"] = field(default_factory=list)


@dataclass
class NpcSayBlock:
    id: str
    label: str
    source: SourceRef
    nodes: list[NpcComponentNode] = field(default_factory=list)


@dataclass
class NpcLabelBlock:
    label: str
    source: SourceRef
    say_blocks: list[NpcSayBlock] = field(default_factory=list)
    act_lines: list[str] = field(default_factory=list)
    openmerchant: NpcComponentNode | None = None


@dataclass
class NpcDocument:
    file_key: str
    source_text: str
    labels: list[NpcLabelBlock] = field(default_factory=list)

    def label_names(self) -> list[str]:
        return [block.label for block in self.labels]

    def label_by_name(self, label: str) -> NpcLabelBlock | None:
        needle = label.casefold()
        for block in self.labels:
            if block.label.casefold() == needle:
                return block
        if self.labels:
            return self.labels[0]
        return None


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int


@dataclass
class LayoutComponent:
    node: NpcComponentNode
    rect: Rect
    visual_rect: Rect
    row: int
    z_index: int = 0


@dataclass
class LayoutBreak:
    node: NpcComponentNode
    row_before: int
    row_after: int


@dataclass
class LayoutDocument:
    label: str
    width: int
    height: int
    row_height: int
    rows: list[int]
    content_x: int = 24
    content_y: int = 14
    components: list[LayoutComponent] = field(default_factory=list)
    breaks: list[LayoutBreak] = field(default_factory=list)
    background: LayoutComponent | None = None

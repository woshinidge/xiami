from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import re

from ..ast import (
    LayoutBreak,
    LayoutComponent,
    LayoutDocument,
    NpcComponentNode,
    NpcLabelBlock,
    Rect,
)
from ..components import CONTAINER_SIZE_INDEXES, LAYOUT_COORDINATE_INDEXES

DEFAULT_WINDOW_W = 760
DEFAULT_WINDOW_H = 560
DEFAULT_DIALOG_W = 448
DEFAULT_DIALOG_H = 246
CONTENT_X = 24
CONTENT_Y = 14
IMG_RESOURCE_DRAW_X_ADJUST = -2
IMG_RESOURCE_DRAW_Y_ADJUST = 0
IMG_RESOURCE_ADVANCE_X_ADJUST = -2
IMG_RESOURCE_MIN_FLOW_WIDTH = 37
_LAYOUT_GAP_CHARS = " \t　\ue779"
DEFAULT_CHAR_WIDTH = 6
DEFAULT_WIDE_CHAR_WIDTH = 11

_COORD_INDEXES = LAYOUT_COORDINATE_INDEXES
_SIZE_INDEXES = CONTAINER_SIZE_INDEXES


@dataclass
class _Container:
    id: str
    x: int
    y: int
    width: int
    height: int
    kind: str = "layout"
    gap: int = 0
    direction: int = 0
    cursor_x: int = 0
    cursor_y: int = 0
    scroll_offset: int = 0
    max_extent: int = 0
    visible: bool = True

    def newline(self, row_height: int) -> None:
        self.cursor_x = 0
        self.cursor_y += row_height + self.gap


class LayoutEngineV2:
    def __init__(
        self,
        char_width: int = DEFAULT_CHAR_WIDTH,
        row_height: int = 16,
        wide_char_width: int = DEFAULT_WIDE_CHAR_WIDTH,
    ) -> None:
        self.char_width = char_width
        self.wide_char_width = wide_char_width
        self.row_height = row_height
        self.content_x = CONTENT_X
        self.content_y = CONTENT_Y
        self.image_size_resolver = None
        self.list_view_scroll_offsets = {}
        self.list_view_regions = []

    def layout(
        self,
        block: NpcLabelBlock | None,
        image_size_resolver: Callable[
            [NpcComponentNode], tuple[int, int] | None
        ]
        | None = None,
        fallback_background_node: NpcComponentNode | None = None,
    ) -> LayoutDocument:
        previous_resolver = self.image_size_resolver
        previous_fallback = getattr(self, "fallback_background_node", None)
        self.image_size_resolver = image_size_resolver
        self.fallback_background_node = fallback_background_node
        try:
            return self._layout(block)
        finally:
            self.image_size_resolver = previous_resolver
            self.fallback_background_node = previous_fallback

    def _layout(self, block: NpcLabelBlock | None) -> LayoutDocument:
        if block is None:
            self.list_view_regions = []
            return LayoutDocument(
                label="",
                width=DEFAULT_WINDOW_W,
                height=DEFAULT_WINDOW_H,
                row_height=self.row_height,
                rows=[],
            )

        background = self._background_component(block)
        width = background.rect.width if background is not None else DEFAULT_WINDOW_W
        height = background.rect.height if background is not None else DEFAULT_WINDOW_H
        content_x, content_y = self._content_origin(background)
        document = LayoutDocument(
            label=block.label,
            width=width,
            height=height,
            row_height=self.row_height,
            rows=[],
            content_x=content_x,
            content_y=content_y,
            background=background,
        )
        self.list_view_regions = []
        x = content_x
        row = 0
        y = content_y
        containers: dict[str, _Container] = {}
        for say in block.say_blocks:
            for node in say.nodes:
                if node.kind == "break":
                    count = int(node.props.get("count", 1) or 1)
                    before = row
                    row += max(1, count)
                    document.breaks.append(
                        LayoutBreak(node=node, row_before=before, row_after=row)
                    )
                    x = content_x
                    y = content_y + row * self.row_height
                    continue

                if node.kind == "container_newline":
                    parent = self._parent_container(node, containers)
                    if parent is not None:
                        parent.newline(self.row_height)
                    continue

                if node.kind in {"layout", "listview"}:
                    self._place_container_node(document, node, containers, x, y)
                    continue

                if self._place_container_child(document, node, containers):
                    continue

                width_px, height_px = self.measure(node)
                visual_x, visual_y = self._visual_position(node, x, y)
                rect = Rect(x=x, y=y, width=width_px, height=height_px)
                visual = Rect(
                    x=visual_x, y=visual_y, width=width_px, height=height_px
                )
                document.components.append(
                    LayoutComponent(
                        node=node,
                        rect=rect,
                        visual_rect=visual,
                        row=row,
                        z_index=self._z_index(node),
                    )
                )
                x += self._flow_advance_width(node, width_px)
                document.rows.append(row)

                trailing_break_count = int(
                    node.props.get("str_trailing_break_count", 0) or 0
                )
                if trailing_break_count > 0:
                    before = row
                    row += trailing_break_count
                    document.breaks.append(
                        LayoutBreak(node=node, row_before=before, row_after=row)
                    )
                    x = content_x
                    y = content_y + row * self.row_height

        if document.components:
            max_bottom = max(
                component.visual_rect.y + component.visual_rect.height
                for component in document.components
            )
            document.height = max(document.height, max_bottom + 24)
        document.rows = sorted(set(document.rows))
        self._finalize_list_views(containers)
        return document

    def measure(self, node: NpcComponentNode) -> tuple[int, int]:
        if node.kind in {"layout", "listview"}:
            width_index, height_index = _SIZE_INDEXES[node.kind]
            return (
                max(1, self._int_arg(node, width_index, 1)),
                max(1, self._int_arg(node, height_index, 1)),
            )

        if node.kind in {
            "img",
            "imgex",
            "playimg",
            "playimgex",
            "monster",
            "itemshow",
            "itembox",
            "progressbar",
        }:
            size = self._resolved_image_size(node)
            if size is not None:
                return size
            if node.kind == "progressbar":
                return (160, 16)
            if node.kind == "itemshow":
                return (36, 36)
            if node.kind == "img":
                return (37, 34)
            if node.kind == "itembox":
                return (
                    max(1, self._int_arg(node, 5, 36)),
                    max(1, self._int_arg(node, 6, 36)),
                )
            return (42, 34)

        if node.kind == "text":
            raw = str(node.raw or "")
            text = str(node.text or "")
            empty_angle_width = self._empty_angle_width(raw)
            if empty_angle_width is not None:
                return (empty_angle_width, self.row_height)
            if self._is_gap_only_text(raw, text):
                return (self._text_width(raw), self.row_height)

        if node.kind == "mtext":
            lines = self._mtext_lines(str(node.text or ""))
            width = max((self._text_width(line) for line in lines), default=1)
            return (max(8, width), max(self.row_height, len(lines) * self.row_height))

        text = node.text or node.raw
        width = max(8, self._text_width(text))
        return (width, self.row_height)

    def _mtext_lines(self, text: str) -> list[str]:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        normalized = re.sub(r"\|[ \t]*\n", "\n", normalized)
        lines = re.split(r"[|\n]", normalized)
        while lines and not lines[-1].strip():
            lines.pop()
        return lines or [""]

    def _empty_angle_width(self, raw: str) -> int | None:
        if raw.startswith("<") and raw.endswith(">"):
            inner = raw[1:-1]
            if not inner.strip():
                return self._text_width(inner)
        return None

    def _is_gap_only_text(self, raw: str, text: str) -> bool:
        if text.strip():
            return False
        if not raw.strip():
            return True
        return raw.strip(_LAYOUT_GAP_CHARS + "\r\n") == ""

    def _background_component(self, block: NpcLabelBlock) -> LayoutComponent | None:
        node = block.openmerchant or getattr(self, "fallback_background_node", None)
        if node is None:
            return None
        width, height = self._resolved_image_size(node) or (640, 360)
        rect = Rect(0, 0, width, height)
        return LayoutComponent(
            node=node, rect=rect, visual_rect=rect, row=-1, z_index=-100
        )

    def _content_origin(self, background: LayoutComponent | None) -> tuple[int, int]:
        if background is not None:
            return (self.content_x, self.content_y)
        left = (DEFAULT_WINDOW_W - DEFAULT_DIALOG_W) // 2
        top = (DEFAULT_WINDOW_H - DEFAULT_DIALOG_H) // 2
        return (left + self.content_x, top + self.content_y)

    def _resolved_image_size(
        self, node: NpcComponentNode
    ) -> tuple[int, int] | None:
        if self.image_size_resolver is None:
            return None
        try:
            size = self.image_size_resolver(node)
        except Exception:
            return None
        if size is None:
            return None
        width, height = size
        if width <= 0 or height <= 0:
            return None
        return (int(width), int(height))

    def _text_width(self, text: str) -> int:
        width = 0
        for ch in text:
            width += self._char_advance(ch)
        return width

    def _char_advance(self, char: str) -> int:
        if ord(char) > 127:
            return self.wide_char_width
        return self.char_width

    def _flow_advance_width(self, node: NpcComponentNode, width: int) -> int:
        if node.props.get("absolute"):
            return 0
        if node.kind == "img" and not self._normalize_container_id(
            str(node.props.get("parent_id") or "")
        ):
            return max(
                0,
                max(IMG_RESOURCE_MIN_FLOW_WIDTH, int(width))
                + IMG_RESOURCE_ADVANCE_X_ADJUST,
            )
        return width

    def _int_arg(self, node: NpcComponentNode, index: int, default: int) -> int:
        args = node.props.get("args")
        if not isinstance(args, list) or not args:
            return default
        try:
            value = str(args[index]).strip()
        except Exception:
            return default
        return self._parse_int_prefix(value, default)

    def _parse_int_prefix(self, value: str, default: int = 0) -> int:
        import re

        match = re.match(r"\s*(-?\d+)", value)
        if not match:
            return default
        try:
            return int(match.group(1))
        except Exception:
            return default

    def _visual_position(
        self,
        node: NpcComponentNode,
        x: int,
        y: int,
        container: _Container | None = None,
    ) -> tuple[int, int]:
        indexes = _COORD_INDEXES.get(node.kind)
        if indexes is None:
            return (x, y)

        background_relative = (
            bool(node.props.get("str_expanded"))
            and not bool(node.props.get("str_multi_expanded"))
            and node.kind == "positioned_text"
        )

        if container is not None and node.props.get("absolute"):
            base_x, base_y = container.x, container.y
        else:
            base_x = 0 if node.props.get("absolute") or background_relative else x
            base_y = (
                0
                if node.props.get("absolute")
                or background_relative
                or node.kind == "progressbar"
                else y
            )

        visual_x = base_x + self._int_arg(node, indexes[0], 0)
        visual_y = base_y + self._int_arg(node, indexes[1], 0)
        if (
            node.kind == "img"
            and not node.props.get("absolute")
            and not self._normalize_container_id(str(node.props.get("parent_id") or ""))
        ):
            visual_x += IMG_RESOURCE_DRAW_X_ADJUST
            visual_y += IMG_RESOURCE_DRAW_Y_ADJUST
        return (visual_x, visual_y)

    def _normalize_container_id(self, value: object) -> str:
        text = str(value or "").strip().lstrip("#")
        return text.casefold()

    def _parent_container(
        self, node: NpcComponentNode, containers: dict[str, _Container]
    ) -> _Container | None:
        parent_id = self._normalize_container_id(node.props.get("parent_id"))
        if parent_id:
            return containers.get(parent_id)
        return None

    def _child_container_id(self, node: NpcComponentNode) -> str:
        return self._normalize_container_id(node.props.get("child_id"))

    def _container_anchor(
        self,
        node: NpcComponentNode,
        containers: dict[str, _Container],
        x: int,
        y: int,
    ) -> tuple[int, int, _Container | None]:
        parent = self._parent_container(node, containers)
        if parent is not None:
            if parent.kind == "listview":
                return (parent.x + parent.cursor_x, parent.y + parent.cursor_y, parent)
            if node.props.get("absolute"):
                return (parent.x, parent.y, parent)
            return (parent.x + parent.cursor_x, parent.y + parent.cursor_y, parent)
        if node.props.get("absolute"):
            return (x, y, None)
        return (x, y, None)

    def _place_container_node(
        self,
        document: LayoutDocument,
        node: NpcComponentNode,
        containers: dict[str, _Container],
        x: int,
        y: int,
    ) -> None:
        anchor_x, anchor_y, parent = self._container_anchor(node, containers, x, y)
        if parent is None and node.props.get("absolute"):
            anchor_x, anchor_y = document.content_x, document.content_y
        draw_x = anchor_x + self._int_arg(node, 0, 0)
        draw_y = anchor_y + self._int_arg(node, 1, 0)
        width, height = self.measure(node)
        rect = Rect(draw_x, draw_y, width, height)
        visible = parent.visible if parent is not None else True
        if parent is not None and parent.kind == "listview":
            visible = visible and self._region_visible_in_container(rect, parent)
        component = LayoutComponent(
            node=node,
            rect=rect,
            visual_rect=rect,
            row=self._row_for_y(document, draw_y),
            z_index=1,
        )
        if visible:
            document.components.append(component)
            document.rows.append(component.row)

        child_id = self._child_container_id(node) or self._normalize_container_id(
            node.props.get("parent_id")
        )
        if child_id:
            direction = self._int_arg(node, 6, 0) if node.kind == "listview" else 0
            scroll_offset = (
                max(0, self.list_view_scroll_offsets.get(child_id, 0))
                if node.kind == "listview"
                else 0
            )
            containers[child_id] = _Container(
                id=child_id,
                x=draw_x,
                y=draw_y,
                width=width,
                height=height,
                kind="listview" if node.kind == "listview" else "layout",
                gap=max(0, self._int_arg(node, 4, 0))
                if node.kind == "listview"
                else 0,
                direction=direction,
                cursor_x=-scroll_offset
                if node.kind == "listview" and direction == 1
                else 0,
                cursor_y=-scroll_offset
                if node.kind == "listview" and direction != 1
                else 0,
                scroll_offset=scroll_offset,
                visible=visible,
            )

        if parent is not None and (
            not node.props.get("absolute") or parent.kind == "listview"
        ):
            self._advance_container(parent, rect, node)
        return None

    def _place_container_child(
        self,
        document: LayoutDocument,
        node: NpcComponentNode,
        containers: dict[str, _Container],
    ) -> bool:
        parent = self._parent_container(node, containers)
        if parent is None:
            return False
        if not parent.visible:
            return True

        start_x = parent.x + parent.cursor_x
        start_y = parent.y + parent.cursor_y
        if parent.kind != "listview" and node.props.get("absolute"):
            start_x, start_y = parent.x, parent.y

        width_px, height_px = self.measure(node)
        visual_x, visual_y = self._visual_position(
            node, start_x, start_y, container=parent
        )
        rect = Rect(start_x, start_y, width_px, height_px)
        visual = Rect(visual_x, visual_y, width_px, height_px)

        if parent.kind == "listview" and not self._region_visible_in_container(
            visual, parent
        ):
            self._advance_container(parent, visual, node)
            return True

        component = LayoutComponent(
            node=node,
            rect=rect,
            visual_rect=visual,
            row=self._row_for_y(document, visual_y),
            z_index=self._z_index(node),
        )
        document.components.append(component)
        document.rows.append(component.row)

        child_id = self._child_container_id(node)
        if child_id:
            containers[child_id] = _Container(
                id=child_id,
                x=visual.x,
                y=visual.y,
                width=visual.width,
                height=visual.height,
            )

        if not node.props.get("absolute"):
            self._advance_container(parent, visual, node)
        return True

    def _region_visible_in_container(self, region: Rect, container: _Container) -> bool:
        if container.direction == 1:
            return (
                region.x >= container.x
                and region.x + region.width <= container.x + container.width
            )
        return (
            region.y >= container.y
            and region.y + region.height <= container.y + container.height
        )

    def _advance_container(
        self, container: _Container, region: Rect, node: NpcComponentNode
    ) -> None:
        if container.kind == "listview":
            if container.direction == 1:
                extent = (
                    region.x
                    + region.width
                    - container.x
                    + container.scroll_offset
                )
            else:
                extent = (
                    region.y
                    + region.height
                    - container.y
                    + container.scroll_offset
                )
            container.max_extent = max(container.max_extent, extent)
        if container.direction == 1:
            container.cursor_x = max(
                container.cursor_x,
                region.x + region.width - container.x + container.gap,
            )
            return None
        if self._child_container_id(node) or node.kind in {
            "layout",
            "listview",
            "img",
            "imgex",
            "playimg",
            "playimgex",
            "monster",
            "itemshow",
            "itembox",
            "progressbar",
        }:
            container.cursor_x = 0
            container.cursor_y = max(
                container.cursor_y,
                region.y + region.height - container.y + container.gap,
            )
            return None
        if node.kind == "mtext":
            container.cursor_x = 0
            container.cursor_y = max(
                container.cursor_y,
                region.y + region.height - container.y + container.gap,
            )
            return None
        container.cursor_x = max(
            container.cursor_x, region.x + region.width - container.x
        )
        container.cursor_y = max(container.cursor_y, region.y - container.y)
        return None

    def _row_for_y(self, document: LayoutDocument, y: int) -> int:
        return max(0, (y - document.content_y) // max(1, self.row_height))

    def _finalize_list_views(self, containers: dict[str, _Container]) -> None:
        regions = []
        for container in containers.values():
            if container.kind != "listview":
                continue
            viewport_extent = (
                container.width if container.direction == 1 else container.height
            )
            max_offset = max(0, container.max_extent - viewport_extent)
            offset = min(container.scroll_offset, max_offset)
            self.list_view_scroll_offsets[container.id] = offset
            regions.append(
                (
                    Rect(container.x, container.y, container.width, container.height),
                    container.id,
                    max_offset,
                    container.direction,
                )
            )
        self.list_view_regions = regions
        return None

    def _z_index(self, node: NpcComponentNode) -> int:
        if node.kind in {"layout", "listview"}:
            return 1
        if node.kind in {
            "img",
            "imgex",
            "playimg",
            "playimgex",
            "monster",
            "itemshow",
            "itembox",
            "progressbar",
        }:
            return 20
        return 30

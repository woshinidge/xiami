"""NPC 可视化编辑器的流式排版、插入与拖拽重排。"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..ast import LayoutComponent, LayoutDocument
from ..components import DIRECT_INSERT_COORDINATE_INDEXES, EDITABLE_COORDINATE_INDEXES
_FLOW_GAP_CHARS = " \t\u3000\ue779"
_IMG_DRAW_X_ADJUST = -2
_IMG_DRAW_Y_ADJUST = 0
_COORD_ARG_INDEXES = DIRECT_INSERT_COORDINATE_INDEXES

@dataclass(frozen=True)
class FlowMoveResult:
    changed: bool
    source: str
    message: str
    selected_node_id: str = ""
    selected_raw: str = ""
    selected_kind: str = ""
    selected_text: str = ""
    selected_row: int = -1
    selected_x: int = -1
    dirty_rows: tuple[int, ...] = ()
    debug_lines: tuple[str, ...] = ()


@dataclass(frozen=True)
class _PlacedComponent:
    component: LayoutComponent
    x: int
    placeholder: bool = False


@dataclass(frozen=True)
class _LabelBlockInfo:
    label: str
    header_start: int
    header_end: int
    block_start: int
    block_end: int


@dataclass(frozen=True)
class _SayRange:
    header_start: int
    content_start: int
    content_end: int


class FlowReflowEngine:
    __doc__ = "Patch flow rows after dragging a stream component."

    def __init__(self, char_width: int=6) -> None:
        self.char_width = char_width

    def move(self, source, layout, component, target_x, target_y) -> FlowMoveResult:
        if layout is None:
            return self._unchanged(source, component, "缺少布局结果，无法做流式重排")
        if source[component.node.source.start:component.node.source.end] != component.node.source.raw:
            return self._unchanged(source, component, "源码已变化，组件位置失效，请重新渲染后再移动")
        target_row = self._target_row(layout, target_y)
        row_components = self._row_components(layout)
        origin_row = component.row
        target_all = row_components.get(target_row, [])
        placed_x = self._place_x(layout, component.rect.width, target_x)
        if placed_x is None:
            return self._unchanged(source, component, "目标位置超出背景边框或没有足够空位")
        dirty_rows = tuple(sorted({origin_row, target_row}))
        token = self._component_token(component, selected=True)
        replacements = [
         (
          component.node.source.start,
          component.node.source.end,
          self._spacer(component.rect.width))]
        target_real = [item for item in self._real_components(target_all) if item.node.id != component.node.id]
        if target_row == origin_row:
            replacement_range = self._row_range(target_all)
            if replacement_range is None:
                return self._unchanged(source, component, "没有找到目标行源码范围")
            (start, end) = replacement_range
            placed = [_PlacedComponent(item, placed_x if item.node.id == component.node.id else item.rect.x) for item in self._real_components(target_all)]
            if not any((item.component.node.id == component.node.id for item in placed)):
                placed.append(_PlacedComponent(component, placed_x))
            row_end_x = max([item.rect.x + item.rect.width for item in target_all] + [placed_x + component.rect.width])
            replacements = [
             (
              start,
              end,
              self._build_row(layout, placed, selected_id=(component.node.id), min_end_x=row_end_x))]
        elif not target_all:
            insert_range = self._empty_row_insert(layout, target_row, [
             _PlacedComponent(component, placed_x)], component.node.id)
            if insert_range is None:
                return self._unchanged(source, component, "目标空行没有可拆分的换行标记")
            replacements.append(insert_range)
        elif target_real:
            gap = self._target_gap(layout, target_all, target_real, component, placed_x)
            if gap is None:
                return self._unchanged(source, component, "没有找到目标行可插入间隔")
            (start, end, cursor_x, next_x) = gap
            placed_x = max(placed_x, cursor_x)
            replacements.append((
             start,
             end,
             self._insert_token_text(component=component,
               token=token,
               placed_x=placed_x,
               cursor_x=cursor_x,
               next_x=next_x)))
        else:
            replacement_range = self._row_range(target_all)
            if replacement_range is None:
                return self._unchanged(source, component, "没有找到目标行源码范围")
            (start, end) = replacement_range
            replacements.append((
             start,
             end,
             self._build_row(layout,
               [
              _PlacedComponent(component, placed_x)],
               selected_id=(component.node.id))))
        if not replacements:
            return self._unchanged(source, component, "没有找到可重排的源码行")
        new_source = self._apply_replacements(source, replacements)
        if new_source is None:
            return self._unchanged(source, component, "目标位置与原位置重叠，请重新渲染后再移动")
        new_source = self._merge_empty_tag_runs(new_source)
        if new_source == source:
            return self._unchanged(source, component, "位置没有产生源码变化")
        return FlowMoveResult(True,
          new_source,
          f"已重排流式组件：row {origin_row} -> {target_row}, x {component.rect.x} -> {placed_x}",
          (component.node.id),
          selected_raw=self._component_token(component, selected=True),
          selected_kind=(component.node.kind),
          selected_text=(component.node.text),
          selected_row=target_row,
          selected_x=placed_x,
          dirty_rows=dirty_rows)

    def _unchanged(self, source, component, message, debug_lines=()) -> FlowMoveResult:
        return FlowMoveResult(False,
          source,
          message,
          (component.node.id),
          selected_raw=(component.node.raw),
          selected_kind=(component.node.kind),
          selected_text=(component.node.text),
          selected_row=(component.row),
          selected_x=(component.rect.x),
          dirty_rows=(
         component.row,),
          debug_lines=debug_lines)

    def shift_components(
        self,
        source: str,
        layout: LayoutDocument | None,
        components: list[LayoutComponent],
        dx: int,
        dy: int,
    ) -> FlowMoveResult:
        if layout is None or not components:
            component = components[0] if components else None
            if component is None:
                return FlowMoveResult(False, source, "没有可移动的流式组件")
            return self._unchanged(source, component, "缺少布局结果，无法批量移动流式组件")
        first = components[0]
        char_width = max(1, int(self.char_width))
        row_height = max(1, int(layout.row_height))
        if dx % char_width or dy % row_height:
            return self._unchanged(source, first, "流式组件必须按字符宽度和行高移动")
        if not dx and not dy:
            return self._unchanged(source, first, "组件位置没有变化")

        selected_ids = {component.node.id for component in components}
        selected_ranges = set()
        for component in components:
            if not self._is_batch_flow_component(component):
                return self._unchanged(source, component, "所选内容包含非流式组件")
            if component.node.props.get("str_expanded") or component.node.props.get("mov_value_source"):
                return self._unchanged(source, component, "变量展开组件不能参加批量流式移动")
            ref = component.node.source
            if source[ref.start : ref.end] != ref.raw:
                return self._unchanged(source, component, "源码已变化，请重新渲染后再操作")
            source_range = (ref.start, ref.end)
            if source_range in selected_ranges:
                return self._unchanged(source, component, "所选组件引用同一段源码")
            selected_ranges.add(source_range)

        row_components = self._row_components(layout)
        all_flow = [
            component
            for component in layout.components
            if self._is_batch_flow_component(component)
        ]
        row_delta = dy // row_height
        if row_delta and selected_ids != {component.node.id for component in all_flow}:
            return self._unchanged(source, first, "上下微移需要选中当前画布的全部流式组件")
        if row_delta and min(component.row for component in components) + row_delta < 0:
            return self._unchanged(source, first, "组件已经到达画布顶部")

        replacements: list[tuple[int, int, str]] = []
        if dx:
            for row in sorted({component.row for component in components}):
                original = row_components.get(row, [])
                real = self._real_components(original)
                if not real:
                    continue
                if any(not self._is_batch_flow_component(component) for component in real):
                    return self._unchanged(source, first, "目标行混有绝对坐标组件，不能批量重排")
                placed = [
                    _PlacedComponent(
                        component,
                        component.rect.x + dx if component.node.id in selected_ids else component.rect.x,
                    )
                    for component in real
                ]
                ordered = sorted(
                    placed,
                    key=lambda item: (item.x, item.component.node.source.start),
                )
                previous_end = int(layout.content_x)
                for item in ordered:
                    if item.x < int(layout.content_x) or item.x < previous_end:
                        return self._unchanged(source, first, "横向微移会与同一行组件重叠")
                    previous_end = item.x + item.component.rect.width
                if previous_end > int(layout.width):
                    return self._unchanged(source, first, "横向微移超出画布范围")
                replacement_range = self._row_range(original)
                if replacement_range is None:
                    return self._unchanged(source, first, "没有找到组件所在行源码范围")
                start, end = replacement_range
                replacements.append(
                    (start, end, self._build_row(layout, placed, selected_id=""))
                )

        if row_delta > 0:
            first_row = min(component.row for component in components)
            original = row_components.get(first_row, [])
            if not original:
                return self._unchanged(source, first, "没有找到首行源码范围")
            anchor = min(component.node.source.start for component in original)
            newline = "\r\n" if "\r\n" in source else "\n"
            break_text = "".join("\\" + newline for _index in range(row_delta))
            row_replacement = next(
                (
                    (index, end, text)
                    for index, (start, end, text) in enumerate(replacements)
                    if start == anchor and end > start
                ),
                None,
            )
            if row_replacement is None:
                replacements.append((anchor, anchor, break_text))
            else:
                index, end, text = row_replacement
                replacements[index] = (anchor, end, break_text + text)
        elif row_delta < 0:
            remaining = -row_delta
            first_row = min(component.row for component in components)
            candidates = sorted(
                (
                    marker
                    for marker in layout.breaks
                    if marker.row_after <= first_row
                ),
                key=lambda marker: (marker.row_after, marker.node.source.start),
                reverse=True,
            )
            for marker in candidates:
                if remaining <= 0:
                    break
                ref = marker.node.source
                if source[ref.start : ref.end] != ref.raw:
                    return self._unchanged(source, first, "换行源码已变化，请重新渲染后再操作")
                available = max(0, marker.row_after - marker.row_before)
                take = min(remaining, available)
                replacement, removed = self._remove_break_tokens(ref.raw, take)
                if removed:
                    replacements.append((ref.start, ref.end, replacement))
                    remaining -= removed
            if remaining:
                return self._unchanged(source, first, "组件已经到达画布顶部")

        if not replacements:
            return self._unchanged(source, first, "组件位置没有变化")
        new_source = self._apply_replacements(source, replacements)
        if new_source is None:
            return self._unchanged(source, first, "批量流式移动的源码范围发生重叠")
        if new_source == source:
            return self._unchanged(source, first, "组件位置没有变化")
        return FlowMoveResult(
            True,
            new_source,
            f"已批量移动 {len(components)} 个流式组件：dx={dx}, dy={dy}",
            first.node.id,
            selected_raw=first.node.raw,
            selected_kind=first.node.kind,
            selected_text=first.node.text,
            selected_row=first.row + row_delta,
            selected_x=first.rect.x + dx,
            dirty_rows=(),
        )

    def _is_batch_flow_component(self, component: LayoutComponent) -> bool:
        if component.node.kind in EDITABLE_COORDINATE_INDEXES:
            return False
        if component.node.kind in {"layout", "listview"}:
            return False
        return not self._is_spacer_component(component)

    def _remove_break_tokens(self, raw: str, count: int) -> tuple[str, int]:
        removed = 0
        parts = []
        for char in raw:
            if char == "\\" and removed < count:
                removed += 1
                continue
            parts.append(char)
        return "".join(parts), removed

    def insert(
        self,
        source,
        layout,
        component,
        target_x,
        target_y,
        exact_coordinates=False,
    ) -> FlowMoveResult:
        if layout is None:
            return self._unchanged(source, component, "缺少布局结果，无法插入组件")
        (target_row, target_col, placed_x) = self._target_grid(layout, target_x, target_y)
        placed_y = target_row * max(1, int(layout.row_height))
        row_components = self._row_components(layout)
        target_all = row_components.get(target_row, [])
        target_existing = self._real_components(target_all)
        placed = [_PlacedComponent(component, placed_x)]
        selected_raw = self._component_token(component, selected=True)
        replacements = []
        fallback_result = None
        insert_detail = ""
        debug_lines = self._insert_debug_header(source=source,
          layout=layout,
          component=component,
          target_x=target_x,
          target_y=target_y,
          target_row=target_row,
          target_col=target_col,
          placed_x=placed_x,
          target_all=target_all)
        absolute_x = int(target_x) if exact_coordinates else placed_x
        absolute_y = int(target_y) if exact_coordinates else placed_y
        direct_token = self._absolute_component_token(
            component,
            absolute_x,
            absolute_y,
            adjust_img_origin=not exact_coordinates,
        )
        if direct_token:
            new_source = self._append_to_say_fallback(source, layout, direct_token + "\n")
            debug_lines.append("插入前行片段：无可替换范围，坐标组件直接使用画布绝对坐标插入")
            debug_lines.append("插入方式：画布绝对坐标；网格起点=画布左上角0,0；不参与流式推进；不替换原源码")
            debug_lines.append(f"插入后片段：{self._source_snippet(new_source, direct_token)}")
            if new_source == source:
                return self._unchanged(source, component, "目标位置没有产生源码变化，已取消插入", tuple(debug_lines))
            return FlowMoveResult(True,
              new_source,
              f"已按画布坐标插入组件：row {target_row}, col {target_col}, x {absolute_x}, y {absolute_y}",
              (component.node.id),
              selected_raw=direct_token,
              selected_kind=(component.node.kind),
              selected_text=(component.node.text),
              selected_row=target_row,
              selected_x=absolute_x,
              dirty_rows=(),
              debug_lines=(tuple(debug_lines)))
        if target_existing:
            gap = self._target_insert_gap(layout, target_all, target_existing, component, placed_x)
            if gap is None:
                fallback_result = self._fallback_insert_source(source, layout, target_row, placed, component.node.id, placed_x, placed_y)
            else:
                (start, end, cursor_x, next_x) = gap
                placed_x = max(placed_x, cursor_x)
                placed = [_PlacedComponent(component, placed_x)]
                prefix_spaces = self._space_count(placed_x - cursor_x)
                suffix_spaces = self._space_count(next_x - (placed_x + component.rect.width))
                insert_detail = f"插入方式：当前行间隙；不换行=True；补空格={prefix_spaces}；保留右侧空格={suffix_spaces}；源码范围={start}-{end}"
                replacements = [
                 (
                  start,
                  end,
                  self._insert_token_text(component=component,
                    token=self._component_token(component, selected=True),
                    placed_x=placed_x,
                    cursor_x=cursor_x,
                    next_x=next_x))]
        elif target_all:
            replacement_range = self._row_range(target_all)
            if replacement_range is None:
                fallback_result = self._fallback_insert_source(source, layout, target_row, placed, component.node.id, placed_x, placed_y)
            else:
                (start, end) = replacement_range
                insert_detail = f"插入方式：替换空占位行；不换行=True；补空格={self._space_count(placed_x)}；源码范围={start}-{end}"
                replacements = [
                 (
                  start,
                  end,
                  self._build_row(layout, placed, selected_id=(component.node.id)))]
        else:
            insert_range = self._empty_row_insert(layout, target_row, placed, component.node.id)
            if insert_range is None:
                fallback_result = self._fallback_insert_source(source, layout, target_row, placed, component.node.id, placed_x, placed_y)
            else:
                (start, end, replacement) = insert_range
                insert_detail = f"插入方式：拆分换行空档；不换行=False；补换行={replacement.count(chr(92))}；补空格={self._space_count(placed_x)}；源码范围={start}-{end}"
                replacements = [
                 insert_range]
        if fallback_result is not None:
            debug_lines.append("插入前行片段：无可替换范围，直接使用兜底插入")
            (new_source, selected_raw, insert_detail) = fallback_result
        else:
            if not replacements:
                return self._unchanged(source, component, "目标位置没有足够空位，已取消插入以避免影响现有组件", tuple(debug_lines))
            debug_lines.append(f"插入前行片段：{self._replacement_before_snippet(source, replacements)}")
            (valid_range, range_reason) = self._replacements_within_edit_range(source, layout, replacements)
            if not valid_range:
                debug_lines.append(range_reason)
                fallback_result = self._fallback_insert_source(source, layout, target_row, placed, component.node.id, placed_x, placed_y)
                if fallback_result is None:
                    return self._unchanged(source, component, "目标源码范围越过当前标签，已取消插入以避免破坏原组件", tuple(debug_lines))
                (new_source, selected_raw, insert_detail) = fallback_result
            else:
                new_source = self._apply_replacements(source, replacements)
                if new_source is None:
                    fallback_result = self._fallback_insert_source(source, layout, target_row, placed, component.node.id, placed_x, placed_y)
                    if fallback_result is None:
                        return self._unchanged(source, component, "目标位置与现有源码范围重叠，请重新渲染后再插入", tuple(debug_lines))
                    (new_source, selected_raw, insert_detail) = fallback_result
        new_source = self._merge_empty_tag_runs(new_source)
        debug_lines.append(insert_detail or "插入方式：未命名")
        debug_lines.append(f"插入后片段：{self._source_snippet(new_source, selected_raw)}")
        if new_source == source:
            return self._unchanged(source, component, "目标位置没有产生源码变化，已取消插入", tuple(debug_lines))
        return FlowMoveResult(True,
          new_source,
          f"已插入组件：row {target_row}, col {target_col}, x {placed_x}",
          (component.node.id),
          selected_raw=selected_raw,
          selected_kind=(component.node.kind),
          selected_text=(component.node.text),
          selected_row=target_row,
          selected_x=placed_x,
          dirty_rows=(
         target_row,),
          debug_lines=(tuple(debug_lines)))

    def _insert_legacy(self, source, layout, component, target_x, target_y) -> FlowMoveResult:
        if layout is None:
            return self._unchanged(source, component, "缺少布局结果，无法插入组件")
        target_row = self._target_row(layout, target_y)
        row_components = self._row_components(layout)
        target_all = row_components.get(target_row, [])
        target_existing = self._real_components(target_all)
        placed_x = self._place_x(layout, component.rect.width, target_x)
        if placed_x is None:
            return self._unchanged(source, component, "目标位置超出背景边框或没有足够空位")
        placed = [
         _PlacedComponent(component, placed_x)]
        fallback_result = None
        selected_raw = self._component_token(component, selected=True)
        if target_existing:
            gap = self._target_insert_gap(layout, target_all, target_existing, component, placed_x)
            if gap is None:
                fallback_result = self._fallback_insert_source_legacy(source, layout, target_row, placed, component.node.id, target_x, target_y)
                replacements = []
            else:
                (start, end, cursor_x, next_x) = gap
                placed_x = max(placed_x, cursor_x)
                placed = [_PlacedComponent(component, placed_x)]
                replacements = [
                 (
                  start,
                  end,
                  self._insert_token_text(component=component,
                    token=self._component_token(component, selected=True),
                    placed_x=placed_x,
                    cursor_x=cursor_x,
                    next_x=next_x))]
        elif target_all:
            replacement_range = self._row_range(target_all)
            if replacement_range is None:
                fallback_result = self._fallback_insert_source_legacy(source, layout, target_row, placed, component.node.id, target_x, target_y)
                replacements = []
            else:
                (start, end) = replacement_range
                replacement = self._build_row(layout,
                  placed,
                  selected_id=(component.node.id))
                replacements = [
                 (
                  start, end, replacement)]
        else:
            insert_range = self._empty_row_insert(layout, target_row, placed, component.node.id)
            if insert_range is None:
                fallback_result = self._fallback_insert_source_legacy(source, layout, target_row, placed, component.node.id, target_x, target_y)
                replacements = []
            else:
                replacements = [
                 insert_range]
        if fallback_result is not None:
            (new_source, selected_raw) = fallback_result
        else:
            if not replacements:
                return self._unchanged(source, component, "目标位置没有足够空位，已取消插入以避免影响现有组件")
            new_source = self._apply_replacements(source, replacements)
            if new_source is None:
                fallback_result = self._fallback_insert_source_legacy(source, layout, target_row, placed, component.node.id, target_x, target_y)
                if fallback_result is None:
                    return self._unchanged(source, component, "目标位置与现有源码范围重叠，请重新渲染后再插入")
                (new_source, selected_raw) = fallback_result
        new_source = self._merge_empty_tag_runs(new_source)
        if new_source == source:
            return self._unchanged(source, component, "目标位置没有产生源码变化，已取消插入")
        return FlowMoveResult(True,
          new_source,
          f"已插入组件：row {target_row}, x {placed_x}",
          (component.node.id),
          selected_raw=selected_raw,
          selected_kind=(component.node.kind),
          selected_text=(component.node.text),
          selected_row=target_row,
          selected_x=placed_x,
          dirty_rows=(
         target_row,))

    def _fallback_insert_source(self, source, layout, target_row, placed, selected_id, target_x, target_y) -> tuple[str, str, str] | None:
        absolute_token = self._absolute_component_token(placed[0].component, target_x, target_y) if placed else None
        if absolute_token:
            detail = "插入方式：绝对坐标兜底；不参与流式推进；补换行=0；补空格=0；写入当前 #SAY 末尾"
            return (
             self._append_to_say_fallback(source, layout, absolute_token + "\n"), absolute_token, detail)
        row_text = self._build_row(layout, placed, selected_id=selected_id)
        if not row_text:
            return
        append_row = self._append_row_text(layout, target_row, row_text)
        if append_row is None:
            return
        row_insert = append_row + self._break_marker(1)
        detail = f"插入方式：追加到当前 #SAY 末尾；补换行={row_insert.count(chr(92))}；补空格={self._space_count(placed[0].x) if placed else 0}"
        return (
         self._append_to_say_fallback(source, layout, row_insert),
         self._component_token((placed[0].component), selected=True),
         detail)

    def _fallback_insert_source_legacy(self, source, layout, target_row, placed, selected_id, target_x, target_y) -> tuple[str, str] | None:
        absolute_token = self._absolute_component_token(placed[0].component, target_x, target_y) if placed else None
        if absolute_token:
            return (self._append_to_say_fallback(source, layout, absolute_token + "\n"), absolute_token)
        row_text = self._build_row(layout, placed, selected_id=selected_id)
        if not row_text:
            return
        append_row = self._append_row_text(layout, target_row, row_text)
        if append_row is None:
            return
        row_insert = append_row + self._break_marker(1)
        return (
         self._append_to_say_fallback(source, layout, row_insert), self._component_token((placed[0].component), selected=True))

    def _append_row_text(self, layout, target_row, row_text) -> str | None:
        has_real_components = bool(self._real_components(layout.components))
        end_row = self._layout_end_row(layout)
        if has_real_components and target_row <= end_row:
            return
        if target_row < end_row:
            return
        return self._break_marker(target_row - end_row) + row_text

    def _layout_end_row(self, layout: LayoutDocument) -> int:
        end_row = 0
        if layout.rows:
            end_row = max(end_row, max(layout.rows))
        if layout.components:
            end_row = max(end_row, max((component.row for component in layout.components)))
        if layout.breaks:
            end_row = max(end_row, max((marker.row_after for marker in layout.breaks)))
        return end_row

    def _absolute_component_token(
        self,
        component,
        target_x,
        target_y,
        adjust_img_origin=True,
    ) -> str | None:
        if component.node.kind == "text":
            return ""
        indexes = _COORD_ARG_INDEXES.get(component.node.kind)
        if indexes is None:
            return ""
        raw = component.node.raw
        if not (raw.startswith("<") and raw.endswith(">")):
            return ""
        body = raw[1:-1].strip()
        if body.startswith("&"):
            body = body[1:].strip()
        if ":" not in body:
            return ""
        (command, payload) = body.split(":", 1)
        label = ""
        if "/@" in payload:
            (payload, label_tail) = payload.split("/@", 1)
            label = "/@" + label_tail
        tip = ""
        if "|" in payload:
            (payload, tip_tail) = payload.split("|", 1)
            tip = "|" + tip_tail
        args = payload.split(":") if payload else []
        if len(args) <= max(indexes):
            return ""
        x_value = int(target_x)
        y_value = int(target_y)
        if component.node.kind == "img" and adjust_img_origin:
            x_value -= _IMG_DRAW_X_ADJUST
            y_value -= _IMG_DRAW_Y_ADJUST
        args[indexes[0]] = str(x_value)
        args[indexes[1]] = str(y_value)
        return f'<&{command}:{":".join(args)}{tip}{label}>'

    def _append_to_say_fallback(self, source, layout, insert_text) -> str:
        if not source.strip():
            return "[@MAIN]\n#IF\n#ACT\n#SAY\n" + insert_text
        label_bounds = self._label_block_bounds(source, layout.label)
        if label_bounds is None:
            prefix = "" if source.endswith(('\n', '\r')) else "\n"
            return source + prefix + "[@MAIN]\n#IF\n#ACT\n#SAY\n" + insert_text
        (block_start, block_end) = label_bounds
        say_offset = self._say_append_offset(source, block_start, block_end)
        if say_offset is not None:
            prefix = "" if (say_offset <= 0) or (source[:say_offset].endswith(('\n',
                                                                               '\r'))) else "\n"
            return source[:say_offset] + prefix + insert_text + source[say_offset:]
        insert_at = block_end
        prefix = "" if (insert_at <= 0) or (source[:insert_at].endswith(('\n', '\r'))) else "\n"
        return source[:insert_at] + prefix + "#SAY\n" + insert_text + source[insert_at:]

    def _replacements_within_edit_range(self, source, layout, replacements) -> tuple[bool, str]:
        edit_range = self._current_edit_range(source, layout)
        if edit_range is None:
            return (False, "插入范围校验：未找到当前标签块，改用绝对坐标兜底")
        (range_start, range_end, range_name) = edit_range
        for (start, end, _text) in replacements:
            if start < range_start or end > range_end:
                return (
                    False,
                    f"插入范围校验：源码范围={start}-{end} 越过当前{range_name}={range_start}-{range_end}，改用绝对坐标兜底",
                )
            fragment = source[start:end]
            if not self._is_safe_insert_replacement_fragment(fragment):
                return (
                    False,
                    f"插入范围校验：源码范围={start}-{end} 片段不是纯空白/空标签/换行，改用绝对坐标兜底",
                )
        return (True, f"插入范围校验：源码范围在当前{range_name}={range_start}-{range_end} 内")

    def _is_safe_insert_replacement_fragment(self, fragment: str) -> bool:
        if not fragment:
            return True
        index = 0
        while index < len(fragment):
            char = fragment[index]
            if char in _FLOW_GAP_CHARS or char in "\r\n\\":
                index += 1
                continue
            if char == "<":
                end = fragment.find(">", index + 1)
                if end < 0:
                    return False
                inner = fragment[index + 1:end]
                if inner.strip(_FLOW_GAP_CHARS):
                    return False
                index = end + 1
                continue
            return False
        return True

    def _replacement_before_snippet(self, source: str, replacements: list[tuple[int, int, str]]) -> str:
        if not replacements:
            return "无可替换范围"
        parts = []
        for (start, end, _text) in replacements[:3]:
            line_start = source.rfind("\n", 0, start) + 1
            line_end = source.find("\n", end)
            if line_end < 0:
                line_end = len(source)
            line = source[line_start:line_end]
            fragment = source[start:end]
            parts.append(f"range={start}-{end} line={self._short(line, limit=220)} fragment={self._short(fragment, limit=160)}")

        if len(replacements) > 3:
            parts.append(f"...共{len(replacements)}段")
        return " || ".join(parts)

    def _current_edit_range(self, source: str, layout: LayoutDocument) -> tuple[int, int, str] | None:
        label_info = self._label_block_info(source, layout.label)
        if label_info is None:
            return
        say_range = self._say_range(source, label_info.block_start, label_info.block_end)
        if say_range is not None:
            return (say_range.content_start, say_range.content_end, "#SAY")
        return (label_info.block_start, label_info.block_end, "标签块")

    def _label_block_bounds(self, source: str, label: str) -> tuple[int, int] | None:
        info = self._label_block_info(source, label)
        if info is None:
            return
        return (info.block_start, info.block_end)

    def _label_block_info(self, source: str, label: str) -> _LabelBlockInfo | None:
        matches = list(re.finditer(r"(?im)^[ \t]*\[@(?P<label>[^\]\r\n]+)\][ \t]*(?:\r?\n|$)", source))
        if not matches:
            return
        needle = str(label or "").strip().casefold()
        if needle.startswith("@"):
            needle = needle[1:]
        selected_index = 0
        for (index, match) in enumerate(matches):
            current = match.group("label").strip().casefold()
            if needle and current == needle:
                selected_index = index
                break
        match = matches[selected_index]
        start = match.end()
        end = matches[selected_index + 1].start() if selected_index + 1 < len(matches) else len(source)
        return _LabelBlockInfo(
            label=("@" + match.group("label").strip()),
            header_start=match.start(),
            header_end=match.end(),
            block_start=start,
            block_end=end,
        )

    def _say_append_offset(self, source, start, end) -> int | None:
        say_range = self._say_range(source, start, end)
        if say_range is not None:
            return say_range.content_end

    def _say_range(self, source, start, end) -> _SayRange | None:
        say_pattern = re.compile("(?im)^[ \\t]*#(?:SAY|ELSESAY)\\b[^\\r\\n]*(?:\\r?\\n|$)")
        say_match = None
        for match in say_pattern.finditer(source, start, end):
            say_match = match

        if say_match is None:
            return
        stop_pattern = re.compile("(?im)^[ \\t]*(?:#(?!SAY\\b|ELSESAY\\b)[A-Z0-9_()]+\\b|\\[@[^\\]\\r\\n]+\\])")
        stop = stop_pattern.search(source, say_match.end(), end)
        return _SayRange(header_start=(say_match.start()),
          content_start=(say_match.end()),
          content_end=(stop.start() if stop is not None else end))

    def _target_insert_gap(self, layout, row_all, row_real, inserted, placed_x) -> tuple[int, int, int, int] | None:
        row_range = self._row_range(row_all)
        if row_range is None:
            return
        previous = None
        next_component = None
        for item in sorted(row_real, key=(lambda value: (value.rect.x, value.node.source.start))):
            midpoint = item.rect.x + max(1, item.rect.width) // 2
            if placed_x < midpoint:
                next_component = item
                break
            previous = item
        if previous is None:
            gap_start = row_range[0]
            gap_end = next_component.node.source.start if next_component is not None else row_range[1]
            cursor_x = layout.content_x
            next_x = next_component.rect.x if next_component is not None else placed_x + inserted.rect.width
        elif next_component is None:
            gap_start = previous.node.source.end
            gap_end = gap_start
            cursor_x = previous.rect.x + previous.rect.width
            next_x = placed_x + inserted.rect.width
        else:
            gap_start = previous.node.source.end
            gap_end = next_component.node.source.start
            cursor_x = previous.rect.x + previous.rect.width
            next_x = next_component.rect.x
        safe_x = max(placed_x, cursor_x)
        if next_component is not None and safe_x + inserted.rect.width > next_x:
            return
        return (gap_start, gap_end, cursor_x, next_x)

    def delete(self, source, layout, component) -> FlowMoveResult:
        if layout is None:
            return self._unchanged(source, component, "缺少布局结果，无法删除组件")
        if source[component.node.source.start:component.node.source.end] != component.node.source.raw:
            return self._unchanged(source, component, "源码已变化，组件位置失效，请重新渲染后再删除")
        row_components = self._row_components(layout)
        original = row_components.get(component.row, [])
        if not original:
            return self._unchanged(source, component, "没有找到组件所在行")
        replacement_range = self._row_range(original)
        if replacement_range is None:
            return self._unchanged(source, component, "没有找到组件所在行源码范围")
        (start, end) = replacement_range
        placed = [_PlacedComponent(item, item.rect.x) for item in self._real_components(original) if item.node.id != component.node.id]
        replacement = self._build_row(layout, placed, selected_id="")
        new_source = source[:start] + replacement + source[end:]
        return FlowMoveResult(True,
          new_source,
          f"已删除组件并补位：row {component.row}, x {component.rect.x}",
          "",
          selected_row=(component.row),
          selected_x=(component.rect.x),
          dirty_rows=(
         component.row,))

    def _target_grid(self, layout, target_x, target_y) -> tuple[int, int, int]:
        row_height = max(1, int(layout.row_height))
        char_width = max(1, int(self.char_width))
        row = max(0, int(target_y) // row_height)
        col = max(0, int(target_x) // char_width)
        return (
         row, col, col * char_width)

    def _insert_debug_header(self, source, layout, component, target_x, target_y, target_row, target_col, placed_x, target_all) -> list[str]:
        row_height = max(1, int(layout.row_height))
        char_width = max(1, int(self.char_width))
        label_info = self._label_block_info(source, layout.label)
        say_range = self._say_range(source, label_info.block_start, label_info.block_end) if label_info else None
        if label_info is None:
            label_text = f'标签范围：未找到 {layout.label or "@MAIN"}'
        else:
            label_text = f"标签范围：{label_info.label} 开始行={self._line_no(source, label_info.header_start)} 结束行={self._line_no(source, label_info.block_end)} offset={label_info.header_start}-{label_info.block_end}"
        if say_range is None:
            say_text = "SAY范围：未找到，必要时会在当前标签块内创建 #SAY"
        else:
            say_text = f"SAY范围：开始行={self._line_no(source, say_range.header_start)} 结束行={self._line_no(source, say_range.content_end)} offset={say_range.content_start}-{say_range.content_end}"
        return [
         f"插入debug：网格={char_width}x{row_height}；网格起点=画布左上角0,0；脚本内容起点={int(layout.content_x)},{int(layout.content_y)}；鼠标canvas={int(target_x)},{int(target_y)}；落格row={target_row}, col={target_col}, x={placed_x}, y={target_row * row_height}",
         label_text,
         say_text,
         f"插入组件：{component.node.kind} {self._short(component.node.raw)}",
         f"目标行组件：{self._row_debug(target_all)}"]

    def _space_count(self, width_px: int) -> int:
        return max(0, round(int(width_px) / max(1, int(self.char_width))))

    def _row_debug(self, components: list[LayoutComponent]) -> str:
        real = self._real_components(components)
        if not real:
            return "无"
        parts = []
        for item in real:
            parts.append(f"{item.node.kind}@{item.rect.x},{item.rect.y} {item.rect.width}x{item.rect.height} {self._short(item.node.raw)}")

        return " | ".join(parts)

    def _source_snippet(self, source: str, needle: str) -> str:
        if not needle:
            return ""
        index = source.rfind(needle)
        if index < 0:
            index = source.find(needle)
        if index < 0:
            return "未找到新组件源码"
        line_start = source.rfind("\n", 0, index) + 1
        line_end = source.find("\n", index)
        if line_end < 0:
            line_end = len(source)
        return self._short((source[line_start:line_end]), limit=220)

    def _short(self, text: str, limit: int=120) -> str:
        value = str(text or "").replace("\r", "\\r").replace("\n", "\\n")
        if len(value) <= limit:
            return value
        return value[:max(0, limit - 3)] + "..."

    def _line_no(self, source: str, offset: int) -> int:
        index = max(0, min(int(offset), len(source)))
        return source.count("\n", 0, index) + 1

    def _target_row(self, layout: LayoutDocument, target_y: int) -> int:
        row = round((target_y - layout.content_y) / max(1, layout.row_height))
        return max(0, row)

    def _row_components(self, layout: LayoutDocument) -> dict[int, list[LayoutComponent]]:
        rows = {}
        for component in layout.components:
            rows.setdefault(component.row, []).append(component)

        for components in rows.values():
            components.sort(key=(lambda item: (item.rect.x, item.node.source.start)))

        return rows

    def _real_components(self, components: list[LayoutComponent]) -> list[LayoutComponent]:
        return [component for component in components if not self._is_spacer_component(component)]

    def _is_spacer_component(self, component: LayoutComponent) -> bool:
        if component.node.kind != "text":
            return False
        if component.node.text.strip():
            return False
        raw = component.node.raw
        if raw.startswith("<") and raw.endswith(">"):
            return raw[1:-1].strip() == ""
        return raw.strip() == ""

    def _place_x(self, layout, width, target_x) -> int:
        return max(layout.content_x, target_x)

    def _row_range(self, components: list[LayoutComponent]) -> tuple[int, int] | None:
        if not components:
            return
        start = min((item.node.source.start for item in components))
        end = max((item.node.source.end for item in components))
        return (
         start, end)

    def _target_gap(self, layout, row_all, row_real, moving, placed_x) -> tuple[int, int, int, int] | None:
        row_range = self._row_range(row_all)
        if row_range is None:
            return
        previous = None
        next_component = None
        for item in sorted(row_real, key=(lambda value: (value.rect.x, value.node.source.start))):
            midpoint = item.rect.x + max(1, item.rect.width) // 2
            if placed_x < midpoint:
                next_component = item
                break
            previous = item
        if previous is None:
            gap_start = row_range[0]
            gap_end = next_component.node.source.start if next_component is not None else row_range[1]
            cursor_x = layout.content_x
            next_x = next_component.rect.x if next_component is not None else placed_x + moving.rect.width
        elif next_component is None:
            gap_start = previous.node.source.end
            gap_end = gap_start
            cursor_x = previous.rect.x + previous.rect.width
            next_x = placed_x + moving.rect.width
        else:
            gap_start = previous.node.source.end
            gap_end = next_component.node.source.start
            cursor_x = previous.rect.x + previous.rect.width
            next_x = next_component.rect.x
        if self._ranges_overlap(gap_start, gap_end, moving.node.source.start, moving.node.source.end):
            if placed_x <= moving.rect.x:
                gap_end = min(gap_end, moving.node.source.start)
                next_x = moving.rect.x
            else:
                gap_start = max(gap_start, moving.node.source.end)
                cursor_x = moving.rect.x + moving.rect.width
            if gap_start > gap_end:
                gap_start = gap_end
        return (gap_start, gap_end, cursor_x, next_x)

    def _insert_token_text(self, component, token, placed_x, cursor_x, next_x) -> str:
        prefix = self._spacer(placed_x - cursor_x)
        suffix = self._spacer(next_x - (placed_x + component.rect.width))
        return prefix + token + suffix

    def _apply_replacements(self, source: str, replacements: list[tuple[int, int, str]]) -> str | None:
        ordered = sorted(replacements, key=(lambda item: (item[0], item[1])))
        last_end = 0
        for (start, end, _text) in ordered:
            if start < 0 or end < start or end > len(source):
                return None
            if start < last_end:
                return None
            else:
                last_end = end

        new_source = source
        for (start, end, text) in sorted(replacements, key=(lambda item: item[0]), reverse=True):
            new_source = new_source[:start] + text + new_source[end:]

        return new_source

    def _ranges_overlap(self, start, end, other_start, other_end) -> bool:
        return start < other_end and other_start < end

    def _merge_empty_tag_runs(self, source: str) -> str:
        parts = []
        index = 0
        changed = False
        while index < len(source):
            first_end = self._empty_tag_end(source, index)
            if first_end is None:
                parts.append(source[index])
                index += 1
                continue
            run_end = first_end
            scan = first_end
            tokens = [("tag", source[index + 1:first_end - 1])]
            tag_count = 1
            while True:
                gap_start = scan
                while scan < len(source) and source[scan] in _FLOW_GAP_CHARS:
                    scan += 1
                next_end = self._empty_tag_end(source, scan)
                if next_end is None:
                    break
                if scan > gap_start:
                    tokens.append(("gap", source[gap_start:scan]))
                tokens.append(("tag", source[scan + 1:next_end - 1]))
                run_end = next_end
                scan = next_end
                tag_count += 1
            if tag_count > 1:
                parts.append(self._merged_empty_tag_run(tokens))
                changed = True
                index = run_end
            else:
                parts.append(source[index:first_end])
                index = first_end
        if changed:
            return "".join(parts)
        return source

    def _merged_empty_tag_run(self, tokens: list[tuple[str, str]]) -> str:
        tag_values = [value for kind, value in tokens if kind == "tag"]
        width_text = "".join((value for _kind, value in tokens))
        if all((value == "" for value in tag_values)):
            return "<" + width_text + ">"
        if tag_values and tag_values[0] == "":
            return "<>" + ("<" + width_text + ">" if width_text else "")
        return "<" + width_text + ">"

    def _empty_tag_end(self, source: str, index: int) -> int | None:
        if index >= len(source) or source[index] != "<":
            return
        end = source.find(">", index + 1)
        if end < 0:
            return
        inner = source[index + 1:end]
        if "\r" in inner or "\n" in inner:
            return
        if inner.strip(_FLOW_GAP_CHARS):
            return
        return end + 1

    def _empty_row_insert(self, layout, target_row, placed, selected_id) -> tuple[int, int, str] | None:
        row_text = self._build_row(layout, placed, selected_id=selected_id)
        for marker in layout.breaks:
            if marker.row_before < target_row <= marker.row_after:
                before_count = target_row - marker.row_before
                after_count = marker.row_after - target_row
                replacement = self._break_marker(before_count) + row_text + self._break_marker(after_count)
                return (
                    marker.node.source.start,
                    marker.node.source.end,
                    replacement,
                )
        real_components = self._real_components(layout.components)
        if real_components and target_row > max((item.row for item in real_components)):
            anchor = max(real_components, key=(lambda item: item.node.source.end))
            gap_rows = max(1, target_row - anchor.row)
            return (
                anchor.node.source.end,
                anchor.node.source.end,
                self._break_marker(gap_rows) + row_text,
            )

    def _build_row(self, layout, placed, selected_id, deleted_ids=None, min_end_x=None) -> str:
        deleted_ids = deleted_ids or set()
        cursor = layout.content_x
        parts = []
        for item in sorted(placed, key=(lambda value: (value.x, value.component.node.source.start, value.placeholder))):
            gap = max(0, item.x - cursor)
            parts.append(self._spacer(gap))
            if item.placeholder or item.component.node.id in deleted_ids:
                parts.append(self._spacer(item.component.rect.width))
            else:
                parts.append(self._component_token((item.component), selected=(item.component.node.id == selected_id)))
            cursor = item.x + item.component.rect.width

        if min_end_x is not None:
            parts.append(self._spacer(min_end_x - cursor))
        return "".join((part for part in parts if part))

    def _component_token(self, component: LayoutComponent, selected: bool) -> str:
        parent_raw = str(component.node.props.get("str_parent_raw") or "")
        if component.node.props.get("str_expanded") and parent_raw and not component.node.props.get("str_multi_expanded"):
            return parent_raw
        raw = component.node.raw
        if raw.startswith("<") and raw.endswith(">"):
            return raw
        text = component.node.text.replace("\r", "").replace("\n", "")
        if not text.strip():
            return self._spacer(component.rect.width)
        return f"<{text.strip()}/FCOLOR=255>"

    def _spacer(self, width_px: int) -> str:
        count = max(0, round(width_px / self.char_width))
        if count <= 0:
            return ""
        return "<" + " " * count + ">"

    def _break_marker(self, count: int) -> str:
        if count <= 0:
            return ""
        return " ".join(("\\" for _index in range(count))) + "\n"

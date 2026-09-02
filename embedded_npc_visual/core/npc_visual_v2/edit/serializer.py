from __future__ import annotations

import re

from ..ast import LayoutComponent, LayoutDocument
from ..components import CoordinateSpec, EDITABLE_COORDINATE_SPECS
from .flow import FlowReflowEngine


class SourceSerializer:
    def __init__(self, flow_engine: FlowReflowEngine | None = None) -> None:
        self.flow_engine = flow_engine or FlowReflowEngine()

    def move_component(
        self,
        source: str,
        component: LayoutComponent,
        target_x: int,
        target_y: int,
        layout: LayoutDocument | None = None,
    ):
        from .operations import EditResult

        node = component.node
        spec = EDITABLE_COORDINATE_SPECS.get(node.kind)
        if spec is None:
            if node.props.get("str_expanded") or node.props.get("mov_value_source"):
                return EditResult(False, source, "STR expanded component has no editable X/Y coordinates", node.id)
            result = self.flow_engine.move(source, layout, component, target_x, target_y)
            return EditResult(
                result.changed,
                result.source,
                result.message,
                result.selected_node_id,
                selected_raw=result.selected_raw,
                selected_kind=result.selected_kind,
                selected_text=result.selected_text,
                selected_row=result.selected_row,
                selected_x=result.selected_x,
                dirty_rows=result.dirty_rows,
                debug_lines=result.debug_lines,
            )

        prepared, error = self._coordinate_replacement(component, target_x, target_y, spec)
        if prepared is None:
            return EditResult(False, source, error, node.id)
        old_x, old_y, new_raw = prepared
        dx = target_x - component.visual_rect.x
        dy = target_y - component.visual_rect.y
        label = "Text" if spec.codec == "text_tail" else "MText" if spec.codec == "mtext" else node.kind
        return self._replace_source(
            source,
            component,
            new_raw,
            f"Updated {label} X/Y: {old_x},{old_y} -> {old_x + dx},{old_y + dy}",
            target_x=target_x,
        )

    def _coordinate_replacement(
        self,
        component: LayoutComponent,
        target_x: int,
        target_y: int,
        spec: CoordinateSpec,
    ) -> tuple[tuple[int, int, str] | None, str]:
        node = component.node
        args = node.props.get("args")
        if not isinstance(args, list):
            return None, "component arguments are not parseable"
        if len(args) <= max(spec.x_index, spec.y_index):
            return None, "component is missing X/Y arguments"

        dx = target_x - component.visual_rect.x
        dy = target_y - component.visual_rect.y
        if spec.codec == "text_tail":
            preserved = self._replace_text_xy_preserving(node.raw, dx, dy)
        elif spec.codec == "mtext":
            preserved = self._replace_mtext_xy_preserving(node.raw, dx, dy)
        else:
            preserved = self._replace_colon_xy_preserving(node.raw, spec, dx, dy)
        if preserved is not None:
            return preserved, ""
        if node.props.get("str_expanded") or node.props.get("mov_value_source"):
            return None, "STR expanded component has no editable X/Y coordinates"

        old_x = self._parse_int_arg(args[spec.x_index])
        if spec.codec == "text_tail":
            old_y, y_suffix = self._parse_int_prefix(args[spec.y_index])
        else:
            old_y = self._parse_int_arg(args[spec.y_index])
            y_suffix = ""
        if old_x is None or old_y is None:
            return None, "X/Y arguments are not integers"

        new_args = list(args)
        new_args[spec.x_index] = str(old_x + dx)
        new_args[spec.y_index] = f"{old_y + dy}{y_suffix}"
        new_raw = self._replace_colon_payload(node.raw, new_args)
        if not new_raw:
            return None, "failed to rebuild component tag"
        return (old_x, old_y, new_raw), ""

    def move_components(
        self,
        source: str,
        moves: list[tuple[LayoutComponent, int, int]],
        layout: LayoutDocument | None = None,
    ):
        from .operations import EditResult, SelectionHint

        if not moves:
            return EditResult(False, source, "没有可移动的组件")
        components = [component for component, _x, _y in moves]
        range_error = self._validate_source_ranges(source, components)
        if range_error:
            return EditResult(False, source, range_error, components[0].node.id)

        replacements: list[tuple[int, int, str]] = []
        hints: list[SelectionHint] = []
        for component, target_x, target_y in moves:
            spec = EDITABLE_COORDINATE_SPECS.get(component.node.kind)
            if spec is None:
                return EditResult(
                    False,
                    source,
                    f"组件 {component.node.kind} 没有可批量写回的 X/Y 坐标",
                    component.node.id,
                )
            prepared, error = self._coordinate_replacement(component, target_x, target_y, spec)
            if prepared is None:
                return EditResult(False, source, error, component.node.id)
            _old_x, _old_y, new_raw = prepared
            ref = component.node.source
            if new_raw != ref.raw:
                replacements.append((ref.start, ref.end, new_raw))
            hints.append(
                SelectionHint(
                    selected_node_id=component.node.id,
                    selected_raw=new_raw,
                    selected_kind=component.node.kind,
                    selected_text=component.node.text,
                    selected_row=component.row,
                    selected_x=target_x,
                )
            )

        if not replacements:
            return EditResult(False, source, "组件位置没有变化", selected_hints=tuple(hints))
        new_source = source
        for start, end, new_raw in sorted(replacements, reverse=True):
            new_source = new_source[:start] + new_raw + new_source[end:]
        primary = hints[0]
        return EditResult(
            True,
            new_source,
            f"已批量移动 {len(moves)} 个组件",
            primary.selected_node_id,
            selected_raw=primary.selected_raw,
            selected_kind=primary.selected_kind,
            selected_text=primary.selected_text,
            selected_row=primary.selected_row,
            selected_x=primary.selected_x,
            selected_hints=tuple(hints),
        )

    def move_flow_components(
        self,
        source: str,
        components: list[LayoutComponent],
        dx: int,
        dy: int,
        layout: LayoutDocument | None = None,
    ):
        from .operations import EditResult, SelectionHint

        if not components:
            return EditResult(False, source, "没有可移动的流式组件")
        result = self.flow_engine.shift_components(
            source,
            layout,
            components,
            dx,
            dy,
        )
        if not result.changed:
            return EditResult(
                False,
                source,
                result.message,
                result.selected_node_id,
                selected_raw=result.selected_raw,
                selected_kind=result.selected_kind,
                selected_text=result.selected_text,
                selected_row=result.selected_row,
                selected_x=result.selected_x,
                debug_lines=result.debug_lines,
            )
        row_height = max(1, int(layout.row_height)) if layout is not None else 16
        row_delta = int(dy) // row_height
        hints = tuple(
            SelectionHint(
                selected_node_id=component.node.id,
                selected_raw=component.node.raw,
                selected_kind=component.node.kind,
                selected_text=component.node.text,
                selected_row=component.row + row_delta,
                selected_x=component.rect.x + int(dx),
            )
            for component in components
        )
        primary = hints[0]
        return EditResult(
            True,
            result.source,
            result.message,
            primary.selected_node_id,
            selected_raw=primary.selected_raw,
            selected_kind=primary.selected_kind,
            selected_text=primary.selected_text,
            selected_row=primary.selected_row,
            selected_x=primary.selected_x,
            selected_hints=hints,
        )

    def delete_components(
        self,
        source: str,
        components: list[LayoutComponent],
        layout: LayoutDocument | None = None,
    ):
        from .operations import EditResult

        if not components:
            return EditResult(False, source, "没有可删除的组件")
        range_error = self._validate_source_ranges(source, components)
        if range_error:
            return EditResult(False, source, range_error, components[0].node.id)
        new_source = source
        refs = [component.node.source for component in components]
        for ref in sorted(refs, key=lambda item: item.start, reverse=True):
            new_source = new_source[: ref.start] + new_source[ref.end :]
        if new_source == source:
            return EditResult(False, source, "组件源码没有变化")
        return EditResult(True, new_source, f"已批量删除 {len(components)} 个组件")

    def _validate_source_ranges(self, source: str, components: list[LayoutComponent]) -> str:
        ranges: list[tuple[int, int]] = []
        for component in components:
            node = component.node
            if node.props.get("str_expanded") or node.props.get("mov_value_source"):
                return "变量展开组件不能参加批量编辑"
            ref = node.source
            if ref.start < 0 or ref.end <= ref.start or ref.end > len(source):
                return "组件源码位置无效，请重新渲染后再操作"
            if source[ref.start : ref.end] != ref.raw:
                return "源码已变化，请重新渲染后再操作"
            ranges.append((ref.start, ref.end))
        ranges.sort()
        for index, (start, end) in enumerate(ranges):
            if index and start < ranges[index - 1][1]:
                return "所选组件源码范围重叠，不能批量编辑"
            if index and (start, end) == ranges[index - 1]:
                return "所选组件引用同一段源码，不能批量编辑"
        return ""

    def _replace_source(
        self,
        source: str,
        component: LayoutComponent,
        new_raw: str,
        message: str,
        target_x: int,
    ):
        from .operations import EditResult

        ref = component.node.source
        if source[ref.start : ref.end] != ref.raw:
            return EditResult(
                False,
                source,
                "source changed; render again before moving this component",
                component.node.id,
                selected_raw=component.node.raw,
                selected_kind=component.node.kind,
                selected_text=component.node.text,
                selected_row=component.row,
                selected_x=component.rect.x,
                dirty_rows=(component.row,),
            )

        new_source = source[: ref.start] + new_raw + source[ref.end :]
        return EditResult(
            True,
            new_source,
            message,
            component.node.id,
            selected_raw=new_raw,
            selected_kind=component.node.kind,
            selected_text=component.node.text,
            selected_row=component.row,
            selected_x=target_x,
            dirty_rows=(component.row,),
        )

    def insert_component(
        self,
        source: str,
        component: LayoutComponent,
        target_x: int,
        target_y: int,
        layout: LayoutDocument | None = None,
        exact_coordinates: bool = False,
    ):
        from .operations import EditResult

        result = self.flow_engine.insert(
            source,
            layout,
            component,
            target_x,
            target_y,
            exact_coordinates=exact_coordinates,
        )
        return EditResult(
            result.changed,
            result.source,
            result.message,
            result.selected_node_id,
            selected_raw=result.selected_raw,
            selected_kind=result.selected_kind,
            selected_text=result.selected_text,
            selected_row=result.selected_row,
            selected_x=result.selected_x,
            dirty_rows=result.dirty_rows,
            debug_lines=result.debug_lines,
        )

    def delete_component(
        self,
        source: str,
        component: LayoutComponent,
        layout: LayoutDocument | None = None,
    ):
        from .operations import EditResult

        result = self.flow_engine.delete(source, layout, component)
        return EditResult(
            result.changed,
            result.source,
            result.message,
            result.selected_node_id,
            selected_raw=result.selected_raw,
            selected_kind=result.selected_kind,
            selected_text=result.selected_text,
            selected_row=result.selected_row,
            selected_x=result.selected_x,
            dirty_rows=result.dirty_rows,
            debug_lines=result.debug_lines,
        )

    def _replace_colon_xy_preserving(
        self,
        raw: str,
        spec: CoordinateSpec,
        dx: int,
        dy: int,
    ) -> tuple[int, int, str] | None:
        if not (raw.startswith("<") and raw.endswith(">")):
            return None

        body = raw[1:-1]
        prefix = "&" if body.startswith("&") else ""
        if prefix:
            body = body[1:]
        if ":" not in body:
            return None

        command, payload = body.split(":", 1)
        label = ""
        if "/@" in payload:
            payload, label_tail = payload.split("/@", 1)
            label = "/@" + label_tail
        tip = ""
        if "|" in payload:
            payload, tip_tail = payload.split("|", 1)
            tip = "|" + tip_tail
        args = payload.split(":") if payload else []
        if len(args) <= max(spec.x_index, spec.y_index):
            return None

        old_x = self._parse_int_arg(args[spec.x_index])
        old_y = self._parse_int_arg(args[spec.y_index])
        if old_x is None or old_y is None:
            return None

        args[spec.x_index] = str(old_x + dx)
        args[spec.y_index] = str(old_y + dy)
        return old_x, old_y, f'<{prefix}{command}:{":".join(args)}{tip}{label}>'

    def _replace_mtext_xy_preserving(self, raw: str, dx: int, dy: int) -> tuple[int, int, str] | None:
        if not (raw.startswith("<") and raw.endswith(">")):
            return None
        body = raw[1:-1]
        prefix = "&" if body.startswith("&") else ""
        if prefix:
            body = body[1:]
        if ":" not in body:
            return None
        command, payload = body.split(":", 1)
        if command.casefold() != "mtext":
            return None
        parts = payload.split(":", 4)
        offset = 1 if parts and "~" in parts[0] else 0
        if len(parts) <= offset + 2:
            return None
        old_x = self._parse_int_arg(parts[offset])
        old_y = self._parse_int_arg(parts[offset + 1])
        if old_x is None or old_y is None:
            return None
        parts[offset] = str(old_x + dx)
        parts[offset + 1] = str(old_y + dy)
        return old_x, old_y, f'<{prefix}{command}:{":".join(parts)}>'

    def _replace_text_xy_preserving(self, raw: str, dx: int, dy: int) -> tuple[int, int, str] | None:
        if not (raw.startswith("<") and raw.endswith(">")):
            return None

        body = raw[1:-1]
        prefix = "&" if body.startswith("&") else ""
        if prefix:
            body = body[1:]
        if ":" not in body:
            return None

        command, payload = body.split(":", 1)
        if command.casefold() != "text":
            return None

        label = ""
        if "/@" in payload:
            payload, label_tail = payload.split("/@", 1)
            label = "/@" + label_tail
        parts = payload.rsplit(":", 2)
        if len(parts) != 3:
            return None

        text_payload, x_arg, y_arg = parts
        old_x = self._parse_int_arg(x_arg)
        old_y, y_suffix = self._parse_int_prefix(y_arg)
        if old_x is None or old_y is None:
            return None

        new_payload = f"{text_payload}:{old_x + dx}:{old_y + dy}{y_suffix}"
        return old_x, old_y, f"<{prefix}{command}:{new_payload}{label}>"

    def _replace_colon_payload(self, raw: str, args: list[str]) -> str:
        if not (raw.startswith("<") and raw.endswith(">")):
            return ""

        body = raw[1:-1]
        prefix = "&" if body.startswith("&") else ""
        if prefix:
            body = body[1:]
        if ":" not in body:
            return ""

        command, payload = body.split(":", 1)
        label = ""
        if "/@" in payload:
            payload, label_tail = payload.split("/@", 1)
            label = "/@" + label_tail
        tip = ""
        if "|" in payload:
            _payload, tip_tail = payload.split("|", 1)
            tip = "|" + tip_tail
        return f'<{prefix}{command}:{":".join(args)}{tip}{label}>'

    def _parse_int_arg(self, value: object) -> int | None:
        text = str(value).strip()
        try:
            return int(text)
        except ValueError:
            return None

    def _parse_int_prefix(self, value: object) -> tuple[int | None, str]:
        text = str(value)
        match = re.match(r"\s*(-?\d+)(.*)\Z", text, re.S)
        if not match:
            return None, ""
        return int(match.group(1)), match.group(2)

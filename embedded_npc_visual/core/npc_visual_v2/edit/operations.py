from __future__ import annotations

from dataclasses import dataclass

from ..ast import LayoutComponent, LayoutDocument
from .serializer import SourceSerializer


@dataclass(frozen=True)
class SelectionHint:
    selected_node_id: str = ""
    selected_raw: str = ""
    selected_kind: str = ""
    selected_text: str = ""
    selected_row: int = -1
    selected_x: int = -1


@dataclass(frozen=True)
class EditResult:
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
    selected_hints: tuple[SelectionHint, ...] = ()


class MoveComponentOperation:
    def __init__(self, serializer: SourceSerializer | None = None) -> None:
        self.serializer = serializer or SourceSerializer()

    def apply(
        self,
        source: str,
        component: LayoutComponent,
        target_x: int,
        target_y: int,
        layout: LayoutDocument | None = None,
    ) -> EditResult:
        return self.serializer.move_component(source, component, target_x, target_y, layout=layout)

    def apply_many(
        self,
        source: str,
        moves: list[tuple[LayoutComponent, int, int]],
        layout: LayoutDocument | None = None,
    ) -> EditResult:
        return self.serializer.move_components(source, moves, layout=layout)

    def apply_flow_group(
        self,
        source: str,
        components: list[LayoutComponent],
        dx: int,
        dy: int,
        layout: LayoutDocument | None = None,
    ) -> EditResult:
        return self.serializer.move_flow_components(
            source,
            components,
            dx,
            dy,
            layout=layout,
        )


class InsertComponentOperation:
    def __init__(self, serializer: SourceSerializer | None = None) -> None:
        self.serializer = serializer or SourceSerializer()

    def apply(
        self,
        source: str,
        component: LayoutComponent,
        target_x: int,
        target_y: int,
        layout: LayoutDocument | None = None,
        exact_coordinates: bool = False,
    ) -> EditResult:
        return self.serializer.insert_component(
            source,
            component,
            target_x,
            target_y,
            layout=layout,
            exact_coordinates=exact_coordinates,
        )


class DeleteComponentOperation:
    def __init__(self, serializer: SourceSerializer | None = None) -> None:
        self.serializer = serializer or SourceSerializer()

    def apply(
        self,
        source: str,
        component: LayoutComponent,
        layout: LayoutDocument | None = None,
    ) -> EditResult:
        return self.serializer.delete_component(source, component, layout=layout)

    def apply_many(
        self,
        source: str,
        components: list[LayoutComponent],
        layout: LayoutDocument | None = None,
    ) -> EditResult:
        return self.serializer.delete_components(source, components, layout=layout)

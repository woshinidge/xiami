from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CoordinateSpec:
    x_index: int
    y_index: int
    codec: str = "colon"
    editable: bool = True
    direct_insert: bool = True


@dataclass(frozen=True)
class ComponentSpec:
    kind: str
    coordinates: CoordinateSpec | None = None
    size_indexes: tuple[int, int] | None = None
    visual_role: str = "text"


COMPONENT_SPECS: dict[str, ComponentSpec] = {
    "img": ComponentSpec("img", CoordinateSpec(2, 3), visual_role="pixmap"),
    "imgex": ComponentSpec("imgex", CoordinateSpec(4, 5), visual_role="pixmap"),
    "playimg": ComponentSpec("playimg", CoordinateSpec(4, 5), visual_role="pixmap"),
    "playimgex": ComponentSpec("playimgex", CoordinateSpec(5, 6), visual_role="pixmap"),
    "monster": ComponentSpec("monster", CoordinateSpec(4, 5), visual_role="pixmap"),
    "itemshow": ComponentSpec("itemshow", CoordinateSpec(2, 3), visual_role="pixmap"),
    "itembox": ComponentSpec("itembox", CoordinateSpec(3, 4), visual_role="pixmap"),
    "progressbar": ComponentSpec("progressbar", CoordinateSpec(0, 1), visual_role="pixmap"),
    "positioned_text": ComponentSpec(
        "positioned_text",
        CoordinateSpec(1, 2, codec="text_tail", direct_insert=False),
    ),
    "mtext": ComponentSpec(
        "mtext",
        CoordinateSpec(0, 1, codec="mtext", direct_insert=False),
    ),
    "layout": ComponentSpec(
        "layout",
        CoordinateSpec(0, 1, editable=False, direct_insert=False),
        size_indexes=(2, 3),
    ),
    "listview": ComponentSpec(
        "listview",
        CoordinateSpec(0, 1, editable=False, direct_insert=False),
        size_indexes=(2, 3),
    ),
}

LAYOUT_COORDINATE_INDEXES = {
    kind: (spec.coordinates.x_index, spec.coordinates.y_index)
    for kind, spec in COMPONENT_SPECS.items()
    if spec.coordinates is not None
}

CONTAINER_SIZE_INDEXES = {
    kind: spec.size_indexes
    for kind, spec in COMPONENT_SPECS.items()
    if spec.size_indexes is not None
}

EDITABLE_COORDINATE_SPECS = {
    kind: spec.coordinates
    for kind, spec in COMPONENT_SPECS.items()
    if spec.coordinates is not None and spec.coordinates.editable
}

EDITABLE_COORDINATE_INDEXES = {
    kind: (spec.x_index, spec.y_index)
    for kind, spec in EDITABLE_COORDINATE_SPECS.items()
}

DIRECT_INSERT_COORDINATE_INDEXES = {
    kind: (spec.x_index, spec.y_index)
    for kind, spec in EDITABLE_COORDINATE_SPECS.items()
    if spec.direct_insert
}

PIXMAP_COMPONENT_KINDS = frozenset(
    kind for kind, spec in COMPONENT_SPECS.items() if spec.visual_role == "pixmap"
)

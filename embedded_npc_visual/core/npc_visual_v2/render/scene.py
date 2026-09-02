from __future__ import annotations

from ..ast import LayoutDocument


class RenderSceneModel:
    """UI-neutral scene payload built from a layout document."""

    def __init__(self, layout: LayoutDocument) -> None:
        self.layout = layout

    @property
    def component_count(self) -> int:
        return len(self.layout.components)

from __future__ import annotations

from dataclasses import dataclass

from ..ast import LayoutComponent


@dataclass(frozen=True)
class RenderItem:
    component: LayoutComponent
    selected: bool = False

"""NPC visual engine v2.

The v2 package keeps parsing, layout, rendering data, and editing operations
separate so the Qt page can stay thin.
"""

from __future__ import annotations

from .ast import LayoutBreak, LayoutComponent, LayoutDocument, NpcComponentNode, NpcDocument, NpcLabelBlock, SourceRef
from .engine import NpcVisualEngine

__all__ = [
    "LayoutComponent",
    "LayoutBreak",
    "LayoutDocument",
    "NpcComponentNode",
    "NpcDocument",
    "NpcLabelBlock",
    "NpcVisualEngine",
    "SourceRef",
]

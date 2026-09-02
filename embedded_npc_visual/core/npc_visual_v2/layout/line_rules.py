from __future__ import annotations


class LineRuleEngine:
    """Central place for NPC line-break behavior.

    The first implementation is deliberately small; later compatibility rules
    should land here instead of inside the renderer or editor.
    """

    def break_count(self, marker: str) -> int:
        count = marker.count("\\")
        return max(1, count)

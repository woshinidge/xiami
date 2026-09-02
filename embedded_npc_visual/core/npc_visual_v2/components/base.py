from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ComponentPlugin:
    kind: str
    display_name: str

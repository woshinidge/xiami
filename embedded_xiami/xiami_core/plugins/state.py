from __future__ import annotations

import json
from pathlib import Path

from xiami_core.storage.paths import LOG_HOME, atomic_write_json


class PluginStateStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or LOG_HOME / "plugins.json"

    def is_enabled(self, plugin_id: str) -> bool:
        return bool(self.load().get(plugin_id, True))

    def set_enabled(self, plugin_id: str, enabled: bool) -> None:
        data = self.load()
        data[plugin_id] = enabled
        self.save(data)

    def load(self) -> dict[str, bool]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            return {}
        if not isinstance(raw, dict):
            return {}
        return {str(key): bool(value) for key, value in raw.items()}

    def save(self, data: dict[str, bool]) -> None:
        atomic_write_json(self.path, data)

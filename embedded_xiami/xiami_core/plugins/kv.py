from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from xiami_core.storage.paths import XIAMI_HOME, atomic_write_json


class PluginKVStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or XIAMI_HOME / "plugin_state"
        self._lock = threading.Lock()

    def get(self, plugin_id: str, key: str, default: Any = None) -> Any:
        return self.load(plugin_id).get(key, default)

    def set(self, plugin_id: str, key: str, value: Any) -> None:
        data = self.load(plugin_id)
        data[key] = value
        self.save(plugin_id, data)

    def delete(self, plugin_id: str, key: str) -> None:
        data = self.load(plugin_id)
        if key in data:
            del data[key]
            self.save(plugin_id, data)

    def load(self, plugin_id: str) -> dict[str, Any]:
        path = self._path(plugin_id)
        if not path.exists():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            return {}
        return raw if isinstance(raw, dict) else {}

    def save(self, plugin_id: str, data: dict[str, Any]) -> None:
        path = self._path(plugin_id)
        with self._lock:
            atomic_write_json(path, data)

    def _path(self, plugin_id: str) -> Path:
        safe_id = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in plugin_id or "shared")
        return self.root / f"{safe_id}.json"

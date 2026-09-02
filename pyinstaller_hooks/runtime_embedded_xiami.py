from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path


def _resource_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))


_embedded_root = _resource_root() / "embedded_xiami"
_manifest_path = _embedded_root / "bundled_plugins.json"
try:
    _manifest_payload = json.loads(_manifest_path.read_text(encoding="utf-8"))
except (OSError, ValueError):
    _manifest_payload = {"plugins": []}

_plugins = {
    str(item.get("id") or ""): dict(item)
    for item in _manifest_payload.get("plugins", [])
    if isinstance(item, dict) and str(item.get("id") or "")
}
_plugin_root_key = os.path.normcase(os.path.abspath(str(_embedded_root / "xiami_plugins")))


def _virtual_plugin_id(path: object) -> str:
    candidate = Path(path)
    if candidate.name.lower() != "plugin.py":
        return ""
    plugin_id = candidate.parent.name
    if plugin_id not in _plugins:
        return ""
    parent_key = os.path.normcase(os.path.abspath(str(candidate.parent.parent)))
    return plugin_id if parent_key == _plugin_root_key else ""


_path_exists = Path.exists
_path_is_file = Path.is_file
_path_read_text = Path.read_text


def _bundled_exists(self: Path) -> bool:
    if _virtual_plugin_id(self):
        return True
    return _path_exists(self)


def _bundled_is_file(self: Path) -> bool:
    if _virtual_plugin_id(self):
        return True
    return _path_is_file(self)


def _bundled_read_text(self: Path, *args, **kwargs) -> str:
    plugin_id = _virtual_plugin_id(self)
    if not plugin_id:
        return _path_read_text(self, *args, **kwargs)
    item = _plugins[plugin_id]
    lines = [
        f"PLUGIN_NAME = {str(item.get('name') or plugin_id)!r}",
        f"PLUGIN_VERSION = {str(item.get('version') or '-')!r}",
        f"PLUGIN_DESCRIPTION = {str(item.get('description') or '')!r}",
        f"_XIAMI_BUNDLED_COMMANDS = {list(item.get('commands') or [])!r}",
    ]
    return "\n".join(lines) + "\n"


# The existing UI and loader use Path checks to discover file-based plugins.
# Expose only the expected virtual entry points; all unrelated paths keep the
# original pathlib behavior.
Path.exists = _bundled_exists
Path.is_file = _bundled_is_file
Path.read_text = _bundled_read_text


try:
    from xiami_core.plugins import loader as _plugin_loader
except Exception:
    _plugin_loader = None


if _plugin_loader is not None:
    _load_module_from_file = _plugin_loader._load_module

    def _load_bundled_module(module_id: str, plugin_file: Path):
        plugin_id = _virtual_plugin_id(plugin_file)
        if not plugin_id:
            return _load_module_from_file(module_id, plugin_file)
        module_name = str(_plugins[plugin_id].get("module") or "")
        if not module_name:
            raise RuntimeError(f"Bundled plugin module is missing: {plugin_id}")
        module = importlib.import_module(module_name)
        if module_name in sys.modules and getattr(module, "__xiami_loaded_once__", False):
            module = importlib.reload(module)
        setattr(module, "__xiami_loaded_once__", True)
        return module

    _plugin_loader._load_module = _load_bundled_module

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from xiami_core.plugins.context import PluginContext


PERMISSIONS_PLUGIN_ID = "permissions"
PERMISSIONS_CONFIG_STATE_KEY = "config"


@dataclass
class PluginPermissionService:
    ctx: PluginContext

    def owners(self) -> set[str]:
        configured = _ids_from_value(self.ctx.get_config("owners", []))
        central_config = _ids_from_value(self._permission_config().get("owners", []))
        file_config = _ids_from_value(_permissions_config_file().get("owners", []))
        stored = _ids_from_value(self._permission_state("owners", []))
        if self.ctx.plugin_id == PERMISSIONS_PLUGIN_ID:
            stored.update(_ids_from_value(self.ctx.get_state("owners", [])))
        return configured | central_config | file_config | stored

    def global_admins(self) -> set[str]:
        configured = _ids_from_value(self.ctx.get_config("admins", []))
        central_config = _ids_from_value(self._permission_config().get("admins", []))
        file_config = _ids_from_value(_permissions_config_file().get("admins", []))
        stored = _ids_from_value(self._permission_state("global_admins", []))
        if self.ctx.plugin_id == PERMISSIONS_PLUGIN_ID:
            stored.update(_ids_from_value(self.ctx.get_state("global_admins", [])))
        return configured | central_config | file_config | stored | self.owners()

    def group_admins(self, group_id: str) -> set[str]:
        groups = self._groups()
        stored = _ids_from_value(groups.get(str(group_id), []))
        return stored | self.global_admins()

    def is_owner(self, user_id: str | int) -> bool:
        return str(user_id) in self.owners()

    def is_admin(self, user_id: str | int, group_id: str = "") -> bool:
        if group_id:
            return str(user_id) in self.group_admins(group_id)
        return str(user_id) in self.global_admins()

    def require_admin(self, user_id: str | int, group_id: str = "") -> tuple[bool, str]:
        if self.is_admin(user_id, group_id):
            return True, ""
        return False, "权限不足，需要管理员。"

    def add_global_admins(self, user_ids: list[str]) -> int:
        admins = set(self._permission_state("global_admins", []))
        before = len(admins)
        admins.update(str(item) for item in user_ids if str(item).strip())
        self._set_permission_state("global_admins", sorted(admins))
        return len(admins) - before

    def remove_global_admins(self, user_ids: list[str]) -> int:
        admins = set(self._permission_state("global_admins", []))
        before = len(admins)
        admins.difference_update(str(item) for item in user_ids)
        self._set_permission_state("global_admins", sorted(admins))
        return before - len(admins)

    def add_group_admins(self, group_id: str, user_ids: list[str]) -> int:
        groups = self._groups()
        admins = set(groups.get(str(group_id), []))
        before = len(admins)
        admins.update(str(item) for item in user_ids if str(item).strip())
        groups[str(group_id)] = sorted(admins)
        self._set_permission_state("group_admins", groups)
        return len(admins) - before

    def remove_group_admins(self, group_id: str, user_ids: list[str]) -> int:
        groups = self._groups()
        admins = set(groups.get(str(group_id), []))
        before = len(admins)
        admins.difference_update(str(item) for item in user_ids)
        groups[str(group_id)] = sorted(admins)
        self._set_permission_state("group_admins", groups)
        return before - len(admins)

    def summary(self, group_id: str = "") -> str:
        lines = [
            "权限列表：",
            f"主人：{_format_ids(self.owners())}",
            f"全局管理员：{_format_ids(self.global_admins() - self.owners())}",
        ]
        if group_id:
            group_only = self.group_admins(group_id) - self.global_admins()
            lines.append(f"本群管理员：{_format_ids(group_only)}")
        return "\n".join(lines)

    def _permission_config(self) -> dict[str, Any]:
        if self.ctx.plugin_id == PERMISSIONS_PLUGIN_ID:
            return self.ctx.config if isinstance(self.ctx.config, dict) else {}
        value = self._permission_state(PERMISSIONS_CONFIG_STATE_KEY, {})
        return value if isinstance(value, dict) else {}

    def _permission_state(self, key: str, default: Any = None) -> Any:
        return self.ctx.state_store.get(PERMISSIONS_PLUGIN_ID, key, default)

    def _set_permission_state(self, key: str, value: Any) -> None:
        self.ctx.state_store.set(PERMISSIONS_PLUGIN_ID, key, value)

    def _groups(self) -> dict[str, list[str]]:
        value: Any = self._permission_state("group_admins", {})
        if self.ctx.plugin_id == PERMISSIONS_PLUGIN_ID:
            current = self.ctx.get_state("group_admins", {})
            if isinstance(current, dict):
                value = current
        if not isinstance(value, dict):
            return {}
        return {str(key): [str(item) for item in items] for key, items in value.items() if isinstance(items, list)}


def sync_permission_config(ctx: PluginContext) -> None:
    config = ctx.config if isinstance(ctx.config, dict) else {}
    snapshot = {
        "owners": sorted(_ids_from_value(config.get("owners", []))),
        "admins": sorted(_ids_from_value(config.get("admins", []))),
    }
    ctx.state_store.set(PERMISSIONS_PLUGIN_ID, PERMISSIONS_CONFIG_STATE_KEY, snapshot)


def _permissions_config_file() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[2] / "xiami_plugins" / PERMISSIONS_PLUGIN_ID / "plugin_config.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def parse_user_ids(text: str) -> list[str]:
    import re

    return re.findall(r"\d{5,}", text or "")


def _ids_from_value(value: Any) -> set[str]:
    if isinstance(value, str):
        return {item for item in parse_user_ids(value)}
    if not isinstance(value, (list, tuple, set)):
        return set()
    return {str(item).strip() for item in value if str(item).strip()}


def _format_ids(values: set[str]) -> str:
    return "、".join(sorted(values)) if values else "无"

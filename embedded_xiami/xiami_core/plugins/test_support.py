from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from xiami_core.plugins.group_settings import GroupSettingService


def enable_loaded_plugins_for_groups(
    ctx: Any,
    plugins: Iterable[Any],
    *group_ids: str,
) -> None:
    """Enable loaded smoke-test plugins for explicit synthetic groups."""
    groups = tuple(str(group_id) for group_id in group_ids if str(group_id)) or ("20001",)
    plugin_ids = tuple(
        str(getattr(plugin, "id", "") or "")
        for plugin in plugins
        if str(getattr(plugin, "id", "") or "")
    )
    settings = GroupSettingService(ctx)
    for group_id in groups:
        for plugin_id in plugin_ids:
            settings.set_plugin_enabled(group_id, plugin_id, True)

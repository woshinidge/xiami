from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from xiami_core.models import SendResult
from xiami_core.plugins.admin import PluginAdminService
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.kv import PluginKVStore
from xiami_core.plugins.loader import PluginLoader
from xiami_core.plugins.state import PluginStateStore


EXPECTED_ADMIN_PLUGINS = {
    "ai_reply",
    "bindings",
    "cards",
    "checkin",
    "custom_replies",
    "friend_review",
    "group_settings",
    "invites",
    "join_review",
    "knowledge",
    "member_guard",
    "quiz",
}


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plugin_root = root / "plugins"
        source_root = Path.cwd() / "xiami_plugins"
        for plugin_id in EXPECTED_ADMIN_PLUGINS:
            shutil.copytree(source_root / plugin_id, plugin_root / plugin_id)

        def send(_target: str, _text: str, _message_type: str) -> SendResult:
            return SendResult(ok=True)

        ctx = PluginContext(send_fn=send, state_store=PluginKVStore(root / "state"))
        loader = PluginLoader(plugin_root, ctx, state_store=PluginStateStore(root / "enabled.json"))
        plugins = loader.load_all()
        failed = [plugin for plugin in plugins if plugin.error]
        if len(plugins) != len(EXPECTED_ADMIN_PLUGINS) or failed:
            raise RuntimeError(f"admin schema plugins load failed: plugins={plugins!r}, failed={failed!r}")

        discovered = {plugin.id for plugin in plugins if plugin.admin_schema}
        if discovered != EXPECTED_ADMIN_PLUGINS:
            raise RuntimeError(f"admin schema plugin set changed: discovered={sorted(discovered)!r}")

        service = PluginAdminService(loader)
        for plugin_id in sorted(EXPECTED_ADMIN_PLUGINS):
            snapshot = service.snapshot(plugin_id, include_values=True)
            if snapshot["plugin_id"] != plugin_id or not snapshot["items"]:
                raise RuntimeError(f"{plugin_id} admin snapshot failed: {snapshot!r}")
            missing_ids = [item for item in snapshot["items"] if not item.get("id")]
            if missing_ids:
                raise RuntimeError(f"{plugin_id} admin snapshot item missing id: {missing_ids!r}")
            exported_path = root / "snapshots" / f"{plugin_id}.json"
            exported = service.export_snapshot(plugin_id, exported_path)
            if not exported.ok or not exported_path.exists():
                raise RuntimeError(f"{plugin_id} admin export failed: {exported!r}")
            preflight = service.import_snapshot(plugin_id, exported_path, dry_run=True)
            if not preflight.ok or not preflight.data or not preflight.data.get("applied"):
                raise RuntimeError(f"{plugin_id} admin import preflight failed: {preflight!r}")

    print("all plugin admin schema smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

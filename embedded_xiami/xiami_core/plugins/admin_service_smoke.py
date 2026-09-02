from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from xiami_core.models import SendResult
from xiami_core.plugins.admin import PluginAdminService
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.loader import PluginLoader
from xiami_core.plugins.state import PluginStateStore


def main() -> int:
    def send(_target: str, _text: str, _message_type: str) -> SendResult:
        return SendResult(ok=True)

    with TemporaryDirectory() as temp:
        root = Path(temp)
        plugin_dir = root / "admin_edit"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.py").write_text(
            "\n".join(
                [
                    "PLUGIN_ID = 'admin_edit'",
                    "PLUGIN_NAME = '后台编辑样例'",
                    "PLUGIN_CONFIG = {'enabled': True}",
                    "PLUGIN_ADMIN_SCHEMA = [",
                    "    {'id': 'members', 'label': '成员名单', 'type': 'state', 'state_key': 'members'},",
                "    {'id': 'enabled', 'label': '开关', 'type': 'config', 'config_key': 'enabled'},",
                "    {'id': 'health', 'label': '运行自检', 'type': 'runtime', 'runtime_key': 'health'},",
                "]",
                "PLUGIN_ADMIN_HANDLERS = {'health': lambda ctx: 'runtime ok'}",
                "def on_load(ctx):",
                    "    ctx.set_state('members', {'10000': ['123']})",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        loader = PluginLoader(root, PluginContext(send_fn=send), PluginStateStore(root / "enabled.json"))
        loader.load_all()
        service = PluginAdminService(loader)

        snapshot = service.snapshot("admin_edit", include_values=True)
        if snapshot["items"][0]["value"] != {"10000": ["123"]}:
            raise RuntimeError(f"snapshot state missing: {snapshot!r}")
        runtime = service.get_item("admin_edit", "health")
        if not runtime.ok or runtime.data["value"] != "runtime ok":
            raise RuntimeError(f"runtime admin item failed: {runtime!r}")
        read_only = service.set_item("admin_edit", "health", "new value")
        if read_only.ok or "只读" not in read_only.message:
            raise RuntimeError(f"runtime admin item should be readonly: {read_only!r}")

        updated = service.set_item("admin_edit", "members", {"10000": ["456", "789"]})
        if not updated.ok or updated.data["value"]["10000"] != ["456", "789"]:
            raise RuntimeError(f"state update failed: {updated!r}")

        config = service.set_item("admin_edit", "enabled", False)
        if not config.ok or config.data["summary"] != "关闭":
            raise RuntimeError(f"config update failed: {config!r}")
        saved_config = json.loads((plugin_dir / "plugin_config.json").read_text(encoding="utf-8"))
        if saved_config.get("enabled") is not False:
            raise RuntimeError(f"config file not saved: {saved_config!r}")

        exported_path = root / "admin_edit_snapshot.json"
        exported = service.export_snapshot("admin_edit", exported_path)
        if not exported.ok or not exported_path.exists():
            raise RuntimeError(f"export failed: {exported!r}")
        exported_json = json.loads(exported_path.read_text(encoding="utf-8"))
        if exported_json["plugin_id"] != "admin_edit" or not exported_json["items"]:
            raise RuntimeError(f"export content wrong: {exported_json!r}")

        deleted = service.delete_item("admin_edit", "members")
        if not deleted.ok or deleted.data["summary"] != "未写入":
            raise RuntimeError(f"delete failed: {deleted!r}")
        service.set_item("admin_edit", "enabled", True)

        imported = service.import_snapshot("admin_edit", exported_path)
        if not imported.ok or len(imported.data["applied"]) != 2:
            raise RuntimeError(f"import failed: {imported!r}")
        restored = service.snapshot("admin_edit", include_values=True)
        restored_values = {item["id"]: item.get("value") for item in restored["items"]}
        if restored_values.get("members") != {"10000": ["456", "789"]}:
            raise RuntimeError(f"state not restored: {restored!r}")
        if restored_values.get("enabled") is not False:
            raise RuntimeError(f"config not restored: {restored!r}")

        mismatch_path = root / "admin_edit_mismatch.json"
        exported_json["plugin_id"] = "other_plugin"
        mismatch_path.write_text(json.dumps(exported_json, ensure_ascii=False), encoding="utf-8")
        mismatch = service.import_snapshot("admin_edit", mismatch_path)
        if mismatch.ok:
            raise RuntimeError(f"mismatch import should fail: {mismatch!r}")
    print("admin service smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

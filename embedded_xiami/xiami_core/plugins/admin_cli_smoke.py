from __future__ import annotations

from pathlib import Path
import tempfile

from xiami_core.plugins.admin_cli import main as admin_cli_main
from xiami_core.plugins.kv import PluginKVStore


def main() -> int:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        plugin_root = root / "plugins"
        state_root = root / "state"
        export_root = root / "exports"
        plugin_id = "admin_cli_case"
        _write_admin_plugin(plugin_root, plugin_id)

        store = PluginKVStore(state_root)
        store.set(plugin_id, "members", {"10000": ["456"]})

        common = ["--plugin-root", str(plugin_root), "--state-root", str(state_root)]
        if admin_cli_main([*common, "list"]) != 0:
            raise RuntimeError("admin cli list failed")

        snapshot = export_root / "admin_cli_case.admin.json"
        if admin_cli_main([*common, "export", plugin_id, "--output", str(snapshot)]) != 0:
            raise RuntimeError("admin cli export failed")
        if not snapshot.is_file():
            raise RuntimeError("admin cli export did not create snapshot")

        if admin_cli_main([*common, "export-all", "--output", str(export_root / "all")]) != 0:
            raise RuntimeError("admin cli export-all failed")
        if not (export_root / "all" / "admin_cli_case.admin.json").is_file():
            raise RuntimeError("admin cli export-all did not create snapshot")

        store.delete(plugin_id, "members")
        if admin_cli_main([*common, "import", plugin_id, str(snapshot), "--dry-run"]) != 0:
            raise RuntimeError("admin cli dry-run import failed")
        if store.get(plugin_id, "members") is not None:
            raise RuntimeError("admin cli dry-run changed state")

        if admin_cli_main([*common, "import", plugin_id, str(snapshot)]) != 0:
            raise RuntimeError("admin cli import failed")
        if store.get(plugin_id, "members") != {"10000": ["456"]}:
            raise RuntimeError("admin cli import did not restore state")

    print("plugin admin cli smoke ok")
    return 0


def _write_admin_plugin(plugin_root: Path, plugin_id: str) -> None:
    plugin_dir = plugin_root / plugin_id
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.py").write_text(
        "\n".join(
            [
                f"PLUGIN_ID = '{plugin_id}'",
                "PLUGIN_NAME = 'Admin CLI Case'",
                "PLUGIN_CONFIG = {'enabled': True}",
                "PLUGIN_ADMIN_SCHEMA = [",
                "    {'id': 'members', 'label': '成员数据', 'type': 'state', 'state_key': 'members'},",
                "    {'id': 'enabled', 'label': '启用', 'type': 'config', 'config_key': 'enabled'},",
                "]",
                "",
            ]
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())

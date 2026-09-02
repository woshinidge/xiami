from __future__ import annotations

from pathlib import Path
import json
import tempfile

from xiami_core.plugins.kv import PluginKVStore
from xiami_core.plugins.migration_bundle_cli import MANIFEST_NAME, main as bundle_cli_main


def main() -> int:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        source_plugins = root / "source_plugins"
        source_state = root / "source_state"
        target_plugins = root / "target_plugins"
        target_state = root / "target_state"
        bundle = root / "bundle"

        _write_admin_plugin(source_plugins)
        _write_legacy_file_plugin(source_plugins)
        _write_constructor_legacy_file_plugin(source_plugins)
        PluginKVStore(source_state).set("bundle_admin", "members", {"10000": ["456"]})

        if bundle_cli_main(
            [
                "--plugin-root",
                str(source_plugins),
                "--state-root",
                str(source_state),
                "export",
                "--output",
                str(bundle),
            ]
        ) != 0:
            raise RuntimeError("bundle export failed")

        manifest_path = bundle / MANIFEST_NAME
        if not manifest_path.is_file():
            raise RuntimeError("bundle manifest missing")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        plugin_ids = {item.get("plugin_id") for item in manifest.get("items", [])}
        if plugin_ids != {"bundle_admin", "bundle_constructor_legacy", "bundle_legacy"}:
            raise RuntimeError(f"bundle manifest items wrong: {manifest!r}")

        if bundle_cli_main(
            [
                "--plugin-root",
                str(target_plugins),
                "--state-root",
                str(target_state),
                "import",
                str(bundle),
            ]
        ) != 0:
            raise RuntimeError("bundle import failed")

        if not (target_plugins / "bundle_admin" / "plugin.py").is_file():
            raise RuntimeError("bundle admin plugin was not imported")
        if not (target_plugins / "bundle_legacy" / "plugin.py").is_file():
            raise RuntimeError("bundle legacy file plugin was not normalized")
        if not (target_plugins / "bundle_constructor_legacy" / "plugin.py").is_file():
            raise RuntimeError("bundle constructor legacy file plugin was not normalized")
        if PluginKVStore(target_state).get("bundle_admin", "members") != {"10000": ["456"]}:
            raise RuntimeError("bundle admin state was not restored")

    print("plugin migration bundle cli smoke ok")
    return 0


def _write_admin_plugin(plugin_root: Path) -> None:
    plugin_dir = plugin_root / "bundle_admin"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.py").write_text(
        "\n".join(
            [
                "PLUGIN_ID = 'bundle_admin'",
                "PLUGIN_NAME = 'Bundle Admin'",
                "PLUGIN_ADMIN_SCHEMA = [",
                "    {'id': 'members', 'label': '成员数据', 'type': 'state', 'state_key': 'members'},",
                "]",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_legacy_file_plugin(plugin_root: Path) -> None:
    plugin_root.mkdir(parents=True, exist_ok=True)
    (plugin_root / "bundle_legacy.py").write_text(
        "\n".join(
            [
                "plugin_spec = {",
                "    'key': 'bundle_legacy',",
                "    'name': 'Bundle Legacy',",
                "    'hooks': ('message.private',),",
                "}",
                "",
                "def handle(context):",
                "    return None",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_constructor_legacy_file_plugin(plugin_root: Path) -> None:
    plugin_root.mkdir(parents=True, exist_ok=True)
    (plugin_root / "constructor_legacy.py").write_text(
        "\n".join(
            [
                "from xiami_onebot.plugin_api import XiamiPlugin",
                "",
                "plugin = XiamiPlugin(",
                "    key='bundle_constructor_legacy',",
                "    name='Bundle Constructor Legacy',",
                "    description='constructor-only legacy bundle smoke',",
                ")",
                "",
                "@plugin.on_message(private=True)",
                "def handle(context):",
                "    return None",
                "",
                "def register(manager):",
                "    plugin.register(manager)",
                "",
            ]
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())

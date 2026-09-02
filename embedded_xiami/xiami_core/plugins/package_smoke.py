from __future__ import annotations

from pathlib import Path
import tempfile
import zipfile

from xiami_core.models import SendResult, XiamiMessage
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.kv import PluginKVStore
from xiami_core.plugins.loader import PluginLoader
from xiami_core.plugins.packages import export_plugin_package, import_plugin_package
from xiami_core.plugins.state import PluginStateStore


def main() -> int:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        source_root = root / "source_plugins"
        _write_native_plugin(source_root)
        _write_legacy_file_plugin(source_root)

        export_dir = root / "exports"
        exported = export_plugin_package(source_root, "packaged_echo", export_dir)
        if not exported.ok or not exported.path or not exported.path.is_file():
            raise RuntimeError(f"export failed: {exported}")

        target_root = root / "target_plugins"
        imported = import_plugin_package(exported.path, target_root)
        if not imported.ok or imported.plugin_id != "packaged_echo":
            raise RuntimeError(f"import failed: {imported}")
        if import_plugin_package(exported.path, target_root).ok:
            raise RuntimeError("duplicate import should fail without overwrite")
        if not import_plugin_package(exported.path, target_root, overwrite=True).ok:
            raise RuntimeError("overwrite import failed")

        legacy_exported = export_plugin_package(source_root, "legacy_file_echo", export_dir)
        if not legacy_exported.ok or not legacy_exported.path or not legacy_exported.path.is_file():
            raise RuntimeError(f"legacy export failed: {legacy_exported}")
        with zipfile.ZipFile(legacy_exported.path) as archive:
            if "legacy_file_echo/plugin.py" not in archive.namelist():
                raise RuntimeError("legacy file plugin was not normalized to plugin.py")
        legacy_imported = import_plugin_package(legacy_exported.path, target_root)
        if not legacy_imported.ok or legacy_imported.plugin_id != "legacy_file_echo":
            raise RuntimeError(f"legacy import failed: {legacy_imported}")

        sent: list[str] = []

        def send(target: str, text: str, message_type: str) -> SendResult:
            sent.append(f"{message_type}:{target}:{text}")
            return SendResult(ok=True)

        ctx = PluginContext(send_fn=send, state_store=PluginKVStore(root / "state"))
        loader = PluginLoader(target_root, ctx, state_store=PluginStateStore(root / "enabled.json"))
        plugins = loader.load_all()
        errors = [plugin.error for plugin in plugins if plugin.error]
        if len(plugins) != 2 or errors:
            raise RuntimeError(f"imported plugin load failed: {plugins}")

        loader.dispatch_message(XiamiMessage(message_type="private", sender="10001", target="10001", text="/pkg ok"))
        loader.dispatch_message(XiamiMessage(message_type="private", sender="10001", target="10001", text="legacy hello"))
        expected = [
            "private:10001:pkg:ok",
            "private:10001:legacy-file:hello",
        ]
        if sent != expected:
            raise RuntimeError(f"imported plugin dispatch failed: {sent}")

        evil = root / "evil.zip"
        with zipfile.ZipFile(evil, "w") as archive:
            archive.writestr("../evil.py", "bad")
        if import_plugin_package(evil, target_root).ok:
            raise RuntimeError("unsafe package path should fail")

    print("plugin package smoke ok")
    return 0


def _write_native_plugin(source_root: Path) -> None:
    source_plugin = source_root / "packaged_echo"
    source_plugin.mkdir(parents=True)
    (source_plugin / "plugin.py").write_text(
        "\n".join(
            [
                "from xiami_core.plugins.compat import on_command",
                "PLUGIN_ID = 'packaged_echo'",
                "PLUGIN_NAME = 'Packaged Echo'",
                "PLUGIN_VERSION = '1.0.0'",
                "MATCHERS = []",
                "@on_command('/pkg')",
                "def pkg(event, ctx, session):",
                "    ctx.reply(event, 'pkg:' + session.argument)",
                "MATCHERS.append(pkg)",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (source_plugin / "plugin_config.json").write_text('{"enabled": true}', encoding="utf-8")


def _write_legacy_file_plugin(source_root: Path) -> None:
    source_root.mkdir(parents=True, exist_ok=True)
    (source_root / "legacy_file_echo.py").write_text(
        "\n".join(
            [
                "plugin_spec = {",
                "    'key': 'legacy_file_echo',",
                "    'name': 'Legacy File Echo',",
                "    'description': 'legacy file package smoke',",
                "    'hooks': ('message.private',),",
                "}",
                "",
                "def handle(context):",
                "    if context.message.startswith('/'):",
                "        return None",
                "    if not context.message.startswith('legacy '):",
                "        return None",
                "    return 'legacy-file:' + context.message[len('legacy '):]",
                "",
            ]
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())

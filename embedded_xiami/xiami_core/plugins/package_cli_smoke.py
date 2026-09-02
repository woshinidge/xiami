from __future__ import annotations

from pathlib import Path
import tempfile

from xiami_core.plugins.package_cli import main as package_cli_main


def main() -> int:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        source_root = root / "source_plugins"
        target_root = root / "target_plugins"
        export_root = root / "exports"
        _write_native_plugin(source_root)
        _write_legacy_file_plugin(source_root)
        _write_constructor_legacy_file_plugin(source_root)

        if package_cli_main(["list", "--plugin-root", str(source_root)]) != 0:
            raise RuntimeError("package cli list failed")
        if package_cli_main(["export-all", "--plugin-root", str(source_root), "--output", str(export_root)]) != 0:
            raise RuntimeError("package cli export-all failed")

        native_package = export_root / "cli_native.xiami-plugin.zip"
        legacy_package = export_root / "cli_legacy_file.xiami-plugin.zip"
        constructor_package = export_root / "cli_constructor_legacy.xiami-plugin.zip"
        if not native_package.is_file() or not legacy_package.is_file() or not constructor_package.is_file():
            raise RuntimeError("package cli did not export expected packages")

        if package_cli_main(["import", str(native_package), str(legacy_package), str(constructor_package), "--plugin-root", str(target_root)]) != 0:
            raise RuntimeError("package cli import failed")
        if not (target_root / "cli_native" / "plugin.py").is_file():
            raise RuntimeError("native plugin package was not imported")
        if not (target_root / "cli_legacy_file" / "plugin.py").is_file():
            raise RuntimeError("legacy file package was not normalized on import")
        if not (target_root / "cli_constructor_legacy" / "plugin.py").is_file():
            raise RuntimeError("constructor legacy package was not normalized on import")

    print("plugin package cli smoke ok")
    return 0


def _write_native_plugin(source_root: Path) -> None:
    plugin_dir = source_root / "cli_native"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.py").write_text(
        "\n".join(
            [
                "PLUGIN_ID = 'cli_native'",
                "PLUGIN_NAME = 'CLI Native'",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_legacy_file_plugin(source_root: Path) -> None:
    source_root.mkdir(parents=True, exist_ok=True)
    (source_root / "cli_legacy_file.py").write_text(
        "\n".join(
            [
                "plugin_spec = {",
                "    'key': 'cli_legacy_file',",
                "    'name': 'CLI Legacy File',",
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


def _write_constructor_legacy_file_plugin(source_root: Path) -> None:
    source_root.mkdir(parents=True, exist_ok=True)
    (source_root / "constructor_legacy.py").write_text(
        "\n".join(
            [
                "from xiami_onebot.plugin_api import XiamiPlugin",
                "",
                "plugin = XiamiPlugin(",
                "    key='cli_constructor_legacy',",
                "    name='CLI Constructor Legacy',",
                "    description='constructor-only legacy file plugin',",
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

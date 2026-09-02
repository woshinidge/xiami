from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from xiami_core.models import SendResult
from xiami_core.plugins.admin import PluginAdminService
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.kv import PluginKVStore
from xiami_core.plugins.loader import PluginLoader
from xiami_core.plugins.packages import discover_exportable_plugins, export_plugin_package, import_plugin_package
from xiami_core.plugins.state import PluginStateStore


MANIFEST_NAME = "xiami_migration_bundle.json"


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return int(args.handler(args))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Xiami plugin code + admin state migration bundle helper")
    parser.add_argument("--plugin-root", type=Path, default=Path("xiami_plugins"))
    parser.add_argument("--state-root", type=Path, default=None)
    parser.add_argument("--enabled-state", type=Path, default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser("export", help="export plugin packages and admin snapshots")
    export_parser.add_argument("plugin_ids", nargs="*")
    export_parser.add_argument("--output", type=Path, default=Path("exports/migration_bundle"))
    export_parser.set_defaults(handler=_cmd_export)

    import_parser = subparsers.add_parser("import", help="import a migration bundle")
    import_parser.add_argument("bundle", type=Path)
    import_parser.add_argument("--overwrite", action="store_true")
    import_parser.add_argument("--skip-admin", action="store_true")
    import_parser.set_defaults(handler=_cmd_import)
    return parser


def _cmd_export(args: argparse.Namespace) -> int:
    output = args.output
    package_dir = output / "plugins"
    admin_dir = output / "admin"
    package_dir.mkdir(parents=True, exist_ok=True)
    admin_dir.mkdir(parents=True, exist_ok=True)

    exportable = {plugin.plugin_id: plugin for plugin in discover_exportable_plugins(args.plugin_root)}
    plugin_ids = list(args.plugin_ids) if args.plugin_ids else sorted(exportable)
    if not plugin_ids:
        print("bundle export failed: no exportable plugins")
        return 1

    service = _admin_service(args.plugin_root, args.state_root, args.enabled_state)
    admin_ids = {plugin.id for plugin in service.loader.plugins if _has_restorable_admin_schema(plugin.admin_schema)}
    items: list[dict[str, Any]] = []
    ok = True

    for plugin_id in plugin_ids:
        item: dict[str, Any] = {"plugin_id": plugin_id}
        package = export_plugin_package(args.plugin_root, plugin_id, package_dir)
        item["package_ok"] = package.ok
        item["package_message"] = package.message
        if package.path:
            item["package"] = _relative_to(package.path, output)
        if not package.ok:
            ok = False

        if plugin_id in admin_ids:
            admin_path = admin_dir / f"{plugin_id}.admin.json"
            admin = service.export_snapshot(plugin_id, admin_path)
            item["admin_ok"] = admin.ok
            item["admin_message"] = admin.message
            if admin.ok:
                item["admin"] = _relative_to(admin_path, output)
            else:
                ok = False
        else:
            item["admin_ok"] = False
            item["admin_message"] = "no admin schema"
        items.append(item)

    manifest = {
        "format": "xiami-plugin-migration-bundle",
        "version": 1,
        "plugin_root": str(args.plugin_root),
        "items": items,
    }
    manifest_path = output / MANIFEST_NAME
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"bundle export {'ok' if ok else 'failed'}: {manifest_path} items={len(items)}")
    return 0 if ok else 1


def _cmd_import(args: argparse.Namespace) -> int:
    bundle = args.bundle
    manifest_path = bundle / MANIFEST_NAME if bundle.is_dir() else bundle
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"bundle import failed: {exc}")
        return 1
    if not isinstance(manifest, dict) or manifest.get("format") != "xiami-plugin-migration-bundle":
        print("bundle import failed: invalid manifest")
        return 1

    base = manifest_path.parent
    items = manifest.get("items")
    if not isinstance(items, list):
        print("bundle import failed: manifest items missing")
        return 1

    ok = True
    imported_plugins: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            ok = False
            continue
        plugin_id = str(item.get("plugin_id") or "").strip()
        package_rel = str(item.get("package") or "").strip()
        if not plugin_id or not package_rel:
            ok = False
            print(f"plugin import failed: invalid item {item!r}")
            continue
        result = import_plugin_package(base / package_rel, args.plugin_root, overwrite=args.overwrite)
        print(f"plugin import {'ok' if result.ok else 'failed'}: {plugin_id} - {result.message}")
        ok = ok and result.ok
        if result.ok:
            imported_plugins.append(result.plugin_id or plugin_id)

    if not args.skip_admin:
        service = _admin_service(args.plugin_root, args.state_root, args.enabled_state)
        for item in items:
            if not isinstance(item, dict):
                continue
            plugin_id = str(item.get("plugin_id") or "").strip()
            admin_rel = str(item.get("admin") or "").strip()
            if not plugin_id or not admin_rel:
                continue
            result = service.import_snapshot(plugin_id, base / admin_rel)
            print(f"admin import {'ok' if result.ok else 'failed'}: {plugin_id} - {result.message}")
            ok = ok and result.ok

    print(f"bundle import {'ok' if ok else 'failed'}: plugins={len(imported_plugins)}")
    return 0 if ok else 1


def _admin_service(plugin_root: Path, state_root: Path | None, enabled_state: Path | None) -> PluginAdminService:
    def send(target: str, text: str, message_type: str = "private") -> SendResult:
        return SendResult(ok=True, message=f"migration-bundle noop send to {message_type}:{target}")

    context = PluginContext(send_fn=send, state_store=PluginKVStore(state_root))
    loader = PluginLoader(plugin_root, context, state_store=PluginStateStore(enabled_state or plugin_root / ".plugin_enabled.json"))
    loader.load_all()
    return PluginAdminService(loader)


def _has_restorable_admin_schema(schema: list[dict[str, Any]]) -> bool:
    return any(item.get("state_key") or item.get("config_key") for item in schema)


def _relative_to(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    raise SystemExit(main())

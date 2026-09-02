from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from xiami_core.plugins.packages import (
    discover_exportable_plugins,
    export_plugin_package,
    import_plugin_package,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return int(args.handler(args))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Xiami plugin package migration helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="list exportable plugins")
    list_parser.add_argument("--plugin-root", type=Path, default=Path("xiami_plugins"))
    list_parser.set_defaults(handler=_cmd_list)

    export_parser = subparsers.add_parser("export", help="export one or more plugins")
    export_parser.add_argument("plugin_ids", nargs="+")
    export_parser.add_argument("--plugin-root", type=Path, default=Path("xiami_plugins"))
    export_parser.add_argument("--output", type=Path, default=Path("exports/plugins"))
    export_parser.set_defaults(handler=_cmd_export)

    export_all_parser = subparsers.add_parser("export-all", help="export every discoverable plugin")
    export_all_parser.add_argument("--plugin-root", type=Path, default=Path("xiami_plugins"))
    export_all_parser.add_argument("--output", type=Path, default=Path("exports/plugins"))
    export_all_parser.set_defaults(handler=_cmd_export_all)

    import_parser = subparsers.add_parser("import", help="import plugin packages")
    import_parser.add_argument("packages", nargs="+", type=Path)
    import_parser.add_argument("--plugin-root", type=Path, default=Path("xiami_plugins"))
    import_parser.add_argument("--overwrite", action="store_true")
    import_parser.set_defaults(handler=_cmd_import)
    return parser


def _cmd_list(args: argparse.Namespace) -> int:
    plugins = discover_exportable_plugins(args.plugin_root)
    for plugin in plugins:
        print(f"{plugin.plugin_id}\t{plugin.source_type}\t{plugin.path}")
    print(f"total={len(plugins)}")
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    ok = True
    for plugin_id in args.plugin_ids:
        result = export_plugin_package(args.plugin_root, plugin_id, args.output)
        ok = _print_result("export", result.ok, result.plugin_id or plugin_id, result.path, result.message) and ok
    return 0 if ok else 1


def _cmd_export_all(args: argparse.Namespace) -> int:
    plugins = discover_exportable_plugins(args.plugin_root)
    if not plugins:
        print("export-all failed: no exportable plugins")
        return 1
    ok = True
    for plugin in plugins:
        result = export_plugin_package(args.plugin_root, plugin.plugin_id, args.output)
        ok = _print_result("export", result.ok, result.plugin_id or plugin.plugin_id, result.path, result.message) and ok
    return 0 if ok else 1


def _cmd_import(args: argparse.Namespace) -> int:
    ok = True
    for package_path in args.packages:
        result = import_plugin_package(package_path, args.plugin_root, overwrite=args.overwrite)
        ok = _print_result("import", result.ok, result.plugin_id, result.path, result.message) and ok
    return 0 if ok else 1


def _print_result(action: str, ok: bool, plugin_id: str, path: Path | None, message: str) -> bool:
    status = "ok" if ok else "failed"
    location = f" {path}" if path else ""
    detail = f" - {message}" if message else ""
    print(f"{action} {status}: {plugin_id}{location}{detail}")
    return ok


if __name__ == "__main__":
    raise SystemExit(main())

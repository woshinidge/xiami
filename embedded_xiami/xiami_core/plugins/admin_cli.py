from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from xiami_core.models import SendResult
from xiami_core.plugins.admin import PluginAdminOperation, PluginAdminService
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.kv import PluginKVStore
from xiami_core.plugins.loader import PluginLoader
from xiami_core.plugins.state import PluginStateStore


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return int(args.handler(args))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Xiami plugin admin state migration helper")
    parser.add_argument("--plugin-root", type=Path, default=Path("xiami_plugins"))
    parser.add_argument("--state-root", type=Path, default=None)
    parser.add_argument("--enabled-state", type=Path, default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="list plugins with admin schema")
    list_parser.set_defaults(handler=_cmd_list)

    export_parser = subparsers.add_parser("export", help="export one plugin admin snapshot")
    export_parser.add_argument("plugin_id")
    export_parser.add_argument("--output", type=Path, default=None)
    export_parser.set_defaults(handler=_cmd_export)

    export_all_parser = subparsers.add_parser("export-all", help="export every admin-capable plugin")
    export_all_parser.add_argument("--output", type=Path, default=Path("exports/admin"))
    export_all_parser.set_defaults(handler=_cmd_export_all)

    import_parser = subparsers.add_parser("import", help="import one plugin admin snapshot")
    import_parser.add_argument("plugin_id")
    import_parser.add_argument("snapshot", type=Path)
    import_parser.add_argument("--dry-run", action="store_true")
    import_parser.set_defaults(handler=_cmd_import)
    return parser


def _cmd_list(args: argparse.Namespace) -> int:
    service = _admin_service(args)
    count = 0
    for plugin in service.loader.plugins:
        if not plugin.admin_schema:
            continue
        count += 1
        items = ",".join(str(item.get("id") or item.get("state_key") or item.get("config_key")) for item in plugin.admin_schema)
        print(f"{plugin.id}\t{len(plugin.admin_schema)}\t{items}")
    print(f"total={count}")
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    service = _admin_service(args)
    output = args.output or Path("exports/admin") / f"{args.plugin_id}.admin.json"
    result = service.export_snapshot(args.plugin_id, output)
    return _print_operation("export", result)


def _cmd_export_all(args: argparse.Namespace) -> int:
    service = _admin_service(args)
    args.output.mkdir(parents=True, exist_ok=True)
    ok = True
    count = 0
    for plugin in service.loader.plugins:
        if not plugin.admin_schema:
            continue
        count += 1
        path = args.output / f"{plugin.id}.admin.json"
        result = service.export_snapshot(plugin.id, path)
        ok = (_print_operation("export", result) == 0) and ok
    if count == 0:
        print("export failed: no plugins with admin schema")
        return 1
    return 0 if ok else 1


def _cmd_import(args: argparse.Namespace) -> int:
    service = _admin_service(args)
    result = service.import_snapshot(args.plugin_id, args.snapshot, dry_run=args.dry_run)
    return _print_operation("import", result)


def _admin_service(args: argparse.Namespace) -> PluginAdminService:
    def send(target: str, text: str, message_type: str = "private") -> SendResult:
        return SendResult(ok=True, message=f"admin-cli noop send to {message_type}:{target}")

    state_store = PluginKVStore(args.state_root)
    context = PluginContext(send_fn=send, state_store=state_store)
    enabled_state = args.enabled_state or args.plugin_root / ".plugin_enabled.json"
    loader = PluginLoader(args.plugin_root, context, state_store=PluginStateStore(enabled_state))
    loader.load_all()
    return PluginAdminService(loader)


def _print_operation(action: str, result: PluginAdminOperation) -> int:
    status = "ok" if result.ok else "failed"
    print(f"{action} {status}: {result.message}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

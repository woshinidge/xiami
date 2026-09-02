from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from xiami_core.plugins.scaffold import create_plugin_scaffold


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    result = create_plugin_scaffold(
        args.plugin_id,
        args.plugin_root,
        name=args.name,
        command=args.command,
        kind=args.kind,
        description=args.description,
        overwrite=args.overwrite,
    )
    print(f"scaffold {'ok' if result.ok else 'failed'}: {result.plugin_id or args.plugin_id} - {result.message}")
    if result.path:
        print(result.path)
    return 0 if result.ok else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a Xiami plugin migration scaffold")
    parser.add_argument("plugin_id", help="new plugin id")
    parser.add_argument("--plugin-root", type=Path, default=Path("xiami_plugins"))
    parser.add_argument("--name", default="", help="plugin display name")
    parser.add_argument("--command", default="", help="starter command")
    parser.add_argument(
        "--kind",
        choices=("command", "event", "timer", "hybrid", "full"),
        default="command",
        help="scaffold type",
    )
    parser.add_argument("--description", default="", help="plugin description")
    parser.add_argument("--overwrite", action="store_true", help="overwrite an existing scaffold")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())

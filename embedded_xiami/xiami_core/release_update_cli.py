from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from xiami_core.release_manifest import DEFAULT_MANIFEST_NAME, DEFAULT_PLATFORM, DEFAULT_VERSION
from xiami_core.release_update import (
    check_release_update,
    format_release_update_decision,
    release_update_json,
)
from xiami_core.storage.paths import PROJECT_ROOT


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check whether a Xiami release manifest offers an update.")
    parser.add_argument(
        "manifest",
        nargs="?",
        type=Path,
        default=PROJECT_ROOT / "dist" / DEFAULT_MANIFEST_NAME,
        help="Release manifest path.",
    )
    parser.add_argument("--current-version", default=DEFAULT_VERSION)
    parser.add_argument("--platform", default=DEFAULT_PLATFORM)
    parser.add_argument("--require-signature", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        decision = check_release_update(
            args.manifest,
            current_version=args.current_version,
            platform=args.platform,
            require_signature=args.require_signature,
        )
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"release update check failed: {exc}")
        return 1

    if args.json:
        print(release_update_json(decision))
    else:
        print(format_release_update_decision(decision))
    return 0 if decision.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

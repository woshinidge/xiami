from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from xiami_core.release_manifest import DEFAULT_MANIFEST_NAME
from xiami_core.release_verify import (
    format_release_verify_report,
    release_verify_json,
    verify_release_manifest,
)
from xiami_core.storage.paths import PROJECT_ROOT


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify Xiami release/update manifest against local artifacts.")
    parser.add_argument(
        "manifest",
        nargs="?",
        type=Path,
        default=PROJECT_ROOT / "dist" / DEFAULT_MANIFEST_NAME,
        help="Release manifest path.",
    )
    parser.add_argument("--artifact-root", type=Path, default=None, help="Directory containing release artifacts.")
    parser.add_argument("--require-signature", action="store_true", help="Require every artifact to have a .sig entry.")
    parser.add_argument("--json", action="store_true", help="Print JSON report.")
    args = parser.parse_args(argv)

    try:
        report = verify_release_manifest(
            args.manifest,
            artifact_root=args.artifact_root,
            require_signatures=args.require_signature,
        )
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"release verify failed: {exc}")
        return 1

    if args.json:
        print(release_verify_json(report))
    else:
        print(format_release_verify_report(report))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

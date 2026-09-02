from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from xiami_core.release_manifest import (
    DEFAULT_CHANNEL,
    DEFAULT_MANIFEST_NAME,
    DEFAULT_PLATFORM,
    DEFAULT_PRODUCT,
    DEFAULT_VERSION,
    build_release_manifest,
    discover_release_artifacts,
    release_manifest_json,
    write_release_manifest,
)
from xiami_core.storage.paths import PROJECT_ROOT


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Xiami release/update manifest.")
    parser.add_argument("artifacts", nargs="*", type=Path, help="Release artifact files.")
    parser.add_argument("--dist", type=Path, default=PROJECT_ROOT / "dist", help="Dist directory for auto discovery.")
    parser.add_argument("--output", type=Path, default=None, help="Output manifest path.")
    parser.add_argument("--version", default=DEFAULT_VERSION)
    parser.add_argument("--channel", default=DEFAULT_CHANNEL)
    parser.add_argument("--platform", default=DEFAULT_PLATFORM)
    parser.add_argument("--product", default=DEFAULT_PRODUCT)
    parser.add_argument("--base-url", default="")
    parser.add_argument("--signature-base-url", default="")
    parser.add_argument("--signature-suffix", default=".sig")
    parser.add_argument("--signature-algorithm", default="")
    parser.add_argument("--signer", default="")
    parser.add_argument("--minimum-version", default="")
    parser.add_argument("--notes", default="")
    parser.add_argument("--json", action="store_true", help="Print generated JSON.")
    args = parser.parse_args(argv)

    artifacts = list(args.artifacts) or discover_release_artifacts(args.dist)
    if not artifacts:
        print(f"release manifest failed: no artifact found in {args.dist}")
        return 1

    manifest = build_release_manifest(
        artifacts,
        version=args.version,
        channel=args.channel,
        platform=args.platform,
        product=args.product,
        base_url=args.base_url,
        signature_base_url=args.signature_base_url,
        signature_suffix=args.signature_suffix,
        signature_algorithm=args.signature_algorithm,
        signer=args.signer,
        minimum_version=args.minimum_version,
        notes=args.notes,
    )
    output = args.output or Path(args.dist) / DEFAULT_MANIFEST_NAME
    output_path = write_release_manifest(manifest, output)
    if args.json:
        print(release_manifest_json(manifest))
    else:
        print(f"release manifest ok: {output_path} artifacts={len(manifest.artifacts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

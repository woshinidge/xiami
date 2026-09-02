from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from xiami_core.release_manifest import (
    build_release_manifest,
    discover_release_artifacts,
    release_manifest_json,
    write_release_manifest,
)
from xiami_core.release_manifest_cli import main as release_manifest_cli_main


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        dist.mkdir()
        artifact = dist / "Xiami.zip"
        payload = b"xiami release smoke artifact"
        artifact.write_bytes(payload)
        signature = dist / "Xiami.zip.sig"
        signature_payload = b"detached signature"
        signature.write_bytes(signature_payload)
        installer = dist / "XiamiSetup.exe"
        installer.write_bytes(b"installer")

        discovered = discover_release_artifacts(dist)
        if [path.name for path in discovered] != ["Xiami.zip", "XiamiSetup.exe"]:
            raise RuntimeError(f"preferred artifact discovery failed: {discovered}")

        manifest = build_release_manifest(
            [artifact],
            version="1.2.3",
            channel="stable",
            platform="windows-x64",
            base_url="https://example.invalid/releases",
            signature_base_url="https://example.invalid/signatures",
            signature_algorithm="RSA-SHA256",
            signer="xiami-ci",
            minimum_version="1.0.0",
            notes="smoke release",
            created_at="2026-01-01T00:00:00+00:00",
        )
        expected_hash = hashlib.sha256(payload).hexdigest()
        expected_signature_hash = hashlib.sha256(signature_payload).hexdigest()
        item = manifest.artifacts[0]
        if item.sha256 != expected_hash or item.size != len(payload):
            raise RuntimeError(f"artifact metadata mismatch: {item}")
        if item.url != "https://example.invalid/releases/Xiami.zip":
            raise RuntimeError(f"artifact URL mismatch: {item.url}")
        if (
            item.signature != "Xiami.zip.sig"
            or item.signature_url != "https://example.invalid/signatures/Xiami.zip.sig"
            or item.signature_sha256 != expected_signature_hash
            or item.signature_algorithm != "RSA-SHA256"
            or item.signer != "xiami-ci"
        ):
            raise RuntimeError(f"artifact signature metadata mismatch: {item}")

        output = write_release_manifest(manifest, dist / "xiami_update.json")
        data = json.loads(output.read_text(encoding="utf-8"))
        if data["version"] != "1.2.3" or data["artifacts"][0]["sha256"] != expected_hash:
            raise RuntimeError(f"manifest JSON mismatch: {data}")
        if json.loads(release_manifest_json(manifest))["product"] != "Xiami":
            raise RuntimeError("manifest JSON product mismatch")

        cli_output = dist / "cli_update.json"
        code = release_manifest_cli_main(
            [
                str(artifact),
                "--output",
                str(cli_output),
                "--version",
                "2.0.0",
            "--base-url",
            "https://example.invalid/download",
            "--signature-base-url",
            "https://example.invalid/download/signatures",
            "--signature-algorithm",
            "RSA-SHA256",
            "--signer",
            "xiami-ci",
        ]
    )
        if code != 0 or not cli_output.is_file():
            raise RuntimeError(f"release manifest CLI failed: code={code}, output={cli_output}")
        cli_data = json.loads(cli_output.read_text(encoding="utf-8"))
    if cli_data["version"] != "2.0.0" or cli_data["artifacts"][0]["url"] != "https://example.invalid/download/Xiami.zip":
        raise RuntimeError(f"release manifest CLI JSON mismatch: {cli_data}")
    if cli_data["artifacts"][0]["signature_url"] != "https://example.invalid/download/signatures/Xiami.zip.sig":
        raise RuntimeError(f"release manifest CLI signature mismatch: {cli_data}")

    print("release manifest smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

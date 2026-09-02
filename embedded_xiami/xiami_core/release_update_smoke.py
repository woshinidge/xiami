from __future__ import annotations

import contextlib
import io
import json
import tempfile
from pathlib import Path

from xiami_core.release_manifest import build_release_manifest, write_release_manifest
from xiami_core.release_update import check_release_update, compare_versions, release_update_json
from xiami_core.release_update_cli import main as release_update_cli_main


def main() -> int:
    if compare_versions("1.2.3", "1.2.2") <= 0:
        raise RuntimeError("version compare stable increment failed")
    if compare_versions("1.2.3", "1.2.3-dev") <= 0:
        raise RuntimeError("version compare prerelease failed")
    if compare_versions("1.2.3", "1.2.3") != 0:
        raise RuntimeError("version compare equality failed")

    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        dist.mkdir()
        artifact = dist / "Xiami.zip"
        artifact.write_bytes(b"xiami update artifact")
        signature = dist / "Xiami.zip.sig"
        signature.write_bytes(b"xiami update signature")
        manifest = build_release_manifest(
            [artifact],
            version="2.0.0",
            platform="windows-x64",
            base_url="https://example.invalid/releases",
            signature_base_url="https://example.invalid/signatures",
            signature_algorithm="RSA-SHA256",
            signer="xiami-ci",
            minimum_version="1.0.0",
            created_at="2026-01-01T00:00:00+00:00",
        )
        manifest_path = write_release_manifest(manifest, dist / "xiami_update.json")

        decision = check_release_update(manifest_path, current_version="1.5.0", require_signature=True)
        if not decision.ok or not decision.update_available or decision.status != "update_available":
            raise RuntimeError(f"update decision should pass: {release_update_json(decision)}")
        if decision.artifact_url != "https://example.invalid/releases/Xiami.zip":
            raise RuntimeError(f"update artifact URL mismatch: {decision}")
        if decision.signature_url != "https://example.invalid/signatures/Xiami.zip.sig":
            raise RuntimeError(f"update signature URL mismatch: {decision}")

        cli_output = io.StringIO()
        with contextlib.redirect_stdout(cli_output):
            code = release_update_cli_main([str(manifest_path), "--current-version", "1.5.0", "--require-signature", "--json"])
        cli_data = json.loads(cli_output.getvalue())
        if code != 0 or cli_data["status"] != "update_available":
            raise RuntimeError(f"release update CLI mismatch: code={code}, output={cli_output.getvalue()}")

        up_to_date = check_release_update(manifest_path, current_version="2.0.0", require_signature=True)
        if not up_to_date.ok or up_to_date.update_available or up_to_date.status != "up_to_date":
            raise RuntimeError(f"up-to-date decision mismatch: {release_update_json(up_to_date)}")

        older = check_release_update(manifest_path, current_version="2.1.0", require_signature=True)
        if not older.ok or older.update_available or older.status != "older_manifest":
            raise RuntimeError(f"older manifest decision mismatch: {release_update_json(older)}")

        platform_blocked = check_release_update(
            manifest_path,
            current_version="1.5.0",
            platform="linux-x64",
            require_signature=True,
        )
        if platform_blocked.ok or platform_blocked.status != "platform_mismatch":
            raise RuntimeError(f"platform mismatch should block: {release_update_json(platform_blocked)}")

        minimum_blocked = check_release_update(manifest_path, current_version="0.9.0", require_signature=True)
        if minimum_blocked.ok or minimum_blocked.status != "minimum_version_blocked":
            raise RuntimeError(f"minimum version should block: {release_update_json(minimum_blocked)}")

        unsigned_manifest = build_release_manifest(
            [artifact],
            version="2.0.1",
            platform="windows-x64",
            signature_suffix="",
            created_at="2026-01-01T00:00:00+00:00",
        )
        unsigned_path = write_release_manifest(unsigned_manifest, dist / "unsigned_update.json")
        unsigned = check_release_update(unsigned_path, current_version="2.0.0", require_signature=True)
        if unsigned.ok or unsigned.status != "signature_required":
            raise RuntimeError(f"signature-required decision should block: {release_update_json(unsigned)}")

    print("release update smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

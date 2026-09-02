from __future__ import annotations

import json
import contextlib
import io
import tempfile
from pathlib import Path

from xiami_core.release_manifest import build_release_manifest, write_release_manifest
from xiami_core.release_verify import release_verify_json, verify_release_manifest
from xiami_core.release_verify_cli import main as release_verify_cli_main


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        dist.mkdir()
        artifact = dist / "Xiami.zip"
        artifact.write_bytes(b"xiami release verify artifact")
        signature = dist / "Xiami.zip.sig"
        signature.write_bytes(b"xiami release verify signature")

        manifest = build_release_manifest(
            [artifact],
            version="3.0.0",
            base_url="https://example.invalid/releases",
            signature_base_url="https://example.invalid/signatures",
            signature_algorithm="RSA-SHA256",
            signer="xiami-ci",
            created_at="2026-01-01T00:00:00+00:00",
        )
        manifest_path = write_release_manifest(manifest, dist / "xiami_update.json")

        report = verify_release_manifest(manifest_path, require_signatures=True)
        if not report.ok or report.artifact_count != 1:
            raise RuntimeError(f"release verify should pass: {release_verify_json(report)}")
        report_data = json.loads(release_verify_json(report))
        if report_data["items"][0]["signature_ok"] is not True:
            raise RuntimeError(f"release verify JSON missing signature ok: {report_data}")

        cli_output = io.StringIO()
        with contextlib.redirect_stdout(cli_output):
            code = release_verify_cli_main([str(manifest_path), "--require-signature"])
        if code != 0:
            raise RuntimeError(f"release verify CLI should pass: {code}")
        if "发布清单验证：OK" not in cli_output.getvalue():
            raise RuntimeError(f"release verify CLI output mismatch: {cli_output.getvalue()}")

        artifact.write_bytes(b"tampered")
        tampered_report = verify_release_manifest(manifest_path, require_signatures=True)
        if tampered_report.ok or "sha256 mismatch" not in tampered_report.items[0].detail:
            raise RuntimeError(f"tampered artifact should fail: {release_verify_json(tampered_report)}")

        artifact.write_bytes(b"xiami release verify artifact")
        signature.unlink()
        missing_signature_report = verify_release_manifest(manifest_path, require_signatures=True)
        if missing_signature_report.ok or "signature file missing" not in missing_signature_report.items[0].signature_detail:
            raise RuntimeError(f"missing signature should fail: {release_verify_json(missing_signature_report)}")

        unsigned_manifest = build_release_manifest(
            [artifact],
            version="3.0.1",
            signature_suffix="",
            created_at="2026-01-01T00:00:00+00:00",
        )
        unsigned_manifest_path = write_release_manifest(unsigned_manifest, dist / "unsigned_update.json")
        unsigned_report = verify_release_manifest(unsigned_manifest_path)
        if not unsigned_report.ok:
            raise RuntimeError(f"unsigned manifest should pass when signatures optional: {release_verify_json(unsigned_report)}")
        strict_unsigned_report = verify_release_manifest(unsigned_manifest_path, require_signatures=True)
        if strict_unsigned_report.ok or "signature metadata missing" not in strict_unsigned_report.items[0].signature_detail:
            raise RuntimeError(f"unsigned strict manifest should fail: {release_verify_json(strict_unsigned_report)}")

    print("release verify smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

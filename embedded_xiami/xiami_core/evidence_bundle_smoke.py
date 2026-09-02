from __future__ import annotations

import json
import zipfile
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from xiami_core.testing import use_temp_xiami_home

use_temp_xiami_home()

from xiami_core.evidence_bundle import build_evidence_bundle, format_evidence_bundle_result
from xiami_core.stability_observer import STABILITY_LOG_FILE, StabilitySample
from xiami_core.storage.config import AppConfig, KernelConfig, save_config


def main() -> int:
    save_config(
        AppConfig(
            kernel=KernelConfig(
                kind="NapCat",
                http_url="http://127.0.0.1:1",
                access_token="secret-token",
            )
        )
    )
    STABILITY_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    samples = [
        StabilitySample(
            timestamp=(start + timedelta(seconds=offset)).isoformat(),
            onebot_ok=True,
            onebot_detail="online=True, good=True",
            provider_checked=True,
            provider_ok=True,
            provider_detail="provider ok",
        )
        for offset in (0, 60, 120)
    ]
    STABILITY_LOG_FILE.write_text(
        "\n".join(json.dumps(asdict(sample), ensure_ascii=False) for sample in samples),
        encoding="utf-8",
    )

    result = build_evidence_bundle(
        output_dir=Path(use_temp_xiami_home()) / "bundle",
        include_zip=True,
        include_progress=False,
        min_samples=3,
        min_duration=120,
        min_onebot_ratio=1.0,
        require_provider=True,
        min_provider_ratio=1.0,
    )
    if not result.ok or not result.evidence_ok:
        raise RuntimeError(format_evidence_bundle_result(result))

    bundle_dir = Path(result.bundle_dir)
    expected = {
        "deployment_summary.txt",
        "deployment_summary.json",
        "runtime_diagnostic.txt",
        "high_risk_gate.txt",
        "high_risk_gate.json",
        "high_risk_next.txt",
        "high_risk_next.json",
        "delivery_checklist.txt",
        "delivery_checklist.json",
        "stability_evidence.txt",
        "stability_readiness.txt",
        "stability_observation.jsonl",
        "manifest.json",
        "README.txt",
    }
    missing = [name for name in expected if not (bundle_dir / name).is_file()]
    if missing:
        raise RuntimeError(f"missing evidence files: {missing}")

    zip_path = Path(result.zip_path)
    if not zip_path.is_file():
        raise RuntimeError(f"missing evidence zip: {zip_path}")
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
    if not expected.issubset(names):
        raise RuntimeError(f"zip missing files: {sorted(expected - names)}")

    combined = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in bundle_dir.iterdir() if path.is_file())
    if "secret-token" in combined:
        raise RuntimeError("evidence bundle leaked access token")

    manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest["stability_sample_count"] != 3 or not manifest["stability_evidence_ok"]:
        raise RuntimeError(f"unexpected manifest: {manifest}")

    print("evidence bundle smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

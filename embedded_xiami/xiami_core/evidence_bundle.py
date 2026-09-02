from __future__ import annotations

import json
import re
import shutil
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from xiami_core.deployment_control import (
    build_deployment_summary,
    deployment_summary_to_dict,
    format_deployment_summary,
)
from xiami_core.delivery_checklist import (
    build_delivery_checklist,
    delivery_checklist_to_dict,
    format_delivery_checklist,
)
from xiami_core.high_risk_gate import build_high_risk_gate, format_high_risk_gate, high_risk_gate_to_dict
from xiami_core.high_risk_next import (
    build_high_risk_next_plan,
    format_high_risk_next_plan,
    high_risk_next_plan_to_dict,
)
from xiami_core.progress_report import build_progress_summary, format_progress_summary
from xiami_core.runtime_diagnostic import build_runtime_diagnostic, format_runtime_diagnostic
from xiami_core.stability_evidence import build_stability_evidence_report, format_stability_evidence_report
from xiami_core.stability_observer import STABILITY_LOG_FILE
from xiami_core.stability_readiness import build_stability_readiness, format_stability_readiness
from xiami_core.storage.paths import PROJECT_ROOT, XIAMI_HOME, ensure_runtime_dirs

EVIDENCE_HOME = XIAMI_HOME / "evidence"

_SECRET_KEYS = ("access_token", "api_key", "authorization", "password", "secret", "token")
_SECRET_TEXT_PATTERNS = (
    re.compile(r"(?i)\b(access[_-]?token|api[_-]?key|authorization|password|secret|token)\b(\s*[:=]\s*)([^\s,;]+)"),
)


@dataclass(frozen=True)
class EvidenceBundleResult:
    ok: bool
    evidence_ok: bool
    deployment_ok: bool
    bundle_dir: str
    zip_path: str
    files: tuple[str, ...]
    warnings: tuple[str, ...]


def build_evidence_bundle(
    *,
    output_dir: Path | str | None = None,
    include_zip: bool = True,
    include_progress: bool = True,
    min_samples: int = 120,
    min_duration: float = 3600.0,
    min_onebot_ratio: float = 0.99,
    require_provider: bool = False,
    min_provider_ratio: float = 0.95,
) -> EvidenceBundleResult:
    ensure_runtime_dirs()
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    bundle_dir = Path(output_dir) if output_dir else EVIDENCE_HOME / _bundle_name(generated_at)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    warnings: list[str] = []
    files: list[str] = []

    deployment = build_deployment_summary()
    _write_text(bundle_dir / "deployment_summary.txt", format_deployment_summary(deployment), files)
    _write_json(bundle_dir / "deployment_summary.json", deployment_summary_to_dict(deployment), files)

    diagnostic = build_runtime_diagnostic()
    _write_text(bundle_dir / "runtime_diagnostic.txt", "\n".join(format_runtime_diagnostic(diagnostic)), files)

    high_risk = build_high_risk_gate()
    _write_text(bundle_dir / "high_risk_gate.txt", format_high_risk_gate(high_risk), files)
    _write_json(bundle_dir / "high_risk_gate.json", high_risk_gate_to_dict(high_risk), files)

    high_risk_next = build_high_risk_next_plan()
    _write_text(bundle_dir / "high_risk_next.txt", format_high_risk_next_plan(high_risk_next), files)
    _write_json(bundle_dir / "high_risk_next.json", high_risk_next_plan_to_dict(high_risk_next), files)

    delivery = build_delivery_checklist(
        duration=min_duration,
        interval=30.0,
        include_provider=require_provider,
        min_samples=min_samples,
        min_duration=min_duration,
        min_onebot_ratio=min_onebot_ratio,
        min_provider_ratio=min_provider_ratio,
    )
    _write_text(bundle_dir / "delivery_checklist.txt", format_delivery_checklist(delivery), files)
    _write_json(bundle_dir / "delivery_checklist.json", delivery_checklist_to_dict(delivery), files)

    evidence = build_stability_evidence_report(
        min_samples=min_samples,
        min_duration=min_duration,
        min_onebot_ratio=min_onebot_ratio,
        require_provider=require_provider,
        min_provider_ratio=min_provider_ratio,
    )
    _write_text(bundle_dir / "stability_evidence.txt", format_stability_evidence_report(evidence), files)

    readiness = build_stability_readiness(
        evidence=evidence,
        min_samples=min_samples,
        min_duration=min_duration,
        min_onebot_ratio=min_onebot_ratio,
        require_provider=require_provider,
        min_provider_ratio=min_provider_ratio,
    )
    _write_text(bundle_dir / "stability_readiness.txt", format_stability_readiness(readiness), files)

    if STABILITY_LOG_FILE.exists():
        target_log = bundle_dir / "stability_observation.jsonl"
        shutil.copyfile(STABILITY_LOG_FILE, target_log)
        files.append(target_log.name)
    else:
        warnings.append(f"未发现长稳观察日志：{STABILITY_LOG_FILE}")

    if include_progress:
        summary, acceptance_hint, failed_acceptance = build_progress_summary(PROJECT_ROOT)
        progress = format_progress_summary(summary, acceptance_hint, failed_acceptance)
        _write_text(bundle_dir / "progress_report.md", progress, files)

    manifest = {
        "generated_at": generated_at,
        "project_root": str(PROJECT_ROOT),
        "xiami_home": str(XIAMI_HOME),
        "deployment_ok": deployment.ok,
        "delivery_checklist_ok": delivery.ok,
        "high_risk_ok": high_risk.ok,
        "high_risk_next": high_risk_next.next_name,
        "stability_evidence_ok": evidence.ok,
        "stability_sample_count": evidence.sample_count,
        "stability_duration_seconds": evidence.duration_seconds,
        "onebot_ratio": evidence.onebot_ratio,
        "provider_ratio": evidence.provider_ratio,
        "files": files,
        "warnings": warnings,
    }
    _write_json(bundle_dir / "manifest.json", manifest, files)
    _write_text(bundle_dir / "README.txt", _readme_text(manifest), files)

    zip_path = ""
    if include_zip:
        zip_target = bundle_dir.with_suffix(".zip")
        _zip_dir(bundle_dir, zip_target)
        zip_path = str(zip_target)

    return EvidenceBundleResult(
        ok=True,
        evidence_ok=evidence.ok,
        deployment_ok=deployment.ok,
        bundle_dir=str(bundle_dir),
        zip_path=zip_path,
        files=tuple(files),
        warnings=tuple(warnings),
    )


def format_evidence_bundle_result(result: EvidenceBundleResult) -> str:
    state = "PASS" if result.evidence_ok else "BLOCKED"
    deployment = "PASS" if result.deployment_ok else "WARN"
    lines = [
        "证据包：已导出",
        f"证据状态：{state}",
        f"部署状态：{deployment}",
        f"目录：{result.bundle_dir}",
    ]
    if result.zip_path:
        lines.append(f"压缩包：{result.zip_path}")
    lines.append("")
    lines.append("文件：")
    lines.extend(f"- {name}" for name in result.files)
    if result.warnings:
        lines.append("")
        lines.append("提醒：")
        lines.extend(f"- {item}" for item in result.warnings)
    return "\n".join(lines)


def evidence_bundle_to_dict(result: EvidenceBundleResult) -> dict[str, Any]:
    return asdict(result)


def evidence_bundle_json(result: EvidenceBundleResult) -> str:
    return json.dumps(evidence_bundle_to_dict(result), ensure_ascii=False, indent=2)


def _bundle_name(generated_at: str) -> str:
    safe = generated_at.replace(":", "").replace("+", "Z")
    return f"xiami_evidence_{safe}"


def _write_text(path: Path, text: str, files: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_redact_text(text), encoding="utf-8")
    files.append(path.name)


def _write_json(path: Path, data: Any, files: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_redact_json(data), ensure_ascii=False, indent=2), encoding="utf-8")
    files.append(path.name)


def _redact_json(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key).lower()
            if any(secret in key_text for secret in _SECRET_KEYS):
                redacted[key] = "<redacted>"
            else:
                redacted[key] = _redact_json(item)
        return redacted
    if isinstance(value, list):
        return [_redact_json(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_json(item) for item in value)
    if isinstance(value, str):
        return _redact_text(value)
    return value


def _redact_text(text: str) -> str:
    redacted = text
    for pattern in _SECRET_TEXT_PATTERNS:
        redacted = pattern.sub(r"\1\2<redacted>", redacted)
    return redacted


def _zip_dir(source_dir: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source_dir.iterdir()):
            if path.is_file():
                archive.write(path, arcname=path.name)


def _readme_text(manifest: dict[str, Any]) -> str:
    return "\n".join(
        [
            "Xiami evidence bundle",
            "",
            "This bundle contains generated status reports for deployment, runtime diagnostics,",
            "stability readiness, and stability evidence. It does not copy raw config files.",
            "",
            f"Generated at: {manifest['generated_at']}",
            f"Evidence ok: {manifest['stability_evidence_ok']}",
            f"Project root: {manifest['project_root']}",
            f"Xiami home: {manifest['xiami_home']}",
        ]
    )

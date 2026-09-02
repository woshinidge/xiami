from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from xiami_core.stability_observer import STABILITY_LOG_FILE, StabilitySample


@dataclass(frozen=True)
class StabilityEvidenceCheck:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class StabilityEvidenceReport:
    ok: bool
    log_path: str
    sample_count: int
    duration_seconds: float
    onebot_ok: int
    onebot_ratio: float
    provider_checked: int
    provider_ok: int
    provider_ratio: float
    latest_onebot_detail: str
    latest_provider_detail: str
    checks: list[StabilityEvidenceCheck]


def load_stability_samples(log_path: Path | str | None = None) -> list[StabilitySample]:
    path = Path(log_path) if log_path else STABILITY_LOG_FILE
    if not path.exists():
        return []

    samples: list[StabilitySample] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
            samples.append(_sample_from_payload(payload))
        except (TypeError, ValueError, KeyError):
            continue
    return samples


def build_stability_evidence_report(
    *,
    log_path: Path | str | None = None,
    min_samples: int = 2,
    min_duration: float = 60.0,
    min_onebot_ratio: float = 1.0,
    require_provider: bool = False,
    min_provider_ratio: float = 1.0,
) -> StabilityEvidenceReport:
    path = Path(log_path) if log_path else STABILITY_LOG_FILE
    samples = load_stability_samples(path)
    sample_count = len(samples)
    duration = _sample_duration_seconds(samples)
    onebot_ok = sum(1 for sample in samples if sample.onebot_ok)
    onebot_ratio = _ratio(onebot_ok, sample_count)
    provider_checked = sum(1 for sample in samples if sample.provider_checked)
    provider_ok = sum(1 for sample in samples if sample.provider_checked and sample.provider_ok)
    provider_ratio = _ratio(provider_ok, provider_checked)
    latest = samples[-1] if samples else None

    checks = [
        StabilityEvidenceCheck(
            name="样本数量",
            ok=sample_count >= min_samples,
            detail=f"{sample_count}/{min_samples}",
        ),
        StabilityEvidenceCheck(
            name="持续时间",
            ok=duration >= min_duration,
            detail=f"{duration:.1f}s/{min_duration:g}s",
        ),
        StabilityEvidenceCheck(
            name="OneBot 可用率",
            ok=sample_count > 0 and onebot_ratio >= min_onebot_ratio,
            detail=f"{onebot_ok}/{sample_count} ({onebot_ratio:.1%}) >= {min_onebot_ratio:.1%}",
        ),
    ]

    if require_provider:
        checks.append(
            StabilityEvidenceCheck(
                name="Provider 可用率",
                ok=provider_checked > 0 and provider_ratio >= min_provider_ratio,
                detail=f"{provider_ok}/{provider_checked} ({provider_ratio:.1%}) >= {min_provider_ratio:.1%}",
            )
        )

    return StabilityEvidenceReport(
        ok=all(check.ok for check in checks),
        log_path=str(path),
        sample_count=sample_count,
        duration_seconds=duration,
        onebot_ok=onebot_ok,
        onebot_ratio=onebot_ratio,
        provider_checked=provider_checked,
        provider_ok=provider_ok,
        provider_ratio=provider_ratio,
        latest_onebot_detail=latest.onebot_detail if latest else "无样本",
        latest_provider_detail=latest.provider_detail if latest else "无样本",
        checks=checks,
    )


def format_stability_evidence_report(report: StabilityEvidenceReport) -> str:
    lines = [
        f"长稳证据：{'PASS' if report.ok else 'BLOCKED'}",
        f"证据日志：{report.log_path}",
        f"样本：{report.sample_count}",
        f"持续：{report.duration_seconds:.1f}s",
        f"OneBot：{report.onebot_ok}/{report.sample_count} ({report.onebot_ratio:.1%})",
    ]
    if report.provider_checked:
        lines.append(
            f"Provider：{report.provider_ok}/{report.provider_checked} ({report.provider_ratio:.1%})"
        )
    else:
        lines.append("Provider：未纳入证据")
    lines.append(f"最近 OneBot：{report.latest_onebot_detail}")
    if report.provider_checked:
        lines.append(f"最近 Provider：{report.latest_provider_detail}")
    lines.append("")
    lines.append("门禁：")
    for check in report.checks:
        lines.append(f"- [{'OK' if check.ok else '待处理'}] {check.name}: {check.detail}")
    return "\n".join(lines)


def _sample_from_payload(payload: dict[str, Any]) -> StabilitySample:
    return StabilitySample(
        timestamp=str(payload["timestamp"]),
        onebot_ok=bool(payload["onebot_ok"]),
        onebot_detail=str(payload.get("onebot_detail") or ""),
        provider_checked=bool(payload.get("provider_checked", False)),
        provider_ok=bool(payload.get("provider_ok", False)),
        provider_detail=str(payload.get("provider_detail") or ""),
    )


def _sample_duration_seconds(samples: list[StabilitySample]) -> float:
    if len(samples) < 2:
        return 0.0
    timestamps = [_parse_timestamp(sample.timestamp) for sample in samples]
    timestamps = [value for value in timestamps if value is not None]
    if len(timestamps) < 2:
        return 0.0
    return max(0.0, (max(timestamps) - min(timestamps)).total_seconds())


def _parse_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _ratio(ok: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return ok / total

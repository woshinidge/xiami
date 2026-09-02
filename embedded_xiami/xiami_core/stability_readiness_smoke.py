from __future__ import annotations

from xiami_core.models import AccountStatus
from xiami_core.recovery_plan import RecoveryPlan
from xiami_core.runtime_diagnostic import RuntimeDiagnostic
from xiami_core.stability_evidence import StabilityEvidenceReport
from xiami_core.stability_readiness import build_stability_readiness, format_stability_readiness
from xiami_core.storage.config import AppConfig, KernelConfig


def main() -> int:
    passed = build_stability_readiness(
        status=AccountStatus(state="online", account="10000"),
        diagnostic=_diag(onebot=True),
        evidence=_evidence(ok=True),
    )
    text = format_stability_readiness(passed)
    if passed.phase != "evidence_passed" or "证据已通过" not in text:
        raise RuntimeError(text)

    ready = build_stability_readiness(
        status=AccountStatus(state="online", account="10000"),
        diagnostic=_diag(onebot=True),
        evidence=_evidence(ok=False),
    )
    text = format_stability_readiness(ready)
    if ready.phase != "ready_for_observation" or "可开始观察" not in text:
        raise RuntimeError(text)

    blocked = build_stability_readiness(
        status=AccountStatus(state="offline"),
        diagnostic=_diag(onebot=False),
        evidence=_evidence(ok=False),
    )
    text = format_stability_readiness(blocked)
    if blocked.phase != "blocked" or "恢复建议" not in text:
        raise RuntimeError(text)

    print("stability readiness smoke ok")
    return 0


def _diag(*, onebot: bool) -> RuntimeDiagnostic:
    return RuntimeDiagnostic(
        config=AppConfig(kernel=KernelConfig(kind="NapCat", executable="napcat.bat")),
        kernel_candidates=(),
        suggested_kernel=KernelConfig(kind="NapCat", executable="napcat.bat"),
        onebot_reachable=onebot,
        onebot_detail="ok" if onebot else "unreachable",
        configured_port_open=onebot,
        qr_candidates=(),
        napcat_config_ok=True,
        napcat_config_detail="ok",
    )


def _evidence(*, ok: bool) -> StabilityEvidenceReport:
    return StabilityEvidenceReport(
        ok=ok,
        log_path="test.jsonl",
        sample_count=120 if ok else 1,
        duration_seconds=3600.0 if ok else 0.0,
        onebot_ok=120 if ok else 0,
        onebot_ratio=1.0 if ok else 0.0,
        provider_checked=120 if ok else 0,
        provider_ok=120 if ok else 0,
        provider_ratio=1.0 if ok else 0.0,
        latest_onebot_detail="ok" if ok else "fail",
        latest_provider_detail="ok" if ok else "not checked",
        checks=[],
    )


if __name__ == "__main__":
    raise SystemExit(main())

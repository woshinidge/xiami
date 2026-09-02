from __future__ import annotations

from xiami_core.testing import use_temp_xiami_home

use_temp_xiami_home()

from xiami_core.acceptance_evidence import record_real_loop_confirmation
from xiami_core.real_acceptance_gate import (
    dumps_real_acceptance_gate,
    format_real_acceptance_gate,
    real_acceptance_gate_to_dict,
    run_real_acceptance_gate,
)
from xiami_core.runtime_diagnostic import RuntimeDiagnostic
from xiami_core.storage.config import AppConfig, KernelConfig, save_config


def main() -> int:
    save_config(AppConfig(kernel=KernelConfig(kind="Mock")))
    gate = run_real_acceptance_gate(require_migration=False)
    if gate.ok:
        raise RuntimeError("mock kernel must not pass real acceptance gate")
    if gate.phase != "mock_or_missing_kernel":
        raise RuntimeError(f"unexpected gate phase: {gate.phase}")
    text = format_real_acceptance_gate(gate)
    if "Xiami real acceptance gate: BLOCKED" not in text or "Fastest next steps" not in text:
        raise RuntimeError(text)
    if "使用推荐真实内核" not in text:
        raise RuntimeError(f"real gate should point to product kernel action: {text}")
    if "同步OneBot配置" not in text:
        raise RuntimeError(f"real gate should point to product OneBot sync action: {text}")
    data = real_acceptance_gate_to_dict(gate)
    if data["phase"] != "mock_or_missing_kernel" or data["ok"]:
        raise RuntimeError(data)
    if '"phase": "mock_or_missing_kernel"' not in dumps_real_acceptance_gate(gate):
        raise RuntimeError("json rendering missing phase")

    save_config(AppConfig(kernel=KernelConfig(kind="NapCat", http_url="http://127.0.0.1:9")))
    record_real_loop_confirmation("smoke manual real loop", source="smoke")
    runtime = RuntimeDiagnostic(
        config=AppConfig(kernel=KernelConfig(kind="NapCat", http_url="http://127.0.0.1:9")),
        kernel_candidates=(),
        suggested_kernel=None,
        onebot_reachable=False,
        onebot_detail="<smoke offline>",
        configured_port_open=False,
        qr_candidates=(),
        napcat_config_ok=True,
        napcat_config_detail="smoke config ok",
    )
    gate = run_real_acceptance_gate(require_migration=False, runtime=runtime)
    if not gate.ok:
        raise RuntimeError(format_real_acceptance_gate(gate))
    if gate.phase != "passed":
        raise RuntimeError(f"manual evidence pass must use passed phase: {gate.phase}")
    onebot = next(check for check in gate.checks if check.name == "onebot_http")
    if "smoke manual real loop" not in onebot.detail:
        raise RuntimeError(onebot.detail)

    print("real acceptance gate smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

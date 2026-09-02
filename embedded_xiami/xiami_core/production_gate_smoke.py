from __future__ import annotations

import json

from xiami_core.testing import use_temp_xiami_home

use_temp_xiami_home()

from xiami_core.production_gate import dumps_production_gate, format_production_gate, run_production_gate
from xiami_core.storage.config import AppConfig, KernelConfig, save_config


def main() -> int:
    save_config(AppConfig(kernel=KernelConfig(kind="Mock")))
    result = run_production_gate(duration=0, interval=1, include_provider=False, run_stability=False, export_bundle=False)
    if result.ok:
        raise RuntimeError("mock/offline production gate should not pass")
    if result.phase != "blocked_real_acceptance":
        raise RuntimeError(f"unexpected production gate phase: {result.phase}")

    text = format_production_gate(result)
    for expected in (
        "Xiami 产品交付 Gate：BLOCKED",
        "真实验收",
        "高风险场景",
        "长稳预检",
        "high_risk_next_cli",
        "onebot_tools_probe_cli",
        "high_risk_probe_cli",
        "high_risk_evidence_cli",
        "stability_continue_cli",
        "production_gate_cli",
    ):
        if expected not in text:
            raise RuntimeError(f"production gate text missing {expected!r}: {text}")

    payload = json.loads(dumps_production_gate(result))
    if payload["ok"] or payload["phase"] != "blocked_real_acceptance":
        raise RuntimeError(f"unexpected production gate json: {payload}")
    if "high_risk" not in payload:
        raise RuntimeError(f"missing high-risk gate payload: {payload}")
    if not payload["next_commands"]:
        raise RuntimeError(f"missing next commands: {payload}")

    print("production gate smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

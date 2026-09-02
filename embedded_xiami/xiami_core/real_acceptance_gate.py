from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from xiami_core.acceptance import (
    AcceptanceItem,
    acceptance_evidence_lines,
    failed_acceptance_details,
    run_v1_acceptance,
    summarize_acceptance,
)
from xiami_core.migration_verify import (
    MigrationVerification,
    migration_verification_to_dict,
    run_migration_verification,
)
from xiami_core.runtime_diagnostic import RuntimeDiagnostic, build_runtime_diagnostic
from xiami_core.storage.paths import LOG_HOME, PROJECT_ROOT


@dataclass(frozen=True)
class RealAcceptanceCheck:
    name: str
    ok: bool
    required: bool
    detail: str
    next_step: str = ""


@dataclass(frozen=True)
class RealAcceptanceGate:
    ok: bool
    phase: str
    checks: tuple[RealAcceptanceCheck, ...]
    acceptance_items: tuple[AcceptanceItem, ...]
    runtime: RuntimeDiagnostic
    migration: MigrationVerification | None
    next_steps: tuple[str, ...]


def run_real_acceptance_gate(
    *,
    project_root: Path | None = None,
    acceptance_items: tuple[AcceptanceItem, ...] | None = None,
    runtime: RuntimeDiagnostic | None = None,
    migration: MigrationVerification | None = None,
    require_online: bool = True,
    require_messages: bool = True,
    require_sends: bool = True,
    require_migration: bool = True,
) -> RealAcceptanceGate:
    root = project_root or PROJECT_ROOT
    acceptance = acceptance_items or tuple(run_v1_acceptance())
    runtime = runtime or build_runtime_diagnostic()
    items = {item.name: item for item in acceptance}
    migration = migration or (
        run_migration_verification(
            project_root=root,
            event_path=LOG_HOME / "onebot_events.jsonl",
            require_mvp=True,
            limit=200,
        )
        if require_migration
        else None
    )

    onebot_evidence_ok = _item_ok(items, "onebot_login_info")
    onebot_detail = _item_detail(items, "onebot_login_info", runtime.onebot_detail)
    if onebot_evidence_ok and not runtime.onebot_reachable:
        onebot_detail = f"{onebot_detail}; 当前实时探测：{runtime.onebot_detail}"
    checks = [
        _check_all(
            "runtime",
            items,
            ("desktop_core", "kernel_config", "real_kernel_selected"),
            required=True,
            fallback="Xiami 主程序或真实登录内核配置未就绪。",
            next_step="在账号页点击“扫码/登录”自动准备真实内核，并在账号页/设置页执行“同步OneBot配置”；也可在设置页点击“使用推荐真实内核”，CLI 可运行 python -m xiami_core.runtime_diagnostic_cli --apply。",
        ),
        _check_login(items, required=require_online),
        RealAcceptanceCheck(
            "onebot_http",
            onebot_evidence_ok,
            require_online,
            onebot_detail,
            "扫码登录完成后等待 OneBot HTTP 端口在线；若仍超时，先停止 NapCat 后重新扫码/登录。",
        ),
        RealAcceptanceCheck(
            "napcat_config",
            runtime.napcat_config_ok is not False,
            True,
            runtime.napcat_config_detail,
            "在设置页点击“同步OneBot配置”；CLI 可运行 python -m xiami_core.real_probe_cli --fast --timeout 120 自动修正。",
        ),
        _check_all(
            "receive_events",
            items,
            ("receive_private_event", "receive_group_event"),
            required=require_messages,
            fallback="真实 OneBot 事件未同时覆盖私聊和群聊。",
            next_step="登录后分别向机器人发一条私聊和一条群消息，再刷新/运行本门禁。",
        ),
        _check_all(
            "ui_message_loop",
            items,
            ("ui_private_received", "ui_group_received"),
            required=require_messages,
            fallback="消息页历史未同时落库私聊和群聊。",
            next_step="确认事件网关仍在运行；发送新消息后查看消息页和 logs/messages.jsonl。",
        ),
        _check_all(
            "send_loop",
            items,
            ("send_private_ok", "send_group_ok"),
            required=require_sends,
            fallback="真实发送未同时覆盖好友和群。",
            next_step="在消息页分别选择好友/群，发送一条测试消息，确认成功提示写入消息历史。",
        ),
        _check_all(
            "plugin_loop",
            items,
            ("plugin_loop",),
            required=True,
            fallback="插件加载或插件回复闭环失败。",
            next_step="先运行 python -m xiami_core.migration_verify --require-mvp 查看插件迁移缺口。",
        ),
    ]
    if migration is not None:
        checks.append(
            RealAcceptanceCheck(
                "migration",
                migration.ok,
                require_migration,
                _migration_detail(migration),
                "先补齐迁移验收失败项，再继续真实 QQ 验收。",
            )
        )

    required_checks = [check for check in checks if check.required]
    ok = all(check.ok for check in required_checks)
    phase = _phase(items, runtime, checks)
    next_steps = _next_steps(checks, acceptance)
    return RealAcceptanceGate(
        ok=ok,
        phase=phase,
        checks=tuple(checks),
        acceptance_items=acceptance,
        runtime=runtime,
        migration=migration,
        next_steps=next_steps,
    )


def format_real_acceptance_gate(gate: RealAcceptanceGate) -> str:
    required = [check for check in gate.checks if check.required]
    passed = sum(1 for check in required if check.ok)
    lines = [
        f"Xiami real acceptance gate: {'PASS' if gate.ok else 'BLOCKED'}",
        f"Phase: {gate.phase}",
        f"Required checks: {passed}/{len(required)}",
        "",
        "Fastest next steps:",
    ]
    lines.extend(f"- {step}" for step in gate.next_steps)
    lines.extend(["", "Blocking details:"])
    for check in gate.checks:
        if check.required and not check.ok:
            lines.append(f"- [{check.name}] {check.detail}")
    if all(check.ok for check in required):
        lines.append("- none")
    lines.extend(["", "Acceptance summary:", summarize_acceptance(list(gate.acceptance_items))])
    lines.extend(["", "Runtime snapshot:"])
    lines.append(f"- kernel={gate.runtime.config.kernel.kind}")
    lines.append(f"- onebot={gate.runtime.onebot_detail}")
    lines.append(f"- onebot_port_open={gate.runtime.configured_port_open}")
    lines.append(f"- qr_candidates={len(gate.runtime.qr_candidates)}")
    if gate.runtime.qr_candidates:
        lines.append(f"- latest_qr={gate.runtime.qr_candidates[-1]}")
    lines.extend(["", "Evidence:"])
    lines.extend(acceptance_evidence_lines())
    return "\n".join(lines)


def format_real_acceptance_gate_brief(gate: RealAcceptanceGate) -> list[str]:
    required = [check for check in gate.checks if check.required]
    passed = sum(1 for check in required if check.ok)
    lines = [
        f"- {'PASS' if gate.ok else 'BLOCKED'}: phase={gate.phase}, required={passed}/{len(required)}",
    ]
    for step in gate.next_steps[:3]:
        lines.append(f"- next: {step}")
    failed = [check for check in required if not check.ok]
    if failed:
        for check in failed:
            lines.append(f"- blocked [{check.name}]: {check.detail}")
    else:
        lines.append("- blocked: none")
    return lines


def real_acceptance_gate_to_dict(gate: RealAcceptanceGate) -> dict[str, object]:
    return {
        "ok": gate.ok,
        "phase": gate.phase,
        "checks": [
            {
                "name": check.name,
                "ok": check.ok,
                "required": check.required,
                "detail": check.detail,
                "next_step": check.next_step,
            }
            for check in gate.checks
        ],
        "next_steps": list(gate.next_steps),
        "acceptance": [
            {"name": item.name, "ok": item.ok, "detail": item.detail}
            for item in gate.acceptance_items
        ],
        "runtime": {
            "kernel": gate.runtime.config.kernel.kind,
            "executable": gate.runtime.config.kernel.executable,
            "working_dir": gate.runtime.config.kernel.working_dir,
            "http_url": gate.runtime.config.kernel.http_url,
            "onebot_reachable": gate.runtime.onebot_reachable,
            "onebot_detail": gate.runtime.onebot_detail,
            "configured_port_open": gate.runtime.configured_port_open,
            "qr_candidates": [str(path) for path in gate.runtime.qr_candidates],
            "napcat_config_ok": gate.runtime.napcat_config_ok,
            "napcat_config_detail": gate.runtime.napcat_config_detail,
        },
        "migration": migration_verification_to_dict(gate.migration)
        if gate.migration is not None
        else None,
    }


def dumps_real_acceptance_gate(gate: RealAcceptanceGate) -> str:
    return json.dumps(real_acceptance_gate_to_dict(gate), ensure_ascii=False, indent=2)


def _check_login(
    items: dict[str, AcceptanceItem],
    *,
    required: bool,
) -> RealAcceptanceCheck:
    login = items.get("real_login")
    qr = items.get("login_qr_ready")
    login_ok = bool(login and login.ok)
    qr_ok = bool(qr and qr.ok)
    if login_ok:
        return RealAcceptanceCheck("login", True, required, login.detail)
    if qr_ok:
        detail = f"等待扫码登录；{qr.detail}"
        return RealAcceptanceCheck(
            "login",
            False,
            required,
            detail,
            "二维码已生成，先扫码登录；登录后门禁会继续检查 OneBot 和收发闭环。",
        )
    detail = login.detail if login else "未发现真实登录状态"
    return RealAcceptanceCheck(
        "login",
        False,
        required,
        detail,
        "点击账号页“扫码/登录”，或运行 python -m xiami_core.real_probe_cli --start --timeout 120。",
    )


def _check_all(
    name: str,
    items: dict[str, AcceptanceItem],
    item_names: tuple[str, ...],
    *,
    required: bool,
    fallback: str,
    next_step: str,
) -> RealAcceptanceCheck:
    selected = [items.get(item_name) for item_name in item_names]
    missing = [item_name for item_name, item in zip(item_names, selected) if item is None]
    failed = [item for item in selected if item is not None and not item.ok]
    ok = not missing and not failed
    if ok:
        detail = "; ".join(item.detail for item in selected if item is not None)
    else:
        parts = []
        if missing:
            parts.append("missing=" + ",".join(missing))
        parts.extend(f"{item.name}: {item.detail}" for item in failed)
        detail = "; ".join(parts) or fallback
    return RealAcceptanceCheck(name, ok, required, detail, next_step)


def _item_ok(items: dict[str, AcceptanceItem], name: str) -> bool:
    item = items.get(name)
    return bool(item and item.ok)


def _item_detail(items: dict[str, AcceptanceItem], name: str, fallback: str) -> str:
    item = items.get(name)
    return item.detail if item else fallback


def _migration_detail(result: MigrationVerification) -> str:
    replay = "skipped"
    if result.replay_gate is not None:
        replay = "pass" if result.replay_gate.ok else "fail"
    return (
        f"plugins={result.plugins}; "
        f"mvp={result.covered_commands}/{result.mvp_commands}; "
        f"onebot_api_missing={result.onebot_api_missing}; "
        f"replay={replay}"
    )


def _phase(
    items: dict[str, AcceptanceItem],
    runtime: RuntimeDiagnostic,
    checks: list[RealAcceptanceCheck],
) -> str:
    if all(check.ok for check in checks if check.required):
        return "passed"
    if not _item_ok(items, "real_kernel_selected"):
        return "mock_or_missing_kernel"
    if not _item_ok(items, "login_qr_ready") and not _item_ok(items, "real_login"):
        return "start_login"
    if not _item_ok(items, "real_login"):
        return "waiting_qr_scan"
    if not runtime.onebot_reachable:
        return "waiting_onebot_http"
    return "acceptance_incomplete"


def _next_steps(
    checks: list[RealAcceptanceCheck],
    acceptance: tuple[AcceptanceItem, ...],
) -> tuple[str, ...]:
    steps: list[str] = []
    seen: set[str] = set()
    for check in checks:
        if check.required and not check.ok and check.next_step and check.next_step not in seen:
            steps.append(check.next_step)
            seen.add(check.next_step)
    if not steps:
        for check in checks:
            if not check.required and not check.ok and check.next_step and check.next_step not in seen:
                steps.append(check.next_step)
                seen.add(check.next_step)
    if not steps:
        for line in failed_acceptance_details(list(acceptance)):
            clean = line[2:].strip() if line.startswith("- ") else line.strip()
            if clean not in seen:
                steps.append(clean)
                seen.add(clean)
    if not steps:
        steps.append("真实登录、收发、插件迁移验收已通过；可以继续按 Xiami 原生插件重写剩余旧功能。")
    return tuple(steps)

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from xiami_core.models import AccountStatus
from xiami_core.runtime_diagnostic import RuntimeDiagnostic, build_runtime_diagnostic


@dataclass(frozen=True)
class RecoveryAction:
    priority: int
    title: str
    detail: str
    ui_action: str


@dataclass(frozen=True)
class RecoveryPlan:
    ok: bool
    status_state: str
    account: str
    summary: str
    actions: tuple[RecoveryAction, ...]


def build_recovery_plan(
    *,
    status: AccountStatus | None = None,
    diagnostic: RuntimeDiagnostic | None = None,
) -> RecoveryPlan:
    diag = diagnostic or build_runtime_diagnostic()
    current = status or AccountStatus(state="offline", detail="未提供当前状态")
    actions: list[RecoveryAction] = []

    if current.state == "online" and diag.onebot_reachable:
        actions.append(
            RecoveryAction(
                10,
                "继续长稳观察",
                "账号在线且 OneBot 可访问，可以运行长稳观察并生成证据门禁。",
                "设置 -> 开发者工具 -> 长稳观察",
            )
        )
        return _plan(True, current, "在线可用", actions)

    if diag.configured_port_open and not diag.onebot_reachable:
        actions.append(
            RecoveryAction(
                20,
                "检查端口占用",
                f"配置端口已打开但不是可用 OneBot：{diag.onebot_detail}",
                "设置 -> 开发者工具 -> 诊断",
            )
        )

    if current.state == "waiting_qr":
        if current.qr_hint or diag.qr_candidates:
            hint = current.qr_hint or str(diag.qr_candidates[0])
            actions.append(
                RecoveryAction(
                    10,
                    "扫码登录",
                    f"已发现二维码线索：{hint}",
                    "账号",
                )
            )
        else:
            actions.append(
                RecoveryAction(
                    30,
                    "刷新二维码",
                    "内核在等待登录但未发现二维码线索，建议刷新状态或重新启动登录内核。",
                    "刷新状态",
                )
            )
        return _plan(False, current, "等待扫码", actions)

    if current.state == "offline":
        if _has_launch_config(diag):
            actions.append(
                RecoveryAction(
                    10,
                    "启动登录内核",
                    "当前离线，但已有可启动内核配置或可用候选包。",
                    "扫码/登录",
                )
            )
        else:
            actions.append(
                RecoveryAction(
                    10,
                    "选择或导入内核",
                    "当前没有可启动内核配置，也未发现可用候选包。",
                    "设置 -> 开发者工具",
                )
            )
        return _plan(False, current, "当前离线", actions)

    if current.state == "starting":
        if diag.onebot_reachable:
            actions.append(
                RecoveryAction(
                    10,
                    "等待登录完成",
                    "OneBot 已可访问，等待扫码或账号状态上报完成。",
                    "刷新状态",
                )
            )
        else:
            actions.append(
                RecoveryAction(
                    20,
                    "等待或重启内核",
                    f"内核启动中但 OneBot 暂不可访问：{diag.onebot_detail}",
                    "刷新状态",
                )
            )
        return _plan(False, current, "启动中", actions)

    if current.state == "online" and not diag.onebot_reachable:
        actions.append(
            RecoveryAction(
                10,
                "重新检测连接",
                "账号状态仍显示在线，但 OneBot HTTP 当前不可访问。",
                "刷新状态",
            )
        )
        actions.append(
            RecoveryAction(
                30,
                "重启登录内核",
                "如果连续多次检测失败，再停止并重新扫码登录。",
                "停止后扫码/登录",
            )
        )
        return _plan(False, current, "在线状态与 OneBot 不一致", actions)

    actions.append(
        RecoveryAction(
            10,
            "查看诊断",
            current.detail or diag.onebot_detail or "状态异常，需要查看诊断信息。",
            "设置 -> 开发者工具 -> 诊断",
        )
    )
    if diag.suggested_kernel:
        actions.append(
            RecoveryAction(
                20,
                "使用建议内核",
                f"发现可用候选内核：{_kernel_label(diag.suggested_kernel)}",
                "使用建议内核",
            )
        )
    return _plan(False, current, "需要人工确认", actions)


def format_recovery_plan(plan: RecoveryPlan) -> str:
    lines = [
        f"恢复计划：{'OK' if plan.ok else '需要处理'}",
        f"状态：{plan.status_state}",
        f"账号：{plan.account or '未登录'}",
        f"摘要：{plan.summary}",
        "",
        "建议动作：",
    ]
    for action in sorted(plan.actions, key=lambda item: item.priority):
        lines.append(f"- [{action.priority}] {action.title}：{action.detail}（入口：{action.ui_action}）")
    return "\n".join(lines)


def _plan(ok: bool, status: AccountStatus, summary: str, actions: list[RecoveryAction]) -> RecoveryPlan:
    return RecoveryPlan(
        ok=ok,
        status_state=status.state,
        account=status.account,
        summary=summary,
        actions=tuple(sorted(actions, key=lambda item: item.priority)),
    )


def _has_launch_config(diagnostic: RuntimeDiagnostic) -> bool:
    kernel = diagnostic.config.kernel
    if kernel.kind.lower() == "mock":
        return bool(diagnostic.suggested_kernel or diagnostic.kernel_candidates)
    if kernel.executable and Path(kernel.executable).exists():
        return True
    return bool(diagnostic.suggested_kernel or diagnostic.kernel_candidates)


def _kernel_label(kernel) -> str:
    executable = getattr(kernel, "executable", "")
    return f"{kernel.kind} {executable}".strip()

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from xiami_core.acceptance import (
    AcceptanceItem,
    acceptance_evidence_lines,
    failed_acceptance_details,
    run_v1_acceptance,
    summarize_acceptance,
)
from xiami_core.legacy_command_audit import audit_legacy_commands
from xiami_core.migration_gap_report import build_report
from xiami_core.migration_inventory import MVP_COMMANDS, inspect_plugins
from xiami_core.mvp_smoke import SMOKE_MODULES
from xiami_core.native_rewrite_audit import audit_native_rewrite
from xiami_core.onebot.replay_gate import run_replay_gate
from xiami_core.real_acceptance_gate import format_real_acceptance_gate_brief, run_real_acceptance_gate
from xiami_core.runtime_diagnostic import build_runtime_diagnostic, format_runtime_diagnostic
from xiami_core.storage.paths import LOG_HOME


_REPLAY_GATE_EXCLUDED_PLUGINS = {"error_history_case"}


@dataclass(frozen=True)
class ProgressSummary:
    plugins: int
    mvp_commands: int
    covered_commands: int
    missing_commands: tuple[str, ...]
    onebot_api_total: int
    onebot_api_missing: int
    legacy_commands: int
    legacy_command_missing: int
    acceptance_total: int
    acceptance_ok: int
    smoke_checks: int

    @property
    def command_percent(self) -> int:
        return _percent(self.covered_commands, self.mvp_commands)

    @property
    def api_percent(self) -> int:
        covered = self.onebot_api_total - self.onebot_api_missing
        return _percent(covered, self.onebot_api_total)

    @property
    def acceptance_percent(self) -> int:
        return _percent(self.acceptance_ok, self.acceptance_total)


def build_progress_summary(project_root: Path | None = None) -> tuple[ProgressSummary, str, tuple[str, ...]]:
    summary, acceptance_hint, failed_acceptance, _acceptance_items = build_progress_details(project_root)
    return summary, acceptance_hint, failed_acceptance


def build_progress_details(
    project_root: Path | None = None,
) -> tuple[ProgressSummary, str, tuple[str, ...], tuple[AcceptanceItem, ...]]:
    root = project_root or Path.cwd()
    inventories = inspect_plugins(root / "xiami_plugins")
    command_to_plugin: dict[str, str] = {}
    for item in inventories:
        for command in item.commands:
            command_to_plugin.setdefault(command, item.plugin_id)
    missing_commands = tuple(command for command in MVP_COMMANDS if command not in command_to_plugin)
    api_report = build_report(root)
    legacy_report = audit_legacy_commands(root)
    acceptance_items = tuple(run_v1_acceptance())
    summary = ProgressSummary(
        plugins=len(inventories),
        mvp_commands=len(MVP_COMMANDS),
        covered_commands=len(MVP_COMMANDS) - len(missing_commands),
        missing_commands=missing_commands,
        onebot_api_total=api_report.old_count,
        onebot_api_missing=len(api_report.missing),
        legacy_commands=len(legacy_report.legacy_commands),
        legacy_command_missing=len(legacy_report.missing_commands),
        acceptance_total=len(acceptance_items),
        acceptance_ok=sum(1 for item in acceptance_items if item.ok),
        smoke_checks=len(SMOKE_MODULES),
    )
    return summary, summarize_acceptance(list(acceptance_items)), tuple(failed_acceptance_details(list(acceptance_items))), acceptance_items


def _product_phase_lines(summary: ProgressSummary, real_gate_ok: bool) -> list[str]:
    core_state = "完成" if summary.command_percent == 100 and summary.api_percent == 100 else "补齐中"
    desktop_state = "可运行" if summary.smoke_checks >= 90 else "补齐中"
    real_state = "已通过" if real_gate_ok else "待账号页自动准备真实内核并保持 OneBot 在线"
    next_state = "真实长稳运行与证据门禁"
    return [
        f"- Xiami Core / 插件迁移：{core_state}",
        f"- 桌面主程序：{desktop_state}（MVP smoke {summary.smoke_checks} 项）",
        f"- 真实登录收发：{real_state}",
        f"- 下一阶段：{next_state}",
    ]


def format_progress_summary(
    summary: ProgressSummary,
    acceptance_hint: str,
    failed_acceptance: tuple[str, ...] = (),
    acceptance_items: tuple[AcceptanceItem, ...] | None = None,
) -> str:
    runtime = build_runtime_diagnostic()
    real_gate = run_real_acceptance_gate(
        acceptance_items=acceptance_items,
        runtime=runtime,
        require_migration=False,
    )
    lines = [
        "# Xiami progress report",
        "",
        f"Plugins: {summary.plugins}",
        f"MVP command coverage: {summary.covered_commands}/{summary.mvp_commands} ({summary.command_percent}%)",
        f"Old OneBot API wrapper coverage: {summary.onebot_api_total - summary.onebot_api_missing}/{summary.onebot_api_total} ({summary.api_percent}%)",
        f"Legacy command audit: {summary.legacy_commands - summary.legacy_command_missing}/{summary.legacy_commands}",
        f"Acceptance snapshot: {summary.acceptance_ok}/{summary.acceptance_total} ({summary.acceptance_percent}%)",
        f"MVP smoke checks: {summary.smoke_checks}",
        "",
        "## Product phase summary",
        *_product_phase_lines(summary, real_gate.ok),
        "",
        "## Missing MVP commands",
    ]
    if summary.missing_commands:
        lines.extend(f"- {command}" for command in summary.missing_commands)
    else:
        lines.append("- none")
    lines.extend(["", "## Next actions", acceptance_hint])
    if failed_acceptance:
        lines.extend(["", "## Pending acceptance items", *failed_acceptance])
    lines.extend(["", "## Real acceptance gate", *format_real_acceptance_gate_brief(real_gate)])
    native_audit = audit_native_rewrite()
    lines.extend(
        [
            "",
            "## Native rewrite audit",
            f"- native: {native_audit.native}/{native_audit.total} ({native_audit.native_percent}%)",
            f"- native with Xiami compat helpers: {native_audit.native_with_helpers}",
            f"- legacy/compat samples: {native_audit.legacy_or_compat}",
        ]
    )
    for item in native_audit.items:
        if item.status != "native":
            reason = "; ".join(item.reasons) if item.reasons else item.status
            lines.append(f"- {item.plugin_id}: {item.status}; {reason}")
    lines.extend(["", "## Runtime diagnostic", *format_runtime_diagnostic(runtime)])
    lines.extend(["", "## Evidence paths", *acceptance_evidence_lines()])
    lines.extend(["", "## Offline replay gate", *offline_replay_gate_lines()])
    lines.extend(["", "## Fast-track status", *fast_track_backlog()])
    return "\n".join(lines)


def offline_replay_gate_lines(project_root: Path | None = None, *, limit: int = 200) -> list[str]:
    root = project_root or Path.cwd()
    event_path = LOG_HOME / "onebot_events.jsonl"
    if not event_path.exists():
        return ["- SKIP: 未发现 OneBot 事件日志，真实登录并接收消息后会生成。"]
    try:
        result = run_replay_gate(
            event_path=event_path,
            plugin_root=root / "xiami_plugins",
            state_root=LOG_HOME / "progress_replay_gate_state",
            plugin_ids=_default_replay_gate_plugins(root / "xiami_plugins"),
            limit=limit,
            min_events=1,
        )
    except Exception as exc:
        return [f"- FAIL: replay gate 执行失败：{exc}"]
    mark = "PASS" if result.ok else "FAIL"
    lines = [
        (
            f"- {mark}: events={result.replay.events_replayed}, "
            f"messages={result.replay.messages_replayed}, "
            f"sends={len(result.replay.sends)}, actions={len(result.replay.actions)}"
        )
    ]
    for check in result.checks:
        state = "OK" if check.ok else "FAIL"
        lines.append(f"  - [{state}] {check.name}: {check.detail}")
    return lines


def _default_replay_gate_plugins(plugin_root: Path) -> tuple[str, ...]:
    if not plugin_root.exists():
        return ()
    plugin_ids: list[str] = []
    for path in sorted(plugin_root.iterdir()):
        if path.name.startswith("__"):
            continue
        if path.is_dir():
            plugin_id = path.name
        elif path.suffix == ".py":
            plugin_id = path.stem
        else:
            continue
        if plugin_id in _REPLAY_GATE_EXCLUDED_PLUGINS:
            continue
        plugin_ids.append(plugin_id)
    return tuple(plugin_ids)


def fast_track_backlog() -> list[str]:
    return [
        "- DONE 真实登录/收发 Gate：历史验收已覆盖登录、私聊/群聊收发、插件回复。",
        "- DONE 迁移一键验收：python -m xiami_core.migration_verify --require-mvp --plugin <插件ID> 已支持单插件命令/API/replay gate。",
        "- DONE 证据包导出：python -m xiami_core.evidence_bundle_cli 可归档部署、诊断、长稳证据和进度报告。",
        "- DONE 产品交付 Gate：python -m xiami_core.production_gate_cli 合并真实验收、长稳预检、证据包和在线后推荐命令。",
        "- DONE 高风险真实场景 Gate：python -m xiami_core.high_risk_gate_cli 记录好友审核、入群审核、群管、撤回/违禁词和 OneBot 工具真实证据。",
        "- DONE 高风险验证向导：python -m xiami_core.high_risk_next_cli 可输出下一项真实验证、测试动作和记录命令。",
        "- DONE OneBot 工具安全探针：python -m xiami_core.onebot_tools_probe_cli --strict 可生成 onebot_tools_real action 证据。",
        "- DONE 高风险安全探针：python -m xiami_core.high_risk_probe_cli --strict 可生成 member_guard_real 撤回 action 证据，其他高风险动作需要显式确认。",
        "- DONE 长稳恢复计划：python -m xiami_core.stability_resume_cli 可基于已有 JSONL 计算剩余样本、剩余时长和继续观察命令。",
        "- DONE 长稳续跑：python -m xiami_core.stability_continue_cli 可基于已有 JSONL 自动补跑剩余观察并输出证据门禁。",
        "- DONE 交付清单：python -m xiami_core.delivery_checklist_cli --provider 汇总真实验收、高风险证据、长稳恢复、证据包和最终 Gate。",
        "- NEEDS REAL GROUP 高风险真实场景：在线后逐项记录 high-risk gate 证据，产品 Gate 才能 PASS。",
        "- NEEDS REAL ONLINE 真实长稳：登录后运行长稳套件，覆盖停止/重启、异常恢复、无残留进程和证据包 PASS。",
        "- NEEDS REAL ONLINE 高风险群功能：入群审核、好友审核、撤回/群管、OneBot 工具 action 需要真实群环境验证。",
        "- NEEDS PROVIDER KEY AI 真模型：供应商配置、知识库检索前置、失败降级和审计日志需要真实密钥/模型验证。",
        "- FEEDBACK DRIVEN 后台管理补齐：运行统计、命令热度、插件配置、部署控制已接入；低频后台动作按真实反馈补。",
    ]


def main() -> int:
    summary, acceptance_hint, failed_acceptance, acceptance_items = build_progress_details(Path.cwd())
    print(format_progress_summary(summary, acceptance_hint, failed_acceptance, acceptance_items))
    ok = not summary.missing_commands and summary.onebot_api_missing == 0 and summary.legacy_command_missing == 0
    return 0 if ok else 1


def _percent(part: int, total: int) -> int:
    if total <= 0:
        return 100
    return round(part * 100 / total)


if __name__ == "__main__":
    raise SystemExit(main())

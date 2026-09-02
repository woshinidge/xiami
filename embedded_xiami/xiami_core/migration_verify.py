from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from xiami_core.migration_gap_report import build_report
from xiami_core.migration_inventory import MVP_COMMANDS, inspect_plugins
from xiami_core.onebot.replay_gate import ReplayGateResult, run_replay_gate
from xiami_core.storage.paths import LOG_HOME, PROJECT_ROOT


_DEFAULT_EXCLUDED_REPLAY_PLUGINS = {"error_history_case"}


@dataclass(frozen=True)
class MigrationVerification:
    plugins: int
    mvp_commands: int
    covered_commands: int
    missing_commands: tuple[str, ...]
    onebot_api_total: int
    onebot_api_missing: int
    replay_gate: ReplayGateResult | None = None
    replay_skipped: str = ""
    require_mvp: bool = False
    require_replay: bool = False

    @property
    def ok(self) -> bool:
        if self.require_mvp and self.missing_commands:
            return False
        if self.onebot_api_missing:
            return False
        if self.require_replay:
            return bool(self.replay_gate and self.replay_gate.ok)
        if self.replay_gate is not None and not self.replay_gate.ok:
            return False
        return True


def run_migration_verification(
    *,
    project_root: Path | None = None,
    plugin_root: Path | None = None,
    event_path: Path | None = None,
    state_root: Path | None = None,
    plugin_ids: tuple[str, ...] = (),
    exclude_plugins: tuple[str, ...] = tuple(sorted(_DEFAULT_EXCLUDED_REPLAY_PLUGINS)),
    limit: int = 200,
    require_mvp: bool = False,
    require_replay: bool = False,
    require_private_message: bool = False,
    require_group_message: bool = False,
    require_notice: bool = False,
    require_request: bool = False,
    min_sends: int = 0,
    min_actions: int = 0,
    require_actions: tuple[str, ...] = (),
) -> MigrationVerification:
    root = project_root or PROJECT_ROOT
    plugins = plugin_root or (root / "xiami_plugins")
    inventories = inspect_plugins(plugins)
    command_to_plugin: dict[str, str] = {}
    for item in inventories:
        for command in item.commands:
            command_to_plugin.setdefault(command, item.plugin_id)
    missing_commands = tuple(command for command in MVP_COMMANDS if command not in command_to_plugin)
    api_report = build_report(root)
    event_log = event_path or (LOG_HOME / "onebot_events.jsonl")
    replay_gate: ReplayGateResult | None = None
    replay_skipped = ""
    if event_log.exists():
        selected_plugins = plugin_ids or _default_replay_plugins(plugins, exclude_plugins)
        replay_gate = run_replay_gate(
            event_path=event_log,
            plugin_root=plugins,
            state_root=state_root or (LOG_HOME / "migration_verify_replay_state"),
            plugin_ids=selected_plugins,
            limit=limit,
            min_events=1,
            min_sends=min_sends,
            min_actions=min_actions,
            require_private_message=require_private_message,
            require_group_message=require_group_message,
            require_notice=require_notice,
            require_request=require_request,
            require_actions=require_actions,
        )
    else:
        replay_skipped = f"OneBot event log not found: {event_log}"
    return MigrationVerification(
        plugins=len(inventories),
        mvp_commands=len(MVP_COMMANDS),
        covered_commands=len(MVP_COMMANDS) - len(missing_commands),
        missing_commands=missing_commands,
        onebot_api_total=api_report.old_count,
        onebot_api_missing=len(api_report.missing),
        replay_gate=replay_gate,
        replay_skipped=replay_skipped,
        require_mvp=require_mvp,
        require_replay=require_replay,
    )


def format_migration_verification(result: MigrationVerification) -> str:
    lines = [
        "# Xiami migration verification",
        "",
        f"Overall: {'PASS' if result.ok else 'FAIL'}",
        f"Plugins: {result.plugins}",
        f"MVP command coverage: {result.covered_commands}/{result.mvp_commands}",
        f"Old OneBot API missing: {result.onebot_api_missing}/{result.onebot_api_total}",
        "",
        "## Missing MVP commands",
    ]
    if result.missing_commands:
        lines.extend(f"- {command}" for command in result.missing_commands)
    else:
        lines.append("- none")
    lines.extend(["", "## Replay gate"])
    if result.replay_gate is None:
        prefix = "FAIL" if result.require_replay else "SKIP"
        lines.append(f"- {prefix}: {result.replay_skipped or 'not requested'}")
    else:
        gate = result.replay_gate
        lines.append(
            f"- {'PASS' if gate.ok else 'FAIL'}: "
            f"events={gate.replay.events_replayed}, "
            f"messages={gate.replay.messages_replayed}, "
            f"sends={len(gate.replay.sends)}, "
            f"actions={len(gate.replay.actions)}"
        )
        for check in gate.checks:
            mark = "OK" if check.ok else "FAIL"
            lines.append(f"  - [{mark}] {check.name}: {check.detail}")
    return "\n".join(lines)


def migration_verification_to_dict(result: MigrationVerification) -> dict[str, object]:
    replay: dict[str, object]
    if result.replay_gate is None:
        replay = {
            "status": "fail" if result.require_replay else "skip",
            "skipped": result.replay_skipped or "not requested",
        }
    else:
        gate = result.replay_gate
        replay = {
            "status": "pass" if gate.ok else "fail",
            "events_replayed": gate.replay.events_replayed,
            "messages_replayed": gate.replay.messages_replayed,
            "plugin_events_replayed": gate.replay.plugin_events_replayed,
            "sends": [
                {"target": item.target, "text": item.text, "message_type": item.message_type}
                for item in gate.replay.sends
            ],
            "actions": [{"action": item.action, "params": item.params} for item in gate.replay.actions],
            "checks": [
                {"name": check.name, "ok": check.ok, "detail": check.detail}
                for check in gate.checks
            ],
            "errors": list(gate.replay.errors),
        }
    return {
        "ok": result.ok,
        "plugins": result.plugins,
        "mvp_commands": {
            "covered": result.covered_commands,
            "total": result.mvp_commands,
            "missing": list(result.missing_commands),
        },
        "onebot_api": {
            "total": result.onebot_api_total,
            "missing": result.onebot_api_missing,
        },
        "requirements": {
            "require_mvp": result.require_mvp,
            "require_replay": result.require_replay,
        },
        "replay_gate": replay,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a fast Xiami legacy-plugin migration verification report.")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--plugin-root", type=Path, default=None)
    parser.add_argument("--events", type=Path, default=LOG_HOME / "onebot_events.jsonl")
    parser.add_argument("--state", type=Path, default=LOG_HOME / "migration_verify_replay_state")
    parser.add_argument("--plugin", action="append", default=[], help="Only replay against plugin id. Repeatable.")
    parser.add_argument(
        "--exclude-plugin",
        action="append",
        default=sorted(_DEFAULT_EXCLUDED_REPLAY_PLUGINS),
        help="Exclude a plugin from default replay gate. Repeatable.",
    )
    parser.add_argument("--limit", type=int, default=200, help="Replay only last N events.")
    parser.add_argument("--require-mvp", action="store_true", help="Fail if MVP command coverage is incomplete.")
    parser.add_argument("--require-replay", action="store_true", help="Fail if replay gate is skipped or fails.")
    parser.add_argument("--require-private", action="store_true", help="Require a private message in replay gate.")
    parser.add_argument("--require-group", action="store_true", help="Require a group message in replay gate.")
    parser.add_argument("--require-notice", action="store_true", help="Require a notice event in replay gate.")
    parser.add_argument("--require-request", action="store_true", help="Require a request event in replay gate.")
    parser.add_argument("--min-sends", type=int, default=0, help="Minimum captured send calls.")
    parser.add_argument("--min-actions", type=int, default=0, help="Minimum captured OneBot action calls.")
    parser.add_argument("--require-action", action="append", default=[], help="Require a captured OneBot action name.")
    parser.add_argument("--format", choices=("text", "json"), default="text", help="Output format.")
    parser.add_argument("--output", type=Path, default=None, help="Write report to a file as well as stdout.")
    args = parser.parse_args(argv)
    result = run_migration_verification(
        project_root=args.project_root,
        plugin_root=args.plugin_root,
        event_path=args.events,
        state_root=args.state,
        plugin_ids=tuple(args.plugin or ()),
        exclude_plugins=tuple(args.exclude_plugin or ()),
        limit=args.limit,
        require_mvp=args.require_mvp,
        require_replay=args.require_replay,
        require_private_message=args.require_private,
        require_group_message=args.require_group,
        require_notice=args.require_notice,
        require_request=args.require_request,
        min_sends=args.min_sends,
        min_actions=args.min_actions,
        require_actions=tuple(args.require_action or ()),
    )
    if args.format == "json":
        output = json.dumps(migration_verification_to_dict(result), ensure_ascii=False, indent=2)
    else:
        output = format_migration_verification(result)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0 if result.ok else 1


def _default_replay_plugins(plugin_root: Path, exclude_plugins: tuple[str, ...]) -> tuple[str, ...]:
    excluded = set(exclude_plugins)
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
        if plugin_id in excluded:
            continue
        plugin_ids.append(plugin_id)
    return tuple(plugin_ids)


if __name__ == "__main__":
    raise SystemExit(main())

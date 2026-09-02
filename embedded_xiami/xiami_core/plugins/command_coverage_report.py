from __future__ import annotations

import argparse
import importlib
import importlib.util
from dataclasses import dataclass
from pathlib import Path

from xiami_core.migration_inventory import PluginInventory, inspect_plugins
from xiami_core.mvp_smoke import SMOKE_MODULES


EXPLICIT_EVIDENCE = {
    "compat_echo": {"xiami_core.plugins.basic_plugins_direct_smoke"},
    "echo": {"xiami_core.plugins.basic_plugins_direct_smoke"},
    "error_history_case": {"xiami_core.plugins.basic_plugins_direct_smoke", "xiami_app.plugin_error_history_ui_smoke"},
    "onebot_tools": {
        "xiami_core.plugins.onebot_tools_smoke",
        "xiami_core.plugins.onebot_tools_alias_matrix_smoke",
    },
}

HIGH_STATE_PLUGINS = {"friend_review", "group_settings", "join_review", "knowledge", "member_guard", "quiz"}


@dataclass(frozen=True)
class PluginCommandCoverage:
    plugin_id: str
    command_count: int
    evidence_modules: tuple[str, ...]
    risk: str

    @property
    def covered(self) -> bool:
        return bool(self.evidence_modules) or self.command_count == 0


def build_command_coverage_report(
    plugin_root: Path | None = None,
    smoke_modules: tuple[str, ...] | None = None,
) -> list[PluginCommandCoverage]:
    plugin_root = plugin_root or Path.cwd() / "xiami_plugins"
    smoke_modules = smoke_modules or tuple(SMOKE_MODULES)
    plugins = inspect_plugins(plugin_root)
    return [build_plugin_coverage(item, smoke_modules) for item in plugins]


def build_plugin_coverage(item: PluginInventory, smoke_modules: tuple[str, ...]) -> PluginCommandCoverage:
    evidence = set(EXPLICIT_EVIDENCE.get(item.plugin_id, set()))
    evidence.update(_module_name_matches(item.plugin_id, smoke_modules))
    evidence.update(_module_source_mentions(item.plugin_id, smoke_modules))
    evidence = {module for module in evidence if module in smoke_modules or module.startswith("xiami_app.")}
    risk = _risk(item.plugin_id, len(item.commands), evidence)
    return PluginCommandCoverage(
        plugin_id=item.plugin_id,
        command_count=len(item.commands),
        evidence_modules=tuple(sorted(evidence)),
        risk=risk,
    )


def format_command_coverage_report(items: list[PluginCommandCoverage]) -> str:
    total = len(items)
    covered = sum(1 for item in items if item.covered)
    high_risk = [item for item in items if item.risk == "high"]
    lines = [
        "# Xiami plugin command coverage",
        f"Plugins: {total}",
        f"Covered: {covered}/{total}",
        f"High risk: {len(high_risk)}",
        "",
        "| Plugin | Commands | Risk | Evidence |",
        "| --- | ---: | --- | --- |",
    ]
    for item in sorted(items, key=lambda value: (value.risk == "high", value.command_count, value.plugin_id), reverse=True):
        evidence = ", ".join(item.evidence_modules) if item.evidence_modules else "-"
        lines.append(f"| {item.plugin_id} | {item.command_count} | {item.risk} | {evidence} |")
    return "\n".join(lines)


def _module_name_matches(plugin_id: str, smoke_modules: tuple[str, ...]) -> set[str]:
    token = plugin_id.lower()
    return {module for module in smoke_modules if token in module.lower()}


def _module_source_mentions(plugin_id: str, smoke_modules: tuple[str, ...]) -> set[str]:
    mentions: set[str] = set()
    token = plugin_id.lower()
    for module in smoke_modules:
        if module.endswith("command_coverage_report_smoke"):
            continue
        path = _module_path(module)
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            continue
        if token in text:
            mentions.add(module)
    return mentions


def _module_path(module: str) -> Path:
    try:
        spec = importlib.util.find_spec(module)
    except (ImportError, ValueError):
        return Path()
    if not spec or not spec.origin:
        return Path()
    return Path(spec.origin)


def _risk(plugin_id: str, command_count: int, evidence: set[str]) -> str:
    if not evidence and command_count:
        return "high"
    if plugin_id in HIGH_STATE_PLUGINS or command_count >= 10:
        return "medium"
    return "low"


def main() -> int:
    parser = argparse.ArgumentParser(description="Report plugin command smoke coverage.")
    parser.add_argument("--strict", action="store_true", help="Fail if any plugin with commands has no evidence module.")
    args = parser.parse_args()
    items = build_command_coverage_report()
    print(format_command_coverage_report(items))
    if args.strict:
        missing = [item.plugin_id for item in items if not item.covered]
        if missing:
            print("\nMissing command evidence: " + ", ".join(missing))
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

from pathlib import Path
import tempfile

from xiami_core.testing import use_temp_xiami_home

use_temp_xiami_home()

from xiami_core.messages import MessageRecord
from xiami_core.migration_inventory import MVP_COMMANDS
from xiami_core.migration_verify import run_migration_verification
from xiami_core.onebot.report import export_diagnostic_report
from xiami_core.onebot.stats import OneBotActionStats
from xiami_core.real_acceptance_gate import run_real_acceptance_gate


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        action_stats = OneBotActionStats(slow_threshold_ms=10)
        action_stats.record("send_group_msg", False, 15, "无法获取用户信息")
        report = export_diagnostic_report(
            plugin_diagnostics=[
                {
                    "id": "echo",
                    "name": "Echo",
                    "enabled": True,
                    "message_count": 2,
                    "message_handled_count": 1,
                    "message_unhandled_count": 1,
                    "event_count": 1,
                    "event_handled_count": 1,
                    "event_unhandled_count": 0,
                    "error_count": 2,
                    "last_error": "事件处理失败：boom-two",
                    "error_history": ["消息处理失败：boom-one", "事件处理失败：boom-two"],
                    "capabilities": ["onebot:get_login_info", "message-matchers:1"],
                    "migration_status": "Xiami 原生接入",
                }
            ],
            recent_messages=[
                MessageRecord(direction="outgoing", message_type="private", target="10001", text="hello", status="ok"),
                MessageRecord(direction="plugin", message_type="private", target="10001", text="pong", status="ok"),
            ],
            action_stats=action_stats,
            migration_verification=run_migration_verification(project_root=Path.cwd(), event_path=Path(tmp) / "missing.jsonl"),
            real_acceptance_gate=run_real_acceptance_gate(require_migration=False),
            output_dir=Path(tmp),
        )
        if not report.path.exists():
            raise RuntimeError(f"report not written: {report.path}")
        content = report.path.read_text(encoding="utf-8")
        for expected in (
            "Xiami Diagnostic Report",
            "Health Summary",
            "| echo | Echo | yes | 2 | 1/1 | 1 | 1/0 | 2 |",
            "Plugin Error History",
            "Plugin Capabilities",
            "Plugin Migration Status",
            "Xiami 原生接入",
            "onebot:get_login_info",
            "OneBot 调用统计",
            "send_group_msg",
            "无法获取用户信息",
            "Migration Verification",
            "Xiami migration verification",
            "Real Acceptance Gate",
            "Xiami real acceptance gate",
        f"MVP command coverage: {len(MVP_COMMANDS)}/{len(MVP_COMMANDS)}",
            "消息处理失败：boom-one",
            "Recent Messages",
        ):
            if expected not in content:
                raise RuntimeError(content)
    print("onebot report smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

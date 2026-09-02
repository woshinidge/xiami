from __future__ import annotations

import subprocess
import sys
import time


SMOKE_MODULES = [
    "xiami_core.kernels.hidden_launch_smoke",
    "xiami_core.kernels.qr_discovery_smoke",
    "xiami_core.kernels.stop_contract_smoke",
    "xiami_core.runtime_diagnostic_smoke",
    "xiami_core.runtime_qr_race_smoke",
    "xiami_core.real_probe_smoke",
    "xiami_core.onebot_tools_probe_smoke",
    "xiami_core.high_risk_probe_smoke",
    "xiami_core.real_acceptance_gate_smoke",
    "xiami_core.high_risk_gate_smoke",
    "xiami_core.high_risk_next_smoke",
    "xiami_core.high_risk_evidence_smoke",
    "xiami_core.delivery_checklist_smoke",
    "xiami_core.plugins.real_scene_acceptance_smoke",
    "xiami_core.release_manifest_smoke",
    "xiami_core.release_verify_smoke",
    "xiami_core.release_update_smoke",
    "xiami_core.stability_observer_smoke",
    "xiami_core.stability_evidence_smoke",
    "xiami_core.stability_readiness_smoke",
    "xiami_core.stability_suite_smoke",
    "xiami_core.stability_resume_smoke",
    "xiami_core.stability_continue_smoke",
    "xiami_core.evidence_bundle_smoke",
    "xiami_core.production_gate_smoke",
    "xiami_core.recovery_plan_smoke",
"xiami_core.deployment_control_smoke",
"xiami_core.text_clean_smoke",
"xiami_core.kernels.process_output_smoke",
"xiami_core.native_rewrite_audit_smoke",
    "xiami_core.plugins.loader_smoke",
    "xiami_core.plugins.command_hook_smoke",
    "xiami_core.plugins.compat_event_regex_smoke",
    "xiami_core.plugins.context_segments_smoke",
    "xiami_core.plugins.context_send_msg_smoke",
    "xiami_core.plugins.context_command_smoke",
    "xiami_core.plugins.context_access_smoke",
    "xiami_core.plugins.context_notify_smoke",
    "xiami_core.plugins.context_mention_smoke",
    "xiami_core.plugins.context_media_smoke",
    "xiami_core.plugins.context_args_smoke",
    "xiami_core.plugins.config_api_smoke",
    "xiami_core.plugins.state_api_smoke",
    "xiami_core.plugins.context_history_smoke",
    "xiami_core.plugins.data_api_smoke",
    "xiami_core.plugins.logging_smoke",
    "xiami_core.plugins.statistics_smoke",
    "xiami_core.plugins.admin_schema_smoke",
    "xiami_core.plugins.admin_service_smoke",
    "xiami_core.plugins.admin_builtin_plugins_smoke",
    "xiami_core.plugins.admin_schema_all_plugins_smoke",
    "xiami_core.plugins.admin_cli_smoke",
    "xiami_core.plugins.package_smoke",
    "xiami_core.plugins.package_cli_smoke",
    "xiami_core.plugins.scaffold_cli_smoke",
    "xiami_core.plugins.migration_bundle_cli_smoke",
    "xiami_core.plugins.legacy_api_smoke",
    "xiami_core.plugins.legacy_hooks_smoke",
    "xiami_core.plugins.legacy_behavior_smoke",
    "xiami_core.plugins.legacy_file_diagnostic_smoke",
    "xiami_core.plugins.legacy_file_multi_spec_smoke",
    "xiami_core.plugins.legacy_file_timer_smoke",
    "xiami_core.plugins.bindings_smoke",
    "xiami_core.plugins.cards_smoke",
    "xiami_core.plugins.checkin_smoke",
    "xiami_core.plugins.custom_replies_smoke",
    "xiami_core.plugins.group_files_smoke",
    "xiami_core.plugins.group_notice_smoke",
    "xiami_core.plugins.group_plugin_gate_smoke",
    "xiami_core.plugins.group_settings_independent_features_smoke",
    "xiami_core.plugins.help_menu_smoke",
    "xiami_core.plugins.notification_templates_smoke",
    "xiami_core.plugins.invites_smoke",
    "xiami_core.plugins.member_guard_smoke",
    "xiami_core.plugins.member_guard_recall_smoke",
    "xiami_core.plugins.member_guard_sweep_smoke",
    "xiami_core.plugins.moderation_smoke",
    "xiami_core.plugins.permissions_smoke",
    "xiami_core.plugins.compat_permissions_smoke",
    "xiami_core.plugins.friend_review_smoke",
    "xiami_core.plugins.join_review_smoke",
    "xiami_core.plugins.quiz_admin_settings_smoke",
    "xiami_core.onebot.forward_smoke",
    "xiami_core.onebot.receive_diagnostic_port_smoke",
    "xiami_core.onebot.receive_diagnostic_online_smoke",
    "xiami_core.plugins.knowledge_smoke",
    "xiami_core.plugins.ai_provider_smoke",
    "xiami_core.plugins.ai_reply_smoke",
    "xiami_core.plugins.quiz_smoke",
    "xiami_core.plugins.command_coverage_report_smoke",
    "xiami_core.plugins.basic_plugins_direct_smoke",
    "xiami_core.plugins.onebot_tools_smoke",
    "xiami_core.plugins.onebot_tools_alias_matrix_smoke",
    "xiami_core.plugins.catalog_smoke",
    "xiami_core.plugins.market_smoke",
    "xiami_core.send_probe_smoke",
    "xiami_core.kernels.external_smoke",
    "xiami_core.onebot.gateway_port_smoke",
    "xiami_core.onebot.actions_smoke",
    "xiami_core.onebot.stats_smoke",
    "xiami_core.onebot.health_smoke",
    "xiami_core.onebot.report_smoke",
    "xiami_core.onebot.replay_gate_smoke",
    "xiami_core.onebot.replay_smoke",
    "xiami_core.migration_verify_smoke",
    "xiami_core.progress_report_smoke",
]


def main() -> int:
    started = time.time()
    failures: list[tuple[str, str]] = []
    print("Xiami MVP smoke started")
    for module in SMOKE_MODULES:
        result = subprocess.run(
            [sys.executable, "-m", module],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode == 0:
            line = (result.stdout or "").strip().splitlines()
            detail = line[-1] if line else "ok"
            print(f"[OK] {module} - {detail}")
            continue
        output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
        failures.append((module, output[-2000:]))
        print(f"[FAIL] {module}")

    elapsed = time.time() - started
    if failures:
        print(f"\nXiami MVP smoke failed: {len(failures)}/{len(SMOKE_MODULES)} failed in {elapsed:.1f}s")
        for module, output in failures:
            print(f"\n--- {module} ---")
            _safe_print(output)
        return 1

    print(f"\nXiami MVP smoke ok: {len(SMOKE_MODULES)} checks in {elapsed:.1f}s")
    return 0


def _safe_print(value: str) -> None:
    try:
        print(value)
    except UnicodeEncodeError:
        sys.stdout.buffer.write((value + "\n").encode("utf-8", errors="replace"))
        sys.stdout.buffer.flush()


if __name__ == "__main__":
    raise SystemExit(main())

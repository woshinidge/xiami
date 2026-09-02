from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from xiami_core.migration_verify import (
    format_migration_verification,
    main as migration_verify_main,
    migration_verification_to_dict,
    run_migration_verification,
)


def main() -> int:
    with TemporaryDirectory() as temp:
        temp_root = Path(temp)
        current = run_migration_verification(
            project_root=Path.cwd(),
            plugin_root=Path.cwd() / "xiami_plugins",
            event_path=temp_root / "missing_events.jsonl",
            require_mvp=True,
        )
        if not current.ok or current.missing_commands or current.onebot_api_missing:
            raise RuntimeError(format_migration_verification(current))
        replay_root = temp_root / "replay"
        plugin_root = replay_root / "plugins"
        plugin_dir = plugin_root / "verify_demo"
        plugin_dir.mkdir(parents=True)
        _write_demo_plugin(plugin_dir / "plugin.py")
        events = replay_root / "events.jsonl"
        _write_events(events)
        replay = run_migration_verification(
            project_root=replay_root,
            plugin_root=plugin_root,
            event_path=events,
            state_root=replay_root / "state",
            plugin_ids=("verify_demo",),
            require_replay=True,
            require_private_message=True,
            min_sends=1,
        )
        if not replay.ok or replay.replay_gate is None:
            raise RuntimeError(format_migration_verification(replay))
        text = format_migration_verification(replay)
        if "Xiami migration verification" not in text or "Replay gate" not in text or "PASS" not in text:
            raise RuntimeError(f"migration verify format missing: {text}")
        payload = migration_verification_to_dict(replay)
        if not payload["ok"] or payload["replay_gate"]["status"] != "pass":  # type: ignore[index]
            raise RuntimeError(f"migration verify json payload invalid: {payload!r}")
        output = replay_root / "report.json"
        exit_code = migration_verify_main(
            [
                "--project-root",
                str(replay_root),
                "--plugin-root",
                str(plugin_root),
                "--events",
                str(events),
                "--state",
                str(replay_root / "cli_state"),
                "--plugin",
                "verify_demo",
                "--require-replay",
                "--require-private",
                "--min-sends",
                "1",
                "--format",
                "json",
                "--output",
                str(output),
            ]
        )
        if exit_code != 0 or not output.exists():
            raise RuntimeError("migration verify json output failed")
        saved = json.loads(output.read_text(encoding="utf-8"))
        if not saved.get("ok") or saved.get("replay_gate", {}).get("status") != "pass":
            raise RuntimeError(f"migration verify saved json invalid: {saved!r}")
    print("migration verify smoke ok")
    return 0


def _write_demo_plugin(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                'PLUGIN_ID = "verify_demo"',
                'PLUGIN_NAME = "Verify Demo"',
                "",
                "def on_message(event, ctx):",
                "    if event.text == 'ping':",
                "        ctx.reply(event, 'pong')",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_events(path: Path) -> None:
    payload = {
        "post_type": "message",
        "message_type": "private",
        "self_id": 10000,
        "user_id": 10001,
        "sender": {"user_id": 10001},
        "message": "ping",
        "raw_message": "ping",
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

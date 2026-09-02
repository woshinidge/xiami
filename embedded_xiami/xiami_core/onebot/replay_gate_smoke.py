from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from xiami_core.onebot.replay_gate import format_replay_gate_result, run_replay_gate


def main() -> int:
    with TemporaryDirectory() as temp:
        root = Path(temp)
        plugin_root = root / "plugins"
        state_root = root / "state"
        plugin_dir = plugin_root / "gate_demo"
        plugin_dir.mkdir(parents=True)
        _write_demo_plugin(plugin_dir / "plugin.py")
        events = root / "events.jsonl"
        _write_events(events)
        _enable_group_plugin(state_root, "20001", "gate_demo")

        result = run_replay_gate(
            event_path=events,
            plugin_root=plugin_root,
            state_root=state_root,
            min_events=4,
            min_sends=3,
            min_actions=1,
            require_private_message=True,
            require_group_message=True,
            require_notice=True,
            require_request=True,
            require_actions=("set_friend_add_request",),
        )
        if not result.ok:
            raise RuntimeError(format_replay_gate_result(result))
        sends = [(item.target, item.text, item.message_type) for item in result.replay.sends]
        expected_sends = [
            ("10001", "reply:ping", "private"),
            ("20001", "reply:ping", "group"),
            ("20001", "welcome:10003", "group"),
        ]
        if sends != expected_sends:
            raise RuntimeError(f"unexpected sends: {sends!r}")
        action = result.replay.actions[0]
        if action.action != "set_friend_add_request" or action.params.get("flag") != "friend-flag":
            raise RuntimeError(f"unexpected action: {action!r}")
    print("onebot replay gate smoke ok")
    return 0


def _write_demo_plugin(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                'PLUGIN_ID = "gate_demo"',
                'PLUGIN_NAME = "Replay Gate Demo"',
                "",
                "def on_message(event, ctx):",
                "    if event.text == 'ping':",
                "        ctx.reply(event, 'reply:' + event.text)",
                "",
                "def on_event(event, ctx):",
                "    if event.notice_type == 'group_increase':",
                "        ctx.send_group(event.group_id, 'welcome:' + event.user_id)",
                "    if event.request_type == 'friend':",
                "        ctx.call_action('set_friend_add_request', flag=event.raw.get('flag'), approve=True)",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_events(path: Path) -> None:
    payloads = [
        {
            "post_type": "message",
            "message_type": "private",
            "self_id": 10000,
            "user_id": 10001,
            "sender": {"user_id": 10001},
            "message": "ping",
            "raw_message": "ping",
        },
        {
            "post_type": "message",
            "message_type": "group",
            "self_id": 10000,
            "group_id": 20001,
            "user_id": 10002,
            "sender": {"user_id": 10002},
            "message": "ping",
            "raw_message": "ping",
        },
        {
            "post_type": "notice",
            "notice_type": "group_increase",
            "group_id": 20001,
            "user_id": 10003,
        },
        {
            "post_type": "request",
            "request_type": "friend",
            "user_id": 10004,
            "flag": "friend-flag",
            "comment": "hello",
        },
    ]
    path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in payloads), encoding="utf-8")


def _enable_group_plugin(state_root: Path, group_id: str, plugin_id: str) -> None:
    path = state_root / "kv" / "group_settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"plugin_enabled": {group_id: {plugin_id: True}}}
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

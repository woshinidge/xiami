from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from xiami_core.onebot.replay import format_replay_result, replay_onebot_events


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plugin_root = root / "plugins"
        _copy_plugin(plugin_root, "echo")
        _copy_plugin(plugin_root, "help_menu")
        _copy_plugin(plugin_root, "friend_review", _friend_config())
        _copy_plugin(plugin_root, "join_review", _join_config())

        events = root / "events.jsonl"
        _write_jsonl(
            events,
            [
                {
                    "post_type": "message",
                    "message_type": "private",
                    "user_id": 10001,
                    "self_id": 10000,
                    "message": "/echo replay ok",
                    "raw_message": "/echo replay ok",
                },
                {
                    "post_type": "message",
                    "message_type": "group",
                    "group_id": 20001,
                    "user_id": 10002,
                    "message": [{"type": "text", "data": {"text": "菜单"}}],
                    "raw_message": "菜单",
                },
                {
                    "post_type": "notice",
                    "notice_type": "group_increase",
                    "group_id": 20001,
                    "user_id": 10003,
                    "operator_id": 10002,
                },
                {
                    "post_type": "request",
                    "request_type": "friend",
                    "user_id": 10004,
                    "flag": "friend-flag",
                    "comment": "请同意我",
                },
                {
                    "post_type": "request",
                    "request_type": "group",
                    "sub_type": "add",
                    "group_id": 20001,
                    "user_id": 10005,
                    "flag": "group-flag",
                    "comment": "invite ok",
                },
            ],
        )
        state_root = root / "state"
        _enable_group_plugins(state_root, "20001", "echo", "help_menu", "friend_review", "join_review")
        result = replay_onebot_events(event_path=events, plugin_root=plugin_root, state_root=state_root)
        if not result.ok:
            raise RuntimeError(f"replay failed: {result.errors}")
        if result.events_read != 5 or result.messages_replayed != 2 or result.plugin_events_replayed != 5:
            raise RuntimeError(f"bad replay counts: {result}")
        combined = "\n".join(item.text for item in result.sends)
        if "replay ok" not in combined or "虾米" not in combined:
            raise RuntimeError(f"replay sends missing expected replies: {result.sends}")

        actions = [(item.action, item.params) for item in result.actions]
        if not any(action == "set_friend_add_request" and params.get("flag") == "friend-flag" for action, params in actions):
            raise RuntimeError(f"friend request action missing: {actions}")
        if not any(action == "set_group_add_request" and params.get("flag") == "group-flag" for action, params in actions):
            raise RuntimeError(f"group request action missing: {actions}")

        text = format_replay_result(result)
        if "Xiami OneBot replay" not in text or "OneBot actions" not in text or "Plugin hits" not in text:
            raise RuntimeError(f"bad replay report: {text}")
    print("onebot replay smoke ok")
    return 0


def _copy_plugin(plugin_root: Path, plugin_id: str, config: dict[str, object] | None = None) -> None:
    source = Path.cwd() / "xiami_plugins" / plugin_id
    target = plugin_root / plugin_id
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source / "plugin.py", target / "plugin.py")
    if config is not None:
        (target / "plugin_config.json").write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")


def _friend_config() -> dict[str, object]:
    return {
        "friend_review_enabled": True,
        "friend_review_mode": "manual",
        "friend_auto_approve_keywords": ["同意"],
    }


def _join_config() -> dict[str, object]:
    return {
        "join_review_enabled": True,
        "review_auto_approve_keywords": ["ok"],
    }


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def _enable_group_plugins(state_root: Path, group_id: str, *plugin_ids: str) -> None:
    path = state_root / "kv" / "group_settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"plugin_enabled": {group_id: {plugin_id: True for plugin_id in plugin_ids}}}
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

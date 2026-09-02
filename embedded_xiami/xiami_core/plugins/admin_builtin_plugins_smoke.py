from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from xiami_core.models import SendResult
from xiami_core.plugins.admin import PluginAdminService
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.kv import PluginKVStore
from xiami_core.plugins.loader import PluginLoader
from xiami_core.plugins.state import PluginStateStore


def main() -> int:
    def send(_target: str, _text: str, _message_type: str) -> SendResult:
        return SendResult(ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plugin_root = root / "plugins"
        for plugin_id in (
            "cards",
            "custom_replies",
            "join_review",
            "friend_review",
            "invites",
            "ai_reply",
            "knowledge",
        ):
            shutil.copytree(Path.cwd() / "xiami_plugins" / plugin_id, plugin_root / plugin_id)
        ctx = PluginContext(send_fn=send, state_store=PluginKVStore(root / "state"))
        loader = PluginLoader(plugin_root, ctx, state_store=PluginStateStore(root / "enabled.json"))
        plugins = loader.load_all()
        if len(plugins) != 7 or any(plugin.error for plugin in plugins):
            raise RuntimeError(f"builtin admin plugins load failed: {plugins!r}")

        service = PluginAdminService(loader)
        cards_schema = {item["id"]: item for item in service.snapshot("cards")["items"]}
        if {"cards", "used_cards", "admins"} - set(cards_schema):
            raise RuntimeError(f"cards admin schema missing: {cards_schema!r}")
        update_cards = service.set_item(
            "cards",
            "cards",
            {"TEST-CARD": {"points": 5, "note": "smoke", "used": False}},
        )
        if not update_cards.ok or update_cards.data["count"] != 1:
            raise RuntimeError(f"cards admin write failed: {update_cards!r}")
        service.set_item("cards", "admins", ["10001"])
        cards_config = json.loads((plugin_root / "cards" / "plugin_config.json").read_text(encoding="utf-8"))
        if cards_config.get("admins") != ["10001"]:
            raise RuntimeError(f"cards admin config failed: {cards_config!r}")

        replies_schema = {item["id"]: item for item in service.snapshot("custom_replies")["items"]}
        if {"custom_replies", "admins"} - set(replies_schema):
            raise RuntimeError(f"custom replies admin schema missing: {replies_schema!r}")
        update_replies = service.set_item(
            "custom_replies",
            "custom_replies",
            {"20001": {"hi": {"response": "hello", "match_type": "contains"}}},
        )
        if not update_replies.ok or update_replies.data["count"] != 1:
            raise RuntimeError(f"custom replies admin write failed: {update_replies!r}")
        service.set_item("custom_replies", "admins", ["10002"])
        replies_config = json.loads(
            (plugin_root / "custom_replies" / "plugin_config.json").read_text(encoding="utf-8")
        )
        if replies_config.get("admins") != ["10002"]:
            raise RuntimeError(f"custom replies admin config failed: {replies_config!r}")

        _assert_state_item(service, "join_review", "settings", {"20001": {"join_review_enabled": True}})
        _assert_state_item(
            service,
            "join_review",
            "records",
            {"20001": [{"action": "manual", "user_id": "10003", "reason": "smoke"}]},
        )
        _assert_config_item(plugin_root, service, "join_review", "default_enabled", True, "join_review_enabled")

        _assert_state_item(service, "friend_review", "enabled", True)
        _assert_state_item(service, "friend_review", "mode", "approve")
        _assert_state_item(service, "friend_review", "approve_keywords", ["ok"])
        _assert_state_item(
            service,
            "friend_review",
            "records",
            [{"action": "approve", "user_id": "10004", "reason": "smoke"}],
        )

        _assert_state_item(service, "invites", "settings", {"20001": {"invite_points_enabled": True}})
        _assert_state_item(
            service,
            "invites",
            "records",
            {"20001:10005": {"group_id": "20001", "user_id": "10005", "inviter_id": "10001", "points": 1}},
        )
        _assert_state_item(service, "invites", "ranks", {"20001": {"10001": {"count": 1, "points": 1}}})
        _assert_config_item(plugin_root, service, "invites", "reward_points", 2, "invite_reward_points")

        _assert_config_item(plugin_root, service, "ai_reply", "knowledge_limit", 5, "knowledge_limit")
        _assert_config_item(plugin_root, service, "ai_reply", "at_bot_enabled", False, "at_bot_enabled")

        _assert_state_item(
            service,
            "knowledge",
            "knowledge_chunks",
            [{"id": "smoke:0", "source": "smoke.md", "text": "hello", "tags": ["smoke"]}],
        )
        _assert_config_item(plugin_root, service, "knowledge", "search_limit", 4, "search_limit")
    print("builtin plugin admin schema smoke ok")
    return 0


def _assert_state_item(service: PluginAdminService, plugin_id: str, item_id: str, value: object) -> None:
    schema = {item["id"]: item for item in service.snapshot(plugin_id)["items"]}
    if item_id not in schema:
        raise RuntimeError(f"{plugin_id} admin item missing: {item_id} from {schema!r}")
    result = service.set_item(plugin_id, item_id, value)
    if not result.ok:
        raise RuntimeError(f"{plugin_id}.{item_id} state write failed: {result!r}")


def _assert_config_item(
    plugin_root: Path, service: PluginAdminService, plugin_id: str, item_id: str, value: object, config_key: str
) -> None:
    schema = {item["id"]: item for item in service.snapshot(plugin_id)["items"]}
    if item_id not in schema:
        raise RuntimeError(f"{plugin_id} admin config item missing: {item_id} from {schema!r}")
    result = service.set_item(plugin_id, item_id, value)
    if not result.ok:
        raise RuntimeError(f"{plugin_id}.{item_id} config write failed: {result!r}")
    config = json.loads((plugin_root / plugin_id / "plugin_config.json").read_text(encoding="utf-8"))
    if config.get(config_key) != value:
        raise RuntimeError(f"{plugin_id}.{config_key} config mismatch: {config!r}")


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

from pathlib import Path
import tempfile

from xiami_core.models import SendResult
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.events import plugin_event_from_onebot
from xiami_core.plugins.kv import PluginKVStore
from xiami_core.plugins.loader import PluginLoader
from xiami_core.plugins.test_support import enable_loaded_plugins_for_groups
from xiami_core.plugins.state import PluginStateStore


def main() -> int:
    sent: list[tuple[str, str, str]] = []

    def send(target: str, text: str, message_type: str) -> SendResult:
        sent.append((target, text, message_type))
        return SendResult(ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plugin_root = root / "plugins"
        for plugin_id in ("help_menu", "join_review", "invites"):
            source = Path.cwd() / "xiami_plugins" / plugin_id
            plugin_dir = plugin_root / plugin_id
            plugin_dir.mkdir(parents=True)
            (plugin_dir / "plugin.py").write_text((source / "plugin.py").read_text(encoding="utf-8"), encoding="utf-8")

        (plugin_root / "help_menu" / "plugin_config.json").write_text(
            """
{
  "notice_templates": {
    "join": "TPL_JOIN {group}/{qq}/{label}",
    "invite": "TPL_INVITE {inviter}->{qq}+{reward}/total{total}",
    "review": "TPL_REVIEW {group}/{qq}/{detail}"
  },
  "notice_switches": {
    "invite": false
  }
}
""".strip(),
            encoding="utf-8",
        )
        (plugin_root / "join_review" / "plugin_config.json").write_text(
            '{"join_review_enabled":true}',
            encoding="utf-8",
        )
        (plugin_root / "invites" / "plugin_config.json").write_text(
            '{"invite_reward_points":3}',
            encoding="utf-8",
        )

        ctx = PluginContext(send_fn=send, state_store=PluginKVStore(root / "state"))
        loader = PluginLoader(plugin_root, ctx, state_store=PluginStateStore(root / "enabled.json"))
        plugins = loader.load_all()
        enable_loaded_plugins_for_groups(ctx, plugins)
        if len(plugins) != 3 or any(plugin.error for plugin in plugins):
            raise RuntimeError(f"notification template plugin load failed: {plugins}")

        loader.dispatch_event(
            plugin_event_from_onebot(
                {
                    "post_type": "notice",
                    "notice_type": "group_increase",
                    "group_id": 20001,
                    "user_id": 10002,
                    "operator_id": 10001,
                }
            )
        )
        texts = [item[1] for item in sent]
        if "TPL_JOIN 20001/10002/入群通知" not in texts:
            raise RuntimeError(f"join template did not render: {texts}")
        if "TPL_INVITE 10001->10002+3/total3" in texts:
            raise RuntimeError(f"disabled invite template still rendered: {texts}")

        loader.dispatch_event(
            plugin_event_from_onebot(
                {
                    "post_type": "request",
                    "request_type": "group",
                    "sub_type": "add",
                    "group_id": 20001,
                    "user_id": 10003,
                    "flag": "flag-manual",
                    "comment": "need review",
                }
            )
        )
        texts = [item[1] for item in sent]
        if "TPL_REVIEW 20001/10003/need review" not in texts:
            raise RuntimeError(f"review template did not render: {texts}")

    print("notification templates smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

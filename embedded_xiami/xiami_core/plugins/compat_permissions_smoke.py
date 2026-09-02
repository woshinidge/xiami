from __future__ import annotations

import tempfile
from pathlib import Path

from xiami_core.models import SendResult, XiamiMessage
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.loader import PluginLoader
from xiami_core.plugins.state import PluginStateStore
from xiami_core.plugins.test_support import enable_loaded_plugins_for_groups


def main() -> int:
    sent: list[tuple[str, str, str]] = []

    def send(target: str, text: str, message_type: str) -> SendResult:
        sent.append((target, text, message_type))
        return SendResult(ok=True, message_id=str(len(sent)))

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plugin_root = root / "plugins"
        plugin_dir = plugin_root / "perm_case"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.py").write_text(
            "\n".join(
                [
                    "from xiami_core.plugins.compat import on_command",
                    "PLUGIN_CONFIG = {'owners': ['10001'], 'admins': ['10002']}",
                    "MATCHERS = []",
                    "@on_command('/owner', owner_only=True)",
                    "def owner_cmd(event, ctx, session):",
                    "    ctx.reply(event, 'owner:' + session.argument)",
                    "@on_command('/admin', admin_only=True, only_group=True)",
                    "def admin_cmd(event, ctx, session):",
                    "    ctx.reply(event, 'admin:' + session.group_id)",
                    "MATCHERS.extend([owner_cmd, admin_cmd])",
                ]
            ),
            encoding="utf-8",
        )

        ctx = PluginContext(send_fn=send)
        loader = PluginLoader(plugin_root, ctx, state_store=PluginStateStore(root / "state.json"))
        plugins = loader.load_all()
        enable_loaded_plugins_for_groups(ctx, plugins)
        loader.dispatch_message(XiamiMessage(message_type="private", sender="99999", text="/owner no"))
        loader.dispatch_message(XiamiMessage(message_type="private", sender="10001", text="/owner ok"))
        loader.dispatch_message(XiamiMessage(message_type="private", sender="10002", text="/admin no"))
        loader.dispatch_message(XiamiMessage(message_type="group", sender="10002", target="20001", text="/admin yes"))

        expected = [("10001", "owner:ok", "private"), ("20001", "admin:20001", "group")]
        if sent != expected:
            raise RuntimeError(f"permission compat failed: {sent}")

    print("plugin compat permissions smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

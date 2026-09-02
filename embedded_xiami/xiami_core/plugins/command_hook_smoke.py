from __future__ import annotations

from pathlib import Path
import tempfile

from xiami_core.models import SendResult, XiamiMessage
from xiami_core.plugins.context import PluginContext
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
        plugin_dir = plugin_root / "legacy_command_hook"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.py").write_text(
            "\n".join(
                [
                    "from xiami_core.plugins.compat import on_command_hook",
                    "PLUGIN_ID = 'legacy_command_hook'",
                    "PLUGIN_NAME = '旧命令 Hook'",
                    "COMMAND_HOOKS = []",
                    "",
                    "@on_command_hook('旧 command 插件')",
                    "def handle_command(session, ctx):",
                    "    if session.message == '旧命令':",
                    "        return {'handled': True, 'message': f'旧命令OK:{session.group_id}:{session.user_id}'}",
                    "    return {'handled': False}",
                    "",
                    "COMMAND_HOOKS.append(handle_command)",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        ctx = PluginContext(send_fn=send, state_store=PluginKVStore(root / "state"))
        loader = PluginLoader(plugin_root, ctx, state_store=PluginStateStore(root / "enabled.json"))
        plugins = loader.load_all()
        enable_loaded_plugins_for_groups(ctx, plugins)
        if not plugins or plugins[0].error:
            raise RuntimeError(f"command hook plugin load failed: {plugins}")

        loader.dispatch_message(XiamiMessage(message_type="group", sender="10001", target="20001", text="旧命令"))
        loader.dispatch_message(XiamiMessage(message_type="group", sender="10001", target="20001", text="未命中"))

        if sent != [("20001", "旧命令OK:20001:10001", "group")]:
            raise RuntimeError(f"unexpected command hook replies: {sent!r}")

        diagnostic = loader.diagnostics()[0]
        if diagnostic.get("message_handled_count") != 1 or diagnostic.get("message_unhandled_count") != 1:
            raise RuntimeError(f"command hook counts wrong: {diagnostic!r}")
        capabilities = diagnostic.get("capabilities") or []
        commands = diagnostic.get("commands") or []
        if "legacy-command-hooks:1" not in capabilities:
            raise RuntimeError(f"command hook capability missing: {diagnostic!r}")
        if not any("旧 command 插件" in item for item in commands):
            raise RuntimeError(f"command hook command label missing: {diagnostic!r}")
        if diagnostic.get("migration_status") != "旧插件兼容接入":
            raise RuntimeError(f"command hook migration status missing: {diagnostic!r}")

    print("command_hook_smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

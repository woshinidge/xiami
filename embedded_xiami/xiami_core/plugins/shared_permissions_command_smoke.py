from __future__ import annotations

import tempfile
from pathlib import Path

from xiami_core.models import SendResult, XiamiMessage
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.group_settings import GroupSettingService
from xiami_core.plugins.kv import PluginKVStore
from xiami_core.plugins.loader import PluginLoader
from xiami_core.plugins.state import PluginStateStore


def main() -> int:
    sent: list[tuple[str, str, str]] = []

    def send(target: str, text: str, message_type: str) -> SendResult:
        sent.append((target, text, message_type))
        return SendResult(ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plugin_root = root / "plugins"
        for plugin_id in ("permissions", "group_settings", "invites", "join_review"):
            source = Path.cwd() / "xiami_plugins" / plugin_id
            plugin_dir = plugin_root / plugin_id
            plugin_dir.mkdir(parents=True)
            (plugin_dir / "plugin.py").write_text((source / "plugin.py").read_text(encoding="utf-8"), encoding="utf-8")
            if plugin_id == "permissions":
                config = '{"owners":["10001"],"admins":[]}'
            else:
                config = "{}"
            (plugin_dir / "plugin_config.json").write_text(config, encoding="utf-8")

        ctx = PluginContext(send_fn=send, state_store=PluginKVStore(root / "state"))
        loader = PluginLoader(plugin_root, ctx, state_store=PluginStateStore(root / "enabled.json"))
        plugins = loader.load_all()
        if len(plugins) != 4 or any(plugin.error for plugin in plugins):
            raise RuntimeError(f"shared permission plugins load failed: {plugins}")
        settings = GroupSettingService(ctx)
        for plugin_id in ("permissions", "invites", "join_review"):
            settings.set_plugin_enabled("20001", plugin_id, True)

        def msg(text: str, sender: str = "10001") -> XiamiMessage:
            return XiamiMessage(message_type="group", sender=sender, target="20001", text=text)

        loader.dispatch_message(msg("开启邀请积分"))
        loader.dispatch_message(msg("开启入群审核"))
        settings.set_plugin_enabled("20001", "invites", False)
        settings.set_plugin_enabled("20001", "group_settings", True)
        loader.dispatch_message(msg("开启 答题"))
        loader.dispatch_message(msg("关闭邀请积分", sender="99999"))

        texts = [item[1] for item in sent]
        if texts.count("已开启本群邀请积分。") != 1:
            raise RuntimeError(f"invite command should reply once: {texts}")
        if texts.count("本群入群审核已开启。") != 1:
            raise RuntimeError(f"join review command should reply once: {texts}")
        if "已开启答题。" not in texts:
            raise RuntimeError(f"group settings did not accept shared owner: {texts}")
        if texts.count("权限不足，需要管理员。") != 1:
            raise RuntimeError(f"non-admin denial should reply once: {texts}")

    print("shared_permissions_command_smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

from pathlib import Path
import tempfile

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
        source = Path.cwd() / "xiami_plugins" / "help_menu"
        plugin_root = root / "plugins"
        plugin_dir = plugin_root / "help_menu"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.py").write_text((source / "plugin.py").read_text(encoding="utf-8"), encoding="utf-8")
        (plugin_dir / "plugin_config.json").write_text('{"admins":["10001"]}', encoding="utf-8")

        ctx = PluginContext(send_fn=send, state_store=PluginKVStore(root / "state"))
        loader = PluginLoader(plugin_root, ctx, state_store=PluginStateStore(root / "enabled.json"))
        plugins = loader.load_all()
        if not plugins or plugins[0].error:
            raise RuntimeError(f"help_menu plugin load failed: {plugins}")
        GroupSettingService(ctx).set_plugin_enabled("20001", "help_menu", True)

        loader.dispatch_message(
            XiamiMessage(message_type="group", sender="10002", target="20001", text="菜单")
        )
        loader.dispatch_message(
            XiamiMessage(message_type="group", sender="10001", target="20001", text="帮助")
        )
        loader.dispatch_message(
            XiamiMessage(message_type="group", sender="99999", target="20001", text="设置菜单 X|Y")
        )
        loader.dispatch_message(
            XiamiMessage(message_type="group", sender="10001", target="20001", text="管理员菜单")
        )
        loader.dispatch_message(
            XiamiMessage(message_type="group", sender="10001", target="20001", text="设置菜单 自助菜单|答题|绑定 区服 账号")
        )
        loader.dispatch_message(
            XiamiMessage(message_type="group", sender="10002", target="20001", text="菜单")
        )
        loader.dispatch_message(
            XiamiMessage(message_type="group", sender="10001", target="20001", text="设置管理菜单 管理菜单|通知设置|设置通知 invite 关")
        )
        loader.dispatch_message(
            XiamiMessage(message_type="group", sender="10001", target="20001", text="管理员菜单")
        )
        loader.dispatch_message(
            XiamiMessage(message_type="group", sender="10001", target="20001", text="通知设置")
        )
        loader.dispatch_message(
            XiamiMessage(message_type="group", sender="10001", target="20001", text="设置通知 invite 关")
        )
        loader.dispatch_message(
            XiamiMessage(message_type="group", sender="10001", target="20001", text="通知模板 invite")
        )
        loader.dispatch_message(
            XiamiMessage(message_type="group", sender="10001", target="20001", text="设置通知模板 invite 邀请人{inviter}奖励{reward}")
        )
        loader.dispatch_message(
            XiamiMessage(message_type="group", sender="10001", target="20001", text="通知模板 invite")
        )
        loader.dispatch_message(
            XiamiMessage(message_type="group", sender="10001", target="20001", text="重置通知模板 invite")
        )
        loader.dispatch_message(
            XiamiMessage(message_type="group", sender="10001", target="20001", text="重置菜单 全部")
        )

        texts = [item[1] for item in sent]
        if not any("虾米机器人命令" in item and "知识搜索" in item for item in texts):
            raise AssertionError(texts)
        if "管理员命令" in texts[0]:
            raise AssertionError(texts)
        if "管理员命令" not in texts[1] or "知识导入" not in texts[1]:
            raise AssertionError(texts)
        if "权限不足，需要管理员。" not in texts:
            raise AssertionError(texts)
        if not any("管理员命令" in item and "知识导入" in item for item in texts):
            raise AssertionError(texts)
        if "普通菜单已保存：3 行。" not in texts:
            raise AssertionError(texts)
        if "自助菜单\n答题\n绑定 区服 账号" not in texts:
            raise AssertionError(texts)
        if "管理员菜单已保存：3 行。" not in texts:
            raise AssertionError(texts)
        if "管理菜单\n通知设置\n设置通知 invite 关" not in texts:
            raise AssertionError(texts)
        if not any("通知开关：" in item and "邀请积分(invite)：开启" in item for item in texts):
            raise AssertionError(texts)
        if "邀请积分通知已关闭。" not in texts:
            raise AssertionError(texts)
        if not any("邀请积分(invite)：\n邀请人{inviter}奖励{reward}" in item for item in texts):
            raise AssertionError(texts)
        if "邀请积分通知模板已恢复默认。" not in texts:
            raise AssertionError(texts)
        if "普通菜单和管理员菜单已恢复默认。" not in texts:
            raise AssertionError(texts)

        assert plugins[0].context is not None
        plugins[0].context.config["menu_lines"] = ["自定义菜单", "测试项"]
        sent.clear()
        loader.dispatch_message(
            XiamiMessage(message_type="group", sender="10002", target="20001", text="菜单")
        )
        if not sent or sent[-1][1] != "自定义菜单\n测试项":
            raise AssertionError(sent)

        print("help_menu_smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

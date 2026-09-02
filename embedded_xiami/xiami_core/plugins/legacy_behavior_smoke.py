from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from xiami_core.models import SendResult, XiamiMessage
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.group_settings import GroupSettingService
from xiami_core.plugins.kv import PluginKVStore
from xiami_core.plugins.loader import PluginLoader
from xiami_core.plugins.points import PointsService
from xiami_core.plugins.state import PluginStateStore


ADMIN = "10001"
USER = "10002"
GROUP = "20001"


def _install_plugin(plugin_root: Path, plugin_id: str, config: dict[str, object] | None = None) -> None:
    source = Path.cwd() / "xiami_plugins" / plugin_id / "plugin.py"
    plugin_dir = plugin_root / plugin_id
    plugin_dir.mkdir(parents=True)
    shutil.copyfile(source, plugin_dir / "plugin.py")
    if config is not None:
        (plugin_dir / "plugin_config.json").write_text(
            json.dumps(config, ensure_ascii=False),
            encoding="utf-8",
        )


def _group(sender: str, text: str) -> XiamiMessage:
    return XiamiMessage(message_type="group", sender=sender, target=GROUP, text=text)


def _must_contain(sent: list[tuple[str, str, str]], *needles: str) -> None:
    combined = "\n".join(text for _target, text, _message_type in sent)
    missing = [needle for needle in needles if needle not in combined]
    if missing:
        raise RuntimeError(f"missing replies {missing}: {combined}")


def main() -> int:
    sent: list[tuple[str, str, str]] = []

    def send(target: str, text: str, message_type: str) -> SendResult:
        sent.append((target, text, message_type))
        return SendResult(ok=True, detail="ok")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plugin_root = root / "plugins"
        admin_config = {"admins": [ADMIN], "owners": [ADMIN]}
        _install_plugin(plugin_root, "permissions", admin_config)
        _install_plugin(plugin_root, "cards", admin_config)
        _install_plugin(plugin_root, "custom_replies", admin_config)
        _install_plugin(plugin_root, "knowledge", {**admin_config, "search_limit": 2})

        ctx = PluginContext(send_fn=send, state_store=PluginKVStore(root / "state"))
        loader = PluginLoader(plugin_root, ctx, state_store=PluginStateStore(root / "enabled.json"))
        plugins = loader.load_all()
        errors = [plugin for plugin in plugins if plugin.error]
        if len(plugins) != 4 or errors:
            raise RuntimeError(f"legacy behavior plugins failed to load: {plugins}")

        settings = GroupSettingService(ctx)
        for plugin_id in ("permissions", "cards", "custom_replies", "knowledge"):
            settings.set_plugin_enabled(GROUP, plugin_id, True)
        PointsService(ctx).set_points(GROUP, USER, 100)
        loader.dispatch_message(_group(ADMIN, f"加管理员 {USER}"))
        loader.dispatch_message(_group(ADMIN, "导入卡密 5 CARD-A CARD-B"))
        loader.dispatch_message(_group(USER, "兑换卡密 CARD-A"))
        loader.dispatch_message(_group(ADMIN, "加精确回答 旧插件验证=新Xiami已接入"))
        loader.dispatch_message(_group(USER, "旧插件验证"))
        loader.dispatch_message(_group(ADMIN, "知识添加 Xiami|Xiami 主程序加载旧机器人插件，并通过 OneBot 收发 QQ 消息。|迁移"))
        loader.dispatch_message(_group(USER, "知识搜索 OneBot"))

        _must_contain(
            sent,
            "已添加本群管理员",
            "已导入",
            "兑换成功",
            "新Xiami已接入",
            "Xiami 主程序加载旧机器人插件",
        )

        diagnostics = {item["id"]: item for item in loader.diagnostics()}
        for plugin_id in ("permissions", "cards", "custom_replies", "knowledge"):
            item = diagnostics[plugin_id]
            if item["message_handled_count"] < 1:
                raise RuntimeError(f"{plugin_id} did not handle any legacy behavior message: {item}")
            if item["error_count"]:
                raise RuntimeError(f"{plugin_id} recorded errors: {item}")

    print("legacy behavior smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

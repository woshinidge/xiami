from __future__ import annotations

from pathlib import Path
import tempfile

from xiami_core.models import SendResult, XiamiMessage
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.group_settings import GroupSettingService
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
        source = Path.cwd() / "xiami_plugins" / "custom_replies"
        plugin_root = root / "plugins"
        plugin_dir = plugin_root / "custom_replies"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.py").write_text((source / "plugin.py").read_text(encoding="utf-8"), encoding="utf-8")
        (plugin_dir / "plugin_config.json").write_text('{"admins":["10001"]}', encoding="utf-8")

        ctx = PluginContext(send_fn=send, state_store=PluginKVStore(root / "state"))
        loader = PluginLoader(plugin_root, ctx, state_store=PluginStateStore(root / "enabled.json"))
        plugins = loader.load_all()
        enable_loaded_plugins_for_groups(ctx, plugins, "20001", "20002")
        if not plugins or plugins[0].error:
            raise RuntimeError(f"custom_replies plugin load failed: {plugins}")

        def msg(sender: str, text: str, group_id: str = "20001") -> XiamiMessage:
            return XiamiMessage(message_type="group", sender=sender, target=group_id, text=text)

        loader.dispatch_message(msg("99999", "加回答 你好=你好，{qq}"))
        loader.dispatch_message(msg("10001", "加回答 你好=你好，{qq}"))
        loader.dispatch_message(msg("10002", "大家你好"))
        loader.dispatch_message(msg("10001", "加精确回答 开门=芝麻开门"))
        loader.dispatch_message(msg("10002", "请开门"))
        loader.dispatch_message(msg("10002", "开门"))
        loader.dispatch_message(msg("10001", "批量加回答 精确:天王盖地虎=宝塔镇河妖\n颜色=蓝色"))
        loader.dispatch_message(msg("10002", "天王盖地虎"))
        loader.dispatch_message(msg("10002", "今天什么颜色"))
        loader.dispatch_message(msg("10001", "加前缀回答 早上=早上好"))
        loader.dispatch_message(msg("10002", "早上大家"))
        loader.dispatch_message(msg("10001", "加后缀回答 晚安=好梦"))
        loader.dispatch_message(msg("10002", "大家晚安"))
        loader.dispatch_message(msg("10001", "加正则回答 ^查(.+)=查询：{1}"))
        loader.dispatch_message(msg("10002", "查天气"))
        loader.dispatch_message(msg("10001", "关闭回答 颜色"))
        loader.dispatch_message(msg("10002", "今天什么颜色"))
        loader.dispatch_message(msg("10001", "开启回答 颜色"))
        loader.dispatch_message(msg("10002", "今天什么颜色"))
        loader.dispatch_message(msg("10001", "导出回答 颜色"))
        loader.dispatch_message(msg("10002", "回答列表 颜色"))
        GroupSettingService(ctx).set_enabled("20001", "custom_replies_enabled", False)
        loader.dispatch_message(msg("10002", "大家你好"))
        loader.dispatch_message(msg("10001", "加回答 你好=你好，{qq}", "20002"))
        loader.dispatch_message(msg("10002", "大家你好", "20002"))
        GroupSettingService(ctx).set_enabled("20001", "custom_replies_enabled", True)
        loader.dispatch_message(msg("10001", "删回答 你好"))
        loader.dispatch_message(msg("10002", "大家你好"))
        loader.dispatch_message(msg("10001", "清空回答"))
        loader.dispatch_message(msg("10002", "开门"))
        loader.dispatch_message(msg("10002", "回答列表"))

    texts = [item[1] for item in sent]
    if "权限不足" not in texts[0]:
        raise AssertionError(texts)
    for item in (
        "已添加自定义回答。",
        "已添加精确自定义回答。",
        "已添加前缀自定义回答。",
        "已添加后缀自定义回答。",
        "已添加正则自定义回答。",
        "已导入自定义回答：2 条。",
        "已停用自定义回答：1 条。",
        "已启用自定义回答：1 条。",
        "宝塔镇河妖",
        "早上好",
        "好梦",
        "查询：天气",
        "蓝色",
        "已删除自定义回答：1 条。",
        "已清空本群自定义回答：6 条。",
        "本群暂无自定义回答。",
    ):
        if item not in texts and not any(item in text for text in texts):
            raise AssertionError(texts)
    if not any(item == "你好，10002" for item in texts):
        raise AssertionError(texts)
    if texts.count("芝麻开门") != 1:
        raise AssertionError(texts)
    if not any("本群自定义回答（筛选：颜色）" in item and "颜色" in item and "你好" not in item for item in texts):
        raise AssertionError(texts)
    if not any("自定义回答导出：" in item and "颜色=蓝色" in item for item in texts):
        raise AssertionError(texts)
    if texts.count("你好，10002") != 2:
        raise AssertionError(texts)
    if ("20002", "你好，10002", "group") not in sent:
        raise AssertionError(sent)
    color_positions = [idx for idx, item in enumerate(texts) if item == "蓝色"]
    if len(color_positions) != 2 or not any("已停用自定义回答：1 条。" in item for item in texts[color_positions[0]:color_positions[-1]]):
        raise AssertionError(texts)
    if texts[-2] == "芝麻开门":
        raise AssertionError(texts)

    print("custom_replies_smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

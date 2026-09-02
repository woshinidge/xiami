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
        source = Path.cwd() / "xiami_plugins" / "quiz"
        plugin_root = root / "plugins"
        plugin_dir = plugin_root / "quiz"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.py").write_text((source / "plugin.py").read_text(encoding="utf-8"), encoding="utf-8")
        (plugin_dir / "plugin_config.json").write_text('{"admins":["10001"],"quiz_reward_points":3}', encoding="utf-8")

        ctx = PluginContext(send_fn=send, state_store=PluginKVStore(root / "state"))
        loader = PluginLoader(plugin_root, ctx, state_store=PluginStateStore(root / "enabled.json"))
        plugins = loader.load_all()
        enable_loaded_plugins_for_groups(ctx, plugins)
        if not plugins or plugins[0].error:
            raise RuntimeError(f"quiz plugin load failed: {plugins}")

        def msg(sender: str, text: str) -> XiamiMessage:
            return XiamiMessage(message_type="group", sender=sender, target="20001", text=text)

        loader.dispatch_message(msg("10002", "出题"))
        loader.dispatch_message(msg("99999", "加题 Xiami托管哪个登录内核=NapCat"))
        loader.dispatch_message(msg("10001", "加题 Xiami托管哪个登录内核=NapCat"))
        loader.dispatch_message(msg("10001", "批量加题 虾米机器人登录内核=NapCat\n机器人扫码内核=NapCat"))
        loader.dispatch_message(msg("10001", "加题 停用:临时停用题=Hidden"))
        loader.dispatch_message(msg("10001", "改题 1 基础:Xiami托管哪个登录内核=NapCat"))
        loader.dispatch_message(msg("10001", "停用题 2"))
        loader.dispatch_message(msg("10001", "启用题 2"))
        loader.dispatch_message(msg("10001", "设置答题奖励 5"))
        loader.dispatch_message(msg("10001", "设置答题间隔 0"))
        loader.dispatch_message(msg("10001", "设置答题限时 0"))
        loader.dispatch_message(msg("10002", "答题设置"))
        loader.dispatch_message(msg("10002", "题库"))
        loader.dispatch_message(msg("10002", "题库 基础"))
        loader.dispatch_message(msg("10002", "导出题库 Xiami"))
        loader.dispatch_message(msg("10002", "出题"))
        loader.dispatch_message(msg("10002", "答题 Lagrange"))
        loader.dispatch_message(msg("10002", "答案 NapCat"))
        loader.dispatch_message(msg("10001", "清除答题"))
        loader.dispatch_message(msg("10001", "关闭答题"))
        loader.dispatch_message(msg("10002", "出题"))
        loader.dispatch_message(msg("10001", "清空题库"))

        texts = [item[1] for item in sent]
        if "题库为空" not in texts[0] and "暂无题目" not in texts[0]:
            raise AssertionError(texts)
        if "权限不足" not in texts[1]:
            raise AssertionError(texts)
        if not any("已添加题目 #1" in item for item in texts):
            raise AssertionError(texts)
        if "已导入题目：2 条。" not in texts:
            raise AssertionError(texts)
        if not any("已添加题目 #4" in item and "停用" in item for item in texts):
            raise AssertionError(texts)
        if "已修改题目 #1。" not in texts:
            raise AssertionError(texts)
        if "已停用题目：1 条。" not in texts:
            raise AssertionError(texts)
        if "已启用题目：1 条。" not in texts:
            raise AssertionError(texts)
        if "已设置本群答题奖励：5 积分。" not in texts:
            raise AssertionError(texts)
        if "已设置本群出题间隔：0 秒。" not in texts:
            raise AssertionError(texts)
        if "已设置本群答题限时：0 秒。" not in texts:
            raise AssertionError(texts)
        if not any("答题设置：" in item and "题库数量：4 条" in item and "启用 3 条" in item for item in texts):
            raise AssertionError(texts)
        if not any("本群题库" in item and "Xiami托管哪个登录内核" in item and "基础" in item for item in texts):
            raise AssertionError(texts)
        if not any("本群题库（筛选：基础）" in item and "Xiami托管哪个登录内核" in item for item in texts):
            raise AssertionError(texts)
        if not any("Xiami托管哪个登录内核|NapCat" in item for item in texts):
            raise AssertionError(texts)
        if not any("题目：" in item and "答题 答案" in item for item in texts):
            raise AssertionError(texts)
        if "回答不正确。" not in texts:
            raise AssertionError(texts)
        if not any("回答正确，积分 +5" in item for item in texts):
            raise AssertionError(texts)
        if "当前没有正在进行的题目。" not in texts:
            raise AssertionError(texts)
        if "本群答题已关闭。" not in texts:
            raise AssertionError(texts)
        if texts[-1] == "题库为空，请先添加题目。":
            raise AssertionError(texts)
        if "已清空本群题库：4 条。" not in texts:
            raise AssertionError(texts)

    print("quiz_smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

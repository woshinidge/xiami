from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile

from xiami_core.models import SendResult, XiamiMessage
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.events import plugin_event_from_onebot
from xiami_core.plugins.join_review import JoinReviewService, ReviewRules
from xiami_core.plugins.kv import PluginKVStore
from xiami_core.plugins.loader import PluginLoader
from xiami_core.plugins.test_support import enable_loaded_plugins_for_groups
from xiami_core.plugins.state import PluginStateStore


@dataclass(frozen=True)
class FakeResponse:
    ok: bool = True
    message: str = ""


def main() -> int:
    sent: list[tuple[str, str, str]] = []
    calls: list[tuple[str, dict[str, object]]] = []

    def send(target: str, text: str, message_type: str) -> SendResult:
        sent.append((target, text, message_type))
        return SendResult(ok=True)

    def onebot_call(action: str, params: dict[str, object]) -> FakeResponse:
        calls.append((action, params))
        return FakeResponse()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plugin_root = root / "plugins"
        for plugin_id in ("member_guard", "join_review"):
            source = Path.cwd() / "xiami_plugins" / plugin_id
            plugin_dir = plugin_root / plugin_id
            plugin_dir.mkdir(parents=True)
            (plugin_dir / "plugin.py").write_text((source / "plugin.py").read_text(encoding="utf-8"), encoding="utf-8")
            (plugin_dir / "plugin_config.json").write_text('{"admins":["10001"]}', encoding="utf-8")

        ctx = PluginContext(send_fn=send, state_store=PluginKVStore(root / "state"), onebot_call_fn=onebot_call)
        loader = PluginLoader(plugin_root, ctx, state_store=PluginStateStore(root / "enabled.json"))
        plugins = loader.load_all()
        enable_loaded_plugins_for_groups(ctx, plugins)
        if len(plugins) != 2 or any(plugin.error for plugin in plugins):
            raise RuntimeError(f"join review plugin load failed: {plugins}")

        def msg(sender: str, text: str) -> XiamiMessage:
            return XiamiMessage(message_type="group", sender=sender, target="20001", text=text)

        loader.dispatch_message(msg("10001", "开启入群审核"))
        loader.dispatch_message(msg("10001", "加白名单 20002"))
        loader.dispatch_message(msg("10001", "加黑名单 20003"))
        loader.dispatch_message(msg("10001", "设置审核关键词 Xiami"))

        loader.dispatch_event(plugin_event_from_onebot(_request("20002", "flag-white", "验证信息")))
        loader.dispatch_event(plugin_event_from_onebot(_request("20003", "flag-black", "验证信息")))
        loader.dispatch_event(plugin_event_from_onebot(_request("20004", "flag-keyword", "我是 Xiami 用户")))
        loader.dispatch_event(plugin_event_from_onebot(_request("20005", "flag-manual", "没有关键词")))
        loader.dispatch_message(msg("10001", "同意入群 flag-manual"))
        loader.dispatch_message(msg("10001", "拒绝入群 flag-other 不通过"))
        loader.dispatch_event(plugin_event_from_onebot({"post_type": "notice", "notice_type": "group_increase", "group_id": 20001, "user_id": 20006}))
        loader.dispatch_event(plugin_event_from_onebot({"post_type": "notice", "notice_type": "group_decrease", "group_id": 20001, "user_id": 20007}))
        loader.dispatch_message(msg("10001", "设置审核性别 不限"))
        loader.dispatch_message(msg("10001", "设置审核等级 0"))
        loader.dispatch_message(msg("10001", "设置审核Q龄 0"))
        loader.dispatch_message(msg("10001", "关闭黑白名单审核"))
        loader.dispatch_message(msg("10001", "开启黑白名单审核"))

        review_plugin = next(plugin for plugin in plugins if plugin.id == "join_review")
        JoinReviewService(review_plugin.context).set_rules(
            "20001",
            ReviewRules(blacklist_enabled=True, level_enabled=True, min_level=10),
        )
        low_level = _request("20008", "flag-level-low", "我是 Xiami 用户")
        low_level["level"] = 3
        loader.dispatch_event(plugin_event_from_onebot(low_level))
        enough_level = _request("20009", "flag-level-ok", "我是 Xiami 用户")
        enough_level["level"] = 20
        loader.dispatch_event(plugin_event_from_onebot(enough_level))
        loader.dispatch_event(plugin_event_from_onebot(_request("20010", "flag-level-missing", "我是 Xiami 用户")))
        loader.dispatch_message(msg("10001", "审核记录"))
        loader.dispatch_message(msg("10001", "审核记录 manual"))
        loader.dispatch_message(msg("10001", "导出入群审核记录 flag"))
        loader.dispatch_message(msg("10001", "清空入群审核记录"))
        loader.dispatch_message(msg("10001", "审核记录"))
        loader.dispatch_message(msg("10001", "重置入群审核"))

        expected_calls = [
            ("set_group_add_request", {"flag": "flag-white", "sub_type": "add", "approve": True, "reason": ""}),
            ("set_group_add_request", {"flag": "flag-black", "sub_type": "add", "approve": False, "reason": "本群已开启入群审核，请联系管理员。"}),
            ("set_group_add_request", {"flag": "flag-keyword", "sub_type": "add", "approve": True, "reason": ""}),
            ("set_group_add_request", {"flag": "flag-manual", "sub_type": "add", "approve": True, "reason": ""}),
            ("set_group_add_request", {"flag": "flag-other", "sub_type": "add", "approve": False, "reason": "不通过"}),
            ("set_group_add_request", {"flag": "flag-level-low", "sub_type": "add", "approve": False, "reason": "本群已开启入群审核，请联系管理员。"}),
            ("set_group_add_request", {"flag": "flag-level-ok", "sub_type": "add", "approve": True, "reason": ""}),
        ]
        if calls != expected_calls:
            raise AssertionError(calls)

        texts = [item[1] for item in sent]
        if not any("已自动同意 20002" in item for item in texts):
            raise AssertionError(texts)
        if not any("已自动拒绝 20003" in item for item in texts):
            raise AssertionError(texts)
        if not any("已自动同意 20004" in item for item in texts):
            raise AssertionError(texts)
        if not any("入群申请待审核：20005" in item for item in texts):
            raise AssertionError(texts)
        if not any("已提交同意入群申请" in item for item in texts):
            raise AssertionError(texts)
        if not any("已提交拒绝入群申请" in item for item in texts):
            raise AssertionError(texts)
        if not any("欢迎 20006" in item for item in texts):
            raise AssertionError(texts)
        if not any("成员 20007 已离开本群" in item for item in texts):
            raise AssertionError(texts)
        if not any("已自动拒绝 20008" in item for item in texts):
            raise AssertionError(texts)
        if not any("已自动同意 20009" in item for item in texts):
            raise AssertionError(texts)
        if not any("入群申请待审核：20010" in item for item in texts):
            raise AssertionError(texts)
        if not any("最近入群审核记录：" in item and "manual_approve" in item and "manual_reject" in item for item in texts):
            raise AssertionError(texts)
        required_texts = [
            "入群审核性别规则已设置：不限制。",
            "入群审核等级规则已关闭：最低 0。",
            "入群审核Q龄规则已关闭：最低 0。",
            "本群黑白名单审核已关闭。",
            "本群黑白名单审核已开启。",
            "入群审核记录已清空：",
            "本群入群审核设置已恢复默认。",
        ]
        for expected in required_texts:
            if not any(expected in item for item in texts):
                raise AssertionError(texts)
        if not any("最近入群审核记录（筛选：manual）：" in item and "manual_approve" in item for item in texts):
            raise AssertionError(texts)
        if not any("入群审核记录导出：" in item and "时间|群号|动作|QQ|flag|验证信息|原因" in item and "flag-manual" in item for item in texts):
            raise AssertionError(texts)
        if texts[-2] != "暂无入群审核记录。":
            raise AssertionError(texts)

    print("join_review_smoke ok")
    return 0


def _request(user_id: str, flag: str, comment: str) -> dict[str, object]:
    return {
        "post_type": "request",
        "request_type": "group",
        "sub_type": "add",
        "group_id": 20001,
        "user_id": int(user_id),
        "flag": flag,
        "comment": comment,
    }


if __name__ == "__main__":
    raise SystemExit(main())

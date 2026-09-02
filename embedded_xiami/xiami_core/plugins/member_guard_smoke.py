from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from xiami_core.models import SendResult, XiamiMessage
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.group_settings import GroupSettingService
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
        source = Path.cwd() / "xiami_plugins" / "member_guard"
        plugin_root = root / "plugins"
        plugin_dir = plugin_root / "member_guard"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.py").write_text((source / "plugin.py").read_text(encoding="utf-8"), encoding="utf-8")
        (plugin_dir / "plugin_config.json").write_text(
            '{"admins":["10001"],"forbidden_ban_seconds":30}',
            encoding="utf-8",
        )

        ctx = PluginContext(send_fn=send, state_store=PluginKVStore(root / "state"), onebot_call_fn=onebot_call)
        loader = PluginLoader(plugin_root, ctx, state_store=PluginStateStore(root / "enabled.json"))
        plugins = loader.load_all()
        enable_loaded_plugins_for_groups(ctx, plugins, "20001", "20002")
        if not plugins or plugins[0].error:
            raise RuntimeError(f"member guard plugin load failed: {plugins}")

        def msg(sender: str, text: str, group_id: str = "20001") -> XiamiMessage:
            return XiamiMessage(message_type="group", sender=sender, target=group_id, text=text)

        loader.dispatch_message(msg("99999", "加黑名单 10002"))
        loader.dispatch_message(msg("10001", "加黑名单 10002"))
        loader.dispatch_message(msg("10002", "普通消息"))
        loader.dispatch_message(msg("10001", "加全局白名单 10003"))
        loader.dispatch_message(msg("10001", "加全局黑名单 10003"))
        loader.dispatch_message(msg("10001", "加全局黑名单 10005"))
        loader.dispatch_message(msg("10001", "名单列表"))
        loader.dispatch_message(msg("10003", "白名单优先消息"))
        loader.dispatch_message(msg("10001", "加违禁词 badword"))
        loader.dispatch_message(msg("10001", "违禁词列表"))
        loader.dispatch_message(msg("10004", "this has badword"))
        loader.dispatch_message(msg("10001", "撤回设置"))
        loader.dispatch_message(msg("10001", "开启群号撤回"))
        loader.dispatch_message(msg("10001", "开启红包撤回"))
        loader.dispatch_message(msg("10001", "设置撤回类型 图片 红包"))
        loader.dispatch_message(msg("10001", "设置违禁词禁言 45"))
        loader.dispatch_message(msg("10001", "设置退群撤回条数 3"))
        loader.dispatch_message(msg("10001", "撤回类型"))

        before_disabled_sent = len(sent)
        before_disabled_calls = len(calls)
        GroupSettingService(ctx).set_enabled("20001", "member_guard_enabled", False)
        loader.dispatch_message(msg("10002", "普通消息"))
        loader.dispatch_message(msg("10004", "this has badword"))
        if len(sent) != before_disabled_sent or len(calls) != before_disabled_calls:
            raise RuntimeError(f"disabled member guard group still acted: sent={sent}, calls={calls}")

        GroupSettingService(ctx).set_enabled("20001", "member_guard_enabled", True)
        GroupSettingService(ctx).set_enabled("20001", "blacklist_kick_enabled", False)
        before_group_kick_disabled_sent = len(sent)
        before_group_kick_disabled_calls = len(calls)
        loader.dispatch_message(msg("10002", "blacklist kick disabled in this group"))
        if len(sent) != before_group_kick_disabled_sent or len(calls) != before_group_kick_disabled_calls:
            raise RuntimeError(f"group blacklist kick switch was not isolated: sent={sent}, calls={calls}")

        loader.dispatch_message(msg("10005", "global black still works", "20002"))
        loader.dispatch_message(msg("10001", "清空黑名单"))
        loader.dispatch_message(msg("10001", "清空违禁词"))

        texts = [item[1] for item in sent]
        required = [
            "权限不足，需要管理员。",
            "已添加本群黑名单：1 个。",
            "已踢出黑名单成员 10002（本群黑名单）。",
            "已添加全局白名单：1 个。",
            "已添加全局黑名单：1 个。",
            "已添加本群违禁词：1 个。",
            "命中违禁词：badword，已禁言 30 秒。",
            "已开启本群群号撤回。",
            "已开启本群红包撤回。",
            "已设置本群撤回类型：图片、红包。",
            "已设置本群违禁词禁言秒数：45。",
            "已设置本群退群撤回条数：3。",
            "当前撤回类型：图片、红包",
            "已清空本群黑名单：1 个。",
            "已清空本群违禁词：1 个。",
        ]
        for item in required:
            if item not in texts:
                raise RuntimeError(f"missing member guard reply {item!r}: {texts}")
        if not any("名单与违禁词：" in item and "本群黑名单：10002" in item and "全局白名单：10003" in item for item in texts):
            raise RuntimeError(f"member list summary missing: {texts}")
        if not any("违禁词列表：" in item and "本群违禁词：badword" in item for item in texts):
            raise RuntimeError(f"forbidden words summary missing: {texts}")
        if not any("撤回设置：" in item and "群号撤回：关闭" in item and "自动类型撤回：关闭" in item for item in texts):
            raise RuntimeError(f"recall settings missing: {texts}")

        expected_calls = [
            ("set_group_kick", {"group_id": 20001, "user_id": 10002, "reject_add_request": False}),
            ("set_group_ban", {"group_id": 20001, "user_id": 10004, "duration": 30}),
            ("set_group_kick", {"group_id": 20002, "user_id": 10005, "reject_add_request": False}),
        ]
        if calls != expected_calls:
            raise RuntimeError(f"wrong member guard onebot calls: {calls}")

    print("member guard plugin smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

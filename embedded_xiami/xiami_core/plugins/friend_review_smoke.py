from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile

from xiami_core.models import SendResult, XiamiMessage
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.events import plugin_event_from_onebot
from xiami_core.plugins.kv import PluginKVStore
from xiami_core.plugins.loader import PluginLoader
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
        source = Path.cwd() / "xiami_plugins" / "friend_review"
        plugin_root = root / "plugins"
        plugin_dir = plugin_root / "friend_review"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.py").write_text((source / "plugin.py").read_text(encoding="utf-8"), encoding="utf-8")
        (plugin_dir / "plugin_config.json").write_text(
            (
                "{"
                '"admins":["10001"],'
                '"friend_review_enabled":true,'
                '"friend_review_mode":"manual",'
                '"friend_notify_users":["10001"],'
                '"friend_auto_approve_keywords":["同意"],'
                '"friend_auto_reject_keywords":["拒绝"],'
                '"friend_auto_approve_users":["30001"],'
                '"friend_auto_reject_users":["30002"]'
                "}"
            ),
            encoding="utf-8",
        )

        ctx = PluginContext(
            send_fn=send,
            state_store=PluginKVStore(root / "state"),
            onebot_call_fn=onebot_call,
        )
        loader = PluginLoader(plugin_root, ctx, state_store=PluginStateStore(root / "enabled.json"))
        plugins = loader.load_all()
        if not plugins or plugins[0].error:
            raise RuntimeError(f"friend_review plugin load failed: {plugins}")

        loader.dispatch_event(plugin_event_from_onebot(_friend_request("20001", "flag-approve", "请同意")))
        loader.dispatch_event(plugin_event_from_onebot(_friend_request("20002", "flag-reject", "请拒绝")))
        loader.dispatch_event(plugin_event_from_onebot(_friend_request("20003", "flag-manual", "普通申请")))
        loader.dispatch_event(plugin_event_from_onebot(_friend_request("30001", "flag-approve-user", "普通申请")))
        loader.dispatch_event(plugin_event_from_onebot(_friend_request("30002", "flag-reject-user", "普通申请")))

        loader.dispatch_message(_private("10001", "同意好友 flag-manual 备注A"))
        loader.dispatch_message(_private("10001", "拒绝好友 flag-other 不通过"))
        loader.dispatch_message(_private("10001", "好友同意QQ 40001 40002"))
        loader.dispatch_message(_private("10001", "好友拒绝QQ 50001 50002"))
        loader.dispatch_message(_private("10001", "设置好友拒绝理由 资料不完整"))
        loader.dispatch_message(_private("10001", "设置好友同意备注 欢迎加入"))
        loader.dispatch_message(_private("10001", "好友审核状态"))
        loader.dispatch_message(_private("10001", "好友审核记录 flag-manual"))
        loader.dispatch_message(_private("10001", "导出好友审核记录 flag"))
        loader.dispatch_message(_private("10001", "清空好友审核记录"))
        loader.dispatch_message(_private("10001", "好友审核记录"))
        loader.dispatch_message(_private("10001", "重置好友审核"))

    expected = [
        ("set_friend_add_request", {"flag": "flag-approve", "approve": True, "remark": ""}),
        ("set_friend_add_request", {"flag": "flag-reject", "approve": False, "remark": "命中拒绝词：拒绝"}),
        ("set_friend_add_request", {"flag": "flag-approve-user", "approve": True, "remark": ""}),
        ("set_friend_add_request", {"flag": "flag-reject-user", "approve": False, "remark": "命中拒绝名单"}),
        ("set_friend_add_request", {"flag": "flag-manual", "approve": True, "remark": "备注A"}),
        ("set_friend_add_request", {"flag": "flag-other", "approve": False, "remark": "不通过"}),
    ]
    if calls != expected:
        raise AssertionError(calls)

    texts = [item[1] for item in sent]
    if not any("好友申请已自动同意：20001" in item for item in texts):
        raise AssertionError(texts)
    if not any("好友申请已自动拒绝：20002" in item for item in texts):
        raise AssertionError(texts)
    if not any("好友申请待审核：20003" in item and "flag-manual" in item for item in texts):
        raise AssertionError(texts)
    if not any("好友申请已自动同意：30001" in item for item in texts):
        raise AssertionError(texts)
    if not any("好友申请已自动拒绝：30002" in item for item in texts):
        raise AssertionError(texts)
    if not any("已设置好友自动同意QQ：40001、40002" in item for item in texts):
        raise AssertionError(texts)
    if not any("已设置好友自动拒绝QQ：50001、50002" in item for item in texts):
        raise AssertionError(texts)
    if not any("好友默认拒绝理由已设置：资料不完整" in item for item in texts):
        raise AssertionError(texts)
    if not any("好友默认同意备注已设置：欢迎加入" in item for item in texts):
        raise AssertionError(texts)
    if not any(
        "好友审核配置：" in item
        and "自动同意QQ：40001, 40002" in item
        and "自动拒绝QQ：50001, 50002" in item
        and "拒绝理由：资料不完整" in item
        for item in texts
    ):
        raise AssertionError(texts)
    if not any("最近好友审核记录（筛选：flag-manual）：" in item and "flag-manual" in item and "manual_approve" in item for item in texts):
        raise AssertionError(texts)
    if not any("好友审核记录导出：" in item and "时间|动作|QQ|flag|验证信息|原因/备注" in item and "flag-manual" in item for item in texts):
        raise AssertionError(texts)
    if "好友审核记录已清空。" not in texts:
        raise AssertionError(texts)
    if texts[-2] != "暂无好友审核记录。" or texts[-1] != "好友审核设置已恢复默认。":
        raise AssertionError(texts)

    print("friend_review_smoke ok")
    return 0


def _friend_request(user_id: str, flag: str, comment: str) -> dict[str, object]:
    return {
        "post_type": "request",
        "request_type": "friend",
        "user_id": int(user_id),
        "flag": flag,
        "comment": comment,
    }


def _private(sender: str, text: str) -> XiamiMessage:
    return XiamiMessage(message_type="private", sender=sender, text=text)


if __name__ == "__main__":
    raise SystemExit(main())

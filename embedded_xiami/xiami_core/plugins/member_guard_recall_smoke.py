from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile

from xiami_core.models import MessageSegment, SendResult, XiamiMessage
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.events import plugin_event_from_onebot
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
            '{"admins":["10001"],"forbidden_ban_seconds":30,'
            '"auto_recall_enabled":true,'
            '"recall_message_types":["image","video","url","json","xml","card","redbag","miniapp","email"],'
            '"leave_recall_enabled":true,"leave_recall_limit":1}',
            encoding="utf-8",
        )

        ctx = PluginContext(send_fn=send, state_store=PluginKVStore(root / "state"), onebot_call_fn=onebot_call)
        loader = PluginLoader(plugin_root, ctx, state_store=PluginStateStore(root / "enabled.json"))
        plugins = loader.load_all()
        enable_loaded_plugins_for_groups(ctx, plugins)
        if not plugins or plugins[0].error:
            raise RuntimeError(f"member guard plugin load failed: {plugins}")
        plugins[0].context.state_store.set("permissions", "global_admins", ["10006"])
        plugins[0].context.state_store.set("permissions", "group_admins", {"20001": ["10007"]})

        loader.dispatch_message(_msg("10001", "加违禁词 bad"))
        loader.dispatch_message(_msg("10001", "加黑名单 10003"))
        loader.dispatch_message(_msg("10001", "加黑名单 10006"))
        loader.dispatch_event(plugin_event_from_onebot(_payload("10002", 41, "this is bad"), _msg("10002", "this is bad")))
        loader.dispatch_event(plugin_event_from_onebot(_payload("10003", 42, "hello"), _msg("10003", "hello")))
        loader.dispatch_event(plugin_event_from_onebot(_payload("10004", 43, "clean"), _msg("10004", "clean")))
        loader.dispatch_event(plugin_event_from_onebot(_payload("10004", 44, "[CQ:image,file=a.png]"), _image_msg("10004")))
        loader.dispatch_event(plugin_event_from_onebot(_payload("10004", 45, "https://xiami.local"), _msg("10004", "https://xiami.local")))
        loader.dispatch_event(plugin_event_from_onebot(_payload("10004", 46, "[CQ:video,file=a.mp4]"), _segment_msg("10004", "video", {"file": "a.mp4"})))
        loader.dispatch_event(plugin_event_from_onebot(_payload("10004", 47, "[CQ:json,data={}]"), _segment_msg("10004", "json", {"data": "{}"})))
        loader.dispatch_event(plugin_event_from_onebot(_payload("10004", 48, "[CQ:xml,data=<msg/>]"), _segment_msg("10004", "xml", {"data": "<msg/>"})))
        loader.dispatch_event(plugin_event_from_onebot(_payload("10004", 49, "[CQ:card,title=test]"), _segment_msg("10004", "card", {"title": "test"})))
        loader.dispatch_event(plugin_event_from_onebot(_payload("10004", 50, "[CQ:redbag,title=红包]"), _segment_msg("10004", "redbag", {"title": "红包"})))
        loader.dispatch_event(plugin_event_from_onebot(_payload("10004", 51, "[CQ:miniapp,title=小程序]"), _segment_msg("10004", "miniapp", {"title": "小程序"})))
        loader.dispatch_event(plugin_event_from_onebot(_payload("10004", 52, "admin@example.com"), _msg("10004", "admin@example.com")))
        loader.dispatch_event(plugin_event_from_onebot(_payload("10004", 73, "[CQ:mface]"), _segment_msg("10004", "mface", {"emoji_id": "123"})))
        loader.dispatch_event(
            plugin_event_from_onebot(
                _payload("10004", 74, "[CQ:lightapp]"),
                _segment_msg("10004", "lightapp", {"data": '{"app":"com.tencent.mobileqq.qwallet","desc":"红包"}'}),
            )
        )
        loader.dispatch_event(
            plugin_event_from_onebot(
                _payload("10004", 75, "[CQ:lightapp]"),
                _segment_msg("10004", "lightapp", {"data": '{"app":"com.tencent.miniapp_01","desc":"小程序"}'}),
            )
        )
        loader.dispatch_event(
            plugin_event_from_onebot(
                _payload("10004", 76, "[CQ:share]"),
                _segment_msg("10004", "share", {"url": "https://example.com", "title": "分享"}),
            )
        )
        plugins[0].context.config["recall_message_types"] = ["redbag"]
        before_redbag_only = len(calls)
        loader.dispatch_event(plugin_event_from_onebot(_payload("10004", 57, "发个红包"), _msg("10004", "发个红包")))
        loader.dispatch_event(plugin_event_from_onebot(_payload("10004", 77, "[CQ:image,file=normal.png]"), _image_msg("10004")))
        if len(calls) != before_redbag_only:
            raise AssertionError(f"redbag-only mode must not recall plain text or normal images: {calls}")
        loader.dispatch_event(
            plugin_event_from_onebot(
                _payload("10004", 55, "[CQ:json,data={\"app\":\"com.tencent.qqwallet\",\"desc\":\"恭喜发财\"}]"),
                _segment_msg("10004", "json", {"data": '{"app":"com.tencent.qqwallet","desc":"恭喜发财"}'}),
            )
        )
        for message_id, redbag_type in (
            (80, "普通红包"),
            (81, "拼手气红包"),
            (82, "专属红包"),
            (83, "口令红包"),
            (84, "语音红包"),
        ):
            loader.dispatch_event(
                plugin_event_from_onebot(
                    _wallet_payload("10004", message_id, redbag_type),
                    _msg("10004", ""),
                )
            )
        plugins[0].context.config["recall_message_types"] = ["image"]
        before_image_only = len(calls)
        loader.dispatch_event(
            plugin_event_from_onebot(
                _payload("10004", 78, "[CQ:json,data={\"app\":\"com.tencent.qqwallet\",\"desc\":\"恭喜发财\"}]"),
                _segment_msg("10004", "json", {"data": '{"app":"com.tencent.qqwallet","desc":"恭喜发财"}'}),
            )
        )
        loader.dispatch_event(plugin_event_from_onebot(_wallet_payload("10004", 85, "拼手气红包"), _msg("10004", "")))
        if len(calls) != before_image_only:
            raise AssertionError(f"image-only mode must not recall redbag cards: {calls}")
        loader.dispatch_event(plugin_event_from_onebot(_payload("10004", 79, "[CQ:image,file=normal.png]"), _image_msg("10004")))
        before_empty_message = len(calls)
        loader.dispatch_event(plugin_event_from_onebot(_empty_payload("10004", 56), _msg("10004", "")))
        if len(calls) != before_empty_message:
            raise AssertionError(f"unknown empty messages must not be treated as red packets: {calls}")
        plugins[0].context.config["group_number_recall_enabled"] = True
        before_plain_number = len(calls)
        loader.dispatch_event(plugin_event_from_onebot(_payload("10004", 60, "313420054"), _msg("10004", "313420054")))
        loader.dispatch_event(plugin_event_from_onebot(_payload("10004", 66, "订单号 123456789"), _msg("10004", "订单号 123456789")))
        loader.dispatch_event(plugin_event_from_onebot(_payload("10004", 67, "联系电话 13800138000"), _msg("10004", "联系电话 13800138000")))
        if len(calls) != before_plain_number:
            raise AssertionError(f"plain QQ/order/phone numbers must not be treated as group ads: {calls}")
        loader.dispatch_event(plugin_event_from_onebot(_payload("10004", 58, "群号 123456789"), _msg("10004", "群号 123456789")))
        loader.dispatch_event(plugin_event_from_onebot(_payload("10004", 59, "https://jq.qq.com/?_wv=1027&k=abc"), _msg("10004", "https://jq.qq.com/?_wv=1027&k=abc")))
        loader.dispatch_event(plugin_event_from_onebot(_payload("10004", 65, "加群①⑦②②⑨⑥⑤②⑦"), _msg("10004", "加群①⑦②②⑨⑥⑤②⑦")))
        plugins[0].context.config["group_number_recall_enabled"] = False
        plugins[0].context.config["recall_message_types"] = ["url"]
        before_media_url = len(calls)
        loader.dispatch_event(plugin_event_from_onebot(_payload("10004", 68, "[CQ:image]"), _image_url_msg("10004")))
        if len(calls) != before_media_url:
            raise AssertionError(f"image CDN URLs must not match the visible URL option: {calls}")
        loader.dispatch_event(plugin_event_from_onebot(_payload("10004", 69, "https://example.com"), _msg("10004", "https://example.com")))
        plugins[0].context.config["recall_message_types"] = ["miniapp"]
        before_plain_miniapp = len(calls)
        loader.dispatch_event(plugin_event_from_onebot(_payload("10004", 70, "这个小程序不错"), _msg("10004", "这个小程序不错")))
        if len(calls) != before_plain_miniapp:
            raise AssertionError(f"plain miniapp discussion must not be treated as a miniapp card: {calls}")
        loader.dispatch_event(plugin_event_from_onebot(_payload("10004", 71, "[CQ:miniapp]"), _segment_msg("10004", "miniapp", {"title": "test"})))
        plugins[0].context.config["recall_message_types"] = ["card"]
        before_plain_card = len(calls)
        loader.dispatch_event(plugin_event_from_onebot(_payload("10004", 72, "card 资料"), _msg("10004", "card 资料")))
        if len(calls) != before_plain_card:
            raise AssertionError(f"plain card text must not be treated as a structured card: {calls}")
        before_admin_recall = len(calls)
        loader.dispatch_event(plugin_event_from_onebot(_payload("10006", 61, "this is bad"), _msg("10006", "this is bad")))
        loader.dispatch_event(plugin_event_from_onebot(_payload("10006", 62, "群号 123456789"), _msg("10006", "群号 123456789")))
        loader.dispatch_event(plugin_event_from_onebot(_empty_payload("10006", 63), _msg("10006", "")))
        loader.dispatch_event(plugin_event_from_onebot(_payload("10007", 64, "[CQ:image,file=admin.png]"), _image_msg("10007")))
        loader.dispatch_event(plugin_event_from_onebot(_leave_payload("10006")))
        if len(calls) != before_admin_recall:
            raise AssertionError(f"configured admins should be exempt from all recalls: {calls}")
        loader.dispatch_event(plugin_event_from_onebot(_payload("10005", 53, "first"), _msg("10005", "first")))
        loader.dispatch_event(plugin_event_from_onebot(_payload("10005", 54, "second"), _msg("10005", "second")))
        loader.dispatch_event(plugin_event_from_onebot(_leave_payload("10005")))

        expected = [
            ("delete_msg", {"message_id": 41}),
            ("delete_msg", {"message_id": 42}),
            ("delete_msg", {"message_id": 44}),
            ("delete_msg", {"message_id": 45}),
            ("delete_msg", {"message_id": 46}),
            ("delete_msg", {"message_id": 47}),
            ("delete_msg", {"message_id": 48}),
            ("delete_msg", {"message_id": 49}),
            ("delete_msg", {"message_id": 50}),
            ("delete_msg", {"message_id": 51}),
            ("delete_msg", {"message_id": 52}),
            ("delete_msg", {"message_id": 73}),
            ("delete_msg", {"message_id": 74}),
            ("delete_msg", {"message_id": 75}),
            ("delete_msg", {"message_id": 76}),
            ("delete_msg", {"message_id": 55}),
            ("delete_msg", {"message_id": 80}),
            ("delete_msg", {"message_id": 81}),
            ("delete_msg", {"message_id": 82}),
            ("delete_msg", {"message_id": 83}),
            ("delete_msg", {"message_id": 84}),
            ("delete_msg", {"message_id": 79}),
            ("delete_msg", {"message_id": 58}),
            ("delete_msg", {"message_id": 59}),
            ("delete_msg", {"message_id": 65}),
            ("delete_msg", {"message_id": 69}),
            ("delete_msg", {"message_id": 71}),
            ("delete_msg", {"message_id": 54}),
        ]
        if calls != expected:
            raise AssertionError(calls)

        texts = [item[1] for item in sent]
        if not any("包含违禁词，已撤回" in item for item in texts):
            raise AssertionError(texts)
        if not any("黑名单成员 10003 的消息已撤回" in item for item in texts):
            raise AssertionError(texts)

    print("member_guard_recall_smoke ok")
    return 0


def _msg(sender: str, text: str) -> XiamiMessage:
    return XiamiMessage(message_type="group", sender=sender, target="20001", text=text)


def _image_msg(sender: str) -> XiamiMessage:
    return XiamiMessage(
        message_type="group",
        sender=sender,
        target="20001",
        text="[图片]",
        raw_message="[CQ:image,file=a.png]",
        segments=(MessageSegment("image", {"file": "a.png"}),),
    )


def _image_url_msg(sender: str) -> XiamiMessage:
    return XiamiMessage(
        message_type="group",
        sender=sender,
        target="20001",
        text="[图片]",
        raw_message="[CQ:image,file=a.png,url=https://media.example/a.png]",
        segments=(MessageSegment("image", {"file": "a.png", "url": "https://media.example/a.png"}),),
    )


def _segment_msg(sender: str, segment_type: str, data: dict[str, str]) -> XiamiMessage:
    return XiamiMessage(
        message_type="group",
        sender=sender,
        target="20001",
        text=f"[{segment_type}]",
        raw_message=f"[CQ:{segment_type}]",
        segments=(MessageSegment(segment_type, data),),
    )


def _payload(sender: str, message_id: int, text: str) -> dict[str, object]:
    return {
        "post_type": "message",
        "message_type": "group",
        "group_id": 20001,
        "user_id": int(sender),
        "message_id": message_id,
        "raw_message": text,
    }


def _empty_payload(sender: str, message_id: int) -> dict[str, object]:
    payload = _payload(sender, message_id, "")
    payload["message"] = []
    payload["raw_message"] = ""
    return payload


def _wallet_payload(sender: str, message_id: int, redbag_type: str) -> dict[str, object]:
    payload = _empty_payload(sender, message_id)
    payload["message_format"] = "array"
    payload["sub_type"] = "normal"
    # NapCat currently drops WALLET element details from OneBot output. The label
    # documents the covered QQ variant without affecting production detection.
    payload["test_redbag_type"] = redbag_type
    return payload


def _leave_payload(sender: str) -> dict[str, object]:
    return {
        "post_type": "notice",
        "notice_type": "group_decrease",
        "sub_type": "leave",
        "group_id": 20001,
        "user_id": int(sender),
        "operator_id": int(sender),
    }


if __name__ == "__main__":
    raise SystemExit(main())

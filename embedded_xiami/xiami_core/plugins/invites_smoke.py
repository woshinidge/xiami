from __future__ import annotations

from pathlib import Path
import sys
import tempfile


EMBEDDED_ROOT = Path(__file__).resolve().parents[2]
if str(EMBEDDED_ROOT) not in sys.path:
    sys.path.insert(0, str(EMBEDDED_ROOT))


from xiami_core.models import SendResult, XiamiMessage
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.events import plugin_event_from_onebot
from xiami_core.plugins.group_settings import GroupSettingService
from xiami_core.plugins.invites import InviteService
from xiami_core.plugins.kv import PluginKVStore
from xiami_core.plugins.loader import PluginLoader
from xiami_core.plugins.points import PointsService
from xiami_core.plugins.state import PluginStateStore


def main() -> int:
    sent: list[tuple[str, str, str]] = []

    def send(target: str, text: str, message_type: str) -> SendResult:
        sent.append((target, text, message_type))
        return SendResult(ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = EMBEDDED_ROOT / "xiami_plugins" / "invites"
        plugin_root = root / "plugins"
        plugin_dir = plugin_root / "invites"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.py").write_text((source / "plugin.py").read_text(encoding="utf-8"), encoding="utf-8")
        (plugin_dir / "plugin_config.json").write_text('{"admins":["10001"],"invite_reward_points":3}', encoding="utf-8")

        ctx = PluginContext(send_fn=send, state_store=PluginKVStore(root / "state"))
        settings = GroupSettingService(ctx)
        settings.set_plugin_enabled("20001", "invites", True)
        settings.set_enabled("20001", "invite_points_enabled", True)
        loader = PluginLoader(plugin_root, ctx, state_store=PluginStateStore(root / "enabled.json"))
        plugins = loader.load_all()
        if not plugins or plugins[0].error:
            raise RuntimeError(f"invites plugin load failed: {plugins}")

        raw = {"post_type": "notice", "notice_type": "group_increase", "group_id": 20001, "user_id": 10002, "operator_id": 10001}
        loader.dispatch_event(plugin_event_from_onebot(raw))
        loader.dispatch_event(plugin_event_from_onebot(raw))
        loader.dispatch_message(XiamiMessage(message_type="group", sender="10002", target="20001", text="邀请排行"))
        loader.dispatch_message(XiamiMessage(message_type="group", sender="10001", target="20001", text="我的邀请"))
        loader.dispatch_message(XiamiMessage(message_type="group", sender="10001", target="20001", text="邀请记录 10002"))
        loader.dispatch_message(XiamiMessage(message_type="group", sender="10001", target="20001", text="邀请设置"))
        loader.dispatch_message(XiamiMessage(message_type="group", sender="10001", target="20001", text="设置邀请奖励 5"))
        loader.dispatch_message(XiamiMessage(message_type="group", sender="10001", target="20001", text="设置邀请天数 7"))
        raw_reward5 = {"post_type": "notice", "notice_type": "group_increase", "group_id": 20001, "user_id": 10004, "operator_id": 10001}
        loader.dispatch_event(plugin_event_from_onebot(raw_reward5))
        raw_leave5 = {"post_type": "notice", "notice_type": "group_decrease", "sub_type": "leave", "group_id": 20001, "user_id": 10004}
        loader.dispatch_event(plugin_event_from_onebot(raw_leave5))
        loader.dispatch_event(plugin_event_from_onebot(raw_leave5))
        loader.dispatch_message(XiamiMessage(message_type="group", sender="10001", target="20001", text="补邀请 10005 10001 6"))
        loader.dispatch_message(XiamiMessage(message_type="group", sender="10001", target="20001", text="导入邀请记录 10006=10001,7\n10007 10002 2"))
        loader.dispatch_message(XiamiMessage(message_type="group", sender="10001", target="20001", text="导出邀请记录 10006"))
        loader.dispatch_message(XiamiMessage(message_type="group", sender="10001", target="20001", text="重算邀请排行"))
        loader.dispatch_message(XiamiMessage(message_type="group", sender="10001", target="20001", text="删除邀请记录 10004"))
        loader.dispatch_message(XiamiMessage(message_type="group", sender="10001", target="20001", text="关闭邀请积分"))
        raw2 = {"post_type": "notice", "notice_type": "group_increase", "group_id": 20001, "user_id": 10003, "operator_id": 10001}
        loader.dispatch_event(plugin_event_from_onebot(raw2))
        loader.dispatch_message(XiamiMessage(message_type="group", sender="10001", target="20001", text="清空邀请记录"))

        texts = [item[1] for item in sent]
        reward = "成员 10002 入群，邀请人 10001 获得 3 积分，当前积分：3。"
        if texts.count(reward) != 1:
            raise RuntimeError(f"invite reward should happen once: {texts}")
        if not any(text.startswith("邀请排行") and "10001 邀请 1 人，奖励 3 积分" in text for text in texts):
            raise RuntimeError(f"invite rank missing: {texts}")
        if not any("我的邀请：邀请 1 人，奖励 3 积分，第 1 名" in text for text in texts):
            raise RuntimeError(f"my invite stats missing: {texts}")
        if not any("邀请记录：" in text and "10002 由 10001 邀请" in text for text in texts):
            raise RuntimeError(f"invite records missing: {texts}")
        if not any("邀请积分设置：" in text and "邀请记录：1 条" in text and "邀请人：1 个" in text for text in texts):
            raise RuntimeError(f"invite settings missing: {texts}")
        if "已设置本群邀请奖励：5 积分。" not in texts:
            raise RuntimeError(f"set invite reward missing: {texts}")
        if "已设置邀请成员入群保留期：7 天。" not in texts:
            raise RuntimeError(f"set invite retention days missing: {texts}")
        if not any("成员 10004 入群，邀请人 10001 获得 5 积分" in text for text in texts):
            raise RuntimeError(f"invite reward 5 missing: {texts}")
        deduction_messages = [text for text in texts if "成员 10004 入群未满 7 天即退群" in text and "扣回 5 积分" in text]
        if len(deduction_messages) != 1:
            raise RuntimeError(f"early leave deduction should happen once: {texts}")
        if "已补录邀请记录：10005 <- 10001，奖励 6 积分。" not in texts:
            raise RuntimeError(f"manual invite record missing: {texts}")
        if "已导入邀请记录：2 条。" not in texts:
            raise RuntimeError(f"import invite records missing: {texts}")
        if not any("10006=10001,7" in text for text in texts):
            raise RuntimeError(f"export invite records missing: {texts}")
        if "已根据 4 条邀请记录重算排行。" not in texts:
            raise RuntimeError(f"rebuild invite rank missing: {texts}")
        if "已删除邀请记录：10004。" not in texts:
            raise RuntimeError(f"delete invite record missing: {texts}")
        if "已关闭本群邀请积分。" not in texts:
            raise RuntimeError(f"disable invite missing: {texts}")
        if any("10003 入群" in text for text in texts):
            raise RuntimeError(f"disabled invite still rewarded: {texts}")
        if "已清空本群邀请记录：4 条。" not in texts:
            raise RuntimeError(f"clear invite records missing: {texts}")

        plugin_ctx = plugins[0].context
        service = InviteService(plugin_ctx)
        points = PointsService(plugin_ctx)
        service.set_retention_days("20002", 7)
        joined = service.add_record("20002", "30002", "30001", 5, now_ts=1_000_000)
        if not joined.rewarded:
            raise RuntimeError(f"deterministic invite join failed: {joined}")
        points.set_points("20002", "30001", 1)
        early = service.record_leave("20002", "30002", now_ts=1_000_001, sub_type="leave")
        if not early.deducted or early.total != -4 or points.points("20002", "30001") != -4:
            raise RuntimeError(f"negative invite deduction failed: {early}")
        duplicate = service.record_leave("20002", "30002", now_ts=1_000_002, sub_type="leave")
        if duplicate.deducted or points.points("20002", "30001") != -4:
            raise RuntimeError(f"duplicate leave deducted twice: {duplicate}")
        service.add_record("20002", "30003", "30001", 5, now_ts=2_000_000)
        retained = service.record_leave("20002", "30003", now_ts=2_000_000 + 7 * 86400, sub_type="leave")
        if retained.deducted:
            raise RuntimeError(f"retained member should keep reward: {retained}")
        if service.rebuild_ranking("20002") != 1:
            raise RuntimeError(f"revoked invite leaked back into ranking: {service.records('20002')}")

    print("invites plugin smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

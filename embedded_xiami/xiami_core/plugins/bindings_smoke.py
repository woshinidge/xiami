from __future__ import annotations

from pathlib import Path
import tempfile

from xiami_core.models import SendResult, XiamiMessage
from xiami_core.plugins.bindings import BindingService
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
        source = Path.cwd() / "xiami_plugins" / "bindings"
        plugin_root = root / "plugins"
        plugin_dir = plugin_root / "bindings"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.py").write_text((source / "plugin.py").read_text(encoding="utf-8"), encoding="utf-8")

        ctx = PluginContext(send_fn=send, state_store=PluginKVStore(root / "state"))
        loader = PluginLoader(plugin_root, ctx, state_store=PluginStateStore(root / "enabled.json"))
        plugins = loader.load_all()
        enable_loaded_plugins_for_groups(ctx, plugins, "20001", "20002")
        if not plugins or plugins[0].error:
            raise RuntimeError(f"bindings plugin load failed: {plugins}")
        ctx.state_store.set("permissions", "global_admins", ["10001"])

        msg = lambda sender, text, group_id="20001": XiamiMessage(message_type="group", sender=sender, target=group_id, text=text)
        service = BindingService(plugins[0].context)
        loader.dispatch_message(msg("10005", "绑定 未建区 test-account"))
        service.replace_group("20001::历史旧区", {"10006": "old-account"})
        loader.dispatch_message(msg("10006", "绑定 历史旧区 new-account"))
        service.set_group_label("20001::一区", "一区")
        service.set_group_label("20001::三区", "三区")
        service.set_group_label("20002::二区", "二区")
        service.set_group_label("20001::临时区", "临时区")
        result = service.bind("20001::临时区", "10008", "temp-account")
        if not result.ok:
            raise RuntimeError(result.message)
        result = service.delete_group("20001::临时区", remove_bindings=True)
        if not result.ok:
            raise RuntimeError(result.message)
        loader.dispatch_message(msg("10008", "绑定 临时区 temp-new"))
        loader.dispatch_message(msg("10001", "绑定 一区 a!"))
        loader.dispatch_message(msg("10001", "绑定 一区 account-1"))
        loader.dispatch_message(msg("10001", "我的绑定"))
        loader.dispatch_message(msg("10002", "绑定+一区+account-1"))
        loader.dispatch_message(msg("10001", "我的绑定"))
        loader.dispatch_message(msg("10002", "查询绑定"))
        loader.dispatch_message(msg("10001", "区服列表"))
        loader.dispatch_message(msg("10001", "绑定记录 account"))
        loader.dispatch_message(msg("10001", "导出绑定 account"))
        loader.dispatch_message(msg("10001", "导入绑定 三区|10009|bulk-account\n未建区|10010|bad-account"))
        loader.dispatch_message(msg("10001", "绑定记录 bulk"))
        loader.dispatch_message(msg("10001", "删除绑定 三区 10009"))
        loader.dispatch_message(msg("10004", "绑定 三区 账号xx"))
        loader.dispatch_message(msg("10004", "我的绑定"))
        loader.dispatch_message(msg("10004", "解绑 三区"))
        loader.dispatch_message(msg("10004", "我的绑定"))
        loader.dispatch_message(msg("10002", "解绑"))
        loader.dispatch_message(msg("10002", "我的绑定"))
        before_disabled = len(sent)
        GroupSettingService(ctx).set_enabled("20001", "bindings_enabled", False)
        loader.dispatch_message(msg("10003", "绑定+一区+disabled-account"))
        if len(sent) != before_disabled:
            raise RuntimeError(f"disabled binding group should not reply: {sent}")
        loader.dispatch_message(msg("10003", "绑定+二区+group-20002", "20002"))

        texts = [item[1] for item in sent]
        required = [
            "账号格式不正确，长度 2-32，可包含中文、字母、数字、点、横线、下划线。",
            "绑定成功：一区+account-1 = 10001",
            "当前绑定账号：一区+account-1",
            "本群可绑定区服：一区、三区",
            "三区/10009：解绑成功。",
            "绑定成功：三区+账号xx = 10004",
            "当前绑定账号：三区+账号xx",
            "当前没有绑定账号。",
            "解绑成功：1 个区服。",
        ]
        for item in required:
            if item not in texts:
                raise RuntimeError(f"missing binding reply {item!r}: {texts}")
        if not any(text.startswith("绑定记录：") and "一区：10002 -> account-1" in text for text in texts):
            raise RuntimeError(f"binding records command did not return expected rows: {texts}")
        if not any(text.startswith("绑定导出：") and "一区|10002|account-1" in text for text in texts):
            raise RuntimeError(f"binding export command did not return expected data: {texts}")
        if not any(text.startswith("已导入 1 条，失败 1 条") and "区服未创建" in text for text in texts):
            raise RuntimeError(f"binding import command did not enforce created servers: {texts}")
        if "当前绑定账号：三区+账号xx" in texts[texts.index("当前绑定账号：三区+账号xx") + 1 :]:
            raise RuntimeError(f"specific server unbind should remove 三区 account: {texts}")
        if "绑定成功：二区+group-20002 = 10003" not in texts:
            raise RuntimeError(f"other group binding should still work: {texts}")
        if "区服未创建，请先在账号绑定后台创建区服后再绑定。" not in texts:
            raise RuntimeError(f"uncreated server should be rejected: {texts}")
        if "绑定成功：历史旧区+new-account = 10006" in texts:
            raise RuntimeError(f"legacy bindings without created server should be rejected: {texts}")
        if "绑定成功：临时区+temp-new = 10008" in texts or service.user_for_account("20001::临时区", "temp-account"):
            raise RuntimeError(f"deleted server should reject new bindings and clear old ones: {texts}")
        if service.user_for_account("20001::一区", "account-1"):
            raise RuntimeError("account should be unbound after smoke")
        storage_dir = root / "binding-data"
        result = service.set_storage_dir(str(storage_dir))
        if not result.ok:
            raise RuntimeError(result.message)
        result = service.bind("20002", "10003", "game-10003")
        if not result.ok:
            raise RuntimeError(result.message)
        storage_file = storage_dir / "bindings.json"
        if not storage_file.exists() or "game-10003" not in storage_file.read_text(encoding="utf-8"):
            raise RuntimeError("binding storage directory did not persist bindings.json")

        print("bindings plugin smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

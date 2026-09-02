from __future__ import annotations

from pathlib import Path
import shutil
import tempfile

from xiami_core.models import SendResult, XiamiMessage
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.kv import PluginKVStore
from xiami_core.plugins.loader import PluginLoader
from xiami_core.plugins.state import PluginStateStore
from xiami_core.plugins.test_support import enable_loaded_plugins_for_groups


def main() -> int:
    sent: list[str] = []

    def send(_target: str, text: str, _message_type: str) -> SendResult:
        sent.append(text)
        return SendResult(ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plugin_root = root / "plugins"
        shutil.copytree(Path.cwd() / "xiami_plugins" / "checkin", plugin_root / "checkin")
        (plugin_root / "checkin" / "plugin_config.json").write_text(
            '{"admins":["10001"],"checkin_points":2}', encoding="utf-8"
        )
        ctx = PluginContext(send_fn=send, state_store=PluginKVStore(root / "state"))
        loader = PluginLoader(plugin_root, ctx, state_store=PluginStateStore(root / "enabled.json"))
        plugins = loader.load_all()
        enable_loaded_plugins_for_groups(ctx, plugins)
        if not plugins or plugins[0].error:
            raise RuntimeError(f"checkin plugin load failed: {plugins!r}")

        message = lambda user, text: XiamiMessage(message_type="group", sender=user, target="20001", text=text)
        loader.dispatch_message(message("10002", "签到"))
        loader.dispatch_message(message("10002", "签到"))
        loader.dispatch_message(message("10002", "积分"))
        loader.dispatch_message(message("10001", "设置签到积分 4"))
        loader.dispatch_message(message("10003", "签到"))
        loader.dispatch_message(message("10003", "积分排行"))

        required = (
            "签到成功，积分 +2，当前积分：2。",
            "今天已经签到过了，当前积分：2。",
            "当前积分：2。",
            "已设置本群签到积分：4。",
            "签到成功，积分 +4，当前积分：4。",
        )
        for expected in required:
            if expected not in sent:
                raise RuntimeError(f"missing checkin reply {expected!r}: {sent!r}")
        if not any("积分排行：" in text and "10003: 4" in text for text in sent):
            raise RuntimeError(f"ranking missing: {sent!r}")

    print("checkin plugin smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

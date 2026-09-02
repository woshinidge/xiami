from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from xiami_core.models import SendResult, XiamiMessage
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.loader import PluginLoader
from xiami_core.plugins.state import PluginStateStore
from xiami_core.plugins.statistics import build_plugin_statistics, format_plugin_statistics, plugin_statistics_json


def main() -> int:
    sent: list[str] = []

    def send(_target: str, text: str, _message_type: str) -> SendResult:
        sent.append(text)
        return SendResult(ok=True)

    with TemporaryDirectory() as temp:
        root = Path(temp)
        plugin_dir = root / "stats_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.py").write_text(
            "\n".join(
                [
                    "from xiami_core.plugins.compat import on_command, on_keyword",
                    "PLUGIN_ID = 'stats_plugin'",
                    "PLUGIN_NAME = '统计插件'",
                    "MATCHERS = []",
                    "",
                    "@on_command('/ping', aliases=('ping',), description='Ping 命令')",
                    "def ping(event, ctx, session):",
                    "    ctx.reply(event, 'pong:' + session.argument)",
                    "",
                    "@on_keyword('hello', description='Hello 关键词')",
                    "def hello(event, ctx, session):",
                    "    ctx.reply(event, 'hi')",
                    "",
                    "MATCHERS.extend([ping, hello])",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        loader = PluginLoader(root, PluginContext(send_fn=send), PluginStateStore(root / "enabled.json"))
        loader.load_all()
        loader.dispatch_message(XiamiMessage(message_type="private", sender="10001", text="/ping now"))
        loader.dispatch_message(XiamiMessage(message_type="private", sender="10001", text="say hello"))
        loader.dispatch_message(XiamiMessage(message_type="private", sender="10001", text="noop"))

        stats = build_plugin_statistics(loader)
        summary = stats["summary"]
        if summary["plugin_count"] != 1 or summary["message_count"] != 3:
            raise RuntimeError(f"summary wrong: {summary!r}")
        if summary["handled_total"] != 2 or summary["unhandled_total"] != 1:
            raise RuntimeError(f"hit summary wrong: {summary!r}")
        labels = {item["label"]: item["count"] for item in stats["hot_matchers"]}
        if not any("Ping" in label and count == 1 for label, count in labels.items()):
            raise RuntimeError(f"command heat missing: {labels!r}")
        if not any("Hello" in label and count == 1 for label, count in labels.items()):
            raise RuntimeError(f"keyword heat missing: {labels!r}")
        report = format_plugin_statistics(loader)
        if "命令/规则热度" not in report or "统计插件" not in report:
            raise RuntimeError(f"report missing fields: {report}")
        exported = plugin_statistics_json(loader)
        if '"hot_matchers"' not in exported or "统计插件" not in exported:
            raise RuntimeError(f"json export missing fields: {exported}")
        if sent != ["pong:now", "hi"]:
            raise RuntimeError(f"unexpected replies: {sent!r}")
    print("statistics_smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

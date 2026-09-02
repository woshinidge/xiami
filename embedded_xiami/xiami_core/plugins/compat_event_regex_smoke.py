from __future__ import annotations

import tempfile
from pathlib import Path

from xiami_core.models import SendResult, XiamiMessage
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.events import PluginEvent
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
        plugin_root = root / "plugins"
        plugin_dir = plugin_root / "compat_event_regex"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.py").write_text(
            "\n".join(
                [
                    "from xiami_core.plugins.compat import on_event, on_notice, on_regex, on_request",
                    "PLUGIN_CONFIG = {'admins': ['10001']}",
                    "MATCHERS = []",
                    "EVENT_MATCHERS = []",
                    "@on_regex(r'^查(.+)$', description='正则查询')",
                    "def regex_cmd(event, ctx, session):",
                    "    ctx.reply(event, 'regex:' + session.match.group(1))",
                    "@on_notice('group_increase', description='入群通知')",
                    "def notice_handler(event, ctx, session):",
                    "    ctx.send_group(session.group_id, 'notice:' + session.user_id)",
                    "@on_request('friend', admin_only=True, description='好友请求')",
                    "def request_handler(event, ctx, session):",
                    "    ctx.send_private(session.user_id, 'request:' + session.event_type)",
                    "@on_event('message', event_type='private', description='私聊原始事件')",
                    "def private_event(event, ctx, session):",
                    "    ctx.send_private(session.user_id, 'event:' + event.text)",
                    "MATCHERS.append(regex_cmd)",
                    "EVENT_MATCHERS.extend([notice_handler, request_handler, private_event])",
                ]
            ),
            encoding="utf-8",
        )

        ctx = PluginContext(send_fn=send)
        loader = PluginLoader(plugin_root, ctx, state_store=PluginStateStore(root / "state.json"))
        plugins = loader.load_all()
        enable_loaded_plugins_for_groups(ctx, plugins, "20001", "30001")
        if len(plugins) != 1 or plugins[0].error:
            raise RuntimeError(f"plugin load failed: {plugins}")
        commands = "\n".join(plugins[0].commands)
        if (
            "正则:^查(.+)$ - 正则查询" not in commands
            or "事件:notice/group_increase - 入群通知" not in commands
            or "事件:message/private - 私聊原始事件" not in commands
        ):
            raise RuntimeError(f"compat labels missing: {commands}")

        loader.dispatch_message(XiamiMessage(message_type="private", sender="20001", text="查天气"))
        loader.dispatch_event(
            PluginEvent(
                type="notice",
                raw={"post_type": "notice", "notice_type": "group_increase", "group_id": 30001, "user_id": 20002},
            )
        )
        loader.dispatch_event(
            PluginEvent(type="request", raw={"post_type": "request", "request_type": "friend", "user_id": 20003})
        )
        loader.dispatch_event(
            PluginEvent(type="request", raw={"post_type": "request", "request_type": "friend", "user_id": 10001})
        )
        loader.dispatch_event(
            PluginEvent(
                type="message",
                message=XiamiMessage(message_type="private", sender="20004", text="raw hi"),
                raw={"post_type": "message", "message_type": "private", "user_id": 20004},
            )
        )

        expected = [
            ("20001", "regex:天气", "private"),
            ("30001", "notice:20002", "group"),
            ("10001", "request:friend", "private"),
            ("20004", "event:raw hi", "private"),
        ]
        if sent != expected:
            raise RuntimeError(f"compat event regex failed: {sent!r}; errors={plugins[0].error_history!r}")
    print("plugin compat event regex smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

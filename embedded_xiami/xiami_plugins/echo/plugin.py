from __future__ import annotations

PLUGIN_NAME = "Echo"
PLUGIN_VERSION = "1.0.0"
PLUGIN_DESCRIPTION = "回复 /echo 后面的文本，用于验证插件加载、消息分发和发送闭环。"


def on_load(ctx) -> None:
    ctx.log("Echo 插件已加载")


def on_message(event, ctx) -> None:
    if event.text.startswith("/echo "):
        ctx.reply(event, event.text[len("/echo "):].strip())

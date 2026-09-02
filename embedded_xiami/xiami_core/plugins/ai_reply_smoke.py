from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from xiami_core.messages import MessageRecord
from xiami_core.models import MessageSegment, SendResult, XiamiMessage
from xiami_core.plugins.ai_reply import LocalAiOrchestrator
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.knowledge import KnowledgeService
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
        plugin_root = root / "plugins"
        plugin_dir = plugin_root / "ai_reply"
        plugin_dir.mkdir(parents=True)
        shutil.copyfile(Path.cwd() / "xiami_plugins" / "ai_reply" / "plugin.py", plugin_dir / "plugin.py")
        (plugin_dir / "plugin_config.json").write_text('{"bot_qq":"10000","admins":["10001"]}', encoding="utf-8")

        ctx = PluginContext(send_fn=send, state_store=PluginKVStore(root / "state"))
        KnowledgeService(ctx.for_plugin("knowledge")).add_document(
            "xiami.md",
            "Xiami 主程序托管 NapCat 登录内核，并通过 OneBot 收发 QQ 消息。",
            title="Xiami 登录",
            tags=("NapCat", "OneBot"),
        )

        loader = PluginLoader(plugin_root, ctx, state_store=PluginStateStore(root / "enabled.json"))
        plugins = loader.load_all()
        enable_loaded_plugins_for_groups(ctx, plugins)
        if not plugins or plugins[0].error:
            raise RuntimeError(f"ai_reply plugin load failed: {plugins}")

        loader.dispatch_message(
            XiamiMessage(message_type="private", sender="10001", target="10001", text="问 NapCat")
        )
        loader.dispatch_message(
            XiamiMessage(message_type="private", sender="10001", target="10001", text="AI状态")
        )
        loader.dispatch_message(
            XiamiMessage(message_type="private", sender="10001", target="10001", text="AI自检")
        )
        loader.dispatch_message(
            XiamiMessage(message_type="private", sender="10001", target="10001", text="AI试连")
        )
        loader.dispatch_message(
            XiamiMessage(message_type="private", sender="10001", target="10001", text="AI提示词 QQ消息")
        )
        loader.dispatch_message(
            XiamiMessage(message_type="private", sender="10001", target="10001", text="问 不存在的问题")
        )
        before_other_at = len(sent)
        loader.dispatch_message(
            XiamiMessage(
                message_type="group",
                sender="10001",
                target="20001",
                text="@99999 NapCat",
                raw_message="[CQ:at,qq=99999] NapCat",
                segments=(
                    MessageSegment("at", {"qq": "99999"}),
                    MessageSegment("text", {"text": " NapCat"}),
                ),
            )
        )
        if len(sent) != before_other_at:
            raise RuntimeError(f"ai replied to unrelated at: {sent[before_other_at:]}")
        loader.dispatch_message(
            XiamiMessage(
                message_type="group",
                sender="10001",
                target="20001",
                text="@10000 NapCat",
                raw_message="[CQ:at,qq=10000] NapCat",
                segments=(
                    MessageSegment("at", {"qq": "10000"}),
                    MessageSegment("text", {"text": " NapCat"}),
                ),
            )
        )
        loader.dispatch_message(
            XiamiMessage(message_type="group", sender="10001", target="20001", text="AI设置")
        )
        loader.dispatch_message(
            XiamiMessage(message_type="group", sender="10001", target="20001", text="关闭普通聊天")
        )
        before_group_ordinary_off = len(sent)
        loader.dispatch_message(
            XiamiMessage(
                message_type="group",
                sender="10001",
                target="20001",
                text="@10000 NapCat",
                raw_message="[CQ:at,qq=10000] NapCat",
                segments=(
                    MessageSegment("at", {"qq": "10000"}),
                    MessageSegment("text", {"text": " NapCat"}),
                ),
            )
        )
        if len(sent) != before_group_ordinary_off:
            raise RuntimeError(f"ai replied while group ordinary chat disabled: {sent[before_group_ordinary_off:]}")
        loader.dispatch_message(
            XiamiMessage(message_type="group", sender="10001", target="20001", text="开启普通聊天")
        )
        loader.dispatch_message(
            XiamiMessage(message_type="group", sender="10001", target="20001", text="关闭AI艾特")
        )
        before_group_at_off = len(sent)
        loader.dispatch_message(
            XiamiMessage(
                message_type="group",
                sender="10001",
                target="20001",
                text="@10000 NapCat",
                raw_message="[CQ:at,qq=10000] NapCat",
                segments=(
                    MessageSegment("at", {"qq": "10000"}),
                    MessageSegment("text", {"text": " NapCat"}),
                ),
            )
        )
        if len(sent) != before_group_at_off:
            raise RuntimeError(f"ai replied while group @ trigger disabled: {sent[before_group_at_off:]}")
        loader.dispatch_message(
            XiamiMessage(message_type="group", sender="10001", target="20001", text="开启AI艾特")
        )
        loader.dispatch_message(
            XiamiMessage(message_type="group", sender="10001", target="20001", text="关闭AI回答")
        )
        before_group_ai_off = len(sent)
        loader.dispatch_message(
            XiamiMessage(message_type="group", sender="10001", target="20001", text="问 NapCat")
        )
        if len(sent) != before_group_ai_off:
            raise RuntimeError(f"ai replied while group ai disabled: {sent[before_group_ai_off:]}")
        loader.dispatch_message(
            XiamiMessage(message_type="group", sender="10001", target="20001", text="开启AI回答")
        )
        loader.dispatch_message(
            XiamiMessage(message_type="group", sender="10001", target="20001", text="设置机器人QQ 10000")
        )

        plugin_root_self = root / "plugins_self_id"
        plugin_dir_self = plugin_root_self / "ai_reply"
        plugin_dir_self.mkdir(parents=True)
        shutil.copyfile(Path.cwd() / "xiami_plugins" / "ai_reply" / "plugin.py", plugin_dir_self / "plugin.py")
        (plugin_dir_self / "plugin_config.json").write_text('{"ordinary_chat_enabled":true}', encoding="utf-8")
        self_ctx = PluginContext(
            send_fn=send,
            state_store=PluginKVStore(root / "state_self_id"),
            config={"self_id": "10000"},
        )
        self_loader = PluginLoader(plugin_root_self, self_ctx, state_store=PluginStateStore(root / "enabled_self_id.json"))
        self_plugins = self_loader.load_all()
        enable_loaded_plugins_for_groups(self_ctx, self_plugins)
        if not self_plugins or self_plugins[0].error:
            raise RuntimeError(f"ai self_id plugin load failed: {self_plugins}")
        before_self_id_at = len(sent)
        self_loader.dispatch_message(
            XiamiMessage(
                message_type="group",
                sender="10001",
                target="20001",
                text="@10000 NapCat",
                raw_message="[CQ:at,qq=10000] NapCat",
                self_id="10000",
                segments=(
                    MessageSegment("at", {"qq": "10000"}),
                    MessageSegment("text", {"text": " NapCat"}),
                ),
            )
        )
        if len(sent) <= before_self_id_at:
            raise RuntimeError("ai did not reply to self_id based @ message")

        plugin_root_disabled = root / "plugins_disabled"
        plugin_dir_disabled = plugin_root_disabled / "ai_reply"
        plugin_dir_disabled.mkdir(parents=True)
        shutil.copyfile(Path.cwd() / "xiami_plugins" / "ai_reply" / "plugin.py", plugin_dir_disabled / "plugin.py")
        (plugin_dir_disabled / "plugin_config.json").write_text(
            '{"bot_qq":"10000","ordinary_chat_enabled":false}',
            encoding="utf-8",
        )
        disabled_ctx = PluginContext(send_fn=send, state_store=PluginKVStore(root / "state_disabled"))
        disabled_loader = PluginLoader(
            plugin_root_disabled,
            disabled_ctx,
            state_store=PluginStateStore(root / "enabled_disabled.json"),
        )
        disabled_plugins = disabled_loader.load_all()
        enable_loaded_plugins_for_groups(disabled_ctx, disabled_plugins)
        if not disabled_plugins or disabled_plugins[0].error:
            raise RuntimeError(f"ai disabled plugin load failed: {disabled_plugins}")
        before_disabled_at = len(sent)
        disabled_loader.dispatch_message(
            XiamiMessage(
                message_type="group",
                sender="10001",
                target="20001",
                text="@10000 NapCat",
                raw_message="[CQ:at,qq=10000] NapCat",
                self_id="10000",
                segments=(
                    MessageSegment("at", {"qq": "10000"}),
                    MessageSegment("text", {"text": " NapCat"}),
                ),
            )
        )
        if len(sent) != before_disabled_at:
            raise RuntimeError(f"ai replied while ordinary chat disabled: {sent[before_disabled_at:]}")

        combined = "\n".join(item[1] for item in sent)
        for expected in [
            "本地知识库参考",
            "Xiami 登录",
            "Provider",
            "AI 自检",
            "AI 试连",
            "本地知识库可检索",
            "问题：QQ消息",
            "暂无相关内容",
            "OneBot",
            "AI 群设置",
            "已关闭本群普通聊天回复。",
            "已开启本群普通聊天回复。",
            "已关闭本群@机器人触发。",
            "已开启本群@机器人触发。",
            "已关闭本群AI回答。",
            "已开启本群AI回答。",
            "机器人QQ已设置：10000。",
        ]:
            if expected not in combined:
                raise RuntimeError(f"ai reply output missing {expected!r}: {combined}")

        diagnostic = loader.diagnostics()[0]
        capabilities = diagnostic.get("capabilities") or []
        if (
            "ai:local-orchestrator" not in capabilities
        or "ai:openai-compatible" not in capabilities
        or "ai:provider-probe" not in capabilities
        or "ai:provider-diagnostics" not in capabilities
        or "ai:tool-calls" not in capabilities
        or "ai:streaming" not in capabilities
        or "ai:audit-log" not in capabilities
        or "knowledge:search" not in capabilities
            or "message:at-bot" not in capabilities
        ):
            raise RuntimeError(f"ai capabilities missing: {diagnostic!r}")

        schema = {item.get("key"): item for item in diagnostic.get("config_schema") or []}
        if not schema.get("api_key", {}).get("secret"):
            raise RuntimeError(f"ai config schema missing api_key secret: {diagnostic!r}")
        provider_choices = set(schema.get("provider", {}).get("choices") or [])
        if "openai_compatible" not in provider_choices or "local_knowledge" not in provider_choices or "deepseek" not in provider_choices:
            raise RuntimeError(f"ai provider choices missing: {diagnostic!r}")
        if schema.get("show_sources", {}).get("type") != "bool":
            raise RuntimeError(f"ai show_sources schema missing: {diagnostic!r}")
        if schema.get("enable_tools", {}).get("type") != "bool":
            raise RuntimeError(f"ai enable_tools schema missing: {diagnostic!r}")
        if schema.get("ordinary_chat_enabled", {}).get("type") != "bool":
            raise RuntimeError(f"ai ordinary_chat_enabled schema missing: {diagnostic!r}")
    if schema.get("enable_stream", {}).get("type") != "bool":
        raise RuntimeError(f"ai enable_stream schema missing: {diagnostic!r}")
    if schema.get("retries", {}).get("type") != "int":
        raise RuntimeError(f"ai retries schema missing: {diagnostic!r}")
    if schema.get("retry_delay", {}).get("type") != "float":
        raise RuntimeError(f"ai retry_delay schema missing: {diagnostic!r}")
    if schema.get("audit_enabled", {}).get("type") != "bool":
        raise RuntimeError(f"ai audit_enabled schema missing: {diagnostic!r}")
    if schema.get("audit_question_preview", {}).get("type") != "bool":
        raise RuntimeError(f"ai audit_question_preview schema missing: {diagnostic!r}")

        openai_ctx = ctx.for_plugin(
            "ai_reply",
            config={
                "provider": "openai",
                "api_key": "test-key",
                "model": "test-model",
            },
        )
        openai_health = LocalAiOrchestrator(openai_ctx).health_check()
        if "远程模型配置完整" not in openai_health or "base_url" in openai_health:
            raise RuntimeError(f"openai provider preset health failed: {openai_health}")

        model_ctx = ctx.for_plugin(
            "ai_reply",
            config={
                "provider": "openai_compatible",
                "base_url": "http://127.0.0.1:9999/v1",
                "api_key": "test-key",
                "model": "test-model",
                "knowledge_limit": 2,
                "show_sources": True,
                "retries": 1,
                "retry_delay": 0.0,
            },
        )

        def transport(url, payload, headers, timeout):
            if not url.endswith("/chat/completions"):
                raise RuntimeError(f"bad model url: {url}")
            if payload.get("model") != "test-model":
                raise RuntimeError(f"bad model payload: {payload}")
            if headers.get("Authorization") != "Bearer test-key":
                raise RuntimeError(f"bad model headers: {headers}")
            return {"choices": [{"message": {"content": "模型已读取知识库上下文"}}]}

        model_result = LocalAiOrchestrator(model_ctx, transport=transport).answer("NapCat", limit=2)
        if not model_result.ok or "模型已读取知识库上下文" not in model_result.text:
            raise RuntimeError(f"ai model reply failed: {model_result}")
        if "参考来源：" not in model_result.text or "xiami.md" not in model_result.text or "score=" not in model_result.text:
            raise RuntimeError(f"ai model sources missing: {model_result.text}")

        stream_payloads: list[dict[str, object]] = []

        def stream_transport(url, payload, headers, timeout):
            stream_payloads.append(payload)
            yield 'data: {"choices":[{"delta":{"content":"流式"}}]}'
            yield 'data: {"choices":[{"delta":{"content":"编排"}}]}'
            yield "data: [DONE]"

        stream_result = LocalAiOrchestrator(model_ctx, stream_transport=stream_transport).stream_answer("NapCat", limit=2)
        if not stream_result.ok or "流式编排" not in stream_result.text:
            raise RuntimeError(f"ai stream reply failed: {stream_result}")
        if not stream_payloads or stream_payloads[0].get("stream") is not True:
            raise RuntimeError(f"ai stream payload missing: {stream_payloads}")

        audit_report = LocalAiOrchestrator(model_ctx).audit_report()
        if "AI 模型调用审计" not in audit_report or "answer" not in audit_report or "stream" not in audit_report:
            raise RuntimeError(f"ai audit report missing calls: {audit_report}")
        if "NapCat" in audit_report:
            raise RuntimeError(f"ai audit report leaked question preview while disabled: {audit_report}")

        status_text = LocalAiOrchestrator(model_ctx).status()
        if "失败重试：1 次" not in status_text:
            raise RuntimeError(f"ai retry status missing: {status_text}")
        provider_report = LocalAiOrchestrator(model_ctx).provider_report()
        if "AI Provider 诊断" not in provider_report or "Chat URL：http://127.0.0.1:9999/v1/chat/completions" not in provider_report:
            raise RuntimeError(f"ai provider report missing: {provider_report}")

        probe_text = LocalAiOrchestrator(model_ctx, transport=transport).probe_provider()
        if "AI 试连成功" not in probe_text or "test-model" not in probe_text:
            raise RuntimeError(f"ai provider probe failed: {probe_text}")

        tool_payloads: list[dict[str, object]] = []

        def tool_transport(url, payload, headers, timeout):
            tool_payloads.append(payload)
            messages = payload.get("messages") if isinstance(payload, dict) else []
            if isinstance(messages, list) and any(isinstance(item, dict) and item.get("role") == "tool" for item in messages):
                return {"choices": [{"message": {"content": "工具结果已用于回答 NapCat。"}}]}
            if "tools" not in payload:
                raise RuntimeError(f"tools missing from first tool-call request: {payload}")
            return {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "call_knowledge",
                                    "type": "function",
                                    "function": {
                                        "name": "knowledge_search",
                                        "arguments": "{\"query\":\"NapCat\",\"limit\":2}",
                                    },
                                }
                            ]
                        }
                    }
                ]
            }

        tool_result = LocalAiOrchestrator(model_ctx, transport=tool_transport).answer("NapCat", limit=2)
        if not tool_result.ok or "工具结果已用于回答" not in tool_result.text:
            raise RuntimeError(f"ai tool call reply failed: {tool_result}")
        if len(tool_payloads) != 2:
            raise RuntimeError(f"ai tool call did not perform two provider calls: {tool_payloads}")
        second_messages = tool_payloads[1].get("messages")
        if not isinstance(second_messages, list) or not any(isinstance(item, dict) and item.get("role") == "tool" for item in second_messages):
            raise RuntimeError(f"ai tool result message missing: {tool_payloads[1]}")

        history_rows = [
            MessageRecord(direction="incoming", message_type="private", target="10001", sender="10001", text="之前说 NapCat 负责扫码登录。"),
            MessageRecord(direction="outgoing", message_type="private", target="10001", text="我会结合本地知识回答。"),
            MessageRecord(direction="incoming", message_type="private", target="10001", sender="10001", text="继续说明"),
        ]
        history_ctx = PluginContext(
            send_fn=send,
            state_store=PluginKVStore(root / "history_state"),
            history_fn=lambda event, limit: history_rows[-limit:],
        )
        KnowledgeService(history_ctx.for_plugin("knowledge")).add_document(
            "history.md",
            "NapCat 作为 Xiami 的 QQ 登录和 OneBot 内核。",
            title="历史上下文",
        )
        history_result = LocalAiOrchestrator(history_ctx).answer(
            "继续说明",
            limit=1,
            event=XiamiMessage(message_type="private", sender="10001", target="10001", text="继续说明"),
            history_limit=3,
        )
        if "最近会话上下文" not in history_result.prompt or "之前说 NapCat" not in history_result.prompt:
            raise RuntimeError(f"ai history prompt missing context: {history_result.prompt}")
        if "[H" in history_result.prompt and "继续说明: 继续说明" in history_result.prompt:
            raise RuntimeError(f"ai history prompt duplicated current question: {history_result.prompt}")

    print("ai_reply_smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

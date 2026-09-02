from __future__ import annotations

from xiami_core.plugins.ai_provider import OPENAI_COMPATIBLE_PROVIDERS
from xiami_core.plugins.ai_reply import LocalAiOrchestrator
from xiami_core.plugins.compat import on_command
from xiami_core.plugins.group_settings import GroupSettingService
from xiami_core.plugins.permissions import PluginPermissionService, parse_user_ids


PLUGIN_ID = "ai_reply"
PLUGIN_NAME = "AI 知识问答"
PLUGIN_VERSION = "0.5.0"
PLUGIN_DESCRIPTION = "提供本地知识库和会话历史增强回复，并可接入 OpenAI-compatible AI 模型。"
PLUGIN_MIGRATION_STATUS = "Xiami 原生接入"
PLUGIN_CAPABILITIES = [
    "ai:local-orchestrator",
    "ai:openai-compatible",
    "ai:provider-probe",
    "ai:provider-diagnostics",
    "ai:tool-calls",
    "ai:streaming",
    "ai:audit-log",
    "ai:conversation-context",
    "knowledge:search",
    "message:at-bot",
    "message-matchers:8",
]
PLUGIN_CONFIG = {
    "knowledge_limit": 3,
    "history_limit": 6,
    "provider": "local_knowledge",
    "base_url": "",
    "api_key": "",
    "model": "",
    "temperature": 0.2,
    "max_tokens": 800,
    "timeout": 90,
    "retries": 1,
    "retry_delay": 0.5,
    "show_prompt": False,
    "show_sources": False,
    "enable_tools": True,
    "enable_stream": False,
    "audit_enabled": True,
    "audit_question_preview": False,
    "ordinary_chat_enabled": True,
    "at_bot_enabled": True,
    "bot_qq": "",
    "game_servers": {},
}
PLUGIN_CONFIG_SCHEMA = [
    {
        "key": "knowledge_limit",
        "label": "知识检索条数",
        "type": "int",
        "required": True,
        "description": "每次回答最多检索的本地知识片段数量。",
    },
    {
        "key": "history_limit",
        "label": "会话历史条数",
        "type": "int",
        "description": "构造提示词时带入的最近同会话消息数量。",
    },
    {
        "key": "provider",
        "label": "AI Provider",
        "type": "str",
        "required": True,
        "choices": ["local_knowledge", *sorted(OPENAI_COMPATIBLE_PROVIDERS)],
        "description": "local_knowledge 使用本地知识库降级回复；其他选项使用 OpenAI-compatible 接口。",
    },
    {
        "key": "base_url",
        "label": "AI Base URL",
        "type": "str",
        "description": "provider 为 openai/deepseek/kimi/moonshot/openrouter/dashscope 时可留空并自动使用预设地址；自定义 OpenAI-compatible 服务需要填写。",
    },
    {"key": "api_key", "label": "AI API Key", "type": "str", "secret": True, "description": "模型访问令牌。"},
    {"key": "model", "label": "AI 模型", "type": "str", "description": "远程模型名称。"},
    {"key": "temperature", "label": "温度", "type": "float"},
    {"key": "max_tokens", "label": "最大输出 Tokens", "type": "int"},
{"key": "timeout", "label": "请求超时秒数", "type": "int"},
{"key": "retries", "label": "失败重试次数", "type": "int"},
{"key": "retry_delay", "label": "重试间隔秒数", "type": "float"},
{"key": "show_prompt", "label": "显示提示词", "type": "bool"},
{"key": "show_sources", "label": "显示知识来源", "type": "bool"},
{"key": "enable_tools", "label": "启用 AI 工具调用", "type": "bool"},
{"key": "enable_stream", "label": "启用流式 Provider", "type": "bool"},
{"key": "audit_enabled", "label": "记录模型调用审计", "type": "bool"},
{"key": "audit_question_preview", "label": "审计记录问题预览", "type": "bool"},
{"key": "ordinary_chat_enabled", "label": "普通聊天回复", "type": "bool", "description": "开启后，群内 @ 机器人并发送普通问题时自动回复；关闭后只响应显式命令。"},
{"key": "at_bot_enabled", "label": "群聊 @ 触发", "type": "bool"},
{"key": "bot_qq", "label": "机器人 QQ", "type": "str", "description": "填写后只响应指定 QQ；为空时需由 self_id/账号配置提供机器人 ID。"},
{"key": "game_servers", "label": "本群区服列表", "type": "dict", "description": "按群保存 AI 回答可用的区服名称和服务端路径。"},
]
PLUGIN_ADMIN_SCHEMA = [
    {"id": "knowledge_limit", "label": "知识检索条数", "type": "config", "config_key": "knowledge_limit"},
    {"id": "history_limit", "label": "会话历史条数", "type": "config", "config_key": "history_limit"},
    {"id": "provider", "label": "AI Provider", "type": "config", "config_key": "provider"},
    {"id": "base_url", "label": "AI Base URL", "type": "config", "config_key": "base_url"},
    {"id": "api_key", "label": "AI API Key", "type": "config", "config_key": "api_key"},
    {"id": "model", "label": "AI 模型", "type": "config", "config_key": "model"},
    {"id": "temperature", "label": "温度", "type": "config", "config_key": "temperature"},
    {"id": "max_tokens", "label": "最大输出 Tokens", "type": "config", "config_key": "max_tokens"},
{"id": "timeout", "label": "请求超时秒数", "type": "config", "config_key": "timeout"},
{"id": "retries", "label": "失败重试次数", "type": "config", "config_key": "retries"},
{"id": "retry_delay", "label": "重试间隔秒数", "type": "config", "config_key": "retry_delay"},
{"id": "show_prompt", "label": "显示提示词", "type": "config", "config_key": "show_prompt"},
{"id": "enable_tools", "label": "启用 AI 工具调用", "type": "config", "config_key": "enable_tools"},
{"id": "enable_stream", "label": "启用流式 Provider", "type": "config", "config_key": "enable_stream"},
{"id": "audit_enabled", "label": "记录模型调用审计", "type": "config", "config_key": "audit_enabled"},
{"id": "audit_question_preview", "label": "审计记录问题预览", "type": "config", "config_key": "audit_question_preview"},
{"id": "ordinary_chat_enabled", "label": "普通聊天回复", "type": "config", "config_key": "ordinary_chat_enabled", "commands": ["开启普通聊天", "关闭普通聊天"]},
{"id": "at_bot_enabled", "label": "群聊 @ 触发", "type": "config", "config_key": "at_bot_enabled", "commands": ["开启AI艾特", "关闭AI艾特"]},
{"id": "bot_qq", "label": "机器人 QQ", "type": "config", "config_key": "bot_qq"},
{"id": "game_servers", "label": "本群区服", "type": "config", "config_key": "game_servers"},
{
        "id": "ai_health",
        "label": "AI 自检结果",
        "type": "runtime",
        "runtime_key": "health",
        "commands": ["AI自检", "AI状态"],
    },
    {
        "id": "ai_audit",
        "label": "AI 调用审计",
        "type": "runtime",
        "runtime_key": "audit",
        "commands": ["AI审计"],
    },
    {
        "id": "ai_provider",
        "label": "AI Provider 诊断",
        "type": "runtime",
        "runtime_key": "provider",
        "commands": ["AI供应商"],
    },
]
PLUGIN_ADMIN_HANDLERS = {
    "health": lambda ctx: LocalAiOrchestrator(ctx).health_check(),
    "audit": lambda ctx: LocalAiOrchestrator(ctx).audit_report(),
    "provider": lambda ctx: LocalAiOrchestrator(ctx).provider_report(),
}

MATCHERS = []


def on_load(ctx) -> None:
    ctx.log("AI 知识问答插件已加载")


def on_message(event, ctx) -> None:
    if not _ordinary_chat_enabled(event, ctx):
        return
    if not _ai_reply_enabled(event, ctx):
        return
    question = _at_bot_question(event, ctx)
    if question:
        _answer(event, ctx, question)


@on_command("问", aliases=("AI ", "ai "), description="问 <问题>，用本地知识库生成参考回复")
def ask(event, ctx, session) -> None:
    if not _ai_reply_enabled(event, ctx):
        return
    _answer(event, ctx, session.argument)


@on_command("AI流式", aliases=("ai流式",), description="AI流式 <问题>，使用 OpenAI-compatible 流式接口收集回复")
def ai_stream(event, ctx, session) -> None:
    if not _ai_reply_enabled(event, ctx):
        return
    _answer(event, ctx, session.argument, stream=True)


@on_command("AI审计", aliases=("ai审计", "AI调用日志", "ai调用日志"), description="查看最近 AI 模型调用审计")
def ai_audit(event, ctx, session) -> None:
    ctx.reply(event, LocalAiOrchestrator(ctx).audit_report())


@on_command("AI供应商", aliases=("ai供应商", "AI提供商", "ai提供商", "AI诊断", "ai诊断"), description="查看 AI Provider 配置与能力诊断")
def ai_provider(event, ctx, session) -> None:
    ctx.reply(event, LocalAiOrchestrator(ctx).provider_report())


@on_command("AI设置", aliases=("AI群设置", "AI回复设置"), only_group=True, description="查看本群 AI 回复开关")
def ai_group_settings(event, ctx, session) -> None:
    service = GroupSettingService(ctx)
    ctx.reply(
        event,
        "\n".join(
            [
                "AI 群设置：",
                f"AI回答：{'开启' if service.enabled(session.group_id, 'ai_reply_enabled') else '关闭'}",
                f"普通聊天：{'开启' if service.enabled(session.group_id, 'ai_ordinary_chat_enabled') else '关闭'}",
                f"@机器人触发：{'开启' if service.enabled(session.group_id, 'ai_at_bot_enabled') else '关闭'}",
                f"机器人QQ：{_bot_id(ctx) or '未设置'}",
                f"Provider：{ctx.get_config('provider', 'local_knowledge')}",
                f"Model：{ctx.get_config('model', '') or '未配置'}",
            ]
        ),
    )


@on_command("开启AI回答", aliases=("开启AI",), only_group=True, description="开启本群 AI 回答")
def enable_ai_reply(event, ctx, session) -> None:
    _set_ai_bool(event, ctx, session, "ai_reply_enabled", True, "AI回答")


@on_command("关闭AI回答", aliases=("关闭AI",), only_group=True, description="关闭本群 AI 回答")
def disable_ai_reply(event, ctx, session) -> None:
    _set_ai_bool(event, ctx, session, "ai_reply_enabled", False, "AI回答")


@on_command("开启普通聊天", aliases=("开启AI普通聊天",), only_group=True, description="开启本群 @机器人普通聊天回复")
def enable_ordinary_chat(event, ctx, session) -> None:
    _set_ai_bool(event, ctx, session, "ai_ordinary_chat_enabled", True, "普通聊天回复")


@on_command("关闭普通聊天", aliases=("关闭AI普通聊天",), only_group=True, description="关闭本群 @机器人普通聊天回复")
def disable_ordinary_chat(event, ctx, session) -> None:
    _set_ai_bool(event, ctx, session, "ai_ordinary_chat_enabled", False, "普通聊天回复")


@on_command("开启AI艾特", aliases=("开启AI@", "开启@机器人"), only_group=True, description="开启本群 @机器人触发")
def enable_at_bot(event, ctx, session) -> None:
    _set_ai_bool(event, ctx, session, "ai_at_bot_enabled", True, "@机器人触发")


@on_command("关闭AI艾特", aliases=("关闭AI@", "关闭@机器人"), only_group=True, description="关闭本群 @机器人触发")
def disable_at_bot(event, ctx, session) -> None:
    _set_ai_bool(event, ctx, session, "ai_at_bot_enabled", False, "@机器人触发")


@on_command("设置机器人QQ", aliases=("机器人QQ",), description="设置机器人QQ <QQ>")
def set_bot_qq(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    user_ids = parse_user_ids(session.argument)
    if not user_ids:
        ctx.reply(event, "格式：设置机器人QQ <QQ>")
        return
    ctx.set_state("bot_qq", user_ids[0])
    ctx.reply(event, f"机器人QQ已设置：{user_ids[0]}。")


def _ai_reply_enabled(event, ctx) -> bool:
    if getattr(event, "message_type", "") != "group":
        return True
    return GroupSettingService(ctx).enabled(getattr(event, "target", ""), "ai_reply_enabled")


def _ordinary_chat_enabled(event, ctx) -> bool:
    if getattr(event, "message_type", "") != "group":
        return bool(ctx.get_config("ordinary_chat_enabled", True))
    return GroupSettingService(ctx).enabled(getattr(event, "target", ""), "ai_ordinary_chat_enabled")


def _at_bot_enabled(event, ctx) -> bool:
    if getattr(event, "message_type", "") != "group":
        return bool(ctx.get_config("at_bot_enabled", True))
    return GroupSettingService(ctx).enabled(getattr(event, "target", ""), "ai_at_bot_enabled")


def _answer(event, ctx, question: str, *, stream: bool = False) -> None:
    orchestrator = LocalAiOrchestrator(ctx)
    answer = orchestrator.stream_answer if stream or bool(ctx.get_config("enable_stream", False)) else orchestrator.answer
    result = answer(
        question,
        limit=int(ctx.get_config("knowledge_limit", 3) or 3),
        event=event,
        history_limit=int(ctx.get_config("history_limit", 6) or 0),
    )
    text = result.text
    if ctx.get_config("show_prompt", False) and result.prompt:
        text = f"{text}\n\nPrompt:\n{result.prompt}"
    ctx.reply(event, text)


@on_command("AI状态", aliases=("ai状态",), description="查看 AI 知识问答状态")
def ai_status(event, ctx, session) -> None:
    ctx.reply(event, LocalAiOrchestrator(ctx).status())


@on_command("AI自检", aliases=("ai自检", "AI检查", "ai检查"), description="检查 AI Provider 和知识库配置")
def ai_health(event, ctx, session) -> None:
    ctx.reply(event, LocalAiOrchestrator(ctx).health_check())


@on_command("AI试连", aliases=("ai试连", "AI连通", "ai连通"), description="试连远程 AI Provider")
def ai_probe(event, ctx, session) -> None:
    ctx.reply(event, LocalAiOrchestrator(ctx).probe_provider())


@on_command("AI提示词", aliases=("提示词",), description="AI提示词 <问题>，查看本地知识增强提示词")
def ai_prompt(event, ctx, session) -> None:
    result = LocalAiOrchestrator(ctx).answer(
        session.argument,
        limit=int(ctx.get_config("knowledge_limit", 3) or 3),
        event=event,
        history_limit=int(ctx.get_config("history_limit", 6) or 0),
    )
    ctx.reply(event, result.prompt or "请输入问题。")


def _at_bot_question(event, ctx) -> str:
    if not _at_bot_enabled(event, ctx):
        return ""
    if getattr(event, "message_type", "") != "group":
        return ""
    bot_qq = _bot_id(ctx)
    if not bot_qq and not str(getattr(event, "self_id", "") or "").strip():
        return ""
    mentioned = bool(ctx.is_at_me(event, bot_qq or None))
    question = ctx.strip_at(event, bot_qq).strip() if bot_qq else ctx.strip_at(event).strip()
    if not mentioned and bot_qq:
        raw = str(getattr(event, "raw_message", "") or getattr(event, "text", "") or "")
        marker = f"[CQ:at,qq={bot_qq}]"
        if marker in raw:
            mentioned = True
            question = raw.replace(marker, " ").strip()
    if not mentioned:
        return ""
    return question or str(getattr(event, "text", "") or "").strip()


def _bot_id(ctx) -> str:
    for key in ("bot_qq", "self_id", "qq", "account"):
        value = str(ctx.get_config(key, "") or "").strip()
        if value:
            return value
    try:
        state_value = str(ctx.get_state("bot_qq", "") or "").strip()
        if state_value:
            return state_value
    except Exception:
        pass
    return ""


def _require_admin(event, ctx, session) -> bool:
    ok, reason = PluginPermissionService(ctx).require_admin(session.user_id, session.group_id)
    if not ok:
        ctx.reply(event, reason)
        return False
    return True


def _set_ai_bool(event, ctx, session, key: str, enabled: bool, label: str) -> None:
    if not _require_admin(event, ctx, session):
        return
    GroupSettingService(ctx).set_enabled(session.group_id, key, enabled)
    ctx.reply(event, f"已{'开启' if enabled else '关闭'}本群{label}。")


MATCHERS.extend([
    ai_status,
    ai_health,
    ai_probe,
    ai_prompt,
    ask,
    ai_stream,
    ai_audit,
    ai_provider,
    ai_group_settings,
    enable_ai_reply,
    disable_ai_reply,
    enable_ordinary_chat,
    disable_ordinary_chat,
    enable_at_bot,
    disable_at_bot,
    set_bot_qq,
])

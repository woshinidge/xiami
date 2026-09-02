from __future__ import annotations

from dataclasses import dataclass, field
import inspect
from typing import Any, Callable

from xiami_core.models import XiamiMessage
from xiami_core.plugins.async_utils import resolve_awaitable
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.events import PluginEvent
from xiami_core.plugins.legacy import LegacyBot, LegacyEvent, legacy_event


@dataclass(frozen=True)
class LegacyHookContext:
    hook: str
    event: dict[str, Any] = field(default_factory=dict)
    group_id: str = ""
    user_id: str = ""
    message: str = ""


class LegacyHookEvent(dict):
    @property
    def message_type(self) -> str:
        return str(self.get("message_type") or "")

    @property
    def sender(self) -> str:
        return str(self.get("user_id") or "")

    @property
    def target(self) -> str:
        return str(self.get("group_id") or self.get("user_id") or "")

    @property
    def raw_message(self) -> str:
        return str(self.get("raw_message") or self.get("message") or "")


def dispatch_legacy_hook_handlers(handlers: object, event: PluginEvent | XiamiMessage, ctx: PluginContext) -> list[str]:
    hook_map = _normalize_hook_handlers(handlers)
    if not hook_map:
        return []
    labels: list[str] = []
    for hook in legacy_hook_names(event):
        for handler in hook_map.get(hook, ()):
            if not callable(handler):
                continue
            _call_hook_handler(handler, legacy_hook_context(hook, event), ctx)
            labels.append(f"旧hook:{hook}")
    return labels


def legacy_hook_names(event: PluginEvent | XiamiMessage) -> list[str]:
    legacy = legacy_event(event)
    hooks: list[str] = []
    post_type = legacy.post_type or ("message" if isinstance(event, XiamiMessage) else "")
    if post_type == "message":
        hooks.append("message")
        if legacy.message_type:
            hooks.append(f"message.{legacy.message_type}")
        if _is_at_bot_message(legacy):
            hooks.append("message.at_bot")
    elif post_type == "notice":
        hooks.append("notice")
        if legacy.notice_type:
            hooks.append(f"notice.{legacy.notice_type}")
    elif post_type == "request":
        hooks.append("request")
        if legacy.request_type:
            hooks.append(f"request.{legacy.request_type}")
            if legacy.request_type == "group":
                sub_type = legacy.sub_type or "add"
                hooks.append(f"request.group_{sub_type}")
    return _unique(hooks)


def legacy_hook_context(hook: str, event: PluginEvent | XiamiMessage) -> LegacyHookContext:
    legacy = legacy_event(event)
    return LegacyHookContext(
        hook=hook,
        event=LegacyHookEvent(legacy.to_dict()),
        group_id=legacy.group_id,
        user_id=legacy.user_id,
        message=_context_message(hook, legacy),
    )


def _normalize_hook_handlers(handlers: object) -> dict[str, list[Callable[..., Any]]]:
    if not isinstance(handlers, dict):
        return {}
    result: dict[str, list[Callable[..., Any]]] = {}
    for hook, value in handlers.items():
        key = str(hook or "").strip()
        if not key:
            continue
        if callable(value):
            result.setdefault(key, []).append(value)
        elif isinstance(value, (list, tuple)):
            result.setdefault(key, []).extend(item for item in value if callable(item))
    return result


def _call_hook_handler(handler: Callable[..., Any], context: LegacyHookContext, ctx: PluginContext) -> Any:
    bot = LegacyBot(ctx)
    args = _hook_args(handler, bot, context, ctx)
    result = handler(*args)
    return resolve_awaitable(result)


def _hook_args(
    handler: Callable[..., Any], bot: LegacyBot, context: LegacyHookContext, ctx: PluginContext
) -> tuple[Any, ...]:
    try:
        params = [
            item
            for item in inspect.signature(handler).parameters.values()
            if item.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        ]
    except (TypeError, ValueError):
        return (context, ctx)
    if not params:
        return ()
    names = [item.name.lower() for item in params]
    if len(params) >= 2 and names[0] in {"bot", "client", "onebot"}:
        return (bot, context)
    if len(params) >= 2 and names[1] in {"ctx", "context", "plugin_context"}:
        return (context, ctx)
    if names[0] in {"bot", "client", "onebot"}:
        return (bot,)
    return (context,)


def _context_message(hook: str, event: LegacyEvent) -> str:
    if hook == "message.at_bot":
        parts = [str(item.data.get("text") or "") for item in event.segments if item.type == "text"]
        text = " ".join(parts).strip()
        if text:
            return text
    return event.plain_text()


def _is_at_bot_message(event: LegacyEvent) -> bool:
    if not event.is_group():
        return False
    self_id = event.self_id
    if self_id and event.has_at(self_id):
        return True
    return bool(event.at_users()) and not self_id


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result

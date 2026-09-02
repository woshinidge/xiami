from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

from xiami_core.models import XiamiMessage
from xiami_core.plugins.async_utils import resolve_awaitable
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.events import PluginEvent


MatcherFn = Callable[[XiamiMessage, PluginContext], None]
EventMatcherFn = Callable[[PluginEvent, PluginContext], None]
ScheduleFn = Callable[..., None]


@dataclass(frozen=True)
class CommandSession:
    command: str
    argument: str
    message_type: str
    user_id: str
    group_id: str = ""

    @property
    def argv(self) -> list[str]:
        return self.argument.split()


@dataclass(frozen=True)
class RegexSession:
    pattern: str
    match: re.Match[str]
    message_type: str
    user_id: str
    group_id: str = ""

    @property
    def text(self) -> str:
        return self.match.group(0)

    @property
    def groups(self) -> tuple[str | None, ...]:
        return self.match.groups()


@dataclass(frozen=True)
class EventSession:
    post_type: str
    event_type: str
    sub_type: str
    user_id: str
    group_id: str
    raw: dict[str, Any]


@dataclass(frozen=True)
class IntervalSession:
    name: str
    seconds: float


@dataclass(frozen=True)
class CommandHookSession:
    hook: str
    message: str
    message_type: str
    user_id: str
    group_id: str = ""
    raw: dict[str, Any] | None = None

    @property
    def argv(self) -> list[str]:
        return self.message.split()


@dataclass(frozen=True)
class CommandRule:
    command: str
    strip: bool = True

    def matches(self, event: XiamiMessage) -> bool:
        text = event.text.strip()
        command = self._probe()
        if not command:
            return False
        if command[-1].isspace():
            return text.startswith(command)
        if text == command.rstrip():
            return True
        if not text.startswith(command):
            return False
        next_char = text[len(command) : len(command) + 1]
        return bool(next_char and next_char.isspace())

    def session(self, event: XiamiMessage) -> CommandSession:
        text = event.text.strip() if self.strip else event.text
        command = self._probe()
        argument = text[len(command):].strip() if command and text.startswith(command) else text.strip()
        return CommandSession(
            command=command.rstrip(),
            argument=argument,
            message_type=event.message_type,
            user_id=event.sender,
            group_id=event.target if event.message_type == "group" else "",
        )

    def _probe(self) -> str:
        command = str(self.command or "")
        return command if command.endswith((" ", "\t")) else command.strip()


def on_command(
    command: str,
    *,
    aliases: tuple[str, ...] = (),
    description: str = "",
    message_type: str | None = None,
    only_private: bool = False,
    only_group: bool = False,
    owner_only: bool = False,
    admin_only: bool = False,
) -> Callable[[Callable[..., None]], MatcherFn]:
    commands = (command, *aliases)
    match_commands = tuple(sorted(commands, key=len, reverse=True))

    def decorator(func: Callable[..., None]) -> MatcherFn:
        def matcher(event: XiamiMessage, context: PluginContext) -> None:
            if not _scope_allowed(event, message_type=message_type, only_private=only_private, only_group=only_group):
                return
            if not _permission_allowed(event, context, owner_only=owner_only, admin_only=admin_only):
                return
            for item in match_commands:
                rule = CommandRule(item)
                if rule.matches(event):
                    session = rule.session(event)
                    _call_handler(func, event, context, session)
                    return

        matcher.__xiami_matcher__ = {
            "type": "command",
            "command": command,
            "aliases": list(aliases),
            "description": description,
            "label": _command_label(command, aliases, description),
        }
        return matcher

    return decorator


def on_keyword(
    keyword: str,
    *,
    description: str = "",
    message_type: str | None = None,
    only_private: bool = False,
    only_group: bool = False,
    owner_only: bool = False,
    admin_only: bool = False,
) -> Callable[[Callable[..., None]], MatcherFn]:
    def decorator(func: Callable[..., None]) -> MatcherFn:
        def matcher(event: XiamiMessage, context: PluginContext) -> None:
            if not _scope_allowed(event, message_type=message_type, only_private=only_private, only_group=only_group):
                return
            if not _permission_allowed(event, context, owner_only=owner_only, admin_only=admin_only):
                return
            if keyword in event.text:
                session = CommandSession("", event.text, event.message_type, event.sender, event.target)
                _call_handler(func, event, context, session)

        matcher.__xiami_matcher__ = {
            "type": "keyword",
            "keyword": keyword,
            "description": description,
            "label": _keyword_label(keyword, description),
        }
        return matcher

    return decorator


def on_regex(
    pattern: str | re.Pattern[str],
    *,
    flags: int = 0,
    fullmatch: bool = False,
    description: str = "",
    message_type: str | None = None,
    only_private: bool = False,
    only_group: bool = False,
    owner_only: bool = False,
    admin_only: bool = False,
) -> Callable[[Callable[..., None]], MatcherFn]:
    compiled = re.compile(pattern, flags) if isinstance(pattern, str) else pattern
    pattern_text = compiled.pattern

    def decorator(func: Callable[..., None]) -> MatcherFn:
        def matcher(event: XiamiMessage, context: PluginContext) -> None:
            if not _scope_allowed(event, message_type=message_type, only_private=only_private, only_group=only_group):
                return
            if not _permission_allowed(event, context, owner_only=owner_only, admin_only=admin_only):
                return
            match = compiled.fullmatch(event.text) if fullmatch else compiled.search(event.text)
            if not match:
                return
            session = RegexSession(
                pattern=pattern_text,
                match=match,
                message_type=event.message_type,
                user_id=event.sender,
                group_id=event.target if event.message_type == "group" else "",
            )
            _call_regex_handler(func, event, context, session)

        matcher.__xiami_matcher__ = {
            "type": "regex",
            "pattern": pattern_text,
            "description": description,
            "label": _regex_label(pattern_text, description),
        }
        return matcher

    return decorator


def on_notice(
    notice_type: str | tuple[str, ...] | None = None,
    *,
    sub_type: str | tuple[str, ...] | None = None,
    description: str = "",
    owner_only: bool = False,
    admin_only: bool = False,
) -> Callable[[Callable[..., None]], EventMatcherFn]:
    return _on_event_filter(
        "notice",
        event_type=notice_type,
        sub_type=sub_type,
        description=description,
        owner_only=owner_only,
        admin_only=admin_only,
    )


def on_request(
    request_type: str | tuple[str, ...] | None = None,
    *,
    sub_type: str | tuple[str, ...] | None = None,
    description: str = "",
    owner_only: bool = False,
    admin_only: bool = False,
) -> Callable[[Callable[..., None]], EventMatcherFn]:
    return _on_event_filter(
        "request",
        event_type=request_type,
        sub_type=sub_type,
        description=description,
        owner_only=owner_only,
        admin_only=admin_only,
    )


def on_event(
    post_type: str | tuple[str, ...] | None = None,
    *,
    event_type: str | tuple[str, ...] | None = None,
    sub_type: str | tuple[str, ...] | None = None,
    description: str = "",
    owner_only: bool = False,
    admin_only: bool = False,
) -> Callable[[Callable[..., None]], EventMatcherFn]:
    return _on_event_filter(
        post_type,
        event_type=event_type,
        sub_type=sub_type,
        description=description,
        owner_only=owner_only,
        admin_only=admin_only,
    )


on_event.__xiami_api_decorator__ = True


def on_interval(
    seconds: float,
    *,
    name: str = "",
    description: str = "",
) -> Callable[[ScheduleFn], ScheduleFn]:
    interval = float(seconds)

    def decorator(func: ScheduleFn) -> ScheduleFn:
        task_name = name or getattr(func, "__name__", "interval")
        func.__xiami_interval__ = {
            "name": task_name,
            "seconds": interval,
            "description": description,
            "label": _interval_label(task_name, interval, description),
        }
        return func

    return decorator


def on_command_hook(description: str = "") -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        label = description or getattr(func, "__name__", "command_hook")
        func.__xiami_command_hook__ = {
            "type": "command-hook",
            "hook": "command",
            "description": description,
            "label": f"旧命令Hook:{label}",
        }
        return func

    return decorator


def _on_event_filter(
    post_type: str | tuple[str, ...] | None,
    *,
    event_type: str | tuple[str, ...] | None = None,
    sub_type: str | tuple[str, ...] | None = None,
    description: str = "",
    owner_only: bool = False,
    admin_only: bool = False,
) -> Callable[[Callable[..., None]], EventMatcherFn]:
    def decorator(func: Callable[..., None]) -> EventMatcherFn:
        def matcher(event: PluginEvent, context: PluginContext) -> None:
            if not _matches_value(event.post_type, post_type):
                return
            actual_type = _event_detail_type(event)
            if not _matches_value(actual_type, event_type):
                return
            if not _matches_value(event.sub_type, sub_type):
                return
            if not _event_permission_allowed(event, context, owner_only=owner_only, admin_only=admin_only):
                return
            session = EventSession(
                post_type=event.post_type,
                event_type=actual_type,
                sub_type=event.sub_type,
                user_id=event.user_id,
                group_id=event.group_id,
                raw=event.raw,
            )
            _call_event_handler(func, event, context, session)

        post_label = _post_type_label(post_type)
        matcher.__xiami_matcher__ = {
            "type": post_label,
            "post_type": post_type,
            "event_type": event_type,
            "sub_type": sub_type,
            "description": description,
            "label": _event_label(post_label, event_type, sub_type, description),
        }
        return matcher

    return decorator


def call_command_hook_handler(
    func: Callable[..., Any],
    event: XiamiMessage,
    context: PluginContext,
    session: CommandHookSession,
) -> Any:
    try:
        return resolve_awaitable(func(event, context, session))
    except TypeError:
        pass
    try:
        return resolve_awaitable(func(session, context))
    except TypeError:
        pass
    try:
        return resolve_awaitable(func(session))
    except TypeError:
        pass
    return resolve_awaitable(func(event, context))


def _scope_allowed(
    event: XiamiMessage,
    *,
    message_type: str | None = None,
    only_private: bool = False,
    only_group: bool = False,
) -> bool:
    if message_type and event.message_type != message_type:
        return False
    if only_private and event.message_type != "private":
        return False
    if only_group and event.message_type != "group":
        return False
    return True


def _permission_allowed(
    event: XiamiMessage,
    context: PluginContext,
    *,
    owner_only: bool = False,
    admin_only: bool = False,
) -> bool:
    if not owner_only and not admin_only:
        return True
    from xiami_core.plugins.permissions import PluginPermissionService

    service = PluginPermissionService(context)
    group_id = event.target if event.message_type == "group" else ""
    if owner_only and not service.is_owner(event.sender):
        return False
    if admin_only and not service.is_admin(event.sender, group_id):
        return False
    return True


def _event_permission_allowed(
    event: PluginEvent,
    context: PluginContext,
    *,
    owner_only: bool = False,
    admin_only: bool = False,
) -> bool:
    if not owner_only and not admin_only:
        return True
    from xiami_core.plugins.permissions import PluginPermissionService

    service = PluginPermissionService(context)
    user_id = str(event.user_id)
    if owner_only and not service.is_owner(user_id):
        return False
    if admin_only and not service.is_admin(user_id, event.group_id):
        return False
    return True


def _call_handler(func: Callable[..., None], event: XiamiMessage, context: PluginContext, session: CommandSession) -> None:
    try:
        resolve_awaitable(func(event, context, session))
        return
    except TypeError:
        pass
    try:
        resolve_awaitable(func(event, context, session.argument))
        return
    except TypeError:
        pass
    resolve_awaitable(func(event, context))


def _call_regex_handler(func: Callable[..., None], event: XiamiMessage, context: PluginContext, session: RegexSession) -> None:
    try:
        resolve_awaitable(func(event, context, session))
        return
    except TypeError:
        pass
    try:
        resolve_awaitable(func(event, context, session.match))
        return
    except TypeError:
        pass
    resolve_awaitable(func(event, context))


def _call_event_handler(func: Callable[..., None], event: PluginEvent, context: PluginContext, session: EventSession) -> None:
    try:
        resolve_awaitable(func(event, context, session))
        return
    except TypeError:
        pass
    resolve_awaitable(func(event, context))


def call_interval_handler(func: Callable[..., None], context: PluginContext, session: IntervalSession) -> None:
    try:
        resolve_awaitable(func(context, session))
        return
    except TypeError:
        pass
    try:
        resolve_awaitable(func(context))
        return
    except TypeError:
        pass
    resolve_awaitable(func())


def _matches_value(actual: str, expected: str | tuple[str, ...] | None) -> bool:
    if expected is None:
        return True
    if isinstance(expected, tuple):
        return actual in {str(item) for item in expected}
    return actual == str(expected)


def _event_detail_type(event: PluginEvent) -> str:
    if event.post_type == "message":
        return event.message_type
    if event.post_type == "notice":
        return event.notice_type
    if event.post_type == "request":
        return event.request_type
    return event.detail_type


def _post_type_label(post_type: str | tuple[str, ...] | None) -> str:
    if post_type is None:
        return "*"
    if isinstance(post_type, tuple):
        return "|".join(str(item) for item in post_type)
    return str(post_type)


def _command_label(command: str, aliases: tuple[str, ...], description: str) -> str:
    names = ", ".join((command, *aliases))
    return f"{names} - {description}" if description else names


def _keyword_label(keyword: str, description: str) -> str:
    return f"关键词:{keyword} - {description}" if description else f"关键词:{keyword}"


def _regex_label(pattern: str, description: str) -> str:
    return f"正则:{pattern} - {description}" if description else f"正则:{pattern}"


def _event_label(
    post_type: str,
    event_type: str | tuple[str, ...] | None,
    sub_type: str | tuple[str, ...] | None,
    description: str,
) -> str:
    parts = [post_type]
    if event_type:
        parts.append("|".join(event_type) if isinstance(event_type, tuple) else str(event_type))
    if sub_type:
        parts.append("|".join(sub_type) if isinstance(sub_type, tuple) else str(sub_type))
    label = "事件:" + "/".join(parts)
    return f"{label} - {description}" if description else label


def _interval_label(name: str, seconds: float, description: str) -> str:
    label = f"定时:{name}/{seconds:g}s"
    return f"{label} - {description}" if description else label

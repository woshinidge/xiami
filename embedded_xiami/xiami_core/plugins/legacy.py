from __future__ import annotations

import inspect
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from xiami_core.models import MessageSegment, SendResult, XiamiMessage
from xiami_core.onebot.message_segments import cq_at, cq_image, cq_reply, cq_text, parse_onebot_segments, segments_to_text
from xiami_core.plugins.async_utils import resolve_awaitable
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.events import PluginEvent


@dataclass
class LegacyEvent(Mapping[str, Any]):
    raw: dict[str, Any] = field(default_factory=dict)
    message: XiamiMessage | None = None
    _data: dict[str, Any] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        self._data = _event_data(self.raw, self.message)

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    @property
    def post_type(self) -> str:
        return _text(self._data.get("post_type"))

    @property
    def message_type(self) -> str:
        return _text(self._data.get("message_type"))

    @property
    def notice_type(self) -> str:
        return _text(self._data.get("notice_type"))

    @property
    def request_type(self) -> str:
        return _text(self._data.get("request_type"))

    @property
    def sub_type(self) -> str:
        return _text(self._data.get("sub_type"))

    @property
    def self_id(self) -> str:
        return _text(self._data.get("self_id"))

    @property
    def user_id(self) -> str:
        return _text(self._data.get("user_id"))

    @property
    def group_id(self) -> str:
        return _text(self._data.get("group_id"))

    @property
    def operator_id(self) -> str:
        return _text(self._data.get("operator_id"))

    @property
    def target_id(self) -> str:
        return _text(self._data.get("target_id"))

    @property
    def message_id(self) -> str:
        return _text(self._data.get("message_id"))

    @property
    def text(self) -> str:
        return _text(self._data.get("raw_message") or self._data.get("message"))

    @property
    def raw_message(self) -> str:
        return _text(self._data.get("raw_message"))

    @property
    def segments(self) -> tuple[MessageSegment, ...]:
        if self.message and self.message.segments:
            return self.message.segments
        return parse_onebot_segments(self._data.get("message"), self._data.get("raw_message"))

    @property
    def time(self) -> int:
        try:
            return int(self._data.get("time") or 0)
        except (TypeError, ValueError):
            return 0

    def is_private(self) -> bool:
        return self.message_type == "private"

    def is_group(self) -> bool:
        return self.message_type == "group"

    def plain_text(self) -> str:
        return segments_to_text(self.segments, fallback=self.raw_message or self.text)

    def get_plain_text(self) -> str:
        return self.plain_text()

    def at_users(self) -> list[str]:
        return [_text(item.data.get("qq")) for item in self.segments if item.type == "at" and item.data.get("qq")]

    def has_at(self, user_id: str | int) -> bool:
        return str(user_id) in self.at_users()

    def image_files(self) -> list[str]:
        return [_text(item.data.get("file") or item.data.get("url")) for item in self.segments if item.type == "image"]

    def first_image(self) -> str:
        images = self.image_files()
        return images[0] if images else ""

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)


@dataclass
class LegacyBot:
    ctx: PluginContext

    def call_action(self, action: str, params: dict[str, Any] | None = None, **extra: Any) -> Any:
        payload = dict(params or {})
        payload.update(extra)
        return self.ctx.call_onebot(action, payload)

    def call_api(self, action: str, params: dict[str, Any] | None = None, **extra: Any) -> Any:
        return self.call_action(action, params, **extra)

    def send_msg(
        self,
        *args: Any,
        message_type: str = "",
        user_id: str | int | None = None,
        group_id: str | int | None = None,
        message: Any = "",
        **extra: Any,
    ) -> Any:
        message_type, user_id, group_id, message = _parse_send_msg_args(
            args,
            message_type=message_type,
            user_id=user_id,
            group_id=group_id,
            message=message,
            extra=extra,
        )
        if message_type == "group" or group_id is not None:
            return self.send_group_msg(group_id or "", message)
        return self.send_private_msg(user_id or "", message)

    def send_private_msg(self, user_id: str | int, message: Any) -> dict[str, Any]:
        return _send_result(self.ctx.send_private(user_id, str(message)))

    def send_group_msg(self, group_id: str | int, message: Any) -> dict[str, Any]:
        return _send_result(self.ctx.send_group(group_id, str(message)))

    def send_private_image(self, user_id: str | int, file: str) -> Any:
        return self.ctx.send_private_image(user_id, file)

    def send_group_image(self, group_id: str | int, file: str) -> Any:
        return self.ctx.send_group_image(group_id, file)

    def upload_group_file(self, group_id: str | int, file: str, name: str = "") -> Any:
        return self.ctx.upload_group_file(group_id, file, name)

    def get_group_root_files(self, group_id: str | int) -> Any:
        return self.ctx.get_group_root_files(group_id)

    def get_group_files_by_folder(self, group_id: str | int, folder_id: str) -> Any:
        return self.ctx.get_group_files_by_folder(group_id, folder_id)

    def get_group_file_url(self, group_id: str | int, file_id: str, busid: str | int) -> Any:
        return self.ctx.get_group_file_url(group_id, file_id, busid)

    def create_group_file_folder(self, group_id: str | int, folder_name: str, parent_id: str = "/") -> Any:
        return self.ctx.create_group_file_folder(group_id, folder_name, parent_id=parent_id)

    def delete_group_folder(self, group_id: str | int, folder_id: str) -> Any:
        return self.ctx.delete_group_folder(group_id, folder_id)

    def delete_group_file(self, group_id: str | int, file_id: str, busid: str | int) -> Any:
        return self.ctx.delete_group_file(group_id, file_id, busid)

    def send(self, event: LegacyEvent | PluginEvent | XiamiMessage | dict[str, Any], message: Any) -> Any:
        legacy = legacy_event(event)
        if legacy.is_group():
            return self.send_group_msg(legacy.group_id, message)
        return self.send_private_msg(legacy.user_id, message)

    def reply(self, event: LegacyEvent | PluginEvent | XiamiMessage | dict[str, Any], message: Any) -> Any:
        return self.send(event, message)

    def delete_msg(self, message_id: str | int) -> Any:
        return self.ctx.delete_msg(message_id)

    def get_msg(self, message_id: str | int) -> Any:
        return self.ctx.get_msg(message_id)

    def get_login_info(self) -> Any:
        return self.ctx.get_login_info()

    def get_status(self) -> Any:
        return self.ctx.get_status()

    def get_version_info(self) -> Any:
        return self.ctx.get_version()

    def get_version(self) -> Any:
        return self.ctx.get_version()

    def get_friend_list(self) -> Any:
        return self.ctx.get_friend_list()

    def get_group_list(self) -> Any:
        return self.ctx.get_group_list()

    def get_group_info(self, group_id: str | int, no_cache: bool = True) -> Any:
        return self.ctx.get_group_info(group_id, no_cache=no_cache)

    def get_group_member_list(self, group_id: str | int) -> Any:
        return self.ctx.get_group_member_list(group_id)

    def get_group_member_info(self, group_id: str | int, user_id: str | int, no_cache: bool = True) -> Any:
        return self.ctx.get_group_member_info(group_id, user_id, no_cache=no_cache)

    def get_stranger_info(self, user_id: str | int, no_cache: bool = True) -> Any:
        return self.ctx.get_stranger_info(user_id, no_cache=no_cache)

    def send_like(self, user_id: str | int, times: int = 1) -> Any:
        return self.ctx.send_like(user_id, times=times)

    def send_poke(self, user_id: str | int, group_id: str | int | None = None) -> Any:
        return self.ctx.send_poke(user_id, group_id=group_id)

    def forward_node(self, content: Any, name: str = "Xiami", uin: str | int = "0") -> dict[str, Any]:
        return self.ctx.forward_node(content, name=name, uin=uin)

    def normalize_forward_messages(self, messages: Any, name: str = "Xiami", uin: str | int = "0") -> list[dict[str, Any]]:
        return self.ctx.normalize_forward_messages(messages, name=name, uin=uin)

    def send_group_forward_msg(self, group_id: str | int, messages: Any) -> Any:
        return self.ctx.send_group_forward_msg(group_id, messages)

    def send_private_forward_msg(self, user_id: str | int, messages: Any) -> Any:
        return self.ctx.send_private_forward_msg(user_id, messages)

    def get_image(self, file: str) -> Any:
        return self.ctx.get_image(file)

    def get_record(self, file: str, out_format: str = "mp3") -> Any:
        return self.ctx.get_record(file, out_format=out_format)

    def set_group_ban(self, group_id: str | int, user_id: str | int, duration: int) -> Any:
        return self.ctx.set_group_ban(group_id, user_id, duration)

    def set_group_kick(self, group_id: str | int, user_id: str | int, reject_add_request: bool = False) -> Any:
        return self.ctx.set_group_kick(group_id, user_id, reject_add_request=reject_add_request)

    def set_group_admin(self, group_id: str | int, user_id: str | int, enable: bool = True) -> Any:
        return self.ctx.set_group_admin(group_id, user_id, enable=enable)

    def set_group_card(self, group_id: str | int, user_id: str | int, card: str = "") -> Any:
        return self.ctx.set_group_card(group_id, user_id, card)

    def set_group_whole_ban(self, group_id: str | int, enable: bool = True) -> Any:
        return self.ctx.set_group_whole_ban(group_id, enable=enable)

    def set_group_name(self, group_id: str | int, group_name: str) -> Any:
        return self.ctx.set_group_name(group_id, group_name)

    def set_group_special_title(
        self,
        group_id: str | int,
        user_id: str | int,
        special_title: str = "",
        duration: int = -1,
    ) -> Any:
        return self.ctx.set_group_special_title(group_id, user_id, special_title, duration=duration)

    def set_group_leave(self, group_id: str | int, is_dismiss: bool = False) -> Any:
        return self.ctx.set_group_leave(group_id, is_dismiss=is_dismiss)

    def set_group_notice(self, group_id: str | int, content: str, image: str = "") -> Any:
        return self.ctx.set_group_notice(group_id, content, image=image)

    def get_group_notice(self, group_id: str | int) -> Any:
        return self.ctx.get_group_notice(group_id)

    def get_group_honor_info(self, group_id: str | int, honor_type: str = "all") -> Any:
        return self.ctx.get_group_honor_info(group_id, honor_type=honor_type)

    def set_essence_msg(self, message_id: str | int) -> Any:
        return self.ctx.set_essence_msg(message_id)

    def delete_essence_msg(self, message_id: str | int) -> Any:
        return self.ctx.delete_essence_msg(message_id)

    def set_group_add_request(self, flag: str, sub_type: str, approve: bool, reason: str = "") -> Any:
        return self.ctx.set_group_add_request(flag, sub_type, approve, reason)

    def set_friend_add_request(self, flag: str, approve: bool, remark: str = "") -> Any:
        return self.ctx.set_friend_add_request(flag, approve, remark)

    def cq_text(self, text: str) -> str:
        return cq_text(text)

    def cq_at(self, user_id: str | int) -> str:
        return cq_at(user_id)

    def cq_image(self, file: str) -> str:
        return cq_image(file)

    def cq_reply(self, message_id: str | int) -> str:
        return cq_reply(message_id)


def legacy_event(event: LegacyEvent | PluginEvent | XiamiMessage | dict[str, Any]) -> LegacyEvent:
    if isinstance(event, LegacyEvent):
        return event
    if isinstance(event, PluginEvent):
        return LegacyEvent(raw=dict(event.raw), message=event.message)
    if isinstance(event, XiamiMessage):
        return LegacyEvent(raw={}, message=event)
    if isinstance(event, dict):
        return LegacyEvent(raw=dict(event), message=None)
    raise TypeError(f"unsupported legacy event: {type(event)!r}")


def legacy_bot(ctx: PluginContext) -> LegacyBot:
    return LegacyBot(ctx)


def call_legacy_handler(handler: Callable[..., Any], event: LegacyEvent | PluginEvent | XiamiMessage, ctx: PluginContext) -> Any:
    legacy = legacy_event(event)
    bot = LegacyBot(ctx)
    args = _legacy_args(handler, bot, legacy, ctx)
    return resolve_awaitable(handler(*args))


def dispatch_legacy_handlers(handlers: object, event: LegacyEvent | PluginEvent | XiamiMessage, ctx: PluginContext) -> None:
    if not isinstance(handlers, list):
        return
    for handler in list(handlers):
        if callable(handler):
            call_legacy_handler(handler, event, ctx)


def _legacy_args(handler: Callable[..., Any], bot: LegacyBot, event: LegacyEvent, ctx: PluginContext) -> tuple[Any, ...]:
    try:
        params = list(inspect.signature(handler).parameters.values())
    except (TypeError, ValueError):
        return (bot, event)
    positional = [
        item
        for item in params
        if item.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    if not positional:
        return ()
    first = positional[0].name.lower()
    second = positional[1].name.lower() if len(positional) >= 2 else ""
    if len(positional) == 1:
        return (bot,) if first in {"bot", "client", "api"} else (event,)
    if first in {"event", "message", "msg"}:
        return (event, ctx) if second in {"ctx", "context"} else (event,)
    if first in {"ctx", "context"}:
        return (ctx, event)
    if second in {"ctx", "context"}:
        return (event, ctx)
    if len(positional) >= 3:
        return (bot, event, ctx)
    return (bot, event)


def _parse_send_msg_args(
    args: tuple[Any, ...],
    *,
    message_type: str,
    user_id: str | int | None,
    group_id: str | int | None,
    message: Any,
    extra: dict[str, Any],
) -> tuple[str, str | int | None, str | int | None, Any]:
    payload = dict(extra)
    remaining = list(args)
    if remaining and isinstance(remaining[0], dict):
        payload.update(remaining.pop(0))
    message_type = str(payload.get("message_type", message_type) or "")
    user_id = payload.get("user_id", user_id)
    group_id = payload.get("group_id", group_id)
    message = payload.get("message", message)

    if remaining:
        first = remaining.pop(0)
        if str(first) in {"private", "group"}:
            message_type = str(first)
            if remaining:
                if message_type == "group":
                    group_id = remaining.pop(0)
                else:
                    user_id = remaining.pop(0)
            if remaining:
                message = remaining.pop(0)
        elif remaining:
            if message_type == "group":
                group_id = first
            elif message_type == "private":
                user_id = first
            elif group_id is None and user_id is None:
                user_id = first
            message = remaining.pop(0)
        elif not message:
            message = first

    return message_type, user_id, group_id, message


def _event_data(raw: dict[str, Any], message: XiamiMessage | None) -> dict[str, Any]:
    data = dict(raw)
    if message:
        data.setdefault("post_type", "message")
        data.setdefault("message_type", message.message_type)
        data.setdefault("user_id", _number_or_text(message.sender))
        data.setdefault("sender", {"user_id": _number_or_text(message.sender)})
        if message.message_type == "group":
            data.setdefault("group_id", _number_or_text(message.target))
        data.setdefault("raw_message", message.raw_message or message.text)
        data.setdefault("message", _message_payload(message))
    sender = data.get("sender")
    if isinstance(sender, dict) and "user_id" not in data:
        data["user_id"] = sender.get("user_id") or sender.get("uin") or ""
    return data


def _message_payload(message: XiamiMessage) -> Any:
    if message.segments:
        return [{"type": item.type, "data": dict(item.data)} for item in message.segments]
    return message.raw_message or message.text


def _send_result(result: SendResult) -> dict[str, Any]:
    data: dict[str, Any] = {}
    if result.message_id:
        data["message_id"] = _number_or_text(result.message_id)
    return {
        "status": "ok" if result.ok else "failed",
        "retcode": 0 if result.ok else -1,
        "data": data,
        "message": result.detail,
    }


def _number_or_text(value: str | int) -> str | int:
    text = str(value)
    return int(text) if text.isdigit() else text


def _text(value: Any) -> str:
    return "" if value is None else str(value)

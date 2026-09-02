from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from pathlib import PureWindowsPath
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

from xiami_core.models import MessageSegment, SendResult, XiamiMessage
from xiami_core.onebot.forward import forward_node, normalize_forward_messages
from xiami_core.onebot.message_segments import cq_at, cq_image, cq_reply, cq_text, parse_cq_message, segments_to_cq, segments_to_text
from xiami_core.plugins.kv import PluginKVStore
from xiami_core.storage.paths import XIAMI_HOME


SendFn = Callable[[str, str, str], SendResult]
TimerFn = Callable[[str, float, Callable[[], None]], None]
OneBotCallFn = Callable[[str, Dict[str, Any]], Any]
HistoryFn = Callable[[Optional[Any], int], List[Any]]


@dataclass
class PluginContext:
    send_fn: SendFn
    config: dict[str, Any] = field(default_factory=dict)
    plugin_id: str = ""
    data_root: Path = field(default_factory=lambda: XIAMI_HOME / "plugin_data")
    state_store: PluginKVStore = field(default_factory=PluginKVStore)
    timer_fn: TimerFn | None = None
    onebot_call_fn: OneBotCallFn | None = None
    history_fn: HistoryFn | None = None
    logs: list[str] = field(default_factory=list)
    runtime_registry: dict[str, Any] = field(default_factory=dict)
    send_count: int = 0
    state_revision: int = 0

    def log(self, message: str, level: str = "info") -> None:
        text = str(message)
        log_level = str(level or "info").lower()
        self.logs.append(text)
        entry = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "level": log_level,
            "plugin_id": self.plugin_id or "shared",
            "message": text,
        }
        self.append_text("_logs.jsonl", json.dumps(entry, ensure_ascii=False) + "\n")

    def log_debug(self, message: str) -> None:
        self.log(message, "debug")

    def log_warning(self, message: str) -> None:
        self.log(message, "warning")

    def log_error(self, message: str) -> None:
        self.log(message, "error")

    def log_file(self) -> Path:
        return self.data_path("_logs.jsonl")

    def recent_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        path = self.log_file()
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[-max(1, int(limit or 1)) :]:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
        return rows

    def reply(self, event: XiamiMessage, text: str) -> SendResult:
        target = event.sender if event.message_type == "private" else event.target
        return self._send(target, text, event.message_type)

    def reply_image(self, event: Any, file: str) -> Any:
        message_type, target = _reply_target(event)
        if message_type == "group":
            return self.send_group_image(target, file)
        return self.send_private_image(target, file)

    def reply_at(self, event: Any, text: str = "", user_id: str | int | None = None) -> SendResult:
        message_type, target = _reply_target(event)
        if message_type != "group":
            return self._send(target, text, "private")
        at_user = user_id or _event_user_id(event)
        message = self.cq_at(at_user) + (self.cq_text(" " + text) if text else "")
        return self._send(target, message, "group")

    def reply_to(self, event: Any, text: str, message_id: str | int | None = None) -> SendResult:
        message_type, target = _reply_target(event)
        reply_id = message_id if message_id is not None else _event_message_id(event)
        message = (self.cq_reply(reply_id) if reply_id else "") + self.cq_text(text)
        return self._send(target, message, message_type)

    def reply_segments(self, event: Any, segments: Any) -> SendResult:
        message_type, target = _reply_target(event)
        return self._send(target, self.message_from_segments(segments), message_type)

    def send_private(self, user_id: str | int, text: str) -> SendResult:
        return self._send(str(user_id), text, "private")

    def send_private_many(self, user_ids: Any, text: str) -> list[SendResult]:
        return [self.send_private(user_id, text) for user_id in _ordered_ids_from_values(user_ids)]

    def send_private_segments(self, user_id: str | int, segments: Any) -> SendResult:
        return self._send(str(user_id), self.message_from_segments(segments), "private")

    def send_private_image(self, user_id: str | int, file: str) -> Any:
        return self.onebot_call("send_private_msg", {"user_id": _number_or_text(user_id), "message": self.cq_image(file)})

    def send_group(self, group_id: str | int, text: str) -> SendResult:
        return self._send(str(group_id), text, "group")

    def send_group_many(self, group_ids: Any, text: str) -> list[SendResult]:
        return [self.send_group(group_id, text) for group_id in _ordered_ids_from_values(group_ids)]

    def send_group_segments(self, group_id: str | int, segments: Any) -> SendResult:
        return self._send(str(group_id), self.message_from_segments(segments), "group")

    def send_group_image(self, group_id: str | int, file: str) -> Any:
        return self.onebot_call("send_group_msg", {"group_id": _number_or_text(group_id), "message": self.cq_image(file)})

    def send_msg(
        self,
        message_type: str | dict[str, Any] = "",
        target: str | int = "",
        message: Any = "",
        **params: Any,
    ) -> SendResult:
        payload = dict(message_type) if isinstance(message_type, dict) else {"message_type": message_type}
        payload.update(params)
        if target:
            payload["target"] = target
        if message != "":
            payload["message"] = message
        msg_type = str(
            payload.get("message_type")
            or payload.get("type")
            or ("group" if payload.get("group_id") is not None else "")
            or ("private" if payload.get("user_id") is not None else "")
            or "private"
        ).lower()
        body = _message_body(payload.get("message", payload.get("text", "")))
        if msg_type == "group":
            group_id = payload.get("group_id", payload.get("target", ""))
            if not group_id:
                raise ValueError("group message requires group_id or target")
            return self._send(str(group_id), body, "group")
        if msg_type == "private":
            user_id = payload.get("user_id", payload.get("target", ""))
            if not user_id:
                raise ValueError("private message requires user_id or target")
            return self._send(str(user_id), body, "private")
        raise ValueError(f"unsupported message_type: {msg_type}")

    def send_message(self, *args: Any, **params: Any) -> SendResult:
        return self.send_msg(*args, **params)

    def upload_group_file(self, group_id: str | int, file: str, name: str = "") -> Any:
        return self.onebot_call(
            "upload_group_file",
            {"group_id": _number_or_text(group_id), "file": file, "name": name or _file_name(file)},
        )

    def get_group_root_files(self, group_id: str | int) -> Any:
        return self.onebot_call("get_group_root_files", {"group_id": _number_or_text(group_id)})

    def get_group_files_by_folder(self, group_id: str | int, folder_id: str) -> Any:
        return self.onebot_call(
            "get_group_files_by_folder",
            {"group_id": _number_or_text(group_id), "folder_id": folder_id},
        )

    def get_group_file_url(self, group_id: str | int, file_id: str, busid: str | int) -> Any:
        return self.onebot_call(
            "get_group_file_url",
            {"group_id": _number_or_text(group_id), "file_id": file_id, "busid": _number_or_text(busid)},
        )

    def create_group_file_folder(self, group_id: str | int, folder_name: str, parent_id: str = "/") -> Any:
        return self.onebot_call(
            "create_group_file_folder",
            {"group_id": _number_or_text(group_id), "folder_name": folder_name, "parent_id": parent_id},
        )

    def delete_group_folder(self, group_id: str | int, folder_id: str) -> Any:
        return self.onebot_call(
            "delete_group_folder",
            {"group_id": _number_or_text(group_id), "folder_id": folder_id},
        )

    def delete_group_file(self, group_id: str | int, file_id: str, busid: str | int) -> Any:
        return self.onebot_call(
            "delete_group_file",
            {"group_id": _number_or_text(group_id), "file_id": file_id, "busid": _number_or_text(busid)},
        )

    def cq_text(self, text: str) -> str:
        return cq_text(text)

    def cq_image(self, file: str) -> str:
        return cq_image(file)

    def cq_at(self, user_id: str | int) -> str:
        return cq_at(user_id)

    def cq_reply(self, message_id: str | int) -> str:
        return cq_reply(message_id)

    def message_from_segments(self, segments: Any) -> str:
        return _message_from_segments(segments)

    def onebot_call(self, action: str, params: dict[str, Any]) -> Any:
        if not self.onebot_call_fn:
            raise RuntimeError("OneBot 调用未启用")
        return self.onebot_call_fn(action, params)

    def call_action(self, action: str, **params: Any) -> Any:
        return self.onebot_call(action, params)

    def call_onebot(self, action: str, params: dict[str, Any] | None = None, **extra: Any) -> Any:
        payload = dict(params or {})
        payload.update(extra)
        return self.onebot_call(action, payload)

    def recent_messages(self, event: Any | None = None, limit: int = 10) -> list[Any]:
        if not self.history_fn:
            return []
        try:
            safe_limit = max(0, int(limit))
        except (TypeError, ValueError):
            safe_limit = 10
        if safe_limit <= 0:
            return []
        return list(self.history_fn(event, safe_limit))

    def onebot_ok(self, response: Any) -> bool:
        if hasattr(response, "ok"):
            return bool(response.ok)
        if isinstance(response, dict):
            return bool(response.get("ok") or response.get("status") == "ok" or response.get("retcode") == 0)
        return bool(response)

    def onebot_data(self, response: Any) -> Any:
        if hasattr(response, "data"):
            return response.data
        if isinstance(response, dict):
            return response.get("data", response)
        return response

    def onebot_message(self, response: Any) -> str:
        if hasattr(response, "message"):
            return str(response.message)
        if isinstance(response, dict):
            value = response.get("message") or response.get("wording") or response.get("msg")
            if value is not None:
                return str(value)
        return str(response)

    def get_login_info(self) -> Any:
        return self.onebot_call("get_login_info", {})

    def get_status(self) -> Any:
        return self.onebot_call("get_status", {})

    def get_version(self) -> Any:
        return self.onebot_call("get_version_info", {})

    def get_friend_list(self) -> Any:
        return self.onebot_call("get_friend_list", {})

    def get_group_list(self) -> Any:
        return self.onebot_call("get_group_list", {})

    def get_group_member_list(self, group_id: str | int) -> Any:
        return self.onebot_call("get_group_member_list", {"group_id": _number_or_text(group_id)})

    def get_group_info(self, group_id: str | int, no_cache: bool = True) -> Any:
        return self.onebot_call("get_group_info", {"group_id": _number_or_text(group_id), "no_cache": bool(no_cache)})

    def get_group_member_info(self, group_id: str | int, user_id: str | int, no_cache: bool = True) -> Any:
        return self.onebot_call(
            "get_group_member_info",
            {"group_id": _number_or_text(group_id), "user_id": _number_or_text(user_id), "no_cache": bool(no_cache)},
        )

    def get_stranger_info(self, user_id: str | int, no_cache: bool = True) -> Any:
        return self.onebot_call("get_stranger_info", {"user_id": _number_or_text(user_id), "no_cache": bool(no_cache)})

    def get_msg(self, message_id: str | int) -> Any:
        return self.onebot_call("get_msg", {"message_id": _number_or_text(message_id)})

    def send_like(self, user_id: str | int, times: int = 1) -> Any:
        return self.onebot_call("send_like", {"user_id": _number_or_text(user_id), "times": int(times)})

    def send_poke(self, user_id: str | int, group_id: str | int | None = None) -> Any:
        params: dict[str, Any] = {"user_id": _number_or_text(user_id)}
        if group_id is not None:
            params["group_id"] = _number_or_text(group_id)
        return self.onebot_call("send_poke", params)

    def forward_node(self, content: Any, name: str = "Xiami", uin: str | int = "0") -> dict[str, Any]:
        return forward_node(content, name=name, uin=uin)

    def normalize_forward_messages(self, messages: Any, name: str = "Xiami", uin: str | int = "0") -> list[dict[str, Any]]:
        return normalize_forward_messages(messages, default_name=name, default_uin=uin)

    def send_group_forward_msg(self, group_id: str | int, messages: Any) -> Any:
        return self.onebot_call(
            "send_group_forward_msg",
            {"group_id": _number_or_text(group_id), "messages": self.normalize_forward_messages(messages)},
        )

    def send_private_forward_msg(self, user_id: str | int, messages: Any) -> Any:
        return self.onebot_call(
            "send_private_forward_msg",
            {"user_id": _number_or_text(user_id), "messages": self.normalize_forward_messages(messages)},
        )

    def get_image(self, file: str) -> Any:
        return self.onebot_call("get_image", {"file": file})

    def get_record(self, file: str, out_format: str = "mp3") -> Any:
        return self.onebot_call("get_record", {"file": file, "out_format": out_format})

    def set_group_ban(self, group_id: str | int, user_id: str | int, duration: int) -> Any:
        return self.onebot_call(
            "set_group_ban",
            {"group_id": _number_or_text(group_id), "user_id": _number_or_text(user_id), "duration": int(duration)},
        )

    def set_group_whole_ban(self, group_id: str | int, enable: bool = True) -> Any:
        return self.onebot_call("set_group_whole_ban", {"group_id": _number_or_text(group_id), "enable": bool(enable)})

    def set_group_kick(self, group_id: str | int, user_id: str | int, reject_add_request: bool = False) -> Any:
        return self.onebot_call(
            "set_group_kick",
            {
                "group_id": _number_or_text(group_id),
                "user_id": _number_or_text(user_id),
                "reject_add_request": bool(reject_add_request),
            },
        )

    def set_group_admin(self, group_id: str | int, user_id: str | int, enable: bool = True) -> Any:
        return self.onebot_call(
            "set_group_admin",
            {"group_id": _number_or_text(group_id), "user_id": _number_or_text(user_id), "enable": bool(enable)},
        )

    def set_group_card(self, group_id: str | int, user_id: str | int, card: str = "") -> Any:
        return self.onebot_call(
            "set_group_card",
            {"group_id": _number_or_text(group_id), "user_id": _number_or_text(user_id), "card": card},
        )

    def set_group_name(self, group_id: str | int, group_name: str) -> Any:
        return self.onebot_call("set_group_name", {"group_id": _number_or_text(group_id), "group_name": group_name})

    def set_group_special_title(
        self,
        group_id: str | int,
        user_id: str | int,
        special_title: str = "",
        duration: int = -1,
    ) -> Any:
        return self.onebot_call(
            "set_group_special_title",
            {
                "group_id": _number_or_text(group_id),
                "user_id": _number_or_text(user_id),
                "special_title": special_title,
                "duration": int(duration),
            },
        )

    def set_group_leave(self, group_id: str | int, is_dismiss: bool = False) -> Any:
        return self.onebot_call("set_group_leave", {"group_id": _number_or_text(group_id), "is_dismiss": bool(is_dismiss)})

    def set_group_notice(self, group_id: str | int, content: str, image: str = "") -> Any:
        return self.onebot_call("_send_group_notice", {"group_id": _number_or_text(group_id), "content": content, "image": image})

    def get_group_notice(self, group_id: str | int) -> Any:
        return self.onebot_call("_get_group_notice", {"group_id": _number_or_text(group_id)})

    def get_group_honor_info(self, group_id: str | int, honor_type: str = "all") -> Any:
        return self.onebot_call("get_group_honor_info", {"group_id": _number_or_text(group_id), "type": honor_type})

    def set_essence_msg(self, message_id: str | int) -> Any:
        return self.onebot_call("set_essence_msg", {"message_id": _number_or_text(message_id)})

    def delete_essence_msg(self, message_id: str | int) -> Any:
        return self.onebot_call("delete_essence_msg", {"message_id": _number_or_text(message_id)})

    def set_group_add_request(self, flag: str, sub_type: str, approve: bool, reason: str = "") -> Any:
        return self.onebot_call(
            "set_group_add_request",
            {"flag": flag, "sub_type": sub_type, "approve": bool(approve), "reason": reason},
        )

    def set_friend_add_request(self, flag: str, approve: bool, remark: str = "") -> Any:
        return self.onebot_call("set_friend_add_request", {"flag": flag, "approve": bool(approve), "remark": remark})

    def delete_msg(self, message_id: str | int) -> Any:
        return self.onebot_call("delete_msg", {"message_id": _number_or_text(message_id)})

    def data_dir(self, plugin_id: str | None = None) -> Path:
        target = self.data_root / (plugin_id or self.plugin_id or "shared")
        target.mkdir(parents=True, exist_ok=True)
        return target

    def data_path(self, name: str | Path, *, plugin_id: str | None = None, create_parent: bool = False) -> Path:
        raw = Path(name)
        if raw.is_absolute():
            raise ValueError("plugin data path must be relative")
        if not str(raw).strip():
            raise ValueError("plugin data path must not be empty")
        root = self.data_dir(plugin_id).resolve()
        target = (root / raw).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise ValueError("plugin data path escapes data directory") from exc
        if create_parent:
            target.parent.mkdir(parents=True, exist_ok=True)
        return target

    def read_text(self, name: str | Path, default: str = "", *, encoding: str = "utf-8") -> str:
        path = self.data_path(name)
        if not path.exists():
            return default
        return path.read_text(encoding=encoding, errors="replace")

    def write_text(self, name: str | Path, text: str, *, encoding: str = "utf-8") -> Path:
        path = self.data_path(name, create_parent=True)
        path.write_text(str(text), encoding=encoding)
        return path

    def append_text(self, name: str | Path, text: str, *, encoding: str = "utf-8") -> Path:
        path = self.data_path(name, create_parent=True)
        with path.open("a", encoding=encoding) as file:
            file.write(str(text))
        return path

    def read_json(self, name: str | Path, default: Any = None) -> Any:
        path = self.data_path(name)
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid plugin json data: {name}") from exc

    def write_json(self, name: str | Path, value: Any) -> Path:
        path = self.data_path(name, create_parent=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def get_config(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)

    def get_config_str(self, key: str, default: str = "") -> str:
        value = self.get_config(key, default)
        if value is None:
            return default
        return str(value)

    def get_config_bool(self, key: str, default: bool = False) -> bool:
        value = self.get_config(key, default)
        return _bool_value(value, default)

    def get_config_int(self, key: str, default: int = 0) -> int:
        value = self.get_config(key, default)
        try:
            return int(value)
        except (TypeError, ValueError):
            return int(default)

    def get_config_float(self, key: str, default: float = 0.0) -> float:
        value = self.get_config(key, default)
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    def get_config_list(self, key: str, default: list[Any] | None = None) -> list[Any]:
        value = self.get_config(key, default or [])
        if isinstance(value, list):
            return list(value)
        if isinstance(value, tuple):
            return list(value)
        if isinstance(value, set):
            return list(value)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return [item.strip() for item in text.split(",") if item.strip()]
            if isinstance(parsed, list):
                return parsed
        return list(default or [])

    def get_config_dict(self, key: str, default: dict[str, Any] | None = None) -> dict[str, Any]:
        value = self.get_config(key, default or {})
        if isinstance(value, dict):
            return dict(value)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return {}
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return dict(default or {})
            if isinstance(parsed, dict):
                return parsed
        return dict(default or {})

    def load_state(self) -> dict[str, Any]:
        return self.state_store.load(self.plugin_id or "shared")

    def save_state(self, data: dict[str, Any]) -> None:
        self.state_revision += 1
        self.state_store.save(self.plugin_id or "shared", data)

    def get_state(self, key: str, default: Any = None) -> Any:
        return self.state_store.get(self.plugin_id or "shared", key, default)

    def get_state_str(self, key: str, default: str = "") -> str:
        value = self.get_state(key, default)
        if value is None:
            return str(default)
        return str(value)

    def get_state_bool(self, key: str, default: bool = False) -> bool:
        value = self.get_state(key, default)
        return _bool_value(value, default)

    def get_state_int(self, key: str, default: int = 0) -> int:
        value = self.get_state(key, default)
        try:
            return int(value)
        except (TypeError, ValueError):
            return int(default)

    def get_state_float(self, key: str, default: float = 0.0) -> float:
        value = self.get_state(key, default)
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    def get_state_list(self, key: str, default: list[Any] | None = None) -> list[Any]:
        value = self.get_state(key, default or [])
        if isinstance(value, list):
            return list(value)
        if isinstance(value, tuple):
            return list(value)
        if isinstance(value, set):
            return list(value)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return [item.strip() for item in text.split(",") if item.strip()]
            if isinstance(parsed, list):
                return parsed
        return list(default or [])

    def get_state_dict(self, key: str, default: dict[str, Any] | None = None) -> dict[str, Any]:
        value = self.get_state(key, default or {})
        if isinstance(value, dict):
            return dict(value)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return {}
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return dict(default or {})
            if isinstance(parsed, dict):
                return parsed
        return dict(default or {})

    def set_state(self, key: str, value: Any) -> None:
        self.state_revision += 1
        self.state_store.set(self.plugin_id or "shared", key, value)

    def increment_state(
        self,
        key: str,
        amount: int | float = 1,
        default: int | float = 0,
    ) -> int | float:
        value = self.get_state(key, default)
        try:
            base = float(value) if isinstance(amount, float) or isinstance(default, float) else int(value)
        except (TypeError, ValueError):
            base = default
        updated = base + amount
        if isinstance(updated, float) and updated.is_integer() and not isinstance(amount, float) and not isinstance(default, float):
            updated = int(updated)
        self.set_state(key, updated)
        return updated

    def append_state_list(self, key: str, value: Any, *, unique: bool = False, limit: int | None = None) -> list[Any]:
        items = self.get_state_list(key)
        if unique and value in items:
            return items
        items.append(value)
        items = _trim_list(items, limit)
        self.set_state(key, items)
        return items

    def prepend_state_list(self, key: str, value: Any, *, unique: bool = False, limit: int | None = None) -> list[Any]:
        items = self.get_state_list(key)
        if unique and value in items:
            return items
        items.insert(0, value)
        items = _trim_list(items, limit, keep_tail=False)
        self.set_state(key, items)
        return items

    def append_state_record(
        self,
        key: str,
        values: dict[str, Any] | None = None,
        *,
        limit: int = 50,
        **items: Any,
    ) -> dict[str, Any]:
        record: dict[str, Any] = {}
        if values:
            record.update(values)
        if items:
            record.update(items)
        record.setdefault("time", datetime.now().isoformat(timespec="seconds"))
        self.append_state_list(key, record, limit=limit)
        return record

    def recent_state_records(self, key: str, limit: int = 10) -> list[dict[str, Any]]:
        records = [dict(item) for item in self.get_state_list(key) if isinstance(item, dict)]
        if limit > 0:
            records = records[-limit:]
        records.reverse()
        return records

    def clear_state_list(self, key: str) -> None:
        self.set_state(key, [])

    def remove_state_list(self, key: str, value: Any) -> list[Any]:
        items = self.get_state_list(key)
        updated = [item for item in items if item != value]
        if updated != items:
            self.set_state(key, updated)
        return updated

    def update_state_dict(
        self,
        key: str,
        values: dict[str, Any] | None = None,
        **items: Any,
    ) -> dict[str, Any]:
        data = self.get_state_dict(key)
        if values:
            data.update(values)
        if items:
            data.update(items)
        self.set_state(key, data)
        return data

    def user_id_of(self, event_or_user: Any) -> str:
        return _event_user_id(event_or_user)

    def group_id_of(self, event_or_group: Any) -> str:
        return _event_group_id(event_or_group)

    def message_text(self, event: Any, default: str = "") -> str:
        return _message_text(event, default=default)

    def message_segments(self, event: Any) -> tuple[MessageSegment, ...]:
        return _message_segments(event)

    def plain_text(self, event: Any, default: str = "") -> str:
        return segments_to_text(self.message_segments(event), fallback=self.message_text(event, default=default))

    def segment_data(self, event: Any, segment_type: str) -> list[dict[str, Any]]:
        wanted = str(segment_type).strip()
        return [dict(segment.data) for segment in self.message_segments(event) if segment.type == wanted]

    def image_files(self, event: Any) -> list[str]:
        return [_segment_value(data, "file", "url", "path") for data in self.segment_data(event, "image") if _segment_value(data, "file", "url", "path")]

    def first_image(self, event: Any) -> str:
        images = self.image_files(event)
        return images[0] if images else ""

    def reply_ids(self, event: Any) -> list[str]:
        return [_segment_value(data, "id", "message_id") for data in self.segment_data(event, "reply") if _segment_value(data, "id", "message_id")]

    def first_reply_id(self, event: Any) -> str:
        replies = self.reply_ids(event)
        return replies[0] if replies else ""

    def at_users(self, event: Any) -> list[str]:
        return _at_users(event)

    def has_at(self, event: Any, user_id: str | int = "all") -> bool:
        target = str(user_id)
        return target in self.at_users(event)

    def is_at_me(self, event: Any, bot_id: str | int | None = None) -> bool:
        candidates = _ordered_ids_from_values(
            bot_id,
            getattr(event, "self_id", ""),
            self.config.get("bot_qq"),
            self.config.get("self_id"),
            self.config.get("qq"),
            self.config.get("account"),
        )
        return any(self.has_at(event, candidate) for candidate in candidates)

    def strip_at(self, event: Any, *user_ids: str | int) -> str:
        targets = {str(item) for item in user_ids if str(item).strip()}
        return _strip_at_text(event, targets)

    def is_private_message(self, event: Any) -> bool:
        return _message_type(event) == "private"

    def is_group_message(self, event: Any) -> bool:
        return _message_type(event) == "group"

    def match_command(
        self,
        event: Any,
        *commands: str,
        prefixes: tuple[str, ...] | list[str] = ("", "/", "!", "！"),
        case_sensitive: bool = False,
    ) -> tuple[str, str] | None:
        text = self.message_text(event).strip()
        if not text:
            return None
        text_for_match = text if case_sensitive else text.lower()
        for command in commands:
            command_text = str(command).strip()
            if not command_text:
                continue
            command_for_match = command_text if case_sensitive else command_text.lower()
            for prefix in prefixes:
                probe = f"{prefix}{command_for_match}"
                if not probe:
                    continue
                if text_for_match == probe:
                    return command_text, ""
                if text_for_match.startswith(probe) and text_for_match[len(probe) : len(probe) + 1].isspace():
                    return command_text, text[len(probe) :].strip()
                if not prefix and text_for_match.startswith(probe):
                    return command_text, text[len(probe) :].strip()
        return None

    def command_args(
        self,
        event: Any,
        command: str,
        *,
        prefixes: tuple[str, ...] | list[str] = ("", "/", "!", "！"),
        case_sensitive: bool = False,
    ) -> str | None:
        matched = self.match_command(event, command, prefixes=prefixes, case_sensitive=case_sensitive)
        return matched[1] if matched else None

    def parse_user_ids(self, value: Any, *, include_at: bool = True, min_digits: int = 5) -> list[str]:
        return _parse_user_ids(value, include_at=include_at, min_digits=min_digits)

    def first_user_id(self, value: Any, *, include_at: bool = True, min_digits: int = 5) -> str:
        user_ids = self.parse_user_ids(value, include_at=include_at, min_digits=min_digits)
        return user_ids[0] if user_ids else ""

    def parse_duration(
        self,
        value: Any,
        default: int = 0,
        *,
        max_seconds: int | None = None,
    ) -> int:
        seconds = _parse_duration_seconds(value, default=default)
        if max_seconds is not None and seconds > max_seconds:
            return int(max_seconds)
        return seconds

    def parse_key_value(self, value: Any, separators: tuple[str, ...] = ("=", "＝", ":", "：")) -> tuple[str, str]:
        return _parse_key_value(value, separators=separators)

    def is_owner(self, event_or_user: Any) -> bool:
        user_id = self.user_id_of(event_or_user)
        return bool(user_id and user_id in _config_ids(self.config, "owners", "owner", "superusers", "superuser"))

    def is_admin(self, event_or_user: Any, group_id: str | int | None = None) -> bool:
        user_id = self.user_id_of(event_or_user)
        if not user_id:
            return False
        if self.is_owner(user_id):
            return True
        if user_id in _config_ids(self.config, "admins", "admin", "global_admins", "global_admin"):
            return True
        group = str(group_id) if group_id is not None else self.group_id_of(event_or_user)
        if not group:
            return False
        group_admins = self.config.get("group_admins", {})
        if isinstance(group_admins, dict):
            value = group_admins.get(group)
            if value is None and group.isdigit():
                value = group_admins.get(int(group))
            return user_id in _ids_from_value(value)
        return user_id in _ids_from_value(group_admins)

    def require_owner(self, event_or_user: Any, deny_text: str = "权限不足") -> bool:
        if self.is_owner(event_or_user):
            return True
        if deny_text and not isinstance(event_or_user, (str, int)):
            self.reply(event_or_user, deny_text)
        return False

    def require_admin(
        self,
        event_or_user: Any,
        group_id: str | int | None = None,
        deny_text: str = "权限不足",
    ) -> bool:
        if self.is_admin(event_or_user, group_id=group_id):
            return True
        if deny_text and not isinstance(event_or_user, (str, int)):
            self.reply(event_or_user, deny_text)
        return False

    def notify_owners(self, text: str) -> list[SendResult]:
        return self.send_private_many(_ordered_config_ids(self.config, "owners", "owner", "superusers", "superuser"), text)

    def notify_admins(self, text: str, *, include_owners: bool = True) -> list[SendResult]:
        keys = ["admins", "admin", "global_admins", "global_admin"]
        if include_owners:
            keys.extend(["owners", "owner", "superusers", "superuser"])
        return self.send_private_many(_ordered_config_ids(self.config, *keys), text)

    def notify_config_users(
        self,
        config_key: str,
        text: str,
        *,
        include_admins: bool = False,
        include_owners: bool = False,
    ) -> list[SendResult]:
        values: list[Any] = [self.config.get(config_key)]
        if include_admins:
            values.extend(self.config.get(key) for key in ("admins", "admin", "global_admins", "global_admin"))
        if include_owners:
            values.extend(self.config.get(key) for key in ("owners", "owner", "superusers", "superuser"))
        return self.send_private_many(_ordered_ids_from_values(*values), text)

    def notify_config_groups(self, config_key: str, text: str) -> list[SendResult]:
        return self.send_group_many(self.config.get(config_key), text)

    def check_cooldown(
        self,
        key: str,
        seconds: int | float,
        *,
        scope: str | int | None = None,
        event: Any = None,
        update: bool = True,
        now: float | None = None,
    ) -> tuple[bool, float]:
        if seconds <= 0:
            return True, 0.0
        current = time.time() if now is None else float(now)
        cooldowns = self.get_state_dict("_cooldowns")
        cooldown_key = _cooldown_key(key, scope=scope, event=event)
        last = _float_value(cooldowns.get(cooldown_key), 0.0)
        remaining = max(0.0, float(seconds) - (current - last))
        if remaining > 0:
            return False, remaining
        if update:
            cooldowns[cooldown_key] = current
            self.set_state("_cooldowns", cooldowns)
        return True, 0.0

    def cooldown_remaining(
        self,
        key: str,
        seconds: int | float,
        *,
        scope: str | int | None = None,
        event: Any = None,
        now: float | None = None,
    ) -> float:
        ok, remaining = self.check_cooldown(key, seconds, scope=scope, event=event, update=False, now=now)
        return 0.0 if ok else remaining

    def touch_cooldown(
        self,
        key: str,
        *,
        scope: str | int | None = None,
        event: Any = None,
        now: float | None = None,
    ) -> None:
        cooldowns = self.get_state_dict("_cooldowns")
        cooldowns[_cooldown_key(key, scope=scope, event=event)] = time.time() if now is None else float(now)
        self.set_state("_cooldowns", cooldowns)

    def clear_cooldown(self, key: str, *, scope: str | int | None = None, event: Any = None) -> None:
        cooldowns = self.get_state_dict("_cooldowns")
        cooldown_key = _cooldown_key(key, scope=scope, event=event)
        if cooldown_key in cooldowns:
            del cooldowns[cooldown_key]
            self.set_state("_cooldowns", cooldowns)

    def delete_state(self, key: str) -> None:
        self.state_revision += 1
        self.state_store.delete(self.plugin_id or "shared", key)

    def every(self, name: str, seconds: float, callback: Callable[[], None]) -> None:
        if seconds <= 0:
            raise ValueError("timer interval must be positive")
        if not self.timer_fn:
            self.log(f"定时任务未启用：{name}")
            return
        self.timer_fn(name, seconds, callback)

    def for_plugin(self, plugin_id: str, config: dict[str, Any] | None = None) -> "PluginContext":
        merged_config = dict(self.config or {})
        if config:
            merged_config.update(config)
        return PluginContext(
            send_fn=self.send_fn,
            config=merged_config,
            plugin_id=plugin_id,
            data_root=self.data_root,
            state_store=self.state_store,
            timer_fn=self.timer_fn,
            onebot_call_fn=self.onebot_call_fn,
            history_fn=self.history_fn,
            logs=self.logs,
            runtime_registry=self.runtime_registry,
        )

    def _send(self, target: str, text: str, message_type: str) -> SendResult:
        self.send_count += 1
        return self.send_fn(target, text, message_type)


def _number_or_text(value: str | int) -> int | str:
    text = str(value)
    return int(text) if text.isdigit() else text


def _trim_list(items: list[Any], limit: int | None, *, keep_tail: bool = True) -> list[Any]:
    if limit is None or limit <= 0 or len(items) <= limit:
        return items
    return items[-limit:] if keep_tail else items[:limit]


def _bool_value(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return bool(default)
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on", "enable", "enabled", "开启", "是"}:
        return True
    if text in {"0", "false", "no", "n", "off", "disable", "disabled", "关闭", "否"}:
        return False
    return bool(default)


def _message_from_segments(segments: Any) -> str:
    if isinstance(segments, str):
        return segments
    if isinstance(segments, MessageSegment):
        return segments_to_cq([segments])
    if isinstance(segments, dict):
        segment = _segment_from_dict(segments)
        return segments_to_cq([segment]) if segment else ""
    normalized: list[MessageSegment] = []
    try:
        items = list(segments)
    except TypeError:
        return cq_text(str(segments))
    for item in items:
        if isinstance(item, str):
            normalized.extend(parse_cq_message(item))
            continue
        if isinstance(item, MessageSegment):
            normalized.append(item)
            continue
        if isinstance(item, dict):
            segment = _segment_from_dict(item)
            if segment:
                normalized.append(segment)
            continue
        normalized.append(MessageSegment("text", {"text": str(item)}))
    return segments_to_cq(normalized)


def _message_body(message: Any) -> str:
    if isinstance(message, str):
        return message
    return _message_from_segments(message)


def _segment_from_dict(item: dict[str, Any]) -> MessageSegment | None:
    segment_type = str(item.get("type") or "").strip()
    if not segment_type:
        return None
    data = item.get("data") or {}
    return MessageSegment(segment_type, data.copy() if isinstance(data, dict) else {})


def _file_name(file: str) -> str:
    normalized = file.replace("\\", "/")
    if normalized.startswith(("http://", "https://", "file://")):
        normalized = urlparse(normalized).path or normalized
    return PureWindowsPath(normalized).name or "file"


def _segment_value(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return ""


def _ids_from_value(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, (str, int)):
        text = str(value).strip()
        if not text:
            return set()
        if "," in text:
            return {item.strip() for item in text.split(",") if item.strip()}
        return {text}
    if isinstance(value, dict):
        return {str(key) for key, enabled in value.items() if enabled}
    if isinstance(value, (list, tuple, set)):
        return {str(item).strip() for item in value if str(item).strip()}
    return {str(value).strip()} if str(value).strip() else set()


def _ordered_ids_from_values(*values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, (str, int)):
            text = str(value).strip()
            if not text:
                return
            items = [item.strip() for item in text.split(",")] if "," in text else [text]
            for item in items:
                if item and item not in seen:
                    seen.add(item)
                    result.append(item)
            return
        if isinstance(value, dict):
            for key, enabled in value.items():
                if enabled:
                    add(key)
            return
        if isinstance(value, (list, tuple, set)):
            for item in value:
                add(item)
            return
        add(str(value))

    for value in values:
        add(value)
    return result


def _config_ids(config: dict[str, Any], *keys: str) -> set[str]:
    result: set[str] = set()
    for key in keys:
        result.update(_ids_from_value(config.get(key)))
    return result


def _ordered_config_ids(config: dict[str, Any], *keys: str) -> list[str]:
    return _ordered_ids_from_values(*(config.get(key) for key in keys))


def _event_user_id(event_or_user: Any) -> str:
    if isinstance(event_or_user, (str, int)):
        return str(event_or_user)
    message = getattr(event_or_user, "message", None)
    if message is not None:
        return _event_user_id(message)
    sender = getattr(event_or_user, "sender", None)
    if isinstance(sender, dict):
        value = sender.get("user_id") or sender.get("uin")
        if value:
            return str(value)
    if sender:
        return str(sender)
    raw = getattr(event_or_user, "raw", None)
    if isinstance(raw, dict):
        raw_sender = raw.get("sender")
        if isinstance(raw_sender, dict):
            value = raw_sender.get("user_id") or raw_sender.get("uin")
            if value:
                return str(value)
        value = raw.get("user_id") or raw.get("operator_id")
        if value:
            return str(value)
    value = getattr(event_or_user, "user_id", None) or getattr(event_or_user, "operator_id", None)
    return str(value or "")


def _event_group_id(event_or_group: Any) -> str:
    if isinstance(event_or_group, (str, int)):
        return str(event_or_group)
    message = getattr(event_or_group, "message", None)
    if message is not None:
        return _event_group_id(message)
    target = getattr(event_or_group, "target", None)
    message_type = str(getattr(event_or_group, "message_type", "") or "")
    if target and message_type == "group":
        return str(target)
    value = getattr(event_or_group, "group_id", None)
    if value:
        return str(value)
    raw = getattr(event_or_group, "raw", None)
    if isinstance(raw, dict):
        value = raw.get("group_id")
        if value:
            return str(value)
    return ""


def _message_type(event: Any) -> str:
    message = getattr(event, "message", None)
    if message is not None:
        return _message_type(message)
    value = getattr(event, "message_type", None)
    if value:
        return str(value)
    raw = getattr(event, "raw", None)
    if isinstance(raw, dict):
        value = raw.get("message_type") or raw.get("detail_type")
        if value:
            return str(value)
    return ""


def _message_text(event: Any, default: str = "") -> str:
    message = getattr(event, "message", None)
    if message is not None:
        return _message_text(message, default=default)
    raw = getattr(event, "raw", None)
    if isinstance(raw, dict):
        value = raw.get("raw_message")
        if value is not None:
            return str(value)
        value = raw.get("message")
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return _plain_text_from_segments(value)
    value = getattr(event, "text", None)
    if value is not None and str(value):
        return str(value)
    value = getattr(event, "raw_message", None)
    if value is not None and str(value):
        return str(value)
    return default


def _message_segments(event: Any) -> tuple[MessageSegment, ...]:
    message = getattr(event, "message", None)
    if message is not None:
        return _message_segments(message)
    value = getattr(event, "segments", None)
    if value:
        segments: list[MessageSegment] = []
        for item in value:
            segment = _coerce_segment(item)
            if segment is not None:
                segments.append(segment)
        return tuple(segments)
    raw = getattr(event, "raw", None)
    if isinstance(raw, dict):
        raw_message = raw.get("raw_message")
        message_value = raw.get("message")
        if isinstance(message_value, list):
            return tuple(segment for item in message_value if (segment := _coerce_segment(item)) is not None)
        if isinstance(message_value, str):
            return parse_cq_message(message_value)
        if raw_message is not None:
            return parse_cq_message(str(raw_message))
    raw_message_value = getattr(event, "raw_message", None)
    if raw_message_value:
        return parse_cq_message(str(raw_message_value))
    text = getattr(event, "text", None)
    if text:
        return parse_cq_message(str(text))
    return ()


def _coerce_segment(value: Any) -> MessageSegment | None:
    if isinstance(value, MessageSegment):
        return value
    if isinstance(value, dict):
        return _segment_from_dict(value)
    if isinstance(value, str):
        return MessageSegment("text", {"text": value})
    return None


def _at_users(event: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for segment in _message_segments(event):
        if segment.type != "at":
            continue
        user_id = str(segment.data.get("qq") or segment.data.get("user_id") or "").strip()
        if user_id and user_id not in seen:
            seen.add(user_id)
            result.append(user_id)
    return result


def _strip_at_text(event: Any, targets: set[str]) -> str:
    return _strip_at_segments(_message_segments(event), targets)


def _strip_at_segments(segments: tuple[MessageSegment, ...] | list[MessageSegment], targets: set[str]) -> str:
    parts: list[str] = []
    for segment in segments:
        if segment.type == "at":
            user_id = str(segment.data.get("qq") or segment.data.get("user_id") or "").strip()
            if not targets or user_id in targets:
                continue
        if segment.type == "text":
            parts.append(str(segment.data.get("text") or ""))
        else:
            parts.append(segments_to_cq([segment]))
    return "".join(parts).strip()


def _parse_user_ids(value: Any, *, include_at: bool = True, min_digits: int = 5) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    def add(user_id: str) -> None:
        text = str(user_id).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)

    if include_at:
        for user_id in _at_users(value):
            add(user_id)
    text = _argument_text(value, strip_at=include_at)
    if include_at and isinstance(value, str):
        for segment in parse_cq_message(value):
            if segment.type == "at":
                add(str(segment.data.get("qq") or segment.data.get("user_id") or ""))
    pattern = re.compile(rf"(?<!\d)(\d{{{max(1, int(min_digits))},}})(?!\d)")
    for match in pattern.finditer(text):
        add(match.group(1))
    return result


def _parse_duration_seconds(value: Any, *, default: int = 0) -> int:
    text = _argument_text(value, strip_at=True)
    pattern = re.compile(r"(?<!\d)(\d+)(?:\s*(秒|s|sec|secs|second|seconds|分|分钟|m|min|mins|minute|minutes|时|小时|h|hr|hour|hours|天|日|d|day|days))?", re.IGNORECASE)
    unitless: list[int] = []
    for match in pattern.finditer(text):
        number = int(match.group(1))
        unit_value = match.group(2)
        if not unit_value:
            unitless.append(number)
            continue
        unit = unit_value.lower()
        if unit in {"秒", "s", "sec", "secs", "second", "seconds"}:
            return number
        if unit in {"分", "分钟", "m", "min", "mins", "minute", "minutes"}:
            return number * 60
        if unit in {"时", "小时", "h", "hr", "hour", "hours"}:
            return number * 60 * 60
        if unit in {"天", "日", "d", "day", "days"}:
            return number * 24 * 60 * 60
    if unitless:
        return unitless[-1]
    return int(default)


def _parse_key_value(value: Any, *, separators: tuple[str, ...]) -> tuple[str, str]:
    text = _argument_text(value, strip_at=False).strip()
    for separator in separators:
        if separator in text:
            key, raw_value = text.split(separator, 1)
            return key.strip(), raw_value.strip()
    return "", ""


def _argument_text(value: Any, *, strip_at: bool = False) -> str:
    if isinstance(value, str):
        return _strip_at_segments(parse_cq_message(value), set()) if strip_at else value
    if isinstance(value, (int, float)):
        return str(value)
    if _message_segments(value):
        return _strip_at_text(value, set()) if strip_at else _message_text(value, default=segments_to_cq(_message_segments(value)))
    return str(value or "")


def _plain_text_from_segments(segments: list[Any]) -> str:
    parts: list[str] = []
    for item in segments:
        if isinstance(item, str):
            parts.append(item)
            continue
        if isinstance(item, MessageSegment):
            if item.type == "text":
                parts.append(str(item.data.get("text") or ""))
            else:
                parts.append(segments_to_cq([item]))
            continue
        if isinstance(item, dict):
            segment_type = str(item.get("type") or "")
            data = item.get("data") if isinstance(item.get("data"), dict) else {}
            if segment_type == "text":
                parts.append(str(data.get("text") or ""))
            else:
                segment = _segment_from_dict(item)
                if segment:
                    parts.append(segments_to_cq([segment]))
    return "".join(parts)


def _cooldown_key(key: str, *, scope: str | int | None = None, event: Any = None) -> str:
    selected_scope = str(scope) if scope is not None else ""
    if not selected_scope and event is not None:
        group_id = _event_group_id(event)
        user_id = _event_user_id(event)
        selected_scope = f"group:{group_id}:user:{user_id}" if group_id else f"user:{user_id}"
    if not selected_scope:
        selected_scope = "global"
    return f"{key}:{selected_scope}"


def _float_value(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _reply_target(event: Any) -> tuple[str, str]:
    message = getattr(event, "message", None)
    if message is not None:
        return _reply_target(message)
    message_type = str(getattr(event, "message_type", "") or "")
    if message_type == "group":
        target = str(getattr(event, "target", "") or getattr(event, "group_id", "") or "")
        return "group", target
    user_id = str(getattr(event, "sender", "") or getattr(event, "user_id", "") or "")
    return "private", user_id


def _event_message_id(event: Any) -> str:
    return str(getattr(event, "message_id", "") or "")

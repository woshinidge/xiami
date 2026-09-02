from __future__ import annotations

import json
import time
from pathlib import PureWindowsPath
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from xiami_core.onebot.forward import normalize_forward_messages
from xiami_core.onebot.message_segments import cq_image
from xiami_core.onebot.action_log import (
    OneBotActionLogEntry,
    append_onebot_action_log,
    compact_action_params,
)
from xiami_core.onebot.stats import OneBotActionStats


@dataclass(frozen=True)
class OneBotResponse:
    ok: bool
    data: Any = None
    message: str = ""


class OneBotHttpClient:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:3000",
        access_token: str = "",
        timeout: float = 2.0,
        action_stats: OneBotActionStats | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self.timeout = timeout
        self.action_stats = action_stats or OneBotActionStats()

    def get_login_info(self) -> OneBotResponse:
        return self.call("get_login_info", {})

    def get_status(self) -> OneBotResponse:
        return self.call("get_status", {})

    def get_version(self) -> OneBotResponse:
        return self.call("get_version_info", {})

    def get_friend_list(self) -> OneBotResponse:
        return self.call("get_friend_list", {})

    def get_group_list(self) -> OneBotResponse:
        return self.call("get_group_list", {})

    def get_group_member_list(self, group_id: str | int) -> OneBotResponse:
        return self.call("get_group_member_list", {"group_id": _number_or_text(group_id)})

    def get_group_info(self, group_id: str | int, no_cache: bool = True) -> OneBotResponse:
        return self.call("get_group_info", {"group_id": _number_or_text(group_id), "no_cache": bool(no_cache)})

    def get_group_member_info(self, group_id: str | int, user_id: str | int, no_cache: bool = True) -> OneBotResponse:
        return self.call(
            "get_group_member_info",
            {"group_id": _number_or_text(group_id), "user_id": _number_or_text(user_id), "no_cache": bool(no_cache)},
        )

    def get_stranger_info(self, user_id: str | int, no_cache: bool = True) -> OneBotResponse:
        return self.call("get_stranger_info", {"user_id": _number_or_text(user_id), "no_cache": bool(no_cache)})

    def get_msg(self, message_id: str | int) -> OneBotResponse:
        return self.call("get_msg", {"message_id": _number_or_text(message_id)})

    def send_like(self, user_id: str | int, times: int = 1) -> OneBotResponse:
        return self.call("send_like", {"user_id": _number_or_text(user_id), "times": int(times)})

    def send_poke(self, user_id: str | int, group_id: str | int | None = None) -> OneBotResponse:
        params: dict[str, Any] = {"user_id": _number_or_text(user_id)}
        if group_id is not None:
            params["group_id"] = _number_or_text(group_id)
        return self.call("send_poke", params)

    def send_private_msg(self, user_id: str, message: str) -> OneBotResponse:
        return self.call("send_private_msg", {"user_id": _number_or_text(user_id), "message": message})

    def send_private_image(self, user_id: str | int, file: str) -> OneBotResponse:
        return self.send_private_msg(user_id, cq_image(file))

    def send_group_msg(self, group_id: str, message: str) -> OneBotResponse:
        return self.call("send_group_msg", {"group_id": _number_or_text(group_id), "message": message})

    def send_group_image(self, group_id: str | int, file: str) -> OneBotResponse:
        return self.send_group_msg(group_id, cq_image(file))

    def upload_group_file(self, group_id: str | int, file: str, name: str = "") -> OneBotResponse:
        return self.call(
            "upload_group_file",
            {"group_id": _number_or_text(group_id), "file": file, "name": name or _file_name(file)},
        )

    def get_group_root_files(self, group_id: str | int) -> OneBotResponse:
        return self.call("get_group_root_files", {"group_id": _number_or_text(group_id)})

    def get_group_files_by_folder(self, group_id: str | int, folder_id: str) -> OneBotResponse:
        return self.call(
            "get_group_files_by_folder",
            {"group_id": _number_or_text(group_id), "folder_id": folder_id},
        )

    def get_group_file_url(self, group_id: str | int, file_id: str, busid: str | int) -> OneBotResponse:
        return self.call(
            "get_group_file_url",
            {"group_id": _number_or_text(group_id), "file_id": file_id, "busid": _number_or_text(busid)},
        )

    def create_group_file_folder(self, group_id: str | int, folder_name: str, parent_id: str = "/") -> OneBotResponse:
        return self.call(
            "create_group_file_folder",
            {"group_id": _number_or_text(group_id), "folder_name": folder_name, "parent_id": parent_id},
        )

    def delete_group_folder(self, group_id: str | int, folder_id: str) -> OneBotResponse:
        return self.call(
            "delete_group_folder",
            {"group_id": _number_or_text(group_id), "folder_id": folder_id},
        )

    def delete_group_file(self, group_id: str | int, file_id: str, busid: str | int) -> OneBotResponse:
        return self.call(
            "delete_group_file",
            {"group_id": _number_or_text(group_id), "file_id": file_id, "busid": _number_or_text(busid)},
        )

    def send_group_forward_msg(self, group_id: str | int, messages: Any) -> OneBotResponse:
        return self.call(
            "send_group_forward_msg",
            {"group_id": _number_or_text(group_id), "messages": normalize_forward_messages(messages)},
        )

    def send_private_forward_msg(self, user_id: str | int, messages: Any) -> OneBotResponse:
        return self.call(
            "send_private_forward_msg",
            {"user_id": _number_or_text(user_id), "messages": normalize_forward_messages(messages)},
        )

    def get_image(self, file: str) -> OneBotResponse:
        return self.call("get_image", {"file": file})

    def get_record(self, file: str, out_format: str = "mp3") -> OneBotResponse:
        return self.call("get_record", {"file": file, "out_format": out_format})

    def set_group_ban(self, group_id: str, user_id: str, duration: int) -> OneBotResponse:
        return self.call(
            "set_group_ban",
            {"group_id": _number_or_text(group_id), "user_id": _number_or_text(user_id), "duration": int(duration)},
        )

    def set_group_whole_ban(self, group_id: str | int, enable: bool = True) -> OneBotResponse:
        return self.call("set_group_whole_ban", {"group_id": _number_or_text(group_id), "enable": bool(enable)})

    def set_group_kick(self, group_id: str, user_id: str, reject_add_request: bool = False) -> OneBotResponse:
        return self.call(
            "set_group_kick",
            {
                "group_id": _number_or_text(group_id),
                "user_id": _number_or_text(user_id),
                "reject_add_request": bool(reject_add_request),
            },
        )

    def set_group_admin(self, group_id: str | int, user_id: str | int, enable: bool = True) -> OneBotResponse:
        return self.call(
            "set_group_admin",
            {"group_id": _number_or_text(group_id), "user_id": _number_or_text(user_id), "enable": bool(enable)},
        )

    def set_group_card(self, group_id: str | int, user_id: str | int, card: str = "") -> OneBotResponse:
        return self.call(
            "set_group_card",
            {"group_id": _number_or_text(group_id), "user_id": _number_or_text(user_id), "card": card},
        )

    def set_group_name(self, group_id: str | int, group_name: str) -> OneBotResponse:
        return self.call("set_group_name", {"group_id": _number_or_text(group_id), "group_name": group_name})

    def set_group_special_title(
        self,
        group_id: str | int,
        user_id: str | int,
        special_title: str = "",
        duration: int = -1,
    ) -> OneBotResponse:
        return self.call(
            "set_group_special_title",
            {
                "group_id": _number_or_text(group_id),
                "user_id": _number_or_text(user_id),
                "special_title": special_title,
                "duration": int(duration),
            },
        )

    def set_group_leave(self, group_id: str | int, is_dismiss: bool = False) -> OneBotResponse:
        return self.call("set_group_leave", {"group_id": _number_or_text(group_id), "is_dismiss": bool(is_dismiss)})

    def set_group_notice(self, group_id: str | int, content: str, image: str = "") -> OneBotResponse:
        return self.call("_send_group_notice", {"group_id": _number_or_text(group_id), "content": content, "image": image})

    def get_group_notice(self, group_id: str | int) -> OneBotResponse:
        return self.call("_get_group_notice", {"group_id": _number_or_text(group_id)})

    def get_group_honor_info(self, group_id: str | int, honor_type: str = "all") -> OneBotResponse:
        return self.call("get_group_honor_info", {"group_id": _number_or_text(group_id), "type": honor_type})

    def set_essence_msg(self, message_id: str | int) -> OneBotResponse:
        return self.call("set_essence_msg", {"message_id": _number_or_text(message_id)})

    def delete_essence_msg(self, message_id: str | int) -> OneBotResponse:
        return self.call("delete_essence_msg", {"message_id": _number_or_text(message_id)})

    def set_group_add_request(
        self,
        flag: str,
        sub_type: str,
        approve: bool,
        reason: str = "",
    ) -> OneBotResponse:
        return self.call(
            "set_group_add_request",
            {"flag": flag, "sub_type": sub_type, "approve": bool(approve), "reason": reason},
        )

    def set_friend_add_request(self, flag: str, approve: bool, remark: str = "") -> OneBotResponse:
        return self.call("set_friend_add_request", {"flag": flag, "approve": bool(approve), "remark": remark})

    def delete_msg(self, message_id: str | int) -> OneBotResponse:
        return self.call("delete_msg", {"message_id": _number_or_text(message_id)})

    def call(self, action: str, params: dict[str, Any]) -> OneBotResponse:
        started = time.monotonic()
        response = self._call_once(action, params)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        self.action_stats.record(action, response.ok, elapsed_ms, response.message)
        append_onebot_action_log(
            OneBotActionLogEntry(
                action=action,
                ok=response.ok,
                elapsed_ms=elapsed_ms,
                message=response.message,
                params=compact_action_params(params),
            )
        )
        return response

    def _call_once(self, action: str, params: dict[str, Any]) -> OneBotResponse:
        url = f"{self.base_url}/{action}"
        payload = json.dumps(params, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(url, data=payload, method="POST")
        request.add_header("Content-Type", "application/json")
        if self.access_token:
            request.add_header("Authorization", f"Bearer {self.access_token}")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.URLError as exc:
            return OneBotResponse(ok=False, message=str(exc))
        except OSError as exc:
            return OneBotResponse(ok=False, message=str(exc))
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            return OneBotResponse(ok=False, message=raw)
        status = body.get("status")
        retcode = body.get("retcode")
        ok = status == "ok" or retcode == 0
        return OneBotResponse(ok=ok, data=body.get("data"), message=body.get("wording") or body.get("message") or raw)


def _number_or_text(value: str | int) -> int | str:
    text = str(value).strip()
    return int(text) if text.isdigit() else text


def _file_name(file: str) -> str:
    normalized = file.replace("\\", "/")
    if normalized.startswith(("http://", "https://", "file://")):
        normalized = urllib.parse.urlparse(normalized).path or normalized
    return PureWindowsPath(normalized).name or "file"

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal

from xiami_core.plugins.context import PluginContext


MatchType = Literal["contains", "exact", "regex", "prefix", "suffix"]


@dataclass(frozen=True)
class CustomReply:
    keyword: str
    response: str
    match_type: MatchType
    enabled: bool = True


class CustomReplyService:
    def __init__(self, ctx: PluginContext) -> None:
        self.ctx = ctx

    def set(self, group_id: str, keyword: str, response: str, match_type: MatchType = "contains", enabled: bool = True) -> bool:
        group_id = str(group_id)
        keyword = keyword.strip()
        response = response.strip()
        match_type = normalize_match_type(match_type)
        if not group_id or not keyword or not response:
            return False

        replies = self._replies()
        group = replies.setdefault(group_id, {})
        group[keyword] = {"response": response, "match_type": match_type, "enabled": bool(enabled)}
        self.ctx.set_state("custom_replies", replies)
        return True

    def import_lines(self, group_id: str, text: str) -> int:
        count = 0
        for line in str(text or "").splitlines():
            keyword, response, match_type, enabled = self.parse_line(line)
            if self.set(group_id, keyword, response, match_type, enabled):
                count += 1
        return count

    def set_enabled(self, group_id: str, keyword: str, enabled: bool) -> int:
        keyword = keyword.strip()
        replies = self._replies()
        group = replies.get(str(group_id), {})
        if not isinstance(group, dict) or keyword not in group or not isinstance(group.get(keyword), dict):
            return 0
        group[keyword]["enabled"] = bool(enabled)
        replies[str(group_id)] = group
        self.ctx.set_state("custom_replies", replies)
        return 1

    def delete(self, group_id: str, keyword: str) -> int:
        keyword = keyword.strip()
        replies = self._replies()
        group = replies.get(str(group_id), {})
        if keyword not in group:
            return 0
        del group[keyword]
        if group:
            replies[str(group_id)] = group
        else:
            replies.pop(str(group_id), None)
        self.ctx.set_state("custom_replies", replies)
        return 1

    def clear_group(self, group_id: str) -> int:
        replies = self._replies()
        group_id = str(group_id)
        group = replies.get(group_id, {})
        removed = len(group) if isinstance(group, dict) else 0
        replies.pop(group_id, None)
        self.ctx.set_state("custom_replies", replies)
        return removed

    def list(self, group_id: str, query: str = "") -> list[CustomReply]:
        group = self._replies().get(str(group_id), {})
        result: list[CustomReply] = []
        if not isinstance(group, dict):
            return result
        query_text = str(query or "").strip().lower()
        for keyword, value in sorted(group.items()):
            if not isinstance(value, dict):
                continue
            response = str(value.get("response", ""))
            match_type = normalize_match_type(value.get("match_type"))
            enabled = bool(value.get("enabled", True))
            label = match_type_label(match_type).lower()
            status = "启用" if enabled else "停用"
            if query_text and query_text not in str(keyword).lower() and query_text not in response.lower() and query_text not in label and query_text not in status:
                continue
            result.append(CustomReply(str(keyword), response, match_type, enabled))
        return result

    def match(self, group_id: str, message: str, user_id: str) -> str:
        for reply in self.list(group_id):
            if not reply.enabled:
                continue
            matched = self._match_reply(reply, message)
            if matched:
                return self._render_response(reply.response, user_id, group_id, message, matched)
        return ""

    def export_lines(self, group_id: str, query: str = "") -> list[str]:
        return [self.format_line(reply) for reply in self.list(group_id, query)]

    def format_line(self, reply: CustomReply) -> str:
        prefix_parts = []
        if not reply.enabled:
            prefix_parts.append("停用")
        if reply.match_type != "contains":
            prefix_parts.append(match_type_label(reply.match_type))
        prefix = "".join(f"{part}:" for part in prefix_parts)
        return f"{prefix}{reply.keyword}={reply.response}"

    def parse_pair(self, text: str) -> tuple[str, str]:
        sep = "=" if "=" in text else "＝" if "＝" in text else ""
        if not sep:
            return "", ""
        keyword, response = text.split(sep, 1)
        return keyword.strip(), response.strip()

    def parse_line(self, text: str) -> tuple[str, str, MatchType, bool]:
        raw = str(text or "").strip()
        if not raw or raw.startswith("#"):
            return "", "", "contains", True
        match_type: MatchType = "contains"
        enabled = True
        lowered = raw.lower()
        prefixes: tuple[tuple[str, str, str], ...] = (
            ("[启用]", "status", "on"),
            ("【启用】", "status", "on"),
            ("启用:", "status", "on"),
            ("启用：", "status", "on"),
            ("[停用]", "status", "off"),
            ("【停用】", "status", "off"),
            ("停用:", "status", "off"),
            ("停用：", "status", "off"),
            ("[精确]", "exact"),
            ("【精确】", "type", "exact"),
            ("精确:", "type", "exact"),
            ("精确：", "type", "exact"),
            ("exact:", "type", "exact"),
            ("exact：", "type", "exact"),
            ("[包含]", "type", "contains"),
            ("【包含】", "type", "contains"),
            ("包含:", "type", "contains"),
            ("包含：", "type", "contains"),
            ("contains:", "type", "contains"),
            ("contains：", "type", "contains"),
            ("[正则]", "type", "regex"),
            ("【正则】", "type", "regex"),
            ("正则:", "type", "regex"),
            ("正则：", "type", "regex"),
            ("regex:", "type", "regex"),
            ("regex：", "type", "regex"),
            ("[前缀]", "type", "prefix"),
            ("【前缀】", "type", "prefix"),
            ("前缀:", "type", "prefix"),
            ("前缀：", "type", "prefix"),
            ("prefix:", "type", "prefix"),
            ("prefix：", "type", "prefix"),
            ("[后缀]", "type", "suffix"),
            ("【后缀】", "type", "suffix"),
            ("后缀:", "type", "suffix"),
            ("后缀：", "type", "suffix"),
            ("suffix:", "type", "suffix"),
            ("suffix：", "type", "suffix"),
        )
        for _ in range(4):
            matched_prefix = False
            lowered = raw.lower()
            for item in prefixes:
                prefix = item[0]
                category = item[1]
                value = item[2] if len(item) >= 3 else item[1]
                probe = prefix.lower()
                if lowered.startswith(probe):
                    if category == "status":
                        enabled = value != "off"
                    else:
                        match_type = normalize_match_type(value)
                    raw = raw[len(prefix):].strip()
                    matched_prefix = True
                    break
            if not matched_prefix:
                break
        keyword, response = self.parse_pair(raw)
        return keyword, response, match_type, enabled

    def _match_reply(self, reply: CustomReply, message: str):
        if reply.match_type == "exact":
            return True if message == reply.keyword else False
        if reply.match_type == "prefix":
            return True if message.startswith(reply.keyword) else False
        if reply.match_type == "suffix":
            return True if message.endswith(reply.keyword) else False
        if reply.match_type == "regex":
            try:
                return re.search(reply.keyword, message)
            except re.error as exc:
                self.ctx.log(f"自定义回复正则错误：{reply.keyword} / {exc}", level="warning")
                return False
        return True if reply.keyword in message else False

    @staticmethod
    def _render_response(response: str, user_id: str, group_id: str, message: str, matched) -> str:
        text = (
            str(response or "")
            .replace("{qq}", str(user_id))
            .replace("{user}", str(user_id))
            .replace("{group}", str(group_id))
            .replace("{msg}", str(message))
            .replace("{message}", str(message))
        )
        if hasattr(matched, "group"):
            try:
                for index, value in enumerate(matched.groups(), start=1):
                    text = text.replace("{" + str(index) + "}", str(value or ""))
            except Exception:
                pass
        return text

    def _replies(self) -> dict[str, dict[str, dict[str, str]]]:
        value = self.ctx.get_state("custom_replies", {})
        return value if isinstance(value, dict) else {}


def normalize_match_type(value: object) -> MatchType:
    text = str(value or "").strip().lower()
    mapping = {
        "exact": "exact",
        "精确": "exact",
        "contains": "contains",
        "contain": "contains",
        "包含": "contains",
        "regex": "regex",
        "regexp": "regex",
        "正则": "regex",
        "prefix": "prefix",
        "startswith": "prefix",
        "前缀": "prefix",
        "suffix": "suffix",
        "endswith": "suffix",
        "后缀": "suffix",
    }
    return mapping.get(text, "contains")  # type: ignore[return-value]


def match_type_label(value: object) -> str:
    return {
        "exact": "精确",
        "regex": "正则",
        "prefix": "前缀",
        "suffix": "后缀",
        "contains": "包含",
    }.get(normalize_match_type(value), "包含")

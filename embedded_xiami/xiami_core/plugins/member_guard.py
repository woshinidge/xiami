from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.permissions import parse_user_ids


Scope = Literal["global", "group"]
ListType = Literal["black", "white"]


@dataclass(frozen=True)
class ListDecision:
    action: Literal["allow", "deny", "none"]
    reason: str = ""
    scope: Scope | None = None
    list_type: ListType | None = None


@dataclass(frozen=True)
class ForbiddenHit:
    word: str
    scope: Scope


class MemberGuardService:
    def __init__(self, ctx: PluginContext) -> None:
        self.ctx = ctx

    def add_members(self, scope: Scope, group_id: str, list_type: ListType, user_ids: list[str]) -> int:
        lists = self._lists()
        key = self._list_key(scope, group_id, list_type)
        values = set(lists.get(key, []))
        before = len(values)
        values.update(str(item) for item in user_ids if str(item).strip())
        lists[key] = sorted(values)
        self.ctx.set_state("member_lists", lists)
        return len(values) - before

    def remove_members(self, scope: Scope, group_id: str, list_type: ListType, user_ids: list[str]) -> int:
        lists = self._lists()
        key = self._list_key(scope, group_id, list_type)
        values = set(lists.get(key, []))
        before = len(values)
        values.difference_update(str(item) for item in user_ids)
        lists[key] = sorted(values)
        self.ctx.set_state("member_lists", lists)
        return before - len(values)

    def clear_members(self, scope: Scope, group_id: str, list_type: ListType) -> int:
        lists = self._lists()
        key = self._list_key(scope, group_id, list_type)
        values = lists.get(key, [])
        removed = len(values) if isinstance(values, list) else 0
        lists.pop(key, None)
        self.ctx.set_state("member_lists", lists)
        return removed

    def members(self, scope: Scope, group_id: str, list_type: ListType) -> list[str]:
        return sorted(
            {
                str(item).strip()
                for item in self._lists().get(self._list_key(scope, group_id, list_type), [])
                if str(item).strip()
            }
        )

    def decide(self, group_id: str, user_id: str) -> ListDecision:
        if self._has_member("global", "", "white", user_id):
            return ListDecision("allow", "全局白名单", "global", "white")
        if self._has_member("global", "", "black", user_id):
            return ListDecision("deny", "全局黑名单", "global", "black")
        if self._has_member("group", group_id, "white", user_id):
            return ListDecision("allow", "本群白名单", "group", "white")
        if self._has_member("group", group_id, "black", user_id):
            return ListDecision("deny", "本群黑名单", "group", "black")
        return ListDecision("none")

    def add_words(self, scope: Scope, group_id: str, words: list[str]) -> int:
        data = self._forbidden_words()
        key = self._word_key(scope, group_id)
        values = set(data.get(key, []))
        before = len(values)
        values.update(word for word in words if word)
        data[key] = sorted(values)
        self.ctx.set_state("forbidden_words", data)
        return len(values) - before

    def remove_words(self, scope: Scope, group_id: str, words: list[str]) -> int:
        data = self._forbidden_words()
        key = self._word_key(scope, group_id)
        values = set(data.get(key, []))
        before = len(values)
        values.difference_update(words)
        data[key] = sorted(values)
        self.ctx.set_state("forbidden_words", data)
        return before - len(values)

    def clear_words(self, scope: Scope, group_id: str) -> int:
        data = self._forbidden_words()
        key = self._word_key(scope, group_id)
        values = data.get(key, [])
        removed = len(values) if isinstance(values, list) else 0
        data.pop(key, None)
        self.ctx.set_state("forbidden_words", data)
        return removed

    def words(self, scope: Scope, group_id: str) -> list[str]:
        return sorted(
            {
                str(item).strip()
                for item in self._forbidden_words().get(self._word_key(scope, group_id), [])
                if str(item).strip()
            }
        )

    def summary_text(self, group_id: str) -> str:
        group_id = str(group_id or "")
        return "\n".join(
            [
                "名单与违禁词：",
                f"本群黑名单：{_format_values(self.members('group', group_id, 'black'))}",
                f"本群白名单：{_format_values(self.members('group', group_id, 'white'))}",
                f"全局黑名单：{_format_values(self.members('global', '', 'black'))}",
                f"全局白名单：{_format_values(self.members('global', '', 'white'))}",
                f"本群违禁词：{_format_values(self.words('group', group_id))}",
                f"全局违禁词：{_format_values(self.words('global', ''))}",
            ]
        )

    def match_forbidden(self, group_id: str, message: str) -> ForbiddenHit | None:
        text = (message or "").lower()
        data = self._forbidden_words()
        for word in data.get(self._word_key("global", ""), []):
            if word and word.lower() in text:
                return ForbiddenHit(word, "global")
        for word in data.get(self._word_key("group", group_id), []):
            if word and word.lower() in text:
                return ForbiddenHit(word, "group")
        return None

    def parse_words(self, text: str) -> list[str]:
        normalized = text.replace("，", ",").replace("、", ",").replace("\n", ",")
        result: list[str] = []
        seen: set[str] = set()
        for part in normalized.split(","):
            word = part.strip()
            if word and word not in seen:
                seen.add(word)
                result.append(word)
        return result

    def parse_user_ids(self, text: str) -> list[str]:
        return parse_user_ids(text)

    def _has_member(self, scope: Scope, group_id: str, list_type: ListType, user_id: str) -> bool:
        return str(user_id) in set(self._lists().get(self._list_key(scope, group_id, list_type), []))

    def _lists(self) -> dict[str, list[str]]:
        value = self.ctx.get_state("member_lists", {})
        return value if isinstance(value, dict) else {}

    def _forbidden_words(self) -> dict[str, list[str]]:
        value = self.ctx.get_state("forbidden_words", {})
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _list_key(scope: Scope, group_id: str, list_type: ListType) -> str:
        return f"{scope}:{group_id if scope == 'group' else ''}:{list_type}"

    @staticmethod
    def _word_key(scope: Scope, group_id: str) -> str:
        return f"{scope}:{group_id if scope == 'group' else ''}"


def _format_values(values: list[str]) -> str:
    return "、".join(values) if values else "无"

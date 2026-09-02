from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.member_guard import MemberGuardService


ReviewAction = Literal["approve", "reject", "manual", "ignore"]


@dataclass(frozen=True)
class ReviewDecision:
    action: ReviewAction
    reason: str = ""


@dataclass(frozen=True)
class ReviewRules:
    blacklist_enabled: bool = True
    gender_enabled: bool = False
    allowed_gender: str = "any"
    level_enabled: bool = False
    min_level: int = 0
    qage_enabled: bool = False
    min_qage: int = 0


class JoinReviewService:
    def __init__(self, ctx: PluginContext) -> None:
        self.ctx = ctx

    def enabled(self, group_id: str) -> bool:
        settings = self._settings()
        value = settings.get(str(group_id), {}).get("join_review_enabled")
        if value is None:
            return bool(self.ctx.get_config("join_review_enabled", False))
        return bool(value)

    def set_enabled(self, group_id: str, enabled: bool) -> None:
        settings = self._settings()
        group_settings = settings.setdefault(str(group_id), {})
        group_settings["join_review_enabled"] = bool(enabled)
        self.ctx.set_state("settings", settings)

    def notice_enabled(self, group_id: str, key: str, default: bool = True) -> bool:
        settings = self._settings()
        value = settings.get(str(group_id), {}).get(key)
        if value is None:
            return bool(self.ctx.get_config(key, default))
        return bool(value)

    def set_notice_enabled(self, group_id: str, key: str, enabled: bool) -> None:
        settings = self._settings()
        group_settings = settings.setdefault(str(group_id), {})
        group_settings[key] = bool(enabled)
        self.ctx.set_state("settings", settings)

    def reject_reason(self, group_id: str) -> str:
        settings = self._settings()
        value = settings.get(str(group_id), {}).get("review_reject_reason")
        if value is None:
            return str(self.ctx.get_config("review_reject_reason", "本群已开启入群审核，请联系管理员。"))
        return str(value)

    def set_reject_reason(self, group_id: str, reason: str) -> None:
        settings = self._settings()
        group_settings = settings.setdefault(str(group_id), {})
        group_settings["review_reject_reason"] = reason.strip() or "本群已开启入群审核，请联系管理员。"
        self.ctx.set_state("settings", settings)

    def rules(self, group_id: str) -> ReviewRules:
        group_settings = self._settings().get(str(group_id), {})
        return ReviewRules(
            blacklist_enabled=self._bool_setting(group_settings, "review_blacklist_enabled", True),
            gender_enabled=self._bool_setting(group_settings, "review_gender_enabled", False),
            allowed_gender=self._gender_setting(group_settings.get("review_allowed_gender", "any")),
            level_enabled=self._bool_setting(group_settings, "review_level_enabled", False),
            min_level=self._int_setting(group_settings, "review_min_level", 0),
            qage_enabled=self._bool_setting(group_settings, "review_qage_enabled", False),
            min_qage=self._int_setting(group_settings, "review_min_qage", 0),
        )

    def set_rules(self, group_id: str, rules: ReviewRules) -> None:
        settings = self._settings()
        group_settings = settings.setdefault(str(group_id), {})
        group_settings.update(
            {
                "review_blacklist_enabled": bool(rules.blacklist_enabled),
                "review_gender_enabled": bool(rules.gender_enabled),
                "review_allowed_gender": self._gender_setting(rules.allowed_gender),
                "review_level_enabled": bool(rules.level_enabled),
                "review_min_level": max(0, int(rules.min_level)),
                "review_qage_enabled": bool(rules.qage_enabled),
                "review_min_qage": max(0, int(rules.min_qage)),
            }
        )
        self.ctx.set_state("settings", settings)

    def reset_group(self, group_id: str) -> bool:
        settings = self._settings()
        removed = settings.pop(str(group_id), None) is not None
        self.ctx.set_state("settings", settings)
        return removed

    def recent_records(self, group_id: str, limit: int = 80, query: str = "") -> list[dict[str, Any]]:
        group_key = str(group_id or "").strip()
        needle = str(query or "").strip().lower()
        rows = [
            item
            for item in self.ctx.recent_state_records("join_review_records", limit=max(1, int(limit or 1)))
            if not group_key or str(item.get("group_id") or "") == group_key
        ]
        if not needle:
            return rows
        return [
            item
            for item in rows
            if needle in " ".join(str(value or "").lower() for value in item.values())
        ]

    def clear_records(self, group_id: str = "") -> int:
        group_key = str(group_id or "").strip()
        raw_records = self.ctx.get_state_list("join_review_records", [])
        if group_key:
            kept = [record for record in raw_records if not isinstance(record, dict) or str(record.get("group_id") or "") != group_key]
        else:
            kept = []
        removed = len(raw_records) - len(kept)
        self.ctx.set_state("join_review_records", kept)
        return removed

    def export_records(self, group_id: str = "", query: str = "", limit: int = 200) -> str:
        lines = ["时间|群号|动作|QQ|flag|验证信息|原因"]
        for item in self.recent_records(group_id, limit=limit, query=query):
            lines.append(
                "|".join(
                    _safe_export_cell(item.get(key, ""))
                    for key in ("time", "group_id", "action", "user_id", "flag", "comment", "reason")
                )
            )
        return "\n".join(lines)

    def decide(self, group_id: str, user_id: str, raw: dict[str, Any]) -> ReviewDecision:
        if not self.enabled(group_id):
            return ReviewDecision("ignore", "入群审核未开启")

        rules = self.rules(group_id)
        if rules.blacklist_enabled:
            guard = MemberGuardService(self.ctx.for_plugin("member_guard", config=self.ctx.config))
            decision = guard.decide(group_id, user_id)
            if decision.action == "allow":
                return ReviewDecision("approve", decision.reason or "命中白名单")
            if decision.action == "deny":
                return ReviewDecision("reject", self.reject_reason(group_id) or decision.reason)

        profile_decision = self._decide_profile_rules(group_id, raw, rules)
        if profile_decision is not None:
            return profile_decision

        comment = str(raw.get("comment") or "")
        for keyword in self.auto_approve_keywords(group_id):
            if keyword and keyword in comment:
                return ReviewDecision("approve", f"验证信息命中关键词：{keyword}")
        return ReviewDecision("manual", "等待管理员人工审核")

    def auto_approve_keywords(self, group_id: str) -> list[str]:
        settings = self._settings()
        value = settings.get(str(group_id), {}).get("review_auto_approve_keywords")
        if value is None:
            value = self.ctx.get_config("review_auto_approve_keywords", [])
        if isinstance(value, str):
            return [item.strip() for item in value.replace("，", ",").split(",") if item.strip()]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []

    def set_auto_approve_keywords(self, group_id: str, words: list[str]) -> None:
        settings = self._settings()
        group_settings = settings.setdefault(str(group_id), {})
        group_settings["review_auto_approve_keywords"] = [word for word in words if word]
        self.ctx.set_state("settings", settings)

    def summary(self, group_id: str) -> str:
        rules = self.rules(group_id)
        return "\n".join(
            [
                "入群审核配置：",
                f"- 入群审核：{'开启' if self.enabled(group_id) else '关闭'}",
                f"- 入群通知：{'开启' if self.notice_enabled(group_id, 'join_notice_enabled', True) else '关闭'}",
                f"- 退群通知：{'开启' if self.notice_enabled(group_id, 'leave_notice_enabled', True) else '关闭'}",
                f"- 自动同意关键词：{', '.join(self.auto_approve_keywords(group_id)) or '无'}",
                f"- 黑白名单审核：{'开启' if rules.blacklist_enabled else '关闭'}",
                f"- 性别审核：{'开启' if rules.gender_enabled else '关闭'} / {self._gender_label(rules.allowed_gender)}",
                f"- 等级审核：{'开启' if rules.level_enabled else '关闭'} / 最低 {rules.min_level}",
                f"- Q龄审核：{'开启' if rules.qage_enabled else '关闭'} / 最低 {rules.min_qage}",
                f"- 拒绝理由：{self.reject_reason(group_id)}",
            ]
        )

    def _decide_profile_rules(
        self,
        group_id: str,
        raw: dict[str, Any],
        rules: ReviewRules,
    ) -> ReviewDecision | None:
        if rules.gender_enabled and rules.allowed_gender != "any":
            gender = self._normalize_gender(self._raw_value(raw, ("sex", "gender")))
            if not gender:
                return ReviewDecision("manual", "等待管理员审核：入群事件未提供性别字段")
            if gender != rules.allowed_gender:
                return ReviewDecision("reject", self.reject_reason(group_id))

        if rules.level_enabled and rules.min_level > 0:
            level = self._raw_int(raw, ("level", "qq_level", "member_level"))
            if level is None:
                return ReviewDecision("manual", "等待管理员审核：入群事件未提供等级字段")
            if level < rules.min_level:
                return ReviewDecision("reject", self.reject_reason(group_id))

        if rules.qage_enabled and rules.min_qage > 0:
            qage = self._raw_int(raw, ("qage", "qq_age", "q_age", "account_age"))
            if qage is None:
                return ReviewDecision("manual", "等待管理员审核：入群事件未提供Q龄字段")
            if qage < rules.min_qage:
                return ReviewDecision("reject", self.reject_reason(group_id))

        return None

    def _settings(self) -> dict[str, dict[str, Any]]:
        value = self.ctx.get_state("settings", {})
        return value if isinstance(value, dict) else {}

    def _bool_setting(self, group_settings: dict[str, Any], key: str, default: bool) -> bool:
        value = group_settings.get(key)
        if value is None:
            value = self.ctx.get_config(key, default)
        return bool(value)

    def _int_setting(self, group_settings: dict[str, Any], key: str, default: int) -> int:
        value = group_settings.get(key)
        if value is None:
            value = self.ctx.get_config(key, default)
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _gender_setting(value: Any) -> str:
        normalized = str(value or "any").strip().lower()
        if normalized in {"male", "m", "男"}:
            return "male"
        if normalized in {"female", "f", "女"}:
            return "female"
        return "any"

    @staticmethod
    def _gender_label(value: str) -> str:
        return {"male": "男", "female": "女"}.get(value, "不限制")

    @classmethod
    def _normalize_gender(cls, value: Any) -> str:
        return cls._gender_setting(value) if value else ""

    @classmethod
    def _raw_int(cls, raw: dict[str, Any], keys: tuple[str, ...]) -> int | None:
        value = cls._raw_value(raw, keys)
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _raw_value(raw: dict[str, Any], keys: tuple[str, ...]) -> Any:
        for key in keys:
            if key in raw:
                return raw.get(key)
        for parent_key in ("user_info", "requester", "sender"):
            parent = raw.get(parent_key)
            if isinstance(parent, dict):
                for key in keys:
                    if key in parent:
                        return parent.get(key)
        return None


def parse_words(text: str) -> list[str]:
    normalized = text.replace("，", ",").replace("、", ",").replace("\n", ",")
    result: list[str] = []
    seen: set[str] = set()
    for item in normalized.split(","):
        word = item.strip()
        if word and word not in seen:
            seen.add(word)
            result.append(word)
    return result


def _safe_export_cell(value: Any) -> str:
    return str(value or "").replace("\r", " ").replace("\n", " ").replace("|", "/").strip()

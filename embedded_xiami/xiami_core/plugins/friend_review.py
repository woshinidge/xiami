from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from xiami_core.plugins.context import PluginContext

FriendReviewAction = Literal["approve", "reject", "manual", "ignore"]


@dataclass(frozen=True)
class FriendReviewDecision:
    action: FriendReviewAction
    reason: str = ""
    remark: str = ""


class FriendReviewService:
    def __init__(self, ctx: PluginContext) -> None:
        self.ctx = ctx

    def enabled(self) -> bool:
        return bool(self.ctx.get_config("friend_review_enabled", False))

    def set_enabled(self, enabled: bool) -> None:
        self.ctx.set_state("friend_review_enabled", bool(enabled))

    def effective_enabled(self) -> bool:
        value = self.ctx.get_state("friend_review_enabled", None)
        if value is None:
            return self.enabled()
        return bool(value)

    def mode(self) -> str:
        value = str(self.ctx.get_state("friend_review_mode", "") or "").strip().lower()
        if value:
            return _normalize_mode(value)
        return _normalize_mode(str(self.ctx.get_config("friend_review_mode", "manual")))

    def set_mode(self, mode: str) -> str:
        normalized = _normalize_mode(mode)
        self.ctx.set_state("friend_review_mode", normalized)
        return normalized

    def approve_keywords(self) -> list[str]:
        return self._words("friend_auto_approve_keywords")

    def reject_keywords(self) -> list[str]:
        return self._words("friend_auto_reject_keywords")

    def set_approve_keywords(self, words: list[str]) -> None:
        self.ctx.set_state("friend_auto_approve_keywords", [word for word in words if word])

    def set_reject_keywords(self, words: list[str]) -> None:
        self.ctx.set_state("friend_auto_reject_keywords", [word for word in words if word])

    def notify_users(self) -> list[str]:
        return self._words("friend_notify_users")

    def set_notify_users(self, users: list[str]) -> None:
        self.ctx.set_state("friend_notify_users", [str(user) for user in users if str(user)])

    def approve_users(self) -> list[str]:
        return self._words("friend_auto_approve_users")

    def reject_users(self) -> list[str]:
        return self._words("friend_auto_reject_users")

    def set_approve_users(self, users: list[str]) -> None:
        self.ctx.set_state("friend_auto_approve_users", [str(user) for user in users if str(user)])

    def set_reject_users(self, users: list[str]) -> None:
        self.ctx.set_state("friend_auto_reject_users", [str(user) for user in users if str(user)])

    def reset(self) -> None:
        for key in (
            "friend_review_enabled",
            "friend_review_mode",
            "friend_auto_approve_keywords",
            "friend_auto_reject_keywords",
            "friend_notify_users",
            "friend_auto_approve_users",
            "friend_auto_reject_users",
            "friend_reject_reason",
            "friend_approve_remark",
        ):
            self.ctx.delete_state(key)

    def reject_reason(self) -> str:
        state_value = self.ctx.get_state("friend_reject_reason", None)
        if state_value is not None:
            return str(state_value or "").strip() or "不接受陌生好友申请。"
        return str(self.ctx.get_config("friend_reject_reason", "不接受陌生好友申请。"))

    def set_reject_reason(self, reason: str) -> None:
        self.ctx.set_state("friend_reject_reason", str(reason or "").strip() or "不接受陌生好友申请。")

    def approve_remark(self) -> str:
        state_value = self.ctx.get_state("friend_approve_remark", None)
        if state_value is not None:
            return str(state_value or "").strip()
        return str(self.ctx.get_config("friend_approve_remark", ""))

    def set_approve_remark(self, remark: str) -> None:
        self.ctx.set_state("friend_approve_remark", str(remark or "").strip())

    def recent_records(self, limit: int = 50, query: str = "") -> list[dict[str, Any]]:
        records = self.ctx.recent_state_records("friend_review_records", limit=max(1, int(limit or 1)))
        needle = str(query or "").strip().lower()
        if not needle:
            return records
        return [
            item
            for item in records
            if needle in " ".join(str(value or "").lower() for value in item.values())
        ]

    def clear_records(self) -> None:
        self.ctx.set_state("friend_review_records", [])

    def export_records(self, query: str = "", limit: int = 200) -> str:
        lines = ["时间|动作|QQ|flag|验证信息|原因/备注"]
        for item in self.recent_records(limit=limit, query=query):
            lines.append(
                "|".join(
                    _safe_export_cell(item.get(key, ""))
                    for key in ("time", "action", "user_id", "flag", "comment", "reason")
                )
            )
        return "\n".join(lines)

    def decide(self, user_id: str, comment: str) -> FriendReviewDecision:
        if not self.effective_enabled():
            return FriendReviewDecision("ignore", "好友审核未开启")

        user_id = str(user_id)
        comment = str(comment or "")

        if user_id in self._words("friend_auto_reject_users"):
            return FriendReviewDecision("reject", "命中拒绝名单")
        if user_id in self._words("friend_auto_approve_users"):
            return FriendReviewDecision("approve", "命中同意名单", self.approve_remark())

        for word in self.reject_keywords():
            if word and word in comment:
                return FriendReviewDecision("reject", f"命中拒绝词：{word}")
        for word in self.approve_keywords():
            if word and word in comment:
                return FriendReviewDecision("approve", f"命中同意词：{word}", self.approve_remark())

        mode = self.mode()
        if mode == "approve":
            return FriendReviewDecision("approve", "默认同意", self.approve_remark())
        if mode == "reject":
            return FriendReviewDecision("reject", self.reject_reason())
        return FriendReviewDecision("manual", "等待人工审核")

    def summary(self) -> str:
        return "\n".join(
            [
                "好友审核配置：",
                f"- 好友审核：{'开启' if self.effective_enabled() else '关闭'}",
                f"- 审核模式：{_mode_text(self.mode())}",
                f"- 自动同意词：{', '.join(self.approve_keywords()) or '无'}",
                f"- 自动拒绝词：{', '.join(self.reject_keywords()) or '无'}",
                f"- 自动同意QQ：{', '.join(self.approve_users()) or '无'}",
                f"- 自动拒绝QQ：{', '.join(self.reject_users()) or '无'}",
                f"- 通知账号：{', '.join(self.notify_users()) or '无'}",
                f"- 拒绝理由：{self.reject_reason()}",
            ]
        )

    def _words(self, key: str) -> list[str]:
        stored = self.ctx.get_state(key, None)
        value: Any = stored if stored is not None else self.ctx.get_config(key, [])
        if isinstance(value, str):
            return parse_words(value)
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []

    def _config_words(self, key: str) -> list[str]:
        value: Any = self.ctx.get_config(key, [])
        if isinstance(value, str):
            return parse_words(value)
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []


def parse_words(text: str) -> list[str]:
    normalized = str(text or "").replace("，", ",").replace("、", ",")
    return [item.strip() for item in normalized.split(",") if item.strip()]


def parse_mode(text: str) -> str:
    return _normalize_mode(text)


def _normalize_mode(text: str) -> str:
    value = str(text or "").strip().lower()
    if value in {"approve", "同意", "自动同意", "通过", "放行"}:
        return "approve"
    if value in {"reject", "拒绝", "自动拒绝", "驳回"}:
        return "reject"
    return "manual"


def _mode_text(mode: str) -> str:
    if mode == "approve":
        return "自动同意"
    if mode == "reject":
        return "自动拒绝"
    return "人工审核"


def _safe_export_cell(value: Any) -> str:
    return str(value or "").replace("\r", " ").replace("\n", " ").replace("|", "/").strip()

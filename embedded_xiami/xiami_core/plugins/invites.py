from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
import time
from typing import Any

from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.points import PointsService, state_transaction


@dataclass(frozen=True)
class InviteResult:
    rewarded: bool
    points: int
    total: int
    message: str


@dataclass(frozen=True)
class InviteLeaveResult:
    matched: bool
    deducted: bool
    points: int
    total: int
    message: str


class InviteService:
    def __init__(self, ctx: PluginContext) -> None:
        self.ctx = ctx

    def enabled(self, group_id: str) -> bool:
        settings = self._settings()
        value = settings.get(str(group_id), {}).get("invite_points_enabled")
        if value is None:
            return bool(self.ctx.get_config("invite_points_enabled", True))
        return bool(value)

    def set_enabled(self, group_id: str, enabled: bool) -> None:
        settings = self._settings()
        group_settings = settings.setdefault(str(group_id), {})
        group_settings["invite_points_enabled"] = bool(enabled)
        self.ctx.set_state("settings", settings)

    def reward_points(self, group_id: str) -> int:
        return self._group_number(
            group_id,
            "invite_reward_points",
            int(self.ctx.get_config("invite_reward_points", 1) or 1),
        )

    def set_reward_points(self, group_id: str, points: int) -> None:
        settings = self._settings()
        group_settings = settings.setdefault(str(group_id), {})
        group_settings["invite_reward_points"] = max(1, int(points or 1))
        self.ctx.set_state("settings", settings)

    def retention_days(self, group_id: str) -> int:
        return self._group_nonnegative_number(
            group_id,
            "invite_retention_days",
            int(self.ctx.get_config("invite_retention_days", 0) or 0),
        )

    def set_retention_days(self, group_id: str, days: int) -> None:
        settings = self._settings()
        group_settings = settings.setdefault(str(group_id), {})
        group_settings["invite_retention_days"] = max(0, int(days or 0))
        self.ctx.set_state("settings", settings)

    def record_join(
        self,
        group_id: str,
        user_id: str,
        inviter_id: str,
        *,
        now_ts: float | int | None = None,
    ) -> InviteResult:
        if not self.enabled(group_id):
            return InviteResult(False, 0, 0, "")
        return self.add_record(group_id, user_id, inviter_id, award_points=True, now_ts=now_ts)

    def add_record(
        self,
        group_id: str,
        user_id: str,
        inviter_id: str,
        points: int | None = None,
        *,
        award_points: bool = True,
        now_ts: float | int | None = None,
    ) -> InviteResult:
        group_id = str(group_id or "").strip()
        user_id = str(user_id or "").strip()
        inviter_id = str(inviter_id or "").strip()
        if not group_id or not user_id:
            return InviteResult(False, 0, 0, "")
        if not inviter_id or inviter_id == user_id:
            return InviteResult(False, 0, 0, "")
        with state_transaction(self.ctx):
            key = f"{group_id}:{user_id}"
            records = self._records()
            if key in records:
                return InviteResult(False, 0, 0, "")
            points_value = max(1, int(points if points is not None else self.reward_points(group_id)))
            joined_at = max(0, int(time.time() if now_ts is None else now_ts))
            records[key] = {
                "group_id": str(group_id),
                "user_id": str(user_id),
                "inviter_id": str(inviter_id),
                "points": points_value,
                "joined_at": joined_at,
                "required_days": self.retention_days(group_id),
                "left_at": 0,
                "revoked": False,
                "revoked_points": 0,
            }
            self.ctx.set_state("invite_records", records)
            points_service = PointsService(self.ctx)
            total = points_service.add_points(group_id, inviter_id, points_value) if award_points else points_service.points(group_id, inviter_id)
            self._increment_rank(group_id, inviter_id, points_value)
        message = f"成员 {user_id} 入群，邀请人 {inviter_id} 获得 {points_value} 积分，当前积分：{total}。"
        return InviteResult(True, points_value, total, message)

    def record_leave(
        self,
        group_id: str,
        user_id: str,
        *,
        now_ts: float | int | None = None,
        sub_type: str = "",
    ) -> InviteLeaveResult:
        group_key = str(group_id or "").strip()
        user_key = str(user_id or "").strip()
        if not group_key or not user_key:
            return InviteLeaveResult(False, False, 0, 0, "")
        with state_transaction(self.ctx):
            records = self._records()
            key = f"{group_key}:{user_key}"
            item = records.get(key)
            if not isinstance(item, dict):
                return InviteLeaveResult(False, False, 0, 0, "")
            inviter_id = str(item.get("inviter_id") or "").strip()
            points_value = max(0, int(item.get("points") or 0))
            points_service = PointsService(self.ctx)
            current_total = points_service.points(group_key, inviter_id) if inviter_id else 0
            if bool(item.get("revoked")):
                return InviteLeaveResult(True, False, int(item.get("revoked_points") or 0), current_total, "")

            left_at = max(0, int(time.time() if now_ts is None else now_ts))
            item["left_at"] = left_at
            item["leave_sub_type"] = str(sub_type or "").strip()
            joined_at = max(0, int(item.get("joined_at") or 0))
            required_days = max(0, int(item.get("required_days") or 0))
            item["retention_met"] = bool(
                required_days <= 0
                or joined_at <= 0
                or left_at - joined_at >= required_days * 86400
            )
            if item["retention_met"]:
                records[key] = item
                self.ctx.set_state("invite_records", records)
                return InviteLeaveResult(True, False, 0, current_total, "")

            total = points_service.add_points(group_key, inviter_id, -points_value) if inviter_id and points_value else current_total
            item["revoked"] = True
            item["revoked_points"] = points_value
            records[key] = item
            self.ctx.set_state("invite_records", records)
            self._decrement_rank(group_key, inviter_id, points_value)
            message = (
                f"成员 {user_key} 入群未满 {required_days} 天即退群，"
                f"已从邀请人 {inviter_id} 扣回 {points_value} 积分，当前积分：{total}。"
            )
            return InviteLeaveResult(True, True, points_value, total, message)

    def import_records(self, group_id: str, text: str, *, award_points: bool = True) -> int:
        count = 0
        for line in str(text or "").splitlines():
            user_id, inviter_id, points = self.parse_record_line(line)
            if user_id and inviter_id:
                result = self.add_record(group_id, user_id, inviter_id, points, award_points=award_points)
                if result.rewarded:
                    count += 1
        return count

    def export_records(self, group_id: str, query: str = "") -> str:
        rows = self.records(group_id, query=query)
        if not rows:
            return "暂无邀请记录。"
        return "\n".join(f"{row['user_id']}={row['inviter_id']},{row['points']}" for row in rows)

    def parse_record_line(self, text: str) -> tuple[str, str, int | None]:
        raw = str(text or "").strip()
        if not raw:
            return "", "", None
        raw = raw.replace("，", ",").replace("：", ":").replace("＝", "=")
        numbers = re.findall(r"\d{5,}", raw)
        if len(numbers) < 2:
            return "", "", None
        points: int | None = None
        # 从第二个 QQ 之后读取第一个普通整数作为奖励积分；没有就用本群默认奖励。
        tail = raw.split(numbers[1], 1)[1] if numbers[1] in raw else ""
        point_match = re.search(r"(?<!\d)(-?\d+)(?!\d)", tail)
        if point_match:
            try:
                points = max(1, int(point_match.group(1)))
            except (TypeError, ValueError):
                points = None
        return numbers[0], numbers[1], points

    def rank_text(self, group_id: str, limit: int = 10) -> str:
        rows = self.ranking(group_id, limit)
        if not rows:
            return "暂无邀请记录。"
        lines = ["邀请排行："]
        for index, row in enumerate(rows, start=1):
            lines.append(f"{index}. {row['inviter_id']} 邀请 {row['invite_count']} 人，奖励 {row['points']} 积分")
        return "\n".join(lines)

    def ranking(self, group_id: str, limit: int = 10) -> list[dict[str, Any]]:
        ranks = self._ranks().get(str(group_id), {})
        rows = [
            {"inviter_id": str(inviter_id), "invite_count": int(data.get("invite_count", 0)), "points": int(data.get("points", 0))}
            for inviter_id, data in ranks.items()
            if isinstance(data, dict)
        ]
        sorted_rows = sorted(rows, key=lambda row: (row["invite_count"], row["points"]), reverse=True)
        return sorted_rows[:limit] if limit and limit > 0 else sorted_rows

    def user_rank(self, group_id: str, inviter_id: str) -> dict[str, Any]:
        inviter_key = str(inviter_id or "").strip()
        for index, row in enumerate(self.ranking(group_id, 0), start=1):
            if str(row.get("inviter_id") or "") == inviter_key:
                result = dict(row)
                result["rank"] = index
                return result
        return {"inviter_id": inviter_key, "invite_count": 0, "points": 0, "rank": 0}

    def records(
        self,
        group_id: str,
        *,
        inviter_id: str = "",
        user_id: str = "",
        query: str = "",
    ) -> list[dict[str, Any]]:
        group_key = str(group_id or "").strip()
        inviter_key = str(inviter_id or "").strip()
        user_key = str(user_id or "").strip()
        query_key = str(query or "").strip()
        rows: list[dict[str, Any]] = []
        for key, item in self._records().items():
            if not isinstance(item, dict):
                continue
            row_group = str(item.get("group_id") or "").strip()
            row_user = str(item.get("user_id") or "").strip()
            row_inviter = str(item.get("inviter_id") or "").strip()
            if group_key and row_group != group_key:
                continue
            if inviter_key and row_inviter != inviter_key:
                continue
            if user_key and row_user != user_key:
                continue
            if query_key and query_key not in row_user and query_key not in row_inviter and query_key not in str(key):
                continue
            rows.append(
                {
                    "key": str(key),
                    "group_id": row_group,
                    "user_id": row_user,
                    "inviter_id": row_inviter,
                    "points": int(item.get("points") or 0),
                    "joined_at": max(0, int(item.get("joined_at") or 0)),
                    "joined_at_text": self._format_timestamp(item.get("joined_at")),
                    "required_days": max(0, int(item.get("required_days") or 0)),
                    "left_at": max(0, int(item.get("left_at") or 0)),
                    "left_at_text": self._format_timestamp(item.get("left_at")),
                    "revoked": bool(item.get("revoked")),
                    "revoked_points": max(0, int(item.get("revoked_points") or 0)),
                    "retention_met": bool(item.get("retention_met")),
                    "status": self._record_status(item),
                }
            )
        return sorted(rows, key=lambda row: (row.get("group_id", ""), row.get("key", "")))

    def records_text(self, group_id: str, query: str = "", limit: int = 10) -> str:
        rows = self.records(group_id, query=query)
        if not rows:
            return "暂无邀请记录。"
        lines = ["邀请记录："]
        for row in rows[:limit]:
            lines.append(
                f"{row['user_id']} 由 {row['inviter_id']} 邀请，奖励 {row['points']} 积分，{row['status']}"
            )
        if len(rows) > limit:
            lines.append(f"还有 {len(rows) - limit} 条记录，请到后台查看。")
        return "\n".join(lines)

    def rebuild_ranking(self, group_id: str) -> int:
        group_key = str(group_id or "").strip()
        if not group_key:
            return 0
        ranks = self._ranks()
        new_group: dict[str, dict[str, int]] = {}
        count = 0
        for row in self.records(group_key):
            if bool(row.get("revoked")):
                continue
            inviter_id = str(row.get("inviter_id") or "").strip()
            if not inviter_id:
                continue
            target = new_group.setdefault(inviter_id, {"invite_count": 0, "points": 0})
            target["invite_count"] = int(target.get("invite_count", 0)) + 1
            target["points"] = int(target.get("points", 0)) + int(row.get("points") or 0)
            count += 1
        if new_group:
            ranks[group_key] = new_group
        else:
            ranks.pop(group_key, None)
        self.ctx.set_state("invite_ranks", ranks)
        return count

    def delete_record(self, group_id: str, user_id_or_key: str) -> dict[str, Any] | None:
        group_key = str(group_id or "").strip()
        value = str(user_id_or_key or "").strip()
        if not group_key or not value:
            return None
        records = self._records()
        key = value if value in records else f"{group_key}:{value}"
        item = records.get(key)
        if not isinstance(item, dict):
            return None
        if str(item.get("group_id") or "") != group_key:
            return None
        removed = dict(item)
        records.pop(key, None)
        self.ctx.set_state("invite_records", records)
        if not bool(removed.get("revoked")):
            self._decrement_rank(group_key, str(removed.get("inviter_id") or ""), int(removed.get("points") or 0))
        removed["key"] = key
        return removed

    def clear_group(self, group_id: str) -> int:
        group_key = str(group_id or "").strip()
        if not group_key:
            return 0
        records = self._records()
        before = len(records)
        records = {
            str(key): value
            for key, value in records.items()
            if not (
                (isinstance(value, dict) and str(value.get("group_id") or "") == group_key)
                or str(key).startswith(f"{group_key}:")
            )
        }
        self.ctx.set_state("invite_records", records)
        ranks = self._ranks()
        ranks.pop(group_key, None)
        self.ctx.set_state("invite_ranks", ranks)
        return before - len(records)

    def _increment_rank(self, group_id: str, inviter_id: str, points: int) -> None:
        ranks = self._ranks()
        group = ranks.setdefault(str(group_id), {})
        row = group.setdefault(str(inviter_id), {"invite_count": 0, "points": 0})
        row["invite_count"] = int(row.get("invite_count", 0)) + 1
        row["points"] = int(row.get("points", 0)) + int(points)
        self.ctx.set_state("invite_ranks", ranks)

    def _decrement_rank(self, group_id: str, inviter_id: str, points: int) -> None:
        if not inviter_id:
            return
        ranks = self._ranks()
        group = ranks.get(str(group_id), {})
        row = group.get(str(inviter_id), {}) if isinstance(group, dict) else {}
        if not isinstance(row, dict):
            return
        row["invite_count"] = max(0, int(row.get("invite_count", 0)) - 1)
        row["points"] = max(0, int(row.get("points", 0)) - int(points or 0))
        if row["invite_count"] <= 0 and row["points"] <= 0:
            group.pop(str(inviter_id), None)
        else:
            group[str(inviter_id)] = row
        if group:
            ranks[str(group_id)] = group
        else:
            ranks.pop(str(group_id), None)
        self.ctx.set_state("invite_ranks", ranks)

    def _settings(self) -> dict[str, dict[str, Any]]:
        value = self.ctx.get_state("settings", {})
        return value if isinstance(value, dict) else {}

    def _group_number(self, group_id: str, key: str, default: int) -> int:
        try:
            value = self._settings().get(str(group_id), {}).get(key, default)
            return max(1, int(value))
        except (TypeError, ValueError):
            return max(1, int(default))

    def _group_nonnegative_number(self, group_id: str, key: str, default: int) -> int:
        try:
            value = self._settings().get(str(group_id), {}).get(key, default)
            return max(0, int(value))
        except (TypeError, ValueError):
            return max(0, int(default))

    @staticmethod
    def _format_timestamp(value: object) -> str:
        try:
            timestamp = int(value or 0)
        except (TypeError, ValueError):
            return ""
        if timestamp <= 0:
            return ""
        try:
            return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")
        except (OSError, OverflowError, ValueError):
            return ""

    @staticmethod
    def _record_status(item: dict[str, Any]) -> str:
        if bool(item.get("revoked")):
            return "提前退群，已扣回"
        joined_at = max(0, int(item.get("joined_at") or 0))
        left_at = max(0, int(item.get("left_at") or 0))
        required_days = max(0, int(item.get("required_days") or 0))
        if joined_at <= 0:
            return "历史记录，不追扣"
        if left_at > 0 and bool(item.get("retention_met")):
            return "已满足保留期"
        if left_at > 0:
            return "已退群"
        if required_days > 0:
            return f"保留期 {required_days} 天"
        return "正常"

    def _records(self) -> dict[str, dict[str, Any]]:
        value = self.ctx.get_state("invite_records", {})
        return value if isinstance(value, dict) else {}

    def _ranks(self) -> dict[str, dict[str, dict[str, int]]]:
        value = self.ctx.get_state("invite_ranks", {})
        return value if isinstance(value, dict) else {}

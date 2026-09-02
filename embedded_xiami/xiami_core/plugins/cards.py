from __future__ import annotations

from datetime import datetime
import secrets
import string
from typing import Any

from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.points import state_transaction


ALPHABET = string.ascii_uppercase + string.digits


class CardService:
    def __init__(self, ctx: PluginContext) -> None:
        self.ctx = ctx

    def generate(
        self,
        count: int,
        points: int | None = None,
        note: str = "",
        owner_group_id: str = "",
    ) -> list[str]:
        """生成卡密。卡密不带面额，兑换所需积分由本群「兑换积分」决定。

        points 参数保留但忽略：工具箱后台按位置传 (count, points, note)，
        去掉这个参数会让「积分」值错位写进备注、备注错位写进群归属。
        owner_group_id 标记卡密归属群：不同群通常是不同区服，
        A 群生成的库存不应被 B 群玩家兑走。
        """
        _ = points
        count = max(1, min(int(count), 1000))
        with state_transaction(self.ctx):
            cards = self._cards()
            codes: list[str] = []
            now = _now_text()
            owner = str(owner_group_id or "").strip()
            for _ in range(count):
                code = self._new_code(cards)
                entry = {"note": note, "used": False, "created_at": now}
                if owner:
                    entry["owner_group_id"] = owner
                cards[code] = entry
                codes.append(code)
            self.ctx.set_state("cards", cards)
            return codes

    def add_many(
        self,
        codes_text: str,
        points: int | None = None,
        note: str = "",
        owner_group_id: str = "",
    ) -> int:
        """导入外部卡密。points 保留但忽略，理由同 generate()。"""
        _ = points
        with state_transaction(self.ctx):
            cards = self._cards()
            count = 0
            now = _now_text()
            owner = str(owner_group_id or "").strip()
            for code in self.parse_codes(codes_text):
                entry = {"note": note, "used": False, "created_at": now}
                if owner:
                    entry["owner_group_id"] = owner
                cards[code] = entry
                count += 1
            self.ctx.set_state("cards", cards)
            return count

    def clear(self, status: str = "all", group_id: str = "") -> int:
        """清理卡密。传 group_id 时只清本群的（含无归属的公共卡密）。"""
        status = str(status or "all").strip().lower()
        if status not in {"all", "used", "unused"}:
            raise ValueError("status must be all, used, or unused")
        with state_transaction(self.ctx):
            cards = self._cards()
            keep_consumed = status == "unused"

            def should_remove(raw: object) -> bool:
                if not isinstance(raw, dict):
                    return False
                if group_id and not self.belongs_to_group(raw, group_id):
                    return False
                if status == "all":
                    return True
                return self._is_consumed(raw) != keep_consumed

            kept = {code: raw for code, raw in cards.items() if not should_remove(raw)}
            removed = len(cards) - len(kept)
            self.ctx.set_state("cards", kept)
            return removed

    def delete_many(self, codes_text: str, group_id: str = "") -> int:
        codes = self.parse_codes(codes_text)
        if not codes:
            return 0
        with state_transaction(self.ctx):
            cards = self._cards()
            removed = 0
            for code in codes:
                raw = cards.get(code)
                if not isinstance(raw, dict):
                    continue
                if group_id and not self.belongs_to_group(raw, group_id):
                    continue
                cards.pop(code, None)
                removed += 1
            if removed:
                self.ctx.set_state("cards", cards)
            return removed

    def update_many(
        self,
        codes_text: str,
        points: int | None = None,
        note: str | None = None,
        group_id: str = "",
    ) -> int:
        """改备注。

        points 参数保留但忽略：卡密已不带面额，兑换所需积分按群统一设置。
        工具箱后台的「修改卡密」按位置传 (codes, points, note)，
        去掉这个参数会让后台按钮直接报 TypeError。
        """
        _ = points
        codes = self.parse_codes(codes_text)
        if not codes:
            return 0
        with state_transaction(self.ctx):
            cards = self._cards()
            changed = 0
            note_value = None if note is None else str(note)
            for code in codes:
                raw = cards.get(code)
                if not isinstance(raw, dict):
                    continue
                if group_id and not self.belongs_to_group(raw, group_id):
                    continue
                if note_value is not None:
                    raw["note"] = note_value
                cards[code] = raw
                changed += 1
            if changed:
                self.ctx.set_state("cards", cards)
            return changed

    def reset_many(self, codes_text: str, group_id: str = "") -> int:
        codes = self.parse_codes(codes_text)
        if not codes:
            return 0
        with state_transaction(self.ctx):
            cards = self._cards()
            changed = 0
            for code in codes:
                raw = cards.get(code)
                if not isinstance(raw, dict):
                    continue
                if group_id and not self.belongs_to_group(raw, group_id):
                    continue
                if not self._is_consumed(raw) and not raw.get("group_id") and not raw.get("user_id"):
                    continue
                raw["used"] = False
                raw.pop("group_id", None)
                raw.pop("user_id", None)
                raw.pop("used_at", None)
                # 也清掉积分兑换的售出标记，让卡密退回可兑换库存
                for field in ("sold", "sold_group_id", "sold_user_id", "sold_at"):
                    raw.pop(field, None)
                cards[code] = raw
                changed += 1
            if changed:
                self.ctx.set_state("cards", cards)
            return changed

    def card(self, code: str, group_id: str = "") -> dict[str, Any] | None:
        code_key = self.normalize_code(code)
        raw = self._cards().get(code_key)
        if not isinstance(raw, dict):
            return None
        if group_id and not self.belongs_to_group(raw, group_id):
            return None
        item = dict(raw)
        item["code"] = code_key
        item["used"] = bool(item.get("used"))
        item["points"] = int(item.get("points") or 0)
        item["note"] = str(item.get("note") or "")
        item["group_id"] = str(item.get("group_id") or "")
        item["user_id"] = str(item.get("user_id") or "")
        item["created_at"] = str(item.get("created_at") or "")
        item["used_at"] = str(item.get("used_at") or "")
        return item

    def inventory(self, status: str = "all", query: str = "", limit: int = 20, group_id: str = "") -> list[dict[str, Any]]:
        status_key = normalize_status(status)
        keyword = self.normalize_code(query)
        requested_group_id = str(group_id or "").strip()
        rows: list[dict[str, Any]] = []
        for code, raw in sorted(self._cards().items()):
            if not isinstance(raw, dict):
                raw = {}
            if requested_group_id and not self.belongs_to_group(raw, requested_group_id):
                continue
            used = self._is_consumed(raw)
            if status_key == "used" and not used:
                continue
            if status_key == "unused" and used:
                continue
            note = str(raw.get("note") or "")
            redeemed_group_id = str(raw.get("sold_group_id") or raw.get("group_id") or "")
            user_id = str(raw.get("sold_user_id") or raw.get("user_id") or "")
            created_at = str(raw.get("created_at") or "")
            used_at = str(raw.get("sold_at") or raw.get("used_at") or "")
            haystack = " ".join([str(code).upper(), note.upper(), redeemed_group_id.upper(), user_id.upper(), created_at.upper(), used_at.upper()])
            if keyword and keyword not in haystack:
                continue
            rows.append(
                {
                    "code": str(code),
                    "note": note,
                    "used": bool(raw.get("used")),
                    "sold": bool(raw.get("sold")),
                    "group_id": redeemed_group_id,
                    "user_id": user_id,
                    "created_at": created_at,
                    "used_at": used_at,
                }
            )
            if limit > 0 and len(rows) >= limit:
                break
        return rows

    @staticmethod
    def _is_consumed(card: object) -> bool:
        """已发放：被积分兑换走（sold）或历史上换过积分（used）。"""
        if not isinstance(card, dict):
            return False
        return bool(card.get("sold")) or bool(card.get("used"))

    def counts(self, group_id: str = "") -> dict[str, int]:
        rows = [
            raw for raw in self._cards().values()
            if not group_id or self.belongs_to_group(raw, group_id)
        ]
        used = sum(1 for raw in rows if self._is_consumed(raw))
        total = len(rows)
        return {"total": total, "unused": total - used, "used": used}

    # ── 积分换卡密（玩家花积分买走一张卡密，卡密拿去游戏内使用）──────────────

    @staticmethod
    def belongs_to_group(card: object, group_id: str) -> bool:
        """卡密是否属于该群。

        没有 owner_group_id 的是历史遗留卡密，视为公共库存，所有群可用，
        以免升级后旧库存突然全部不可兑换。
        """
        if not isinstance(card, dict):
            return False
        owner = str(card.get("owner_group_id") or "").strip()
        return not owner or owner == str(group_id or "").strip()

    def _is_in_stock(self, card: object, group_id: str = "") -> bool:
        """未兑换、未售出且属于本群，才算本群可售库存。"""
        if not isinstance(card, dict):
            return False
        if bool(card.get("used")) or bool(card.get("sold")):
            return False
        if group_id and not self.belongs_to_group(card, group_id):
            return False
        return True

    def stock_count(self, group_id: str = "") -> int:
        return sum(1 for card in self._cards().values() if self._is_in_stock(card, group_id))

    def card_cost(self, group_id: str = "") -> int:
        """兑换一张卡密所需积分。按群设置，未设置则用插件默认值。"""
        default = 100
        try:
            default = max(1, int(self.ctx.get_config("card_cost", 100) or 100))
        except (TypeError, ValueError):
            default = 100
        key = str(group_id or "").strip()
        if not key:
            return default
        try:
            value = self._cost_settings().get(key, {}).get("card_cost", default)
            return max(1, int(value))
        except (TypeError, ValueError):
            return default

    def set_card_cost(self, group_id: str, cost: int) -> int:
        with state_transaction(self.ctx):
            value = max(1, int(cost))
            key = str(group_id or "").strip()
            if not key:
                self.ctx.config["card_cost"] = value
                return value
            settings = self._cost_settings()
            settings.setdefault(key, {})["card_cost"] = value
            self.ctx.set_state("card_settings", settings)
            return value

    def _cost_settings(self) -> dict[str, dict[str, Any]]:
        value = self.ctx.get_state("card_settings", {})
        return value if isinstance(value, dict) else {}

    def take_from_stock(self, group_id: str, user_id: str) -> str:
        """取一张可售卡密并标记售出。库存为空返回空串。

        标记 sold 后该卡密不再进入库存，也不能再走 redeem 换积分。
        """
        with state_transaction(self.ctx):
            cards = self._cards()
            for code in sorted(cards.keys()):
                card = cards.get(code)
                if not self._is_in_stock(card, group_id):
                    continue
                card["sold"] = True
                card["sold_group_id"] = str(group_id)
                card["sold_user_id"] = str(user_id)
                card["sold_at"] = _now_text()
                cards[code] = card
                self.ctx.set_state("cards", cards)
                return str(code)
            return ""

    def return_to_stock(self, code: str) -> bool:
        """私聊下发失败时把卡密退回库存，避免玩家扣了积分却拿不到卡密。"""
        key = self.normalize_code(code)
        with state_transaction(self.ctx):
            cards = self._cards()
            card = cards.get(key)
            if not isinstance(card, dict):
                return False
            for field in ("sold", "sold_group_id", "sold_user_id", "sold_at"):
                card.pop(field, None)
            cards[key] = card
            self.ctx.set_state("cards", cards)
            return True

    def parse_codes(self, text: str) -> list[str]:
        normalized = text.replace("，", ",").replace("、", ",").replace("\n", ",").replace(" ", ",")
        result: list[str] = []
        seen: set[str] = set()
        for part in normalized.split(","):
            code = self.normalize_code(part)
            if code and code not in seen:
                seen.add(code)
                result.append(code)
        return result

    @staticmethod
    def normalize_code(value: str) -> str:
        return str(value or "").strip().upper()

    def _cards(self) -> dict[str, dict[str, Any]]:
        with state_transaction(self.ctx):
            value = self.ctx.get_state("cards", {})
            return value if isinstance(value, dict) else {}

    def _new_code(self, cards: dict[str, dict[str, Any]]) -> str:
        while True:
            # 纯字母数字，不含横杠等特殊符号，便于游戏内输入
            code = "XM" + "".join(secrets.choice(ALPHABET) for _ in range(12))
            if code not in cards:
                return code


def normalize_status(value: str) -> str:
    text = str(value or "all").strip().lower()
    if text in {"used", "已兑换", "已使用", "使用", "兑换"}:
        return "used"
    if text in {"unused", "未兑换", "未使用", "可用", "库存"}:
        return "unused"
    return "all"


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

from __future__ import annotations

from dataclasses import dataclass
import random
import re
import time
from typing import Any

from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.points import PointsService


@dataclass(frozen=True)
class QuizResult:
    handled: bool
    message: str


@dataclass(frozen=True)
class QuizQuestion:
    question_id: str
    question: str
    answer: str
    enabled: bool = True
    category: str = ""
    note: str = ""


@dataclass(frozen=True)
class ParsedQuizQuestion:
    question: str
    answer: str
    enabled: bool = True
    category: str = ""
    note: str = ""


class QuizService:
    def __init__(self, ctx: PluginContext) -> None:
        self.ctx = ctx

    def enabled(self, group_id: str) -> bool:
        value = self._settings().get(str(group_id), {}).get("quiz_enabled")
        if value is None:
            return bool(self.ctx.get_config("quiz_enabled", True))
        return bool(value)

    def set_enabled(self, group_id: str, enabled: bool) -> None:
        self._set_group_value(group_id, "quiz_enabled", bool(enabled))

    def reward_points(self, group_id: str) -> int:
        return self._group_number(group_id, "quiz_reward_points", _positive_int(self.ctx.get_config("quiz_reward_points", 1), default=1), minimum=1)

    def set_reward_points(self, group_id: str, value: int) -> None:
        self._set_group_value(group_id, "quiz_reward_points", max(1, int(value)))

    def interval_seconds(self, group_id: str) -> int:
        return self._group_number(group_id, "quiz_interval_seconds", _non_negative_int(self.ctx.get_config("quiz_interval_seconds", 0), default=0), minimum=0)

    def set_interval_seconds(self, group_id: str, value: int) -> None:
        self._set_group_value(group_id, "quiz_interval_seconds", max(0, int(value)))

    def answer_timeout_seconds(self, group_id: str) -> int:
        return self._group_number(group_id, "quiz_answer_timeout_seconds", _non_negative_int(self.ctx.get_config("quiz_answer_timeout_seconds", 0), default=0), minimum=0)

    def set_answer_timeout_seconds(self, group_id: str, value: int) -> None:
        self._set_group_value(group_id, "quiz_answer_timeout_seconds", max(0, int(value)))

    def add_question(
        self,
        group_id: str,
        question: str,
        answer: str,
        *,
        category: str = "",
        note: str = "",
        enabled: bool = True,
    ) -> QuizQuestion | None:
        question = question.strip()
        answer = answer.strip()
        if not question or not answer:
            return None
        bank = self._bank()
        group_bank = bank.setdefault(str(group_id), [])
        question_id = str(max([int(item.get("id", 0)) for item in group_bank if str(item.get("id", "")).isdigit()] or [0]) + 1)
        group_bank.append(
            {
                "id": question_id,
                "question": question,
                "answer": answer,
                "enabled": bool(enabled),
                "category": str(category or "").strip(),
                "note": str(note or "").strip(),
            }
        )
        self.ctx.set_state("quiz_bank", bank)
        return QuizQuestion(
            question_id,
            question,
            answer,
            bool(enabled),
            str(category or "").strip(),
            str(note or "").strip(),
        )

    def import_questions(self, group_id: str, text: str) -> int:
        count = 0
        for line in (text or "").splitlines():
            item = self.parse_question_entry(line)
            if item and self.add_question(
                group_id,
                item.question,
                item.answer,
                category=item.category,
                note=item.note,
                enabled=item.enabled,
            ):
                count += 1
        return count

    def delete_question(self, group_id: str, question_id: str) -> int:
        return self.delete_questions(group_id, question_id)

    def delete_questions(self, group_id: str, question_ids: str | list[str] | tuple[str, ...] | set[str]) -> int:
        ids = self._parse_question_ids(question_ids)
        if not ids:
            return 0
        bank = self._bank()
        group_bank = bank.get(str(group_id), [])
        before = len(group_bank)
        group_bank = [item for item in group_bank if str(item.get("id", "")) not in ids]
        bank[str(group_id)] = group_bank
        self.ctx.set_state("quiz_bank", bank)
        return before - len(group_bank)

    def update_question(
        self,
        group_id: str,
        question_id: str,
        question: str,
        answer: str,
        *,
        category: str | None = None,
        note: str | None = None,
        enabled: bool | None = None,
    ) -> QuizQuestion | None:
        question_id = str(question_id or "").strip()
        question = str(question or "").strip()
        answer = str(answer or "").strip()
        if not question_id or not question or not answer:
            return None
        bank = self._bank()
        group_key = str(group_id)
        group_bank = bank.get(group_key, [])
        if not isinstance(group_bank, list):
            return None
        for item in group_bank:
            if not isinstance(item, dict) or str(item.get("id", "")) != question_id:
                continue
            item["question"] = question
            item["answer"] = answer
            if category is not None:
                item["category"] = str(category or "").strip()
            if note is not None:
                item["note"] = str(note or "").strip()
            if enabled is not None:
                item["enabled"] = bool(enabled)
            self.ctx.set_state("quiz_bank", bank)
            return self._question_from_item(item)
        return None

    def set_question_enabled(self, group_id: str, question_ids: str | list[str] | tuple[str, ...] | set[str], enabled: bool) -> int:
        ids = self._parse_question_ids(question_ids)
        if not ids:
            return 0
        bank = self._bank()
        group_key = str(group_id)
        group_bank = bank.get(group_key, [])
        changed = 0
        if not isinstance(group_bank, list):
            return 0
        for item in group_bank:
            if isinstance(item, dict) and str(item.get("id", "")) in ids:
                if bool(item.get("enabled", True)) != bool(enabled):
                    changed += 1
                item["enabled"] = bool(enabled)
        if changed:
            self.ctx.set_state("quiz_bank", bank)
        return changed

    def clear_group(self, group_id: str) -> int:
        bank = self._bank()
        group_id = str(group_id)
        group_bank = bank.get(group_id, [])
        removed = len(group_bank) if isinstance(group_bank, list) else 0
        bank.pop(group_id, None)
        self.ctx.set_state("quiz_bank", bank)
        return removed

    def list_questions(self, group_id: str, query: str = "") -> list[QuizQuestion]:
        result: list[QuizQuestion] = []
        query_text = str(query or "").strip().lower()
        for item in self._bank().get(str(group_id), []):
            if not isinstance(item, dict):
                continue
            question = self._question_from_item(item)
            if question is None:
                continue
            if query_text and query_text not in self._question_search_text(question):
                continue
            result.append(question)
        return sorted(result, key=lambda item: _int_value(item.question_id, default=0))

    def export_questions(self, group_id: str, query: str = "") -> str:
        questions = self.list_questions(group_id, query)
        if not questions:
            return "本群题库为空。"
        lines: list[str] = []
        for item in questions:
            fields = [item.category, item.question, item.answer, item.note]
            if item.category or item.note:
                line = "|".join(fields).rstrip("|")
            else:
                line = f"{item.question}={item.answer}"
            if not item.enabled:
                line = f"停用:{line}"
            lines.append(line)
        return "\n".join(lines)

    def cancel_current(self, group_id: str) -> int:
        sessions = self._sessions()
        removed = 1 if sessions.pop(str(group_id), None) is not None else 0
        if removed:
            self.ctx.set_state("quiz_sessions", sessions)
        return removed

    def current_session(self, group_id: str) -> dict[str, Any]:
        session = self._sessions().get(str(group_id), {})
        return dict(session) if isinstance(session, dict) else {}

    def question_count(self, group_id: str, *, enabled_only: bool = False) -> int:
        questions = self.list_questions(group_id)
        if enabled_only:
            questions = [item for item in questions if item.enabled]
        return len(questions)
        return result

    def start(self, group_id: str) -> QuizResult:
        if not self.enabled(group_id):
            return QuizResult(False, "")
        group_id = str(group_id)
        questions = [item for item in self.list_questions(group_id) if item.enabled]
        if not questions:
            total = self.question_count(group_id)
            if total:
                return QuizResult(True, "本群暂无已启用题目，请管理员启用题目。")
            return QuizResult(True, "本群暂无题目，请管理员先加题。")
        now = time.time()
        interval = self.interval_seconds(group_id)
        last_started = _float_value(self._settings().get(group_id, {}).get("quiz_last_started_at"), default=0.0)
        if interval and last_started and now - last_started < interval:
            wait = max(1, int(interval - (now - last_started)))
            return QuizResult(True, f"出题间隔未到，请 {wait} 秒后再试。")
        question = random.choice(questions)
        sessions = self._sessions()
        sessions[group_id] = {
            "question_id": question.question_id,
            "answer": question.answer,
            "started_at": now,
            "timeout_seconds": self.answer_timeout_seconds(group_id),
        }
        self.ctx.set_state("quiz_sessions", sessions)
        self._set_group_value(group_id, "quiz_last_started_at", now)
        return QuizResult(True, f"题目：{question.question}\n请发送：答题 答案")

    def answer(self, group_id: str, user_id: str, answer: str) -> QuizResult:
        if not self.enabled(group_id):
            return QuizResult(False, "")
        group_id = str(group_id)
        session = self._sessions().get(group_id)
        if not isinstance(session, dict):
            return QuizResult(True, "当前没有正在进行的题目，请先发送“出题”。")
        timeout = _non_negative_int(session.get("timeout_seconds", 0), default=0)
        started_at = _float_value(session.get("started_at"), default=0.0)
        if timeout and started_at and time.time() - started_at > timeout:
            sessions = self._sessions()
            sessions.pop(group_id, None)
            self.ctx.set_state("quiz_sessions", sessions)
            return QuizResult(True, "答题已超时，请重新出题。")
        expected = str(session.get("answer", "")).strip()
        if answer.strip().lower() != expected.lower():
            return QuizResult(True, "回答不正确。")
        reward = self.reward_points(group_id)
        total = PointsService(self.ctx).add_points(group_id, user_id, reward)
        sessions = self._sessions()
        sessions.pop(group_id, None)
        self.ctx.set_state("quiz_sessions", sessions)
        return QuizResult(True, f"回答正确，积分 +{reward}，当前积分：{total}。")

    def parse_question_pair(self, text: str) -> tuple[str, str]:
        item = self.parse_question_entry(text)
        if item is None:
            return "", ""
        return item.question, item.answer

    def parse_question_entry(self, text: str) -> ParsedQuizQuestion | None:
        raw = str(text or "").strip()
        if not raw:
            return None
        enabled = True
        for prefix in ("停用:", "停用：", "禁用:", "禁用：", "关闭:", "关闭："):
            if raw.startswith(prefix):
                enabled = False
                raw = raw[len(prefix) :].strip()
                break
        if not raw:
            return None

        if "|" in raw:
            parts = [part.strip() for part in raw.split("|")]
            if len(parts) >= 3:
                category, question, answer = parts[0], parts[1], parts[2]
                note = "|".join(parts[3:]).strip() if len(parts) > 3 else ""
                if question and answer:
                    return ParsedQuizQuestion(question, answer, enabled, category, note)

        separators = ("=>", "->", "＝", "=")
        for sep in separators:
            if sep in raw:
                question, answer = raw.split(sep, 1)
                question = question.strip()
                answer = answer.strip()
                if not question or not answer:
                    return None
                category = ""
                for marker in ("：", ":"):
                    if marker in question:
                        prefix, rest = question.split(marker, 1)
                        prefix = prefix.strip()
                        rest = rest.strip()
                        if prefix and rest and len(prefix) <= 30:
                            category = prefix
                            question = rest
                        break
                return ParsedQuizQuestion(question, answer, enabled, category, "")
        if "|" in raw:
            question, answer = raw.split("|", 1)
            question = question.strip()
            answer = answer.strip()
            if question and answer:
                return ParsedQuizQuestion(question, answer, enabled, "", "")
        return None

    def _set_group_value(self, group_id: str, key: str, value: Any) -> None:
        settings = self._settings()
        group_settings = settings.setdefault(str(group_id), {})
        group_settings[key] = value
        self.ctx.set_state("settings", settings)

    def _settings(self) -> dict[str, dict[str, Any]]:
        value = self.ctx.get_state("settings", {})
        return value if isinstance(value, dict) else {}

    def _bank(self) -> dict[str, list[dict[str, Any]]]:
        value = self.ctx.get_state("quiz_bank", {})
        return value if isinstance(value, dict) else {}

    def _sessions(self) -> dict[str, dict[str, Any]]:
        value = self.ctx.get_state("quiz_sessions", {})
        return value if isinstance(value, dict) else {}

    def _group_number(self, group_id: str, key: str, default: int, *, minimum: int = 1) -> int:
        try:
            value = self._settings().get(str(group_id), {}).get(key, default)
            return max(minimum, int(value))
        except (TypeError, ValueError):
            return max(minimum, int(default))

    def _question_from_item(self, item: dict[str, Any]) -> QuizQuestion | None:
        question_id = str(item.get("id", ""))
        question = str(item.get("question", ""))
        answer = str(item.get("answer", ""))
        if not question_id or not question or not answer:
            return None
        return QuizQuestion(
            question_id,
            question,
            answer,
            bool(item.get("enabled", True)),
            str(item.get("category", "") or ""),
            str(item.get("note", "") or ""),
        )

    def _question_search_text(self, item: QuizQuestion) -> str:
        status = "启用 enabled 开启" if item.enabled else "停用 disabled 禁用 关闭"
        return " ".join(
            [
                item.question_id,
                item.question,
                item.answer,
                item.category,
                item.note,
                status,
            ]
        ).lower()

    def _parse_question_ids(self, value: str | list[str] | tuple[str, ...] | set[str]) -> set[str]:
        if isinstance(value, str):
            ids = re.findall(r"\d+", value)
        elif isinstance(value, (list, tuple, set)):
            ids = [str(item).strip() for item in value]
        else:
            ids = []
        return {item for item in ids if item}


def _positive_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, parsed)


def _non_negative_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, parsed)


def _float_value(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int_value(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

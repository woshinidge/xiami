from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OneBotActionRecord:
    action: str
    ok: bool
    elapsed_ms: int
    message: str = ""
    slow: bool = False


class OneBotActionStats:
    def __init__(self, slow_threshold_ms: int = 1000, recent_limit: int = 50) -> None:
        self.slow_threshold_ms = int(slow_threshold_ms)
        self.recent_limit = int(recent_limit)
        self.total = 0
        self.ok = 0
        self.failed = 0
        self.slow = 0
        self.by_action: dict[str, dict[str, int]] = {}
        self.recent: list[OneBotActionRecord] = []

    def record(self, action: str, ok: bool, elapsed_ms: int, message: str = "") -> None:
        action = str(action or "unknown")
        elapsed_ms = max(0, int(elapsed_ms))
        is_slow = elapsed_ms >= self.slow_threshold_ms
        self.total += 1
        if ok:
            self.ok += 1
        else:
            self.failed += 1
        if is_slow:
            self.slow += 1

        bucket = self.by_action.setdefault(action, {"total": 0, "ok": 0, "failed": 0, "slow": 0})
        bucket["total"] += 1
        bucket["ok" if ok else "failed"] += 1
        if is_slow:
            bucket["slow"] += 1

        self.recent.append(OneBotActionRecord(action=action, ok=ok, elapsed_ms=elapsed_ms, message=message, slow=is_slow))
        if len(self.recent) > self.recent_limit:
            del self.recent[:-self.recent_limit]

    def snapshot(self, top_limit: int = 10) -> dict[str, Any]:
        actions = [
            {
                "action": action,
                "total": values["total"],
                "ok": values["ok"],
                "failed": values["failed"],
                "slow": values["slow"],
            }
            for action, values in self.by_action.items()
        ]
        actions.sort(key=lambda item: (item["failed"], item["slow"], item["total"], item["action"]), reverse=True)
        return {
            "total": self.total,
            "ok": self.ok,
            "failed": self.failed,
            "slow": self.slow,
            "slow_threshold_ms": self.slow_threshold_ms,
            "actions": actions[:top_limit],
            "recent": [
                {
                    "action": item.action,
                    "ok": item.ok,
                    "elapsed_ms": item.elapsed_ms,
                    "message": item.message,
                    "slow": item.slow,
                }
                for item in self.recent[-top_limit:]
            ],
        }


def format_onebot_action_stats(stats: OneBotActionStats | dict[str, Any], top_limit: int = 10) -> str:
    snapshot = stats.snapshot(top_limit=top_limit) if isinstance(stats, OneBotActionStats) else stats
    lines = [
        "OneBot 调用统计：",
        f"- 总数：{snapshot.get('total', 0)}",
        f"- 成功：{snapshot.get('ok', 0)}",
        f"- 失败：{snapshot.get('failed', 0)}",
        f"- 慢调用：{snapshot.get('slow', 0)}（阈值 {snapshot.get('slow_threshold_ms', 0)}ms）",
    ]
    actions = snapshot.get("actions") or []
    if actions:
        lines.append("- 动作排行：")
        for item in actions[:top_limit]:
            lines.append(
                "  - {action}: total={total}, ok={ok}, failed={failed}, slow={slow}".format(**item)
            )
    recent = snapshot.get("recent") or []
    if recent:
        lines.append("- 最近调用：")
        for item in recent[-top_limit:]:
            status = "OK" if item.get("ok") else "FAIL"
            slow = " slow" if item.get("slow") else ""
            message = str(item.get("message") or "")
            detail = f" {message}" if message else ""
            lines.append(f"  - {status}{slow} {item.get('action')} {item.get('elapsed_ms')}ms{detail}")
    return "\n".join(lines)

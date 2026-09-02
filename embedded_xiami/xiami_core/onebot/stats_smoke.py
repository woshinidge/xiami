from __future__ import annotations

from xiami_core.onebot.client import OneBotHttpClient, OneBotResponse
from xiami_core.onebot.stats import OneBotActionStats, format_onebot_action_stats


class FakeClient(OneBotHttpClient):
    def _call_once(self, action: str, params: dict[str, object]) -> OneBotResponse:
        if action == "send_group_msg":
            return OneBotResponse(ok=False, message="群消息失败")
        return OneBotResponse(ok=True, data={"params": params}, message="ok")


def main() -> int:
    stats = OneBotActionStats(slow_threshold_ms=0, recent_limit=5)
    client = FakeClient("http://127.0.0.1:1", action_stats=stats)
    ok = client.call("get_login_info", {})
    failed = client.call("send_group_msg", {"group_id": 10000, "message": "hello"})
    if not ok.ok or failed.ok:
        raise RuntimeError(f"fake client responses wrong: {ok!r} {failed!r}")

    snapshot = stats.snapshot()
    if snapshot["total"] != 2 or snapshot["ok"] != 1 or snapshot["failed"] != 1:
        raise RuntimeError(f"summary wrong: {snapshot!r}")
    if snapshot["slow"] != 2:
        raise RuntimeError(f"slow count wrong: {snapshot!r}")
    failed_actions = [item for item in snapshot["actions"] if item["action"] == "send_group_msg"]
    if not failed_actions or failed_actions[0]["failed"] != 1:
        raise RuntimeError(f"failed action missing: {snapshot!r}")
    recent = snapshot["recent"]
    if recent[-1]["action"] != "send_group_msg" or "群消息失败" not in recent[-1]["message"]:
        raise RuntimeError(f"recent call missing: {recent!r}")
    text = format_onebot_action_stats(stats)
    if "OneBot 调用统计" not in text or "send_group_msg" not in text or "FAIL" not in text:
        raise RuntimeError(f"formatted stats missing fields: {text}")
    print("onebot stats smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

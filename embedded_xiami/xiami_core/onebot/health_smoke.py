from __future__ import annotations

import json

from xiami_core.testing import use_temp_xiami_home

use_temp_xiami_home()

from xiami_core.messages import MessageRecord
from xiami_core.onebot.health import build_onebot_health_summary, format_onebot_health_summary
from xiami_core.onebot.stats import OneBotActionStats
from xiami_core.storage.paths import LOG_HOME


def main() -> int:
    LOG_HOME.mkdir(parents=True, exist_ok=True)
    event_log = LOG_HOME / "onebot_events.jsonl"
    event_log.write_text(
        json.dumps(
            {
                "time": "2026-06-29T12:00:00",
                "ok": True,
                "post_type": "message",
                "parsed_type": "group",
                "parsed_sender": "10001",
                "parsed_target": "20001",
                "parsed_text": "hello",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    action_stats = OneBotActionStats(slow_threshold_ms=10)
    action_stats.record("get_login_info", True, 3, "ok")
    action_stats.record("send_group_msg", False, 15, "无法获取用户信息")
    summary = build_onebot_health_summary(
        plugin_diagnostics=[
            {
                "id": "echo",
                "name": "Echo",
                "enabled": True,
                "error": "",
                "message_count": 2,
                "message_handled_count": 1,
                "message_unhandled_count": 1,
                "event_count": 1,
                "event_handled_count": 1,
                "event_unhandled_count": 0,
                "error_count": 0,
                "capabilities": ["message-matchers:2", "event-matchers:1", "schedules:1", "onebot:get_group_list", "send:image"],
            }
        ],
        recent_messages=[
            MessageRecord(direction="outgoing", message_type="private", target="10001", text="hi", status="ok"),
            MessageRecord(direction="plugin", message_type="private", target="10001", text="pong", status="ok"),
            MessageRecord(direction="plugin", message_type="group", target="20001", text="", status="failed", detail="failed"),
        ],
        action_stats=action_stats,
    )
    rendered = format_onebot_health_summary(summary)
    for expected in (
        "Xiami 健康摘要",
        "插件：",
        "消息分发：2",
        "消息命中：1，未命中：1",
        "事件命中：1，未命中：0",
        "迁移能力：覆盖 1 个插件，能力 5 项",
        "插件回复：成功 1，失败 1",
        "OneBot 调用统计",
        "send_group_msg",
        "失败：1",
        "最近 OneBot 事件",
    ):
        if expected not in rendered:
            raise RuntimeError(rendered)
    print("onebot health smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

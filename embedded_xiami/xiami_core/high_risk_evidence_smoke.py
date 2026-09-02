from __future__ import annotations

import json

from xiami_core.testing import use_temp_xiami_home

use_temp_xiami_home()

from xiami_core.high_risk_evidence import (
    EVENT_LOG_FILE,
    build_high_risk_evidence_suggestions,
    format_high_risk_evidence_suggestions,
    record_suggested_high_risk_evidence,
)
from xiami_core.high_risk_gate import build_high_risk_gate
from xiami_core.messages import MessageRecord, MessageStore
from xiami_core.onebot.action_log import OneBotActionLogEntry, append_onebot_action_log


def main() -> int:
    EVENT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    EVENT_LOG_FILE.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "time": "2026-01-01T00:00:00",
                        "post_type": "request",
                        "request_type": "friend",
                        "raw": {"post_type": "request", "request_type": "friend"},
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "time": "2026-01-01T00:00:01",
                        "post_type": "request",
                        "request_type": "group",
                        "raw": {"post_type": "request", "request_type": "group"},
                    },
                    ensure_ascii=False,
                ),
            ]
        ),
        encoding="utf-8",
    )
    for action in ["set_group_ban", "delete_msg", "get_group_list"]:
        append_onebot_action_log(OneBotActionLogEntry(action=action, ok=True, elapsed_ms=8))
    MessageStore().append(
        MessageRecord(
            direction="plugin",
            message_type="group",
            target="20001",
            text="违禁词命中并撤回",
            source="smoke",
        )
    )

    suggestions = build_high_risk_evidence_suggestions()
    rendered = format_high_risk_evidence_suggestions(suggestions)
    if suggestions.recordable_count != 5:
        raise RuntimeError(rendered)
    recorded = record_suggested_high_risk_evidence(suggestions, source="smoke")
    if len(recorded) != 5:
        raise RuntimeError(f"recorded mismatch: {len(recorded)}")
    gate = build_high_risk_gate()
    if not gate.ok:
        raise RuntimeError(rendered)
    print("high-risk evidence smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

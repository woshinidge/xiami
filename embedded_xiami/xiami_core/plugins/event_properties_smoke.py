from __future__ import annotations

from xiami_core.models import XiamiMessage
from xiami_core.plugins.events import plugin_event_from_message, plugin_event_from_onebot


def main() -> int:
    message = plugin_event_from_message(XiamiMessage(message_type="group", sender="10001", target="20001", text="hello"))
    if message.post_type != "message" or message.message_type != "group" or message.user_id != "10001":
        raise AssertionError(message)
    if message.group_id != "20001" or message.text != "hello" or not message.is_group:
        raise AssertionError(message)

    notice = plugin_event_from_onebot(
        {
            "post_type": "notice",
            "notice_type": "group_decrease",
            "sub_type": "leave",
            "group_id": 20001,
            "user_id": 10002,
            "operator_id": 10003,
            "message_id": 42,
        }
    )
    if notice.post_type != "notice" or notice.notice_type != "group_decrease" or notice.sub_type != "leave":
        raise AssertionError(notice)
    if notice.group_id != "20001" or notice.user_id != "10002" or notice.operator_id != "10003" or notice.message_id != "42":
        raise AssertionError(notice)

    request = plugin_event_from_onebot(
        {
            "post_type": "request",
            "request_type": "friend",
            "user_id": 10004,
            "flag": "flag-a",
            "comment": "验证信息",
        }
    )
    if request.post_type != "request" or request.request_type != "friend":
        raise AssertionError(request)
    if request.user_id != "10004" or request.flag != "flag-a" or request.comment != "验证信息":
        raise AssertionError(request)

    print("event properties smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

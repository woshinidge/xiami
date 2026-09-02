from __future__ import annotations

from xiami_core.contacts import ContactStore, contact_from_message
from xiami_core.messages import MessageRecord
from xiami_core.testing import use_temp_xiami_home


def main() -> int:
    use_temp_xiami_home()
    friend_record = MessageRecord(
        direction="incoming",
        message_type="private",
        target="10000",
        sender="好友昵称(10001)",
        text="hello",
        source="onebot",
    )
    friend = contact_from_message(friend_record)
    if not friend or friend.kind != "friend" or friend.id != "10001" or friend.name != "好友昵称":
        raise RuntimeError(f"friend contact parse failed: {friend}")
    group_record = MessageRecord(
        direction="incoming",
        message_type="group",
        target="测试群(20001)",
        sender="群成员(10002)",
        text="hello",
        source="onebot",
    )
    group = contact_from_message(group_record)
    if not group or group.kind != "group" or group.id != "20001" or group.name != "测试群":
        raise RuntimeError(f"group contact parse failed: {group}")
    store = ContactStore()
    store.upsert_from_message(friend_record)
    store.upsert_from_message(group_record)
    contacts = store.load()
    if {contact.id for contact in contacts} != {"10001", "20001"}:
        raise RuntimeError(f"contacts not persisted: {contacts}")
    print("contacts from message smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

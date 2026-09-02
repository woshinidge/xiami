from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from xiami_core.messages import MessageRecord
from xiami_core.onebot.client import OneBotHttpClient
from xiami_core.storage.config import load_config
from xiami_core.storage.paths import LOG_HOME, ensure_runtime_dirs
from xiami_core.text_clean import clean_text


ContactKind = Literal["friend", "group"]


@dataclass(frozen=True)
class Contact:
    kind: ContactKind
    id: str
    name: str
    remark: str = ""


@dataclass(frozen=True)
class ContactSyncResult:
    ok: bool
    detail: str
    contacts: list[Contact]


class ContactStore:
    def __init__(self, path: Path | None = None) -> None:
        ensure_runtime_dirs()
        self.path = path or LOG_HOME / "contacts.json"

    def save(self, contacts: list[Contact]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = [asdict(contact) for contact in contacts]
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self) -> list[Contact]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        contacts: list[Contact] = []
        if not isinstance(data, list):
            return contacts
        for item in data:
            contact = _contact_from_json(item)
            if contact:
                contacts.append(contact)
        return contacts

    def upsert_from_message(self, record: MessageRecord) -> Contact | None:
        contact = contact_from_message(record)
        if not contact:
            return None
        contacts = self.load()
        merged: list[Contact] = []
        replaced = False
        for item in contacts:
            if item.kind == contact.kind and item.id == contact.id:
                merged.append(_merge_contact(item, contact))
                replaced = True
            else:
                merged.append(item)
        if not replaced:
            merged.append(contact)
        self.save(merged)
        return contact


def sync_contacts() -> ContactSyncResult:
    config = load_config().kernel
    client = OneBotHttpClient(config.http_url, config.access_token, timeout=2.5)
    contacts: list[Contact] = []
    errors: list[str] = []
    friend_response = client.get_friend_list()
    if friend_response.ok:
        contacts.extend(_parse_friends(friend_response.data))
    else:
        errors.append(f"好友列表失败：{friend_response.message}")
    group_response = client.get_group_list()
    if group_response.ok:
        contacts.extend(_parse_groups(group_response.data))
    else:
        errors.append(f"群列表失败：{group_response.message}")
    if contacts:
        ContactStore().save(contacts)
    detail = f"已同步 {len(contacts)} 个联系人"
    if errors:
        detail += "；" + "；".join(errors)
    return ContactSyncResult(ok=not errors, detail=detail, contacts=contacts)


def contact_from_message(record: MessageRecord) -> Contact | None:
    if record.message_type == "group":
        group_id = _id_from_label(record.target)
        if not group_id:
            return None
        return Contact(kind="group", id=group_id, name=_name_from_label(record.target) or group_id)
    if record.message_type == "private":
        label = record.sender if record.direction == "incoming" else record.target
        contact_id = _id_from_label(label)
        if not contact_id or contact_id in {"xiami", "plugin-test"}:
            return None
        return Contact(kind="friend", id=contact_id, name=_name_from_label(label) or contact_id)
    return None


def _parse_friends(data: object) -> list[Contact]:
    contacts: list[Contact] = []
    for item in _as_list(data):
        if not isinstance(item, dict):
            continue
        user_id = item.get("user_id") or item.get("uin") or item.get("id")
        if user_id is None:
            continue
        name = item.get("remark") or item.get("nickname") or item.get("name") or str(user_id)
        contacts.append(Contact(kind="friend", id=str(user_id), name=str(name), remark=str(item.get("remark") or "")))
    return contacts


def _parse_groups(data: object) -> list[Contact]:
    contacts: list[Contact] = []
    for item in _as_list(data):
        if not isinstance(item, dict):
            continue
        group_id = item.get("group_id") or item.get("id")
        if group_id is None:
            continue
        name = item.get("group_name") or item.get("group_remark") or item.get("name") or str(group_id)
        contacts.append(Contact(kind="group", id=str(group_id), name=str(name)))
    return contacts


def _as_list(data: object) -> list[Any]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        nested = data.get("data")
        if isinstance(nested, list):
            return nested
    return []


def _contact_from_json(data: object) -> Contact | None:
    if not isinstance(data, dict):
        return None
    kind = data.get("kind")
    if kind not in {"friend", "group"}:
        return None
    contact_id = str(data.get("id") or "")
    if not contact_id:
        return None
    return Contact(
        kind=kind,  # type: ignore[arg-type]
        id=contact_id,
        name=clean_text(data.get("name") or contact_id),
        remark=clean_text(data.get("remark") or ""),
    )


def _merge_contact(existing: Contact, incoming: Contact) -> Contact:
    return Contact(
        kind=existing.kind,
        id=existing.id,
        name=existing.name if existing.name and existing.name != existing.id else incoming.name,
        remark=existing.remark or incoming.remark,
    )


def _id_from_label(value: str) -> str:
    value = clean_text(value)
    matches = re.findall(r"\((\d{5,})\)", value)
    if matches:
        return matches[-1]
    return value if re.fullmatch(r"\d{5,}", value) else ""


def _name_from_label(value: str) -> str:
    value = clean_text(value)
    if not value:
        return ""
    value = re.sub(r"\(\d{5,}\)$", "", value).strip()
    return value

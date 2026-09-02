from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Iterable

from xiami_core.storage.paths import LOG_HOME, ensure_runtime_dirs

if TYPE_CHECKING:
    from xiami_core.acceptance import AcceptanceItem


MANUAL_EVIDENCE_FILE = LOG_HOME / "manual_acceptance.json"


@dataclass(frozen=True)
class ManualAcceptanceEvidence:
    name: str
    ok: bool
    detail: str
    source: str
    updated_at: str


def load_manual_evidence() -> dict[str, ManualAcceptanceEvidence]:
    if not MANUAL_EVIDENCE_FILE.exists():
        return {}
    try:
        raw = json.loads(MANUAL_EVIDENCE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(raw, dict):
        return {}
    records: dict[str, ManualAcceptanceEvidence] = {}
    for name, item in raw.items():
        if not isinstance(item, dict):
            continue
        evidence_name = str(item.get("name") or name)
        records[evidence_name] = ManualAcceptanceEvidence(
            name=evidence_name,
            ok=bool(item.get("ok")),
            detail=str(item.get("detail") or ""),
            source=str(item.get("source") or "manual"),
            updated_at=str(item.get("updated_at") or ""),
        )
    return records


def save_manual_evidence(records: dict[str, ManualAcceptanceEvidence]) -> None:
    ensure_runtime_dirs()
    MANUAL_EVIDENCE_FILE.write_text(
        json.dumps({name: asdict(item) for name, item in sorted(records.items())}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def record_manual_evidence(
    name: str,
    detail: str,
    *,
    ok: bool = True,
    source: str = "manual",
    records: dict[str, ManualAcceptanceEvidence] | None = None,
) -> ManualAcceptanceEvidence:
    current = records if records is not None else load_manual_evidence()
    evidence = ManualAcceptanceEvidence(
        name=str(name),
        ok=bool(ok),
        detail=str(detail),
        source=str(source or "manual"),
        updated_at=datetime.now().isoformat(timespec="seconds"),
    )
    current[evidence.name] = evidence
    if records is None:
        save_manual_evidence(current)
    return evidence


def record_real_loop_confirmation(detail: str, *, source: str = "user") -> list[ManualAcceptanceEvidence]:
    records = load_manual_evidence()
    items = [
        "real_login",
        "onebot_login_info",
        "receive_private_event",
        "receive_group_event",
        "ui_private_received",
        "ui_group_received",
        "send_private_ok",
        "send_group_ok",
    ]
    result = [record_manual_evidence(name, detail, source=source, records=records) for name in items]
    save_manual_evidence(records)
    return result


def apply_manual_evidence(items: Iterable["AcceptanceItem"]) -> list["AcceptanceItem"]:
    from xiami_core.acceptance import AcceptanceItem

    records = load_manual_evidence()
    result: list[AcceptanceItem] = []
    for item in items:
        evidence = records.get(item.name)
        if evidence and evidence.ok and not item.ok:
            result.append(
                AcceptanceItem(
                    item.name,
                    True,
                    f"{evidence.detail}（{evidence.source} confirmed at {evidence.updated_at}）",
                )
            )
        else:
            result.append(item)
    return result

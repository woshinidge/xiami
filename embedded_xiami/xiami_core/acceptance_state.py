from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime

from xiami_core.acceptance import AcceptanceItem, format_acceptance
from xiami_core.storage.paths import LOG_HOME, ensure_runtime_dirs


@dataclass(frozen=True)
class AcceptanceSnapshot:
    passed: int
    total: int
    report: str
    updated_at: str


def save_acceptance_snapshot(items: list[AcceptanceItem]) -> AcceptanceSnapshot:
    ensure_runtime_dirs()
    snapshot = AcceptanceSnapshot(
        passed=sum(1 for item in items if item.ok),
        total=len(items),
        report=format_acceptance(items),
        updated_at=datetime.now().isoformat(timespec="seconds"),
    )
    path = _snapshot_path()
    path.write_text(json.dumps(asdict(snapshot), ensure_ascii=False, indent=2), encoding="utf-8")
    return snapshot


def load_acceptance_snapshot() -> AcceptanceSnapshot | None:
    path = _snapshot_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    try:
        return AcceptanceSnapshot(
            passed=int(data.get("passed") or 0),
            total=int(data.get("total") or 0),
            report=str(data.get("report") or ""),
            updated_at=str(data.get("updated_at") or ""),
        )
    except (TypeError, ValueError):
        return None


def _snapshot_path():
    return LOG_HOME / "acceptance_snapshot.json"

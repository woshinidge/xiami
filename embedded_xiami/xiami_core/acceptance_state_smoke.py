from __future__ import annotations

from xiami_core.testing import use_temp_xiami_home

use_temp_xiami_home()

from xiami_core.acceptance import AcceptanceItem
from xiami_core.acceptance_state import load_acceptance_snapshot, save_acceptance_snapshot


def main() -> int:
    snapshot = save_acceptance_snapshot(
        [
            AcceptanceItem("a", True, "ok"),
            AcceptanceItem("b", False, "pending"),
        ]
    )
    if snapshot.passed != 1 or snapshot.total != 2 or "Xiami v1 验收" not in snapshot.report:
        raise RuntimeError(f"bad saved snapshot: {snapshot}")
    loaded = load_acceptance_snapshot()
    if loaded != snapshot:
        raise RuntimeError(f"snapshot load mismatch: {loaded} != {snapshot}")
    print("acceptance state smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

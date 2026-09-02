from __future__ import annotations

from xiami_core.testing import use_temp_xiami_home

use_temp_xiami_home()

from xiami_core.messages import MessageStore
from xiami_core.send_probe import format_send_probe, run_send_probe
from xiami_core.storage.config import AppConfig, KernelConfig, save_config


def main() -> int:
    save_config(
        AppConfig(
            kernel=KernelConfig(kind="Mock"),
            probe_private_target="10001",
            probe_group_target="20001",
        )
    )
    items = run_send_probe()
    names = {item.name for item in items}
    if {"send_private_probe", "send_group_probe"} - names:
        raise RuntimeError(f"send probe items missing: {names}")
    failed = [item for item in items if not item.ok]
    if failed:
        raise RuntimeError(f"send probe failed under mock: {failed}")
    records = MessageStore().recent(10)
    if not any(record.message_type == "private" and record.status == "ok" for record in records):
        raise RuntimeError("private probe record missing")
    if not any(record.message_type == "group" and record.status == "ok" for record in records):
        raise RuntimeError("group probe record missing")
    report = format_send_probe(items)
    if "真实收发探针" not in report or "send_group_probe" not in report:
        raise RuntimeError(f"bad send probe report: {report}")
    print("send probe smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

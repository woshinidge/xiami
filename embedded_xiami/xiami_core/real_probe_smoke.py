from __future__ import annotations

from pathlib import Path

from xiami_core.testing import use_temp_xiami_home

use_temp_xiami_home()

from xiami_core.real_probe import format_probe, run_real_login_probe
from xiami_core.storage.config import AppConfig, KernelConfig, save_config


def main() -> int:
    home = Path(use_temp_xiami_home())
    kernel_root = home / "kernels" / "NapCat"
    save_config(
        AppConfig(
            kernel=KernelConfig(
                kind="NapCat",
                executable=str(kernel_root / "missing.bat"),
                working_dir=str(kernel_root),
                http_url="http://127.0.0.1:1",
            )
        )
    )
    items = run_real_login_probe(start=True, timeout=1)
    names = {item.name for item in items}
    for expected in {"event_gateway", "napcat_config_ensure", "napcat_onebot_config", "real_login"}:
        if expected not in names:
            raise RuntimeError(f"real probe start item missing {expected}: {items}")
    if not next(item for item in items if item.name == "event_gateway").ok:
        raise RuntimeError(f"event gateway did not start: {items}")
    if not next(item for item in items if item.name == "napcat_onebot_config").ok:
        raise RuntimeError(f"napcat onebot config not ensured: {items}")
    if next(item for item in items if item.name == "real_login").ok:
        raise RuntimeError(f"missing executable should not pass real login: {items}")
    report = format_probe(items)
    if "真实登录探针" not in report or "event_gateway" not in report:
        raise RuntimeError(f"bad real probe report: {report}")
    print("real probe smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

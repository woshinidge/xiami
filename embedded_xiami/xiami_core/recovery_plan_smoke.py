from __future__ import annotations

from pathlib import Path

from xiami_core.models import AccountStatus
from xiami_core.recovery_plan import build_recovery_plan, format_recovery_plan
from xiami_core.runtime_diagnostic import RuntimeDiagnostic
from xiami_core.storage.config import AppConfig, KernelConfig


def main() -> int:
    diag = _diag(onebot=True)
    online = build_recovery_plan(status=AccountStatus(state="online", account="10000"), diagnostic=diag)
    if not online.ok or "长稳观察" not in format_recovery_plan(online):
        raise RuntimeError(format_recovery_plan(online))

    offline = build_recovery_plan(status=AccountStatus(state="offline"), diagnostic=_diag(suggested=True))
    if offline.ok or "启动登录内核" not in format_recovery_plan(offline):
        raise RuntimeError(format_recovery_plan(offline))

    qr = build_recovery_plan(
        status=AccountStatus(state="waiting_qr", qr_hint="qrcode.png"),
        diagnostic=_diag(qr_candidates=(Path("qrcode.png"),)),
    )
    if "扫码登录" not in format_recovery_plan(qr):
        raise RuntimeError(format_recovery_plan(qr))

    conflict = build_recovery_plan(
        status=AccountStatus(state="online", account="10000"),
        diagnostic=_diag(onebot=False, port=True),
    )
    text = format_recovery_plan(conflict)
    if "检查端口占用" not in text or "重启登录内核" not in text:
        raise RuntimeError(text)

    print("recovery plan smoke ok")
    return 0


def _diag(
    *,
    onebot: bool = False,
    port: bool = False,
    executable: str = "",
    suggested: bool = False,
    qr_candidates: tuple[Path, ...] = (),
) -> RuntimeDiagnostic:
    return RuntimeDiagnostic(
        config=AppConfig(kernel=KernelConfig(kind="NapCat", executable=executable)),
        kernel_candidates=(),
        suggested_kernel=KernelConfig(kind="NapCat", executable="napcat.bat") if suggested else None,
        onebot_reachable=onebot,
        onebot_detail="ok" if onebot else "unreachable",
        configured_port_open=port,
        qr_candidates=qr_candidates,
        napcat_config_ok=True,
        napcat_config_detail="ok",
    )


if __name__ == "__main__":
    raise SystemExit(main())

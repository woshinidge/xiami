from __future__ import annotations

import tempfile
from pathlib import Path

from xiami_core.kernels.external import NapCatKernel
from xiami_core.storage.config import KernelConfig


def main() -> int:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        bootmain = root / "bootmain"
        bootmain.mkdir()
        executable = bootmain / "xiami_napcat_start.bat"
        executable.write_text("@echo off\r\nNapCatWinBootMain.exe\r\n", encoding="utf-8")
        (root / "NapCatInstaller.exe").write_text("", encoding="utf-8")
        kernel = NapCatKernel(
            KernelConfig(
                kind="NapCat",
                executable=str(executable),
                working_dir=str(bootmain),
            )
        )
        status = kernel.prepare()
        if status.state != "error" or "阻止启动安装器" not in status.detail:
            raise RuntimeError(f"guard did not block uninitialized OneKey: {status}")
    print("napcat guard smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

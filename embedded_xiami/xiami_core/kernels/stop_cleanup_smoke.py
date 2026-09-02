from __future__ import annotations

import tempfile
from pathlib import Path

from xiami_core.kernels.external import NapCatKernel
from xiami_core.storage.config import KernelConfig


def main() -> int:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        executable = root / "napcat.bat"
        executable.write_text("node.exe ./index.js\r\n", encoding="utf-8")
        qr = root / "napcat" / "cache" / "qrcode.png"
        qr.parent.mkdir(parents=True)
        qr.write_bytes(b"fake")
        kernel = NapCatKernel(KernelConfig(kind="NapCat", executable=str(executable), working_dir=str(root)))
        status = kernel.status()
        if not status.qr_hint:
            raise RuntimeError(f"qr was not discovered before stop: {status}")
        stopped = kernel.stop()
        if stopped.qr_hint or qr.exists():
            raise RuntimeError(f"stop did not clean qr cache: {stopped}, exists={qr.exists()}")
    print("stop cleanup smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

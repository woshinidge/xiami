from __future__ import annotations

import tempfile
import os
from pathlib import Path
import time

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
        kernel = NapCatKernel(
            KernelConfig(
                kind="NapCat",
                executable=str(executable),
                working_dir=str(root),
                http_url="http://127.0.0.1:1",
            )
        )
        status = kernel.status()
        if status.state != "waiting_qr" or status.qr_hint != str(qr):
            raise RuntimeError(f"qr discovery failed: {status}")
        old_time = time.time() - 60
        qr.touch()
        os.utime(qr, (old_time, old_time))
        kernel._start_wall_time = time.time()
        kernel._qr_hint_cache = ""
        kernel._qr_scan_at = 0.0
        status = kernel.status()
        if status.qr_hint:
            raise RuntimeError(f"stale qr should be ignored: {status}")
        time.sleep(0.01)
        qr.write_bytes(b"fresh")
        kernel._qr_scan_at = 0.0
        status = kernel.status()
        if status.state != "waiting_qr" or status.qr_hint != str(qr):
            raise RuntimeError(f"fresh qr discovery failed: {status}")
        print("qr discovery smoke ok")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path

from xiami_core.kernels.external import NapCatKernel
from xiami_core.storage.config import KernelConfig


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        sleeper = root / "sleeper.py"
        marker = root / "started.txt"
        sleeper.write_text(
            "\n".join(
                [
                    "from pathlib import Path",
                    "import time",
                    f"Path({str(marker)!r}).write_text('started', encoding='utf-8')",
                    "time.sleep(60)",
                ]
            ),
            encoding="utf-8",
        )
        kernel = NapCatKernel(
            KernelConfig(
                kind="NapCat",
                executable=sys.executable,
                working_dir=str(root),
                arguments=[str(sleeper)],
                http_url="http://127.0.0.1:1",
            )
        )
        status = kernel.start_login()
        if status.state not in {"starting", "waiting_qr", "error"}:
            raise RuntimeError(f"unexpected start state: {status}")
        deadline = time.monotonic() + 3
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        if not marker.exists():
            raise RuntimeError("test kernel process did not start")
        process = kernel._process
        if process is None or process.poll() is not None:
            raise RuntimeError("kernel process exited before stop")
        kernel.stop()
        deadline = time.monotonic() + 3
        while process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        if process.poll() is None:
            process.kill()
            raise RuntimeError("kernel stop did not terminate process")
        if sys.platform == "win32" and _is_pid_alive(process.pid):
            raise RuntimeError(f"kernel process still alive after stop: {process.pid}")
    print("kernel stop contract smoke ok")
    return 0


def _is_pid_alive(pid: int) -> bool:
    result = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )
    return str(pid) in result.stdout


if __name__ == "__main__":
    raise SystemExit(main())

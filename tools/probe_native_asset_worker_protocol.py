from __future__ import annotations

import argparse
import os
import struct
import subprocess
import sys
import threading
import time
from concurrent.futures import Future
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from toolbox_native_asset_worker import (  # noqa: E402
    HEADER,
    MAGIC,
    MAX_CONTROL_PAYLOAD,
    NativeAssetWorkerBroker,
    NativeAssetWorkerError,
    PING,
    PROTOCOL_VERSION,
)


def _spawn(executable: Path) -> subprocess.Popen:
    return subprocess.Popen(
        [str(executable), "--asset-worker", "--input", "-", "--output", "-"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def _expect_rejected(executable: Path, payload: bytes) -> None:
    process = _spawn(executable)
    assert process.stdout.read(28)
    process.stdin.write(payload)
    process.stdin.close()
    process.stdin = None
    _stdout, stderr = process.communicate(timeout=3.0)
    assert process.returncode != 0, "malformed frame was accepted"
    assert b"XIAMI_NATIVE_ERROR" in stderr, stderr.decode("utf-8", errors="replace")


def _probe_heartbeat_and_transaction_guards(executable: Path) -> None:
    class TwoCycleStop:
        def __init__(self) -> None:
            self.calls = 0

        def wait(self, _timeout: float) -> bool:
            self.calls += 1
            return self.calls > 1

    heartbeat_broker = NativeAssetWorkerBroker(str(executable), timeout=0.1)
    heartbeat_broker._heartbeat_stop = TwoCycleStop()
    heartbeat_broker._pending[99] = Future()
    heartbeat_calls = []
    heartbeat_broker.ping = lambda *args, **kwargs: heartbeat_calls.append(
        (args, kwargs)
    )
    heartbeat_broker._heartbeat_loop()
    assert not heartbeat_calls, "heartbeat ran while a business request was pending"

    class Sink:
        def write(self, _data: bytes) -> None:
            return None

        def flush(self) -> None:
            return None

    class WaitingProcess:
        def __init__(self) -> None:
            self.stdin = Sink()
            self.killed = False

        def poll(self):
            return None

        def kill(self) -> None:
            self.killed = True

    timeout_broker = NativeAssetWorkerBroker(str(executable), timeout=0.02)
    waiting_process = WaitingProcess()
    timeout_broker._process = waiting_process
    timeout_broker.start = lambda: 1
    try:
        timeout_broker.request(
            PING,
            b"nonfatal-heartbeat",
            timeout=0.02,
            terminate_on_timeout=False,
        )
    except NativeAssetWorkerError:
        pass
    else:
        raise AssertionError("nonfatal heartbeat timeout unexpectedly succeeded")
    assert not waiting_process.killed
    assert timeout_broker._process is waiting_process
    assert timeout_broker._abandoned

    transaction_broker = NativeAssetWorkerBroker(str(executable), timeout=0.1)
    first_entered = threading.Event()
    transaction_order = []

    def first_transaction() -> None:
        with transaction_broker.authorization_transaction():
            transaction_order.append("first-open")
            first_entered.set()
            time.sleep(0.05)
            transaction_order.append("first-commit")

    def second_transaction() -> None:
        assert first_entered.wait(1.0)
        with transaction_broker.authorization_transaction():
            transaction_order.append("second-open")
            transaction_order.append("second-commit")

    first_thread = threading.Thread(target=first_transaction)
    second_thread = threading.Thread(target=second_transaction)
    first_thread.start()
    second_thread.start()
    first_thread.join(timeout=2.0)
    second_thread.join(timeout=2.0)
    assert not first_thread.is_alive() and not second_thread.is_alive()
    assert transaction_order == [
        "first-open",
        "first-commit",
        "second-open",
        "second-commit",
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--exe",
        default=str(PROJECT_ROOT / "build" / "native_core" / "xiami_native_core.exe"),
    )
    args = parser.parse_args()
    executable = Path(args.exe).resolve()
    if not executable.is_file():
        raise SystemExit("native core executable is missing: %s" % executable)

    with NativeAssetWorkerBroker(str(executable), timeout=3.0) as broker:
        pid = broker.pid
        generation = broker.generation
        assert "protocol=1" in broker.hello
        for index in range(100):
            payload = ("ping-%d" % index).encode("ascii")
            assert broker.ping(payload) == payload
            assert broker.pid == pid
            assert broker.generation == generation
        broker.assert_generation(generation)

    _probe_heartbeat_and_transaction_guards(executable)

    good_header = HEADER.pack(MAGIC, PROTOCOL_VERSION, 2, 0, 7, 0)
    _expect_rejected(executable, good_header[:12])
    _expect_rejected(executable, b"BAD!" + good_header[4:])
    _expect_rejected(executable, HEADER.pack(MAGIC, 99, 2, 0, 7, 0))
    _expect_rejected(executable, HEADER.pack(MAGIC, PROTOCOL_VERSION, 99, 0, 7, 0))
    _expect_rejected(
        executable,
        HEADER.pack(MAGIC, PROTOCOL_VERSION, 2, 0, 7, MAX_CONTROL_PAYLOAD + 1),
    )
    print("native asset worker protocol probe: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

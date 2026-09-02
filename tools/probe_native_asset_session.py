from __future__ import annotations

import hashlib
import os
import pathlib
import secrets
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import toolbox_native_core as native_core  # noqa: E402
from toolbox_native_asset_worker import NativeAssetWorkerBroker  # noqa: E402
from tools import probe_native_core_protocol as protocol_probe  # noqa: E402


def main() -> int:
    executable = ROOT / "build" / "native_core" / "xiami_native_core.exe"
    if not executable.is_file():
        raise RuntimeError("native core is missing: %s" % executable)
    old_path = os.environ.get("XIAMI_NATIVE_CORE_PATH")
    os.environ["XIAMI_NATIVE_CORE_PATH"] = str(executable)
    try:
        with tempfile.TemporaryDirectory(prefix="xiami-asset-session-") as temporary:
            data_dir = pathlib.Path(temporary)
            backend = protocol_probe._load_backend(data_dir)
            backend.USERS.clear()
            backend_session, client_session = protocol_probe._identity(
                backend, "asset_session_probe", "asset-session-device"
            )
            password = "NativeSession-%s" % secrets.token_hex(4)
            asset = protocol_probe._write_npc_fixture(
                data_dir, "persistent-session.pak", marker=b"PERSISTENT-ASSET-SESSION"
            )
            calls = {"issue": [], "consume": []}
            with NativeAssetWorkerBroker(str(executable), timeout=5.0) as broker:
                pid = broker.pid
                with protocol_probe._protocol_bridge(
                    backend, backend_session, client_session["device_id"], calls
                ):
                    result = native_core.authorize_npc_asset_read(
                        client_session,
                        asset,
                        "npc-resource",
                        -1,
                        password,
                        allow_local_http=True,
                        asset_broker=broker,
                    )
                assert result["file_sha256"] == hashlib.sha256(asset.read_bytes()).hexdigest()
                assert result["asset_handle"]
                assert result["worker_generation"] == broker.generation
                assert "resolved_password" not in result
                assert "header_password" not in result
                assert broker.pid == pid
                assert broker.stats()["sessions"] == 1
                broker.close_asset(result["asset_handle"], result["worker_generation"])
                assert broker.stats()["sessions"] == 0
                assert len(calls["issue"]) == 1 and len(calls["consume"]) == 1
        print("native asset authorization session probe: PASS")
        return 0
    finally:
        if old_path is None:
            os.environ.pop("XIAMI_NATIVE_CORE_PATH", None)
        else:
            os.environ["XIAMI_NATIVE_CORE_PATH"] = old_path


if __name__ == "__main__":
    raise SystemExit(main())

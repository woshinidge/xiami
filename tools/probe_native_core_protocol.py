from __future__ import annotations

import base64
import copy
import hashlib
import importlib.util
import json
import os
import pathlib
import secrets
import sqlite3
import struct
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager


ROOT = pathlib.Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT.parent / "服务器控制后台_绑定"
BACKEND_FILE = BACKEND_ROOT / "服务器控制后台_绑定.py"
NATIVE_EXE = ROOT / "build" / "native_core" / "xiami_native_core.exe"
REMOVED_NATIVE_OPERATIONS = (
    ("npc.visual.parse", "parse-summary", "parse_npc_summary"),
    ("spawn.visual.edit", "parse-document", "parse_spawn_document"),
    ("store.settings", "render-template", "render_store_template"),
)
NPC_JOB_FIELDS = frozenset(
    (
        "path_sha256",
        "file_name",
        "suffix",
        "file_sha256",
        "file_size",
        "magic",
        "purpose",
        "asset_index",
        "password_sha256",
    )
)
NATIVE_REQUEST_FIELDS = frozenset(
    (
        "schema_version",
        "feature",
        "operation",
        "operation_id",
        "client_version",
        "scope_sha256",
        "nonce",
        "device_key_id",
        "device_public_key",
    )
)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import toolbox_native_core as native_core
from toolbox_capabilities import load_capability_public_keys


def _load_backend(data_dir: pathlib.Path):
    os.environ["XIAMI_DATA_DIR"] = str(data_dir)
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))
    module_name = "xiami_native_probe_backend_" + secrets.token_hex(6)
    spec = importlib.util.spec_from_file_location(module_name, str(BACKEND_FILE))
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load backend module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _identity(backend, username: str, device_id: str):
    backend.USERS[username] = {
        "username": username,
        "role": "admin",
        "auth_version": 1,
        "toolbox_features": [],
    }
    backend_session = {
        "username": username,
        "role": "admin",
        "auth_version": 1,
        "transport": "tls",
        "app": "toolbox",
        "device_id": device_id,
        "device_bound_at_login": True,
    }
    client_session = {
        "username": username,
        "token": "probe-token-" + username,
        "device_id": device_id,
        "server": "http://127.0.0.1:1",
    }
    return backend_session, client_session


@contextmanager
def _protocol_bridge(
    backend,
    backend_session,
    device_id,
    calls,
    *,
    issue_mutator=None,
    consume_mutator=None,
):
    original_issue = native_core._request_lease
    original_consume = native_core._request_consume

    def issue(_session, request_payload, **_kwargs):
        request_copy = copy.deepcopy(dict(request_payload))
        response = backend._issue_native_lease(
            backend_session,
            request_copy,
            device_id,
            "127.0.0.1",
        )
        if issue_mutator is not None:
            response = issue_mutator(copy.deepcopy(response))
        calls["issue"].append({"request": request_copy, "response": copy.deepcopy(response)})
        return response

    def consume(_session, request_payload, **_kwargs):
        request_copy = copy.deepcopy(dict(request_payload))
        response, _rollback = backend._consume_native_lease(
            backend_session,
            request_copy,
            device_id,
        )
        if consume_mutator is not None:
            response = consume_mutator(copy.deepcopy(response))
        calls["consume"].append({"request": request_copy, "response": copy.deepcopy(response)})
        return response

    native_core._request_lease = issue
    native_core._request_consume = consume
    try:
        yield
    finally:
        native_core._request_lease = original_issue
        native_core._request_consume = original_consume


def _text(result, key):
    return result[key].decode("utf-8", errors="strict")


def _contains_plaintext(value, needle):
    if isinstance(value, dict):
        return any(
            _contains_plaintext(key, needle) or _contains_plaintext(item, needle)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple, set)):
        return any(_contains_plaintext(item, needle) for item in value)
    return isinstance(value, str) and str(needle) in value


def _check(records, name, condition):
    if not condition:
        raise AssertionError(name)
    records.append(name)


def _request(device_info, feature, operation, operation_id, scope_char):
    return {
        "schema_version": 2,
        "feature": feature,
        "operation": operation,
        "operation_id": operation_id,
        "client_version": native_core.DEFAULT_NATIVE_CLIENT_VERSION,
        "scope_sha256": scope_char * 64,
        "nonce": "native-probe-nonce-" + secrets.token_urlsafe(12),
        "device_key_id": device_info["key_id"],
        "device_public_key": device_info["public_key_b64"],
    }


def _alternate_public_key():
    public_key = next(iter(load_capability_public_keys().values()))
    modulus = int(public_key["n"])
    exponent = int(public_key["e"])
    modulus_raw = modulus.to_bytes(384, "big")
    exponent_raw = exponent.to_bytes((exponent.bit_length() + 7) // 8, "big")
    blob = (
        struct.pack("<6I", 0x31415352, 3072, len(exponent_raw), len(modulus_raw), 0, 0)
        + exponent_raw
        + modulus_raw
    )
    return {
        "key_id": hashlib.sha256(blob).hexdigest(),
        "public_key_b64": base64.b64encode(blob).decode("ascii"),
    }


def _flip_b64(value):
    raw = bytearray(base64.b64decode(value.encode("ascii"), validate=True))
    raw[len(raw) // 2] ^= 1
    result = base64.b64encode(raw).decode("ascii")
    for index in range(len(raw)):
        raw[index] = 0
    return result


def _expect_native_error(action, expected_code=None):
    try:
        action()
    except native_core.NativeCoreError as exc:
        if expected_code is not None and exc.code != expected_code:
            raise AssertionError("unexpected native error code: {}".format(exc.code))
        return exc.code
    raise AssertionError("native protocol failure was accepted")


def _run_tamper_case(backend, name, issue_mutator=None, consume_mutator=None):
    backend_session, client_session = _identity(backend, name, "device-" + name)
    calls = {"issue": [], "consume": []}
    processes = []
    with _protocol_bridge(
        backend,
        backend_session,
        client_session["device_id"],
        calls,
        issue_mutator=issue_mutator,
        consume_mutator=consume_mutator,
    ):
        code = _expect_native_error(
            lambda: native_core.parse_free_micro_text(
                client_session,
                "password=NativeTamper42!",
                allow_local_http=True,
                process_callback=lambda process: processes.append(process),
            )
        )
    assert processes and processes[-1] is None
    assert all(process.poll() is not None for process in processes if process is not None)
    return code, calls


def _npc_asset_metadata(path, purpose="npc-resource", asset_index=-1, password=""):
    path = pathlib.Path(path).resolve(strict=True)
    stat = path.stat()
    suffix = path.suffix.lower()
    return {
        "path_sha256": hashlib.sha256(str(path).encode("utf-8", errors="strict")).hexdigest(),
        "file_name": path.name,
        "suffix": suffix,
        "file_sha256": native_core._sha256_file(path),
        "file_size": int(stat.st_size),
        "magic": native_core._npc_asset_magic(path, suffix),
        "purpose": purpose,
        "asset_index": int(asset_index),
        "password_sha256": hashlib.sha256(
            str(password).encode("utf-8", errors="strict")
        ).hexdigest(),
    }


def _write_npc_fixture(root, name, marker=b"NPC-RAW-BYTES-CANARY"):
    path = pathlib.Path(root) / name
    path.write_bytes(b"PACK" + b"\x00" * 12 + bytes(marker) + b"\x00" * 19)
    return path.resolve()


def _start_boundary_password_holder(root):
    helper = pathlib.Path(root) / "native_boundary_holder.py"
    helper.write_text(
        """import ctypes
import sys
import time

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.VirtualAlloc.argtypes = (ctypes.c_void_p, ctypes.c_size_t, ctypes.c_ulong, ctypes.c_ulong)
kernel32.VirtualAlloc.restype = ctypes.c_void_p
size = 128 * 1024
address = kernel32.VirtualAlloc(None, size, 0x3000, 0x04)
if not address:
    raise OSError(ctypes.get_last_error(), "VirtualAlloc failed")
secret = bytes([78, 97, 116, 105, 118, 101, 66, 111, 117, 110, 100, 97, 114, 121, 52, 50, 33])
marker = bytes([48, 46, 48, 48, 66, 47, 115])
payload = secret + b" " + marker
offset = (64 * 1024) - 20
ctypes.memmove(address + offset, payload, len(payload))
sys.stdout.write("READY\\n")
sys.stdout.flush()
time.sleep(40)
""",
        encoding="utf-8",
    )
    base_executable = getattr(sys, "_base_executable", None) or sys.executable
    process = subprocess.Popen(
        [base_executable, "-B", str(helper)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    ready = process.stdout.readline().strip() if process.stdout is not None else ""
    if ready != "READY":
        stderr = process.stderr.read() if process.stderr is not None else ""
        process.kill()
        process.wait(timeout=5)
        raise RuntimeError("boundary holder failed: {}".format(stderr))
    return process


def _run_npc_file_tamper_case(backend, root, name, mutate_file):
    backend_session, client_session = _identity(backend, name, "device-" + name)
    path = _write_npc_fixture(root, name + ".pak")
    calls = {"issue": [], "consume": []}
    processes = []

    def mutate_after_issue(payload):
        mutate_file(path)
        return payload

    with _protocol_bridge(
        backend,
        backend_session,
        client_session["device_id"],
        calls,
        issue_mutator=mutate_after_issue,
    ):
        code = _expect_native_error(
            lambda: native_core.authorize_npc_asset_read(
                client_session,
                path,
                "npc-resource",
                -1,
                "NpcTamper42!",
                allow_local_http=True,
                process_callback=lambda process: processes.append(process),
            )
        )
    assert processes and processes[-1] is None
    assert all(process.poll() is not None for process in processes if process is not None)
    return code, calls


def _run_npc_password_binding_case(backend, root):
    name = "npc_password_binding"
    backend_session, client_session = _identity(backend, name, "device-" + name)
    path = _write_npc_fixture(root, name + ".pak")
    metadata = _npc_asset_metadata(path, password="metadata-password")
    job = dict(metadata, path=str(path), password="different-local-password")
    job["file_size"] = str(metadata["file_size"])
    job["asset_index"] = str(metadata["asset_index"])
    calls = {"issue": [], "consume": []}
    processes = []
    with _protocol_bridge(
        backend, backend_session, client_session["device_id"], calls
    ):
        code = _expect_native_error(
            lambda: native_core.run_native_core(
                client_session,
                native_core.NPC_ASSET_FEATURE,
                native_core.NPC_ASSET_AUTHORIZE_OPERATION,
                job,
                lease_context=metadata,
                allow_local_http=True,
                process_callback=lambda process: processes.append(process),
            )
        )
    assert processes and processes[-1] is None
    assert all(process.poll() is not None for process in processes if process is not None)
    return code, calls


def _direct_worker_tamper(backend, device_info, name, tamper):
    backend_session, client_session = _identity(backend, name, "device-" + name)
    feature = "free.micro.parse"
    operation = "parse-text"
    operation_id = "native_direct_{}_0001".format(name)
    job_block = native_core._encode_block_mutable(
        native_core.JOB_HEADER, {"text": "password=NativeDirect42!"}
    )
    scope_sha256 = hashlib.sha256(job_block).hexdigest()
    request = {
        "schema_version": 2,
        "feature": feature,
        "operation": operation,
        "operation_id": operation_id,
        "client_version": native_core.DEFAULT_NATIVE_CLIENT_VERSION,
        "scope_sha256": scope_sha256,
        "nonce": "native-direct-nonce-" + secrets.token_urlsafe(12),
        "device_key_id": device_info["key_id"],
        "device_public_key": device_info["public_key_b64"],
    }
    lease_payload = backend._issue_native_lease(
        backend_session, request, client_session["device_id"], "127.0.0.1"
    )
    lease = native_core._validate_lease(
        lease_payload,
        feature,
        operation,
        operation_id,
        scope_sha256,
        device_info["key_id"],
    )
    initial_payload = native_core._encode_block_mutable(
        native_core.LEASE_HEADER,
        {
            "schema_version": "2",
            "lease_id": lease["lease_id"],
            "operation_id": lease["operation_id"],
            "feature": lease["feature"],
            "operation": lease["operation"],
            "scope_sha256": lease["scope_sha256"],
            "expires_at": str(lease["expires_at"]),
            "key_id": lease["key_id"],
            "wrapped_key": lease["wrapped_key"],
            "nonce": lease["nonce"],
            "ciphertext": lease["ciphertext"],
            "tag": lease["tag"],
            "aad": lease["aad"],
        },
    )
    initial_payload.extend(job_block)
    native_core._wipe(job_block)

    process = None
    threads = []
    challenge_block = bytearray()
    challenge = bytearray()
    proof = bytearray()
    signature = bytearray()
    consume_block = bytearray()
    stdout = bytearray()
    stderr = bytearray()
    try:
        process = subprocess.Popen(
            [
                str(NATIVE_EXE),
                "--feature",
                feature,
                "--operation",
                operation,
                "--input",
                "-",
                "--output",
                "-",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            close_fds=True,
            bufsize=0,
        )
        deadline = time.monotonic() + 15.0
        native_core._write_pipe_with_deadline(
            process.stdin, initial_payload, deadline, threads
        )
        native_core._wipe(initial_payload)
        challenge_block = native_core._read_pipe_block_with_deadline(
            process.stdout, deadline, native_core.MAX_CHALLENGE_BLOCK_BYTES, threads
        )
        challenge_fields = native_core._decode_block(
            challenge_block,
            native_core.CHALLENGE_HEADER,
            max_bytes=native_core.MAX_CHALLENGE_BLOCK_BYTES,
        )
        challenge = native_core._validate_challenge(challenge_fields, lease)
        consume_request = {
            "schema_version": 1,
            "lease_id": lease["lease_id"],
            "operation_id": lease["operation_id"],
            "feature": lease["feature"],
            "operation": lease["operation"],
            "scope_sha256": lease["scope_sha256"],
            "key_id": lease["key_id"],
            "challenge": base64.b64encode(challenge).decode("ascii"),
        }
        consume_payload, _rollback = backend._consume_native_lease(
            backend_session, consume_request, client_session["device_id"]
        )
        consume = consume_payload["consume"]
        proof.extend(base64.b64decode(consume["proof"].encode("ascii"), validate=True))
        signature.extend(
            base64.b64decode(
                consume["server_signature"]["value"].encode("ascii"), validate=True
            )
        )
        signature_key_id = consume["server_signature"]["key_id"]
        if tamper == "proof":
            proof[len(proof) // 2] ^= 1
        elif tamper == "server_signature":
            signature[len(signature) // 2] ^= 1
        elif tamper == "server_signature_key_id":
            signature_key_id = "0000000000000000"
        else:
            raise AssertionError("unknown direct worker tamper")
        consume_block = native_core._encode_block_mutable(
            native_core.CONSUME_HEADER,
            {
                "schema_version": "1",
                "lease_id": lease["lease_id"],
                "challenge": challenge,
                "proof": proof,
                "server_signature_alg": consume["server_signature"]["alg"],
                "server_signature_key_id": signature_key_id,
                "server_signature": signature,
            },
        )
        native_core._write_pipe_with_deadline(
            process.stdin, consume_block, deadline, threads
        )
        native_core._wipe(consume_block)
        process.stdin.close()
        process.stdin = None
        raw_stdout, raw_stderr = process.communicate(timeout=native_core._remaining(deadline))
        stdout.extend(raw_stdout)
        stderr.extend(raw_stderr)
        return process.returncode, bytes(stderr).decode("ascii", errors="replace")
    finally:
        native_core._kill_and_wait(process)
        native_core._close_process_pipes(process)
        for thread in threads:
            thread.join(timeout=1.0)
        for buffer in (
            job_block,
            initial_payload,
            challenge_block,
            challenge,
            proof,
            signature,
            consume_block,
            stdout,
            stderr,
        ):
            native_core._wipe(buffer)
        for field in ("wrapped_key", "nonce", "ciphertext", "tag", "aad"):
            native_core._wipe(lease.get(field))


def _rollback_state(db_path, username, device_id, lease_id, operation_id, day, feature):
    connection = sqlite3.connect(str(db_path))
    try:
        binding = connection.execute(
            "SELECT COUNT(*) FROM native_device_keys WHERE username = ? AND device_id = ?",
            (username, device_id),
        ).fetchone()[0]
        lease = connection.execute(
            "SELECT COUNT(*) FROM native_leases WHERE lease_id = ?",
            (lease_id,),
        ).fetchone()[0]
        operation = connection.execute(
            "SELECT COUNT(*) FROM native_lease_operations WHERE username = ? AND operation_id = ?",
            (username, operation_id),
        ).fetchone()[0]
        daily = connection.execute(
            "SELECT used FROM native_lease_daily WHERE day_utc = ? AND username = ? AND feature = ?",
            (day, username, feature),
        ).fetchone()
        return {
            "binding": int(binding),
            "lease": int(lease),
            "operation": int(operation),
            "used": int(daily[0]) if daily else 0,
        }
    finally:
        connection.close()


def main() -> int:
    if not BACKEND_FILE.is_file():
        raise RuntimeError("backend source is missing: {}".format(BACKEND_FILE))
    if not NATIVE_EXE.is_file():
        raise RuntimeError("native core is missing: {}".format(NATIVE_EXE))

    records = []
    _check(
        records,
        "native_client_v3_keeps_lease_schema_v2",
        native_core.DEFAULT_NATIVE_CLIENT_VERSION == "toolbox-native-v3"
        and native_core.NATIVE_PROTOCOL_VERSION == "2",
    )
    old_native_path = os.environ.get("XIAMI_NATIVE_CORE_PATH")
    os.environ["XIAMI_NATIVE_CORE_PATH"] = str(NATIVE_EXE)
    try:
        with tempfile.TemporaryDirectory(prefix="xiami-native-v2-probe-") as temporary:
            data_dir = pathlib.Path(temporary)
            backend = _load_backend(data_dir)
            backend.USERS.clear()
            _check(
                records,
                "native_python_surface_removed_legacy_operations",
                all(
                    not hasattr(native_core, helper_name)
                    for _feature, _operation, helper_name in REMOVED_NATIVE_OPERATIONS
                ),
            )
            _check(
                records,
                "backend_native_surface_matches_hybrid_gate",
                backend._NATIVE_LEASE_OPERATIONS
                == {
                    "free.micro.parse": frozenset(("parse-text", "monitor-password")),
                    "npc.asset.decode": frozenset(("authorize-read",)),
                    "npc.tooltip.data": frozenset(("authorize-files",)),
                },
            )
            backend_session, client_session = _identity(
                backend, "native_probe", "native-probe-device"
            )
            device_one = native_core._query_native_device_key(
                str(NATIVE_EXE), time.monotonic() + 5.0, None
            )
            device_two = native_core._query_native_device_key(
                str(NATIVE_EXE), time.monotonic() + 5.0, None
            )
            _check(
                records,
                "device_key_v1_stable_and_hashed",
                device_one["key_id"] == device_two["key_id"]
                and device_one["public_key"] == device_two["public_key"]
                and device_one["key_id"] == hashlib.sha256(device_one["public_key"]).hexdigest()
                and len(device_one["public_key"]) == 411,
            )

            frozen_root = data_dir / "frozen-layout"
            frozen_native = frozen_root / "native" / "xiami_native_core.exe"
            frozen_native.parent.mkdir(parents=True)
            frozen_native.write_bytes(b"MZ-FROZEN-PROBE")
            malicious_native = data_dir / "malicious-native.exe"
            malicious_native.write_bytes(b"MZ-MALICIOUS-PROBE")
            missing = object()
            previous_frozen = getattr(sys, "frozen", missing)
            previous_meipass = getattr(sys, "_MEIPASS", missing)
            previous_override = os.environ.get("XIAMI_NATIVE_CORE_PATH")
            try:
                sys.frozen = True
                sys._MEIPASS = str(frozen_root)
                os.environ["XIAMI_NATIVE_CORE_PATH"] = str(malicious_native)
                resolved_native = pathlib.Path(native_core._native_core_path()).resolve()
                _check(
                    records,
                    "frozen_native_path_ignores_environment_override",
                    resolved_native == frozen_native.resolve(),
                )
            finally:
                if previous_frozen is missing:
                    delattr(sys, "frozen")
                else:
                    sys.frozen = previous_frozen
                if previous_meipass is missing:
                    delattr(sys, "_MEIPASS")
                else:
                    sys._MEIPASS = previous_meipass
                if previous_override is None:
                    os.environ.pop("XIAMI_NATIVE_CORE_PATH", None)
                else:
                    os.environ["XIAMI_NATIVE_CORE_PATH"] = previous_override

            calls = {"issue": [], "consume": []}
            process_events = []
            usage_seen = []
            results = []
            with _protocol_bridge(
                backend, backend_session, client_session["device_id"], calls
            ):
                free_result = native_core.parse_free_micro_text(
                    client_session,
                    "micro update endpoint key=Abc123!",
                    allow_local_http=True,
                    usage_callback=lambda usage: usage_seen.append(dict(usage)),
                    process_callback=lambda process: process_events.append(process),
                )
                results.append(free_result)
                _check(
                    records,
                    "free_micro_parse_v2",
                    _text(free_result, "role") == "micro"
                    and _text(free_result, "password") == "Abc123!",
                )

                holder_env = os.environ.copy()
                holder_env["XIAMI_NATIVE_PROBE_SECRET"] = "key expansion NativeProbe42! 0.00B/s"
                holder = subprocess.Popen(
                    [os.environ.get("ComSpec", "cmd.exe"), "/d", "/c", "ping -n 40 127.0.0.1 > nul"],
                    env=holder_env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                try:
                    time.sleep(0.25)
                    if holder.poll() is not None:
                        raise RuntimeError("native monitor probe holder exited before inspection")
                    monitor_result = native_core.monitor_free_micro_password(
                        client_session,
                        int(holder.pid),
                        "probe-holder.exe",
                        timeout_seconds=30,
                        allow_local_http=True,
                        process_callback=lambda process: process_events.append(process),
                    )
                    results.append(monitor_result)
                    monitor_ok = (
                        _text(monitor_result, "found") == "1"
                        and _text(monitor_result, "password") == "NativeProbe42!"
                    )
                    if not monitor_ok:
                        raise AssertionError("free_micro_monitor_v2 result: %r" % (monitor_result,))
                    _check(
                        records,
                        "free_micro_monitor_v2",
                        monitor_ok,
                    )
                finally:
                    if holder.poll() is None:
                        holder.kill()
                    holder.wait(timeout=5)

                boundary_backend_session, boundary_client_session = _identity(
                    backend, "native_boundary", "native-boundary-device"
                )
                boundary_holder = _start_boundary_password_holder(data_dir)
                try:
                    with _protocol_bridge(
                        backend,
                        boundary_backend_session,
                        boundary_client_session["device_id"],
                        {"issue": [], "consume": []},
                    ):
                        boundary_result = native_core.monitor_free_micro_password(
                            boundary_client_session,
                            int(boundary_holder.pid),
                            "probe-boundary-holder.exe",
                            timeout_seconds=30,
                            allow_local_http=True,
                            process_callback=lambda process: process_events.append(process),
                        )
                    results.append(boundary_result)
                    _check(
                        records,
                        "free_micro_monitor_cross_chunk_boundary",
                        _text(boundary_result, "found") == "1"
                        and _text(boundary_result, "password") == "NativeBoundary42!",
                    )
                finally:
                    if boundary_holder.poll() is None:
                        boundary_holder.kill()
                    boundary_holder.wait(timeout=5)

            _check(
                records,
                "v2_result_bindings",
                all(
                    _text(result, "schema_version") == "2"
                    and len(_text(result, "operation_id")) >= 16
                    and len(_text(result, "scope_sha256")) == 64
                    and _text(result, "key_id") == device_one["key_id"]
                    for result in results
                ),
            )
            _check(
                records,
                "lease_v2_device_binding_and_no_raw_key",
                len(calls["issue"]) == 2
                and all(call["request"]["schema_version"] == 2 for call in calls["issue"])
                and all(call["request"]["device_key_id"] == device_one["key_id"] for call in calls["issue"])
                and all(
                    base64.b64decode(call["request"]["device_public_key"].encode("ascii"), validate=True)
                    == device_one["public_key"]
                    for call in calls["issue"]
                )
                and all("key" not in call["response"]["lease"] for call in calls["issue"])
                and all("wrapped_key" in call["response"]["lease"] for call in calls["issue"]),
            )
            _check(
                records,
                "consume_v1_for_every_operation",
                len(calls["consume"]) == 2
                and all(call["request"]["schema_version"] == 1 for call in calls["consume"])
                and all(call["response"]["consume"]["proof_alg"] == "HMAC-SHA256" for call in calls["consume"])
                and all(call["response"]["consume"]["server_signature"]["alg"] == "RS256" for call in calls["consume"]),
            )
            _check(
                records,
                "usage_and_process_cleanup",
                usage_seen
                and usage_seen[-1]["used"] == 1
                and usage_seen[-1]["limit"] == 2
                and process_events
                and process_events[-1] is None
                and all(process.poll() is not None for process in process_events if process is not None),
            )

            npc_marker = "NPC-RAW-BYTES-CANARY-7f6e3a"
            npc_password = "NpcLocalPassword-8d11!"
            npc_path = _write_npc_fixture(
                data_dir,
                "npc-network-canary.pak",
                marker=npc_marker.encode("ascii"),
            )
            npc_calls = {"issue": [], "consume": []}
            npc_processes = []
            npc_usage = []
            with _protocol_bridge(
                backend, backend_session, client_session["device_id"], npc_calls
            ):
                npc_result = native_core.authorize_npc_asset_read(
                    client_session,
                    npc_path,
                    "npc-resource",
                    -1,
                    npc_password,
                    allow_local_http=True,
                    usage_callback=lambda usage: npc_usage.append(dict(usage)),
                    process_callback=lambda process: npc_processes.append(process),
                )
            _check(
                records,
                "npc_asset_authorize_read_v2",
                npc_result["path"] == npc_path
                and npc_result["file_sha256"] == hashlib.sha256(npc_path.read_bytes()).hexdigest()
                and npc_result["file_size"] == npc_path.stat().st_size
                and npc_result["magic"] == "GOMPACK"
                and npc_result["purpose"] == "npc-resource"
                and npc_result["asset_index"] == -1
                and npc_result["resolved_password"] == npc_password
                and npc_result["prefix_size"] == "0"
                and npc_result["data_base"] == 0
                and len(npc_result["authorization_id"]) == 64
                and npc_result["usage"]["limit"] == 0,
            )
            _check(
                records,
                "npc_asset_operation_consumed_and_cleaned",
                len(npc_calls["issue"]) == 1
                and len(npc_calls["consume"]) == 1
                and npc_usage
                and npc_usage[-1]["limit"] == 0
                and npc_processes
                and npc_processes[-1] is None
                and all(
                    process.poll() is not None
                    for process in npc_processes
                    if process is not None
                ),
            )
            npc_issue = npc_calls["issue"][0]
            npc_request = npc_issue["request"]
            _check(
                records,
                "npc_asset_network_job_schema_exact",
                set(npc_request) == set(NATIVE_REQUEST_FIELDS).union(("job",))
                and set(npc_request["job"]) == set(NPC_JOB_FIELDS)
                and npc_request["feature"] == "npc.asset.decode"
                and npc_request["operation"] == "authorize-read"
                and npc_request["job"]["asset_index"] == -1
                and npc_request["job"]["file_name"] == npc_path.name,
            )
            _check(
                records,
                "npc_asset_network_omits_raw_path_password_and_bytes",
                all(
                    not _contains_plaintext(container, secret)
                    for container in (npc_issue["request"], npc_issue["response"])
                    for secret in (str(npc_path), npc_password, npc_marker)
                ),
            )
            _check(
                records,
                "npc_asset_request_is_json_serializable_metadata_only",
                bool(json.dumps(npc_request, ensure_ascii=False, sort_keys=True))
                and "path" not in npc_request["job"]
                and "password" not in npc_request["job"],
            )

            denied_backend_session, _denied_client_session = _identity(
                backend, "npc_feature_denied", "device-npc-feature-denied"
            )
            denied_backend_session["role"] = "user"
            backend.USERS["npc_feature_denied"]["role"] = "user"
            denied_request = copy.deepcopy(npc_request)
            denied_request["operation_id"] = "npc_feature_denied_0001"
            denied_request["nonce"] = "npc-feature-denied-" + secrets.token_urlsafe(12)
            try:
                backend._issue_native_lease(
                    denied_backend_session,
                    denied_request,
                    denied_backend_session["device_id"],
                    "127.0.0.1",
                )
            except backend._NativeLeaseError as exc:
                _check(records, "npc_asset_without_entitlement_denied", exc.code == "feature_denied")
            else:
                raise AssertionError("NPC asset lease was issued without entitlement")

            pair_paths = []
            for suffix in (".wil", ".wix"):
                pair_path = (data_dir / ("NpcPair" + suffix)).resolve()
                pair_path.write_bytes(("PAIR" + suffix).encode("ascii"))
                pair_paths.append(pair_path)
            pair_calls = {"issue": [], "consume": []}
            with _protocol_bridge(
                backend, backend_session, client_session["device_id"], pair_calls
            ):
                pair_results = [
                    native_core.authorize_npc_asset_read(
                        client_session,
                        pair_path,
                        "npc-item",
                        -1,
                        "",
                        allow_local_http=True,
                    )
                    for pair_path in pair_paths
                ]
            _check(
                records,
                "npc_wil_index_pair_authorized_independently",
                len(pair_calls["issue"]) == 2
                and len(pair_calls["consume"]) == 2
                and all(result["magic"] == "WIL" for result in pair_results)
                and {call["request"]["job"]["suffix"] for call in pair_calls["issue"]}
                == {".wil", ".wix"}
                and all(
                    call["request"]["job"]["asset_index"] == -1
                    for call in pair_calls["issue"]
                ),
            )

            d3dm2_profile = backend._native_npc_asset_decode_parameters(
                {
                    "magic": "D3DM2",
                    "password_sha256": hashlib.sha256(b"").hexdigest(),
                }
            )
            d3dm2_path = (data_dir / "NpcD3dm2Probe.pak").resolve()
            d3dm2_path.write_bytes(b"D3DM2" + b"\x00" * 64)
            d3dm2_calls = {"issue": [], "consume": []}
            with _protocol_bridge(
                backend, backend_session, client_session["device_id"], d3dm2_calls
            ):
                d3dm2_result = native_core.authorize_npc_asset_read(
                    client_session,
                    d3dm2_path,
                    "npc-resource",
                    -1,
                    "",
                    allow_local_http=True,
                )
            _check(
                records,
                "npc_d3dm2_profile_uses_data_base_262",
                d3dm2_profile["prefix_size"] == "5"
                and d3dm2_profile["data_base"] == "262"
                and d3dm2_result["magic"] == "D3DM2"
                and d3dm2_result["prefix_size"] == "5"
                and d3dm2_result["data_base"] == 262
                and d3dm2_result["format_version"] == "d3dm2-v1"
                and len(d3dm2_calls["issue"]) == 1
                and len(d3dm2_calls["consume"]) == 1,
            )

            geepak2_password = "stream-pass"
            geepak2_profile = backend._native_npc_asset_decode_parameters(
                {
                    "magic": "GEEPAK2",
                    "password_sha256": hashlib.sha256(
                        geepak2_password.encode("ascii")
                    ).hexdigest(),
                }
            )
            geepak2_path = (data_dir / "NpcGeePak2Probe.pak").resolve()
            geepak2_path.write_bytes(b"\x07GEEPAK2" + b"\x00" * 64)
            geepak2_calls = {"issue": [], "consume": []}
            with _protocol_bridge(
                backend, backend_session, client_session["device_id"], geepak2_calls
            ):
                geepak2_result = native_core.authorize_npc_asset_read(
                    client_session,
                    geepak2_path,
                    "npc-resource",
                    -1,
                    geepak2_password,
                    allow_local_http=True,
                )
            _check(
                records,
                "npc_geepak2_profile_separates_header_and_stream_passwords",
                geepak2_profile["header_password"] == "bandao"
                and geepak2_result["magic"] == "GEEPAK2"
                and geepak2_result["resolved_password"] == geepak2_password
                and geepak2_result["header_password"] == "bandao"
                and geepak2_result["prefix_size"] == "10"
                and geepak2_result["data_base"] == 266
                and geepak2_result["allowed_index_modes"] == "0,1,2"
                and geepak2_result["format_version"] == "geepak2-v1"
                and len(geepak2_calls["issue"]) == 1
                and len(geepak2_calls["consume"]) == 1,
            )

            geem2lp_password = "QQ4283164"
            geem2lp_profile = backend._native_npc_asset_decode_parameters(
                {
                    "magic": "GEEM2LP",
                    "password_sha256": hashlib.sha256(
                        geem2lp_password.encode("ascii")
                    ).hexdigest(),
                }
            )
            geem2lp_path = (data_dir / "NpcGeem2LengthPrefixedProbe.pak").resolve()
            geem2lp_path.write_bytes(b"\x05GEEM2" + b"\x00" * 64)
            geem2lp_calls = {"issue": [], "consume": []}
            with _protocol_bridge(
                backend, backend_session, client_session["device_id"], geem2lp_calls
            ):
                geem2lp_result = native_core.authorize_npc_asset_read(
                    client_session,
                    geem2lp_path,
                    "npc-resource",
                    -1,
                    geem2lp_password,
                    allow_local_http=True,
                )
            _check(
                records,
                "npc_geem2lp_profile_uses_iv60_layout",
                geem2lp_profile["prefix_size"] == "10"
                and geem2lp_profile["data_base"] == "266"
                and geem2lp_profile["allowed_index_modes"] == "2"
                and geem2lp_profile["format_version"] == "geem2lp-v1"
                and geem2lp_result["magic"] == "GEEM2LP"
                and geem2lp_result["prefix_size"] == "10"
                and geem2lp_result["data_base"] == 266
                and geem2lp_result["format_version"] == "geem2lp-v1"
                and len(geem2lp_calls["issue"]) == 1
                and len(geem2lp_calls["consume"]) == 1,
            )

            def mutate_content(path):
                raw = bytearray(path.read_bytes())
                raw[-1] ^= 1
                path.write_bytes(raw)

            def mutate_size(path):
                path.write_bytes(path.read_bytes() + b"X")

            def mutate_magic(path):
                raw = bytearray(path.read_bytes())
                raw[:4] = b"NOPE"
                path.write_bytes(raw)

            def mutate_path(path):
                path.rename(path.with_name(path.stem + "-moved" + path.suffix))

            for case_name, mutator in (
                ("npc_content_after_issue", mutate_content),
                ("npc_size_after_issue", mutate_size),
                ("npc_magic_after_issue", mutate_magic),
                ("npc_path_after_issue", mutate_path),
            ):
                code, tamper_calls = _run_npc_file_tamper_case(
                    backend, data_dir, case_name, mutator
                )
                _check(
                    records,
                    case_name + "_rejected",
                    bool(code)
                    and len(tamper_calls["issue"]) == 1
                    and len(tamper_calls["consume"]) <= 1,
                )

            password_code, password_calls = _run_npc_password_binding_case(
                backend, data_dir
            )
            _check(
                records,
                "npc_password_binding_mismatch_rejected",
                bool(password_code)
                and len(password_calls["issue"]) == 1
                and len(password_calls["consume"]) <= 1,
            )

            for index, (feature, operation, _helper_name) in enumerate(
                REMOVED_NATIVE_OPERATIONS, 1
            ):
                removed_request = _request(
                    device_one,
                    feature,
                    operation,
                    "native_removed_{:02d}_0001".format(index),
                    "f",
                )
                try:
                    backend._issue_native_lease(
                        backend_session,
                        removed_request,
                        client_session["device_id"],
                        "127.0.0.1",
                    )
                except backend._NativeLeaseError as exc:
                    _check(
                        records,
                        "{}_native_operation_unsupported".format(feature),
                        exc.code == "native_feature_unknown",
                    )
                else:
                    raise AssertionError("removed native feature was accepted: {}".format(feature))

            alternate = _alternate_public_key()
            conflict_request = _request(
                alternate,
                "free.micro.parse",
                "parse-text",
                "native_key_conflict_0001",
                "a",
            )
            try:
                backend._issue_native_lease(
                    backend_session,
                    conflict_request,
                    client_session["device_id"],
                    "127.0.0.1",
                )
            except backend._NativeLeaseError as exc:
                _check(records, "device_key_conflict_rejected", exc.code == "native_device_key_changed")
            else:
                raise AssertionError("device key conflict was accepted")

            replay_backend_session, replay_client_session = _identity(
                backend, "replay_probe", "device-replay-probe"
            )
            replay_request = _request(
                device_one,
                "free.micro.parse",
                "parse-text",
                "native_operation_replay_0001",
                "b",
            )
            backend._issue_native_lease(
                replay_backend_session,
                replay_request,
                replay_client_session["device_id"],
                "127.0.0.1",
            )
            try:
                backend._issue_native_lease(
                    replay_backend_session,
                    replay_request,
                    replay_client_session["device_id"],
                    "127.0.0.1",
                )
            except backend._NativeLeaseError as exc:
                _check(records, "operation_replay_rejected", exc.code == "native_lease_replay")
            else:
                raise AssertionError("operation replay was accepted")

            consumed_request = copy.deepcopy(calls["consume"][0]["request"])
            try:
                backend._consume_native_lease(
                    backend_session, consumed_request, client_session["device_id"]
                )
            except backend._NativeLeaseError as exc:
                _check(records, "consume_replay_rejected", exc.code == "native_lease_replay")
            else:
                raise AssertionError("consume replay was accepted")

            wrapped_code, wrapped_calls = _run_tamper_case(
                backend,
                "wrapped_tamper",
                issue_mutator=lambda payload: (
                    payload["lease"].__setitem__(
                        "wrapped_key", _flip_b64(payload["lease"]["wrapped_key"])
                    )
                    or payload
                ),
            )
            _check(
                records,
                "wrapped_key_tamper_rejected",
                bool(wrapped_code)
                and wrapped_calls["issue"]
                and not wrapped_calls["consume"],
            )

            proof_code, _proof_calls = _run_tamper_case(
                backend,
                "proof_tamper",
                consume_mutator=lambda payload: (
                    payload["consume"].__setitem__(
                        "proof", _flip_b64(payload["consume"]["proof"])
                    )
                    or payload
                ),
            )
            _check(records, "proof_tamper_rejected", proof_code == "invalid_server_signature")

            signature_code, _signature_calls = _run_tamper_case(
                backend,
                "signature_tamper",
                consume_mutator=lambda payload: (
                    payload["consume"]["server_signature"].__setitem__(
                        "value", _flip_b64(payload["consume"]["server_signature"]["value"])
                    )
                    or payload
                ),
            )
            _check(
                records,
                "server_signature_tamper_rejected",
                signature_code == "invalid_server_signature",
            )

            unknown_key_code, _unknown_key_calls = _run_tamper_case(
                backend,
                "unknown_signer",
                consume_mutator=lambda payload: (
                    payload["consume"]["server_signature"].__setitem__(
                        "key_id", "0000000000000000"
                    )
                    or payload
                ),
            )
            _check(
                records,
                "unknown_server_signature_key_rejected",
                unknown_key_code == "invalid_server_signature",
            )

            for name, tamper, expected_error in (
                ("direct_proof", "proof", "consume proof verification failed"),
                (
                    "direct_signature",
                    "server_signature",
                    "server signature verification failed",
                ),
                (
                    "direct_signer",
                    "server_signature_key_id",
                    "server signature identity is invalid",
                ),
            ):
                exit_code, stderr_text = _direct_worker_tamper(
                    backend, device_one, name, tamper
                )
                _check(
                    records,
                    "native_{}_rejected".format(name),
                    exit_code == 2 and expected_error in stderr_text,
                )

            rollback_username = "rollback_probe"
            rollback_device_id = "device-rollback-probe"
            rollback_backend_session, _rollback_client_session = _identity(
                backend, rollback_username, rollback_device_id
            )
            rollback_operation_id = "native_issue_rollback_0001"
            rollback_request = _request(
                device_one,
                "free.micro.parse",
                "parse-text",
                rollback_operation_id,
                "d",
            )
            rollback_payload = backend._issue_native_lease(
                rollback_backend_session,
                rollback_request,
                rollback_device_id,
                "127.0.0.1",
            )
            rollback_lease_id = rollback_payload["lease"]["lease_id"]
            rollback_day = rollback_payload["usage"]["day_utc"]
            rollback_db = pathlib.Path(backend.NATIVE_LEASE_DB_FILE)
            rollback_before = _rollback_state(
                rollback_db,
                rollback_username,
                rollback_device_id,
                rollback_lease_id,
                rollback_operation_id,
                rollback_day,
                rollback_request["feature"],
            )
            _check(
                records,
                "native_issue_rollback_state_created",
                rollback_before
                == {"binding": 1, "lease": 1, "operation": 1, "used": 1},
            )
            rollback_ok = backend._rollback_native_lease_quota(
                rollback_username,
                rollback_request["feature"],
                rollback_operation_id,
                rollback_day,
                rollback_lease_id,
            )
            rollback_after = _rollback_state(
                rollback_db,
                rollback_username,
                rollback_device_id,
                rollback_lease_id,
                rollback_operation_id,
                rollback_day,
                rollback_request["feature"],
            )
            _check(
                records,
                "native_issue_rollback_removes_all_state",
                rollback_ok
                and rollback_after
                == {"binding": 0, "lease": 0, "operation": 0, "used": 0},
            )

            reloaded = _load_backend(data_dir)
            reloaded.USERS.clear()
            for username in ("native_probe", "replay_probe"):
                reloaded.USERS[username] = dict(backend.USERS[username])
            try:
                reloaded._issue_native_lease(
                    replay_backend_session,
                    replay_request,
                    replay_client_session["device_id"],
                    "127.0.0.1",
                )
            except reloaded._NativeLeaseError as exc:
                _check(records, "operation_replay_persists_after_reload", exc.code == "native_lease_replay")
            else:
                raise AssertionError("operation replay state reset after reload")
            try:
                reloaded._consume_native_lease(
                    backend_session, consumed_request, client_session["device_id"]
                )
            except reloaded._NativeLeaseError as exc:
                _check(records, "consume_replay_persists_after_reload", exc.code == "native_lease_replay")
            else:
                raise AssertionError("consume replay state reset after reload")

            quota_request = _request(
                device_one,
                "free.micro.parse",
                "parse-text",
                "native_daily_persist_0001",
                "c",
            )
            try:
                reloaded._issue_native_lease(
                    backend_session,
                    quota_request,
                    client_session["device_id"],
                    "127.0.0.1",
                )
            except reloaded._NativeLeaseError as exc:
                _check(records, "free_micro_daily_limit_persists_after_reload", exc.code == "native_lease_daily_limit")
            else:
                raise AssertionError("free micro daily limit reset after reload")

            persisted_db = pathlib.Path(reloaded.NATIVE_LEASE_DB_FILE)
            connection = sqlite3.connect(str(persisted_db))
            try:
                persisted_features = {
                    row[0]
                    for row in connection.execute(
                        "SELECT feature FROM native_lease_operations "
                        "UNION SELECT feature FROM native_leases "
                        "UNION SELECT feature FROM native_lease_daily"
                    )
                }
            finally:
                connection.close()
            _check(
                records,
                "native_state_contains_only_supported_hybrid_features",
                persisted_features == {"free.micro.parse", "npc.asset.decode"},
            )
            _check(
                records,
                "v2_sqlite_state_persisted",
                (data_dir / "native_lease_usage.sqlite3").is_file(),
            )

        print("native core V2 protocol probe: {0}/{0} passed".format(len(records)))
        return 0
    finally:
        if old_native_path is None:
            os.environ.pop("XIAMI_NATIVE_CORE_PATH", None)
        else:
            os.environ["XIAMI_NATIVE_CORE_PATH"] = old_native_path


if __name__ == "__main__":
    raise SystemExit(main())

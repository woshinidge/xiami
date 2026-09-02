from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import toolbox_capabilities as capability
import toolbox_backend_tls as backend_tls
import toolbox_core_rpc as core_rpc
from embedded_npc_visual.core.npc_visual_v2.rpc_codec import npc_document_from_rpc


DEFAULT_BACKEND_SOURCE = ROOT.parent / "服务器控制后台_绑定" / "服务器控制后台_绑定.py"
DEFAULT_OPENSSL = Path(
    shutil.which("openssl") or r"C:\Program Files\Git\usr\bin\openssl.exe"
)


def _run_openssl(openssl: Path, *arguments: str) -> None:
    subprocess.run(
        [str(openssl)] + list(arguments),
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _generate_rsa_key(openssl: Path, key_path: Path) -> None:
    _run_openssl(
        openssl,
        "genpkey",
        "-algorithm",
        "RSA",
        "-pkeyopt",
        "rsa_keygen_bits:2048",
        "-out",
        str(key_path),
    )


def _generate_probe_ca(openssl: Path, key_path: Path, cert_path: Path, common_name: str) -> None:
    _generate_rsa_key(openssl, key_path)
    _run_openssl(
        openssl,
        "req",
        "-new",
        "-x509",
        "-key",
        str(key_path),
        "-sha256",
        "-days",
        "1",
        "-subj",
        "/CN={}".format(common_name),
        "-addext",
        "basicConstraints=critical,CA:TRUE",
        "-addext",
        "keyUsage=critical,keyCertSign,cRLSign",
        "-out",
        str(cert_path),
    )


def _generate_probe_tls_material(
    openssl: Path,
    ca_key_path: Path,
    ca_cert_path: Path,
    server_key_path: Path,
    server_cert_path: Path,
    temp_dir: Path,
) -> None:
    _generate_probe_ca(openssl, ca_key_path, ca_cert_path, "Xiami RPC Integration Root")
    server_csr_path = temp_dir / "tls-server.csr"
    server_extensions_path = temp_dir / "tls-server.ext"
    server_extensions_path.write_text(
        "\n".join(
            (
                "basicConstraints=critical,CA:FALSE",
                "keyUsage=critical,digitalSignature,keyEncipherment",
                "extendedKeyUsage=serverAuth",
                "subjectAltName=IP:127.0.0.1",
                "",
            )
        ),
        encoding="ascii",
    )
    _generate_rsa_key(openssl, server_key_path)
    _run_openssl(
        openssl,
        "req",
        "-new",
        "-key",
        str(server_key_path),
        "-subj",
        "/CN=127.0.0.1",
        "-out",
        str(server_csr_path),
    )
    _run_openssl(
        openssl,
        "x509",
        "-req",
        "-in",
        str(server_csr_path),
        "-CA",
        str(ca_cert_path),
        "-CAkey",
        str(ca_key_path),
        "-CAcreateserial",
        "-days",
        "1",
        "-sha256",
        "-extfile",
        str(server_extensions_path),
        "-out",
        str(server_cert_path),
    )


def _load_backend(source: Path):
    backend_dir = str(source.resolve().parent)
    inserted = backend_dir not in sys.path
    if inserted:
        sys.path.insert(0, backend_dir)
    spec = importlib.util.spec_from_file_location("xiami_rpc_integration_backend", str(source))
    if spec is None or spec.loader is None:
        raise RuntimeError("backend module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    finally:
        if inserted:
            sys.path.remove(backend_dir)
    return module


def _set_probe_ca(pem: str) -> None:
    backend_tls.PINNED_BACKEND_CA_PEM = pem
    backend_tls._PINNED_CONTEXT = None


def _expect_tls_rejection(session: dict, public_keys: dict, label: str) -> None:
    try:
        core_rpc.encrypt_micro_pak_passwords(
            session=session,
            passwords=["tls-negative"],
            client_version="1.3.8",
            public_keys=public_keys,
        )
    except core_rpc.CoreRpcTransportError as exc:
        if exc.code != "network_error":
            raise AssertionError("{} returned unexpected error: {}".format(label, exc.code))
    else:
        raise AssertionError("{} was accepted".format(label))


def _assert_encoded_shape(passwords, encoded) -> None:
    if not isinstance(encoded, list) or len(encoded) != len(passwords):
        raise AssertionError("encoded result count mismatch")
    for password, value in zip(passwords, encoded):
        if password == "":
            if value != "":
                raise AssertionError("empty password result mismatch")
            continue
        raw_length = len(password.encode("gbk", errors="replace"))
        if len(value) != 2 * (raw_length + 1):
            raise AssertionError("encoded result length mismatch")
        if value.upper() != value or any(ch not in "0123456789ABCDEF" for ch in value):
            raise AssertionError("encoded result is not uppercase hexadecimal")
        if value.startswith("00"):
            raise AssertionError("encoded seed must be non-zero")


def run_probe(backend_source: Path, openssl: Path) -> None:
    if not backend_source.is_file():
        raise FileNotFoundError("backend source not found: {}".format(backend_source))
    if not openssl.is_file():
        raise FileNotFoundError("OpenSSL not found: {}".format(openssl))

    environment_names = (
        "XIAMI_DATA_DIR",
        "XIAMI_ADMIN_PASSWORD",
        "XIAMI_PBKDF2_ITERATIONS",
        "XIAMI_CAPABILITY_PRIVATE_KEY_FILE",
        "XIAMI_CAPABILITY_KEY_ID",
        "XIAMI_RPC_AUDIT_PEPPER",
    )
    old_environment = {name: os.environ.get(name) for name in environment_names}
    old_pinned_ca = backend_tls.PINNED_BACKEND_CA_PEM
    old_pinned_context = backend_tls._PINNED_CONTEXT
    server = None
    server_thread = None

    with tempfile.TemporaryDirectory(prefix="xiami_rpc_integration_") as temp_name:
        temp_dir = Path(temp_name)
        capability_key_path = temp_dir / "capability.pem"
        tls_ca_key_path = temp_dir / "tls-ca.key"
        tls_ca_cert_path = temp_dir / "tls-ca.pem"
        tls_server_key_path = temp_dir / "tls-server.key"
        tls_server_cert_path = temp_dir / "tls-server.pem"
        wrong_ca_key_path = temp_dir / "wrong-ca.key"
        wrong_ca_cert_path = temp_dir / "wrong-ca.pem"
        _generate_rsa_key(openssl, capability_key_path)
        _generate_probe_tls_material(
            openssl,
            tls_ca_key_path,
            tls_ca_cert_path,
            tls_server_key_path,
            tls_server_cert_path,
            temp_dir,
        )
        _generate_probe_ca(
            openssl,
            wrong_ca_key_path,
            wrong_ca_cert_path,
            "Xiami RPC Integration Wrong Root",
        )
        os.environ["XIAMI_DATA_DIR"] = str(temp_dir / "data")
        os.environ["XIAMI_ADMIN_PASSWORD"] = "Integration-Probe-Admin-Only"
        os.environ["XIAMI_PBKDF2_ITERATIONS"] = "100000"
        os.environ["XIAMI_CAPABILITY_PRIVATE_KEY_FILE"] = str(capability_key_path)
        os.environ["XIAMI_CAPABILITY_KEY_ID"] = "integration-capability-2026"
        os.environ["XIAMI_RPC_AUDIT_PEPPER"] = "integration-probe-pepper-not-for-production-2026"

        try:
            backend = _load_backend(backend_source)
            feature = backend.MICRO_PAK_RPC_FEATURE
            username = "rpc-integration@example.com"
            device_id = "rpc-integration-device-001"
            user = {
                "role": "user",
                "auth_version": 0,
                "expire_ts": int(time.time()) + 3600,
                "toolbox_features": [
                    feature,
                    backend.STORE_RENDER_RPC_FEATURE,
                    backend.SPAWN_PARSE_RPC_FEATURE,
                    backend.NPC_PARSE_RPC_FEATURE,
                ],
            }
            backend._set_user_password(user, "integration-probe-password")
            backend.USERS[username] = user
            backend._save_users(backend.USERS)
            token = backend._make_token(
                username,
                "user",
                "toolbox",
                "127.0.0.1",
                device_id=device_id,
                audience="public",
                transport="tls",
            )

            tls_context = backend._build_tls_context(
                str(tls_server_cert_path),
                str(tls_server_key_path),
            )
            server = backend.RoleThreadingHTTPServer(
                ("127.0.0.1", 0),
                backend.Handler,
                listener_role="tls_api",
                tls_context=tls_context,
            )
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()

            modulus, _private_exponent = backend._rsa_private_numbers_from_pem(
                capability_key_path.read_text(encoding="ascii")
            )
            public_keys = {
                "integration-capability-2026": {
                    "n": "0x" + format(modulus, "x"),
                    "e": 65537,
                }
            }
            session = {
                "server": "https://127.0.0.1:{}".format(server.server_port),
                "token": token,
                "username": username,
                "device_id": device_id,
            }

            _set_probe_ca(wrong_ca_cert_path.read_text(encoding="ascii"))
            _expect_tls_rejection(session, public_keys, "untrusted TLS root")
            _set_probe_ca(tls_ca_cert_path.read_text(encoding="ascii"))
            wrong_hostname_session = dict(session)
            wrong_hostname_session["server"] = "https://localhost:{}".format(server.server_port)
            _expect_tls_rejection(wrong_hostname_session, public_keys, "TLS hostname mismatch")

            passwords = ["密码", "", "A1-测试"]
            shape_operation_id = "rpc-integration-shape-20260723"
            encoded = core_rpc.encrypt_micro_pak_passwords(
                session=session,
                passwords=passwords,
                client_version="1.3.8",
                operation_id=shape_operation_id,
                public_keys=public_keys,
            )
            _assert_encoded_shape(passwords, encoded)

            # Keep the UpdateServer compatibility oracle on the real backend
            # path; shape-only assertions cannot catch an algorithm drift.
            known_password = "破解的人生儿子没有PY"
            vector_operation_id = "rpc-integration-vector-20260723"
            with mock.patch.object(backend.secrets, "randbelow", return_value=254):
                known_encoded = core_rpc.encrypt_micro_pak_passwords(
                    session=session,
                    passwords=[known_password],
                    client_version="1.3.8",
                    operation_id=vector_operation_id,
                    public_keys=public_keys,
                )
            expected_known_encoded = "FF850488259B23A326A1DDD799384247405C64FA15"
            if known_encoded != [expected_known_encoded]:
                raise AssertionError(
                    "real backend PAK compatibility vector changed: {}".format(known_encoded)
                )

            store_config = {
                "feature_folder": "虾米存销功能",
                "category_folder": "虾米物品分类",
                "script_name": "虾米仓库",
                "method_name": "打开虾米仓库",
                "common_folder": "虾米通区",
                "zone_name": "ZoneA",
                "store_u_var": "U335",
                "teleport_condition": "LARGE U599 777",
                "timer_id": 63,
                "qr_trigger": 208,
                "resource_number": 21,
                "qr_method": "虾米掉落检测",
                "filter_tip": "RPC过滤",
                "store_tip": "RPC存储",
                "target_scope_sha256": hashlib.sha256(b"integration-store-target").hexdigest(),
            }
            store_result = core_rpc.render_store_bundle_rpc(
                session,
                store_config,
                "1.3.8",
                operation_id="rpc-integration-store-20260724",
                public_keys=public_keys,
            )
            artifacts = store_result.get("artifacts")
            if not isinstance(artifacts, dict) or tuple(artifacts) != core_rpc.STORE_BUNDLE_ROLES:
                raise AssertionError("store RPC returned an invalid seven-role bundle")
            main_content = artifacts["feature.filter_main"]["content"]
            if "N$仓库刷新标记" not in main_content:
                raise AssertionError("store RPC did not return the finalized server template")
            if "ZoneA" not in main_content or "虾米通区" not in main_content:
                raise AssertionError("store RPC did not bind main-template path config")
            if "LARGE U599 777" not in main_content or "SetOnTimer 63" not in main_content:
                raise AssertionError("store RPC main-template config changed unexpectedly")
            if "ADDBUTTON <$STR(N$虾米资源编号)> 208" not in artifacts["owned.qmanage_login"]["content"]:
                raise AssertionError("store RPC did not bind QR trigger")
            if "mov N$虾米资源编号 20" not in artifacts["owned.qmanage_login"]["content"]:
                raise AssertionError("store RPC did not bind resource number")
            qfunction_content = artifacts["owned.qfunction_main"]["content"]
            if "RPC过滤" not in qfunction_content or "RPC存储" not in qfunction_content:
                raise AssertionError("store RPC did not bind QFunction tips")
            expected_config_sha = hashlib.sha256(
                core_rpc.canonical_rpc_json(store_config)
            ).hexdigest()
            if store_result.get("config_sha256") != expected_config_sha:
                raise AssertionError("store RPC config identity mismatch")
            if store_result.get("target_scope_sha256") != store_config["target_scope_sha256"]:
                raise AssertionError("store RPC target identity mismatch")

            spawn_text = (
                "; comment\r\n"
                "B01 001 2 鸡 3 4 5 255\r\n"
                "invalid row\r\n"
            )
            spawn_result = core_rpc.parse_spawn_document_rpc(
                session,
                spawn_text,
                "1.3.8",
                target_scope_sha256=hashlib.sha256(b"integration-spawn-target").hexdigest(),
                expected_pre_sha256=hashlib.sha256(spawn_text.encode("utf-8")).hexdigest(),
                operation_id="rpc-integration-spawn-20260724",
                public_keys=public_keys,
            )
            if spawn_result.get("accepted") != 1 or spawn_result.get("rejected") != 1:
                raise AssertionError("spawn RPC counts changed: {}".format(spawn_result))
            spawn_record = spawn_result["records"][0]
            if spawn_record["fields"] != ["B01", "001", "2", "鸡", "3", "4", "5", "255"]:
                raise AssertionError("spawn RPC fields changed")

            npc_source = "[@main]\n#SAY\n你好<关闭/@exit>\\\n#ACT\nBREAK\n"
            npc_payload = core_rpc.parse_npc_document_rpc(
                session,
                npc_source,
                "1.3.8",
                target_scope_sha256=hashlib.sha256(b"integration-npc-target").hexdigest(),
                expected_pre_sha256=hashlib.sha256(npc_source.encode("utf-8")).hexdigest(),
                operation_id="rpc-integration-npc-20260724",
                public_keys=public_keys,
            )
            npc_document = npc_document_from_rpc(
                npc_payload,
                npc_source,
                r"C:\probe\Market_Def\npc.txt",
            )
            if npc_document.label_names() != ["@main"]:
                raise AssertionError("NPC RPC labels changed")
            if not npc_document.labels[0].say_blocks:
                raise AssertionError("NPC RPC returned no SAY block")

            denied_username = "rpc-denied@example.com"
            denied_device_id = "rpc-integration-device-002"
            denied_user = {
                "role": "user",
                "auth_version": 0,
                "expire_ts": int(time.time()) + 3600,
                "toolbox_features": [],
            }
            backend._set_user_password(denied_user, "integration-probe-password")
            backend.USERS[denied_username] = denied_user
            denied_token = backend._make_token(
                denied_username,
                "user",
                "toolbox",
                "127.0.0.1",
                device_id=denied_device_id,
                audience="public",
                transport="tls",
            )
            denied_session = {
                "server": session["server"],
                "token": denied_token,
                "username": denied_username,
                "device_id": denied_device_id,
            }
            try:
                core_rpc.encrypt_micro_pak_passwords(
                    session=denied_session,
                    passwords=["denied"],
                    client_version="1.3.8",
                    public_keys=public_keys,
                )
            except core_rpc.CoreRpcAuthorizationError as exc:
                if exc.http_status != 403:
                    raise AssertionError("default-deny returned unexpected status")
            else:
                raise AssertionError("unentitled user was allowed")

            audit_files = list((temp_dir / "data" / "audit").glob("toolbox_rpc-*.jsonl"))
            if len(audit_files) != 1:
                raise AssertionError("RPC audit file was not created")
            audit_text = audit_files[0].read_text(encoding="utf-8")
            audit_records = [json.loads(line) for line in audit_text.splitlines() if line.strip()]
            if not any(record.get("status") == 200 for record in audit_records):
                raise AssertionError("successful RPC audit record is missing")
            expected_audit_fields = {
                "utc",
                "request_id",
                "event",
                "user_hash",
                "device_hash",
                "ip_hash",
                "feature",
                "jti_hash",
                "operation_hash",
                "request_sha256",
                "input_count",
                "output_count",
                "status",
                "duration_ms",
                "reject_code",
                "server_version",
            }
            for record in audit_records:
                if set(record) != expected_audit_fields:
                    raise AssertionError("RPC audit field set changed")
                for field in (
                    "user_hash",
                    "device_hash",
                    "ip_hash",
                    "jti_hash",
                    "operation_hash",
                    "request_sha256",
                ):
                    value = record[field]
                    if value and (
                        len(value) != 64
                        or any(character not in "0123456789abcdef" for character in value)
                    ):
                        raise AssertionError("RPC audit HMAC field is malformed: {}".format(field))
            issued_jtis = [
                str((record.get("claims") or {}).get("jti") or "")
                for record in backend.RPC_GRANTS.values()
                if isinstance(record, dict)
            ]
            forbidden_values = (
                passwords
                + encoded
                + known_encoded
                + issued_jtis
                + [
                    known_password,
                    spawn_text,
                    npc_source,
                    token,
                    device_id,
                    username,
                    "127.0.0.1",
                    backend.MICRO_PAK_RPC_PATH,
                    shape_operation_id,
                    vector_operation_id,
                ]
            )
            for forbidden in forbidden_values:
                if forbidden and forbidden in audit_text:
                    raise AssertionError("sensitive RPC material leaked into audit")
        finally:
            backend_tls.PINNED_BACKEND_CA_PEM = old_pinned_ca
            backend_tls._PINNED_CONTEXT = old_pinned_context
            if server is not None:
                server.shutdown()
                server.server_close()
            if server_thread is not None:
                server_thread.join(timeout=5)
            for name, value in old_environment.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the client against the real backend RPC handler")
    parser.add_argument("--backend-source", type=Path, default=DEFAULT_BACKEND_SOURCE)
    parser.add_argument("--openssl", type=Path, default=DEFAULT_OPENSSL)
    args = parser.parse_args()
    run_probe(args.backend_source.resolve(), args.openssl.resolve())
    print("core RPC backend integration probe: PASS")
    print("- pinned TLS accepted the probe CA and rejected wrong CA/hostname")
    print("- real backend TLS handler accepted the client capability and RPC wrapper")
    print("- seven-role store bundle, spawn records, and NPC AST completed real TLS round trips")
    print("- explicit entitlement succeeded and default-deny returned 403")
    print("- UpdateServer compatibility vector, response shape, and redacted audit output passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

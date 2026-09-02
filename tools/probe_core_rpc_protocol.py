from __future__ import annotations

import base64
import hashlib
import json
import math
import random
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import toolbox_capabilities as capability
import toolbox_core_rpc as core_rpc


NOW = 2_000_000_000
CLIENT_VERSION = "1.3.8"
SUBJECT = "rpc-probe-user"
DEVICE_ID = "rpc-probe-device-2026-07"
DEVICE_HASH = capability.compute_device_hash(DEVICE_ID)
SESSION_TOKEN = "rpc-probe-session-token"
NONCE = "rpc_probe_nonce_0123456789abcdef"
OPERATION_ID = "rpc_probe_operation_0123456789"
KEY_ID = "rpc-probe-capability-2026"
PASSWORDS = ["破解的人生儿子没有PY", "", "A1-测试"]
TARGET_SCOPE_SHA256 = hashlib.sha256(b"rpc-probe-target-scope").hexdigest()
ALT_TARGET_SCOPE_SHA256 = hashlib.sha256(b"rpc-probe-alt-target-scope").hexdigest()
EXPECTED_PRE_SHA256 = hashlib.sha256(b"rpc-probe-pre-image").hexdigest()


def _is_probable_prime(value: int) -> bool:
    if value < 2:
        return False
    for prime in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43):
        if value == prime:
            return True
        if value % prime == 0:
            return False
    d = value - 1
    shifts = 0
    while d % 2 == 0:
        shifts += 1
        d //= 2
    for base in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        x = pow(base, d, value)
        if x in (1, value - 1):
            continue
        for _ in range(shifts - 1):
            x = pow(x, 2, value)
            if x == value - 1:
                break
        else:
            return False
    return True


def _prime(rng: random.Random, bits: int, exponent: int) -> int:
    while True:
        value = rng.getrandbits(bits) | (1 << (bits - 1)) | 1
        if math.gcd(value - 1, exponent) == 1 and _is_probable_prime(value):
            return value


def _probe_keypair():
    rng = random.Random(0x5250434341504142494C495459)
    exponent = 65537
    p = _prime(rng, 1024, exponent)
    q = _prime(rng, 1024, exponent)
    while q == p or (p * q).bit_length() < 2048:
        q = _prime(rng, 1024, exponent)
    modulus = p * q
    private_exponent = pow(exponent, -1, (p - 1) * (q - 1))
    return modulus, exponent, private_exponent


def _sign(payload: bytes, modulus: int, private_exponent: int) -> str:
    width = (modulus.bit_length() + 7) // 8
    digest_info = capability._RSA_SHA256_DIGEST_INFO_PREFIX + hashlib.sha256(payload).digest()
    padding_len = width - len(digest_info) - 3
    encoded = b"\x00\x01" + (b"\xff" * padding_len) + b"\x00" + digest_info
    signature = pow(int.from_bytes(encoded, "big"), private_exponent, modulus).to_bytes(width, "big")
    return base64.b64encode(signature).decode("ascii")


def _base_rpc_claims(request: dict) -> dict:
    return {
        "iss": capability.CAPABILITY_ISSUER,
        "aud": capability.CAPABILITY_AUDIENCE,
        "schema_version": capability.RPC_CAPABILITY_CLAIMS_SCHEMA_VERSION,
        "sub": SUBJECT,
        "app": capability.CAPABILITY_APP,
        "feature": request["feature"],
        "client_version": request["client_version"],
        "device_hash": request["device_hash"],
        "nonce": request["nonce"],
        "iat": NOW - 5,
        "nbf": NOW - 5,
        "exp": NOW + 300,
        "jti": "rpc_probe_jti_0123456789abcdef",
        "auth_version": 0,
        "session_hash": capability.compute_session_hash(SESSION_TOKEN),
        "purpose": request["purpose"],
        "request_sha256": request["request_sha256"],
        "rpc_path": request["rpc_path"],
    }


def _signed_rpc_envelope(claims: dict, modulus: int, private_exponent: int) -> dict:
    payload = capability.canonical_capability_payload(claims)
    encoded_payload = base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")
    signed_bytes = capability.RPC_CAPABILITY_SIGNATURE_CONTEXT + encoded_payload.encode("ascii")
    return {
        "ok": True,
        "capability": {
            "format": capability.RPC_CAPABILITY_FORMAT,
            "payload": encoded_payload,
            "signature": {
                "alg": "RS256",
                "key_id": KEY_ID,
                "value": _sign(signed_bytes, modulus, private_exponent),
            },
        },
    }


def _fake_encoded(password: str) -> str:
    if password == "":
        return ""
    return "01" + ("A5" * len(password.encode("gbk", errors="replace")))


def _expect_error(error_type, code: str, callback) -> None:
    try:
        callback()
    except error_type as exc:
        assert exc.code == code, (type(exc).__name__, exc.code, str(exc))
    else:
        raise AssertionError("expected {} ({})".format(error_type.__name__, code))


def _run_nonfinite_timeout_probe(public_keys: dict) -> None:
    opener_calls = []
    old_capability_opener = capability.build_backend_opener
    old_rpc_opener = core_rpc.build_backend_opener

    def unexpected_opener():
        opener_calls.append("called")
        raise AssertionError("non-finite timeout reached the network opener")

    session = {
        "server": "https://127.0.0.1:1",
        "token": SESSION_TOKEN,
        "username": SUBJECT,
        "device_id": DEVICE_ID,
    }
    request_payload = core_rpc.build_micro_pak_encrypt_request(
        PASSWORDS,
        operation_id=OPERATION_ID,
    )
    request_hash = core_rpc.compute_rpc_request_sha256(request_payload)
    invalid_values = (float("nan"), float("inf"), float("-inf"))
    capability.build_backend_opener = unexpected_opener
    core_rpc.build_backend_opener = unexpected_opener
    try:
        for timeout in invalid_values:
            _expect_error(
                capability.CapabilityConfigurationError,
                "invalid_timeout",
                lambda timeout=timeout: capability.request_capability(
                    "https://127.0.0.1:1",
                    SESSION_TOKEN,
                    core_rpc.MICRO_PAK_FEATURE,
                    CLIENT_VERSION,
                    DEVICE_HASH,
                    expected_subject=SUBJECT,
                    _test_nonce=NONCE,
                    timeout_seconds=timeout,
                    allow_local_http=True,
                    now=NOW,
                    public_keys=public_keys,
                ),
            )
            _expect_error(
                capability.CapabilityConfigurationError,
                "invalid_timeout",
                lambda timeout=timeout: capability.request_rpc_capability(
                    "https://127.0.0.1:1",
                    SESSION_TOKEN,
                    core_rpc.MICRO_PAK_FEATURE,
                    CLIENT_VERSION,
                    DEVICE_HASH,
                    expected_subject=SUBJECT,
                    request_sha256=request_hash,
                    rpc_path=core_rpc.MICRO_PAK_RPC_PATH,
                    _test_nonce=NONCE,
                    timeout_seconds=timeout,
                    allow_local_http=True,
                    now=NOW,
                    public_keys=public_keys,
                ),
            )
            _expect_error(
                core_rpc.CoreRpcConfigurationError,
                "invalid_timeout",
                lambda timeout=timeout: core_rpc.encrypt_micro_pak_passwords(
                    session=session,
                    passwords=PASSWORDS,
                    client_version=CLIENT_VERSION,
                    operation_id=OPERATION_ID,
                    timeout_seconds=timeout,
                    allow_local_http=True,
                    now=NOW,
                    public_keys=public_keys,
                    _test_nonce=NONCE,
                ),
            )
    finally:
        capability.build_backend_opener = old_capability_opener
        core_rpc.build_backend_opener = old_rpc_opener
    assert opener_calls == [], opener_calls


def _run_loopback_probe(modulus: int, private_exponent: int, public_keys: dict) -> None:
    observed = {"capability": None, "rpc": None, "wrong_device": None}
    issued = {"envelope": None}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            request = json.loads(body.decode("utf-8"))
            status = 200
            if self.path == capability.CAPABILITY_ENDPOINT_PATH:
                observed["capability"] = {
                    "authorization": self.headers.get("Authorization"),
                    "content_type": self.headers.get("Content-Type"),
                    "request": request,
                }
                claims = _base_rpc_claims(request)
                envelope = _signed_rpc_envelope(claims, modulus, private_exponent)
                issued["envelope"] = envelope
                response = envelope
            elif self.path == core_rpc.MICRO_PAK_RPC_PATH:
                device_id = self.headers.get("X-Device-Id")
                if device_id != DEVICE_ID:
                    observed["wrong_device"] = device_id
                    status = 403
                    response = {
                        "ok": False,
                        "error": {
                            "code": "device_mismatch",
                            "message": "device mismatch",
                        },
                    }
                else:
                    observed["rpc"] = {
                        "authorization": self.headers.get("Authorization"),
                        "content_type": self.headers.get("Content-Type"),
                        "device_id": device_id,
                        "wrapper": request,
                    }
                    assert set(request) == {"capability", "request"}
                    assert set(request["capability"]) == {"format", "payload", "signature"}
                    assert request["capability"] == issued["envelope"]["capability"]
                    rpc_request = request["request"]
                    request_hash = hashlib.sha256(core_rpc.canonical_rpc_json(rpc_request)).hexdigest()
                    assert request_hash == observed["capability"]["request"]["request_sha256"]
                    response = {
                        "ok": True,
                        "operation_id": rpc_request["operation_id"],
                        "encoded": [_fake_encoded(value) for value in rpc_request["passwords"]],
                    }
            else:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            raw = json.dumps(
                response,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        base = "http://127.0.0.1:{}".format(server.server_address[1])
        session = {
            "server": base + "/api/login",
            "token": SESSION_TOKEN,
            "username": SUBJECT,
            "device_id": DEVICE_ID,
        }
        encoded = core_rpc.encrypt_micro_pak_passwords(
            session,
            PASSWORDS,
            CLIENT_VERSION,
            operation_id=OPERATION_ID,
            allow_local_http=True,
            now=NOW,
            public_keys=public_keys,
            _test_nonce=NONCE,
        )
        assert encoded == [_fake_encoded(value) for value in PASSWORDS]
        assert observed["capability"]["authorization"] == "Bearer " + SESSION_TOKEN
        assert observed["rpc"]["authorization"] == "Bearer " + SESSION_TOKEN
        assert observed["rpc"]["device_id"] == DEVICE_ID
        assert observed["capability"]["request"] == {
            "feature": core_rpc.MICRO_PAK_FEATURE,
            "client_version": CLIENT_VERSION,
            "device_hash": DEVICE_HASH,
            "nonce": NONCE,
            "purpose": capability.RPC_CAPABILITY_PURPOSE,
            "request_sha256": hashlib.sha256(
                core_rpc.canonical_rpc_json(observed["rpc"]["wrapper"]["request"])
            ).hexdigest(),
            "rpc_path": core_rpc.MICRO_PAK_RPC_PATH,
        }
        assert set(observed["rpc"]["wrapper"]) == {"capability", "request"}
        assert observed["rpc"]["wrapper"]["request"] == {
            "schema_version": core_rpc.RPC_REQUEST_SCHEMA_VERSION,
            "operation_id": OPERATION_ID,
            "passwords": PASSWORDS,
        }

        capability_request = observed["capability"]["request"]
        grant = capability.verify_rpc_capability_envelope(
            issued["envelope"],
            expected_feature=core_rpc.MICRO_PAK_FEATURE,
            expected_client_version=CLIENT_VERSION,
            expected_device_hash=DEVICE_HASH,
            expected_nonce=NONCE,
            expected_subject=SUBJECT,
            session_token=SESSION_TOKEN,
            expected_request_sha256=capability_request["request_sha256"],
            expected_rpc_path=core_rpc.MICRO_PAK_RPC_PATH,
            now=NOW,
            public_keys=public_keys,
        )
        _expect_error(
            core_rpc.CoreRpcAuthorizationError,
            "device_mismatch",
            lambda: core_rpc._call_micro_pak_rpc(
                base,
                SESSION_TOKEN,
                "wrong-device-id",
                grant,
                observed["rpc"]["wrapper"]["request"],
                timeout_seconds=5,
                allow_local_http=True,
            ),
        )
        assert observed["wrong_device"] == "wrong-device-id"
        _expect_error(
            core_rpc.CoreRpcConfigurationError,
            "invalid_device_id",
            lambda: core_rpc._call_micro_pak_rpc(
                base,
                SESSION_TOKEN,
                "",
                grant,
                observed["rpc"]["wrapper"]["request"],
                timeout_seconds=5,
                allow_local_http=True,
            ),
        )
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


def _run_extended_operation_contract_probes() -> None:
    session = {
        "server": "https://rpc-operation-probe.invalid",
        "token": SESSION_TOKEN,
        "username": SUBJECT,
        "device_id": DEVICE_ID,
    }
    observed = []
    response_builders = {}
    original_rpc_options = core_rpc._rpc_options

    def fake_rpc_options(
        actual_session,
        request_payload,
        feature,
        rpc_path,
        client_version,
        *_args,
        **_kwargs
    ):
        observed.append(
            {
                "session": dict(actual_session),
                "request": json.loads(json.dumps(request_payload, ensure_ascii=False)),
                "feature": feature,
                "rpc_path": rpc_path,
                "client_version": client_version,
            }
        )
        return response_builders[feature](request_payload)

    core_rpc._rpc_options = fake_rpc_options
    try:
        store_operation = OPERATION_ID + "_store"
        store_config = {
            "feature_folder": "游戏功能",
            "category_folder": "武器分类",
            "script_name": "仓库主脚本",
            "method_name": "打开仓库",
            "common_folder": "通区文件",
            "zone_name": "盟重",
            "store_u_var": "U335",
            "teleport_condition": "LARGE U599 499",
            "timer_id": 51,
            "qr_trigger": 200,
            "resource_number": 21,
            "qr_method": "掉落前检测",
            "filter_tip": "虾米过滤",
            "store_tip": "虾米存储",
            "target_scope_sha256": TARGET_SCOPE_SHA256,
        }
        store_names = {
            "feature.filter_main": "仓库主脚本.txt",
            "feature.create_file": "创建文件.txt",
            "feature.interface_config": "界面配置读取.txt",
            "feature.variable_init": "存销变量初始化.txt",
            "owned.qmanage_login": "QManage.txt",
            "owned.qmanage_timer": "QManage.txt",
            "owned.qfunction_main": "QFunction-0.txt",
        }

        def store_response(request):
            artifacts = []
            for index, role in enumerate(core_rpc.STORE_BUNDLE_ROLES):
                content = ";SERVER-%d-%s" % (index, role)
                artifacts.append({
                    "role": role,
                    "name": store_names[role],
                    "content": content,
                    "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                })
            return {
                "ok": True,
                "schema_version": core_rpc.RPC_REQUEST_SCHEMA_VERSION,
                "operation_id": request["operation_id"],
                "core_version": "probe-core-v1",
                "artifacts": artifacts,
                "identity": {
                    "config_sha256": hashlib.sha256(
                        core_rpc.canonical_rpc_json(request["config"])
                    ).hexdigest(),
                    "target_scope_sha256": request["config"]["target_scope_sha256"],
                },
            }

        response_builders[core_rpc.STORE_SETTINGS_FEATURE] = store_response
        store_request = core_rpc.build_store_bundle_request(
            store_config, operation_id=store_operation
        )
        assert store_request == {
            "schema_version": core_rpc.RPC_REQUEST_SCHEMA_VERSION,
            "operation_id": store_operation,
            "config": store_config,
        }
        store_result = core_rpc.render_store_bundle_rpc(
            session,
            store_config,
            CLIENT_VERSION,
            operation_id=store_operation,
        )
        assert set(store_result) == {"artifacts", "config_sha256", "target_scope_sha256"}
        assert tuple(store_result["artifacts"]) == core_rpc.STORE_BUNDLE_ROLES
        assert store_result["artifacts"]["feature.filter_main"]["name"] == "仓库主脚本.txt"
        assert store_result["config_sha256"] == hashlib.sha256(
            core_rpc.canonical_rpc_json(store_config)
        ).hexdigest()
        assert store_result["target_scope_sha256"] == TARGET_SCOPE_SHA256
        assert observed[-1]["feature"] == core_rpc.STORE_SETTINGS_FEATURE
        assert observed[-1]["rpc_path"] == core_rpc.STORE_RENDER_RPC_PATH
        assert observed[-1]["request"] == store_request
        assert observed[-1]["session"] == session

        def invalid_store_response(request):
            response = store_response(request)
            response["artifacts"][0]["content_sha256"] = "0" * 64
            return response

        response_builders[core_rpc.STORE_SETTINGS_FEATURE] = invalid_store_response
        _expect_error(
            core_rpc.CoreRpcProtocolError,
            "invalid_store_response",
            lambda: core_rpc.render_store_bundle_rpc(
                session,
                store_config,
                CLIENT_VERSION,
                operation_id=store_operation,
            ),
        )
        _expect_error(
            core_rpc.CoreRpcConfigurationError,
            "invalid_store_config",
            lambda: core_rpc.build_store_bundle_request(
                dict(store_config, EXTRA="not-allowed"),
                operation_id=store_operation,
            ),
        )
        for label, mutate in (
            ("missing-role", lambda response: response["artifacts"].pop()),
            ("duplicate-role", lambda response: response["artifacts"].__setitem__(1, dict(response["artifacts"][0]))),
            ("extra-field", lambda response: response["artifacts"][0].__setitem__("extra", True)),
            ("config-hash", lambda response: response["identity"].__setitem__("config_sha256", "0" * 64)),
            ("target-scope-echo", lambda response: response["identity"].__setitem__("target_scope_sha256", ALT_TARGET_SCOPE_SHA256)),
        ):
            def malformed_store_response(request, mutate=mutate):
                response = store_response(request)
                mutate(response)
                return response
            response_builders[core_rpc.STORE_SETTINGS_FEATURE] = malformed_store_response
            _expect_error(
                core_rpc.CoreRpcProtocolError,
                "invalid_store_response",
                lambda: core_rpc.render_store_bundle_rpc(
                    session, store_config, CLIENT_VERSION, operation_id=store_operation,
                ),
            )
        for bad_config in (
            dict(store_config, feature_folder="../escape"),
            dict(store_config, method_name="bad label"),
            dict(store_config, timer_id=256),
            dict(store_config, qr_trigger=True),
            dict(store_config, target_scope_sha256=TARGET_SCOPE_SHA256.upper()),
        ):
            _expect_error(
                core_rpc.CoreRpcConfigurationError,
                "invalid_store_config",
                lambda bad_config=bad_config: core_rpc.build_store_bundle_request(
                    bad_config, operation_id=store_operation,
                ),
            )
        changed_scope_request = core_rpc.build_store_bundle_request(
            dict(store_config, target_scope_sha256=ALT_TARGET_SCOPE_SHA256),
            operation_id=store_operation,
        )
        assert core_rpc.compute_rpc_request_sha256(changed_scope_request) != core_rpc.compute_rpc_request_sha256(store_request)

        spawn_operation = OPERATION_ID + "_spawn"
        spawn_text = "; comment\n 0 001 2 Monster 3 4 5 255 tail\n# skip\nbad row\n"
        spawn_line = spawn_text.splitlines()[1]
        spawn_matches = list(re.finditer(r"\S+", spawn_line))[:8]
        spawn_record = {
            "line_number": 1,
            "fields": [match.group(0) for match in spawn_matches],
            "token_spans": [[match.start(), match.end()] for match in spawn_matches],
        }

        def spawn_response(request):
            return {
                "ok": True,
                "schema_version": core_rpc.RPC_REQUEST_SCHEMA_VERSION,
                "operation_id": request["operation_id"],
                "core_version": "probe-core-v1",
                "accepted": 1,
                "rejected": 1,
                "records": [spawn_record],
                "identity": {
                    "target_scope_sha256": request["target_scope_sha256"],
                    "expected_pre_sha256": request["expected_pre_sha256"],
                    "source_sha256": hashlib.sha256(request["text"].encode("utf-8")).hexdigest(),
                },
            }

        response_builders[core_rpc.SPAWN_VISUAL_FEATURE] = spawn_response
        spawn_request = core_rpc.build_spawn_parse_request(
            spawn_text,
            target_scope_sha256=TARGET_SCOPE_SHA256,
            expected_pre_sha256=EXPECTED_PRE_SHA256,
            operation_id=spawn_operation,
        )
        spawn_result = core_rpc.parse_spawn_document_rpc(
            session,
            spawn_text,
            CLIENT_VERSION,
            target_scope_sha256=TARGET_SCOPE_SHA256,
            expected_pre_sha256=EXPECTED_PRE_SHA256,
            operation_id=spawn_operation,
        )
        assert spawn_result == {"accepted": 1, "rejected": 1, "records": [spawn_record]}
        assert observed[-1]["feature"] == core_rpc.SPAWN_VISUAL_FEATURE
        assert observed[-1]["rpc_path"] == core_rpc.SPAWN_PARSE_RPC_PATH
        assert observed[-1]["request"] == spawn_request

        def invalid_spawn_response(request):
            response = spawn_response(request)
            response["records"] = [json.loads(json.dumps(spawn_record))]
            response["records"][0]["token_spans"][0] = [0, 1]
            return response

        response_builders[core_rpc.SPAWN_VISUAL_FEATURE] = invalid_spawn_response
        _expect_error(
            core_rpc.CoreRpcProtocolError,
            "invalid_spawn_response",
            lambda: core_rpc.parse_spawn_document_rpc(
                session,
                spawn_text,
                CLIENT_VERSION,
                target_scope_sha256=TARGET_SCOPE_SHA256,
                expected_pre_sha256=EXPECTED_PRE_SHA256,
                operation_id=spawn_operation,
            ),
        )
        _expect_error(
            core_rpc.CoreRpcConfigurationError,
            "spawn_document_too_large",
            lambda: core_rpc.build_spawn_parse_request(
                "x" * (core_rpc.MAX_SPAWN_DOCUMENT_BYTES + 1),
                target_scope_sha256=TARGET_SCOPE_SHA256,
                expected_pre_sha256=EXPECTED_PRE_SHA256,
                operation_id=spawn_operation,
            ),
        )
        response_builders[core_rpc.SPAWN_VISUAL_FEATURE] = spawn_response
        for field, invalid_value in (
            ("target_scope_sha256", ALT_TARGET_SCOPE_SHA256),
            ("expected_pre_sha256", "0" * 64),
            ("source_sha256", "F" * 64),
        ):
            def wrong_spawn_identity(request, field=field, invalid_value=invalid_value):
                response = spawn_response(request)
                response["identity"][field] = invalid_value
                return response
            response_builders[core_rpc.SPAWN_VISUAL_FEATURE] = wrong_spawn_identity
            _expect_error(
                core_rpc.CoreRpcProtocolError,
                "invalid_spawn_response",
                lambda: core_rpc.parse_spawn_document_rpc(
                    session,
                    spawn_text,
                    CLIENT_VERSION,
                    target_scope_sha256=TARGET_SCOPE_SHA256,
                    expected_pre_sha256=EXPECTED_PRE_SHA256,
                    operation_id=spawn_operation,
                ),
            )

        npc_operation = OPERATION_ID + "_npc"
        npc_source = "[@main]\n#SAY\n<hello/@exit>\n"
        node_start = npc_source.index("<hello")
        node_end = node_start + len("<hello/@exit>")
        npc_document = {
            "labels": [
                {
                    "label": "@main",
                    "source": {"start": 0, "end": len(npc_source), "line": 1, "column": 1},
                    "say_blocks": [
                        {
                            "id": "say-1",
                            "label": "@main",
                            "source": {"start": node_start, "end": node_end, "line": 3, "column": 1},
                            "nodes": [
                                {
                                    "id": "node-1",
                                    "kind": "link",
                                    "text": "hello",
                                    "raw": "<hello/@exit>",
                                    "source": {"start": node_start, "end": node_end, "line": 3, "column": 1},
                                    "props": {"label": "@exit"},
                                    "children": [],
                                }
                            ],
                        }
                    ],
                    "act_lines": [],
                    "openmerchant": None,
                }
            ]
        }

        def npc_response(request):
            return {
                "ok": True,
                "schema_version": core_rpc.RPC_REQUEST_SCHEMA_VERSION,
                "operation_id": request["operation_id"],
                "core_version": "probe-core-v1",
                "document": npc_document,
                "identity": {
                    "target_scope_sha256": request["target_scope_sha256"],
                    "expected_pre_sha256": request["expected_pre_sha256"],
                    "source_sha256": hashlib.sha256(request["source_text"].encode("utf-8")).hexdigest(),
                },
            }

        response_builders[core_rpc.NPC_VISUAL_FEATURE] = npc_response
        npc_request = core_rpc.build_npc_parse_request(
            npc_source,
            target_scope_sha256=TARGET_SCOPE_SHA256,
            expected_pre_sha256=EXPECTED_PRE_SHA256,
            operation_id=npc_operation,
        )
        npc_result = core_rpc.parse_npc_document_rpc(
            session,
            npc_source,
            CLIENT_VERSION,
            target_scope_sha256=TARGET_SCOPE_SHA256,
            expected_pre_sha256=EXPECTED_PRE_SHA256,
            operation_id=npc_operation,
        )
        assert npc_result == npc_document
        assert observed[-1]["feature"] == core_rpc.NPC_VISUAL_FEATURE
        assert observed[-1]["rpc_path"] == core_rpc.NPC_PARSE_RPC_PATH
        assert observed[-1]["request"] == npc_request

        def invalid_npc_response(request):
            response = npc_response(request)
            response["document"] = {"labels": [], "source_text": npc_source}
            return response

        response_builders[core_rpc.NPC_VISUAL_FEATURE] = invalid_npc_response
        _expect_error(
            core_rpc.CoreRpcProtocolError,
            "invalid_npc_response",
            lambda: core_rpc.parse_npc_document_rpc(
                session,
                npc_source,
                CLIENT_VERSION,
                target_scope_sha256=TARGET_SCOPE_SHA256,
                expected_pre_sha256=EXPECTED_PRE_SHA256,
                operation_id=npc_operation,
            ),
        )
        _expect_error(
            core_rpc.CoreRpcConfigurationError,
            "npc_document_too_large",
            lambda: core_rpc.build_npc_parse_request(
                "x" * (core_rpc.MAX_NPC_DOCUMENT_BYTES + 1),
                target_scope_sha256=TARGET_SCOPE_SHA256,
                expected_pre_sha256=EXPECTED_PRE_SHA256,
                operation_id=npc_operation,
            ),
        )
        response_builders[core_rpc.NPC_VISUAL_FEATURE] = npc_response
        for field, invalid_value in (
            ("target_scope_sha256", ALT_TARGET_SCOPE_SHA256),
            ("expected_pre_sha256", "0" * 64),
            ("source_sha256", "F" * 64),
        ):
            def wrong_npc_identity(request, field=field, invalid_value=invalid_value):
                response = npc_response(request)
                response["identity"][field] = invalid_value
                return response
            response_builders[core_rpc.NPC_VISUAL_FEATURE] = wrong_npc_identity
            _expect_error(
                core_rpc.CoreRpcProtocolError,
                "invalid_npc_response",
                lambda: core_rpc.parse_npc_document_rpc(
                    session,
                    npc_source,
                    CLIENT_VERSION,
                    target_scope_sha256=TARGET_SCOPE_SHA256,
                    expected_pre_sha256=EXPECTED_PRE_SHA256,
                    operation_id=npc_operation,
                ),
            )
    finally:
        core_rpc._rpc_options = original_rpc_options


def main() -> int:
    modulus, exponent, private_exponent = _probe_keypair()
    public_keys = {KEY_ID: {"n": "0x" + format(modulus, "x"), "e": exponent}}
    assert capability.CAPABILITY_FORMAT == 1
    assert capability.CAPABILITY_CLAIMS_SCHEMA_VERSION == 1
    assert capability.RPC_CAPABILITY_FORMAT == 2
    assert capability.RPC_CAPABILITY_CLAIMS_SCHEMA_VERSION == 2

    request_payload = core_rpc.build_micro_pak_encrypt_request(
        PASSWORDS,
        operation_id=OPERATION_ID,
    )
    request_hash = core_rpc.compute_rpc_request_sha256(request_payload)
    capability_request = {
        "feature": core_rpc.MICRO_PAK_FEATURE,
        "client_version": CLIENT_VERSION,
        "device_hash": DEVICE_HASH,
        "nonce": NONCE,
        "purpose": capability.RPC_CAPABILITY_PURPOSE,
        "request_sha256": request_hash,
        "rpc_path": core_rpc.MICRO_PAK_RPC_PATH,
    }
    signed = _signed_rpc_envelope(
        _base_rpc_claims(capability_request),
        modulus,
        private_exponent,
    )
    verified = capability.verify_rpc_capability_envelope(
        signed,
        expected_feature=core_rpc.MICRO_PAK_FEATURE,
        expected_client_version=CLIENT_VERSION,
        expected_device_hash=DEVICE_HASH,
        expected_nonce=NONCE,
        expected_subject=SUBJECT,
        session_token=SESSION_TOKEN,
        expected_request_sha256=request_hash,
        expected_rpc_path=core_rpc.MICRO_PAK_RPC_PATH,
        now=NOW,
        public_keys=public_keys,
    )
    assert verified.claims["purpose"] == "rpc"
    assert verified.claims["request_sha256"] == request_hash

    wrong_hash = "0" * 64 if request_hash != "0" * 64 else "1" * 64
    _expect_error(
        capability.CapabilityClaimError,
        "request_sha256_mismatch",
        lambda: capability.verify_rpc_capability_envelope(
            signed,
            expected_feature=core_rpc.MICRO_PAK_FEATURE,
            expected_client_version=CLIENT_VERSION,
            expected_device_hash=DEVICE_HASH,
            expected_nonce=NONCE,
            expected_subject=SUBJECT,
            session_token=SESSION_TOKEN,
            expected_request_sha256=wrong_hash,
            expected_rpc_path=core_rpc.MICRO_PAK_RPC_PATH,
            now=NOW,
            public_keys=public_keys,
        ),
    )

    wrong_purpose_claims = _base_rpc_claims(capability_request)
    wrong_purpose_claims["purpose"] = "batch"
    wrong_purpose = _signed_rpc_envelope(wrong_purpose_claims, modulus, private_exponent)
    _expect_error(
        capability.CapabilityClaimError,
        "purpose_mismatch",
        lambda: capability.verify_rpc_capability_envelope(
            wrong_purpose,
            expected_feature=core_rpc.MICRO_PAK_FEATURE,
            expected_client_version=CLIENT_VERSION,
            expected_device_hash=DEVICE_HASH,
            expected_nonce=NONCE,
            expected_subject=SUBJECT,
            session_token=SESSION_TOKEN,
            expected_request_sha256=request_hash,
            expected_rpc_path=core_rpc.MICRO_PAK_RPC_PATH,
            now=NOW,
            public_keys=public_keys,
        ),
    )

    _expect_error(
        core_rpc.CoreRpcConfigurationError,
        "invalid_password_count",
        lambda: core_rpc.build_micro_pak_encrypt_request(
            ["x"] * (core_rpc.MAX_PASSWORD_COUNT + 1),
            operation_id=OPERATION_ID,
        ),
    )
    _expect_error(
        core_rpc.CoreRpcProtocolError,
        "invalid_encoded_value",
        lambda: core_rpc._validate_rpc_result(
            {
                "ok": True,
                "operation_id": OPERATION_ID,
                "encoded": ["01aa"],
            },
            operation_id=OPERATION_ID,
            passwords=["A"],
        ),
    )

    _run_nonfinite_timeout_probe(public_keys)
    _run_loopback_probe(modulus, private_exponent, public_keys)
    _run_extended_operation_contract_probes()

    print("core RPC protocol probe: PASS")
    print("- capability v1 constants remain unchanged")
    print("- v2 grant signature, purpose, path, session, device, and canonical body hash verified")
    print("- loopback capability + RPC POST wrapper, X-Device-Id binding, and strict batch result validation passed")
    print("- wrong hash, wrong purpose, oversized batch, and lowercase result rejected")
    print("- NaN and positive/negative infinity timeouts rejected before any opener call")
    print("- seven-role store bundle, spawn, and NPC request builders/routes passed strict validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

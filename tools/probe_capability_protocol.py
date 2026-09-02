from __future__ import annotations

import base64
import json
import math
import os
import random
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import toolbox_capabilities as capability


NOW = 2_000_000_000
FEATURE = "npc.visual.parse"
CLIENT_VERSION = "1.3.8"
EXPECTED_SUBJECT = "probe-user"
DEVICE_ID = "probe-device-2026-07"
DEVICE_HASH = capability.compute_device_hash(DEVICE_ID)
NONCE = "probe_nonce_0123456789abcdef"
SESSION_TOKEN = "probe-session-token"
KEY_ID = "probe-capability-2026"


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
    rng = random.Random(0x4341504142494C495459)
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
    digest_info = capability._RSA_SHA256_DIGEST_INFO_PREFIX + capability.hashlib.sha256(payload).digest()
    padding_len = width - len(digest_info) - 3
    if padding_len < 8:
        raise AssertionError("probe RSA modulus is too small")
    encoded = b"\x00\x01" + (b"\xff" * padding_len) + b"\x00" + digest_info
    signature = pow(int.from_bytes(encoded, "big"), private_exponent, modulus).to_bytes(width, "big")
    return base64.b64encode(signature).decode("ascii")


def _base_claims(session_token: str = SESSION_TOKEN) -> dict:
    return {
        "iss": capability.CAPABILITY_ISSUER,
        "aud": capability.CAPABILITY_AUDIENCE,
        "schema_version": capability.CAPABILITY_CLAIMS_SCHEMA_VERSION,
        "sub": EXPECTED_SUBJECT,
        "app": capability.CAPABILITY_APP,
        "feature": FEATURE,
        "client_version": CLIENT_VERSION,
        "device_hash": DEVICE_HASH,
        "nonce": NONCE,
        "iat": NOW - 5,
        "nbf": NOW - 5,
        "exp": NOW + 300,
        "jti": "probe_jti_0123456789abcdef",
        "auth_version": 0,
        "session_hash": capability.compute_session_hash(session_token),
    }


def _signed_envelope(claims: dict, modulus: int, private_exponent: int) -> dict:
    payload = capability.canonical_capability_payload(claims)
    encoded_payload = base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")
    signed_bytes = capability.CAPABILITY_SIGNATURE_CONTEXT + encoded_payload.encode("ascii")
    return {
        "ok": True,
        "capability": {
            "format": capability.CAPABILITY_FORMAT,
            "payload": encoded_payload,
            "signature": {
                "alg": "RS256",
                "key_id": KEY_ID,
                "value": _sign(signed_bytes, modulus, private_exponent),
            },
        },
    }


def _expect_error(error_type, code: str, callback) -> None:
    try:
        callback()
    except error_type as exc:
        assert exc.code == code, (type(exc).__name__, exc.code, str(exc))
    else:
        raise AssertionError("expected {} ({})".format(error_type.__name__, code))


def _verify(envelope: dict, public_keys: dict, **overrides):
    values = {
        "expected_feature": FEATURE,
        "expected_client_version": CLIENT_VERSION,
        "expected_device_hash": DEVICE_HASH,
        "expected_nonce": NONCE,
        "expected_subject": EXPECTED_SUBJECT,
        "session_token": SESSION_TOKEN,
        "now": NOW,
        "public_keys": public_keys,
    }
    values.update(overrides)
    return capability.verify_capability_envelope(envelope, **values)


def _run_http_probe(modulus: int, private_exponent: int, public_keys: dict) -> None:
    observed = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            observed["path"] = self.path
            observed["authorization"] = self.headers.get("Authorization")
            length = int(self.headers.get("Content-Length", "0"))
            request = json.loads(self.rfile.read(length).decode("utf-8"))
            observed["request"] = request
            claims = _base_claims()
            claims["feature"] = request["feature"]
            claims["client_version"] = request["client_version"]
            claims["device_hash"] = request["device_hash"]
            claims["nonce"] = request["nonce"]
            raw = json.dumps(
                _signed_envelope(claims, modulus, private_exponent),
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            self.send_response(200)
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
        grant = capability.request_capability(
            base,
            SESSION_TOKEN,
            FEATURE,
            CLIENT_VERSION,
            DEVICE_HASH,
            expected_subject=EXPECTED_SUBJECT,
            _test_nonce=NONCE,
            allow_local_http=True,
            now=NOW,
            public_keys=public_keys,
        )
        assert grant.claims["feature"] == FEATURE
        assert observed["path"] == capability.CAPABILITY_ENDPOINT_PATH
        assert observed["authorization"] == "Bearer probe-session-token"
        assert observed["request"] == {
            "feature": FEATURE,
            "client_version": CLIENT_VERSION,
            "device_hash": DEVICE_HASH,
            "nonce": NONCE,
        }
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


def _run_redirect_probe(public_keys: dict) -> None:
    observed = {"post": 0, "get": 0}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            observed["post"] += 1
            self.send_response(302)
            self.send_header("Location", "/must-not-receive-bearer")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            observed["get"] += 1
            self.send_response(500)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        base = "http://127.0.0.1:{}".format(server.server_address[1])
        _expect_error(
            capability.CapabilityTransportError,
            "http_error",
            lambda: capability.request_capability(
                base,
                SESSION_TOKEN,
                FEATURE,
                CLIENT_VERSION,
                DEVICE_HASH,
                expected_subject=EXPECTED_SUBJECT,
                _test_nonce=NONCE,
                allow_local_http=True,
                now=NOW,
                public_keys=public_keys,
            ),
        )
        assert observed == {"post": 1, "get": 0}, observed
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


def _run_http_exception_probe(public_keys: dict) -> None:
    class BrokenOpener:
        def open(self, request, timeout):
            raise capability.http.client.BadStatusLine("invalid status line")

    original = capability.urllib.request.build_opener
    capability.urllib.request.build_opener = lambda *args: BrokenOpener()
    try:
        _expect_error(
            capability.CapabilityTransportError,
            "network_error",
            lambda: capability.request_capability(
                "http://127.0.0.1:9",
                SESSION_TOKEN,
                FEATURE,
                CLIENT_VERSION,
                DEVICE_HASH,
                expected_subject=EXPECTED_SUBJECT,
                _test_nonce=NONCE,
                allow_local_http=True,
                now=NOW,
                public_keys=public_keys,
            ),
        )
    finally:
        capability.urllib.request.build_opener = original


def main() -> int:
    modulus, exponent, private_exponent = _probe_keypair()
    public_keys = {KEY_ID: {"n": "0x" + format(modulus, "x"), "e": exponent}}
    assert modulus.bit_length() >= 2048
    assert capability.CAPABILITY_PUBLIC_KEYS
    production_keys = capability.load_capability_public_keys()
    assert "1cd8407399b1c949" in production_keys
    assert production_keys["1cd8407399b1c949"]["n"].bit_length() == 3072

    signed = _signed_envelope(_base_claims(), modulus, private_exponent)
    grant = _verify(signed, public_keys)
    assert grant.claims["feature"] == FEATURE
    assert grant.claims["auth_version"] == 0
    assert grant.claims["session_hash"] == capability.compute_session_hash(SESSION_TOKEN)
    assert grant.expires_at == NOW + 300
    assert json.loads(grant.to_json())["capability"]["payload"] == signed["capability"]["payload"]

    tampered = json.loads(json.dumps(signed))
    tampered_claims = _base_claims()
    tampered_claims["feature"] = "cdk.generate"
    tampered_payload = capability.canonical_capability_payload(tampered_claims)
    tampered["capability"]["payload"] = base64.urlsafe_b64encode(tampered_payload).rstrip(b"=").decode("ascii")
    _expect_error(
        capability.CapabilityTrustError,
        "invalid_signature",
        lambda: _verify(tampered, public_keys),
    )

    expired_claims = _base_claims()
    expired_claims.update({"iat": NOW - 400, "nbf": NOW - 400, "exp": NOW - 31})
    expired = _signed_envelope(expired_claims, modulus, private_exponent)
    _expect_error(
        capability.CapabilityClaimError,
        "expired",
        lambda: _verify(expired, public_keys),
    )

    _expect_error(
        capability.CapabilityClaimError,
        "feature_mismatch",
        lambda: _verify(signed, public_keys, expected_feature="cdk.generate"),
    )
    _expect_error(
        capability.CapabilityClaimError,
        "nonce_mismatch",
        lambda: _verify(
            signed,
            public_keys,
            expected_nonce="wrong_nonce_0123456789abcdef",
        ),
    )
    _expect_error(
        capability.CapabilityClaimError,
        "device_mismatch",
        lambda: _verify(
            signed,
            public_keys,
            expected_device_hash=capability.compute_device_hash("another-device"),
        ),
    )
    _expect_error(
        capability.CapabilityClaimError,
        "session_mismatch",
        lambda: _verify(
            signed,
            public_keys,
            session_token="wrong-bearer-token",
        ),
    )

    wrong_subject_claims = _base_claims()
    wrong_subject_claims["sub"] = "another-user"
    wrong_subject = _signed_envelope(wrong_subject_claims, modulus, private_exponent)
    _expect_error(
        capability.CapabilityClaimError,
        "subject_mismatch",
        lambda: _verify(wrong_subject, public_keys),
    )

    wrong_audience_claims = _base_claims()
    wrong_audience_claims["aud"] = "another-audience"
    wrong_audience = _signed_envelope(wrong_audience_claims, modulus, private_exponent)
    _expect_error(
        capability.CapabilityClaimError,
        "claim_scope_mismatch",
        lambda: _verify(wrong_audience, public_keys),
    )

    bad_signature = json.loads(json.dumps(signed))
    signature = bad_signature["capability"]["signature"]["value"]
    bad_signature["capability"]["signature"]["value"] = ("A" if signature[0] != "A" else "B") + signature[1:]
    _expect_error(
        capability.CapabilityTrustError,
        "invalid_signature",
        lambda: _verify(bad_signature, public_keys),
    )

    padded_payload = json.loads(json.dumps(signed))
    padded_payload["capability"]["payload"] += "="
    padded_ascii = padded_payload["capability"]["payload"].encode("ascii")
    padded_payload["capability"]["signature"]["value"] = _sign(
        capability.CAPABILITY_SIGNATURE_CONTEXT + padded_ascii,
        modulus,
        private_exponent,
    )
    _expect_error(
        capability.CapabilityProtocolError,
        "invalid_payload_encoding",
        lambda: _verify(padded_payload, public_keys),
    )

    noncanonical_bytes = json.dumps(
        _base_claims(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(", ", ": "),
    ).encode("utf-8")
    noncanonical = {
        "ok": True,
        "capability": {
            "format": capability.CAPABILITY_FORMAT,
            "payload": base64.urlsafe_b64encode(noncanonical_bytes).rstrip(b"=").decode("ascii"),
            "signature": {
                "alg": "RS256",
                "key_id": KEY_ID,
                "value": "",
            },
        },
    }
    noncanonical_ascii = noncanonical["capability"]["payload"].encode("ascii")
    noncanonical["capability"]["signature"]["value"] = _sign(
        capability.CAPABILITY_SIGNATURE_CONTEXT + noncanonical_ascii,
        modulus,
        private_exponent,
    )
    _expect_error(
        capability.CapabilityProtocolError,
        "noncanonical_payload",
        lambda: _verify(noncanonical, public_keys),
    )

    unknown_key = json.loads(json.dumps(signed))
    unknown_key["capability"]["signature"]["key_id"] = "unknown-capability-key"
    _expect_error(
        capability.CapabilityTrustError,
        "unknown_key",
        lambda: _verify(unknown_key, public_keys),
    )

    too_long_claims = _base_claims()
    too_long_claims["exp"] = too_long_claims["iat"] + capability.MAX_CAPABILITY_TTL_SECONDS + 1
    too_long = _signed_envelope(too_long_claims, modulus, private_exponent)
    _expect_error(
        capability.CapabilityClaimError,
        "ttl_exceeded",
        lambda: _verify(too_long, public_keys),
    )

    reversed_time_claims = _base_claims()
    reversed_time_claims["iat"] = NOW - 5
    reversed_time_claims["nbf"] = NOW
    reversed_time = _signed_envelope(reversed_time_claims, modulus, private_exponent)
    _expect_error(
        capability.CapabilityClaimError,
        "invalid_time_claims",
        lambda: _verify(reversed_time, public_keys),
    )

    extra_claims = _base_claims()
    extra_claims["role"] = "admin"
    extra_claim = _signed_envelope(extra_claims, modulus, private_exponent)
    _expect_error(
        capability.CapabilityProtocolError,
        "invalid_claim_set",
        lambda: _verify(extra_claim, public_keys),
    )

    ok, _ = capability.validate_capability_transport_url(
        "https://auth.example.invalid/api/v2/capabilities"
    )
    assert ok
    ok, _ = capability.validate_capability_transport_url(
        "http://auth.example.invalid/api/v2/capabilities",
        allow_local_http=True,
    )
    assert not ok
    ok, _ = capability.validate_capability_transport_url(
        "http://127.0.0.1:18080/api/v2/capabilities",
        allow_local_http=True,
    )
    assert ok

    previous_allow = os.environ.get("XIAMI_CAPABILITY_ALLOW_DEV_TRUST_KEYS")
    previous_keys = os.environ.get("XIAMI_CAPABILITY_DEV_PUBLIC_KEYS_JSON")
    try:
        os.environ["XIAMI_CAPABILITY_ALLOW_DEV_TRUST_KEYS"] = "1"
        os.environ["XIAMI_CAPABILITY_DEV_PUBLIC_KEYS_JSON"] = json.dumps(public_keys)
        assert KEY_ID not in capability.load_capability_public_keys()
        assert KEY_ID in capability.load_capability_public_keys(allow_dev_trust_keys=True)
        collision = {
            "1cd8407399b1c949": public_keys[KEY_ID],
        }
        os.environ["XIAMI_CAPABILITY_DEV_PUBLIC_KEYS_JSON"] = json.dumps(collision)
        _expect_error(
            capability.CapabilityConfigurationError,
            "production_key_override",
            lambda: capability.load_capability_public_keys(allow_dev_trust_keys=True),
        )
    finally:
        if previous_allow is None:
            os.environ.pop("XIAMI_CAPABILITY_ALLOW_DEV_TRUST_KEYS", None)
        else:
            os.environ["XIAMI_CAPABILITY_ALLOW_DEV_TRUST_KEYS"] = previous_allow
        if previous_keys is None:
            os.environ.pop("XIAMI_CAPABILITY_DEV_PUBLIC_KEYS_JSON", None)
        else:
            os.environ["XIAMI_CAPABILITY_DEV_PUBLIC_KEYS_JSON"] = previous_keys

    _expect_error(
        capability.CapabilityProtocolError,
        "invalid_json",
        lambda: capability._strict_json_loads(b'{"ok":true,"ok":false}'),
    )
    _run_http_probe(modulus, private_exponent, public_keys)
    _run_redirect_probe(public_keys)
    _run_http_exception_probe(public_keys)

    print("capability protocol probe: PASS")
    print("- production trust key pinned independently")
    print("- valid signed capability and loopback POST verified")
    print("- tamper/expiry/subject/feature/nonce/device/session/audience/time/signature failures rejected")
    print("- redirects, malformed HTTP, remote HTTP, noncanonical payloads, and key override rejected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

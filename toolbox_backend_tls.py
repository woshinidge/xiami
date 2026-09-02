from __future__ import annotations

import ipaddress
import ssl
import threading
import urllib.parse
import urllib.request
from typing import Optional, Union


PRODUCTION_BACKEND_HOST = "114.66.40.205"
PRODUCTION_BACKEND_PORT = 9443
PRODUCTION_BACKEND_ORIGIN = "https://{}:{}".format(
    PRODUCTION_BACKEND_HOST,
    PRODUCTION_BACKEND_PORT,
)
PRODUCTION_LOGIN_URL = PRODUCTION_BACKEND_ORIGIN + "/api/login"

# Public trust material only. The root private key and the server private key
# never belong in the client repository or release package.
PINNED_BACKEND_CA_PEM = """-----BEGIN CERTIFICATE-----
MIIFfjCCA2agAwIBAgIUU5enGOqGLggUr1GSnkgDt9fKbxcwDQYJKoZIhvcNAQEL
BQAwRTErMCkGA1UEAwwiWGlhbWkgVG9vbGJveCBQcml2YXRlIFJvb3QgQ0EgMjAy
NjEWMBQGA1UECgwNWGlhbWkgVG9vbGJveDAeFw0yNjA3MjIwODM2NDhaFw0zNjA3
MTkwODM2NDhaMEUxKzApBgNVBAMMIlhpYW1pIFRvb2xib3ggUHJpdmF0ZSBSb290
IENBIDIwMjYxFjAUBgNVBAoMDVhpYW1pIFRvb2xib3gwggIiMA0GCSqGSIb3DQEB
AQUAA4ICDwAwggIKAoICAQCywQIdTicuh8qUbQY6NycNvFdJwxQZ6r3XfwYdL16M
46+ivYyg5WWkE6xB9phwN91wTpbe23L9nPv0+taowE4l6+Vm32L6ny/g+yZsmqdx
m5NlfW7jmiAKRRoDvQZcXSmK30simENNVSeXQT0FKnxHUM7UBzs8WCcQznlw8yrI
6adwbJ3N3AP4dF8GPTSSE2uJ51whAKqzAJnWvAK9AFdVUTHS/LwZFbg3SAY/qltp
iXz+ya4wSQQJG9GCkFQ3SWJa8K8PGL7a895Tm5ATBxz6LrdCkUZ6xBTntUedLXTT
Hm6vXtakT0vwvtnNNNzgnJ1XlDXYtB4OqNp2HRRHMlAybnIqCJL266hciEv2y68M
L2V3MSU5rFCM3+s/xx4HqgyBPg2bOFRRzl/E+fV1VnHlyAb8LAm+B2em0yUrcGlT
p91S8/8cjPU5o3tVulyb/6HYkTI7bs6q6pw6sw24js2JaOnyjbiKGk/633rVP69E
arC863+05tgjue7MnF6Gas0+ewgFSpeBrklzTv4hbhFSYT9uHLF35cN09fTfIebV
yWBQrojxiIIXyqt8U0Mtj7YginGBpFO1mRV6G3cXjJp7beqwl6/Rqpaq9OKhoFpD
+4fOR6XTEdNeOyas33rUcNcbmm9IY6dnjdgeoJms3JcqXqwJ/QJZE3+NGo3Tw/fY
zwIDAQABo2YwZDAfBgNVHSMEGDAWgBQJ64frJ/fYY4/0cyte5GWQ1yxFZjASBgNV
HRMBAf8ECDAGAQH/AgEAMA4GA1UdDwEB/wQEAwIBBjAdBgNVHQ4EFgQUCeuH6yf3
2GOP9HMrXuRlkNcsRWYwDQYJKoZIhvcNAQELBQADggIBAFVGLU0Mg4QbLmISAFOG
LBxeNeh37g8oeDK0aM7L4HJkMQmd6KVJfUZwpAKoQm14nyDAhkZuC9NLz6p2XWW+
57+MGp2dC4BSk/EVr1DIydlOVpNj2VsT+xZMlR4+sVNuTuWfknSvUdIqeU1fehPO
DWkpgSaY3KxPAilxJNlvbb0aQ+YlC+KpFsF1RoxdomJ0W3d9ahTt13aHfg6chCSj
8Lwjc9lH3pugeQwcq3FRQPdysf2pdj5gJktEQOh3p0pS54KxFD5f3/6Ewss3pfr2
cLGmlvqQ2mgXNq/PiNI/2t6kUeViwnshQYFjuVCbySk9lEx12kD2Y4IfCISqn8eN
On+80d9jZ0O6NS4sqR5D5L858Nkf31f+UH4/WDqm/jBgKmcJVLbkdZaiYSas4YPl
DSqgnzo7rhtV5+ZOKFFjWe5dT0sOWpEZ9ZgRBR0aE0vX6mPn8gwRkaKpjcGxKQ62
wMkUWxrkLn9JWCFkRihdAe2vkrV8YQfcUvxhv8KPq9srOh8RS8crO3ZskF2hkNC/
CSMe15jTcSMThPrJRlfzsFvDFm6y3hz6SnEu9TIfLp7+h4bA2/zcxIUjec3ZIrJR
lAIlF03S+eBaBYTy1NkMTa3A5V+FuuojdqrIE3GgU1G6rfb8d+jIsDEF4kjndbhu
fIgqoAI+zPlS3h0+dnANT0PU
-----END CERTIFICATE-----
"""


class BackendTransportPolicyError(ValueError):
    pass


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def is_loopback_host(host: str) -> bool:
    value = str(host or "").strip().strip("[]").lower()
    if value == "localhost":
        return True
    try:
        return bool(ipaddress.ip_address(value).is_loopback)
    except Exception:
        return False


def normalize_backend_url(url: str, *, allow_local_http: bool = True) -> str:
    raw = str(url or "").strip()
    if not raw:
        raise BackendTransportPolicyError("Backend URL is empty")
    try:
        parsed = urllib.parse.urlsplit(raw)
        port = parsed.port
    except Exception as exc:
        raise BackendTransportPolicyError("Backend URL is invalid") from exc
    host = str(parsed.hostname or "").strip().lower()
    if not host or parsed.username is not None or parsed.password is not None:
        raise BackendTransportPolicyError("Backend URL must have a host and no credentials")
    if parsed.query or parsed.fragment:
        raise BackendTransportPolicyError("Backend URL must not contain a query or fragment")
    scheme = str(parsed.scheme or "").lower()
    path = str(parsed.path or "")
    if host == PRODUCTION_BACKEND_HOST:
        if scheme not in {"http", "https"}:
            raise BackendTransportPolicyError("Production backend requires HTTPS")
        return urllib.parse.urlunsplit(
            ("https", "{}:{}".format(PRODUCTION_BACKEND_HOST, PRODUCTION_BACKEND_PORT), path, "", "")
        )
    if scheme == "http":
        if not allow_local_http or not is_loopback_host(host):
            raise BackendTransportPolicyError("Remote backend HTTP is forbidden")
    elif scheme != "https":
        raise BackendTransportPolicyError("Backend URL only supports HTTPS or loopback HTTP")
    netloc = parsed.netloc
    if port is None and host == "localhost":
        netloc = "localhost"
    return urllib.parse.urlunsplit((scheme, netloc, path, "", ""))


def normalize_backend_base_url(url: str, *, allow_local_http: bool = True) -> str:
    raw = str(url or "").strip()
    if not raw:
        return PRODUCTION_BACKEND_ORIGIN
    if raw.rstrip("/").lower().endswith("/api/login"):
        raw = raw.rstrip("/")[:-len("/api/login")]
    normalized = normalize_backend_url(raw, allow_local_http=allow_local_http)
    parsed = urllib.parse.urlsplit(normalized)
    if parsed.path not in {"", "/"}:
        raise BackendTransportPolicyError("Backend base URL must not contain an API path")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def normalize_login_url(url: str, *, allow_local_http: bool = True) -> str:
    raw = str(url or "").strip()
    if not raw:
        return PRODUCTION_LOGIN_URL
    normalized = normalize_backend_url(raw, allow_local_http=allow_local_http)
    parsed = urllib.parse.urlsplit(normalized)
    path = str(parsed.path or "").rstrip("/")
    if not path:
        path = "/api/login"
    if path.lower() != "/api/login":
        raise BackendTransportPolicyError("Login URL must use /api/login")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def backend_base_from_login_url(url: str, *, allow_local_http: bool = True) -> str:
    login_url = normalize_login_url(url, allow_local_http=allow_local_http)
    parsed = urllib.parse.urlsplit(login_url)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def build_pinned_ssl_context() -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    if hasattr(ssl, "TLSVersion"):
        context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_verify_locations(cadata=PINNED_BACKEND_CA_PEM)
    return context


_CONTEXT_LOCK = threading.Lock()
_PINNED_CONTEXT: Optional[ssl.SSLContext] = None


def get_pinned_ssl_context() -> ssl.SSLContext:
    global _PINNED_CONTEXT
    if _PINNED_CONTEXT is None:
        with _CONTEXT_LOCK:
            if _PINNED_CONTEXT is None:
                _PINNED_CONTEXT = build_pinned_ssl_context()
    return _PINNED_CONTEXT


def build_backend_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _NoRedirectHandler(),
        urllib.request.HTTPSHandler(context=get_pinned_ssl_context()),
    )


def _canonical_request(
    request_or_url: Union[str, urllib.request.Request],
    *,
    allow_local_http: bool,
) -> Union[str, urllib.request.Request]:
    if isinstance(request_or_url, urllib.request.Request):
        current_url = str(request_or_url.full_url or "")
        normalized_url = normalize_backend_url(current_url, allow_local_http=allow_local_http)
        if normalized_url == current_url:
            return request_or_url
        headers = dict(request_or_url.header_items())
        return urllib.request.Request(
            normalized_url,
            data=request_or_url.data,
            headers=headers,
            origin_req_host=request_or_url.origin_req_host,
            unverifiable=request_or_url.unverifiable,
            method=request_or_url.get_method(),
        )
    return normalize_backend_url(str(request_or_url or ""), allow_local_http=allow_local_http)


def backend_urlopen(
    request_or_url: Union[str, urllib.request.Request],
    *,
    timeout: float,
    allow_local_http: bool = True,
):
    request = _canonical_request(request_or_url, allow_local_http=allow_local_http)
    return build_backend_opener().open(request, timeout=float(timeout))

from __future__ import annotations

import base64
from collections import deque
import hashlib
import json
import socket
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

from xiami_core.events import EventBus
from xiami_core.onebot.events import parse_onebot_event
from xiami_core.plugins.events import plugin_event_from_onebot
from xiami_core.storage.paths import LOG_HOME, ensure_runtime_dirs


_EVENT_LOG_LOCK = threading.Lock()
_EVENT_DEDUPE_LOCK = threading.Lock()
_RECENT_EVENT_LIMIT = 1024
_RECENT_EVENT_KEYS = deque()
_RECENT_EVENT_KEY_SET = set()


class OneBotEventGateway:
    def __init__(self, event_bus: EventBus, host: str = "127.0.0.1", port: int = 18081) -> None:
        self.event_bus = event_bus
        self.host = host
        self.port = port
        self.ws_port = port + 1
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._ws_server: ThreadingHTTPServer | None = None
        self._ws_thread: threading.Thread | None = None

    def start(self) -> str:
        if self._server and self._ws_server:
            return self.url
        handler = _make_handler(self.event_bus)
        if not self._server:
            self._server = _bind_server(self.host, self.port, handler)
            self.port = int(self._server.server_port)
            self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
            self._thread.start()
        if not self._ws_server:
            ws_handler = _make_ws_handler(self.event_bus)
            self._ws_server = _bind_server(self.host, max(self.port + 1, self.ws_port), ws_handler)
            self.ws_port = int(self._ws_server.server_port)
            self._ws_thread = threading.Thread(target=self._ws_server.serve_forever, daemon=True)
            self._ws_thread.start()
        return self.url

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
            self._thread = None
        if self._ws_server:
            self._ws_server.shutdown()
            self._ws_server.server_close()
            self._ws_server = None
            self._ws_thread = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/onebot/event"

    @property
    def ws_url(self) -> str:
        return f"ws://{self.host}:{self.ws_port}/onebot/event"


def _make_handler(event_bus: EventBus) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                _append_event_log({"time": _now(), "ok": False, "error": "invalid json", "raw": raw.decode("utf-8", errors="replace")})
                self.send_response(400)
                self.end_headers()
                return
            _handle_payload(event_bus, payload, transport="http")
            self.send_response(204)
            self.end_headers()

        def log_message(self, format: str, *args) -> None:
            return

    return Handler


def _make_ws_handler(event_bus: EventBus) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if str(self.headers.get("Upgrade") or "").lower() != "websocket":
                self.send_response(404)
                self.end_headers()
                return
            key = str(self.headers.get("Sec-WebSocket-Key") or "")
            if not key:
                self.send_response(400)
                self.end_headers()
                return
            accept = base64.b64encode(hashlib.sha1((key + _WS_GUID).encode("ascii")).digest()).decode("ascii")
            self.send_response(101, "Switching Protocols")
            self.send_header("Upgrade", "websocket")
            self.send_header("Connection", "Upgrade")
            self.send_header("Sec-WebSocket-Accept", accept)
            self.end_headers()
            while True:
                frame = _read_ws_frame(self.rfile)
                if frame is None:
                    break
                opcode, payload = frame
                if opcode == 8:
                    _safe_send_ws_frame(self.connection, 8, b"")
                    break
                if opcode == 9:
                    _safe_send_ws_frame(self.connection, 10, payload)
                    continue
                if opcode == 10:
                    continue
                if opcode not in {1, 2}:
                    continue
                try:
                    text = payload.decode("utf-8", errors="replace")
                    data = json.loads(text or "{}")
                except json.JSONDecodeError:
                    _append_event_log({"time": _now(), "ok": False, "transport": "ws", "error": "invalid json", "raw": payload.decode("utf-8", errors="replace")})
                    continue
                _handle_payload(event_bus, data, transport="ws")
            self.close_connection = True

        def log_message(self, format: str, *args) -> None:
            return

    return Handler


_WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
_MAX_WS_FRAME_BYTES = 10 * 1024 * 1024


def _read_ws_frame(stream) -> tuple[int, bytes] | None:
    try:
        header = stream.read(2)
        if len(header) < 2:
            return None
        b1, b2 = header[0], header[1]
        opcode = b1 & 0x0F
        masked = bool(b2 & 0x80)
        length = b2 & 0x7F
        if length == 126:
            raw = stream.read(2)
            if len(raw) < 2:
                return None
            length = int.from_bytes(raw, "big")
        elif length == 127:
            raw = stream.read(8)
            if len(raw) < 8:
                return None
            length = int.from_bytes(raw, "big")
        if length > _MAX_WS_FRAME_BYTES:
            return None
        mask = stream.read(4) if masked else b""
        payload = stream.read(length) if length else b""
        if len(payload) < length:
            return None
        if masked and len(mask) == 4:
            payload = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
        return opcode, payload
    except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, OSError):
        return None


def _safe_send_ws_frame(connection, opcode: int, payload: bytes) -> None:
    try:
        _send_ws_frame(connection, opcode, payload)
    except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, OSError):
        return


def _send_ws_frame(connection, opcode: int, payload: bytes) -> None:
    data = bytes([0x80 | (opcode & 0x0F)])
    length = len(payload)
    if length < 126:
        data += bytes([length])
    elif length <= 0xFFFF:
        data += bytes([126]) + length.to_bytes(2, "big")
    else:
        data += bytes([127]) + length.to_bytes(8, "big")
    connection.sendall(data + payload)


def _handle_payload(event_bus: EventBus, payload: dict[str, object], transport: str) -> None:
    message = parse_onebot_event(payload)
    duplicate = _seen_recent_event(payload)
    _append_event_log(
        {
            "time": _now(),
            "ok": True,
            "transport": transport,
            "duplicate": duplicate,
            "post_type": payload.get("post_type"),
            "message_type": payload.get("message_type") or payload.get("detail_type"),
            "user_id": payload.get("user_id"),
            "group_id": payload.get("group_id"),
            "parsed": bool(message),
            "parsed_type": message.message_type if message else "",
            "parsed_sender": message.sender if message else "",
            "parsed_target": message.target if message else "",
            "parsed_text": message.text if message else "",
            "raw": _compact_payload(payload),
        }
    )
    if duplicate:
        return
    event_bus.publish_plugin_event(plugin_event_from_onebot(payload, message))
    if message:
        event_bus.publish_message(message)


def _seen_recent_event(payload: dict[str, object]) -> bool:
    key = _dedupe_key(payload)
    if not key:
        return False
    with _EVENT_DEDUPE_LOCK:
        if key in _RECENT_EVENT_KEY_SET:
            return True
        _RECENT_EVENT_KEYS.append(key)
        _RECENT_EVENT_KEY_SET.add(key)
        while len(_RECENT_EVENT_KEYS) > _RECENT_EVENT_LIMIT:
            old_key = _RECENT_EVENT_KEYS.popleft()
            _RECENT_EVENT_KEY_SET.discard(old_key)
    return False


def _dedupe_key(payload: dict[str, object]) -> tuple[str, ...] | None:
    post_type = _value_text(payload.get("post_type"))
    if not post_type:
        return None
    self_id = _value_text(payload.get("self_id"))
    message_type = _value_text(payload.get("message_type") or payload.get("detail_type"))
    group_id = _value_text(payload.get("group_id"))
    user_id = _value_text(payload.get("user_id"))
    if post_type == "message":
        message_id = _value_text(payload.get("message_id") or payload.get("message_seq") or payload.get("real_id"))
        if not message_id:
            return None
        return (
            "message",
            self_id,
            message_type,
            group_id,
            user_id,
            message_id,
            _value_text(payload.get("real_id")),
            _value_text(payload.get("message_seq")),
        )
    if post_type == "request":
        flag = _value_text(payload.get("flag"))
        if flag:
            return ("request", self_id, _value_text(payload.get("request_type")), group_id, user_id, flag)
    if post_type == "notice":
        notice_id = _value_text(
            payload.get("message_id")
            or payload.get("target_id")
            or payload.get("operator_id")
            or payload.get("file", {})
        )
        event_time = _value_text(payload.get("time"))
        if notice_id or event_time:
            return (
                "notice",
                self_id,
                _value_text(payload.get("notice_type")),
                _value_text(payload.get("sub_type")),
                group_id,
                user_id,
                notice_id,
                event_time,
            )
    if post_type == "meta_event":
        event_time = _value_text(payload.get("time"))
        if event_time:
            return (
                "meta_event",
                self_id,
                _value_text(payload.get("meta_event_type")),
                _value_text(payload.get("sub_type")),
                event_time,
            )
    return None


def _value_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except TypeError:
        return str(value)


def _append_event_log(entry: dict[str, object]) -> None:
    ensure_runtime_dirs()
    path = LOG_HOME / "onebot_events.jsonl"
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    with _EVENT_LOG_LOCK:
        with path.open("a", encoding="utf-8") as file:
            file.write(line)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _compact_payload(payload: dict[str, object], limit: int = 1200) -> str:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(raw) <= limit:
        return raw
    return raw[:limit] + "...(truncated)"


def _bind_server(host: str, port: int, handler: type[BaseHTTPRequestHandler]) -> ThreadingHTTPServer:
    if port == 0:
        return ThreadingHTTPServer((host, port), handler)
    last_error: OSError | None = None
    for candidate in range(port, port + 10):
        if _port_is_listening(host, candidate):
            continue
        try:
            return ThreadingHTTPServer((host, candidate), handler)
        except OSError as exc:
            if exc.errno not in {10048, 98, socket.EADDRINUSE}:
                raise
            last_error = exc
    if last_error:
        raise last_error
    raise OSError("No available OneBot event gateway port")


def _port_is_listening(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.2):
            return True
    except OSError:
        return False

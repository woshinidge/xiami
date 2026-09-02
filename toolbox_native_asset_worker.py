from __future__ import annotations

"""Persistent binary transport for the native NPC asset worker."""

import json
import os
import re
import struct
import subprocess
import threading
import time
from concurrent.futures import Future, TimeoutError as FutureTimeoutError
from pathlib import Path
from typing import Dict, Optional, Tuple


MAGIC = b"XAW1"
PROTOCOL_VERSION = 1
HEADER = struct.Struct("<4sHHIQQ")
MAX_CONTROL_PAYLOAD = 1024 * 1024

HELLO = 1
PING = 2
PONG = 3
SHUTDOWN = 4
SHUTDOWN_ACK = 5
ERROR = 6
AUTHORIZE_OPEN = 10
CHALLENGE = 11
AUTHORIZE_COMMIT = 12
OPEN_RESULT = 13
CLOSE_ASSET = 14
CLOSE_RESULT = 15
STATS = 16
STATS_RESULT = 17
LIST_RECORDS = 20
RECORDS_RESULT = 21
DECODE_IMAGE = 22
PIXELS_INLINE = 23
RELEASE_BUFFER = 24
RELEASE_RESULT = 25
PIXELS_MAPPING = 26
PREFETCH_IMAGES = 27
PREFETCH_RESULT = 28
BUILD_ITEM_TOOLTIP = 29
TOOLTIP_RESULT = 30
OPEN_LOCAL_TOOLTIP = 31

_FRAME_TYPES = {
    HELLO, PING, PONG, SHUTDOWN, SHUTDOWN_ACK, ERROR,
    AUTHORIZE_OPEN, CHALLENGE, AUTHORIZE_COMMIT, OPEN_RESULT,
    CLOSE_ASSET, CLOSE_RESULT, STATS, STATS_RESULT, LIST_RECORDS, RECORDS_RESULT,
    DECODE_IMAGE, PIXELS_INLINE, RELEASE_BUFFER, RELEASE_RESULT, PIXELS_MAPPING,
    PREFETCH_IMAGES, PREFETCH_RESULT, BUILD_ITEM_TOOLTIP, TOOLTIP_RESULT,
    OPEN_LOCAL_TOOLTIP,
}
_REQUEST_TYPES = {
    PING, SHUTDOWN, AUTHORIZE_OPEN, AUTHORIZE_COMMIT, CLOSE_ASSET, STATS,
    LIST_RECORDS, DECODE_IMAGE, RELEASE_BUFFER, PREFETCH_IMAGES, BUILD_ITEM_TOOLTIP,
    OPEN_LOCAL_TOOLTIP,
}


class NativeAssetWorkerError(RuntimeError):
    pass


class NativeAssetWorkerProtocolError(NativeAssetWorkerError):
    pass


class NativeAssetWorkerStaleHandle(NativeAssetWorkerError):
    pass


def _default_executable() -> str:
    from toolbox_native_core import _native_core_path

    return str(_native_core_path())


def _read_exact(stream, size: int) -> bytes:
    if size < 0 or size > MAX_CONTROL_PAYLOAD:
        raise NativeAssetWorkerProtocolError("native asset frame size is invalid")
    chunks = bytearray()
    while len(chunks) < size:
        chunk = stream.read(size - len(chunks))
        if not chunk:
            raise NativeAssetWorkerProtocolError("native asset frame is truncated")
        chunks.extend(chunk)
    return bytes(chunks)


def _read_frame(stream) -> Tuple[int, int, int, bytes]:
    raw = _read_exact(stream, HEADER.size)
    magic, version, frame_type, flags, request_id, payload_size = HEADER.unpack(raw)
    if magic != MAGIC or version != PROTOCOL_VERSION:
        raise NativeAssetWorkerProtocolError("native asset frame header is invalid")
    if frame_type not in _FRAME_TYPES:
        raise NativeAssetWorkerProtocolError("native asset frame type is unsupported")
    if request_id == 0 or payload_size > MAX_CONTROL_PAYLOAD:
        raise NativeAssetWorkerProtocolError("native asset frame identifier or payload is invalid")
    return frame_type, flags, request_id, _read_exact(stream, int(payload_size))


def _encode_frame(frame_type: int, request_id: int, payload: bytes = b"", flags: int = 0) -> bytes:
    payload = bytes(payload)
    if frame_type not in _REQUEST_TYPES or request_id <= 0 or len(payload) > MAX_CONTROL_PAYLOAD:
        raise NativeAssetWorkerProtocolError("native asset request frame is invalid")
    return HEADER.pack(MAGIC, PROTOCOL_VERSION, frame_type, flags, request_id, len(payload)) + payload


class NativeAssetWorkerBroker:
    def __init__(self, executable: Optional[str] = None, timeout: float = 10.0) -> None:
        self._executable = str(executable or _default_executable())
        self._timeout = max(0.1, float(timeout))
        self._state_lock = threading.RLock()
        self._write_lock = threading.Lock()
        self._authorization_lock = threading.RLock()
        self._pending: Dict[int, Future] = {}
        self._abandoned = set()
        self._process: Optional[subprocess.Popen] = None
        self._reader: Optional[threading.Thread] = None
        self._request_id = 1
        self._generation = 0
        self._hello = b""
        self._closing = False
        self._heartbeat_stop = threading.Event()
        self._heartbeat: Optional[threading.Thread] = None

    @property
    def generation(self) -> int:
        with self._state_lock:
            return self._generation

    @property
    def pid(self) -> Optional[int]:
        with self._state_lock:
            return self._process.pid if self._process is not None else None

    @property
    def hello(self) -> str:
        with self._state_lock:
            return self._hello.decode("utf-8", errors="strict")

    def start(self) -> int:
        with self._state_lock:
            if self._process is not None and self._process.poll() is None:
                return self._generation
            path = Path(self._executable)
            if not path.is_file():
                raise NativeAssetWorkerError("native asset worker executable is missing")
            self._closing = False
            process = subprocess.Popen(
                [str(path), "--asset-worker", "--input", "-", "--output", "-"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
                close_fds=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            try:
                frame_type, _flags, request_id, payload = _read_frame(process.stdout)
                if frame_type != HELLO or request_id != 1:
                    raise NativeAssetWorkerProtocolError("native asset worker hello is invalid")
            except Exception:
                process.kill()
                process.wait(timeout=2.0)
                raise
            self._process = process
            self._generation += 1
            self._hello = payload
            self._reader = threading.Thread(
                target=self._reader_loop,
                args=(process, self._generation),
                name="xiami-native-asset-reader",
                daemon=True,
            )
            self._reader.start()
            if self._heartbeat is None or not self._heartbeat.is_alive():
                self._heartbeat_stop.clear()
                self._heartbeat = threading.Thread(
                    target=self._heartbeat_loop,
                    name="xiami-native-asset-heartbeat",
                    daemon=True,
                )
                self._heartbeat.start()
            return self._generation

    def authorization_transaction(self):
        """Serialize AUTHORIZE_OPEN -> server consume -> AUTHORIZE_COMMIT."""
        return self._authorization_lock

    def request(
        self,
        frame_type: int,
        payload: bytes = b"",
        timeout: Optional[float] = None,
        *,
        terminate_on_timeout: bool = True,
    ) -> Tuple[int, bytes]:
        self.start()
        with self._state_lock:
            process = self._process
            if process is None or process.poll() is not None or process.stdin is None:
                raise NativeAssetWorkerError("native asset worker is unavailable")
            self._request_id += 1
            request_id = self._request_id
            future = Future()
            self._pending[request_id] = future
        try:
            frame = _encode_frame(frame_type, request_id, payload)
            with self._write_lock:
                process.stdin.write(frame)
                process.stdin.flush()
            result_type, result_payload = future.result(timeout=self._timeout if timeout is None else timeout)
            if result_type == ERROR:
                raise NativeAssetWorkerProtocolError(result_payload.decode("utf-8", errors="replace"))
            return result_type, result_payload
        except FutureTimeoutError as exc:
            with self._state_lock:
                self._pending.pop(request_id, None)
                if not terminate_on_timeout:
                    self._abandoned.add(request_id)
            if terminate_on_timeout:
                self._terminate_broken(
                    process,
                    NativeAssetWorkerError("native asset worker request timed out"),
                )
            raise NativeAssetWorkerError("native asset worker request timed out") from exc
        except Exception:
            with self._state_lock:
                self._pending.pop(request_id, None)
            raise

    def ping(
        self,
        payload: bytes = b"ping",
        timeout: Optional[float] = None,
        *,
        terminate_on_timeout: bool = True,
    ) -> bytes:
        response_type, response_payload = self.request(
            PING,
            payload,
            timeout,
            terminate_on_timeout=terminate_on_timeout,
        )
        if response_type != PONG:
            raise NativeAssetWorkerProtocolError("native asset worker returned an invalid ping response")
        return response_payload

    def assert_generation(self, generation: int) -> None:
        self.start()
        if int(generation) != self.generation:
            raise NativeAssetWorkerStaleHandle("native asset handle belongs to an expired worker generation")

    def close_asset(self, handle: str, generation: int) -> None:
        self.assert_generation(generation)
        response_type, response_payload = self.request(CLOSE_ASSET, handle.encode("ascii"))
        if response_type != CLOSE_RESULT or response_payload != b"ok":
            raise NativeAssetWorkerProtocolError("native asset worker did not close the asset")

    def stats(self) -> Dict[str, int]:
        response_type, payload = self.request(STATS)
        if response_type != STATS_RESULT:
            raise NativeAssetWorkerProtocolError("native asset worker returned invalid stats")
        result: Dict[str, int] = {}
        for line in payload.decode("ascii", errors="strict").splitlines():
            name, value = line.split("=", 1)
            result[name] = int(value)
        return result

    def list_records(self, handle: str, generation: int, index_handle: Optional[str] = None) -> bytes:
        self.assert_generation(generation)
        request_payload = handle if not index_handle else handle + "\n" + index_handle
        response_type, payload = self.request(LIST_RECORDS, request_payload.encode("ascii"))
        if response_type != RECORDS_RESULT:
            raise NativeAssetWorkerProtocolError("native asset worker returned invalid records")
        return payload

    def decode_image(self, handle: str, generation: int, index: int, index_handle: Optional[str] = None) -> Tuple[int, int, int, int, int, bytes]:
        self.assert_generation(generation)
        request_text = handle + "\n" + (index_handle + "\n" if index_handle else "") + str(int(index))
        payload = request_text.encode("ascii")
        response_type, raw = self.request(DECODE_IMAGE, payload)
        if response_type == PIXELS_MAPPING:
            fields = {}
            for line in raw.decode("ascii", errors="strict").splitlines():
                name, value = line.split("=", 1)
                fields[name] = value
            required = {"name", "size", "width", "height", "stride", "origin_x", "origin_y"}
            if not required.issubset(fields):
                raise NativeAssetWorkerProtocolError("native asset mapping metadata is incomplete")
            import mmap
            mapping_name = fields["name"]
            size = int(fields["size"])
            with mmap.mmap(-1, size, tagname=mapping_name, access=mmap.ACCESS_READ) as mapping:
                pixels = mapping[:]
            release_type, release_payload = self.request(RELEASE_BUFFER, mapping_name.encode("ascii"))
            if release_type != RELEASE_RESULT or release_payload != b"ok":
                raise NativeAssetWorkerProtocolError("native asset mapping release failed")
            return (int(fields["width"]), int(fields["height"]), int(fields["stride"]),
                    int(fields["origin_x"]), int(fields["origin_y"]), pixels)
        if response_type != PIXELS_INLINE or len(raw) < 28:
            raise NativeAssetWorkerProtocolError("native asset worker returned invalid pixels")
        width, height, stride, origin_x, origin_y, data_size = struct.unpack_from("<IIIiiI", raw, 0)
        pixels = raw[28:]
        if data_size != len(pixels) or stride * height != data_size:
            raise NativeAssetWorkerProtocolError("native asset pixels size is invalid")
        return width, height, stride, origin_x, origin_y, pixels

    def prefetch_images(
        self,
        handle: str,
        generation: int,
        indexes,
        index_handle: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> int:
        self.assert_generation(generation)
        normalized = [int(value) for value in indexes]
        if len(normalized) > 256 or any(value < 0 for value in normalized):
            raise NativeAssetWorkerProtocolError("native asset prefetch indexes are invalid")
        payload = (
            handle + "\n" + (index_handle or "") + "\n" + ",".join(map(str, normalized))
        ).encode("ascii")
        response_type, raw = self.request(PREFETCH_IMAGES, payload, timeout)
        if response_type != PREFETCH_RESULT:
            raise NativeAssetWorkerProtocolError("native asset worker returned invalid prefetch result")
        text = raw.decode("ascii", errors="strict")
        if not text.startswith("cached="):
            raise NativeAssetWorkerProtocolError("native asset prefetch result is malformed")
        return int(text[7:])

    def build_item_tooltip(
        self,
        dataset_handle: str,
        generation: int,
        item_id: int,
        timeout: Optional[float] = None,
    ) -> bytes:
        """Request a tooltip DTO from an already-authorized native dataset."""
        self.assert_generation(generation)
        if not isinstance(dataset_handle, str) or re.fullmatch(r"[0-9a-f]{32}", dataset_handle) is None:
            raise NativeAssetWorkerProtocolError("native tooltip dataset handle is invalid")
        if isinstance(item_id, bool) or not isinstance(item_id, int) or not 0 <= item_id <= 2147483647:
            raise NativeAssetWorkerProtocolError("native tooltip item identifier is invalid")
        try:
            payload = json.dumps(
                {
                    "schema_version": 1,
                    "action": "build_item_tooltip",
                    "dataset_handle": dataset_handle,
                    "item_id": item_id,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8", errors="strict")
        except (TypeError, ValueError, UnicodeError) as exc:
            raise NativeAssetWorkerProtocolError("native tooltip request JSON is invalid") from exc
        if len(payload) > 4096:
            raise NativeAssetWorkerProtocolError("native tooltip request JSON is too large")
        response_type, raw = self.request(BUILD_ITEM_TOOLTIP, payload, timeout)
        if response_type != TOOLTIP_RESULT:
            raise NativeAssetWorkerProtocolError("native asset worker returned an invalid tooltip result")
        try:
            raw.decode("utf-8", errors="strict")
        except UnicodeError as exc:
            raise NativeAssetWorkerProtocolError("native tooltip result is not valid UTF-8") from exc
        return raw

    def open_local_tooltip_data(
        self,
        payload: bytes,
        timeout: Optional[float] = None,
    ) -> bytes:
        """Open a locally validated tooltip dataset without a server lease."""
        if not isinstance(payload, (bytes, bytearray)) or not 0 < len(payload) <= MAX_CONTROL_PAYLOAD:
            raise NativeAssetWorkerProtocolError("native local tooltip request is invalid")
        response_type, raw = self.request(OPEN_LOCAL_TOOLTIP, bytes(payload), timeout)
        if response_type != OPEN_RESULT:
            raise NativeAssetWorkerProtocolError(
                "native asset worker did not open the local tooltip dataset"
            )
        return raw

    def close(self) -> None:
        with self._state_lock:
            process = self._process
            if process is None:
                return
            self._closing = True
            self._heartbeat_stop.set()
        if process.poll() is None:
            try:
                response_type, _payload = self.request(SHUTDOWN, timeout=min(self._timeout, 2.0))
                if response_type != SHUTDOWN_ACK:
                    raise NativeAssetWorkerProtocolError("native asset worker rejected shutdown")
            except Exception:
                process.kill()
        try:
            process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2.0)
        self._mark_broken(process, NativeAssetWorkerError("native asset worker closed"))

    def restart_once(self) -> int:
        self.close()
        return self.start()

    def _reader_loop(self, process: subprocess.Popen, generation: int) -> None:
        failure: Exception = NativeAssetWorkerError("native asset worker stopped")
        try:
            while True:
                frame_type, _flags, request_id, payload = _read_frame(process.stdout)
                with self._state_lock:
                    if generation != self._generation:
                        return
                    future = self._pending.pop(request_id, None)
                    abandoned = request_id in self._abandoned
                    if abandoned:
                        self._abandoned.discard(request_id)
                if future is None:
                    if abandoned:
                        continue
                    raise NativeAssetWorkerProtocolError("native asset response request id is unknown")
                future.set_result((frame_type, payload))
        except Exception as exc:
            failure = exc
        finally:
            self._mark_broken(process, failure)

    def _heartbeat_loop(self) -> None:
        while not self._heartbeat_stop.wait(15.0):
            with self._state_lock:
                if self._pending:
                    continue
            try:
                self.ping(
                    b"heartbeat",
                    timeout=min(self._timeout, 3.0),
                    terminate_on_timeout=False,
                )
            except Exception:
                continue

    def _mark_broken(self, process: subprocess.Popen, failure: Exception) -> None:
        with self._state_lock:
            if self._process is not process:
                return
            self._process = None
            pending = list(self._pending.values())
            self._pending.clear()
            self._abandoned.clear()
        for future in pending:
            if not future.done():
                future.set_exception(failure)
        for stream in (process.stdin, process.stdout, process.stderr):
            try:
                if stream is not None:
                    stream.close()
            except Exception:
                pass

    def _terminate_broken(self, process: subprocess.Popen, failure: Exception) -> None:
        self._mark_broken(process, failure)
        if process.poll() is None:
            try:
                process.kill()
            except Exception:
                pass
        try:
            process.wait(timeout=2.0)
        except Exception:
            pass

    def __enter__(self) -> "NativeAssetWorkerBroker":
        self.start()
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.close()


__all__ = [
    "BUILD_ITEM_TOOLTIP",
    "OPEN_LOCAL_TOOLTIP",
    "NativeAssetWorkerBroker",
    "NativeAssetWorkerError",
    "NativeAssetWorkerProtocolError",
    "NativeAssetWorkerStaleHandle",
    "TOOLTIP_RESULT",
]

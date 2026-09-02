"""PAK/WIL/WZL/WIS 素材读取、解密与预览图像解码。"""
from __future__ import annotations

import base64
import hashlib
import os
import struct
import threading
import zlib
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from PIL import Image
from cryptography.hazmat.primitives.ciphers import Cipher, modes
from cryptography.hazmat.primitives.ciphers import algorithms as primitive_algorithms
try:
    from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
except ImportError:
    from cryptography.hazmat.primitives.ciphers.algorithms import TripleDES
MASK32 = 4294967295
PAK_IMAGE_HEADER_SIZE = 16
PAK_HEADER_SIZE = 256
WZL_DATA_HEADER_SIZE = 64
WZX_HEADER_SIZE = 48
BITS_BY_TYPE = { 3: 8, 4: 16, 5: 16, 6: 24, 7: 32, 9: 32}
RECOVERED_KINDS = {"recovered_pak", "recovered_wzl", "recovered_wil", "recovered_wis"}
ALLOW_LEGACY_WIL_BGRA32_ENV = "CW_ALLOW_LEGACY_WIL_BGRA32"
PAYLOAD_FILE_CACHE_MAX_BYTES = 268435456
PAYLOAD_FILE_CACHE_MAX_BYTES_ENV = "CW_PAYLOAD_FILE_CACHE_MAX_BYTES"
_MIR_INDEXED8_PALETTE = None
_MIR_INDEXED8_PALETTE: tuple[tuple[int, int, int, int], ...] | None
_PAYLOAD_FILE_CACHE = OrderedDict()
_PAYLOAD_FILE_CACHE_BYTES = 0
_PAYLOAD_FILE_CACHE_HITS = 0
_PAYLOAD_FILE_CACHE_MISSES = 0
_PAYLOAD_FILE_CACHE_LOCK = threading.RLock()
_ROT = base64.b64decode("AAABAQEBAQEAAQEBAQEBAA==")
_KEY_TABLE = struct.unpack("<512I", base64.b64decode("AAAAABAAAAAAAAAgEAAAIAAAAQAQAAEAAAABIBAAASAACAAAEAgAAAAIACAQCAAgAAgBABAIAQAACAEgEAgBICAAAAAwAAAAIAAAIDAAACAgAAEAMAABACAAASAwAAEgIAgAADAIAAAgCAAgMAgAICAIAQAwCAEAIAgBIDAIASAAAAgAEAAIAAAACCAQAAggAAAJABAACQAAAAkgEAAJIAAICAAQCAgAAAgIIBAICCAACAkAEAgJAAAICSAQCAkgIAAIADAACAAgAAggMAAIICAACQAwAAkAIAAJIDAACSAgCAgAMAgIACAICCAwCAggIAgJADAICQAgCAkgMAgJIAAAAAAAAAACACAAAAAgAAIAACAAAAAgAgAgIAAAICACBAAAAAQAAAIEIAAABCAAAgQAIAAEACACBCAgAAQgIAIABAAAAAQAAgAkAAAAJAACAAQgAAAEIAIAJCAAACQgAgQEAAAEBAACBCQAAAQkAAIEBCAABAQgAgQkIAAEJCACAAAAEAAAABIAIAAQACAAEgAAIBAAACASACAgEAAgIBIEAAAQBAAAEgQgABAEIAASBAAgEAQAIBIEICAQBCAgEgAEABAABAASACQAEAAkABIABCAQAAQgEgAkIBAAJCASBAQAEAQEABIEJAAQBCQAEgQEIBAEBCASBCQgEAQkIBIAAAAAAQAAAAAABAABAAQAAAAAAQEAAAEAAAQBAQAEAQIAAAADAAAAAgAEAAMABAACAAABAwAAAQIABAEDAAQBAAIAAAECAAAAAgQAAQIEAAACAAEBAgABAAIEAQECBAECAgAAAwIAAAICBAADAgQAAgIAAQMCAAECAgQBAwIEAQAAAAgBAAAIAAAECAEABAgAAAAJAQAACQAABAkBAAQJAgAACAMAAAgCAAQIAwAECAIAAAkDAAAJAgAECQMABAkAAgAIAQIACAACBAgBAgQIAAIACQECAAkAAgQJAQIECQICAAgDAgAIAgIECAMCBAgCAgAJAwIACQICBAkDAgQJAAAAAAAAEAAAAQAAAAEQAAgAAAAIABAACAEAAAgBEAAAEAAAABAQAAARAAAAERAACBAAAAgQEAAIEQAACBEQAAAAAAQAABAEAAEABAABEAQIAAAECAAQBAgBAAQIARAEABAABAAQEAQAEQAEABEQBAgQAAQIEBAECBEABAgREAQAAAIAAAASAAABAgAAARIACAACAAgAEgAIAQIACAESAAAQAgAAEBIAABECAAAREgAIEAIACBASAAgRAgAIERIAAAACBAAAEgQAAQIEAAESBAgAAgQIABIECAECBAgBEgQAEAIEABASBAARAgQAERIECBACBAgQEgQIEQIECBESBAAAAAAAAAAQAAABAAAAARAEAAAABAAAEAQAAQAEAAEQAAAAIAAAADAAAAEgAAABMAQAACAEAAAwBAABIAQAATAAABAAAAAQEAAAEQAAABEQBAAQAAQAEBAEABEABAAREAAAECAAABAwAAARIAAAETAEABAgBAAQMAQAESAEABEwABAAAAAQABAAEAEAABABEAQQAAAEEAAQBBABAAQQARAAEAAgABAAMAAQASAAEAEwBBAAIAQQADAEEAEgBBABMAAQEAAAEBAQABARAAAQERAEEBAABBAQEAQQEQAEEBEQABAQIAAQEDAAEBEgABARMAQQECAEEBAwBBARIAQQETAAAAAAAAAACAgAAAAIAAAIAAQAAAAEAAgIBAAACAQACAAAAgAAAAIICAACAAgAAggABAIAAAQCCAgEAgAIBAIIAQAAAAEAAAgJAAAACQAACAEEAAABBAAICQQAAAkEAAgBAAIAAQACCAkAAgAJAAIIAQQCAAEEAggJBAIACQQCCAAAAAIAAAAKCAAAAggAAAoABAACAAQACggEAAIIBAAKAAACAgAAAgoIAAICCAACCgAEAgIABAIKCAQCAggEAgoBAAACAQAACgkAAAIJAAAKAQQAAgEEAAoJBAACCQQACgEAAgIBAAIKCQACAgkAAgoBBAICAQQCCgkEAgIJBAIKAAAAAAABAAAAAAgAAAEIAAAAAAEAAQABAAAIAQABCAEQAAAAEAEAABAACAAQAQgAEAAAARABAAEQAAgBEAEIAQAAIAAAASAAAAAoAAABKAAAACABAAEgAQAAKAEAASgBEAAgABABIAAQACgAEAEoABAAIAEQASABEAAoARABKAEAAgAAAAMAAAACCAAAAwgAAAIAAQADAAEAAggBAAMIARACAAAQAwAAEAIIABADCAAQAgABEAMAARACCAEQAwgBAAIgAAADIAAAAigAAAMoAAACIAEAAyABAAIoAQADKAEQAiAAEAMgABACKAAQAygAEAIgARADIAEQAigBEAMoAQAAAAAAAAAEAAAEAAAABAQCAAAAAgAABAIABAACAAQEACAAAAAgAAQAIAQAACAEBAIgAAACIAAEAiAEAAIgBAQgAAAAIAAABCAABAAgAAQEIgAAACIAAAQiAAQAIgAEBCAgAAAgIAAEICAEACAgBAQiIAAAIiAABCIgBAAiIAQEAAgAAAAIAAQACAQAAAgEBAIIAAACCAAEAggEAAIIBAQAKAAAACgABAAoBAAAKAQEAigAAAIoAAQCKAQAAigEBCAIAAAgCAAEIAgEACAIBAQiCAAAIggABCIIBAAiCAQEICgAACAoAAQgKAQAICgEBCIoAAAiKAAEIigEACIoBAQ="))
_SP_TABLE = struct.unpack("<512I", base64.b64decode("AAgIAgAACAACAAACAggIAgAAAAICCAgAAgAIAAIAAAICCAgAAAgIAgAACAICCAAAAggAAgAAAAIAAAAAAgAIAAAACAACAAAAAAgAAgAICAACCAgCAAAIAgIIAAAACAACAgAAAAAIAAAACAgAAgAIAgAIAAACCAACAgAIAgAAAAAAAAAAAggIAgAIAAICAAgAAAgIAgAACAACCAAAAAgAAgIACAIACAAAAAgIAAIAAAICCAgAAgAAAAIAAAIAAAgCAggIAgAICAAAAAgCAggAAgAAAAICCAAAAgAIAAAAAAAAAAgAAAAAAgIIAAIACAgCAgAAAAIACAIACAAAAggIABCAEEAAAAAAAIAQAAAAEEAQAABAEIAAAACAAEAAgBAAAIAAABAAEEAQAAAAAIAAQBAAEAAAgBBAAAAQQBAAAAAAABAAEIAAQBAAEEAAgAAAEIAQAAAAAEAAAAAAEAAQABCAAEAQgBAAAIAQQBAAAEAAAABAAAAQABCAAAAQgBBAEAAQAACAEEAAgABAEIAQABCAEEAQABAAEAAAQAAAAAAAAABAEIAAAAAAEAAQABBAAIAAAAAAAEAQgBAAEIAAQACAEEAAgAAAAAAAABAAAEAQAAAAEIAQQACAEAAAABBAEAAQQAAAEAAQgAAAAIAAQBCAAEAQAAAAAAAQQACAEAABAAAEAAEEBAABAAABAQAEAQAEAAAAAAQBAQAEAAEEAAABAAQAAAQAAAAEBAEAAAABAQQEAQEAAAEAAAABAAQEAAAAAAEABAAAAQQEAAEAAAEBAAABAQQEAAAEAAEAAAQBAAQEAAEABAEBBAAAAAQEAAEEAAAAAAAAAAAEAQEEAAABBAQAAQAAAQAAAAAABAABAQAAAQAEAAAABAQBAQAEAAAAAAABBAQAAQQAAQAEBAEABAAAAAAEAQEEBAEAAAABAQQAAQAABAAAAAQBAQQEAAAEAAABAAQBAQAEAAEEAAABAAQAAAAAAQAEBAEBAAABAAAEAQEEAAABAAAAAAQECBBAAAAQABAIAAAACBBAEAAAAAAAAEAQCBAAEAgAQAAAEEAQCAAAEAAAABAIEAAACAAAEAgQQAAAAEAAAAAAEAgAQBAAEEAAABAAAAgAAAAAEEAACBAAEAAAQBAAEAAACBAAAAAAAAAIAEAAABBAEAAQABAIAEAQCBBAEAAAQAAIAEAQCBAAAAAAQAAIAAAQABBAAAAQABAIAAAAAABAEAgQABAAAAAAABAAAAgAQAAAAAAACABAEAAQQBAAEAAAAAAAEAgQQBAIEEAAAABAAAgQQBAIAAAAABAAEAgQQAAIAEAAABBAAAAAQBAIEAAQCBAAAAAAABAIAAAQABBAEAAAAAgAAAEAAAQAACAEAQggAAEIAAQACCAEAQAAAAEIAAABACAAAAAgAAAIAAQBACAEAAggAAEIAAQBCAAAAAAABAEAAAAACCAAAQAgBAAAAAQACCAEAQAAAAAAIAAACCAAAAAgBAAIIAQBCCAAAQAAAAEIAAQAACAEAAAABAEIAAQBCCAEAAggAAEAAAABCAAAAQAgAAAAIAAACAAEAAgAAAAIAAQBACAEAQgAAAAAIAQBAAAAAAgABAAAIAABACAEAAgABAAAAAAAACAEAQggAAEIAAQBCCAEAAAAAAEAAAQBACAAAQgABAAIIAQAACAAAAAgBAEAAAABCCAAAAhAAACAQAAgAAAAAAAAICCAQAAgAAAgAABAIACAAAAgAEAgAABAICCAACAgAAAAAIAAIACAQAAAgAAAIIBAICAAAAAgAEAgAIBAACCAAAAAAAAgAABAAAAAACAggEAAIIBAICCAAAAggAAAAIBAIAAAQAAAAAAgIABAICAAACAAgEAgAAAAAACAACAAgEAgIAAAICCAQAAgAAAAAAAAIACAAAAAgAAgAABAACCAAAAgAEAAIABAICCAACAgAEAAAABAICCAACAgAAAAIABAIACAQAAAgAAAIIBAICAAAAAAAAAgAABAAACAQCAAgAAgIIAAACCAQCAAAEAAAABAACCAAEAAAAACAAAAAgABBAAAAQRCAAEEQAAAAEIAAAAAAAAAAAABBAIAAQQCAAAAQAABBAAAAABCAAEAQAABBAIAAAQCAAEAQAAABEAAAARCAAEAAAAAAAIAAQQAAAEAQgAABEAAAQRCAAAAQgABBAAAAARCAAAEQAABAAIAAAAAAAEEQgAAAEAAAQRAAAEEAgAAAEAAAAACAAAAAAABBEAAAQQCAAEEQgAAAEIAAAAAAAAAAgAABAAAAQQAAAAAAgABAAAAAAQCAAEAAgABAEIAAAQCAAAAQAAABEIAAQAAAAEAQgABBAAAAARAAAAEQgABBAAAAQBCAAEAQAABBEAAAIAAgCAAAIIggAACAAAAAAAAAAIggACAAAAAgCCAAIIggAAAAAAAACAAAIIAgAACAIAAggCAAAIggAAAIAAAgCAAAAIAgACCAIAAgAAAAAIggACCIIAAACAAAAAAAACCAAAAACAAAIAAgAACIIAAgCAAAIAAAAACAAAAgiCAAAAAAACAAAAAAgCAAAAggACCIIAAAgAAAAAgAAAAAAAAggCAAIAggAACIAAAAiCAAIAAAACCIIAAAACAAIAAAAACIIAAgiAAAIAAAACAIIAAACAAAIIAgAACAIAAAiAAAIAggAAAAAAAgiCAAIIAAAAAAAAAACCAAIAgAAACAIAAggA="))


def _payload_file_cache_limit() -> int:
    raw = os.environ.get(PAYLOAD_FILE_CACHE_MAX_BYTES_ENV, "")
    try:
        value = int(raw) if raw.strip() else PAYLOAD_FILE_CACHE_MAX_BYTES
    except ValueError:
        value = PAYLOAD_FILE_CACHE_MAX_BYTES
    return max(0, value)


def _payload_file_cache_key(path: Path) -> tuple[str, int, int]:
    resolved = Path(path).resolve()
    stat_result = resolved.stat()
    return (str(resolved), int(stat_result.st_size), int(stat_result.st_mtime_ns))


def _read_payload_slice(path: Path, offset: int, length: int) -> bytes:
    global _PAYLOAD_FILE_CACHE_BYTES, _PAYLOAD_FILE_CACHE_HITS, _PAYLOAD_FILE_CACHE_MISSES
    offset = max(0, int(offset))
    length = int(length)
    key = _payload_file_cache_key(Path(path))
    limit = _payload_file_cache_limit()
    if limit <= 0 or key[1] > limit:
        with _PAYLOAD_FILE_CACHE_LOCK:
            _PAYLOAD_FILE_CACHE_MISSES += 1
        with Path(key[0]).open("rb") as handle:
            handle.seek(offset)
            return handle.read(length)

    with _PAYLOAD_FILE_CACHE_LOCK:
        cached = _PAYLOAD_FILE_CACHE.get(key)
        if cached is not None:
            _PAYLOAD_FILE_CACHE.move_to_end(key)
            _PAYLOAD_FILE_CACHE_HITS += 1
            return cached[offset:] if length < 0 else cached[offset:offset + length]

    data = Path(key[0]).read_bytes()
    with _PAYLOAD_FILE_CACHE_LOCK:
        previous = _PAYLOAD_FILE_CACHE.pop(key, None)
        if previous is not None:
            _PAYLOAD_FILE_CACHE_BYTES -= len(previous)
        _PAYLOAD_FILE_CACHE[key] = data
        _PAYLOAD_FILE_CACHE_BYTES += len(data)
        _PAYLOAD_FILE_CACHE_MISSES += 1
        while _PAYLOAD_FILE_CACHE and _PAYLOAD_FILE_CACHE_BYTES > limit:
            _old_key, old_data = _PAYLOAD_FILE_CACHE.popitem(last=False)
            _PAYLOAD_FILE_CACHE_BYTES -= len(old_data)
    return data[offset:] if length < 0 else data[offset:offset + length]


def clear_payload_file_cache() -> None:
    global _PAYLOAD_FILE_CACHE_BYTES, _PAYLOAD_FILE_CACHE_HITS, _PAYLOAD_FILE_CACHE_MISSES
    with _PAYLOAD_FILE_CACHE_LOCK:
        _PAYLOAD_FILE_CACHE.clear()
        _PAYLOAD_FILE_CACHE_BYTES = 0
        _PAYLOAD_FILE_CACHE_HITS = 0
        _PAYLOAD_FILE_CACHE_MISSES = 0


def payload_file_cache_stats() -> tuple[int, int, int, int, int]:
    with _PAYLOAD_FILE_CACHE_LOCK:
        return (
            len(_PAYLOAD_FILE_CACHE),
            _PAYLOAD_FILE_CACHE_BYTES,
            _payload_file_cache_limit(),
            _PAYLOAD_FILE_CACHE_HITS,
            _PAYLOAD_FILE_CACHE_MISSES,
        )

@dataclass(frozen=True)
class RecoveredImageHeader:
    image_type: int
    flag1: int
    flag2: int
    alpha: int
    width: int
    height: int
    offset_x: int
    offset_y: int
    packed_size: int

    @classmethod
    def decode(cls, data: bytes) -> "'RecoveredImageHeader'":
        if len(data) != PAK_IMAGE_HEADER_SIZE:
            raise ValueError("image header must be 16 bytes")
        return cls(image_type=(data[0]),
          flag1=(data[1]),
          flag2=(data[2]),
          alpha=(data[3]),
          width=int.from_bytes((data[4:6]), "little", signed=True),
          height=int.from_bytes((data[6:8]), "little", signed=True),
          offset_x=int.from_bytes((data[8:10]), "little", signed=True),
          offset_y=int.from_bytes((data[10:12]), "little", signed=True),
          packed_size=int.from_bytes((data[12:16]), "little", signed=True))

    @property
    def bits(self) -> int:
        bits = BITS_BY_TYPE.get(self.image_type)
        if bits is None:
            raise ValueError(f"unsupported image type: {self.image_type}")
        return bits

    @property
    def is_packed(self) -> bool:
        return self.packed_size > 0

    @property
    def color_stride(self) -> int:
        return dib_stride(self.bits, self.width)

    @property
    def alpha_stride(self) -> int:
        return dib_stride(8, self.width)

    @property
    def raw_payload_size(self) -> int:
        color_size = self.color_stride * max(0, self.height)
        if self.alpha:
            color_size += self.alpha_stride * max(0, self.height)
        return color_size

    @property
    def stored_payload_size(self) -> int:
        if self.packed_size > 0:
            return self.packed_size
        return self.raw_payload_size


def _u32(value: int) -> int:
    return value & MASK32


def _rol32(value: int, bits: int) -> int:
    bits &= 31
    return _u32(value << bits | value >> 32 - bits)


def _ror32(value: int, bits: int) -> int:
    bits &= 31
    return value >> bits | value << 32 - bits & MASK32


def _ror28(value: int, bits: int) -> int:
    return (value >> bits | value << 28 - bits) & 268435455


def _swap_right(a, b, mask, shift):
    temp = (a >> shift ^ b) & mask
    b ^= temp
    a ^= temp << shift & MASK32
    return (
     a & MASK32, b & MASK32)


def _swap_left(a, mask, shift):
    count = 16 - shift & 31
    temp = (a << count & MASK32 ^ a) & mask
    return (
     (temp >> count ^ (a ^ temp)) & MASK32, temp & MASK32)


def expand_des_key(key8: bytes) -> list[int]:
    left = int.from_bytes(key8[:4], "little")
    right = int.from_bytes(key8[4:8], "little")
    (right, left) = _swap_right(right, left, 252645135, 4)
    (left, _) = _swap_left(left, 3435921408, -2)
    (right, _) = _swap_left(right, 3435921408, -2)
    (right, left) = _swap_right(right, left, 1431655765, 1)
    (left, right) = _swap_right(left, right, 16711935, 8)
    (right, left) = _swap_right(right, left, 1431655765, 1)
    right = (right & 255) << 16 | right & 65280 | (right & 16711680) >> 16 | (left & 4026531840) >> 4
    left &= 268435455
    subkeys = [0] * 32
    for i in range(16):
        if _ROT[i]:
            left = _ror28(left, 2)
            right = _ror28(right, 2)
        else:
            left = _ror28(left, 1)
            right = _ror28(right, 1)
        t0 = _KEY_TABLE[64 + (left >> 6 & 3 | left >> 7 & 60)] | _KEY_TABLE[left & 63] | _KEY_TABLE[128 + (left >> 13 & 15 | left >> 14 & 48)] | _KEY_TABLE[192 + (left >> 20 & 1 | left >> 21 & 6 | left >> 22 & 56)]
        t1 = _KEY_TABLE[320 + (right >> 7 & 3 | right >> 8 & 60)] | _KEY_TABLE[256 + (right & 63)] | _KEY_TABLE[384 + (right >> 15 & 63)] | _KEY_TABLE[448 + (right >> 21 & 15 | right >> 22 & 48)]
        subkeys[i * 2] = _rol32(t1 << 16 & MASK32 | t0 & 65535, 2)
        subkeys[i * 2 + 1] = _rol32(t0 >> 16 | t1 & 4294901760, 6)

    return subkeys


def ansi_bytes(text: str) -> bytes:
    for encoding in ("mbcs", "gbk", "latin1"):
        try:
            return text.encode(encoding, "replace")
        except LookupError:
            continue
    return text.encode("utf-8", "replace")

def _des_block(key8, block8, encrypt):
    cipher = Cipher(TripleDES(key8 * 3), modes.ECB())
    context = cipher.encryptor() if encrypt else cipher.decryptor()
    return context.update(block8) + context.finalize()


def _derive_des_key(password: bytes) -> bytes:
    return hashlib.sha1(password).digest()[:8]


def crypt_buffer(data, password, decode, *, iv_fill=143):
    key8 = _derive_des_key(password)
    out = bytearray(data)
    iv = bytearray([iv_fill] * 20)
    iv[:8] = _des_block(key8, bytes(iv[:8]), True)
    pos = 0
    remaining = len(out)
    while remaining >= 20:
        old = bytes(out[pos:pos + 20])
        if decode:
            out[pos:pos + 8] = _des_block(key8, bytes(out[pos:pos + 8]), False)
        for i in range(20):
            out[pos + i] ^= iv[i]
        if not decode:
            out[pos:pos + 8] = _des_block(key8, bytes(out[pos:pos + 8]), True)
        iv[:] = old if decode else out[pos:pos + 20]
        pos += 20
        remaining -= 20
    if remaining:
        iv[:8] = _des_block(key8, bytes(iv[:8]), True)
        for i in range(remaining):
            out[pos + i] ^= iv[i]
    return bytes(out)


@dataclass(frozen=True)
class _GeePak2StreamState:
    schedule: tuple[int, ...]
    chain: bytes


def _xor_bytes(left: bytes, right: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(left, right))


def _geepak2_legacy_mix_block(a: int, b: int, c: int) -> tuple[int, int, int]:
    a = _u32(a - b - c)
    a ^= c >> 13
    b = _u32(b - c - a)
    b ^= _u32(a << 8)
    c = _u32(c - a - b)
    c ^= b >> 19
    a = _u32(a - b - c)
    a ^= c >> 12
    b = _u32(b - c - a)
    b ^= _u32(a << 11)
    c = _u32(c - a - b)
    c ^= b >> 5
    a = _u32(a - b - c)
    a ^= c >> 3
    b = _u32(b - c - a)
    b ^= _u32(a << 10)
    c = _u32(c - a - b)
    c ^= b >> 15
    return _u32(a), _u32(b), _u32(c)


def _geepak2_legacy_mix_final(a: int, b: int, c: int) -> tuple[int, int, int]:
    a = _u32(a - b - c)
    a ^= c >> 13
    b = _u32(b - c - a)
    b ^= _u32(a << 8)
    c = _u32(c - a - b)
    c ^= b >> 11
    a = _u32(a - b - c)
    a ^= c >> 12
    b = _u32(b - c - a)
    b ^= _u32(a << 17)
    c = _u32(c - a - b)
    c ^= b >> 5
    a = _u32(a - b - c)
    a ^= c >> 3
    b = _u32(b - c - a)
    b ^= _u32(a << 10)
    c = _u32(c - a - b)
    c ^= b >> 15
    return _u32(a), _u32(b), _u32(c)


def _geepak2_legacy_crc32(data: bytes) -> int:
    crc = 0x24399977
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0xEDB88320 if crc & 1 else 0)
    return _u32(crc ^ MASK32)


def _derive_geepak2_header_key(password: bytes) -> bytes:
    if not password:
        return bytes(8)
    crc = _geepak2_legacy_crc32(password)
    a, b, c = 0xAD2832E3, 0x50FF46DE, 0xF07BB613
    offset = 0
    remaining = len(password)
    while remaining >= 12:
        part = password[offset:offset + 12]
        a = _u32(a + int.from_bytes(part[0:4], "little"))
        b = _u32(b + part[5] + (part[4] << 8) + (part[6] << 16) + (part[7] << 24))
        c = _u32(c + int.from_bytes(part[8:12], "little"))
        a, b, c = _geepak2_legacy_mix_block(a, b, c)
        offset += 12
        remaining -= 12

    tail = password[offset:]
    c = _u32(c + len(password))
    if remaining >= 11:
        c = _u32(c + (tail[10] << 24))
    if remaining >= 10:
        c = _u32(c + (tail[9] << 16))
    if remaining >= 9:
        c = _u32(c + (tail[8] << 8))
    if remaining >= 8:
        b = _u32(b + (tail[7] << 24))
    if remaining >= 7:
        b = _u32(b + (tail[6] << 16))
    if remaining >= 6:
        b = _u32(b + tail[5])
    if remaining >= 5:
        b = _u32(b + (tail[4] << 8))
    if remaining >= 4:
        a = _u32(a + (tail[3] << 24))
    if remaining >= 3:
        a = _u32(a + (tail[2] << 16))
    if remaining >= 2:
        a = _u32(a + (tail[1] << 8))
    if remaining >= 1:
        a = _u32(a + tail[0])
    _a, _b, c = _geepak2_legacy_mix_final(a, b, c)
    return c.to_bytes(4, "little") + _u32(crc ^ c).to_bytes(4, "little")


def _decode_geepak2_password_header(data: bytes, password: bytes) -> bytes:
    if len(data) != PAK_HEADER_SIZE:
        raise ValueError("GEEPAK2 password header must be 256 bytes")
    key = _derive_geepak2_header_key(password)
    chain = bytearray(b"\x8f" * 20)
    chain[:8] = _des_block(key, bytes(chain[:8]), True)
    output = bytearray(len(data))
    position = 0
    while len(data) - position >= 20:
        cipher = data[position:position + 20]
        output[position:position + 8] = _xor_bytes(
            _des_block(key, cipher[:8], False), chain[:8]
        )
        output[position + 8:position + 20] = _xor_bytes(cipher[8:], chain[8:])
        chain[:] = cipher
        position += 20
    if position < len(data):
        stream = _des_block(key, bytes(chain[:8]), False) + bytes(chain[8:])
        output[position:] = _xor_bytes(data[position:], stream)
    return bytes(output)


def _des_schedule_round(value: int, schedule_a: int, schedule_b: int) -> int:
    u = _u32(schedule_a ^ value)
    t = _ror32(schedule_b ^ value, 4)
    return _u32(
        _SP_TABLE[(u >> 2) & 0x3F]
        ^ _SP_TABLE[128 + ((u >> 10) & 0x3F)]
        ^ _SP_TABLE[256 + ((u >> 18) & 0x3F)]
        ^ _SP_TABLE[384 + ((u >> 26) & 0x3F)]
        ^ _SP_TABLE[64 + ((t >> 2) & 0x3F)]
        ^ _SP_TABLE[192 + ((t >> 10) & 0x3F)]
        ^ _SP_TABLE[320 + ((t >> 18) & 0x3F)]
        ^ _SP_TABLE[448 + ((t >> 26) & 0x3F)]
    )


def _des_schedule_block(
    block: bytes,
    schedule: tuple[int, ...],
    *,
    decrypt: bool,
) -> bytes:
    if len(block) != 8 or len(schedule) != 32:
        raise ValueError("DES schedule block requires 8-byte data and 32 words")
    left, right = struct.unpack("<2I", block)

    temp = ((right >> 4) ^ left) & 0x0F0F0F0F
    left = _u32(left ^ temp)
    right = _u32(right ^ (temp << 4))
    temp = ((left >> 16) ^ right) & 0x0000FFFF
    right = _u32(right ^ temp)
    left = _u32(left ^ (temp << 16))
    temp = ((right >> 2) ^ left) & 0x33333333
    left = _u32(left ^ temp)
    right = _u32(right ^ (temp << 2))
    temp = ((left >> 8) ^ right) & 0x00FF00FF
    right = _u32(right ^ temp)
    left = _u32(left ^ (temp << 8))
    temp = ((right >> 1) ^ left) & 0x55555555
    left = _u32(left ^ temp)
    right = _u32(right ^ (temp << 1))
    left = _rol32(left, 3)
    right = _rol32(right, 3)

    indexes = range(30, -1, -2) if decrypt else range(0, 32, 2)
    for round_index, schedule_index in enumerate(indexes):
        if round_index & 1:
            left = _u32(
                left
                ^ _des_schedule_round(
                    right,
                    schedule[schedule_index],
                    schedule[schedule_index + 1],
                )
            )
        else:
            right = _u32(
                right
                ^ _des_schedule_round(
                    left,
                    schedule[schedule_index],
                    schedule[schedule_index + 1],
                )
            )

    left = _ror32(left, 3)
    right = _ror32(right, 3)
    temp = ((left >> 1) ^ right) & 0x55555555
    right = _u32(right ^ temp)
    left = _u32(left ^ (temp << 1))
    temp = ((right >> 8) ^ left) & 0x00FF00FF
    left = _u32(left ^ temp)
    right = _u32(right ^ (temp << 8))
    temp = ((left >> 2) ^ right) & 0x33333333
    right = _u32(right ^ temp)
    left = _u32(left ^ (temp << 2))
    temp = ((right >> 16) ^ left) & 0x0000FFFF
    left = _u32(left ^ temp)
    right = _u32(right ^ (temp << 16))
    temp = ((left >> 4) ^ right) & 0x0F0F0F0F
    right = _u32(right ^ temp)
    left = _u32(left ^ (temp << 4))
    return struct.pack("<2I", right, left)


def _geepak2_feedback_decrypt(data: bytes, state: _GeePak2StreamState) -> bytes:
    output = bytearray(len(data))
    chain = bytearray(state.chain)
    position = 0
    while len(data) - position >= 20:
        cipher = data[position:position + 20]
        output[position:position + 8] = _xor_bytes(
            _des_schedule_block(cipher[:8], state.schedule, decrypt=True),
            chain[:8],
        )
        output[position + 8:position + 20] = _xor_bytes(cipher[8:], chain[8:])
        chain[:] = cipher
        position += 20
    if position < len(data):
        stream = (
            _des_schedule_block(bytes(chain[:8]), state.schedule, decrypt=False)
            + bytes(chain[8:])
        )
        output[position:] = _xor_bytes(data[position:], stream)
    return bytes(output)


def _build_geepak2_stream_state(password: bytes) -> _GeePak2StreamState:
    schedule = tuple(expand_des_key(_derive_des_key(password)))
    chain = bytearray(b"\x60" * 20)
    chain[:8] = _des_schedule_block(bytes(chain[:8]), schedule, decrypt=False)
    return _GeePak2StreamState(schedule=schedule, chain=bytes(chain))


def _decode_geepak2_directory(
    raw_table: bytes,
    state: _GeePak2StreamState,
) -> list[int]:
    if len(raw_table) % 4:
        raise ValueError("GEEPAK2 directory must be dword aligned")
    first_pass = _geepak2_feedback_decrypt(raw_table, state)
    second_pass = _geepak2_feedback_decrypt(first_pass, state)
    key_byte = state.chain[0]
    return [
        value ^ key_byte
        for value in struct.unpack(f"<{len(second_pass) // 4}I", second_pass)
    ]


def _decode_geepak2_resource_header(
    raw_header: bytes,
    state: _GeePak2StreamState,
) -> bytes:
    if len(raw_header) != PAK_IMAGE_HEADER_SIZE:
        raise ValueError("GEEPAK2 resource header must be 16 bytes")
    altered = list(state.schedule)
    for index in range(0, len(altered), 2):
        altered[index] ^= altered[index + 1]
    first_pass = _geepak2_feedback_decrypt(
        raw_header,
        _GeePak2StreamState(tuple(altered), state.chain),
    )
    return _geepak2_feedback_decrypt(first_pass, state)


def _geepak2_raw_payload_size(header: RecoveredImageHeader) -> int:
    return header.raw_payload_size

def _mix_a(a, b, c):
    a = _u32(a - b - c)
    a ^= c >> 8
    b = _u32(b - c - a)
    b ^= _u32(a << 9)
    c = _u32(c - a - b)
    c ^= b >> 13
    a = _u32(a - b - c)
    a ^= c >> 9
    b = _u32(b - c - a)
    b ^= _u32(a << 6)
    c = _u32(c - a - b)
    c ^= b >> 4
    a = _u32(a - b - c)
    a ^= c >> 8
    b = _u32(b - c - a)
    b ^= _u32(a << 3)
    c = _u32(c - a - b)
    c ^= b >> 15
    return (
     _u32(a), _u32(b), _u32(c))


def _mix_a_tail(a, b, c):
    a = _u32(a - b - c)
    a ^= c >> 4
    b = _u32(b - c - a)
    b ^= _u32(a << 9)
    c = _u32(c - a - b)
    c ^= b >> 19
    a = _u32(a - b - c)
    a ^= c >> 11
    b = _u32(b - c - a)
    b ^= _u32(a << 14)
    c = _u32(c - a - b)
    c ^= b >> 5
    a = _u32(a - b - c)
    a ^= c >> 9
    b = _u32(b - c - a)
    b ^= _u32(a << 12)
    c = _u32(c - a - b)
    c ^= b >> 3
    return (
     _u32(a), _u32(b), _u32(c))


def _mix_b(a, b, c):
    a = _u32(a - b - c)
    a ^= c >> 9
    b = _u32(b - c - a)
    b ^= _u32(a << 3)
    c = _u32(c - a - b)
    c ^= b >> 12
    a = _u32(a - b - c)
    a ^= c >> 11
    b = _u32(b - c - a)
    b &= _u32(a << 7)
    c = _u32(c - a - b)
    c ^= b >> 10
    a = _u32(a - b - c)
    a ^= c >> 4
    b = _u32(b - c - a)
    b ^= _u32(a << 1)
    c = _u32(c - a - b)
    c ^= b >> 8
    return (
     _u32(a), _u32(b), _u32(c))


def _mix_b_tail(a, b, c):
    a = _u32(a - b - c)
    a ^= c >> 11
    b = _u32(b - c - a)
    b ^= _u32(a << 1)
    c = _u32(c - a - b)
    c ^= b >> 15
    a = _u32(a - b - c)
    a ^= c >> 2
    b = _u32(b - c - a)
    b ^= _u32(a << 7)
    c = _u32(c - a - b)
    c ^= b >> 9
    a = _u32(a - b - c)
    a ^= c >> 1
    b = _u32(b - c - a)
    b ^= _u32(a << 3)
    c = _u32(c - a - b)
    c |= b >> 5
    return (
     _u32(a), _u32(b), _u32(c))


def derive_gee_pak3_key_block(password: bytes) -> tuple[bytes, list[int]]:
    subkeys = expand_des_key(_derive_des_key(password))
    iv = bytearray([96] * 20)
    iv[:8] = _des_block(_derive_des_key(password), bytes(iv[:8]), True)
    key_words = [0] * 64
    for index in range(32):
        key_words[index * 2] = subkeys[31 - index]

    for (index, value) in zip([1,7,11,13,15], struct.unpack("<5I", iv)):
        key_words[index] = value

    remaining = 32
    key_index = 0
    (a, b, c) = (3164750357, 3172549425, 3114183698)
    while remaining >= 3:
        a = _u32(a + subkeys[key_index])
        b = _u32(b + subkeys[key_index + 1])
        c = _u32(c + subkeys[key_index + 2])
        (a, b, c) = _mix_a(a, b, c)
        key_index += 3
        remaining -= 3

    c = _u32(c + 32)
    if remaining >= 1:
        a = _u32(a + subkeys[key_index])
    if remaining >= 2:
        a = _u32(a + subkeys[key_index + 1])
    (a, b, c) = _mix_a_tail(a, b, c)
    key_words[3], key_words[5], key_words[9] = a, b, c
    x = 1315423911
    for index in range(17):
        value = _u32(key_words[index] + _u32(x << 5) + (x >> 2))
        x = _u32(x ^ value)

    key_words[17] = x
    x = 5381
    for index in range(18):
        x = _u32(key_words[index] + _u32(x + _u32(x << 5)))

    key_words[19] = x
    for outer in range(10, 32):
        remaining = outer * 2
        key_index = 0
        (a, b, c) = (381261768, 1215581588, 3120985135)
        while remaining >= 3:
            a = _u32(a + key_words[key_index])
            b = _u32(b + key_words[key_index + 1])
            c = _u32(c + key_words[key_index + 2])
            (a, b, c) = _mix_b(a, b, c)
            key_index += 3
            remaining -= 3

        c = _u32(c + outer * 2)
        if remaining >= 1:
            a = _u32(a + key_words[key_index])
        if remaining >= 2:
            a = _u32(a + key_words[key_index + 1])
        (_a, _b, c) = _mix_b_tail(a, b, c)
        key_words[outer * 2 + 1] = c

    return ((struct.pack)(*('<64I', ), *key_words), key_words)


def aes_ctr_crypt(key: bytes, data: bytes) -> bytes:
    cipher = Cipher(primitive_algorithms.AES(key), modes.ECB())
    encryptor = cipher.encryptor()
    counter = bytearray(16)
    out = bytearray(len(data))
    for offset in range(0, len(data), 16):
        stream = encryptor.update(bytes(counter))
        block = data[offset:offset + 16]
        for (index, value) in enumerate(block):
            out[offset + index] = value ^ stream[index]
        carry = 7
        while carry >= 0:
            counter[carry] = (counter[carry] + 1) & 255
            if counter[carry] != 0:
                break
            carry -= 1
    encryptor.finalize()
    return bytes(out)

def image_header_aes_key(key_words: list[int], index: int) -> bytes:
    words = [
     key_words[index & 63] ^ key_words[index + 14 & 63],
     key_words[index + 12 & 63] & key_words[index + 19 & 63],
     key_words[index + 28 & 63] ^ _u32(~key_words[index + 10 & 63]),
     key_words[index + 1 & 63]]
    return (struct.pack)(*('<4I', ), *[_u32(word) for word in words])


def decode_gee_image_header(raw_header, key_words, index):
    return aes_ctr_crypt(image_header_aes_key(key_words, index), raw_header)


def dib_stride(bits: int, width: int) -> int:
    return (width * bits + 31 & -32) // 8


def read_magic(path: str | Path) -> str:
    source = Path(path)
    suffix = source.suffix.lower()
    if suffix in {'.wzl', '.wzx'}:
        return "WZL"
    if suffix in {'.wil', '.wix'}:
        return "WIL"
    if suffix == ".wis":
        return "WIS"
    with source.open("rb") as handle:
        data = handle.read(32)
    if data.startswith(b'SWPAK01\x00'):
        return "SWPAK"
    if data.startswith(b'PACK'):
        return "GOMPACK"
    if data.startswith(b'\x07GEEPAK3'):
        return "GEEPAK3"
    if data.startswith(b'\x07GEEPAK2'):
        return "GEEPAK2"
    if data.startswith(b'\x05GEEM2'):
        return "GEEM2LP"
    if data.startswith(b'\nGAMEOFMIR2'):
        return "GAMEOFMIR2"
    if data.startswith(b'\tGAMEOFMIR'):
        return "GAMEOFMIR"
    if data.startswith(b'GAMEOFMIR2'):
        return "GAMEOFMIR2"
    if data.startswith(b'GAMEOFMIR'):
        return "GAMEOFMIR"
    if data.startswith(b'D3DM2') or data.startswith(b'MIRYQ') or data.startswith(b'GEEM2'):
        return "D3DM2"
    magic_len = data[0] if data else 0
    if 0 < magic_len < len(data):
        return data[1:1 + magic_len].decode("ascii", "replace")
    return ""


def default_password_for_magic(magic: str) -> str:
    value = str(magic or "").upper()
    if value in {'GOMPACK', 'GAMEOFMIR2', 'GAMEOFMIR'}:
        return "gameofmir"
    if value == "GEEPAK3":
        return "V8M2"
    return ""


_AUTHORIZED_DECODE_PROFILES = {
    "GEEPAK3": ("geepak3-v1", "", {(10, 266)}, {2}),
    "GEEPAK2": ("geepak2-v1", None, {(10, 266)}, {0, 1, 2}),
    "GEEM2LP": ("geem2lp-v1", "", {(10, 266)}, {2}),
    "D3DM2": ("d3dm2-v1", "442517066", {(5, 262)}, {0, 1}),
    "GAMEOFMIR": ("gameofmir-v1", "3698175006", {(10, 266)}, {0, 1}),
    "GAMEOFMIR2": ("gameofmir2-v1", "2282260488", {(10, 266), (13, 269)}, {0, 1}),
    "GOMPACK": ("frame-scan-v1", "", {(0, 0)}, {0, 1}),
    "SWPAK": ("frame-scan-v1", "", {(0, 0)}, {0, 1}),
    "WIL": ("wil-v1", "", {(0, 0)}, {0, 1}),
    "WIS": ("wil-v1", "", {(0, 0)}, {0, 1}),
    "WZL": ("wil-v1", "", {(0, 0)}, {0, 1}),
}


def _authorized_decode_profile(
    profile: Mapping[str, Any] | None,
    actual_magic: str,
) -> dict[str, Any] | None:
    if profile is None:
        return None
    if not isinstance(profile, Mapping):
        raise ValueError("authorized asset decode profile is invalid")
    magic = str(profile.get("magic") or "").upper()
    if magic != str(actual_magic or "").upper():
        raise ValueError("authorized asset magic does not match the local file")
    expected = _AUTHORIZED_DECODE_PROFILES.get(magic)
    if expected is None:
        raise ValueError(f"unsupported authorized asset format: {magic or '<empty>'}")
    expected_version, expected_header_password, expected_layouts, expected_modes = expected
    try:
        prefix_size = int(str(profile.get("prefix_size") or "0"))
        data_base = int(str(profile.get("data_base") or "0"))
        raw_modes = profile.get("allowed_index_modes")
        if isinstance(raw_modes, (set, frozenset, list, tuple)):
            allowed_index_modes = {int(value) for value in raw_modes}
        else:
            allowed_index_modes = {
                int(value.strip())
                for value in str(raw_modes or "").split(",")
                if value.strip()
            }
    except (TypeError, ValueError) as exc:
        raise ValueError("authorized asset decode profile has invalid numeric fields") from exc
    format_version = str(profile.get("format_version") or "")
    header_password = str(profile.get("header_password") or "")
    resolved_password = str(profile.get("resolved_password") or "")
    if (
        format_version != expected_version
        or (
            expected_header_password is not None
            and header_password != expected_header_password
        )
        or (prefix_size, data_base) not in expected_layouts
        or allowed_index_modes != expected_modes
    ):
        raise ValueError("authorized asset decode profile is not supported by this client")
    return {
        "magic": magic,
        "resolved_password": resolved_password,
        "header_password": header_password,
        "prefix_size": prefix_size,
        "data_base": data_base,
        "allowed_index_modes": frozenset(allowed_index_modes),
        "format_version": format_version,
    }


def _detect_pak_prefix(data: bytes) -> tuple[str, int, int, bytes]:
    if data.startswith(b'\x07GEEPAK3'):
        return ('GEEPAK3', 10, 266, b'')
    if data.startswith(b'\x07GEEPAK2'):
        return ('GEEPAK2', 10, 266, b'')
    if data.startswith(b'\x05GEEM2'):
        return ('GEEM2LP', 10, 266, b'')
    if data.startswith(b'D3DM2') or data.startswith(b'MIRYQ') or data.startswith(b'GEEM2'):
        return ('D3DM2', 5, 262, b'442517066')
    if data.startswith(b'\tGAMEOFMIR'):
        return ('GAMEOFMIR', 10, 266, b'3698175006')
    if data.startswith(b'\nGAMEOFMIR2'):
        return ('GAMEOFMIR2', 13, 269, b'2282260488')
    if data.startswith(b'GAMEOFMIR2'):
        return ('GAMEOFMIR2', 10, 266, b'2282260488')
    if data.startswith(b'GAMEOFMIR'):
        return ('GAMEOFMIR', 10, 266, b'3698175006')
    raise ValueError(f"unsupported PAK prefix: {data[:16].hex()}")


def _decode_gee_index(raw, key_words, count):
    offsets = []
    for index in range(count):
        raw_value = struct.unpack_from("<I", raw, index * 4)[0]
        offsets.append(_u32(raw_value ^ key_words[index & 63] ^ _u32(~index)))

    return offsets


def _plain_header_is_plausible(header: bytes, file_size: int) -> bool:
    if len(header) != PAK_HEADER_SIZE:
        return False
    count = struct.unpack_from("<I", header, 46)[0]
    index_mode = header[50]
    index_offset = struct.unpack_from("<I", header, 54)[0]
    index_unit = 8 if index_mode == 0 else 4
    return 0 <= count < 2000000 and index_mode in (0, 1, 2) and 0 <= index_offset <= file_size and index_offset + count * index_unit <= file_size


def _geepak2_header_is_plausible(
    header: bytes,
    file_size: int,
    data_base: int,
) -> bool:
    if len(header) != PAK_HEADER_SIZE:
        return False
    count = struct.unpack_from("<I", header, 0x2E)[0]
    index_mode = struct.unpack_from("<I", header, 0x32)[0]
    index_offset = struct.unpack_from("<I", header, 0x36)[0]
    return (
        0 < count < 2000000
        and index_mode in (0, 1, 2)
        and index_offset == data_base
        and index_offset + count * 4 <= file_size
    )


def _decode_pak_header_and_offsets(
    path: Path,
    password: str,
    *,
    decode_profile: Mapping[str, Any] | None = None,
) -> tuple[
    str,
    int,
    bytes,
    list[int],
    list[int] | _GeePak2StreamState | None,
]:
    file_size = path.stat().st_size

    def read_at(offset: int, size: int) -> bytes:
        if offset < 0 or size < 0 or offset + size > file_size:
            raise ValueError("PAK read range is outside the local file")
        with path.open("rb") as handle:
            handle.seek(offset)
            raw = handle.read(size)
        if len(raw) != size:
            raise ValueError("PAK read range is incomplete")
        return raw

    prefix = read_at(0, min(16, file_size))
    (kind, detected_prefix_size, detected_data_base, detected_header_password) = _detect_pak_prefix(prefix)
    profile = _authorized_decode_profile(decode_profile, kind)
    if profile is not None:
        prefix_size = int(profile["prefix_size"])
        data_base = int(profile["data_base"])
        header_password = ansi_bytes(str(profile["header_password"]))
        user_password = str(profile["resolved_password"])
        if password and password != user_password:
            raise ValueError("authorized asset password does not match the decoder request")
        if prefix_size != detected_prefix_size or data_base != detected_data_base:
            raise ValueError("authorized asset layout does not match the local file")
    else:
        prefix_size = detected_prefix_size
        data_base = detected_data_base
        header_password = detected_header_password
        user_password = password or default_password_for_magic(kind)
    if kind == "GEEPAK2":
        if not user_password:
            raise ValueError("GEEPAK2 password is required")
        password_bytes = ansi_bytes(user_password)
        header_password_bytes = header_password or password_bytes
        header = _decode_geepak2_password_header(
            read_at(prefix_size, PAK_HEADER_SIZE),
            header_password_bytes,
        )
        if not _geepak2_header_is_plausible(header, file_size, data_base):
            raise ValueError("GEEPAK2 password is wrong or header is invalid")
        declared_count = struct.unpack_from("<I", header, 0x2E)[0]
        index_mode = struct.unpack_from("<I", header, 0x32)[0]
        index_offset = struct.unpack_from("<I", header, 0x36)[0]
        if profile is not None and index_mode not in profile["allowed_index_modes"]:
            raise ValueError(f"GEEPAK2 index mode {index_mode} is not authorized")
        stream_state = _build_geepak2_stream_state(password_bytes)
        declared_size = declared_count * 4
        declared_offsets = _decode_geepak2_directory(
            read_at(index_offset, declared_size),
            stream_state,
        )
        table_end = next((offset for offset in declared_offsets if offset), 0)
        table_size = table_end - index_offset
        if (
            table_size <= 0
            or table_size % 20
            or table_end > file_size
            or table_end > index_offset + declared_size
        ):
            raise ValueError("GEEPAK2 directory boundary is invalid")
        offsets = _decode_geepak2_directory(
            read_at(index_offset, table_size),
            stream_state,
        )
        nonempty_offsets = [offset for offset in offsets if offset]
        if (
            not nonempty_offsets
            or min(nonempty_offsets) != table_end
            or any(not (table_end <= offset < file_size) for offset in nonempty_offsets)
            or any(
                left >= right
                for left, right in zip(nonempty_offsets, nonempty_offsets[1:])
            )
        ):
            raise ValueError("GEEPAK2 directory offsets are invalid")
        count = len(offsets)
        patched_header = bytearray(header)
        struct.pack_into("<I", patched_header, 0x2E, count)
        return (kind, count, bytes(patched_header), offsets, stream_state)
    if kind == "GEEPAK3":
        (key_block, key_words) = derive_gee_pak3_key_block(ansi_bytes(user_password))
        header = aes_ctr_crypt(key_block[:16], read_at(prefix_size, PAK_HEADER_SIZE))
        if not _plain_header_is_plausible(header, file_size):
            raise ValueError("GEEPAK3 password is wrong or header is invalid")
        count = struct.unpack_from("<I", header, 46)[0]
        index_offset = struct.unpack_from("<I", header, 54)[0]
        index_mode = header[50]
        if index_mode != 2:
            raise ValueError(f"unsupported GEEPAK3 index mode: {index_mode}")
        if profile is not None and index_mode not in profile["allowed_index_modes"]:
            raise ValueError(f"GEEPAK3 index mode {index_mode} is not authorized")
        raw_index = read_at(index_offset, count * 4)
        offsets = _decode_gee_index(raw_index, key_words, count)
        data_start = index_offset + count * 4
        if any(offset and not (data_start <= offset < file_size) for offset in offsets):
            raise ValueError("GEEPAK3 index contains an out-of-profile data offset")
        return (
         kind, count, header, offsets, key_words)
    if kind == "GEEM2LP":
        if not user_password:
            raise ValueError("GEEM2LP password is required")
        user_password_bytes = ansi_bytes(user_password)
        header = crypt_buffer(
            read_at(prefix_size, PAK_HEADER_SIZE),
            user_password_bytes,
            True,
            iv_fill=96,
        )
        index_mode = header[50]
        index_offset = struct.unpack_from("<I", header, 54)[0]
        if index_mode != 2 or index_offset != data_base:
            raise ValueError("GEEM2LP header is invalid")
        if profile is not None and index_mode not in profile["allowed_index_modes"]:
            raise ValueError(f"GEEM2LP index mode {index_mode} is not authorized")

        available_size = file_size - index_offset
        max_probe_size = min(available_size, 4096 * 4)
        max_block_probe_size = max_probe_size - max_probe_size % 20
        probe_sizes = [
            size for size in (4, 8, 12, 16, max_block_probe_size)
            if 0 < size <= available_size
        ]
        if not probe_sizes:
            raise ValueError("GEEM2LP index is missing")
        candidate_data_starts = set()
        for probe_size in dict.fromkeys(probe_sizes):
            probe = crypt_buffer(
                read_at(index_offset, probe_size),
                user_password_bytes,
                True,
                iv_fill=96,
            )
            for position in range(0, len(probe) - 3, 4):
                offset = struct.unpack_from("<I", probe, position)[0]
                index_size = offset - index_offset
                if (
                    data_base < offset < file_size
                    and index_size > 0
                    and index_size % 4 == 0
                    and index_size <= available_size
                ):
                    candidate_data_starts.add(offset)

        count = 0
        data_start = 0
        offsets = []
        for candidate_data_start in sorted(candidate_data_starts):
            candidate_count = (candidate_data_start - index_offset) // 4
            if candidate_count <= 0 or candidate_count >= 2000000:
                continue
            raw_index = read_at(index_offset, candidate_data_start - index_offset)
            index = crypt_buffer(raw_index, user_password_bytes, True, iv_fill=96)
            candidate_offsets = [
                struct.unpack_from("<I", index, index_no * 4)[0]
                for index_no in range(candidate_count)
            ]
            nonzero_offsets = [offset for offset in candidate_offsets if offset]
            if (
                nonzero_offsets
                and min(nonzero_offsets) == candidate_data_start
                and all(candidate_data_start <= offset < file_size for offset in nonzero_offsets)
                and all(left <= right for left, right in zip(nonzero_offsets, nonzero_offsets[1:]))
            ):
                count = candidate_count
                data_start = candidate_data_start
                offsets = candidate_offsets
                break
        if not offsets:
            raise ValueError("GEEM2LP index boundary or offsets are invalid")
        patched_header = bytearray(header)
        struct.pack_into("<I", patched_header, 46, count)
        patched_header[50] = 2
        struct.pack_into("<I", patched_header, 54, index_offset)
        return (kind, count, bytes(patched_header), offsets, None)
    header = crypt_buffer(read_at(prefix_size, PAK_HEADER_SIZE), header_password, True)
    if not _plain_header_is_plausible(header, file_size):
        raise ValueError(f"{kind} header is invalid")
    count = struct.unpack_from("<I", header, 46)[0]
    index_mode = header[50]
    index_offset = struct.unpack_from("<I", header, 54)[0]
    if profile is not None and index_mode not in profile["allowed_index_modes"]:
        raise ValueError(f"{kind} index mode {index_mode} is not authorized")
    raw_index = read_at(index_offset, count * (8 if index_mode == 0 else 4))
    index = crypt_buffer(raw_index, ansi_bytes(user_password), True)
    offsets = []
    for index_no in range(count):
        offsets.append(struct.unpack_from("<I", index, index_no * (8 if index_mode == 0 else 4))[0])

    if any(offset and not (data_base <= offset < index_offset) for offset in offsets):
        raise ValueError(f"{kind} index contains an out-of-profile data offset")

    return (kind, count, header, offsets, None)


def _decode_pak_image_header(path, password, index, offset, key_words, decode_profile=None):
    with path.open("rb") as handle:
        handle.seek(offset)
        raw_header = handle.read(PAK_IMAGE_HEADER_SIZE)
    if isinstance(key_words, _GeePak2StreamState):
        plain = _decode_geepak2_resource_header(raw_header, key_words)
    elif key_words is None:
        profile = _authorized_decode_profile(decode_profile, read_magic(Path(path)))
        if profile is not None:
            format_version = str(profile["format_version"])
            image_password = str(profile["resolved_password"])
            if not image_password and format_version == "d3dm2-v1":
                image_password = "gameofmir"
        else:
            image_password = password or "gameofmir"
        iv_fill = 96 if profile is not None and profile["format_version"] == "geem2lp-v1" else 143
        if profile is not None and profile["format_version"] == "geepak2-v1":
            raise ValueError("GEEPAK2 stream state is missing")
        plain = crypt_buffer(raw_header, ansi_bytes(image_password), True, iv_fill=iv_fill)
    else:
        plain = decode_gee_image_header(raw_header, key_words, index)
    return RecoveredImageHeader.decode(plain)


def _header_is_valid(header: RecoveredImageHeader) -> bool:
    return header.image_type in BITS_BY_TYPE and 0 < header.width <= 8192 and 0 < header.height <= 8192 and header.stored_payload_size >= 0


def _geepak2_image_header_is_valid(header: RecoveredImageHeader) -> bool:
    return (
        header.image_type in {3, 4, 5, 6, 7}
        and 0 < header.width <= 0x800
        and 0 < header.height <= 0x800
        and header.packed_size < 0x01000000
    )


def load_recovered_pak_records(
    path,
    password='',
    *,
    transparent_zero=True,
    progress=None,
    decode_profile: Mapping[str, Any] | None = None,
):
    pak_path = Path(path)
    magic = read_magic(pak_path)
    profile = _authorized_decode_profile(decode_profile, magic)
    if magic in {"GOMPACK", "SWPAK"}:
        return _load_gameofmir_frame_records(pak_path,
          source_magic=magic,
          transparent_zero=transparent_zero,
          progress=progress)
    return _load_direct_recovered_pak_records(pak_path,
      password,
      transparent_zero=transparent_zero,
      progress=progress,
      decode_profile=profile)


def _load_gameofmir_frame_records(pak_path, *, source_magic: str, transparent_zero=True, progress=None):
    from .pak_asset_browser import AssetRecord
    try:
        from . import recovered_gameofmir_codec as gameofmir_codec
    except ImportError:
        from core.npc_preview import recovered_gameofmir_codec as gameofmir_codec

    pak_path = Path(pak_path)
    source_magic = str(source_magic or "GOMPACK").upper()
    data = pak_path.read_bytes()
    records = []
    for offset in sorted(gameofmir_codec.find_zlib_offsets(data)):
        header = gameofmir_codec.parse_frame_header(data, offset)
        if header is None:
            continue
        compressed_size = int(header["compressed_size"])
        decoded = gameofmir_codec.decompress_exact(data[offset:offset + compressed_size])
        if decoded is None:
            continue
        width = int(header["width"])
        height = int(header["height"])
        image_format = str(header["format"])
        expected_size = gameofmir_codec.expected_decoded_size(width, height, image_format)
        if len(decoded) != expected_size:
            continue
        bgra = gameofmir_codec.decoded_to_bgra(decoded, width, height, image_format, transparent_zero)
        image = Image.frombytes("RGBA", (width, height), bgra, "raw", "BGRA")
        uid = len(records)
        record = AssetRecord(uid=uid,
          source_index=f"{uid:05d}",
          file_name=f"{uid:05d}_{width}x{height}_{image_format}_{source_magic.lower()}.png",
          path=None,
          width=width,
          height=height,
          color_format=image_format,
          method="gameofmir_zlib",
          kind="recovered_pak",
          pak_path=pak_path,
          data_off=offset,
          data_len=compressed_size,
          raw_len=len(decoded),
          bits={"gray8": 8, "rgb565": 16, "bgr24": 24, "bgr24a8": 24, "bgrx32": 32}.get(image_format, 0),
          stride={
           "gray8": gameofmir_codec.align4(width),
           "rgb565": gameofmir_codec.align4(width * 2),
           "bgr24": gameofmir_codec.align4(width * 3),
           "bgr24a8": gameofmir_codec.align4(width * 3),
           "bgrx32": width * 4}.get(image_format, 0),
          alpha_stride=(gameofmir_codec.align4(width) if image_format == "bgr24a8" else 0),
          enc1=-1,
          enc2=1 if image_format == "bgr24a8" else 0,
          transparent_zero=transparent_zero,
          image=image,
          compressed_size=compressed_size,
          origin_x=int(header["origin_x"]),
          origin_y=int(header["origin_y"]),
          _cache_kind="recovered_pak",
          original_uid=uid,
          source_magic=source_magic)
        records.append(record)

    if progress:
        progress(f"{source_magic} 帧扫描完成：{len(records)} 个素材")
    if not records:
        raise ValueError(f"{source_magic} parsed zero valid zlib frames: {pak_path}")
    return (source_magic, len(records), records, "gameofmir-frame-scan")


def _load_direct_recovered_pak_records(
    pak_path,
    password='',
    *,
    transparent_zero=True,
    progress=None,
    decode_profile: Mapping[str, Any] | None = None,
):
    from .pak_asset_browser import AssetRecord
    profile = _authorized_decode_profile(decode_profile, read_magic(Path(pak_path)))
    resolved_password = str(profile["resolved_password"]) if profile is not None else password
    (magic, count, _header, offsets, key_words) = _decode_pak_header_and_offsets(
      pak_path, resolved_password, decode_profile=profile)
    if progress:
        progress(f"{magic} 索引读取完成：{count} 个槽位")
    records = []
    valid = 0
    geepak2_boundaries = {}
    if isinstance(key_words, _GeePak2StreamState):
        nonempty_slots = [
            (index, offset)
            for index, offset in enumerate(offsets)
            if offset > 0
        ]
        file_size = Path(pak_path).stat().st_size
        for position, (index, _offset) in enumerate(nonempty_slots):
            geepak2_boundaries[index] = (
                nonempty_slots[position + 1][1]
                if position + 1 < len(nonempty_slots)
                else file_size
            )
    for (index, offset) in enumerate(offsets):
        if offset <= 0:
            records.append(_empty_record(AssetRecord, pak_path, index, "recovered_pak", magic))
        else:
            try:
                header = _decode_pak_image_header(
                  pak_path, resolved_password, index, offset, key_words, decode_profile=profile)
                if isinstance(key_words, _GeePak2StreamState):
                    if not _geepak2_image_header_is_valid(header):
                        raise ValueError("invalid GEEPAK2 image header")
                    payload_size = (
                        header.packed_size
                        if header.packed_size > 0
                        else _geepak2_raw_payload_size(header)
                    )
                    if offset + PAK_IMAGE_HEADER_SIZE + payload_size != geepak2_boundaries[index]:
                        raise ValueError("invalid GEEPAK2 record boundary")
                elif not _header_is_valid(header):
                    raise ValueError("invalid image header")
                records.append(_record_from_header(
                    AssetRecord,
                    pak_path,
                    index,
                    offset + PAK_IMAGE_HEADER_SIZE,
                    header,
                    "recovered_pak",
                    transparent_zero,
                    magic,
                ))
                valid += 1
            except Exception:
                records.append(_empty_record(AssetRecord, pak_path, index, "recovered_pak", magic))

    if count and not valid:
        raise ValueError(f"{magic} parsed zero valid image headers")
    return (magic, count, records, "recovered-direct")


def _empty_record(record_type, path, index, kind, source_magic=''):
    return record_type(uid=index,
      source_index=(f"{index:05d}"),
      file_name=f"{index:05d}_empty.png",
      path=None,
      width=0,
      height=0,
      color_format="empty",
      method="",
      kind="empty",
      pak_path=path,
      _cache_kind=kind,
      original_uid=index,
      source_magic=source_magic)


def _record_file_name(index, header, method, kind):
    method_name = "".join((ch if (ch.isalnum()) or (ch in {'_', '-'}) else "_" for ch in method))
    kind_name = "".join((ch if (ch.isalnum()) or (ch in {'_', '-'}) else "_" for ch in kind))
    return f"{index:05d}_{header.width}x{header.height}_{header.bits}b_{method_name}_{kind_name}.png"


def _record_from_header(
    record_type,
    path,
    index,
    data_off,
    header,
    kind,
    transparent_zero,
    source_magic='',
):
    is_wil_family = kind in {'recovered_wil', 'recovered_wis', 'recovered_wzl'}
    render_method = "wzl_alpha4" if is_wil_family and header.alpha == 9 and header.bits == 16 else "raw"
    method = "zlib" if header.is_packed else render_method
    if header.is_packed and render_method != "raw":
        method = f"{render_method}_zlib"
    color_stride = header.color_stride
    alpha_stride = header.alpha_stride
    raw_payload_size = header.raw_payload_size
    data_len = header.stored_payload_size
    return record_type(uid=index,
      source_index=(f"{index:05d}"),
      file_name=(_record_file_name(index, header, method, kind)),
      path=None,
      width=(header.width),
      height=(header.height),
      color_format=f"{header.bits}b type={header.image_type}",
      method=method,
      kind=kind,
      pak_path=path,
      data_off=data_off,
      data_len=data_len,
      raw_len=raw_payload_size,
      bits=(header.bits),
      stride=color_stride,
      alpha_stride=(alpha_stride if header.alpha else 0),
      enc1=(header.image_type),
      enc2=(header.alpha),
      transparent_zero=transparent_zero,
      compressed_size=(header.packed_size if header.is_packed else 0),
      origin_x=(header.offset_x),
      origin_y=(header.offset_y),
      _cache_kind=kind,
      original_uid=index,
      source_magic=source_magic)

def _sibling_with_suffix(path: Path, suffixes: tuple[str, ...]) -> Path | None:
    for suffix in suffixes:
        candidate = path.with_suffix(suffix)
        if candidate.is_file():
            return candidate

    if path.parent.is_dir():
        stem = path.stem.casefold()
        wanted = {suffix.casefold() for suffix in suffixes}
        for child in path.parent.iterdir():
            if child.is_file():
                if child.stem.casefold() == stem:
                    if child.suffix.casefold() in wanted:
                        return child


def _resolve_wil_paths(path: Path) -> tuple[Path, Path, str, str]:
    suffix = path.suffix.lower()
    if suffix in {'.wzl', '.wzx'}:
        data_path = _sibling_with_suffix(path, ('.wzl', '.WZL'))
        index_path = _sibling_with_suffix(path, ('.wzx', '.WZX'))
        return (
         _require_path(data_path, path), _require_path(index_path, path.with_suffix(".wzx")), "WZL", "recovered_wzl")
    if suffix == '.wix':
        wil_data_path = _sibling_with_suffix(path, ('.wil', '.WIL'))
        wis_data_path = _sibling_with_suffix(path, ('.wis', '.WIS'))
        if wil_data_path is None and wis_data_path is not None:
            index_path = _sibling_with_suffix(path, ('.wix', '.WIX'))
            return (
             _require_path(wis_data_path, path.with_suffix(".wis")), _require_path(index_path, path.with_suffix(".wix")), "WIS", "recovered_wis")
    if suffix in {'.wil', '.wix'}:
        data_path = _sibling_with_suffix(path, ('.wil', '.WIL'))
        index_path = _sibling_with_suffix(path, ('.wix', '.WIX'))
        return (
         _require_path(data_path, path), _require_path(index_path, path.with_suffix(".wix")), "WIL", "recovered_wil")
    if suffix == ".wis":
        data_path = _sibling_with_suffix(path, ('.wis', '.WIS'))
        index_path = _sibling_with_suffix(path, ('.wix', '.WIX'))
        return (
         _require_path(data_path, path), _require_path(index_path, path.with_suffix(".wix")), "WIS", "recovered_wis")
    raise ValueError(f"unsupported image library: {path.name}")


def _require_path(path: Path | None, fallback: Path) -> Path:
    if path is None:
        raise FileNotFoundError(str(fallback))
    return path


def load_recovered_wil_records(
    path: str | Path,
    *,
    transparent_zero: bool=True,
    decode_profile: Mapping[str, Any] | None = None,
) -> tuple[str, int, list[object], str]:
    from .pak_asset_browser import AssetRecord
    (data_path, index_path, magic, kind) = _resolve_wil_paths(Path(path))
    profile = _authorized_decode_profile(decode_profile, magic)
    if profile is not None and 1 not in profile["allowed_index_modes"]:
        raise ValueError(f"{magic} fixed 4-byte index mode is not authorized")
    data = data_path.read_bytes()
    index = index_path.read_bytes()
    if len(index) < WZX_HEADER_SIZE:
        raise ValueError(f"{index_path.name} header is too small")
    count = struct.unpack_from("<I", index, 44)[0]
    if count < 0 or WZX_HEADER_SIZE + count * 4 > len(index):
        raise ValueError(f"{index_path.name} index table is invalid")
    offsets = [struct.unpack_from("<I", index, WZX_HEADER_SIZE + slot * 4)[0] for slot in range(count)]
    records = []
    valid = 0
    for (slot, offset) in enumerate(offsets):
        if offset < WZL_DATA_HEADER_SIZE or offset + PAK_IMAGE_HEADER_SIZE > len(data):
            records.append(_empty_record(AssetRecord, data_path, slot, kind, magic))
        else:
            try:
                header = RecoveredImageHeader.decode(data[offset:offset + PAK_IMAGE_HEADER_SIZE])
                if not _header_is_valid(header):
                    raise ValueError("invalid image header")
                records.append(_record_from_header(AssetRecord, data_path, slot, offset + PAK_IMAGE_HEADER_SIZE, header, kind, transparent_zero, magic))
                valid += 1
            except Exception:
                records.append(_empty_record(AssetRecord, data_path, slot, kind, magic))

    if count and not valid:
        if all(int(offset or 0) == 0 for offset in offsets):
            return (magic, count, records, "recovered-direct-empty")
        if os.environ.get(ALLOW_LEGACY_WIL_BGRA32_ENV, "").strip().lower() not in {"1", "true", "yes", "on"}:
            raise ValueError(f"{magic} parsed zero valid image headers")
        legacy_records = []
        legacy_valid = 0
        for slot, offset in enumerate(offsets):
            next_offset = next((candidate for candidate in offsets[slot + 1:] if candidate > offset), len(data))
            if offset < 0 or offset + 8 > len(data):
                legacy_records.append(_empty_record(AssetRecord, data_path, slot, kind, magic))
                continue
            width = int.from_bytes(data[offset:offset + 2], "little", signed=False)
            height = int.from_bytes(data[offset + 2:offset + 4], "little", signed=False)
            origin_x = int.from_bytes(data[offset + 4:offset + 6], "little", signed=True)
            origin_y = int.from_bytes(data[offset + 6:offset + 8], "little", signed=True)
            if not (0 < width <= 4096 and 0 < height <= 4096):
                legacy_records.append(_empty_record(AssetRecord, data_path, slot, kind, magic))
                continue
            header = RecoveredImageHeader(
                image_type=9,
                flag1=0,
                flag2=0,
                alpha=0,
                width=width,
                height=height,
                offset_x=origin_x,
                offset_y=origin_y,
                packed_size=0,
            )
            data_off = offset + 8
            if data_off + header.raw_payload_size > min(next_offset, len(data)):
                legacy_records.append(_empty_record(AssetRecord, data_path, slot, kind, magic))
                continue
            record = _record_from_header(AssetRecord, data_path, slot, data_off, header, kind, transparent_zero, magic)
            record.method = "legacy_bgra32"
            record.file_name = f"{slot:05d}_{width}x{height}_32b_legacy_bgra32_{kind}.png"
            legacy_records.append(record)
            legacy_valid += 1
        if not legacy_valid:
            raise ValueError(f"{magic} parsed zero valid image headers")
        return (magic, count, legacy_records, "legacy-wil-bgra32")
    return (magic, count, records, "recovered-direct")


def load_recovered_resource_records(
    path,
    password='',
    *,
    transparent_zero=True,
    progress=None,
    decode_profile: Mapping[str, Any] | None = None,
):
    suffix = Path(path).suffix.lower()
    if suffix in {'.wix', '.wzx', '.wzl', '.wil', '.wis'}:
        return load_recovered_wil_records(
          path, transparent_zero=transparent_zero, decode_profile=decode_profile)
    return load_recovered_pak_records(
      path,
      password,
      transparent_zero=transparent_zero,
      progress=progress,
      decode_profile=decode_profile)


def load_record_pixels(record: object) -> bytes:
    path = getattr(record, "pak_path", None)
    if path is None:
        raise ValueError("record does not reference an asset file")
    data_off = int(getattr(record, "data_off", 0))
    data_len = int(getattr(record, "data_len", 0))
    payload = _read_payload_slice(Path(path), data_off, data_len)
    method = str(getattr(record, "method", ""))
    compressed_size = int(getattr(record, "compressed_size", 0) or 0)
    if method == "zlib" or method.endswith("_zlib") or compressed_size > 0:
        return zlib.decompress(payload)
    return payload

def _rgba_from_rgb565(value: int, transparent_zero: bool=True) -> tuple[int, int, int, int]:
    r = (value >> 11 & 31) * 255 // 31
    g = (value >> 5 & 63) * 255 // 63
    b = (value & 31) * 255 // 31
    a = 0 if transparent_zero and value == 0 else 255
    return (r, g, b, a)

def _mir_indexed8_palette() -> tuple[tuple[int, int, int, int], ...]:
    global _MIR_INDEXED8_PALETTE
    if _MIR_INDEXED8_PALETTE is not None:
        return _MIR_INDEXED8_PALETTE
    try:
        from .recovered_geepak_codec import default_palette
    except ImportError:
        from core.npc_preview.recovered_geepak_codec import default_palette
    try:
        palette = tuple(tuple(int(channel) for channel in color[:4]) for color in default_palette())
        if len(palette) >= 256:
            _MIR_INDEXED8_PALETTE = palette[:256]
            return _MIR_INDEXED8_PALETTE
    except Exception:
        palette = ()
    _MIR_INDEXED8_PALETTE = tuple((index, index, index, 0 if index == 0 else 255) for index in range(256))
    return _MIR_INDEXED8_PALETTE

def _wzl_alpha4_to_rgba(raw, width, height, pitch, transparent_zero=True):
    color_pitch = pitch // 2
    alpha_pitch = max(1, width // 2)
    alpha_base = color_pitch * height
    image = Image.new("RGBA", (width, height))
    pixels = image.load()
    for y in range(height):
        color_y = height - 1 - y
        alpha_y = y
        color_row = raw[color_y * color_pitch:color_y * color_pitch + width * 2]
        alpha_row = raw[alpha_base + alpha_y * alpha_pitch:alpha_base + alpha_y * alpha_pitch + alpha_pitch]
        for x in range(width):
            cpos = x * 2
            if cpos + 1 >= len(color_row):
                continue
            value = color_row[cpos] | color_row[cpos + 1] << 8
            (r, g, b, fallback_a) = _rgba_from_rgb565(value, transparent_zero)
            apos = x // 2
            if apos >= len(alpha_row):
                a = fallback_a
            else:
                packed = alpha_row[apos]
                nibble = packed & 15 if x % 2 == 0 else packed >> 4 & 15
                a = nibble * 16
            pixels[(x, y)] = (
             r, g, b, a)

    image.load()
    return image

def record_to_image(record: object) -> Image.Image:
    raw = load_record_pixels(record)
    width = int(getattr(record, "width", 0))
    height = int(getattr(record, "height", 0))
    image_type = int(getattr(record, "enc1", 0))
    bits = int(getattr(record, "bits", BITS_BY_TYPE.get(image_type, 0)))
    stride = int(getattr(record, "stride", dib_stride(bits, width)))
    alpha_stride = int(getattr(record, "alpha_stride", 0))
    alpha_flag = int(getattr(record, "enc2", 0))
    method = str(getattr(record, "method", ""))
    kind = str(getattr(record, "kind", ""))
    transparent_zero = bool(getattr(record, "transparent_zero", True))
    if method.startswith("wzl_alpha4") or (kind in {'recovered_wil', 'recovered_wis', 'recovered_wzl'} and image_type == 5 and alpha_flag == 9):
        return _wzl_alpha4_to_rgba(raw, width, height, stride, transparent_zero)
    flip_y = kind in {'recovered_wil', 'recovered_pak', 'recovered_wis', 'recovered_wzl'}
    image = render_planes_to_rgba(raw,
      width,
      height,
      image_type,
      bits,
      stride,
      (alpha_stride if alpha_flag else 0),
      transparent_zero=transparent_zero,
      flip_y=flip_y)
    image.load()
    return image

def render_planes_to_rgba(raw, width, height, image_type, bits, stride, alpha_stride, *, transparent_zero, flip_y):
    if width <= 0 or height <= 0:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    color_size = stride * height
    color = raw[:color_size]
    alpha = raw[color_size:color_size + alpha_stride * height] if alpha_stride else b""
    indexed8_palette = _mir_indexed8_palette() if bits == 8 else ()
    rgba = bytearray(width * height * 4)
    for y in range(height):
        source_y = height - 1 - y if flip_y else y
        color_row = color[source_y * stride:source_y * stride + stride]
        alpha_row = alpha[source_y * alpha_stride:source_y * alpha_stride + alpha_stride] if alpha_stride else b""
        for x in range(width):
            if bits == 8:
                value = color_row[x] if x < len(color_row) else 0
                r, g, b, palette_a = indexed8_palette[value]
                a = alpha_row[x] if x < len(alpha_row) else palette_a
                if transparent_zero and value == 0:
                    a = 0
            elif bits == 16:
                start = x * 2
                value = int.from_bytes(color_row[start:start + 2], "little") if start + 2 <= len(color_row) else 0
                r = (value >> 11 & 31) * 255 // 31
                g = (value >> 5 & 63) * 255 // 63
                b = (value & 31) * 255 // 31
                a = alpha_row[x] if x < len(alpha_row) else 0 if transparent_zero and value == 0 else 255
            elif bits == 24:
                start = x * 3
                if start + 3 <= len(color_row):
                    b, g, r = color_row[start:start + 3]
                else:
                    b = g = r = 0
                a = alpha_row[x] if x < len(alpha_row) else 0 if transparent_zero and (r, g, b) == (0, 0, 0) else 255
            elif bits == 32:
                start = x * 4
                if start + 4 <= len(color_row):
                    b, g, r, stored_a = color_row[start:start + 4]
                else:
                    b = g = r = 0
                    stored_a = 255
                a = alpha_row[x] if x < len(alpha_row) else stored_a
            else:
                r = g = b = 0
                a = 0
            out = (y * width + x) * 4
            rgba[out:out + 4] = bytes([r, g, b, a])
    return Image.frombytes("RGBA", (width, height), bytes(rgba))

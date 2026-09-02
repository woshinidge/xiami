from __future__ import annotations

import struct
import zlib
from collections.abc import Iterator
from typing import Any

ZLIB_HEADERS = (b"x\x9c", b"x\xda", b"x\x01")

_FRAME_PREFIX_FORMATS = {
    b"d\xadC\xd9": "rgb565",
    b"b\xadC\xd9": "gray8",
    b"f\xadC\xd9": "bgrx32",
    b"g\xadC\xd9": "bgr24",
    b"g\xadC\xd8": "bgr24a8",
}


def u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def s16(value: int) -> int:
    if value & 0x8000:
        return value - 0x10000
    return value


def align4(value: int) -> int:
    return (value + 3) & -4


def rgb565_to_bgra(pixel: int, transparent_zero: bool) -> bytes:
    if transparent_zero and pixel == 0:
        return b"\x00\x00\x00\x00"
    blue = (pixel & 0x1F) * 255 // 31
    green = ((pixel >> 5) & 0x3F) * 255 // 63
    red = ((pixel >> 11) & 0x1F) * 255 // 31
    return bytes((blue, green, red, 255))


def decoded_to_bgra(
    decoded: bytes,
    width: int,
    height: int,
    image_format: str,
    transparent_zero: bool,
) -> bytes:
    output = bytearray(width * height * 4)

    if image_format == "rgb565":
        stride = align4(width * 2)
        for y in range(height):
            src_base = y * stride
            dst_base = y * width * 4
            for x in range(width):
                pixel = struct.unpack_from("<H", decoded, src_base + x * 2)[0]
                output[dst_base + x * 4 : dst_base + x * 4 + 4] = rgb565_to_bgra(pixel, transparent_zero)
        return bytes(output)

    if image_format == "gray8":
        stride = align4(width)
        for y in range(height):
            src_base = y * stride
            dst_base = y * width * 4
            for x in range(width):
                value = decoded[src_base + x]
                alpha = 0 if transparent_zero and value == 0 else 255
                output[dst_base + x * 4 : dst_base + x * 4 + 4] = bytes((value, value, value, alpha))
        return bytes(output)

    if image_format == "bgr24":
        stride = align4(width * 3)
        for y in range(height):
            src_base = y * stride
            dst_base = y * width * 4
            for x in range(width):
                b, g, r = decoded[src_base + x * 3 : src_base + x * 3 + 3]
                output[dst_base + x * 4 : dst_base + x * 4 + 4] = bytes((b, g, r, 255))
        return bytes(output)

    if image_format == "bgr24a8":
        stride = align4(width * 3)
        alpha_stride = align4(width)
        alpha_base = stride * height
        for y in range(height):
            src_base = y * stride
            alpha_row = alpha_base + y * alpha_stride
            dst_base = y * width * 4
            for x in range(width):
                b, g, r = decoded[src_base + x * 3 : src_base + x * 3 + 3]
                alpha_offset = alpha_row + x
                a = decoded[alpha_offset] if alpha_offset < len(decoded) else 255
                output[dst_base + x * 4 : dst_base + x * 4 + 4] = bytes((b, g, r, a))
        return bytes(output)

    if image_format == "bgrx32":
        for y in range(height):
            src_base = y * width * 4
            dst_base = y * width * 4
            for x in range(width):
                b, g, r, _unused = decoded[src_base + x * 4 : src_base + x * 4 + 4]
                output[dst_base + x * 4 : dst_base + x * 4 + 4] = bytes((b, g, r, 255))
        return bytes(output)

    raise ValueError(f"unsupported image format: {image_format}")


def expected_decoded_size(width: int, height: int, image_format: str) -> int:
    if image_format == "rgb565":
        return align4(width * 2) * height
    if image_format == "gray8":
        return align4(width) * height
    if image_format == "bgr24":
        return align4(width * 3) * height
    if image_format == "bgr24a8":
        return (align4(width * 3) + align4(width)) * height
    if image_format == "bgrx32":
        return width * height * 4
    raise ValueError(f"unsupported image format: {image_format}")


def find_zlib_offsets(data: bytes) -> Iterator[int]:
    seen: set[int] = set()
    for header in ZLIB_HEADERS:
        pos = 0
        while True:
            pos = data.find(header, pos)
            if pos < 0:
                break
            if pos not in seen:
                seen.add(pos)
                yield pos
            pos += 1


def parse_frame_header(data: bytes, zlib_offset: int) -> dict[str, Any] | None:
    if zlib_offset < 16:
        return None

    header = data[zlib_offset - 16 : zlib_offset]
    width = u16(header, 4) ^ 16046
    height = u16(header, 6) ^ 3041
    origin_x = s16(u16(header, 8) ^ 36751)
    origin_y = s16(u16(header, 10) ^ 36751)
    compressed_size = u32(header, 12) ^ 2408550287

    if not (0 < width <= 4096 and 0 < height <= 4096):
        return None
    if not 8 <= compressed_size <= len(data) - zlib_offset:
        return None

    image_format = _FRAME_PREFIX_FORMATS.get(header[:4])
    if image_format is None:
        return None

    return {
        "raw_header": header,
        "format": image_format,
        "width": width,
        "height": height,
        "origin_x": origin_x,
        "origin_y": origin_y,
        "compressed_size": compressed_size,
    }


def decompress_exact(chunk: bytes) -> bytes | None:
    obj = zlib.decompressobj()
    pixels = obj.decompress(chunk)
    if not obj.eof or obj.unused_data:
        return None
    return pixels

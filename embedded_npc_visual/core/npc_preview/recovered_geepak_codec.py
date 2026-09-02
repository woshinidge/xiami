"""GeePak image codec used by the NPC previewer."""

import base64
import math
import os
import pathlib
import re
import struct
import zlib
from collections import Counter, defaultdict
from functools import lru_cache

from PIL import Image

VALID_ENC1 = (3, 5, 6, 7, 9)
ENC1_BITS = {3: 8, 5: 16, 6: 24, 7: 32, 9: 32}
MIR_STANDARD_PALETTE_RGBA_B64 = "AAAAAIAAAP8AgAD/gIAA/wAAgP+AAID/AICA/8DAwP9VgJf/nbnI/3tzc/8tKSn/WlJS/2NaWv9COTn/HRgY/xgQEP8pGBj/EAgI//J5cf/hZ1///1pa//8xMf/WWlL/lBAA/5QpGP85CAD/cxAA/7UYAP+9Y1L/QhgQ//+qmf9aEAD/czkp/6VKMf+Ue3P/vVIx/1IhEP97MRj/LRgQ/4xKMf+UKQD/vTEA/8ZzUv9rMRj/xmtC/85KAP+lYzn/WjEY/yoQAP8VCAD/OhgA/wgAAP8pAAD/SgAA/50AAP/cAAD/3gAA//sAAP+cc1L/lGtK/3NKKf9SMRj/jEoY/4hEEf9KIQD/IRgQ/9aUWv/GayH/72sA//93AP+llIT/QjEh/xgQCP8pGAj/IRAA/zkpGP+MYzn/QikQ/2tCGP97Shj/lEoA/4yEe/9rY1r/SkI5/ykhGP9GOSn/taWU/3trWv/OsZT/pYxz/4xzWv+1lHP/1qVz/++lSv/vxoz/e2NC/2tWOf+9lFr/YzkA/9bGrf9SQin/lGMY/+/Wrf+ljGP/Y1pK/72le/9aQhj/vYwx/zUxKf+UhGP/e2tK/6WMWv9aSin/nHs5/0IxEP/vrSH/GBAA/ykhAP+cawD/lIRa/1JCGP9rWin/e2Mh/5x7If/epQD/WlI5/zEpEP/OvXv/Y1o5/5SESv/GpSn/EJwY/0KMSv8xjEL/EJQp/wgYEP8IGBj/CCkQ/xhCKf+lta3/a3Nz/xgpKf8YQkr/MUJK/2PG3v9E3f//jNbv/3NrOf/33jn/9++M//fnAP9ra1r/Woyl/zm17/9KnM7/MYS1/zFSa//e3tb/vb21/4yMhP/3997/AAgY/wgYOf8IECn/CBgA/wgpAP8AUqX/AHve/xApSv8QOWv/EFKM/yFapf8QMVr/EEKE/zFShP8YITH/Slp7/1Jrpf8pOWP/EEre/ykpIf9KSjn/KSkY/0pKKf97e0L/nJxK/1paKf9CQhT/OTkA/1lZAP/KNSz/a3Mh/ykxAP8xORD/MTkY/0JKAP9SYxj/WnMp/zFKGP8YIQD/GDEA/xg5EP9jhEr/a71K/2O1Sv9jvUr/WpxK/0qMOf9jxkr/Y9ZK/1KESv8xcyn/Y8Za/1K9Sv8Q/wD/GCkY/0qISv9K50r/AFoA/wCIAP8AlAD/AN4A/wDuAP8A+wD/SlqU/2Nztf97jNb/a3vW/3eI///Gxs7/lJSc/5yUxv8xMTn/KRiE/xgAhP9KQlL/UkJ7/2Nac//Otff/jHuc/3cizP/dqv//8LQq/98An//jF7P///vw/6CgpP+AgID//wAA/wD/AP///wD/AAD///8A//8A/////////w=="


def scan_zlib_records(data):
    records = []
    signatures = (b"x\x01", b"x^", b"x\x9c", b"x\xda")
    offsets = set()
    for signature in signatures:
        start = 0
        while True:
            pos = data.find(signature, start)
            if pos < 0:
                break
            offsets.add(pos)
            start = pos + 1

    skip_until = 0
    for i in sorted(offsets):
        if i < skip_until:
            continue
        if i < len(data) - 2:
            try:
                dec = zlib.decompressobj()
                raw = dec.decompress(data[i:])
                consumed = len(data[i:]) - len(dec.unused_data)
                if consumed > 8 and raw:
                    records.append({
                        "kind": "zlib",
                        "hdr_off": i - 16,
                        "data_off": i,
                        "data_len": consumed,
                        "out_len": len(raw),
                        "raw": raw,
                    })
                    skip_until = i + consumed
            except zlib.error:
                continue
    return records


def add_raw_gap_records(records, data):
    enriched = []
    for idx, rec in enumerate(records):
        enriched.append(rec)
        end = rec["data_off"] + rec["data_len"]
        if idx + 1 < len(records):
            next_off = records[idx + 1]["data_off"]
            gap = next_off - end
            if gap > 32:
                raw_off = end + 16
                raw_len = gap - 32
                enriched.append({
                    "kind": "raw",
                    "hdr_off": end,
                    "data_off": raw_off,
                    "data_len": raw_len,
                    "out_len": raw_len,
                    "gap_end": next_off - 16,
                    "raw": data[raw_off:raw_off + raw_len],
                })
    enriched.sort(key=lambda item: item["hdr_off"])
    return enriched


def width_bytes(width, bits):
    return (width * bits + 31) // 32 * 4


def record_stride(width, height, bits, length, kind):
    if width <= 0 or height <= 0:
        return 0
    if kind == "zlib":
        if length % height == 0:
            stride = length // height
            if stride >= width * (bits // 8):
                return stride
        return width_bytes(width, bits)
    return width * (bits // 8)


@lru_cache(maxsize=1)
def default_palette():
    try:
        raw_palette = base64.b64decode(MIR_STANDARD_PALETTE_RGBA_B64, validate=True)
        if len(raw_palette) >= 1024:
            return tuple(tuple(raw_palette[i:i + 4]) for i in range(0, 1024, 4))
    except (ValueError, base64.binascii.Error):
        raw_palette = b""

    source_candidates = [
        pathlib.Path(r"E:\BaiduNetdiskDownload\GXX三端引擎移动端站点\GameOfMir_hwmir2\Source\ImageView\M2Wil.pas"),
        pathlib.Path(r"E:\BaiduNetdiskDownload\GXX三端引擎移动端站点\GameOfMir_hwmir2\Source\SceneUI\uGameEngine.pas"),
    ]
    for base in (pathlib.Path(r"E:\BaiduNetdiskDownload"), pathlib.Path.cwd()):
        if not base.is_dir():
            continue
        try:
            matches = list(base.rglob("M2Wil.pas"))
        except OSError:
            matches = []
        for match in matches:
            text = str(match)
            if "GameOfMir_hwmir2" in text and "ImageView" in text:
                source_candidates.insert(0, match)
                break

    for source_path in source_candidates:
        if not source_path.is_file():
            continue
        text = source_path.read_text(encoding="latin1", errors="ignore")
        match = re.search(
            r"ColorArray\s*:\s*array\s*\[0\.\.1023\]\s*of\s*Byte\s*=\s*\((.*?)\);",
            text,
            flags=(re.IGNORECASE | re.DOTALL),
        )
        if not match:
            continue
        values = [int(value, 16) for value in re.findall(r"\$([0-9A-Fa-f]{1,2})", match.group(1))]
        if len(values) >= 1024:
            palette = []
            for i in range(256):
                b, g, r, reserved = values[i * 4:i * 4 + 4]
                alpha = 0 if (r, g, b, reserved) == (0, 0, 0, 0) else 255
                palette.append((r, g, b, alpha))
            return tuple(palette)
    return tuple((i, i, i, 0 if i == 0 else 255) for i in range(256))


def rgb565_diff(a, b):
    return (
        abs((a & 31) - (b & 31)) * 2
        + abs((a >> 5 & 63) - (b >> 5 & 63))
        + abs((a >> 11 & 31) - (b >> 11 & 31)) * 2
    )


def word16(raw, pos):
    return raw[pos] | (raw[pos + 1] << 8)


def score_rgb565_shape(raw, width, height, stride):
    if width <= 0 or height <= 1 or stride < width * 2:
        return -1000000000
    step_x = max(1, width // 160)
    step_y = max(1, height // 120)
    horiz_sum = horiz_n = vert_sum = vert_n = 0

    for y in range(0, height, step_y):
        base = y * stride
        prev = None
        for x in range(0, width, step_x):
            pos = base + x * 2
            if pos + 1 >= base + stride or pos + 1 >= len(raw):
                break
            current = word16(raw, pos)
            if prev is not None:
                horiz_sum += rgb565_diff(prev, current)
                horiz_n += 1
            prev = current

    for y in range(0, height - 1, step_y):
        row_a = y * stride
        row_b = (y + 1) * stride
        for x in range(0, width, step_x):
            pos_a = row_a + x * 2
            pos_b = row_b + x * 2
            if pos_a + 1 >= row_a + stride or pos_b + 1 >= row_b + stride:
                break
            if pos_b + 1 >= len(raw):
                break
            vert_sum += rgb565_diff(word16(raw, pos_a), word16(raw, pos_b))
            vert_n += 1

    horiz = horiz_sum / max(1, horiz_n)
    vert = vert_sum / max(1, vert_n)
    aspect = width / height
    aspect_penalty = abs(math.log(max(aspect, 1 / aspect)))
    common_bonus = (2 if width % 8 == 0 else 0) + (1 if height % 8 == 0 else 0)
    pad_penalty = (stride - width * 2) / max(1, stride) * 8
    return -(horiz * 0.6 + vert * 1.4) - aspect_penalty * 4 - pad_penalty + common_bonus


@lru_cache(maxsize=None)
def rgb565_shape_candidates(length, max_dim=4096):
    candidates = []
    limit = int(math.isqrt(length))
    divs = set()
    for value in range(1, limit + 1):
        if length % value == 0:
            divs.add(value)
            divs.add(length // value)
    for stride in sorted(divs):
        if stride % 4:
            continue
        height = length // stride
        if not (1 <= height <= max_dim):
            continue
        if stride > max_dim * 4:
            continue
        for width in (stride // 2, stride // 2 - 1):
            if 1 <= width <= max_dim:
                candidates.append((width, height, stride))
    return tuple(candidates)


def best_rgb565_dimensions(raw, max_dim=4096):
    length = len(raw)
    shapes = rgb565_shape_candidates(length, max_dim)
    if not shapes:
        return None
    return max((score_rgb565_shape(raw, width, height, stride), width, height, stride) for width, height, stride in shapes)


def rgb565_to_image(raw, width, height, stride, transparent_zero=True):
    image = Image.new("RGBA", (width, height))
    pixels = image.load()
    for y in range(height):
        source_y = height - 1 - y
        row = raw[source_y * stride:source_y * stride + width * 2]
        for x in range(width):
            pos = x * 2
            if pos + 1 >= len(row):
                continue
            value = row[pos] | (row[pos + 1] << 8)
            r = ((value >> 11) & 31) * 255 // 31
            g = ((value >> 5) & 63) * 255 // 63
            b = (value & 31) * 255 // 31
            a = 0 if transparent_zero and value == 0 else 255
            pixels[x, y] = (r, g, b, a)
    return image


def rgba_from_rgb565(value, transparent_zero=True):
    r = ((value >> 11) & 31) * 255 // 31
    g = ((value >> 5) & 63) * 255 // 63
    b = (value & 31) * 255 // 31
    a = 0 if transparent_zero and value == 0 else 255
    return (r, g, b, a)


def indexed8_to_image(raw, width, height, stride, transparent_zero=True):
    palette = default_palette()
    image = Image.new("RGBA", (width, height))
    pixels = image.load()
    for y in range(height):
        source_y = height - 1 - y
        row = raw[source_y * stride:source_y * stride + width]
        for x, value in enumerate(row[:width]):
            r, g, b, a = palette[value]
            if transparent_zero and value == 0:
                a = 0
            pixels[x, y] = (r, g, b, a)
    return image


def bgr24_to_image(raw, width, height, stride, transparent_zero=True):
    image = Image.new("RGBA", (width, height))
    pixels = image.load()
    for y in range(height):
        source_y = height - 1 - y
        row = raw[source_y * stride:source_y * stride + width * 3]
        for x in range(width):
            pos = x * 3
            if pos + 2 >= len(row):
                continue
            b, g, r = row[pos], row[pos + 1], row[pos + 2]
            a = 0 if transparent_zero and (r, g, b) == (0, 0, 0) else 255
            pixels[x, y] = (r, g, b, a)
    return image


def bgr24_pitched_to_image(raw, width, height, pitch, transparent_zero=True):
    image = Image.new("RGBA", (width, height))
    pixels = image.load()
    for y in range(height):
        source_y = height - 1 - y
        row = raw[source_y * pitch:source_y * pitch + width * 3]
        for x in range(width):
            pos = x * 3
            if pos + 2 >= len(row):
                continue
            b, g, r = row[pos], row[pos + 1], row[pos + 2]
            a = 0 if transparent_zero and (r, g, b) == (0, 0, 0) else 255
            pixels[x, y] = (r, g, b, a)
    return image


def bgra32_to_image(raw, width, height, stride, transparent_zero=True):
    image = Image.new("RGBA", (width, height))
    pixels = image.load()
    for y in range(height):
        source_y = height - 1 - y
        row = raw[source_y * stride:source_y * stride + width * 4]
        for x in range(width):
            pos = x * 4
            if pos + 3 >= len(row):
                continue
            b, g, r, a = row[pos], row[pos + 1], row[pos + 2], row[pos + 3]
            if transparent_zero and (r, g, b, a) == (0, 0, 0, 0):
                pixels[x, y] = (0, 0, 0, 0)
                continue
            pixels[x, y] = (r, g, b, max(a, 255))
    return image


def bgra32_pitched_to_image(raw, width, height, pitch, transparent_zero=True):
    image = Image.new("RGBA", (width, height))
    pixels = image.load()
    for y in range(height):
        source_y = height - 1 - y
        row = raw[source_y * pitch:source_y * pitch + width * 4]
        for x in range(width):
            pos = x * 4
            if pos + 3 >= len(row):
                continue
            b, g, r, a = row[pos], row[pos + 1], row[pos + 2], row[pos + 3]
            if transparent_zero and (r, g, b, a) == (0, 0, 0, 0):
                pixels[x, y] = (0, 0, 0, 0)
                continue
            pixels[x, y] = (r, g, b, max(a, 255))
    return image


def alpha4_to_image(raw, width, height, color_stride, alpha_stride, transparent_zero=True):
    image = Image.new("RGBA", (width, height))
    pixels = image.load()
    alpha_base = color_stride * height
    for y in range(height):
        color_y = y
        alpha_y = height - 1 - y
        color_row = raw[color_y * color_stride:color_y * color_stride + width * 2]
        alpha_row = raw[alpha_base + alpha_y * alpha_stride:alpha_base + alpha_y * alpha_stride + alpha_stride]
        for x in range(width):
            cpos = x * 2
            if cpos + 1 >= len(color_row):
                continue
            value = color_row[cpos] | (color_row[cpos + 1] << 8)
            r, g, b, fallback_a = rgba_from_rgb565(value, transparent_zero)
            apos = x // 2
            if apos >= len(alpha_row):
                a = fallback_a
            else:
                packed = alpha_row[apos]
                nibble = (packed & 15) if x % 2 == 0 else ((packed >> 4) & 15)
                a = nibble * 17
            pixels[x, y] = (r, g, b, a)
    return image


def wzl_alpha4_to_image(raw, width, height, pitch, transparent_zero=True):
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
            value = color_row[cpos] | (color_row[cpos + 1] << 8)
            r, g, b, fallback_a = rgba_from_rgb565(value, transparent_zero)
            apos = x // 2
            if apos >= len(alpha_row):
                a = fallback_a
            else:
                packed = alpha_row[apos]
                nibble = (packed & 15) if x % 2 == 0 else ((packed >> 4) & 15)
                a = nibble * 16
            pixels[x, y] = (r, g, b, a)
    return image


def bgr24_alpha8_to_image_slow(raw, width, height, color_stride, alpha_stride, transparent_zero=True, color_order=(2, 1, 0)):
    image = Image.new("RGBA", (width, height))
    pixels = image.load()
    alpha_base = color_stride * height
    r_index, g_index, b_index = color_order
    for y in range(height):
        source_y = height - 1 - y
        color_row = raw[source_y * color_stride:source_y * color_stride + width * 3]
        alpha_row = raw[alpha_base + source_y * alpha_stride:alpha_base + source_y * alpha_stride + width]
        for x in range(width):
            pos = x * 3
            if pos + 2 >= len(color_row):
                continue
            r = color_row[pos + r_index]
            g = color_row[pos + g_index]
            b = color_row[pos + b_index]
            if x < len(alpha_row):
                a = alpha_row[x]
            else:
                a = 0 if transparent_zero and (r, g, b) == (0, 0, 0) else 255
            pixels[x, y] = (r, g, b, a)
    return image


def bgr24_alpha8_to_image(raw, width, height, color_stride, alpha_stride, transparent_zero=True, color_order=(2, 1, 0)):
    alpha_base = color_stride * height
    if width <= 0 or height <= 0 or color_stride < width * 3 or alpha_stride < width or alpha_base + alpha_stride * height > len(raw):
        return bgr24_alpha8_to_image_slow(raw, width, height, color_stride, alpha_stride, transparent_zero, color_order)
    color_plane = raw[:alpha_base]
    alpha_plane = raw[alpha_base:alpha_base + alpha_stride * height]
    try:
        if color_order == (2, 1, 0):
            image = Image.frombytes("RGB", (width, height), color_plane, "raw", "BGR", color_stride, -1).convert("RGBA")
        elif color_order == (0, 1, 2):
            image = Image.frombytes("RGB", (width, height), color_plane, "raw", "RGB", color_stride, -1).convert("RGBA")
        elif color_order == (0, 2, 1):
            swapped = Image.frombytes("RGB", (width, height), color_plane, "raw", "RGB", color_stride, -1)
            r, b, g = swapped.split()
            image = Image.merge("RGB", (r, g, b)).convert("RGBA")
        else:
            return bgr24_alpha8_to_image_slow(raw, width, height, color_stride, alpha_stride, transparent_zero, color_order)
        alpha = Image.frombytes("L", (width, height), alpha_plane, "raw", "L", alpha_stride, -1)
        image.putalpha(alpha)
        return image
    except (OSError, ValueError):
        return bgr24_alpha8_to_image_slow(raw, width, height, color_stride, alpha_stride, transparent_zero, color_order)


def render_pixels(raw, width, height, bits, stride, kind, transparent_zero=True, alpha_stride=0):
    if kind == "wzl_alpha4":
        return wzl_alpha4_to_image(raw, width, height, stride, transparent_zero)
    if kind == "pitch24":
        return bgr24_pitched_to_image(raw, width, height, stride, transparent_zero)
    if kind == "pitch32":
        return bgra32_pitched_to_image(raw, width, height, stride, transparent_zero)
    if kind == "header_rbg24a8":
        return bgr24_alpha8_to_image(raw, width, height, stride, alpha_stride, transparent_zero, (0, 2, 1))
    if bits == 24 and alpha_stride:
        return bgr24_alpha8_to_image(raw, width, height, stride, alpha_stride, transparent_zero)
    if alpha_stride:
        return alpha4_to_image(raw, width, height, stride, alpha_stride, transparent_zero)
    if bits == 8:
        return indexed8_to_image(raw, width, height, stride, transparent_zero)
    if bits == 16:
        return rgb565_to_image(raw, width, height, stride, transparent_zero)
    if bits == 24:
        return bgr24_to_image(raw, width, height, stride, transparent_zero)
    if bits == 32:
        return bgra32_to_image(raw, width, height, stride, transparent_zero)
    raise ValueError(f"unsupported bit depth: {bits}")


def assign_key_slots(records, data):
    key_to_slot = {}
    key_order = []
    for rec in records:
        header = data[rec["hdr_off"]:rec["hdr_off"] + 16]
        plain_len = rec["data_len"] if rec["kind"] == "zlib" else 0
        plain = struct.pack("<I", plain_len)
        key = bytes(header[12 + i] ^ plain[i] for i in range(4))
        if key not in key_to_slot:
            key_to_slot[key] = len(key_order)
            key_order.append(key)
        rec["key_slot"] = key_to_slot[key]
        rec["len_key"] = struct.unpack("<I", key)[0]


def align_to(value, alignment):
    return (value + alignment - 1) // alignment * alignment


def divisors(value):
    result = set()
    limit = int(math.isqrt(value))
    for n in range(1, limit + 1):
        if value % n == 0:
            result.add(n)
            result.add(value // n)
    return result


def shape_weight(width, height, bits, stride, kind):
    bpp = bits // 8
    minimum = width * bpp
    if stride < minimum:
        return -1000000
    pad = stride - minimum
    score = 100
    if kind == "zlib":
        if stride == width_bytes(width, bits):
            score += 35
        if stride == align_to(minimum, 16):
            score += 20
        if stride == minimum:
            score += 18
        score -= min(pad, 64)
    elif stride == minimum:
        score += 35
    else:
        score -= 200
    aspect = width / max(1, height)
    if aspect > 20 or aspect < 0.05:
        score -= 20
    if width % 2 == 0:
        score += 2
    if width % 4 == 0:
        score += 1
    if height % 2 == 0:
        score += 1
    return score


@lru_cache(maxsize=None)
def payload_shape_candidates(length, kind, max_dim=4096, max_pad=64):
    candidates = []
    if length <= 0:
        return tuple()
    if kind == "raw":
        for bits in (8, 16, 24, 32):
            bpp = bits // 8
            if length % bpp:
                continue
            pixels = length // bpp
            for width in divisors(pixels):
                height = pixels // width
                if 1 <= width <= max_dim and 1 <= height <= max_dim:
                    stride = width * bpp
                    candidates.append((width, height, bits, stride, 0, "raw"))
        for height in divisors(length):
            if not (1 <= height <= max_dim):
                continue
            stride = length // height
            widths = {(stride - extra) // 4 for extra in (0, 4) if stride >= extra}
            for width in widths:
                if not (1 <= width <= max_dim):
                    continue
                color_stride = width_bytes(width, 24)
                alpha_stride = align_to(width, 4)
                if color_stride + alpha_stride == stride:
                    candidates.append((width, height, 24, color_stride, alpha_stride, "rgb24a8"))
        return tuple(candidates)

    for height in divisors(length):
        if not (1 <= height <= max_dim):
            continue
        stride = length // height
        if stride <= 0:
            continue
        for bits in (8, 16, 24, 32):
            bpp = bits // 8
            widths = {stride // bpp, stride // bpp - 1 if bits == 16 and stride % 4 == 0 else 0}
            for alignment in (4, 16):
                min_width = max(1, (stride - alignment + bpp) // bpp)
                max_width = min(max_dim, stride // bpp)
                for width in range(min_width, max_width + 1):
                    if align_to(width * bpp, alignment) == stride:
                        widths.add(width)
            for width in widths:
                if not (1 <= width <= max_dim):
                    continue
                minimum = width * bpp
                if stride < minimum or stride - minimum > max_pad:
                    continue
                if stride in (minimum, width_bytes(width, bits), align_to(minimum, 16)):
                    candidates.append((width, height, bits, stride, 0, "normal"))
        rgb24a8_widths = {(stride - extra) // 4 for extra in (0, 4) if stride >= extra}
        for width in rgb24a8_widths:
            if not (1 <= width <= max_dim):
                continue
            color_stride = width_bytes(width, 24)
            alpha_stride = align_to(width, 4)
            if color_stride + alpha_stride == stride:
                candidates.append((width, height, 24, color_stride, alpha_stride, "rgb24a8"))
        alpha_center = stride * 2 // 5
        alpha_start = max(1, alpha_center - 96)
        alpha_end = min(max_dim, alpha_center + 96)
        for width in range(alpha_start, alpha_end + 1):
            color_strides = {width * 2, width_bytes(width, 16), align_to(width * 2, 16)}
            alpha_strides = {
                (width + 1) // 2,
                width // 2,
                width_bytes(width, 4),
                align_to((width + 1) // 2, 4),
                align_to((width + 1) // 2, 16),
            }
            for color_stride in color_strides:
                if color_stride < width * 2:
                    continue
                for alpha_stride in alpha_strides:
                    if alpha_stride < width // 2:
                        continue
                    if (color_stride + alpha_stride) * height == length:
                        candidates.append((width, height, 16, color_stride, alpha_stride, "alpha4"))
    return tuple(candidates)


def candidate_matches_record(candidate, enc1):
    _width, _height, bits, _stride, alpha_stride, _mode = candidate
    expected = ENC1_BITS.get(enc1)
    if alpha_stride:
        if enc1 in (5, 6, 7, 9):
            return 8
        return 2
    if expected == bits:
        return 14
    if enc1 == 6 and bits == 32:
        return 9
    if enc1 == 7 and bits in (24, 32):
        return 8
    return 1


def solve_header_model(records, data):
    by_slot = defaultdict(list)
    for seq, rec in enumerate(records):
        rec["seq"] = seq
        by_slot[rec["key_slot"]].append(rec)

    model = {}
    for slot, slot_records in by_slot.items():
        k0_candidates = [
            key for key in range(256)
            if all((data[rec["hdr_off"]] ^ key) in VALID_ENC1 for rec in slot_records)
        ]
        if not k0_candidates:
            continue
        best_choice = None
        for k0 in k0_candidates:
            votes = {}
            supports = Counter()
            for rec in slot_records:
                header = data[rec["hdr_off"]:rec["hdr_off"] + 16]
                enc1 = header[0] ^ k0
                stored_width = struct.unpack_from("<H", header, 4)[0]
                stored_height = struct.unpack_from("<H", header, 6)[0]
                local_best = {}
                for candidate in payload_shape_candidates(len(rec["raw"]), rec["kind"]):
                    width, height, bits, stride, _alpha_stride, _mode = candidate
                    key = (stored_width ^ width, stored_height ^ height)
                    score = shape_weight(width, height, bits, stride, rec["kind"])
                    score += candidate_matches_record(candidate, enc1)
                    if score > local_best.get(key, -1000000):
                        local_best[key] = score
                for key, score in local_best.items():
                    votes[key] = votes.get(key, 0) + score
                    supports[key] += 1
            if not votes:
                continue
            key = max(votes, key=lambda item: (supports[item], votes[item]))
            choice = (supports[key], votes[key], k0, key[0], key[1])
            if best_choice is None or choice[:2] > best_choice[:2]:
                best_choice = choice
        if best_choice is None:
            continue
        support, vote_score, k0, width_key, height_key = best_choice
        k1_candidates = [
            key for key in range(256)
            if all((data[rec["hdr_off"] + 1] ^ key) in (0, 1, 9) for rec in slot_records)
        ]
        model[slot] = {
            "enc1_key": k0,
            "enc2_key": k1_candidates[0] if k1_candidates else 0,
            "width_key": width_key,
            "height_key": height_key,
            "support": support,
            "vote_score": vote_score,
        }
    return model


def clone_raw_record_at(data, offset, gap_end, slot, len_key, model):
    header = data[offset:offset + 16]
    params = model.get(slot)
    if not params:
        return None
    enc1 = header[0] ^ params["enc1_key"]
    enc2 = header[1] ^ params.get("enc2_key", 0)
    width = struct.unpack_from("<H", header, 4)[0] ^ params["width_key"]
    height = struct.unpack_from("<H", header, 6)[0] ^ params["height_key"]
    if not (1 <= width <= 4096 and 1 <= height <= 4096):
        return None
    data_off = offset + 16
    raw_len_candidates = []
    if enc1 == 6:
        rgb24a8_len = (width_bytes(width, 24) + align_to(width, 4)) * height
        if enc2 == 9:
            raw_len_candidates.append(rgb24a8_len)
    bit_candidates = []
    expected_bits = ENC1_BITS.get(enc1)
    if expected_bits:
        bit_candidates.append(expected_bits)
    if enc1 == 6:
        bit_candidates.append(32)
    if enc1 == 7:
        bit_candidates.append(24)
    for bits in bit_candidates:
        raw_len_candidates.append(width * height * (bits // 8))
    if enc1 == 6 and enc2 != 9:
        raw_len_candidates.append((width_bytes(width, 24) + align_to(width, 4)) * height)
    seen_lengths = set()
    for raw_len in raw_len_candidates:
        if raw_len in seen_lengths:
            continue
        seen_lengths.add(raw_len)
        if raw_len > 0 and data_off + raw_len <= gap_end:
            break
    else:
        return None
    return {
        "kind": "raw",
        "hdr_off": offset,
        "data_off": data_off,
        "data_len": raw_len,
        "out_len": raw_len,
        "raw": data[data_off:data_off + raw_len],
        "key_slot": slot,
        "len_key": len_key,
        "gap_end": gap_end,
    }


def split_raw_gap_records(records, data, model):
    len_key_to_slot = {}
    for rec in records:
        if "len_key" in rec and rec["key_slot"] not in len_key_to_slot.values():
            len_key_to_slot[rec["len_key"]] = rec["key_slot"]
    result = []
    changed = False
    for rec in records:
        if rec["kind"] != "raw" or "gap_end" not in rec:
            result.append(rec)
            continue
        start = rec["hdr_off"]
        gap_end = rec["gap_end"]
        hits = []
        for offset in range(start, gap_end - 15):
            stored_len = struct.unpack_from("<I", data, offset + 12)[0]
            slot = len_key_to_slot.get(stored_len)
            if slot is None:
                continue
            candidate = clone_raw_record_at(data, offset, gap_end, slot, stored_len, model)
            if candidate:
                hits.append(candidate)
        if not hits:
            result.append(rec)
            continue
        hits.sort(key=lambda item: item["hdr_off"])
        chain = []
        for candidate in hits:
            candidate_end = candidate["data_off"] + candidate["data_len"]
            if candidate_end > gap_end:
                continue
            chain.append(candidate)
        if len(chain) > 1:
            result.extend(chain)
            changed = True
        else:
            result.append(rec)
    if changed:
        result.sort(key=lambda item: item["hdr_off"])
    return result


def decode_header(rec, data, model):
    params = model.get(rec["key_slot"])
    if not params:
        return None
    header = data[rec["hdr_off"]:rec["hdr_off"] + 16]
    enc1 = header[0] ^ params["enc1_key"]
    enc2 = header[1] ^ params["enc2_key"]
    width = struct.unpack_from("<H", header, 4)[0] ^ params["width_key"]
    height = struct.unpack_from("<H", header, 6)[0] ^ params["height_key"]
    px = struct.unpack_from("<h", header, 8)[0]
    py = struct.unpack_from("<h", header, 10)[0]
    stored_len = struct.unpack_from("<I", header, 12)[0]
    decoded_len = stored_len ^ rec["len_key"]
    return {"enc1": enc1, "enc2": enc2, "width": width, "height": height, "px": px, "py": py, "decoded_len": decoded_len}


def choose_render_format(raw_len, kind, header_info):
    if not header_info:
        return None
    width = header_info["width"]
    height = header_info["height"]
    enc1 = header_info["enc1"]
    if not (1 <= width <= 4096 and 1 <= height <= 4096):
        return None
    if kind == "raw":
        rgb24_stride = width_bytes(width, 24)
        alpha8_stride = align_to(width, 4)
        if enc1 in (6, 7, 9) and (rgb24_stride + alpha8_stride) * height == raw_len:
            return (24, rgb24_stride, alpha8_stride, "header_rgb24a8")
        bit_order = []
        expected_bits = ENC1_BITS.get(enc1)
        if expected_bits:
            bit_order.append(expected_bits)
        if enc1 == 6:
            bit_order.append(32)
        if enc1 == 7:
            bit_order.append(24)
        bit_order.extend([8, 16, 24, 32])
        seen = set()
        for bits in bit_order:
            if bits in seen:
                continue
            seen.add(bits)
            stride = width * (bits // 8)
            if stride * height == raw_len:
                return (bits, stride, 0, "header")
        return None

    if raw_len % height:
        return None
    stride = raw_len // height
    rgb24_stride = width_bytes(width, 24)
    alpha8_stride = align_to(width, 4)
    if enc1 in (6, 7, 9) and stride == rgb24_stride + alpha8_stride:
        return (24, rgb24_stride, alpha8_stride, "header_rgb24a8")

    exact_strides = {
        8: {width_bytes(width, 8), width},
        16: {width_bytes(width, 16), width * 2},
        24: {width_bytes(width, 24)},
        32: {width * 4, width_bytes(width, 32)},
    }
    scored = []
    for bits, strides in exact_strides.items():
        if stride in strides:
            score = 1000
            if bits == ENC1_BITS.get(enc1):
                score += 100
            if enc1 == 6 and bits == 32:
                score += 80
            if bits == 24:
                score += 20
            scored.append((score, bits, stride, 0, "header"))
    if scored:
        _score, bits, stride, alpha_stride, method = max(scored)
        return (bits, stride, alpha_stride, method)

    expected_bits = ENC1_BITS.get(enc1)
    bit_order = []
    if expected_bits:
        bit_order.append(expected_bits)
    if enc1 == 6:
        bit_order.append(32)
    if enc1 == 7:
        bit_order.append(24)
    bit_order.extend([8, 16, 24, 32])
    seen = set()
    for bits in bit_order:
        if bits in seen:
            continue
        seen.add(bits)
        bpp = bits // 8
        pad = stride - width * bpp
        if 0 <= pad <= min(32, max(4, width)):
            return (bits, stride, 0, "header_loose")

    if kind == "zlib":
        for color_stride in (width * 2, width_bytes(width, 16), align_to(width * 2, 16)):
            for alpha_stride in ((width + 1) // 2, width // 2, width_bytes(width, 4), align_to((width + 1) // 2, 4), align_to((width + 1) // 2, 16)):
                if (color_stride + alpha_stride) * height == raw_len:
                    return (16, color_stride, alpha_stride, "header_alpha4")
    return None


def _byte_at(raw, pos):
    if 0 <= pos < len(raw):
        return raw[pos]
    return 0


def _sample_rgb(raw, width, height, bits, pitch, x, y):
    if bits == 8:
        value = _byte_at(raw, y * pitch + x)
        r, g, b, _a = default_palette()[value]
        return (r, g, b)
    if bits == 16:
        pos = y * pitch + x * 2
        value = _byte_at(raw, pos) | (_byte_at(raw, pos + 1) << 8)
        r, g, b, _a = rgba_from_rgb565(value, True)
        return (r, g, b)
    if bits == 24:
        pos = y * pitch + x * 3
        b, g, r = _byte_at(raw, pos), _byte_at(raw, pos + 1), _byte_at(raw, pos + 2)
        return (r, g, b)
    if bits == 32:
        pos = y * pitch + x * 4
        b, g, r = _byte_at(raw, pos), _byte_at(raw, pos + 1), _byte_at(raw, pos + 2)
        return (r, g, b)
    return (0, 0, 0)


def _layout_score(raw, width, height, bits, pitch):
    if width <= 0 or height <= 1 or pitch <= 0 or pitch * height > len(raw):
        return -1000000000
    if pitch < width * (bits // 8):
        return -1000000000
    step_x = max(1, width // 96)
    step_y = max(1, height // 64)
    horiz_sum = vert_sum = 0
    horiz_n = vert_n = 0
    nonzero = samples = 0
    for y in range(0, height, step_y):
        prev = None
        for x in range(0, width, step_x):
            rgb = _sample_rgb(raw, width, height, bits, pitch, x, y)
            if rgb != (0, 0, 0):
                nonzero += 1
            samples += 1
            if prev is not None:
                horiz_sum += sum(abs(rgb[i] - prev[i]) for i in range(3))
                horiz_n += 1
            prev = rgb
    for y in range(0, height - step_y, step_y):
        for x in range(0, width, step_x):
            a = _sample_rgb(raw, width, height, bits, pitch, x, y)
            b = _sample_rgb(raw, width, height, bits, pitch, x, y + step_y)
            vert_sum += sum(abs(a[i] - b[i]) for i in range(3))
            vert_n += 1
    smooth = horiz_sum / max(1, horiz_n) * 0.7 + vert_sum / max(1, vert_n) * 1.3
    fill = nonzero / max(1, samples)
    fill_penalty = abs(fill - 0.18) * 60
    aspect = width / max(1, height)
    aspect_penalty = 0 if 0.05 <= aspect <= 20 else 200
    compact_bonus = 45 if width <= 512 else 0
    true_color_bonus = 20 if bits in (16, 24, 32) else 0
    return -smooth - fill_penalty - aspect_penalty + compact_bonus + true_color_bonus


@lru_cache(maxsize=256)
def rgb24a8_shape_candidates(raw_len):
    candidates = []
    max_width = min(4096, raw_len // 4 if raw_len > 0 else 0)
    for width in range(1, max_width + 1):
        color_pitch = width_bytes(width, 24)
        alpha_pitch = align_to(width, 4)
        row_len = color_pitch + alpha_pitch
        if row_len <= 0 or raw_len % row_len:
            continue
        height = raw_len // row_len
        if 1 <= height <= 4096:
            candidates.append((width, height, 24, color_pitch, alpha_pitch, "visual_rgb24a8"))
    return tuple(candidates)


def _candidate_identity(candidate):
    """Stable identity for visual render-format candidates."""
    return tuple(candidate[:6])


def _append_unique_candidate(candidates, seen, candidate):
    key = _candidate_identity(candidate)
    if key in seen:
        return False
    candidates.append(candidate)
    seen.add(key)
    return True


@lru_cache(maxsize=256)
def packed_shape_candidates(raw_len, bits):
    bpp = bits // 8
    if bpp <= 0 or raw_len <= 0 or raw_len % bpp:
        return ()
    pixels = raw_len // bpp
    candidates = []
    for height in divisors(pixels):
        width = pixels // height
        if 1 <= width <= 4096 and 1 <= height <= 4096:
            candidates.append((width, height, bits, width * bpp, 0, f"visual_{bits}b"))
    return tuple(candidates)


def choose_visual_render_format(raw, kind, header_info):
    if not header_info or kind != "zlib":
        return None
    height = header_info["height"]
    candidates = []
    width = header_info["width"]
    if 1 <= height <= 4096 and len(raw) % height == 0:
        pitch = len(raw) // height
        if 1 <= width <= 4096 and header_info.get("enc1") in (6, 7, 9):
            color_pitch = width_bytes(width, 24)
            alpha_pitch = align_to(width, 4)
            if (color_pitch + alpha_pitch) * height == len(raw):
                candidates.append((width, height, 24, color_pitch, alpha_pitch, "header_rgb24a8"))
        for bits in (8, 16, 24, 32):
            bpp = bits // 8
            inferred_width = pitch // bpp
            if not (1 <= inferred_width <= 4096):
                continue
            if pitch < inferred_width * bpp:
                continue
            candidates.append((inferred_width, height, bits, pitch, 0, "visual"))
        if header_info.get("enc2") == 9 and 1 <= width <= 4096:
            color_pitch = pitch // 2
            alpha_pitch = max(1, width // 2)
            if color_pitch >= width * 2 and color_pitch * height + alpha_pitch * height <= len(raw):
                candidates.append((width, height, 16, pitch, alpha_pitch, "wzl_alpha4"))

    if header_info.get("enc1") in (6, 7, 9):
        existing = {_candidate_identity(candidate) for candidate in candidates}
        for candidate in rgb24a8_shape_candidates(len(raw)):
            _append_unique_candidate(candidates, existing, candidate)

    expected_bits = ENC1_BITS.get(header_info.get("enc1"))
    packed_bits = []
    if expected_bits in (8, 16, 24, 32):
        packed_bits.append(expected_bits)
    if header_info.get("enc1") == 6:
        packed_bits.append(24)
    existing = {_candidate_identity(candidate) for candidate in candidates}
    for bits in packed_bits:
        for candidate in packed_shape_candidates(len(raw), bits):
            _append_unique_candidate(candidates, existing, candidate)

    if not candidates:
        return None
    expected = choose_render_format(len(raw), kind, header_info)
    scored = []
    for candidate in candidates:
        width, height, bits, pitch, alpha_stride, method = candidate
        score = _layout_score(raw, width, height, bits, pitch)
        aspect = width / max(1, height)
        if method in {"header_rgb24a8", "visual_rgb24a8"}:
            score += 20
            if 0.5 <= aspect <= 2:
                score += 16
            elif 0.25 <= aspect <= 4:
                score += 6
            else:
                score -= 24
            if 16 <= width <= 96 and 16 <= height <= 96:
                score += 12
        if method.startswith("visual_") and bits in (8, 16):
            if 0.5 <= aspect <= 2:
                score += 10
            elif aspect < 0.25 or aspect > 4:
                score -= 20
            if 16 <= width <= 96 and 16 <= height <= 96:
                score += 8
        if bits == 24:
            score += 40
        if bits == 32:
            score += 40 if header_info.get("enc1") in (7, 9) else -15
        if expected and bits == expected[0] and pitch == expected[1]:
            score += 8
        if bits == ENC1_BITS.get(header_info.get("enc1")) and width == header_info.get("width"):
            score += 5
        scored.append((score, candidate))
    _score, best = max(scored, key=lambda item: item[0])
    width, height, bits, pitch, alpha_stride, method = best
    if method == "wzl_alpha4":
        return (width, height, bits, pitch, alpha_stride, "wzl_alpha4")
    if method in {"header_rgb24a8", "visual_rgb24a8"}:
        return (width, height, bits, pitch, alpha_stride, method)
    if bits == 24:
        return (width, height, bits, pitch, alpha_stride, "pitch24")
    if bits == 32:
        return (width, height, bits, pitch, alpha_stride, "pitch32")
    return (width, height, bits, pitch, alpha_stride, method)


def fallback_render_format(raw):
    best = best_rgb565_dimensions(raw)
    if not best:
        return None
    score, width, height, stride = best
    return (16, stride, 0, "fallback", score, width, height)

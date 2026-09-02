from __future__ import annotations

import hashlib
import os
import pathlib
import struct
import sys
import tempfile
import zlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from toolbox_native_asset_worker import NativeAssetWorkerBroker  # noqa: E402
import toolbox_native_core as native_core  # noqa: E402
from embedded_npc_visual.core.npc_preview.recovered_asset_reader import (  # noqa: E402
    aes_ctr_crypt,
    crypt_buffer,
    decode_gee_image_header,
    derive_gee_pak3_key_block,
)
from embedded_npc_visual.core.npc_preview.pak_asset_browser import image_for_record  # noqa: E402
from embedded_npc_visual.core.npc_visual_v2.resources.asset_providers import (  # noqa: E402
    NativeAssetReadGate,
    WzlImageProvider,
    load_records_for_pak,
)
from tools import probe_native_core_protocol as protocol_probe  # noqa: E402


def _fixture(path: pathlib.Path, password: str) -> None:
    header = bytearray(256)
    struct.pack_into("<I", header, 46, 2)
    header[50] = 1
    struct.pack_into("<I", header, 54, 262)
    index = struct.pack("<II", 270, 302)
    image_header = bytearray(16)
    image_header[0] = 7
    struct.pack_into("<hh", image_header, 4, 2, 2)
    pixels = bytes(
        [
            0, 0, 255, 255, 0, 255, 0, 255,
            255, 0, 0, 255, 255, 255, 255, 255,
        ]
    )
    raw = b"D3DM2" + crypt_buffer(bytes(header), b"442517066", False) + b"\x00" + crypt_buffer(index, password.encode("ascii"), False)
    large_header = bytearray(16)
    large_header[0] = 7
    struct.pack_into("<hh", large_header, 4, 520, 520)
    large_pixels = bytes([1, 2, 3, 255]) * (520 * 520)
    raw += crypt_buffer(bytes(image_header), password.encode("ascii"), False) + pixels
    raw += crypt_buffer(bytes(large_header), password.encode("ascii"), False) + large_pixels
    path.write_bytes(raw)


def _wil_fixture(data_path: pathlib.Path, index_path: pathlib.Path) -> None:
    image_header = bytearray(16)
    image_header[0] = 7
    struct.pack_into("<hh", image_header, 4, 2, 2)
    pixels = bytes(
        [
            0, 0, 255, 255, 0, 255, 0, 255,
            255, 0, 0, 255, 255, 255, 255, 255,
        ]
    )
    data_path.write_bytes(bytes(64) + bytes(image_header) + pixels)
    index = bytearray(52)
    struct.pack_into("<I", index, 44, 1)
    struct.pack_into("<I", index, 48, 64)
    index_path.write_bytes(index)


def _wzl_alpha4_fixture(data_path: pathlib.Path, index_path: pathlib.Path) -> None:
    image_header = bytearray(16)
    image_header[0] = 5
    image_header[3] = 9
    struct.pack_into("<hh", image_header, 4, 2, 2)
    pixels = bytes([0x00, 0xF8, 0xE0, 0x07, 0x1F, 0x00]) + bytes(10)
    data_path.write_bytes(bytes(64) + bytes(image_header) + pixels)
    index = bytearray(52)
    struct.pack_into("<I", index, 44, 1)
    struct.pack_into("<I", index, 48, 64)
    index_path.write_bytes(index)


def _wzl_sparse_fixture(data_path: pathlib.Path, index_path: pathlib.Path) -> None:
    image_header = bytearray(16)
    image_header[0] = 7
    struct.pack_into("<hh", image_header, 4, 2, 2)
    first_pixels = bytes([1, 2, 3, 255]) * 4
    second_pixels = bytes([4, 5, 6, 255]) * 4
    second_offset = 64 + len(image_header) + len(first_pixels)
    data_path.write_bytes(
        bytes(64)
        + bytes(image_header)
        + first_pixels
        + bytes(image_header)
        + second_pixels
    )
    index = bytearray(64)
    struct.pack_into("<I", index, 44, 4)
    struct.pack_into("<IIII", index, 48, 48, 64, 0xFFFFFFF0, second_offset)
    index_path.write_bytes(index)


def _empty_wzl_fixture(data_path: pathlib.Path, index_path: pathlib.Path) -> None:
    data_path.write_bytes(bytes(64))
    index_path.write_bytes(bytes(48))


def _geem2lp_fixture(path: pathlib.Path, password: str) -> None:
    header = bytearray(256)
    struct.pack_into("<I", header, 46, 1)
    header[50] = 2
    struct.pack_into("<I", header, 54, 266)
    index = struct.pack("<I", 270)
    image_header = bytearray(16)
    image_header[0] = 7
    struct.pack_into("<hh", image_header, 4, 2, 2)
    pixels = bytes([9, 8, 7, 255]) * 4
    raw = b"\x05GEEM2" + bytes(4)
    raw += crypt_buffer(bytes(header), password.encode("ascii"), False, iv_fill=96)
    raw += crypt_buffer(index, password.encode("ascii"), False, iv_fill=96)
    raw += crypt_buffer(bytes(image_header), password.encode("ascii"), False, iv_fill=96)
    raw += pixels
    path.write_bytes(raw)


def _compressed_palette_fixture(path: pathlib.Path, password: str) -> None:
    header = bytearray(256)
    struct.pack_into("<I", header, 46, 1)
    header[50] = 1
    struct.pack_into("<I", header, 54, 262)
    image_offset = 266
    index = struct.pack("<I", image_offset)
    pixels = bytes([0, 1, 0, 0, 2, 3, 0, 0])
    compressed = zlib.compress(pixels, 9)
    image_header = bytearray(16)
    image_header[0] = 3
    struct.pack_into("<hh", image_header, 4, 2, 2)
    struct.pack_into("<i", image_header, 12, len(compressed))
    raw = b"D3DM2" + crypt_buffer(bytes(header), b"442517066", False) + b"\x00"
    raw += crypt_buffer(index, password.encode("ascii"), False)
    raw += crypt_buffer(bytes(image_header), password.encode("ascii"), False)
    raw += compressed
    path.write_bytes(raw)


def _geepak3_fixture(path: pathlib.Path, password: str) -> None:
    key_block, key_words = derive_gee_pak3_key_block(password.encode("ascii"))
    header = bytearray(256)
    struct.pack_into("<I", header, 46, 1)
    header[50] = 2
    struct.pack_into("<I", header, 54, 266)
    image_offset = 270
    encoded_offset = image_offset ^ key_words[0] ^ 0xFFFFFFFF
    image_header = bytearray(16)
    image_header[0] = 7
    struct.pack_into("<hh", image_header, 4, 2, 2)
    pixels = bytes([11, 22, 33, 255]) * 4
    raw = b"\x07GEEPAK3" + bytes(2)
    raw += aes_ctr_crypt(key_block[:16], bytes(header))
    raw += struct.pack("<I", encoded_offset & 0xFFFFFFFF)
    raw += decode_gee_image_header(bytes(image_header), key_words, 0)
    raw += pixels
    path.write_bytes(raw)


def main() -> int:
    executable = ROOT / "build" / "native_core" / "xiami_native_core.exe"
    old_path = os.environ.get("XIAMI_NATIVE_CORE_PATH")
    os.environ["XIAMI_NATIVE_CORE_PATH"] = str(executable)
    password = "gameofmir"
    try:
        with tempfile.TemporaryDirectory(prefix="xiami-asset-decode-") as temporary:
            data_dir = pathlib.Path(temporary) / "中文素材"
            data_dir.mkdir()
            backend = protocol_probe._load_backend(data_dir)
            backend.USERS.clear()
            backend_session, client_session = protocol_probe._identity(
                backend, "asset_decode_probe", "asset-decode-device"
            )
            asset = data_dir / "probe.pak"
            _fixture(asset, password)
            wzl = data_dir / "probe.wzl"
            wzx = data_dir / "probe.wzx"
            _wil_fixture(wzl, wzx)
            alpha_wzl = data_dir / "alpha.wzl"
            alpha_wzx = data_dir / "alpha.wzx"
            _wzl_alpha4_fixture(alpha_wzl, alpha_wzx)
            sparse_wzl = data_dir / "sparse.wzl"
            sparse_wzx = data_dir / "sparse.wzx"
            _wzl_sparse_fixture(sparse_wzl, sparse_wzx)
            empty_wzl = data_dir / "empty.wzl"
            empty_wzx = data_dir / "empty.wzx"
            _empty_wzl_fixture(empty_wzl, empty_wzx)
            geem2lp = data_dir / "geem2lp.pak"
            geem2lp_password = "QQ4283164"
            _geem2lp_fixture(geem2lp, geem2lp_password)
            compressed_palette = data_dir / "compressed-palette.pak"
            _compressed_palette_fixture(compressed_palette, password)
            geepak3 = data_dir / "geepak3.pak"
            geepak3_password = "V8M2"
            _geepak3_fixture(geepak3, geepak3_password)
            calls = {"issue": [], "consume": []}
            with NativeAssetWorkerBroker(str(executable), timeout=5.0) as broker:
                with protocol_probe._protocol_bridge(
                    backend, backend_session, client_session["device_id"], calls
                ):
                    result = native_core.authorize_npc_asset_read(
                        client_session, asset, "npc-resource", -1, password,
                        allow_local_http=True, asset_broker=broker,
                    )
                records = broker.list_records(result["asset_handle"], result["worker_generation"])
                assert b"count=2" in records and b"record=0,270" in records and b"record=1,302" in records
                width, height, stride, origin_x, origin_y, pixels = broker.decode_image(
                    result["asset_handle"], result["worker_generation"], 0
                )
                assert (width, height, stride, origin_x, origin_y) == (2, 2, 8, 0, 0)
                assert pixels == bytes(
                    [
                        255, 0, 0, 255, 255, 255, 255, 255,
                        0, 0, 255, 255, 0, 255, 0, 255,
                    ]
                )
                width, height, stride, origin_x, origin_y, pixels = broker.decode_image(
                    result["asset_handle"], result["worker_generation"], 1
                )
                assert (width, height, stride, origin_x, origin_y) == (520, 520, 2080, 0, 0)
                assert len(pixels) == 520 * 520 * 4
                assert pixels[:16] == bytes([1, 2, 3, 255]) * 4
                assert pixels[-16:] == bytes([1, 2, 3, 255]) * 4
                gate = NativeAssetReadGate(lambda: client_session, asset_broker=broker)
                automatic_prefetch_calls = []
                original_prefetch_images = broker.prefetch_images
                broker.prefetch_images = lambda *args, **kwargs: (
                    automatic_prefetch_calls.append((args, kwargs))
                    or original_prefetch_images(*args, **kwargs)
                )
                with protocol_probe._protocol_bridge(
                    backend, backend_session, client_session["device_id"], calls
                ):
                    records_from_provider = load_records_for_pak(
                        asset, password, gate=gate, purpose="npc-resource"
                    )
                broker.prefetch_images = original_prefetch_images
                assert not automatic_prefetch_calls
                provider_image = image_for_record(records_from_provider[0])
                assert provider_image.size == (2, 2)
                assert provider_image.tobytes() == bytes(
                    [
                        0, 0, 255, 255, 255, 255, 255, 255,
                        255, 0, 0, 255, 0, 255, 0, 255,
                    ]
                )
                wil_gate = NativeAssetReadGate(lambda: client_session, asset_broker=broker)
                wil_provider = WzlImageProvider(data_dir, asset_gate=wil_gate)
                with protocol_probe._protocol_bridge(
                    backend, backend_session, client_session["device_id"], calls
                ):
                    wil_asset = wil_provider.read_image_asset_file(wzl, 0)
                assert wil_asset.image.size == (2, 2)
                assert wil_asset.image.tobytes() == provider_image.tobytes()
                sparse_gate = NativeAssetReadGate(lambda: client_session, asset_broker=broker)
                with protocol_probe._protocol_bridge(
                    backend, backend_session, client_session["device_id"], calls
                ):
                    sparse_records = load_records_for_pak(
                        sparse_wzl, "", gate=sparse_gate, purpose="npc-resource"
                    )
                assert len(sparse_records) == 4
                assert [record.kind for record in sparse_records] == [
                    "empty", "recovered_pak", "empty", "recovered_pak"
                ]
                assert sparse_records[1]._native_asset_index_handle
                assert image_for_record(sparse_records[1]).tobytes() == bytes([3, 2, 1, 255]) * 4
                assert image_for_record(sparse_records[3]).tobytes() == bytes([6, 5, 4, 255]) * 4
                empty_gate = NativeAssetReadGate(lambda: client_session, asset_broker=broker)
                with protocol_probe._protocol_bridge(
                    backend, backend_session, client_session["device_id"], calls
                ):
                    empty_records = load_records_for_pak(
                        empty_wzl, "", gate=empty_gate, purpose="npc-resource"
                    )
                assert empty_records == []
                alpha_gate = NativeAssetReadGate(lambda: client_session, asset_broker=broker)
                alpha_provider = WzlImageProvider(data_dir, asset_gate=alpha_gate)
                with protocol_probe._protocol_bridge(
                    backend, backend_session, client_session["device_id"], calls
                ):
                    alpha_asset = alpha_provider.read_image_asset_file(alpha_wzl, 0)
                assert alpha_asset.image.size == (2, 2)
                assert alpha_asset.image.tobytes() == bytes([
                    0, 255, 0, 240, 0, 0, 255, 16,
                    255, 0, 0, 0, 0, 255, 0, 0,
                ]), alpha_asset.image.tobytes().hex()
                with protocol_probe._protocol_bridge(
                    backend, backend_session, client_session["device_id"], calls
                ):
                    geem2_result = native_core.authorize_npc_asset_read(
                        client_session, geem2lp, "npc-resource", -1, geem2lp_password,
                        allow_local_http=True, asset_broker=broker,
                    )
                geem2_records = broker.list_records(
                    geem2_result["asset_handle"], geem2_result["worker_generation"]
                )
                assert b"count=1" in geem2_records and b"record=0,270" in geem2_records
                geem2_image = broker.decode_image(
                    geem2_result["asset_handle"], geem2_result["worker_generation"], 0
                )
                assert geem2_image[:5] == (2, 2, 8, 0, 0)
                assert geem2_image[5] == bytes([9, 8, 7, 255]) * 4
                with protocol_probe._protocol_bridge(
                    backend, backend_session, client_session["device_id"], calls
                ):
                    compressed_result = native_core.authorize_npc_asset_read(
                        client_session, compressed_palette, "npc-resource", -1, password,
                        allow_local_http=True, asset_broker=broker,
                    )
                compressed_image = broker.decode_image(
                    compressed_result["asset_handle"], compressed_result["worker_generation"], 0
                )
                assert compressed_image[:5] == (2, 2, 8, 0, 0)
                assert compressed_image[5] == bytes([
                    0, 128, 0, 255, 0, 128, 128, 255,
                    0, 0, 0, 0, 0, 0, 128, 255,
                ]), compressed_image[5].hex()
                with protocol_probe._protocol_bridge(
                    backend, backend_session, client_session["device_id"], calls
                ):
                    geepak3_result = native_core.authorize_npc_asset_read(
                        client_session, geepak3, "npc-resource", -1, geepak3_password,
                        allow_local_http=True, asset_broker=broker,
                    )
                geepak3_records = broker.list_records(
                    geepak3_result["asset_handle"], geepak3_result["worker_generation"]
                )
                assert b"count=1" in geepak3_records and b"record=0,270" in geepak3_records
                assert broker.prefetch_images(
                    geepak3_result["asset_handle"], geepak3_result["worker_generation"], [0]
                ) == 1
                geepak3_image = broker.decode_image(
                    geepak3_result["asset_handle"], geepak3_result["worker_generation"], 0
                )
                assert geepak3_image[:5] == (2, 2, 8, 0, 0)
                assert geepak3_image[5] == bytes([11, 22, 33, 255]) * 4
                broker.close_asset(result["asset_handle"], result["worker_generation"])
            assert len(calls["issue"]) >= 2 and len(calls["consume"]) >= 2
        print("native asset decode probe: PASS")
        return 0
    finally:
        if old_path is None:
            os.environ.pop("XIAMI_NATIVE_CORE_PATH", None)
        else:
            os.environ["XIAMI_NATIVE_CORE_PATH"] = old_path


if __name__ == "__main__":
    raise SystemExit(main())

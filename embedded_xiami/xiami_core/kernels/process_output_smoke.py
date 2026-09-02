from __future__ import annotations

from xiami_core.kernels.process_output import _decode, _normalize_qr_hint
from xiami_core.path_alias import cleanup_aliases, ensure_ascii_workspace_alias, remove_empty_alias_base_dirs
from xiami_core.storage.paths import PROJECT_ROOT


def main() -> int:
    try:
        expected = PROJECT_ROOT / "runtime" / "xiami_v1" / "kernels" / "NapCat" / "napcat" / "cache" / "qrcode.png"
        alias_root = ensure_ascii_workspace_alias()
        actual = _normalize_qr_hint(str(alias_root / "runtime" / "xiami_v1" / "kernels" / "NapCat" / "napcat" / "cache" / "qrcode.png"))
        if actual != str(expected):
            raise RuntimeError(f"bad qr path normalization: {actual}")
        decoded = _decode("06-29 \x1b[32minfo\x1b[39m 虾米 | 接收 <- 私聊 [好友(10001)] 你好".encode("utf-8"))
        if "\x1b" in decoded or "你好" not in decoded:
            raise RuntimeError(f"bad process output decode: {decoded!r}")
        mojibake_bytes = "二维码解码URL".encode("utf-8").decode("gbk").encode("gbk")
        repaired = _decode(mojibake_bytes)
        if "二维码解码URL" not in repaired:
            raise RuntimeError(f"bad mojibake repair: {repaired!r}")
        print("process output smoke ok")
        return 0
    finally:
        cleanup_aliases()
        remove_empty_alias_base_dirs()


if __name__ == "__main__":
    raise SystemExit(main())

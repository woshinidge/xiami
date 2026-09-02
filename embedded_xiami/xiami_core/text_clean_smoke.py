from __future__ import annotations

from xiami_core.text_clean import clean_text


def main() -> int:
    if clean_text("浜岀淮鐮佽В鐮乁RL") != "二维码解码URL":
        raise RuntimeError("qr mojibake not repaired")
    cleaned = clean_text("\x1b[32minfo\x1b[39m 铏剧背 | 鎺ユ敹 <- 缇よ亰")
    if cleaned != "info 虾米 | 接收 <- 群聊":
        raise RuntimeError(f"ansi mojibake not cleaned: {cleaned}")
    broken_ansi = clean_text("[[32minfo[39m] 钏剧背 | 紐ュ敦 <- 绐你京 (3685280759)")
    if broken_ansi != "info 虾米 | 接收 <- 私聊 (3685280759)":
        raise RuntimeError(f"broken ansi mojibake not cleaned: {broken_ansi}")
    mixed_private = clean_text("铏剧背 | 鎺ユ敹 <- 绐你京 (3685280759)")
    if mixed_private != "虾米 | 接收 <- 私聊 (3685280759)":
        raise RuntimeError(f"mixed private mojibake not cleaned: {mixed_private}")
    qr_saved = clean_text("浜岀淮鐮佸凡淇濆瓨鍒� X:\\runtime\\xiami_v1\\qrcode.png")
    if "二维码已保存到" not in qr_saved:
        raise RuntimeError(f"qr saved mojibake not cleaned: {qr_saved}")
    print("text clean smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["XIAMI_HOME"] = str(Path(tmp) / "runtime")
        from xiami_core.runtime_diagnostic import (
            apply_suggested_kernel_config,
            build_runtime_diagnostic,
            format_runtime_diagnostic,
        )
        from xiami_core.storage.config import AppConfig, KernelConfig, load_config, save_config
        from xiami_core.storage.paths import KERNEL_HOME

        save_config(
            AppConfig(
                kernel=KernelConfig(kind="Mock", http_url="http://127.0.0.1:1"),
                probe_private_target="10001",
                probe_group_target="20001",
            )
        )
        kernel_root = KERNEL_HOME / "NapCat.Shell.Windows.Node"
        kernel_root.mkdir(parents=True)
        (kernel_root / "napcat.bat").write_text("node.exe ./index.js\r\n", encoding="utf-8")
        (kernel_root / "node.exe").write_text("", encoding="utf-8")
        (kernel_root / "index.js").write_text("", encoding="utf-8")
        qr = kernel_root / "napcat" / "cache" / "qrcode.png"
        qr.parent.mkdir(parents=True)
        qr.write_bytes(b"fake")
        onebot = kernel_root / "napcat" / "config" / "onebot11_10000.json"
        onebot.parent.mkdir(parents=True)
        onebot.write_text(
            '{"network":{"httpServers":[{"enable":true,"port":3000}],"httpClients":[{"enable":true,"url":"http://127.0.0.1:18081/onebot/event"}]}}',
            encoding="utf-8",
        )

        diagnostic = build_runtime_diagnostic()
        if not diagnostic.suggested_kernel or diagnostic.suggested_kernel.kind != "NapCat":
            raise RuntimeError(f"NapCat suggestion missing: {diagnostic}")
        if not diagnostic.qr_candidates or diagnostic.qr_candidates[-1] != qr.resolve():
            raise RuntimeError(f"QR candidate missing: {diagnostic.qr_candidates}")
        if diagnostic.napcat_config_ok is not True:
            raise RuntimeError(f"NapCat onebot config not detected: {diagnostic.napcat_config_detail}")
        text = "\n".join(format_runtime_diagnostic(diagnostic))
        for needle in ("当前内核配置：Mock", "建议切换真实内核：NapCat", "二维码素材："):
            if needle not in text:
                raise RuntimeError(f"formatted runtime diagnostic missing {needle}: {text}")
        result = apply_suggested_kernel_config()
        if not result.ok:
            raise RuntimeError(f"suggested kernel apply failed: {result.detail}")
        saved = load_config()
        if saved.kernel.kind != "NapCat" or not saved.kernel.executable.endswith("napcat.bat"):
            raise RuntimeError(f"suggested kernel not saved: {saved}")
        if saved.kernel.http_url != "http://127.0.0.1:1":
            raise RuntimeError(f"OneBot HTTP setting was not preserved: {saved.kernel.http_url}")
        if saved.probe_private_target != "10001" or saved.probe_group_target != "20001":
            raise RuntimeError(f"probe targets were not preserved: {saved}")

    print("runtime diagnostic smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

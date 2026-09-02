from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from xiami_core.runtime_diagnostic import _find_qr_candidates
from xiami_core.storage.config import KernelConfig


def main() -> int:
    with TemporaryDirectory() as temp:
        root = Path(temp)
        qr = root / "napcat" / "cache" / "qrcode.png"
        qr.parent.mkdir(parents=True)
        qr.write_bytes(b"fake")
        original_stat = Path.stat

        def flaky_stat(self: Path, *args, **kwargs):  # type: ignore[no-untyped-def]
            if self == qr:
                raise FileNotFoundError(str(self))
            return original_stat(self, *args, **kwargs)

        try:
            Path.stat = flaky_stat  # type: ignore[method-assign]
            result = _find_qr_candidates(KernelConfig(kind="NapCat", executable=str(root / "napcat.bat"), working_dir=str(root)), None)
        finally:
            Path.stat = original_stat  # type: ignore[method-assign]
        if result:
            raise RuntimeError(f"vanished qr candidate should be skipped: {result}")
    print("runtime qr race smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

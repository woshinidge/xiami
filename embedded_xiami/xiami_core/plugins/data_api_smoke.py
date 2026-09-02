from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from xiami_core.models import SendResult
from xiami_core.plugins.context import PluginContext


def main() -> int:
    def send(target: str, text: str, message_type: str) -> SendResult:
        return SendResult(ok=True)

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        ctx = PluginContext(send_fn=send, plugin_id="demo", data_root=root / "data")
        ctx.write_text("logs/run.txt", "hello")
        ctx.append_text("logs/run.txt", "\nworld")
        if ctx.read_text("logs/run.txt") != "hello\nworld":
            raise RuntimeError("plugin text data api failed")

        ctx.write_json("state/cache.json", {"count": 2, "items": ["a", "b"]})
        if ctx.read_json("state/cache.json") != {"count": 2, "items": ["a", "b"]}:
            raise RuntimeError("plugin json data api failed")
        if ctx.read_json("missing.json", {"default": True}) != {"default": True}:
            raise RuntimeError("plugin json default failed")

        other = ctx.for_plugin("other")
        other.write_text("logs/run.txt", "other")
        if ctx.read_text("logs/run.txt") == other.read_text("logs/run.txt"):
            raise RuntimeError("plugin data isolation failed")

        for unsafe in ("../escape.txt", "..\\escape.txt"):
            try:
                ctx.write_text(unsafe, "bad")
            except ValueError:
                continue
            raise RuntimeError(f"unsafe plugin data path accepted: {unsafe}")

        try:
            ctx.write_text(str((root / "absolute.txt").resolve()), "bad")
        except ValueError:
            pass
        else:
            raise RuntimeError("absolute plugin data path accepted")

    print("plugin data api smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

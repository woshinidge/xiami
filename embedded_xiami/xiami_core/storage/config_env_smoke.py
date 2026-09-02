from __future__ import annotations

from xiami_core.storage.paths import CONFIG_FILE, XIAMI_HOME


def main() -> int:
    if "runtime" not in str(CONFIG_FILE):
        raise RuntimeError(f"unexpected config path: {CONFIG_FILE}")
    if XIAMI_HOME.name != "xiami_v1":
        raise RuntimeError(f"unexpected xiami home: {XIAMI_HOME}")
    print("config env smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import os
from tempfile import TemporaryDirectory


_TEMP_HOME: TemporaryDirectory[str] | None = None


def use_temp_xiami_home(*, respect_existing: bool = False) -> str:
    global _TEMP_HOME
    if respect_existing and "XIAMI_HOME" in os.environ:
        return os.environ["XIAMI_HOME"]
    if _TEMP_HOME is None:
        _TEMP_HOME = TemporaryDirectory()
    os.environ["XIAMI_HOME"] = _TEMP_HOME.name
    return _TEMP_HOME.name

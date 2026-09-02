from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from xiami_core.kernels.external import _build_command, _hidden_subprocess_kwargs


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _assert_direct_node(root: Path, script: str, expected_script: str = "./index.js") -> None:
    napcat_bat = root / "napcat.bat"
    _write(napcat_bat, script)
    _write(root / "node.exe", "")
    command = _build_command(napcat_bat, [], root)
    if Path(command[0]).name.lower() != "node.exe" or command[1] != expected_script:
        raise RuntimeError(f"NapCat batch was not bypassed: {command}")


def main() -> int:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        _assert_direct_node(root, "node.exe ./index.js\n")
        _assert_direct_node(root, "call node.exe ./index.js\n")
        _assert_direct_node(root, 'start "" node.exe ./index.js\n')
        _assert_direct_node(root, 'start "" /b node.exe ./index.js\n')
        _assert_direct_node(root, 'start /b "" node.exe ./index.js\n')
        _assert_direct_node(root, '"%~dp0node.exe" ./index.js %*\n')
        _assert_direct_node(root, '@echo off\ncd /d "%~dp0"\nnode.exe ./index.js\n')
        _assert_direct_node(root, 'setlocal\npushd "%~dp0"\nnode.exe ./index.js\npopd\nendlocal\n')

        boot = root / "NapCatWinBootMain.exe"
        _write(boot, "")
        quick = root / "napcat.quick.bat"
        _write(quick, r".\NapCatWinBootMain.exe 10086 %*" + "\n")
        command = _build_command(quick, ["--probe"], root)
        if Path(command[0]).name.lower() != "napcatwinbootmain.exe" or command[1:] != ["10086", "--probe"]:
            raise RuntimeError(f"NapCat quick batch was not bypassed: {command}")

    hidden_kwargs = _hidden_subprocess_kwargs()
    if sys.platform == "win32":
        if "creationflags" not in hidden_kwargs or "startupinfo" not in hidden_kwargs:
            raise RuntimeError(f"hidden process kwargs missing: {hidden_kwargs}")
    print("hidden launch smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

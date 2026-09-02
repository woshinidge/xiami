from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from unittest import mock

from xiami_core.kernels import packages
from xiami_core.kernels.packages import classify_kernel_path, config_from_entry, find_kernel_entry


def main() -> int:
    with TemporaryDirectory() as temp:
        root = Path(temp)
        lagrange = root / "Lagrange.OneBot.dll"
        lagrange.write_text("", encoding="utf-8")
        config = config_from_entry("Lagrange", lagrange)
        if config.executable != "dotnet" or config.arguments != [str(lagrange)]:
            raise RuntimeError(f"dll config invalid: {config}")
        package = root / "kernel.zip"
        nested = root / "nested"
        nested.mkdir()
        (nested / "napcat.bat").write_text("", encoding="utf-8")
        with ZipFile(package, "w") as archive:
            archive.write(nested / "napcat.bat", "NapCat/bootmain/napcat.bat")
        extract = root / "extract"
        with ZipFile(package) as archive:
            archive.extractall(extract)
        entry = find_kernel_entry(extract)
        if not entry or entry.name != "napcat.bat":
            raise RuntimeError(f"entry not found: {entry}")
        (entry.parent / "NapCatWinBootMain.exe").write_text("", encoding="utf-8")
        config = config_from_entry("NapCat", entry)
        if not config.executable.endswith("xiami_napcat_start.bat"):
            raise RuntimeError(f"managed NapCat script not selected: {config}")
        if "pause" in Path(config.executable).read_text(encoding="utf-8").lower():
            raise RuntimeError("managed NapCat script must not pause")

        portable_zip = root / "QQ机器人必备环境.zip"
        with ZipFile(portable_zip, "w") as archive:
            archive.writestr("使用说明.txt", "fixture")
            archive.writestr("NapCat.Shell.Windows/napcat.bat", "node.exe ./index.js\r\n")
            archive.writestr("NapCat.Shell.Windows/node.exe", b"MZ")
            archive.writestr("NapCat.Shell.Windows/index.js", "")
            archive.writestr("NapCat.Shell.Windows/napcat/napcat.mjs", "")
            archive.writestr("NapCat.Shell.Windows/napcat/launcher-user.bat", "")
            archive.writestr("NapCat.Shell.Windows/napcat/NapCatWinBootMain.exe", b"MZ")
        kernel_home = root / "runtime-kernels"
        with mock.patch.object(packages, "KERNEL_HOME", kernel_home):
            portable_config = packages.import_kernel_package(portable_zip)
        expected_root = kernel_home / "NapCat.Shell.Windows"
        if Path(portable_config.executable) != expected_root / "napcat.bat":
            raise RuntimeError(f"portable NapCat entry did not match 1.3.9 layout: {portable_config}")
        if Path(portable_config.working_dir) != expected_root:
            raise RuntimeError(f"portable NapCat working directory did not match 1.3.9: {portable_config}")
        if (kernel_home / "QQ机器人必备环境").exists():
            raise RuntimeError("portable environment retained the archive-name directory layer")
        if classify_kernel_path(root / "NapCat.Shell.Windows.Node" / "ordinary.dll"):
            raise RuntimeError("ordinary files under a NapCat directory must not be kernel candidates")
        if classify_kernel_path(root / "NapCat.Shell.Windows.Node.zip") != "NapCat":
            raise RuntimeError("NapCat zip package should remain discoverable")
    print("kernel packages smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

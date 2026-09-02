from __future__ import annotations

import os
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

from xiami_core.storage.config import KernelConfig
from xiami_core.storage.paths import KERNEL_HOME, PROJECT_ROOT, ensure_runtime_dirs


@dataclass(frozen=True)
class KernelPackage:
    kind: str
    path: Path
    source: str


ENTRY_NAMES = (
    "Lagrange.OneBot.exe",
    "Lagrange.OneBot.dll",
    "Lagrange.OneBot",
    "NapCatWinBootMain.exe",
    "napcat.bat",
)


def discover_kernel_packages(extra_roots: list[Path] | None = None) -> list[KernelPackage]:
    roots = [PROJECT_ROOT / "downloads", KERNEL_HOME]
    if extra_roots:
        roots.extend(Path(root) for root in extra_roots)
    packages: list[KernelPackage] = []
    seen: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        for path in _iter_kernel_candidate_files(root):
            kind = classify_kernel_path(path)
            if not kind:
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            packages.append(KernelPackage(kind=kind, path=resolved, source=str(root)))
    return sorted(packages, key=lambda item: (item.kind, str(item.path).lower()))


def _iter_kernel_candidate_files(root: Path):
    entry_names = {name.lower() for name in ENTRY_NAMES}
    skipped_dirs = {
        ".git",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "logs",
        "cache",
        "static",
        "assets",
        "resources",
    }
    root = root.resolve()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            name
            for name in dirnames
            if name.lower() not in skipped_dirs and not name.lower().endswith((".asar.unpacked", ".dist-info"))
        ]
        current = Path(dirpath)
        for filename in filenames:
            lower = filename.lower()
            if lower in entry_names or lower.endswith(".zip"):
                yield current / filename


def import_kernel_package(path: Path) -> KernelConfig:
    ensure_runtime_dirs()
    source = path.resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    target_root = _next_target_dir(KERNEL_HOME / source.stem)
    if source.is_dir():
        shutil.copytree(source, target_root)
    else:
        target_root.mkdir(parents=True, exist_ok=False)
    if source.is_file() and source.suffix.lower() == ".zip":
        with zipfile.ZipFile(source) as archive:
            archive.extractall(target_root)
        children = list(target_root.iterdir())
        child_dirs = [child for child in children if child.is_dir()]
        if len(child_dirs) == 1:
            nested_root = child_dirs[0]
            nested_entry = find_kernel_entry(nested_root)
            if nested_entry is not None:
                flattened_root = _next_target_dir(KERNEL_HOME / nested_root.name)
                nested_root.replace(flattened_root)
                for child in children:
                    if child == nested_root or not child.is_file():
                        continue
                    child.replace(flattened_root / child.name)
                target_root.rmdir()
                target_root = flattened_root
    elif source.is_file():
        shutil.copy2(source, target_root / source.name)
    entry = find_kernel_entry(target_root)
    if not entry:
        raise RuntimeError(f"未在包内发现可启动内核：{source}")
    kind = classify_kernel_path(entry) or classify_kernel_path(source) or "NapCat"
    return config_from_entry(kind, entry)


def find_kernel_entry(root: Path) -> Path | None:
    matches: list[Path] = []
    for name in ENTRY_NAMES:
        matches.extend(root.rglob(name))
    if not matches:
        return None
    return sorted(matches, key=_entry_priority)[0]


def config_from_entry(kind: str, entry: Path) -> KernelConfig:
    args: list[str] = []
    launch_entry = _managed_entry(kind, entry)
    executable = str(launch_entry)
    if entry.suffix.lower() == ".dll":
        executable = "dotnet"
        args = [str(entry)]
    return KernelConfig(
        kind=kind,
        executable=executable,
        working_dir=str(launch_entry.parent),
        arguments=args,
    )


def classify_kernel_path(path: Path) -> str:
    name = path.name.lower()
    if name in {"lagrange.onebot.exe", "lagrange.onebot.dll", "lagrange.onebot"}:
        return "Lagrange"
    if name in {"napcatwinbootmain.exe", "napcat.bat"}:
        return "NapCat"
    if name.endswith(".zip"):
        if "lagrange" in name:
            return "Lagrange"
        if "napcat" in name:
            return "NapCat"
    return ""


def _entry_priority(path: Path) -> tuple[int, str]:
    name = path.name.lower()
    if name == "lagrange.onebot.exe":
        priority = 0
    elif name == "lagrange.onebot.dll":
        priority = 1
    elif name == "napcat.bat":
        priority = 10
    elif name == "napcatwinbootmain.exe":
        priority = 11
    else:
        priority = 50
    return priority, str(path).lower()


def _next_target_dir(base: Path) -> Path:
    if not base.exists():
        return base
    index = 2
    while True:
        candidate = base.with_name(f"{base.name}-{index}")
        if not candidate.exists():
            return candidate
        index += 1


def _managed_entry(kind: str, entry: Path) -> Path:
    if kind.lower() != "napcat" or entry.name.lower() != "napcat.bat":
        return entry
    bootmain = entry.parent / "NapCatWinBootMain.exe"
    if not bootmain.exists():
        return entry
    managed = entry.parent / "xiami_napcat_start.bat"
    managed.write_text(
        "@echo off\r\n"
        "chcp 65001 >nul\r\n"
        "cd /d \"%~dp0\"\r\n"
        "NapCatWinBootMain.exe\r\n",
        encoding="utf-8",
    )
    return managed

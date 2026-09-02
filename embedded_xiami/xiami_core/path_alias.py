from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from xiami_core.storage.paths import PROJECT_ROOT
from xiami_core.windows_process import hidden_check_output, hidden_run


# 旧版为了绕开 NapCat/Node 对中文路径的兼容问题，曾用 subst 创建 X:/Y:/Z:
# 现在改为临时目录 junction，避免在“此电脑”里额外出现盘符。
DEFAULT_ALIAS_DRIVE = "X:"
FALLBACK_ALIAS_DRIVES = ("Y:", "Z:", "W:", "V:", "U:", "T:")
LEGACY_ALIAS_DRIVES = (DEFAULT_ALIAS_DRIVE, *FALLBACK_ALIAS_DRIVES)
ALIAS_BASE_ENV = "XIAMI_RUNTIME_ALIAS_BASE"
ALIAS_DIR_NAME = "xiami_runtime_alias"

_alias_root_cache: Path | None = None


def ensure_ascii_workspace_alias(drive: str = DEFAULT_ALIAS_DRIVE) -> Path:
    """Return an ASCII-only alias directory for PROJECT_ROOT without creating drive letters.

    The *drive* argument is kept for compatibility with older callers. It is intentionally
    ignored so QQ 机器人 runtime never creates X:/Y:/Z: subst drives again.
    """

    del drive
    global _alias_root_cache

    root = PROJECT_ROOT.resolve()
    if _alias_root_cache and _path_points_to(_alias_root_cache, root):
        return _alias_root_cache

    last_error = ""
    for base in _alias_base_candidates():
        alias = _alias_path_for_root(root, base)
        try:
            _ensure_junction(alias, root)
            _alias_root_cache = alias
            return alias
        except OSError as exc:
            last_error = str(exc)
            continue
        except subprocess.SubprocessError as exc:
            last_error = str(exc)
            continue

    detail = f"：{last_error}" if last_error else ""
    raise RuntimeError(f"无法创建 Xiami 临时工作区别名{detail}")


def current_alias_root() -> Path:
    """Return the active alias root if it already exists; do not create it."""

    root = PROJECT_ROOT.resolve()
    if _alias_root_cache and _path_points_to(_alias_root_cache, root):
        return _alias_root_cache
    for base in _alias_base_candidates():
        alias = _alias_path_for_root(root, base)
        if _path_points_to(alias, root):
            return alias
    return Path()


def alias_path(path: str | Path, drive: str = DEFAULT_ALIAS_DRIVE) -> Path:
    source = Path(path)
    if not source.is_absolute():
        return source
    root = PROJECT_ROOT.resolve()
    resolved = source.resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError:
        return resolved
    return ensure_ascii_workspace_alias(drive) / relative


def alias_arg(value: str, drive: str = DEFAULT_ALIAS_DRIVE) -> str:
    if not value:
        return value
    try:
        path = Path(value)
    except OSError:
        return value
    if not path.is_absolute():
        return value
    return str(alias_path(path, drive))


def normalize_alias_path_to_real(value: str) -> str:
    if not value:
        return value
    root = PROJECT_ROOT.resolve()

    alias = current_alias_root()
    if alias:
        normalized = _replace_prefix(value, alias, root)
        if normalized != value:
            return normalized

    # 兼容旧日志里已经输出的 X:/Y:/Z: 二维码路径，但不再创建这些盘符。
    for drive in LEGACY_ALIAS_DRIVES:
        drive = _normalize_drive(drive)
        prefix = drive + "\\"
        if value.upper().startswith(prefix.upper()):
            target = _subst_target(drive)
            if target and _same_path(Path(target), root):
                relative = value[len(prefix) :]
                return str(root / Path(relative))
    return value


def cleanup_aliases() -> None:
    """Remove the junction created for the current PROJECT_ROOT if no process is using it."""

    global _alias_root_cache
    root = PROJECT_ROOT.resolve()
    for base in _alias_base_candidates():
        alias = _alias_path_for_root(root, base)
        if not alias.exists() and not alias.is_symlink():
            continue
        if not _path_points_to(alias, root):
            continue
        try:
            alias.rmdir()
        except OSError:
            continue
    _alias_root_cache = None


def cleanup_legacy_subst_aliases() -> None:
    """Delete only legacy Xiami/NapCat subst drives created by older builds."""

    mappings = _subst_mappings()
    allowed = {_normalize_drive(item) for item in LEGACY_ALIAS_DRIVES}
    for drive, target in mappings.items():
        if _normalize_drive(drive) not in allowed:
            continue
        if not _looks_like_xiami_alias_target(target):
            continue
        try:
            hidden_run(
                ["subst", _normalize_drive(drive), "/D"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except (OSError, subprocess.SubprocessError):
            continue


def _alias_base_candidates() -> list[Path]:
    raw_candidates: list[Path] = []
    env_base = os.environ.get(ALIAS_BASE_ENV, "").strip()
    if env_base:
        raw_candidates.append(Path(env_base))
    raw_candidates.append(Path(tempfile.gettempdir()) / ALIAS_DIR_NAME)
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        raw_candidates.append(Path(local_app_data) / "XiamiToolbox" / "runtime_alias")
    public_dir = os.environ.get("PUBLIC", "").strip()
    if public_dir:
        raw_candidates.append(Path(public_dir) / "XiamiToolbox" / "runtime_alias")

    result: list[Path] = []
    seen: set[str] = set()
    for candidate in raw_candidates:
        key = os.path.normcase(os.path.abspath(str(candidate)))
        if key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    ascii_first = [item for item in result if str(item).isascii()]
    non_ascii = [item for item in result if item not in ascii_first]
    return ascii_first + non_ascii


def _alias_path_for_root(root: Path, base: Path) -> Path:
    digest = hashlib.sha1(_norm(root).encode("utf-8", errors="ignore")).hexdigest()[:16]
    return base / f"root_{digest}"


def _ensure_junction(alias: Path, root: Path) -> None:
    if _path_points_to(alias, root):
        return
    alias.parent.mkdir(parents=True, exist_ok=True)
    if alias.exists() or alias.is_symlink():
        _remove_alias(alias)
    hidden_run(
        ["cmd", "/d", "/c", "mklink", "/J", str(alias), str(root)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if not _path_points_to(alias, root):
        raise OSError(f"临时工作区别名创建后校验失败：{alias}")


def _remove_alias(alias: Path) -> None:
    try:
        if alias.is_dir() or alias.is_symlink():
            alias.rmdir()
        else:
            alias.unlink()
    except OSError:
        # 不能安全删除时不递归清理，避免误删真实目录。
        raise


def _replace_prefix(value: str, alias: Path, root: Path) -> str:
    alias_text = str(alias).rstrip("\\/")
    for prefix in (alias_text + "\\", alias_text + "/"):
        if value.upper().startswith(prefix.upper()):
            relative = value[len(prefix) :]
            return str(root / Path(relative))
    if value.upper() == alias_text.upper():
        return str(root)
    return value


def _path_points_to(alias: Path, root: Path) -> bool:
    try:
        if not alias.exists():
            return False
        return _same_path(alias.resolve(), root)
    except OSError:
        return False


def _same_path(left: Path, right: Path) -> bool:
    return _norm(left) == _norm(right)


def _norm(path: Path) -> str:
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    return os.path.normcase(os.path.abspath(str(resolved))).rstrip("\\/")


def _normalize_drive(drive: str) -> str:
    drive = drive.strip().rstrip("\\/")
    match = re.match(r"^([A-Za-z]):", drive)
    if match:
        return f"{match.group(1).upper()}:"
    if not drive.endswith(":"):
        drive = f"{drive}:"
    return drive.upper()


def _subst_target(drive: str) -> str:
    return _subst_mappings().get(_normalize_drive(drive), "")


def _subst_mappings() -> dict[str, str]:
    try:
        output = hidden_check_output(["subst"], text=True, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return {}
    result: dict[str, str] = {}
    for line in output.splitlines():
        normalized = line.strip()
        if "=>" not in normalized:
            continue
        left, right = normalized.split("=>", 1)
        result[_normalize_drive(left.strip())] = right.strip()
    return result


def _looks_like_xiami_alias_target(target: str) -> bool:
    if not target:
        return False
    try:
        path = Path(target).resolve()
    except OSError:
        path = Path(target)
    root = PROJECT_ROOT.resolve()
    if _same_path(path, root):
        return True
    parts = [part.lower() for part in path.parts]
    text = str(path).lower()
    if "embedded_xiami" in parts:
        return True
    if "qq机器人" in text:
        return True
    if "虾米工具箱" in text and ("embedded_xiami" in text or "qq机器人" in text):
        return True
    return False


def remove_empty_alias_base_dirs() -> None:
    for base in _alias_base_candidates():
        try:
            if base.exists() and not any(base.iterdir()):
                base.rmdir()
        except OSError:
            continue

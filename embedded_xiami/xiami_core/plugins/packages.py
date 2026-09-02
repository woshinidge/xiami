from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
import shutil
import tempfile
import zipfile

from xiami_core.plugins.legacy_file import looks_like_legacy_file_plugin


PLUGIN_PACKAGE_SUFFIX = ".xiami-plugin.zip"
SKIP_DIRS = {"__pycache__", ".git", ".svn", ".hg"}
SKIP_SUFFIXES = {".pyc", ".pyo", ".tmp", ".log"}


@dataclass(frozen=True)
class PluginPackageResult:
    ok: bool
    plugin_id: str = ""
    path: Path | None = None
    message: str = ""


@dataclass(frozen=True)
class ExportablePlugin:
    plugin_id: str
    name: str
    path: Path
    source_type: str
    description: str = ""
    version: str = ""


@dataclass(frozen=True)
class _PluginExportSource:
    root: Path
    plugin_file: Path
    is_file_plugin: bool = False


def discover_exportable_plugins(plugin_root: Path) -> list[ExportablePlugin]:
    if not plugin_root.exists():
        return []

    result: list[ExportablePlugin] = []
    seen: set[str] = set()
    for plugin_dir in sorted(path for path in plugin_root.iterdir() if path.is_dir()):
        plugin_file = plugin_dir / "plugin.py"
        if not plugin_file.is_file():
            continue
        item = _exportable_plugin(plugin_file, plugin_dir, "directory", plugin_dir.name)
        result.append(item)
        seen.add(item.plugin_id)

    for plugin_file in sorted(plugin_root.glob("*.py")):
        if not looks_like_legacy_file_plugin(plugin_file):
            continue
        item = _exportable_plugin(plugin_file, plugin_file, "legacy_file", plugin_file.stem)
        if item.plugin_id in seen:
            continue
        result.append(item)
        seen.add(item.plugin_id)

    return sorted(result, key=lambda item: (item.plugin_id.lower(), item.source_type))


def export_plugin_package(plugin_root: Path, plugin_id: str, output_dir: Path | None = None) -> PluginPackageResult:
    plugin_id = plugin_id.strip()
    if not plugin_id:
        return PluginPackageResult(False, message="插件 ID 不能为空")
    source = _plugin_export_source(plugin_root, plugin_id)
    if not source:
        return PluginPackageResult(False, plugin_id=plugin_id, message=f"插件不存在或缺少 plugin.py：{plugin_id}")

    metadata = inspect_plugin_metadata(source.plugin_file)
    package_id = metadata.get("PLUGIN_ID") or plugin_id
    output_dir = output_dir or plugin_root
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / f"{package_id}{PLUGIN_PACKAGE_SUFFIX}"

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        if source.is_file_plugin:
            archive.write(source.plugin_file, f"{package_id}/plugin.py")
        else:
            for file_path in sorted(source.root.rglob("*")):
                if not file_path.is_file() or _should_skip(file_path):
                    continue
                archive.write(file_path, f"{package_id}/{file_path.relative_to(source.root).as_posix()}")

    return PluginPackageResult(True, plugin_id=package_id, path=archive_path, message=f"插件包已导出：{archive_path}")


def import_plugin_package(package_path: Path, plugin_root: Path, *, overwrite: bool = False) -> PluginPackageResult:
    if not package_path.is_file():
        return PluginPackageResult(False, path=package_path, message=f"插件包不存在：{package_path}")
    plugin_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as temp:
        temp_root = Path(temp)
        try:
            _safe_extract(package_path, temp_root)
        except (OSError, zipfile.BadZipFile, ValueError) as exc:
            return PluginPackageResult(False, path=package_path, message=f"插件包解压失败：{exc}")

        source_dir = _find_plugin_source_dir(temp_root)
        if source_dir is None:
            return PluginPackageResult(False, path=package_path, message="插件包内未找到 plugin.py")

        metadata = inspect_plugin_metadata(source_dir / "plugin.py")
        plugin_id = _safe_plugin_id(metadata.get("PLUGIN_ID") or source_dir.name or package_path.stem)
        if not plugin_id:
            return PluginPackageResult(False, path=package_path, message="插件 ID 无效")

        target_dir = plugin_root / plugin_id
        if target_dir.exists():
            if not overwrite:
                return PluginPackageResult(False, plugin_id=plugin_id, path=target_dir, message=f"插件已存在：{plugin_id}")
            shutil.rmtree(target_dir)
        shutil.copytree(source_dir, target_dir, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))

    return PluginPackageResult(True, plugin_id=plugin_id, path=target_dir, message=f"插件包已导入：{plugin_id}")


def inspect_plugin_metadata(plugin_file: Path) -> dict[str, str]:
    try:
        tree = ast.parse(plugin_file.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeError):
        return {}
    result: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        names = [target.id for target in node.targets if isinstance(target, ast.Name)]
        if not names:
            continue
        value = _literal_string(node.value)
        for name in names:
            if value is not None and name in {"PLUGIN_ID", "PLUGIN_NAME", "PLUGIN_VERSION", "PLUGIN_DESCRIPTION"}:
                result[name] = value
            if name == "plugin_spec" and isinstance(node.value, ast.Dict):
                result.update(_metadata_from_plugin_spec(node.value))
            if isinstance(node.value, ast.Call) and _call_name(node.value) in {"XiamiPlugin", "PluginSpec"}:
                result.update(_metadata_from_legacy_constructor(node.value))
    return result


def _metadata_from_plugin_spec(node: ast.Dict) -> dict[str, str]:
    mapping = {
        "key": "PLUGIN_ID",
        "name": "PLUGIN_NAME",
        "version": "PLUGIN_VERSION",
        "description": "PLUGIN_DESCRIPTION",
    }
    result: dict[str, str] = {}
    for key_node, value_node in zip(node.keys, node.values):
        key = _literal_string(key_node) if key_node is not None else None
        if not key or key not in mapping:
            continue
        value = _literal_string(value_node)
        if value:
            result[mapping[key]] = value
    return result


def _metadata_from_legacy_constructor(node: ast.Call) -> dict[str, str]:
    mapping = {
        "key": "PLUGIN_ID",
        "name": "PLUGIN_NAME",
        "version": "PLUGIN_VERSION",
        "description": "PLUGIN_DESCRIPTION",
    }
    result: dict[str, str] = {}
    positional = ["PLUGIN_ID", "PLUGIN_NAME", "PLUGIN_DESCRIPTION"]
    for index, arg in enumerate(node.args[: len(positional)]):
        value = _literal_string(arg)
        if value:
            result[positional[index]] = value
    for keyword in node.keywords:
        key = keyword.arg or ""
        target = mapping.get(key)
        if not target:
            continue
        value = _literal_string(keyword.value)
        if value:
            result[target] = value
    return result


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _exportable_plugin(plugin_file: Path, path: Path, source_type: str, fallback_id: str) -> ExportablePlugin:
    metadata = inspect_plugin_metadata(plugin_file)
    plugin_id = metadata.get("PLUGIN_ID") or fallback_id
    return ExportablePlugin(
        plugin_id=plugin_id,
        name=metadata.get("PLUGIN_NAME") or plugin_id,
        path=path,
        source_type=source_type,
        description=metadata.get("PLUGIN_DESCRIPTION", ""),
        version=metadata.get("PLUGIN_VERSION", ""),
    )


def _plugin_export_source(plugin_root: Path, plugin_id: str) -> _PluginExportSource | None:
    plugin_dir = plugin_root / plugin_id
    plugin_file = plugin_dir / "plugin.py"
    if plugin_file.is_file():
        return _PluginExportSource(root=plugin_dir, plugin_file=plugin_file)

    direct_file = plugin_root / f"{plugin_id}.py"
    if direct_file.is_file() and looks_like_legacy_file_plugin(direct_file):
        return _PluginExportSource(root=plugin_root, plugin_file=direct_file, is_file_plugin=True)

    for candidate in sorted(plugin_root.glob("*.py")):
        if not looks_like_legacy_file_plugin(candidate):
            continue
        metadata = inspect_plugin_metadata(candidate)
        if metadata.get("PLUGIN_ID") == plugin_id:
            return _PluginExportSource(root=plugin_root, plugin_file=candidate, is_file_plugin=True)
    return None


def _safe_extract(package_path: Path, target_root: Path) -> None:
    with zipfile.ZipFile(package_path) as archive:
        for member in archive.infolist():
            member_path = target_root / member.filename
            resolved = member_path.resolve()
            if not str(resolved).startswith(str(target_root.resolve())):
                raise ValueError(f"非法路径：{member.filename}")
            archive.extract(member, target_root)


def _find_plugin_source_dir(root: Path) -> Path | None:
    if (root / "plugin.py").is_file():
        return root
    candidates = [path.parent for path in root.rglob("plugin.py") if path.is_file()]
    if not candidates:
        return None
    candidates.sort(key=lambda item: len(item.relative_to(root).parts))
    return candidates[0]


def _safe_plugin_id(value: str) -> str:
    result = "".join(ch for ch in value.strip() if ch.isalnum() or ch in {"_", "-"})
    return result[:80]


def _literal_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _should_skip(file_path: Path) -> bool:
    if any(part in SKIP_DIRS for part in file_path.parts):
        return True
    return file_path.suffix.lower() in SKIP_SUFFIXES

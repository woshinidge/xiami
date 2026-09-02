from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import tempfile
from urllib.parse import urlparse
import urllib.error
import urllib.request
import zipfile

from xiami_core.plugins.loader import PluginLoader
from xiami_core.plugins.packages import PLUGIN_PACKAGE_SUFFIX, inspect_plugin_metadata
from xiami_core.plugins.signing import check_package_signature, load_trusted_signers, manifest_signature_required

MARKET_MANIFEST_NAMES = ("xiami-market.json", "market.json")
XIAMI_MARKET_VERSION = "1.0.0"
DEFAULT_ALLOWED_CHANNELS = frozenset({"stable", "release"})


@dataclass(frozen=True)
class PluginMarketItem:
    plugin_id: str
    name: str
    version: str
    description: str
    package_path: Path
    status: str
    installed_version: str = ""
    download_url: str = ""
    sha256: str = ""
    checksum_status: str = ""
    signature: str = ""
    signature_status: str = ""
    signature_required: bool = False
    signer: str = ""
    channel: str = "stable"
    xiami_min_version: str = ""
    xiami_max_version: str = ""
    compatibility_status: str = "compatible"
    homepage: str = ""
    release_notes: str = ""
    source: str = "package"


@dataclass(frozen=True)
class PluginMarketDownloadResult:
    ok: bool
    path: Path = Path()
    message: str = ""


@dataclass(frozen=True)
class PluginMarketInstallDecision:
    ok: bool
    overwrite: bool = False
    message: str = ""


def scan_local_market(package_dir: Path, loader: PluginLoader) -> list[PluginMarketItem]:
    installed = {plugin.id: plugin.version for plugin in loader.plugins}
    items_by_id: dict[str, PluginMarketItem] = {}
    if not package_dir.exists():
        return []
    for package_path in sorted(package_dir.glob(f"*{PLUGIN_PACKAGE_SUFFIX}")):
        item = inspect_market_package(package_path, installed)
        if item:
            items_by_id[item.plugin_id] = item
    for item in _manifest_items(package_dir, installed):
        items_by_id[item.plugin_id] = item
    return sorted(items_by_id.values(), key=lambda item: item.plugin_id)


def inspect_market_package(package_path: Path, installed_versions: dict[str, str] | None = None) -> PluginMarketItem | None:
    installed_versions = installed_versions or {}
    metadata = _package_metadata(package_path)
    plugin_id = metadata.get("PLUGIN_ID") or _plugin_id_from_package_name(package_path)
    if not plugin_id:
        return None
    version = metadata.get("PLUGIN_VERSION", "")
    installed_version = installed_versions.get(plugin_id, "")
    return PluginMarketItem(
        plugin_id=plugin_id,
        name=metadata.get("PLUGIN_NAME") or plugin_id,
        version=version,
        description=metadata.get("PLUGIN_DESCRIPTION", ""),
        package_path=package_path,
        status=_market_status(version, installed_version),
        installed_version=installed_version,
        checksum_status="",
    )


def format_market_items(items: list[PluginMarketItem]) -> str:
    lines = ["# Xiami local plugin market", ""]
    if not items:
        lines.append("- no local plugin packages")
        return "\n".join(lines)
    for item in items:
        version = f" v{item.version}" if item.version else ""
        installed = f", installed={item.installed_version}" if item.installed_version else ""
        checksum = f", sha256={item.checksum_status}" if item.checksum_status else ""
        signature = f", signature={item.signature_status}" if item.signature_status else ""
        signer = f", signer={item.signer}" if item.signer else ""
        channel = f", channel={item.channel}" if item.channel else ""
        compatibility = f", xiami={item.compatibility_status}" if item.compatibility_status else ""
        source = _format_item_source(item)
        lines.append(
            f"- {item.plugin_id}: {item.name}{version} "
            f"[{item.status}{installed}{checksum}{signature}{signer}{channel}{compatibility}] {source}"
        )
    return "\n".join(lines)


def download_market_package(item: PluginMarketItem, cache_dir: Path, *, timeout: float = 30.0) -> PluginMarketDownloadResult:
    if item.package_path.is_file():
        return PluginMarketDownloadResult(True, item.package_path, "本地插件包已存在。")
    if not item.download_url:
        return PluginMarketDownloadResult(False, Path(), "市场项没有可下载 URL。")
    if not _is_url(item.download_url):
        return PluginMarketDownloadResult(False, Path(), f"不支持的下载地址：{item.download_url}")
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / _download_filename(item)
    temp_target = target.with_suffix(target.suffix + ".download")
    try:
        with urllib.request.urlopen(item.download_url, timeout=timeout) as response:
            with temp_target.open("wb") as handle:
                for chunk in iter(lambda: response.read(1024 * 1024), b""):
                    handle.write(chunk)
        if item.sha256:
            actual = _sha256_file(temp_target)
            if actual.lower() != item.sha256.lower():
                try:
                    temp_target.unlink()
                except OSError:
                    pass
                return PluginMarketDownloadResult(False, Path(), "插件包 sha256 校验失败。")
        temp_target.replace(target)
        return PluginMarketDownloadResult(True, target, f"插件包已下载：{target}")
    except (OSError, urllib.error.URLError) as exc:
        try:
            temp_target.unlink()
        except OSError:
            pass
        return PluginMarketDownloadResult(False, Path(), f"插件包下载失败：{exc}")


def market_install_decision(item: PluginMarketItem) -> PluginMarketInstallDecision:
    if item.checksum_status == "mismatch":
        return PluginMarketInstallDecision(False, False, f"插件包校验失败，已阻止安装：{item.plugin_id}")
    if item.signature_status in {"invalid", "unsupported", "untrusted"}:
        return PluginMarketInstallDecision(False, False, f"插件包签名校验失败，已阻止安装：{item.plugin_id}")
    if item.signature_required and item.signature_status != "ok":
        return PluginMarketInstallDecision(False, False, f"市场要求插件包签名，已阻止安装：{item.plugin_id}")
    if item.channel and item.channel.lower() not in DEFAULT_ALLOWED_CHANNELS:
        return PluginMarketInstallDecision(False, False, f"插件处于 {item.channel} 更新通道，默认策略已阻止安装：{item.plugin_id}")
    if item.compatibility_status == "incompatible":
        return PluginMarketInstallDecision(False, False, f"插件不兼容当前 Xiami 版本，已阻止安装：{item.plugin_id}")
    if item.download_url and not item.package_path.is_file() and not item.sha256:
        return PluginMarketInstallDecision(False, False, f"远程插件包缺少 sha256，已阻止安装：{item.plugin_id}")
    if item.status == "not_installed":
        return PluginMarketInstallDecision(True, False, f"准备安装插件：{item.plugin_id}")
    if item.status == "update_available":
        return PluginMarketInstallDecision(True, True, f"准备更新插件：{item.plugin_id} {item.installed_version} -> {item.version}")
    if item.status == "installed":
        return PluginMarketInstallDecision(False, False, f"插件已是当前版本：{item.plugin_id} {item.installed_version or item.version}")
    if item.status == "downgrade":
        return PluginMarketInstallDecision(False, False, f"市场版本低于已安装版本，已阻止降级：{item.plugin_id} {item.installed_version} -> {item.version}")
    return PluginMarketInstallDecision(False, False, f"不支持的市场安装状态：{item.status}")


def _manifest_items(package_dir: Path, installed_versions: dict[str, str]) -> list[PluginMarketItem]:
    for manifest_name in MARKET_MANIFEST_NAMES:
        manifest_path = package_dir / manifest_name
        if not manifest_path.is_file():
            continue
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        trusted_signers = load_trusted_signers(package_dir, data if isinstance(data, dict) else None)
        signature_required = manifest_signature_required(data) if isinstance(data, dict) else False
        raw_items = data.get("plugins") if isinstance(data, dict) else None
        if raw_items is None and isinstance(data, dict):
            raw_items = data.get("items")
        if not isinstance(raw_items, list):
            return []
        items: list[PluginMarketItem] = []
        for entry in raw_items:
            if isinstance(entry, dict):
                item = _manifest_item(entry, package_dir, installed_versions, trusted_signers, signature_required)
                if item:
                    items.append(item)
        return items
    return []


def _manifest_item(
    entry: dict[str, object],
    package_dir: Path,
    installed_versions: dict[str, str],
    trusted_signers: dict[str, dict[str, str]],
    signature_required: bool,
) -> PluginMarketItem | None:
    package_ref = _entry_text(entry, "package", "path", "file")
    url = _entry_text(entry, "url", "download_url")
    package_path = _resolve_package_ref(package_dir, package_ref)
    download_url = url or (package_ref if _is_url(package_ref) else "")
    metadata = _package_metadata(package_path) if package_path.is_file() else {}
    plugin_id = _entry_text(entry, "id", "plugin_id") or metadata.get("PLUGIN_ID") or _plugin_id_from_package_name(package_path)
    if not plugin_id:
        return None
    version = _entry_text(entry, "version") or metadata.get("PLUGIN_VERSION", "")
    installed_version = installed_versions.get(plugin_id, "")
    sha256 = _entry_text(entry, "sha256", "checksum")
    checksum_status = _checksum_status(package_path, sha256) if sha256 else ""
    channel = (_entry_text(entry, "channel", "release_channel") or "stable").lower()
    xiami_min_version = _entry_text(entry, "min_xiami_version", "xiami_min_version", "requires_xiami")
    xiami_max_version = _entry_text(entry, "max_xiami_version", "xiami_max_version")
    compatibility_status = _compatibility_status(xiami_min_version, xiami_max_version)
    signature_check = check_package_signature(
        entry,
        package_path=package_path,
        expected_sha256=sha256,
        trusted_signers=trusted_signers,
        required=signature_required,
    )
    return PluginMarketItem(
        plugin_id=plugin_id,
        name=_entry_text(entry, "name") or metadata.get("PLUGIN_NAME") or plugin_id,
        version=version,
        description=_entry_text(entry, "description") or metadata.get("PLUGIN_DESCRIPTION", ""),
        package_path=package_path,
        status=_market_status(version, installed_version),
        installed_version=installed_version,
        download_url=download_url,
        sha256=sha256,
        checksum_status=checksum_status,
        signature=signature_check.signature,
        signature_status=signature_check.status,
        signature_required=signature_check.required,
        signer=signature_check.key_id,
        channel=channel,
        xiami_min_version=xiami_min_version,
        xiami_max_version=xiami_max_version,
        compatibility_status=compatibility_status,
        homepage=_entry_text(entry, "homepage", "repo", "repository"),
        release_notes=_entry_text(entry, "release_notes", "notes", "changelog"),
        source="manifest",
    )


def _package_metadata(package_path: Path) -> dict[str, str]:
    try:
        with zipfile.ZipFile(package_path) as archive:
            plugin_member = _find_plugin_member(archive)
            if not plugin_member:
                return {}
            with tempfile.TemporaryDirectory() as temp:
                target = Path(temp) / "plugin.py"
                target.write_bytes(archive.read(plugin_member))
                return inspect_plugin_metadata(target)
    except (OSError, zipfile.BadZipFile, KeyError):
        return {}


def _find_plugin_member(archive: zipfile.ZipFile) -> str:
    for name in archive.namelist():
        if name.endswith("/plugin.py") or name == "plugin.py":
            return name
    return ""


def _plugin_id_from_package_name(package_path: Path) -> str:
    name = package_path.name
    if name.endswith(PLUGIN_PACKAGE_SUFFIX):
        return name[: -len(PLUGIN_PACKAGE_SUFFIX)]
    return package_path.stem


def _entry_text(entry: dict[str, object], *keys: str) -> str:
    for key in keys:
        value = entry.get(key)
        if value is not None:
            return str(value).strip()
    return ""


def _resolve_package_ref(package_dir: Path, package_ref: str) -> Path:
    if not package_ref or _is_url(package_ref):
        return Path()
    path = Path(package_ref)
    if path.is_absolute():
        return path
    return package_dir / path


def _is_url(value: str) -> bool:
    return urlparse(value).scheme in {"http", "https"}


def _checksum_status(package_path: Path, expected: str) -> str:
    if not package_path.is_file():
        return "missing"
    actual = _sha256_file(package_path)
    return "ok" if actual.lower() == expected.lower() else "mismatch"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _format_item_source(item: PluginMarketItem) -> str:
    if item.package_path.is_file():
        return str(item.package_path)
    if item.download_url:
        return item.download_url
    return "no package"


def _download_filename(item: PluginMarketItem) -> str:
    name = Path(urlparse(item.download_url).path).name
    if not name.endswith(PLUGIN_PACKAGE_SUFFIX):
        name = f"{item.plugin_id}{PLUGIN_PACKAGE_SUFFIX}"
    return name


def _compatibility_status(min_version: str, max_version: str) -> str:
    current = _version_tuple(XIAMI_MARKET_VERSION)
    if min_version and current < _version_tuple(min_version):
        return "incompatible"
    if max_version and current > _version_tuple(max_version):
        return "incompatible"
    return "compatible"


def _market_status(version: str, installed_version: str) -> str:
    if not installed_version:
        return "not_installed"
    if not version or version == installed_version:
        return "installed"
    if _version_tuple(version) > _version_tuple(installed_version):
        return "update_available"
    return "downgrade"


def _version_tuple(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for raw in version.replace("-", ".").split("."):
        if raw.isdigit():
            parts.append(int(raw))
        else:
            parts.append(0)
    return tuple(parts)

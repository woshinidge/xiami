from __future__ import annotations

import ast
import hashlib
import json
import os
import re
from pathlib import Path, PurePath
from typing import Iterable


PYTHON_CODE_SUFFIXES = {".py", ".pyw", ".pyi", ".pyc", ".pyo"}
PYTHON_CACHE_DIRS = {"__pycache__"}
PLUGIN_CONSTANTS = ("PLUGIN_NAME", "PLUGIN_VERSION", "PLUGIN_DESCRIPTION")
SENSITIVE_FILE_SUFFIXES = (".pem", ".key", ".pfx", ".p12", ".jks", ".keystore", ".env")
RUNTIME_STATE_SUFFIXES = (".log", ".jsonl", ".db", ".db-shm", ".db-wal")
RUNTIME_STATE_PREFIXES = (
    "runtime/tmp_state/",
    "runtime/xiami_v1/logs/",
    "runtime/xiami_v1/plugin_configs/",
    "runtime/xiami_v1/plugin_data/",
    "runtime/xiami_v1/plugin_state/",
    "runtime/xiami_v1/kernels/napcat.shell.windows/napcat/logs/",
    "runtime/xiami_v1/kernels/napcat.shell.windows/napcat/cache/",
)
RUNTIME_STATE_FILES = {
    "runtime/xiami_v1/config.json",
    "runtime/xiami_v1/saved_accounts.json",
    "runtime/xiami_v1/kernels/napcat.shell.windows/beacon_report.log",
    "runtime/xiami_v1/kernels/napcat.shell.windows/guild1.db",
    "runtime/xiami_v1/kernels/napcat.shell.windows/guild1.db-shm",
    "runtime/xiami_v1/kernels/napcat.shell.windows/guild1.db-wal",
    "runtime/xiami_v1/kernels/napcat.shell.windows/napcat/config/webui.json",
}
CONTENT_AUDIT_SUFFIXES = {".json", ".ini", ".yaml", ".yml", ".cfg", ".conf"}
SENSITIVE_CONFIG_KEYS = {
    "accesstoken",
    "apikey",
    "authorization",
    "cookie",
    "password",
    "privatekey",
    "secret",
    "session",
    "token",
    "totpsecret",
}
NON_CONFIG_KEY_CONTAINERS = {
    "bundleddependencies",
    "dependencies",
    "devdependencies",
    "optionaldependencies",
    "peerdependencies",
}
ACCOUNT_CONFIG_PATTERN = re.compile(
    r"^(?:napcat|onebot11)_\d{5,}\.json$|^napcat_protocol_\d{5,}\.json$",
    re.IGNORECASE,
)
EXECUTABLE_SCRIPT_SUFFIXES = {".ps1", ".psm1", ".psd1", ".py", ".pyw", ".pyi", ".bat", ".cmd"}
GLOBAL_STATE_SUFFIXES = {".log", ".jsonl", ".db", ".sqlite", ".sqlite3", ".db-shm", ".db-wal"}
SENSITIVE_CONFIG_NAMES = {
    "accounts.json",
    "auth.json",
    "cookies.json",
    "credentials.json",
    "plugin_config.json",
    "saved_accounts.json",
    "session.json",
    "tokens.json",
    "user_config.json",
    "user_settings.json",
}
RESOURCE_RELEASE_ALLOWLIST = {
    "222.ico": "995e77b5f6e75ae495c63cd2ca1c5338976c1abe11c9904a51ef6113d68ef79b",
    "咕咕鸡过滤.txt": "0362248bd889c181905619bb105f56eeab8d720cd33ec6c25bab4741c9561ac7",
}

MICRO_RELEASE_ALLOWLIST = {
    "qqq/说明.txt": "95be247ce4cb74855e64ee7b68016265fbfc3aeac13b9676c65e99dea5c83714",
    "qqq/图解.png": "f8bd99509c425995aa29e8833c3143d6afd266f7048a9e0ca4c621736849a3dc",
    "qqq/微端程序/简述.txt": "f74d71553e71983f00298042c7f96c619cc1df1f56b8c773af3ec5eff1f5e2ee",
    "qqq/微端程序/pak.txt": "e78a774aa03ce5cc25cde2b69e10689f01eb4e6868dc07ef25fa4d406e332757",
    "qqq/微端程序/pak1.txt": "546a80b8fb0dcf20bda2006afef15d87db6f45e44594c18628df25d58c200d8b",
    "qqq/微端程序/updateserver_x64.exe": "2fe71e3c8ed9fd113a392ebc50d603396412debd6dec6cbceefc785646055de2",
    "qqq/微端程序/updateserver_x64(无缓存).exe": "6e16f596e90a49f961a3eb64251e0620c9717b30b7cf001768273db008eaebef",
    "qqq/微端程序/updateserver.ini": "9352f9c5bbf47506cfdf1c5d8a31e13fe9ee93f9ca5e6744180ec6e02ceae5f8",
    "qqq/微端网关/!serverinfo.txt": "869e95d6b573609eebb22f8b8ef76388b1c58e935868307376e3facabcf49934",
    "qqq/微端网关/config.ini": "0a0a91df7300294eba8709abc3d3895d5710aabdaeff8191b1521834f6ff9fbe",
    "qqq/微端网关/mirupdategate.exe": "2f12ab71f0d35d4259f96c2ccba77f5dc8239bf0b3705654457f59d27cfb26b5",
    "qqq/微端网关/qqwry.dat": "7d2bb097808591375ce7e59e1e8f6000506b6c5114419bc7c30a84de2f2a2ec5",
}

APPROVED_VENDOR_SCRIPT_HASHES = {
    "embedded_xiami/runtime/xiami_v1/kernels/napcat.shell.windows/napcat.bat": "1ecb10069095348d9240704710201314862a8af2a1533b1e919e8a5551aff125",
    "embedded_xiami/runtime/xiami_v1/kernels/napcat.shell.windows/napcat/killqq.bat": "2da28579963ad3f92f2a84b69c77a55c34eb9847f8b99a51c5708f74003180ed",
    "embedded_xiami/runtime/xiami_v1/kernels/napcat.shell.windows/napcat/launcher-user.bat": "1f946e1fc40d79174153d0fdf0ea831c132a447b690d1c8dfce4116869d9719d",
    "embedded_xiami/runtime/xiami_v1/kernels/napcat.shell.windows/napcat/launcher-win10-user.bat": "8d6d6414cddc91f54548c2dc98a7da8d8c8d9e9a0aa35407790df3677afbf0c5",
    "embedded_xiami/runtime/xiami_v1/kernels/napcat.shell.windows/napcat/launcher-win10.bat": "6049a0a2f3e1b9416604ac19abb29b92e7706937ff0f4d7eddf54ba886fa9f4f",
    "embedded_xiami/runtime/xiami_v1/kernels/napcat.shell.windows/napcat/launcher.bat": "0c9cbe19f6a093fe734dbd7da242012d1d189570231f962629ebac89f7dfd51e",
    "embedded_xiami/runtime/xiami_v1/kernels/napcat.shell.windows/napcat/quickloginexample.bat": "cda85806d7037ad71e58a9b2ebaf222a75365f27d8a2f756bd9ab6935ab277a9",
}


def discover_bundled_plugins(plugin_root: os.PathLike[str] | str) -> list[dict[str, object]]:
    root = Path(plugin_root)
    plugins: list[dict[str, object]] = []
    if not root.is_dir():
        return plugins
    for plugin_dir in sorted(root.iterdir(), key=lambda path: path.name.lower()):
        plugin_file = plugin_dir / "plugin.py"
        if not plugin_dir.is_dir() or not plugin_file.is_file():
            continue
        if not plugin_dir.name.isidentifier():
            raise ValueError(f"Bundled plugin directory is not a valid module name: {plugin_dir.name}")
        source = plugin_file.read_text(encoding="utf-8-sig")
        metadata = _read_plugin_metadata(source)
        plugins.append(
            {
                "id": plugin_dir.name,
                "module": f"xiami_plugins.{plugin_dir.name}.plugin",
                "name": metadata.get("PLUGIN_NAME") or plugin_dir.name,
                "version": metadata.get("PLUGIN_VERSION") or "-",
                "description": metadata.get("PLUGIN_DESCRIPTION") or "",
                "commands": sorted(set(re.findall(r"['\"](/[A-Za-z0-9_\\-]+)", source))),
            }
        )
    return plugins


def collect_non_python_datas(
    source_root: os.PathLike[str] | str,
    destination_root: str,
) -> list[tuple[str, str]]:
    """Collect resources while refusing Python source and bytecode as loose data."""
    root = Path(source_root)
    result: list[tuple[str, str]] = []
    collected_release_paths: set[str] = set()
    if not root.is_dir():
        return result
    for current_root, dir_names, file_names in os.walk(str(root)):
        dir_names[:] = sorted(name for name in dir_names if name not in PYTHON_CACHE_DIRS)
        current = Path(current_root)
        relative_dir = current.relative_to(root)
        destination = os.path.join(destination_root, str(relative_dir)) if relative_dir.parts else destination_root
        for file_name in sorted(file_names):
            source = current / file_name
            if source.suffix.lower() in PYTHON_CODE_SUFFIXES:
                continue
            relative_file = source.relative_to(root).as_posix()
            release_path = PurePath(destination_root, relative_file).as_posix()
            content = source.read_bytes() if release_file_requires_content(release_path) else None
            reason = release_file_violation(release_path, content)
            if reason:
                if source.suffix.lower() in EXECUTABLE_SCRIPT_SUFFIXES:
                    raise RuntimeError(f"Required runtime script failed release review: {source} ({reason})")
                continue
            result.append((str(source), destination))
            collected_release_paths.add(_normalize_release_path(release_path).casefold())
    destination_prefix = _normalize_release_path(destination_root).rstrip("/").casefold() + "/"
    required_scripts = {
        path for path in APPROVED_VENDOR_SCRIPT_HASHES if path.startswith(destination_prefix)
    }
    missing_scripts = sorted(required_scripts - collected_release_paths)
    if missing_scripts:
        raise RuntimeError("Required reviewed runtime scripts are missing: " + ", ".join(missing_scripts))
    return result


def collect_allowlisted_datas(
    source_root: os.PathLike[str] | str,
    destination_root: str,
    allowlist: dict[str, str],
) -> list[tuple[str, str]]:
    """Collect only reviewed files and fail if a reviewed artifact changed or disappeared."""
    root = Path(source_root)
    if not root.is_dir():
        raise FileNotFoundError(f"Required release resource directory is missing: {root}")
    available = {
        path.relative_to(root).as_posix().casefold(): path
        for path in root.rglob("*")
        if path.is_file()
    }
    result: list[tuple[str, str]] = []
    for relative_path, expected_sha256 in allowlist.items():
        normalized = relative_path.replace("\\", "/").lstrip("./")
        source = available.get(normalized.casefold())
        if source is None:
            raise FileNotFoundError(f"Required reviewed release resource is missing: {root / normalized}")
        actual_sha256 = _sha256_path(source)
        if actual_sha256 != expected_sha256.lower():
            raise RuntimeError(
                f"Reviewed release resource changed: {source} "
                f"(expected sha256 {expected_sha256.lower()}, got {actual_sha256})"
            )
        relative_parent = PurePath(normalized).parent
        destination = destination_root
        if str(relative_parent) not in {"", "."}:
            destination = os.path.join(destination_root, *relative_parent.parts)
        result.append((str(source), destination))
    return result


def write_bundled_plugin_manifest(
    output_path: os.PathLike[str] | str,
    plugins: Iterable[dict[str, object]],
) -> str:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"format": 1, "plugins": list(plugins)}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return str(path)


def assert_no_embedded_python_datas(datas: Iterable[tuple[str, str]]) -> None:
    violations: list[str] = []
    for source, destination in datas:
        destination_parts = Path(str(destination).replace("/", os.sep)).parts
        if not destination_parts or destination_parts[0].lower() != "embedded_xiami":
            continue
        source_path = Path(source)
        if source_path.is_dir():
            violations.append(f"directory data entry can leak Python sources: {source} -> {destination}")
        elif source_path.suffix.lower() in PYTHON_CODE_SUFFIXES:
            violations.append(f"loose Python code: {source} -> {destination}")
    if violations:
        raise RuntimeError("embedded_xiami data policy failed:\n" + "\n".join(violations))


def assert_no_forbidden_embedded_datas(datas: Iterable[tuple[str, str]]) -> None:
    violations: list[str] = []
    for source, destination in datas:
        destination_parts = Path(str(destination).replace("/", os.sep)).parts
        if not destination_parts or destination_parts[0].lower() != "embedded_xiami":
            continue
        source_path = Path(source)
        destination_relative = Path(*destination_parts[1:], source_path.name).as_posix()
        reason = embedded_release_violation(destination_relative) or _source_content_violation(
            source_path, destination_relative
        )
        if reason:
            violations.append(f"{reason}: {source} -> {destination}")
    if violations:
        raise RuntimeError("embedded_xiami release data policy failed:\n" + "\n".join(violations))


def assert_release_datas(datas: Iterable[tuple[str, str]]) -> None:
    """Validate every loose file that PyInstaller will copy into the release."""
    violations: list[str] = []
    for source, destination in datas:
        source_path = Path(source)
        release_path = PurePath(str(destination), source_path.name).as_posix()
        if source_path.is_dir():
            violations.append(f"unreviewed directory data entry: {source} -> {destination}")
            continue
        if not source_path.is_file():
            violations.append(f"missing release data file: {source} -> {destination}")
            continue
        content = source_path.read_bytes() if release_file_requires_content(release_path) else None
        reason = release_file_violation(release_path, content)
        if reason:
            violations.append(f"{reason}: {source} -> {destination}")
    if violations:
        raise RuntimeError("release security policy failed:\n" + "\n".join(violations))


def release_file_requires_content(relative_path: str) -> bool:
    normalized = _normalize_release_path(relative_path)
    suffix = Path(normalized).suffix.lower()
    name = PurePath(normalized).name.casefold()
    return bool(
        suffix in EXECUTABLE_SCRIPT_SUFFIXES
        or suffix in CONTENT_AUDIT_SUFFIXES
        or name in SENSITIVE_CONFIG_NAMES
        or _rooted_release_path(normalized, "resources")
        or _rooted_release_path(normalized, "微端配置目录")
    )


def release_file_violation(relative_path: str, content: bytes | None = None) -> str | None:
    """Return a fail-closed reason for any loose file in a directory or ZIP release."""
    normalized = _normalize_release_path(relative_path)
    parts = PurePath(normalized).parts
    if not parts:
        return None
    name = parts[-1].casefold()
    suffix = Path(name).suffix.lower()

    embedded_path = _rooted_release_path(normalized, "embedded_xiami")
    if embedded_path:
        embedded_relative = PurePath(*PurePath(embedded_path).parts[1:]).as_posix()
        reason = embedded_release_violation(embedded_relative)
        if reason:
            return reason

    resource_path = _rooted_release_path(normalized, "resources")
    if resource_path:
        resource_relative = PurePath(*PurePath(resource_path).parts[1:]).as_posix().casefold()
        if resource_relative == "free_micro_client/passwordworker.ps1":
            return "retired legacy PasswordWorker.ps1"
        expected_sha256 = _casefold_allowlist(RESOURCE_RELEASE_ALLOWLIST).get(resource_relative)
        if expected_sha256 is None:
            return "unapproved top-level resource"
        if content is None:
            return "reviewed resource content was not available for verification"
        if _sha256_bytes(content) != expected_sha256:
            return "reviewed resource hash mismatch"
        return None

    micro_path = _rooted_release_path(normalized, "微端配置目录")
    if micro_path:
        micro_relative = PurePath(*PurePath(micro_path).parts[1:]).as_posix().casefold()
        expected_sha256 = _casefold_allowlist(MICRO_RELEASE_ALLOWLIST).get(micro_relative)
        if expected_sha256 is None:
            return "unapproved micro-client template resource"
        if content is None:
            return "reviewed micro-client resource content was not available for verification"
        if _sha256_bytes(content) != expected_sha256:
            return "reviewed micro-client resource hash mismatch"
        return None

    if suffix in EXECUTABLE_SCRIPT_SUFFIXES:
        vendor_path = embedded_path or normalized
        expected_sha256 = APPROVED_VENDOR_SCRIPT_HASHES.get(vendor_path.casefold())
        if expected_sha256 is None:
            return "unprotected executable script"
        if content is None:
            return "approved vendor script content was not available for verification"
        if _sha256_bytes(content) != expected_sha256:
            return "approved vendor script hash mismatch"
        return None

    if name.endswith(SENSITIVE_FILE_SUFFIXES) or name == ".env" or name.startswith(".env."):
        return "credential or private-key file"
    if name.endswith(tuple(GLOBAL_STATE_SUFFIXES)):
        return "runtime log or database state"
    if name in SENSITIVE_CONFIG_NAMES or ACCOUNT_CONFIG_PATTERN.fullmatch(name):
        return "account, token, or user configuration"

    if content is not None:
        reason = embedded_content_violation(normalized, content)
        if reason:
            return reason
    return None


def _normalize_release_path(path: str) -> str:
    return PurePath(path.replace("\\", "/").lstrip("./")).as_posix()


def _rooted_release_path(normalized_path: str, root_name: str) -> str | None:
    parts = PurePath(normalized_path).parts
    root = root_name.casefold()
    for index in range(min(2, len(parts))):
        if parts[index].casefold() == root:
            return PurePath(*parts[index:]).as_posix()
    return None


def _casefold_allowlist(allowlist: dict[str, str]) -> dict[str, str]:
    return {key.replace("\\", "/").lstrip("./").casefold(): value.lower() for key, value in allowlist.items()}


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def embedded_release_violation(relative_path: str) -> str | None:
    """Return a fail-closed release-policy reason for an embedded_xiami path."""
    normalized = relative_path.replace("\\", "/").lstrip("./").lower()
    parts = PurePath(normalized).parts
    if not parts:
        return None
    name = parts[-1]
    if name.endswith(tuple(PYTHON_CODE_SUFFIXES)):
        return "loose Python source or bytecode"
    if name.endswith(SENSITIVE_FILE_SUFFIXES) or name == ".env" or name.startswith(".env."):
        return "credential or private-key file"
    if normalized in RUNTIME_STATE_FILES:
        return "machine-specific runtime state"
    if any(normalized.startswith(prefix) for prefix in RUNTIME_STATE_PREFIXES):
        return "generated runtime state"
    if normalized.startswith("runtime/") and name.endswith(RUNTIME_STATE_SUFFIXES):
        return "runtime log or database state"
    if normalized.startswith("runtime/") and ACCOUNT_CONFIG_PATTERN.fullmatch(name):
        return "account-specific runtime configuration"
    if len(parts) >= 3 and parts[0] == "xiami_plugins" and name == "plugin_config.json":
        return "plugin user configuration"
    return None


def embedded_content_violation(relative_path: str, content: bytes) -> str | None:
    """Reject non-empty credentials in text configuration without exposing values."""
    suffix = Path(relative_path).suffix.lower()
    if suffix not in CONTENT_AUDIT_SUFFIXES:
        return None
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None
    if suffix == ".json":
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return _text_config_violation(text)
        return "non-empty credential in JSON configuration" if _contains_nonempty_credential(payload) else None
    return _text_config_violation(text)


def _source_content_violation(source: Path, relative_path: str) -> str | None:
    if source.suffix.lower() not in CONTENT_AUDIT_SUFFIXES:
        return None
    try:
        return embedded_content_violation(relative_path, source.read_bytes())
    except OSError:
        return "unreadable configuration cannot pass credential audit"


def _contains_nonempty_credential(value: object) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized_key = re.sub(r"[^a-z0-9]", "", str(key).lower())
            if normalized_key in NON_CONFIG_KEY_CONTAINERS:
                continue
            if normalized_key in SENSITIVE_CONFIG_KEYS and _is_nonempty_value(child):
                return True
            if _contains_nonempty_credential(child):
                return True
    elif isinstance(value, list):
        return any(_contains_nonempty_credential(child) for child in value)
    return False


def _is_nonempty_value(value: object) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return bool(value)
    return value != 0


def _text_config_violation(text: str) -> str | None:
    for line in text.splitlines():
        match = re.match(r"^\s*([A-Za-z0-9_.-]+)\s*[:=]\s*(.*?)\s*$", line)
        if not match:
            continue
        normalized_key = re.sub(r"[^a-z0-9]", "", match.group(1).lower())
        if normalized_key not in SENSITIVE_CONFIG_KEYS:
            continue
        raw_value = match.group(2).split("#", 1)[0].strip().strip("\"'")
        if raw_value and raw_value.lower() not in {"null", "none", "false", "0"}:
            return "non-empty credential in text configuration"
    return None


def _read_plugin_metadata(source: str) -> dict[str, object]:
    try:
        module = ast.parse(source)
    except SyntaxError as exc:
        raise ValueError(f"Cannot parse bundled plugin metadata: {exc}") from exc
    metadata: dict[str, object] = {}
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        names = {target.id for target in node.targets if isinstance(target, ast.Name)}
        for name in PLUGIN_CONSTANTS:
            if name not in names:
                continue
            try:
                metadata[name] = ast.literal_eval(node.value)
            except (TypeError, ValueError):
                pass
    return metadata

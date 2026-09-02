from __future__ import annotations

import os
import configparser
import sys
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any, Callable, Mapping

try:
    from PIL import Image
except BaseException:
    Image = None

from embedded_npc_visual.core.npc_visual_v2.resources.asset_providers import (
    AssetAuthorizationSnapshot,
    MerchantBackgroundProvider,
    NativeAssetAuthorizationError,
    NativeAssetReadGate,
    RenderImageAsset,
    WzlImageProvider,
)
from toolbox_native_asset_worker import NativeAssetWorkerBroker, NativeAssetWorkerError


@dataclass(frozen=True)
class ResourceImage:
    image: Any
    origin_x: int = 0
    origin_y: int = 0
    file_name: str = ""
    status: str = ""


def _recovered_append_unique_compat_path(paths: list[Path], path: Path) -> None:
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path.absolute()
    for item in paths:
        try:
            if item.resolve() == resolved:
                return None
        except OSError:
            if item.absolute() == resolved:
                return None
    paths.append(path)
    return None


def _recovered_append_v2_data_dir_compat_candidates(
    paths: list[Path],
    root: Path,
    login: Path,
    patch_folder: str,
    resource_dir: str,
) -> None:
    original_paths = tuple(paths)
    ordered_paths = []

    def append_candidate(path: Path) -> None:
        _recovered_append_unique_compat_path(ordered_paths, path)

    append_candidate(root / "Data")
    append_candidate(root / "data")
    append_candidate(root / "Mir200" / "Data")
    append_candidate(root / "Mir200" / "data")
    append_candidate(login / "Data")
    append_candidate(login / "data")
    append_candidate(login / "补丁文件夹" / "Data")
    append_candidate(login / "补丁文件夹" / "data")
    if resource_dir:
        append_candidate(login / "补丁文件夹" / resource_dir / "Data")
        append_candidate(login / "补丁文件夹" / resource_dir / "data")

    if patch_folder:
        patch_root = Path(patch_folder)
        append_candidate(patch_root / "Data")
        append_candidate(patch_root / "data")
        if resource_dir:
            append_candidate(patch_root / resource_dir / "Data")
            append_candidate(patch_root / resource_dir / "data")

    append_candidate(login)
    append_candidate(login / "补丁文件夹")
    if resource_dir:
        append_candidate(login / "补丁文件夹" / resource_dir)
    if patch_folder:
        patch_root = Path(patch_folder)
        append_candidate(patch_root)
        if resource_dir:
            append_candidate(patch_root / resource_dir)
    for path in original_paths:
        append_candidate(path)
    paths[:] = ordered_paths
    return None


def _recovered_restrict_to_client(
    paths: list[Path], client_folder: str, resource_dir: str = ""
) -> list[Path]:
    """Search only the selected game client, expanding its own data dirs.

    Server folders and the login-maker packaging folder can hold same-named
    copies of an asset; reading those instead of the deployed client is what
    produced the wrong slot counts. The client is expanded the same way the
    patch root is, then any known path already inside the client is kept.

    Returns the input untouched when no client is selected or the path is
    unusable, so a project root alone never narrows the search.
    """
    if not client_folder:
        return paths
    client_root = Path(client_folder)
    if not client_root.is_dir():
        return paths
    ordered: list[Path] = []

    def add(candidate: Path) -> None:
        if candidate.is_dir() and candidate not in ordered:
            ordered.append(candidate)

    for name in ("Data", "data"):
        add(client_root / name)
    if resource_dir:
        for name in ("Data", "data"):
            add(client_root / resource_dir / name)
    add(client_root)
    if resource_dir:
        add(client_root / resource_dir)
    try:
        client_key = str(client_root.resolve()).casefold()
    except OSError:
        return ordered or paths
    for path in paths:
        try:
            resolved = str(Path(path).resolve()).casefold()
        except OSError:
            continue
        if resolved == client_key or resolved.startswith(client_key + os.sep):
            add(Path(path))
    return ordered or paths


def _recovered_discover_login_folder(root: Path) -> Path:
    """Locate the client folder under root when the UI has not named one.

    "登录器" is only the usual name; private versions use others such as
    登录器边界村. Score each child on the markers a client actually carries so a
    leftover folder holding a stale PAK cannot win over the real client.
    """
    default = root / "登录器"
    if not root.is_dir():
        return default
    best_path = None
    best_score = 0
    try:
        children = sorted(root.iterdir(), key=lambda item: item.name)
    except OSError:
        return default
    for child in children:
        if not child.is_dir():
            continue
        score = 0
        if (child / "pak.txt").is_file():
            score += 4
        if (child / "Config.ini").is_file():
            score += 3
        if (child / "补丁文件夹").is_dir():
            score += 3
        try:
            if any(item.suffix.lower() == ".pak" for item in child.iterdir()):
                score += 1
        except OSError:
            pass
        if child.name.startswith("登录器"):
            score += 1
        if score > best_score:
            best_score = score
            best_path = child
    if best_path is not None:
        return best_path
    return default


def _recovered_select_v2_pak_txt_compat(
    pak_txt: Path,
    login: Path,
    root: Path,
    patch_folder: str,
    data_dirs: list[Path],
    data_dir: Path | None,
) -> Path:
    pak_candidates = [
        pak_txt,
        login / "补丁文件夹" / "pak.txt",
        root / "pak.txt",
    ]
    if root.is_dir():
        try:
            pak_candidates.extend(
                child / "pak.txt"
                for child in root.iterdir()
                if child.is_dir()
            )
        except OSError:
            pass
    if patch_folder:
        patch_root = Path(patch_folder)
        pak_candidates.append(patch_root / "pak.txt")
        parent = patch_root.parent
        if parent.name:
            pak_candidates.append(parent / "pak.txt")
    if data_dir is not None:
        pak_candidates.append(data_dir / "pak.txt")
        parent = data_dir.parent
        if parent.name:
            pak_candidates.append(parent / "pak.txt")
    for path in data_dirs:
        pak_candidates.append(path / "pak.txt")
        parent = path.parent
        if parent.name:
            pak_candidates.append(parent / "pak.txt")
    return next((path for path in pak_candidates if path.is_file()), pak_candidates[0])


class ResourceProvider:
    """Resource-facing adapter for v2 visual NPC rendering.

    The heavy PAK/WIL/WZL decoding stays in the existing preview providers.
    This class only resolves version-specific paths and exposes a stable,
    small surface to the v2 Qt page.
    """

    def __init__(
        self,
        session_provider: Callable[[], Mapping[str, Any] | None] | None = None,
        asset_broker: NativeAssetWorkerBroker | None = None,
    ) -> None:
        self.session_provider = session_provider
        native_worker_setting = os.environ.get("XIAMI_NATIVE_ASSET_WORKER", "").strip().lower()
        if asset_broker is None and (
            bool(getattr(sys, "frozen", False))
            or native_worker_setting not in {"0", "false", "no", "off"}
        ):
            asset_broker = NativeAssetWorkerBroker()
        self._asset_gate = NativeAssetReadGate(session_provider, asset_broker=asset_broker)
        self.background_provider = MerchantBackgroundProvider(
            session_provider=session_provider,
            asset_gate=self._asset_gate,
        )
        self.item_provider = WzlImageProvider(
            session_provider=session_provider,
            asset_gate=self._asset_gate,
        )
        self.version_path = ""
        self.login_folder = ""
        self.patch_folder = ""
        self.engine_family = "lf"
        self.database_path = ""
        self.client_folder = ""
        self.effect_list_path = None
        self.pak_txt_path = None
        self.data_dir = None
        self.data_dirs = ()
        self.last_status = ""
        self.configured = False
        self._image_cache = {}

    def clear_authorized_caches(self) -> None:
        self._image_cache.clear()
        gates = []
        background = self.background_provider
        if background is not None:
            for name in ("records_cache", "image_cache", "wzl_cache"):
                cache = getattr(background, name, None)
                if hasattr(cache, "clear"):
                    cache.clear()
            gate = getattr(background, "asset_gate", None)
            if hasattr(gate, "clear") and gate not in gates:
                gates.append(gate)
        item = self.item_provider
        if item is not None:
            for name in ("cache", "item_records_cache"):
                cache = getattr(item, name, None)
                if hasattr(cache, "clear"):
                    cache.clear()
            if hasattr(item, "background_cache"):
                item.background_cache = None
            if hasattr(item, "background_cache_key"):
                item.background_cache_key = None
            gate = getattr(item, "asset_gate", None)
            if hasattr(gate, "clear") and gate not in gates:
                gates.append(gate)
        for gate in gates:
            gate.clear()

    def configure(
        self,
        version_path: str,
        login_folder: str = "",
        patch_folder: str = "",
        engine_family: str = "lf",
        database_path: str = "",
        client_folder: str = "",
    ) -> None:
        version_path = str(version_path or "")
        login_folder = str(login_folder or "")
        patch_folder = str(patch_folder or "")
        client_folder = str(client_folder or "")
        engine_family = str(engine_family or "lf").casefold()
        signature = (
            version_path,
            login_folder,
            patch_folder,
            engine_family,
            database_path,
            client_folder,
        )
        old_signature = (
            self.version_path,
            self.login_folder,
            self.patch_folder,
            self.engine_family,
            self.database_path,
            self.client_folder,
        )
        if signature == old_signature and self.data_dirs:
            return None
        if not version_path:
            self.configured = False
            self.version_path = ""
            self.login_folder = ""
            self.patch_folder = ""
            self.engine_family = engine_family
            self.database_path = database_path
            self.client_folder = client_folder
            self.effect_list_path = None
            self.pak_txt_path = None
            self.data_dir = None
            self.data_dirs = ()
            self._image_cache.clear()
            return None

        self.version_path = version_path
        self.login_folder = login_folder
        self.patch_folder = patch_folder
        self.engine_family = engine_family
        self.database_path = database_path
        self.client_folder = client_folder
        self.configured = True
        self._image_cache.clear()

        envir, pak_txt, data_dir, data_dirs = self._version_paths(
            version_path, login_folder, patch_folder, engine_family, client_folder
        )
        self.effect_list_path = (
            envir / "EffectImageList.txt" if envir is not None else None
        )
        self.pak_txt_path = pak_txt
        self.data_dir = data_dir
        self.data_dirs = data_dirs
        if (
            self.background_provider is not None
            and self.effect_list_path is not None
            and pak_txt is not None
            and data_dir is not None
        ):
            self.background_provider.configure(
                self.effect_list_path, pak_txt, data_dir, data_dirs
            )
        if (
            self.item_provider is not None
            and data_dir is not None
            and hasattr(self.item_provider, "configure")
        ):
            self.item_provider.configure(
                data_dir,
                database_path or None,
                data_dirs,
                pak_txt_path=pak_txt,
            )
        return None

    def _asset_cache_operation(
        self,
        *parts: object,
        snapshot: AssetAuthorizationSnapshot | None = None,
    ) -> tuple[
        NativeAssetReadGate | None,
        AssetAuthorizationSnapshot | None,
        tuple[object, ...],
    ]:
        gate = getattr(self, "_asset_gate", None)
        if not isinstance(gate, NativeAssetReadGate):
            gate = getattr(self.background_provider, "asset_gate", None)
        if not isinstance(gate, NativeAssetReadGate):
            return None, None, (None, *parts)
        try:
            current = snapshot or gate.capture_snapshot()
            gate.ensure_snapshot_current(current)
        except NativeAssetAuthorizationError:
            if snapshot is not None:
                raise
            return gate, None, (None, *parts)
        return gate, current, (current.cache_identity, *parts)

    @staticmethod
    def _ensure_asset_cache_snapshot(
        gate: NativeAssetReadGate | None,
        snapshot: AssetAuthorizationSnapshot | None,
    ) -> None:
        if isinstance(gate, NativeAssetReadGate) and isinstance(
            snapshot, AssetAuthorizationSnapshot
        ):
            gate.ensure_snapshot_current(snapshot)

    def _authorized_image_cache_key(self, *parts: object) -> tuple[object, ...]:
        return self._asset_cache_operation(*parts)[2]

    def get_image(
        self,
        file_id: str | int,
        index: int,
        *,
        _snapshot: AssetAuthorizationSnapshot | None = None,
    ) -> ResourceImage | None:
        gate, snapshot, key = self._asset_cache_operation(
            str(file_id), int(index), snapshot=_snapshot
        )
        if key in self._image_cache:
            self._ensure_asset_cache_snapshot(gate, snapshot)
            return self._clone(self._image_cache[key])
        image = self._load_image(file_id, index)
        if image is not None:
            self._ensure_asset_cache_snapshot(gate, snapshot)
            self._image_cache[key] = image
        self._ensure_asset_cache_snapshot(gate, snapshot)
        return self._clone(image)

    def get_cached_image(
        self, file_id: str | int, index: int
    ) -> ResourceImage | None:
        gate, snapshot, key = self._asset_cache_operation(str(file_id), int(index))
        if snapshot is None:
            return None
        image = self._image_cache.get(key)
        self._ensure_asset_cache_snapshot(gate, snapshot)
        return self._clone(image)

    def prewarm_images(self, specs) -> int:
        """Load the exact images a pending render will need off the GUI thread.

        PAK record tables are warmed concurrently first, then every requested
        image index is decoded into this provider's cache. The later paint pass
        only clones cached PIL images and creates Qt pixmaps.
        """
        if not self.configured or self.background_provider is None:
            return 0
        gate, snapshot, _key = self._asset_cache_operation("__prewarm__")
        if snapshot is None:
            return 0
        warmer = getattr(self.background_provider, "prewarm_file_names", None)
        normalized_specs: list[tuple[str | int, int]] = []
        spec_keys: set[tuple[str, int]] = set()
        names: list[str] = []
        seen_names: set[str] = set()
        for spec in specs or ():
            if isinstance(spec, (tuple, list)) and spec:
                file_id = spec[0]
                try:
                    image_index = int(spec[1]) if len(spec) > 1 else 0
                except (TypeError, ValueError):
                    image_index = 0
            else:
                file_id = spec
                image_index = 0
            text = str(file_id or "").strip()
            if not text:
                continue
            normalized_file_id: str | int = (
                int(text) if text.lstrip("-").isdigit() else text
            )
            spec_key = (str(normalized_file_id).casefold(), image_index)
            if spec_key not in spec_keys:
                spec_keys.add(spec_key)
                normalized_specs.append((normalized_file_id, image_index))
            if text.lstrip("-").isdigit():
                try:
                    text = self.background_provider.file_name_for_index(int(text))
                except Exception:
                    continue
            text = str(text or "").strip()
            if not text or text.casefold() in seen_names:
                continue
            seen_names.add(text.casefold())
            names.append(text)
        if not normalized_specs:
            return 0
        if callable(warmer) and names:
            try:
                warmer(names)
            except Exception:
                pass
        loaded = 0
        for file_id, image_index in normalized_specs:
            try:
                image = self.get_image(
                    file_id,
                    image_index,
                    _snapshot=snapshot,
                )
            except Exception:
                continue
            if image is not None:
                loaded += 1
        self._ensure_asset_cache_snapshot(gate, snapshot)
        return loaded

    def get_item_image(
        self,
        item_id: int,
        *,
        _snapshot: AssetAuthorizationSnapshot | None = None,
    ) -> ResourceImage | None:
        self.last_status = ""
        gate, snapshot, key = self._asset_cache_operation(
            "__item__", int(item_id), snapshot=_snapshot
        )
        if key in self._image_cache:
            self._ensure_asset_cache_snapshot(gate, snapshot)
            return self._clone(self._image_cache[key])
        if not self.configured:
            self.last_status = "Resource provider is not configured"
            return None
        if self.item_provider is None:
            self.last_status = "Item provider unavailable"
            return None
        try:
            getter = getattr(self.item_provider, "get_item_asset", None)
            if callable(getter):
                if snapshot is None:
                    asset = getter(int(item_id))
                else:
                    asset = getter(int(item_id), _snapshot=snapshot)
            else:
                image = self.item_provider.get_item_image(int(item_id))
                asset = ResourceImage(image, file_name=f"item:{item_id}")
            resource = self._resource_image_from_asset(asset, f"item:{item_id}")
            if resource is None:
                self.last_status = str(
                    getattr(self.item_provider, "last_status", "")
                    or f"ItemShow item {item_id} resource not found"
                )
            if resource is not None:
                self._ensure_asset_cache_snapshot(gate, snapshot)
                self._image_cache[key] = resource
            self._ensure_asset_cache_snapshot(gate, snapshot)
            return resource
        except (NativeAssetAuthorizationError, NativeAssetWorkerError):
            raise
        except Exception as exc:
            self.last_status = f"ItemShow load failed: {exc}"
            return None

    def item_id_for_name(self, item_name: str) -> int | None:
        if not self.configured or self.item_provider is None:
            return None
        resolver = getattr(self.item_provider, "item_id_for_name", None)
        if not callable(resolver):
            return None
        try:
            return resolver(item_name)
        except BaseException as exc:
            self.last_status = f"ItemShow item-name lookup failed: {exc}"
            return None

    def item_field_for_name(self, item_name: str, field_name: str) -> object | None:
        if not self.configured or self.item_provider is None:
            return None
        resolver = getattr(self.item_provider, "item_field_for_name", None)
        if not callable(resolver):
            return None
        try:
            return resolver(item_name, field_name)
        except BaseException as exc:
            self.last_status = f"StdItems field lookup failed: {exc}"
            return None

    def get_monster_image(
        self,
        file_index: int,
        frame_index: int,
        *,
        _snapshot: AssetAuthorizationSnapshot | None = None,
    ) -> ResourceImage | None:
        gate, snapshot, key = self._asset_cache_operation(
            "__monster__",
            int(file_index),
            int(frame_index),
            snapshot=_snapshot,
        )
        if key in self._image_cache:
            self._ensure_asset_cache_snapshot(gate, snapshot)
            return self._clone(self._image_cache[key])
        if not self.configured or self.background_provider is None:
            self.last_status = "Monster provider is not configured"
            return None
        file_name = f"Mon{int(file_index)}.wzl"
        try:
            getter = getattr(self.background_provider, "image_asset_for_file_name", None)
            if not callable(getter):
                return None
            asset = getter(file_name, int(frame_index))
            image = self._resource_image_from_asset(asset, f"{file_name} #{frame_index}")
            if image is not None:
                self._ensure_asset_cache_snapshot(gate, snapshot)
                self._image_cache[key] = image
            self._ensure_asset_cache_snapshot(gate, snapshot)
            return self._clone(image)
        except NativeAssetAuthorizationError:
            raise
        except BaseException as exc:
            self.last_status = f"Monster load failed: {file_name} #{frame_index} / {exc}"
            return None

    def _load_image(self, file_id: str | int, index: int) -> ResourceImage | None:
        self.last_status = ""
        if not self.configured:
            self.last_status = "Resource provider is not configured"
            return None
        if self.background_provider is None:
            self.last_status = "Background provider unavailable"
            return None
        try:
            if isinstance(file_id, int) or str(file_id).strip().lstrip("-").isdigit():
                getter = getattr(self.background_provider, "image_asset_for_wil", None)
                if callable(getter):
                    asset = getter(int(file_id), int(index))
                else:
                    image, file_name = self.background_provider.image_for_wil(
                        int(file_id), int(index)
                    )
                    asset = ResourceImage(image, file_name=file_name)
            else:
                getter = getattr(
                    self.background_provider, "image_asset_for_file_name", None
                )
                if callable(getter):
                    asset = getter(str(file_id), int(index))
                else:
                    image, file_name = self.background_provider.image_for_file_name(
                        str(file_id), int(index)
                    )
                    asset = ResourceImage(image, file_name=file_name)
            return self._resource_image_from_asset(asset, f"{file_id} #{index}")
        except NativeAssetAuthorizationError:
            raise
        except BaseException as exc:
            self.last_status = f"Resource load failed: {file_id} #{index} / {exc}"
            return None

    def _resource_image_from_asset(
        self, asset: Any, fallback_name: str
    ) -> ResourceImage | None:
        if asset is None:
            return None
        image = getattr(asset, "image", asset)
        if image is None:
            return None
        file_name = str(getattr(asset, "file_name", "") or fallback_name)
        origin_x = int(getattr(asset, "origin_x", 0) or 0)
        origin_y = int(getattr(asset, "origin_y", 0) or 0)
        status = f"{file_name}"
        self.last_status = status
        return ResourceImage(image, origin_x, origin_y, file_name, status)

    def _clone(self, image: ResourceImage | None) -> ResourceImage | None:
        if image is None:
            return None
        pil_image = image.image
        if hasattr(pil_image, "copy"):
            pil_image = pil_image.copy()
        return ResourceImage(
            pil_image, image.origin_x, image.origin_y, image.file_name, image.status
        )

    def _version_paths(
        self, version_path: str, login_folder: str, patch_folder: str,
        engine_family: str, client_folder: str = ""
    ) -> tuple[Path | None, Path | None, Path | None, tuple[Path, ...]]:
        if not version_path:
            return (None, None, None, ())
        root = Path(version_path)
        login = Path(login_folder) if login_folder else _recovered_discover_login_folder(root)
        envir = root / "Mir200" / "Envir"
        pak_txt = login / "pak.txt"
        data_dirs = self._patch_data_dir_candidates(
            root, login, patch_folder, engine_family, client_folder
        )
        data_dir = next(
            (path for path in data_dirs if path.is_dir()),
            data_dirs[0] if data_dirs else None,
        )
        pak_txt = _recovered_select_v2_pak_txt_compat(
            pak_txt, login, root, patch_folder, data_dirs, data_dir
        )
        return envir, pak_txt, data_dir, tuple(data_dirs)

    def _patch_data_dir_candidates(
        self, root: Path, login: Path, patch_folder: str, engine_family: str,
        client_folder: str = ""
    ) -> list[Path]:
        paths = []
        config_ini = login / "Config.ini"
        keys = (
            ("Resources目录", "ResourcesDir")
            if engine_family == "lf"
            else ("ResourcesDir", "Resources目录")
        )
        resource_dir = self._normalize_resource_dir(
            self._read_login_config_value(config_ini, keys)
        )

        def add(path: Path) -> None:
            self._append_unique_path(paths, path)

        add(login)
        add(login / "补丁文件夹" / "data")
        if resource_dir:
            add(login / "补丁文件夹" / resource_dir / "data")

        if patch_folder:
            patch_root = Path(patch_folder)
            add(patch_root / "data")
            if resource_dir:
                add(patch_root / resource_dir / "data")
        _recovered_append_v2_data_dir_compat_candidates(
            paths, root, login, patch_folder, resource_dir
        )
        # Restrict only when the user actually picked a client. The derived
        # 补丁文件夹 must not narrow the search by itself, or choosing a
        # project root would silently act as a client choice.
        paths = _recovered_restrict_to_client(
            paths, client_folder, resource_dir
        )
        return paths

    def _read_login_config_value(
        self, config_path: Path, keys: tuple[str, ...]
    ) -> str:
        if not config_path.is_file():
            return ""
        raw = self._read_text_guess(config_path)
        parser = configparser.ConfigParser()
        parser.optionxform = str
        try:
            parser.read_string("[root]\n" + raw)
            for key in keys:
                if parser.has_option("root", key):
                    return str(parser.get("root", key)).strip()
        except configparser.Error:
            pass
        for line in raw.splitlines():
            if "=" not in line:
                continue
            name, value = line.split("=", 1)
            if name.strip() in keys:
                return value.strip()
        return ""

    def _read_text_guess(self, path: Path) -> str:
        data = path.read_bytes()
        for encoding in ("utf-8-sig", "gb18030", "gbk", "utf-16"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")

    def _normalize_resource_dir(self, value: str) -> str:
        text = str(value or "").strip().strip('"\'')
        if not text:
            return ""
        normalized = str(PureWindowsPath(text)).strip("\\/")
        if not normalized or normalized == ".":
            return ""
        if Path(normalized).is_absolute():
            _drive, tail = PureWindowsPath(normalized).drive, str(
                PureWindowsPath(normalized)
            ).split(":", 1)[-1]
            normalized = tail.strip("\\/")
        if normalized.startswith(".."):
            return ""
        return normalized

    def _append_unique_path(self, paths: list[Path], path: Path) -> None:
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path.absolute()
        for item in paths:
            try:
                if item.resolve() == resolved:
                    return None
            except OSError:
                if item.absolute() == resolved:
                    return None
        paths.append(path)
        return None

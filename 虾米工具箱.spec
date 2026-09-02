# -*- mode: python ; coding: utf-8 -*-

import os
import sys
import _sqlite3
from PyInstaller.utils.hooks import collect_data_files, collect_submodules


ROOT_DIR = os.path.abspath(SPECPATH)
HOOKS_DIR = [os.path.join(ROOT_DIR, "pyinstaller_hooks"), os.path.dirname(ROOT_DIR)]
EMBEDDED_XIAMI_DIR = os.path.join(ROOT_DIR, "embedded_xiami")
if EMBEDDED_XIAMI_DIR not in sys.path:
    sys.path.insert(0, EMBEDDED_XIAMI_DIR)
if HOOKS_DIR[0] not in sys.path:
    sys.path.insert(0, HOOKS_DIR[0])

from xiami_embedded_packaging import (
    MICRO_RELEASE_ALLOWLIST,
    RESOURCE_RELEASE_ALLOWLIST,
    assert_no_forbidden_embedded_datas,
    assert_no_embedded_python_datas,
    assert_release_datas,
    collect_allowlisted_datas,
    collect_non_python_datas,
    discover_bundled_plugins,
    write_bundled_plugin_manifest,
)


APP_NAME = "\u867e\u7c73\u5de5\u5177\u7bb1"
MAIN_SCRIPT = os.path.join(ROOT_DIR, "\u5de5\u5177\u7bb1_qt.py")
ICON_FILE = os.path.join(ROOT_DIR, "resources", "222.ico")
VERSION_INFO_FILE = os.path.join(ROOT_DIR, "xiami_toolbox_version_info.txt")
NATIVE_CORE_FILE = os.path.join(ROOT_DIR, "build", "native_core", "xiami_native_core.exe")
SQLITE3_DLL_FILE = os.path.join(os.path.dirname(_sqlite3.__file__), "sqlite3.dll")
if not os.path.isfile(VERSION_INFO_FILE):
    raise RuntimeError("Windows version information file is missing: " + VERSION_INFO_FILE)
if not os.path.isfile(NATIVE_CORE_FILE):
    raise RuntimeError("Native core executable is missing; run scripts\\build_native_core.ps1 first")
if not os.path.isfile(SQLITE3_DLL_FILE):
    raise RuntimeError("SQLite runtime DLL is missing: " + SQLITE3_DLL_FILE)

datas = []
datas += collect_data_files("embedded_npc_visual", includes=["**/*.csv"])
resources_dir = os.path.join(ROOT_DIR, "resources")
datas += collect_allowlisted_datas(resources_dir, "resources", RESOURCE_RELEASE_ALLOWLIST)

brand_asset = os.path.join(ROOT_DIR, "outputs", "ui-assets", "brand-v2", "xiami-brand-v2-a.png")
if os.path.isfile(brand_asset):
    datas.append((brand_asset, os.path.join("outputs", "ui-assets", "brand-v2")))

micro_dir = os.path.join(ROOT_DIR, "\u5fae\u7aef\u914d\u7f6e\u76ee\u5f55")
datas += collect_allowlisted_datas(
    micro_dir,
    "\u5fae\u7aef\u914d\u7f6e\u76ee\u5f55",
    MICRO_RELEASE_ALLOWLIST,
)

NON_RELEASE_PLUGIN_IDS = {"compat_echo", "echo", "error_history_case"}
EXCLUDED_EMBEDDED_DATA_PREFIXES = (
    "embedded_xiami/runtime/xiami_v1/kernels/",
)
bundled_xiami_plugins = []
if os.path.isdir(EMBEDDED_XIAMI_DIR):
    datas += collect_non_python_datas(EMBEDDED_XIAMI_DIR, "embedded_xiami")
    datas = [
        entry
        for entry in datas
        if not any(
            (os.path.join(str(entry[1]), os.path.basename(str(entry[0])))
             .replace("\\", "/")
             .lower() + "/").startswith(prefix)
            for prefix in EXCLUDED_EMBEDDED_DATA_PREFIXES
        )
    ]
    bundled_xiami_plugins = [
        plugin
        for plugin in discover_bundled_plugins(os.path.join(EMBEDDED_XIAMI_DIR, "xiami_plugins"))
        if str(plugin.get("id") or "") not in NON_RELEASE_PLUGIN_IDS
    ]
    bundled_manifest = write_bundled_plugin_manifest(
        os.path.join(workpath, "embedded_xiami", "bundled_plugins.json"),
        bundled_xiami_plugins,
    )
    datas.append((bundled_manifest, "embedded_xiami"))
    for plugin in bundled_xiami_plugins:
        datas.append((bundled_manifest, os.path.join("embedded_xiami", "xiami_plugins", plugin["id"])))

assert_no_embedded_python_datas(datas)
assert_no_forbidden_embedded_datas(datas)
assert_release_datas(datas)
bundled_kernel_datas = [
    entry
    for entry in datas
    if (os.path.join(str(entry[1]), os.path.basename(str(entry[0])))
        .replace("\\", "/")
        .lower() + "/").startswith(EXCLUDED_EMBEDDED_DATA_PREFIXES)
]
if bundled_kernel_datas:
    raise RuntimeError("QQ/NapCat kernel environment leaked into release datas")

def is_release_xiami_module(name):
    parts = str(name or "").split(".")
    return not any(
        part == "tests"
        or part == "test"
        or part.startswith("test_")
        or part.endswith("_smoke")
        for part in parts
    )


def is_non_release_plugin_module(name):
    value = str(name or "")
    return any(
        value == "xiami_plugins." + plugin_id
        or value.startswith("xiami_plugins." + plugin_id + ".")
        for plugin_id in NON_RELEASE_PLUGIN_IDS
    )


xiami_core_modules = collect_submodules("xiami_core")
xiami_hiddenimports = [
    name for name in xiami_core_modules
    if is_release_xiami_module(name)
]
non_release_xiami_modules = [
    name for name in xiami_core_modules
    if not is_release_xiami_module(name)
]
xiami_hiddenimports += [str(plugin["module"]) for plugin in bundled_xiami_plugins]
SERVER_ONLY_MODULE_PREFIXES = (
    "embedded_npc_visual.core.npc_visual_v2.parser",
    "embedded_npc_visual.core.npc_visual_v2.runtime",
    "embedded_npc_visual.core.npc_preview.npc_dialog_core",
    "embedded_npc_visual.core.npc_preview.mir_npc",
    "embedded_npc_visual.core.npc_preview.pak_loader",
    "embedded_npc_visual.core.npc_preview.recovered_asset_reader",
    "embedded_npc_visual.core.npc_preview.recovered_geepak_codec",
    "embedded_npc_visual.core.npc_preview.recovered_gameofmir_codec",
)


def is_server_only_module(name):
    return any(
        name == prefix or name.startswith(prefix + ".")
        for prefix in SERVER_ONLY_MODULE_PREFIXES
    )


embedded_npc_modules = collect_submodules("embedded_npc_visual")
embedded_npc_hiddenimports = [
    name for name in embedded_npc_modules
    if not is_server_only_module(name)
]
server_only_modules = sorted(
    set(SERVER_ONLY_MODULE_PREFIXES).union(
        non_release_xiami_modules,
        {name for name in embedded_npc_modules if is_server_only_module(name)},
    )
)

a = Analysis(
    [MAIN_SCRIPT],
    pathex=[ROOT_DIR],
    binaries=[
        (NATIVE_CORE_FILE, "native"),
        (SQLITE3_DLL_FILE, "native"),
    ],
    datas=datas,
    hiddenimports=["PySide2", "PySide2.QtCore", "PySide2.QtGui", "PySide2.QtWidgets"] + collect_submodules("asyncio") + collect_submodules("html") + embedded_npc_hiddenimports + xiami_hiddenimports,
    hookspath=HOOKS_DIR,
    hooksconfig={},
    runtime_hooks=[
        os.path.join(ROOT_DIR, "pyinstaller_hooks", "runtime_crash_logging.py"),
        os.path.join(ROOT_DIR, "pyinstaller_hooks", "runtime_embedded_xiami.py"),
    ],
    excludes=sorted(server_only_modules),
    noarchive=False,
    optimize=0,
)

analysis_module_names = {
    entry[0]
    for entry in a.pure
    if isinstance(entry, (tuple, list)) and entry and isinstance(entry[0], str)
}
forbidden_analysis_modules = sorted(
    name for name in analysis_module_names if is_server_only_module(name)
)
if forbidden_analysis_modules:
    raise RuntimeError(
        "Server-only NPC modules leaked into PyInstaller Analysis.pure: "
        + ", ".join(forbidden_analysis_modules)
    )

forbidden_test_modules = sorted(
    name for name in analysis_module_names
    if (name.startswith("xiami_core.") and not is_release_xiami_module(name))
    or is_non_release_plugin_module(name)
)
if forbidden_test_modules:
    raise RuntimeError(
        "Test/smoke modules leaked into PyInstaller Analysis.pure: "
        + ", ".join(forbidden_test_modules)
    )

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[ICON_FILE],
    version=VERSION_INFO_FILE,
    contents_directory=".",
    append_pkg=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)

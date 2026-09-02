from __future__ import annotations

import io
import pathlib
import sys
import tempfile
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import toolbox_update as update


class _FakeInfo:
    def __init__(self, name: str, file_size: int, compressed_size: int) -> None:
        self.filename = name
        self.file_size = file_size
        self.compress_size = compressed_size
        self.flag_bits = 0
        self.external_attr = 0

    def is_dir(self) -> bool:
        return False


class _FakeArchive:
    def __init__(self, info: _FakeInfo, payload: bytes) -> None:
        self.info = info
        self.payload = payload

    def infolist(self):
        return [self.info]

    def open(self, _info, _mode="r"):
        return io.BytesIO(self.payload)


def _expect_runtime_error(callable_obj, marker: str) -> None:
    try:
        callable_obj()
    except RuntimeError as exc:
        assert marker in str(exc), str(exc)
    else:
        raise AssertionError("expected RuntimeError containing {!r}".format(marker))


def _probe_main_executable_selection(root: pathlib.Path) -> None:
    root.mkdir(parents=True)
    native = root / "native"
    native.mkdir()
    (native / "xiami_native_core.exe").write_bytes(b"MZ-native")
    preferred = ["虾米工具箱.exe", "XiamiToolbox.exe"]
    assert update.find_exe_in_dir(str(root), preferred) == ""

    nested = root / "nested"
    nested.mkdir()
    (nested / "虾米工具箱.exe").write_bytes(b"MZ-nested")
    assert update.find_exe_in_dir(str(root), preferred) == ""

    main = root / "虾米工具箱.exe"
    main.write_bytes(b"MZ-main")
    assert pathlib.Path(update.find_exe_in_dir(str(root), preferred)) == main.resolve()


def _probe_zip_limits(root: pathlib.Path) -> None:
    root.mkdir(parents=True)
    valid_zip = root / "valid.zip"
    with zipfile.ZipFile(str(valid_zip), "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("虾米工具箱/虾米工具箱.exe", b"MZ-main")
        archive.writestr("虾米工具箱/data/value.txt", b"value")
    extract_root = root / "valid-extract"
    with zipfile.ZipFile(str(valid_zip), "r") as archive:
        update.safe_extract_zip(archive, str(extract_root))
    assert (extract_root / "虾米工具箱" / "虾米工具箱.exe").read_bytes() == b"MZ-main"

    old_entries = update.MAX_UPDATE_ZIP_ENTRIES
    old_total = update.MAX_UPDATE_ZIP_EXPANDED_BYTES
    old_entry = update.MAX_UPDATE_ZIP_ENTRY_BYTES
    old_ratio = update.MAX_UPDATE_ZIP_COMPRESSION_RATIO
    old_ratio_min = update._UPDATE_ZIP_RATIO_MIN_BYTES
    try:
        update.MAX_UPDATE_ZIP_ENTRIES = 1
        with zipfile.ZipFile(str(valid_zip), "r") as archive:
            _expect_runtime_error(
                lambda: update._validate_zip_archive(archive, str(root / "entries")),
                "文件数量",
            )

        update.MAX_UPDATE_ZIP_ENTRIES = old_entries
        update.MAX_UPDATE_ZIP_EXPANDED_BYTES = 4
        _expect_runtime_error(
            lambda: update._validate_zip_archive(
                _FakeArchive(_FakeInfo("payload.bin", 5, 5), b"12345"),
                str(root / "total"),
            ),
            "展开总量",
        )

        update.MAX_UPDATE_ZIP_EXPANDED_BYTES = old_total
        update.MAX_UPDATE_ZIP_ENTRY_BYTES = 4
        _expect_runtime_error(
            lambda: update._validate_zip_archive(
                _FakeArchive(_FakeInfo("payload.bin", 5, 5), b"12345"),
                str(root / "entry"),
            ),
            "超大单文件",
        )

        update.MAX_UPDATE_ZIP_ENTRY_BYTES = old_entry
        update.MAX_UPDATE_ZIP_COMPRESSION_RATIO = 2
        update._UPDATE_ZIP_RATIO_MIN_BYTES = 1
        _expect_runtime_error(
            lambda: update._validate_zip_archive(
                _FakeArchive(_FakeInfo("payload.bin", 10, 1), b"1234567890"),
                str(root / "ratio"),
            ),
            "压缩比异常",
        )

        update.MAX_UPDATE_ZIP_COMPRESSION_RATIO = old_ratio
        update._UPDATE_ZIP_RATIO_MIN_BYTES = old_ratio_min
        _expect_runtime_error(
            lambda: update.safe_extract_zip(
                _FakeArchive(_FakeInfo("payload.bin", 3, 3), b"123456"),
                str(root / "stream"),
            ),
            "实际展开尺寸",
        )

        _expect_runtime_error(
            lambda: update._validate_zip_archive(
                _FakeArchive(_FakeInfo("payload.bin:stream", 1, 1), b"x"),
                str(root / "ads"),
            ),
            "Windows 特殊路径",
        )
        _expect_runtime_error(
            lambda: update._validate_zip_archive(
                _FakeArchive(_FakeInfo("AUX.txt", 1, 1), b"x"),
                str(root / "reserved"),
            ),
            "Windows 保留路径",
        )
    finally:
        update.MAX_UPDATE_ZIP_ENTRIES = old_entries
        update.MAX_UPDATE_ZIP_EXPANDED_BYTES = old_total
        update.MAX_UPDATE_ZIP_ENTRY_BYTES = old_entry
        update.MAX_UPDATE_ZIP_COMPRESSION_RATIO = old_ratio
        update._UPDATE_ZIP_RATIO_MIN_BYTES = old_ratio_min


def _probe_atomic_update_commands() -> None:
    keep_files, keep_dirs = update.update_keep_paths("toolbox")
    expected_qq_runtime_dirs = {
        "embedded_xiami\\runtime\\xiami_v1",
        "_internal\\embedded_xiami\\runtime\\xiami_v1",
        "runtime\\xiami_v1",
    }
    assert expected_qq_runtime_dirs.issubset(set(keep_dirs)), keep_dirs
    pre_keep, post_keep = update.build_keep_commands(
        keep_files,
        keep_dirs,
        restore_root_var="NEW",
    )
    commands = update._build_atomic_install_commands(
        pre_keep,
        post_keep,
        update.update_retired_paths("toolbox"),
        full_payload=True,
        success_commands=["rem state-written-after-swap"],
    )
    script = "\n".join(commands)
    assert 'robocopy "%SRC%" "%NEW%" /MIR' in script
    assert 'robocopy "%SRC%" "%DST%"' not in script
    assert 'move "%DST%" "%OLD%"' in script
    assert 'move "%NEW%" "%DST%"' in script
    assert 'cd /d "%DST%\\.."' in script
    assert ':swap_target_failed' in script
    assert 'move "%OLD%" "%DST%"' in script
    assert "%NEW%\\resources\\free_micro_client\\PasswordWorker.ps1" in script
    restored = [line for line in post_keep if " copy " in line or "robocopy " in line]
    assert restored and all("%NEW%" in line for line in restored)
    for runtime_dir in expected_qq_runtime_dirs:
        assert any(runtime_dir in line for line in pre_keep), runtime_dir
        assert any(runtime_dir in line for line in post_keep), runtime_dir

    overlay = "\n".join(
        update._build_atomic_install_commands(
            [],
            [],
            update.update_retired_paths("toolbox"),
            full_payload=False,
            success_commands=[],
        )
    )
    assert 'robocopy "%DST%" "%NEW%" /MIR' in overlay
    assert 'robocopy "%SRC%" "%NEW%" /E' in overlay


def _probe_plugin_config_discovery(root: pathlib.Path) -> None:
    normal = root / "embedded_xiami" / "xiami_plugins" / "invites"
    internal = root / "_internal" / "embedded_xiami" / "xiami_plugins" / "cards"
    ignored = root / "embedded_xiami" / "xiami_plugins" / "ignored"
    normal.mkdir(parents=True)
    internal.mkdir(parents=True)
    ignored.mkdir(parents=True)
    (normal / "plugin_config.json").write_text('{"points": 8}', encoding="utf-8")
    (internal / "plugin_config.json").write_text('{"cost": 10}', encoding="utf-8")
    (ignored / "plugin.py").write_text("VALUE = 1", encoding="utf-8")
    found = set(update.discover_update_plugin_config_paths(str(root)))
    assert found == {
        "embedded_xiami\\xiami_plugins\\invites\\plugin_config.json",
        "_internal\\embedded_xiami\\xiami_plugins\\cards\\plugin_config.json",
    }, found


def _probe_work_base_outside_install(root: pathlib.Path) -> None:
    install_dir = root / "install"
    install_dir.mkdir(parents=True)
    original_update_base_dir = update.update_base_dir
    try:
        update.update_base_dir = lambda _app: str(install_dir / ".xiami_update")
        work_base = pathlib.Path(
            update._choose_update_work_base_dir("toolbox", str(install_dir))
        ).resolve()
    finally:
        update.update_base_dir = original_update_base_dir
    assert install_dir.resolve() not in (work_base, *work_base.parents)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="xiami-update-safety-") as temporary:
        root = pathlib.Path(temporary)
        _probe_main_executable_selection(root / "exe")
        _probe_zip_limits(root / "zip")
        _probe_plugin_config_discovery(root / "plugin-configs")
        _probe_work_base_outside_install(root / "work-base")
    _probe_atomic_update_commands()
    print("update install safety probe: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

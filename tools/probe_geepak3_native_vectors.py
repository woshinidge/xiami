from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
CODEC_CPP = ROOT / "native" / "core_worker" / "xiami_geepak3_codec.cpp"

VECTORS = {
    "V8M2": {
        "key_sha256": "1ae6b6e84c10736297d44839f08d8c8cec82c134a7ad05aaaed9404b05cab4b8",
        "header_cipher": "74c3c54df8c24cb3e0ccfc646028b1b01c5e52d7587a86ccdb5f8b34b9a968bb",
        "image_key_0": "4754f40a054100007faefc0cef632255",
        "image_key_63": "175fdce700202040aa8f2192cbc84802",
        "resource_cipher_0": "d471f86c93319b648e9a57d7cd35e042",
        "directory_0": "ec950470",
        "directory_64": "ec9504f0",
    },
    "123456": {
        "key_sha256": "23f9157762f976de514b512aa1d7341e4fc84bebd94ccc08cec44b9bbe679f66",
        "header_cipher": "0280a904fe0283139c09e05d8fe2983da29afbc9c969296d6cb756941477fe73",
        "image_key_0": "756fa1670101800038d76fb1ee6150fa",
        "image_key_63": "be958fb720402020307391820d4b418b",
        "resource_cipher_0": "8f844cab786cb337ceea8ee5ce5dcd7b",
        "directory_0": "659c87b6",
        "directory_64": "659c8736",
    },
}

HARNESS = r'''
#include "xiami_geepak3_codec.hpp"

#include <algorithm>
#include <array>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>

template <typename Range>
std::string hex(const Range& value) {
    std::ostringstream output;
    output << std::hex << std::setfill('0');
    for (const auto byte : value) output << std::setw(2) << static_cast<unsigned int>(byte);
    return output.str();
}

int main() {
    for (const std::string password : {std::string("V8M2"), std::string("123456")}) {
        xiami::geepak3::Bytes password_bytes(password.begin(), password.end());
        const auto material = xiami::geepak3::derive_key_material(password_bytes);
        xiami::geepak3::AesKey header_key{};
        std::copy_n(material.key_block.begin(), header_key.size(), header_key.begin());
        xiami::geepak3::Bytes plain(32);
        for (std::size_t index = 0; index < plain.size(); ++index) plain[index] = static_cast<unsigned char>(index);
        const auto header_cipher = xiami::geepak3::aes_ctr_crypt(header_key, plain);

        xiami::geepak3::ResourceHeader resource_plain{};
        for (std::size_t index = 0; index < resource_plain.size(); ++index) {
            resource_plain[index] = static_cast<unsigned char>(index);
        }
        const xiami::geepak3::Bytes resource_input(resource_plain.begin(), resource_plain.end());
        const auto resource_cipher_bytes = xiami::geepak3::aes_ctr_crypt(
            xiami::geepak3::resource_header_key(material.words, 0), resource_input);
        xiami::geepak3::ResourceHeader resource_cipher{};
        std::copy(resource_cipher_bytes.begin(), resource_cipher_bytes.end(), resource_cipher.begin());
        if (xiami::geepak3::decode_resource_header(resource_cipher, material.words, 0) != resource_plain) {
            std::cerr << "resource header roundtrip failed" << std::endl;
            return 2;
        }

        std::cout << password << '|'
                  << hex(material.key_block) << '|'
                  << hex(header_cipher) << '|'
                  << hex(xiami::geepak3::resource_header_key(material.words, 0)) << '|'
                  << hex(xiami::geepak3::resource_header_key(material.words, 63)) << '|'
                  << hex(resource_cipher_bytes) << '|'
                  << std::hex << std::setw(8) << std::setfill('0')
                  << xiami::geepak3::decode_directory_offset(0x11223344U, 0U, material.words) << '|'
                  << std::hex << std::setw(8) << std::setfill('0')
                  << xiami::geepak3::decode_directory_offset(0x11223384U, 64U, material.words)
                  << std::endl;
    }
    return 0;
}
'''


def _vcvars64() -> Path:
    program_files_x86 = os.environ.get("ProgramFiles(x86)")
    if not program_files_x86:
        raise RuntimeError("ProgramFiles(x86) is unavailable")
    vswhere = Path(program_files_x86) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    if not vswhere.is_file():
        raise RuntimeError(f"vswhere.exe is unavailable: {vswhere}")
    result = subprocess.run(
        [
            str(vswhere),
            "-latest",
            "-products",
            "*",
            "-requires",
            "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
            "-property",
            "installationPath",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    installation = result.stdout.strip().splitlines()[0]
    path = Path(installation) / "VC" / "Auxiliary" / "Build" / "vcvars64.bat"
    if not path.is_file():
        raise RuntimeError(f"vcvars64.bat is unavailable: {path}")
    return path


def _compile(temp_dir: Path) -> Path:
    harness = temp_dir / "geepak3_vector_harness.cpp"
    executable = temp_dir / "geepak3_vector_harness.exe"
    harness.write_text(HARNESS, encoding="ascii")
    arguments = [
        "cl.exe",
        "/nologo",
        "/std:c++17",
        "/EHsc",
        "/W4",
        "/WX",
        f"/I{CODEC_CPP.parent}",
        str(CODEC_CPP),
        str(harness),
        f"/Fe:{executable}",
        "/link",
        "bcrypt.lib",
    ]
    build_command = temp_dir / "build_geepak3_probe.cmd"
    build_command.write_text(
        f'@echo off\nchcp 65001 >nul\ncall "{_vcvars64()}" >nul\n{subprocess.list2cmdline(arguments)}\n',
        encoding="utf-8",
    )
    result = subprocess.run(
        [os.environ.get("ComSpec", "cmd.exe"), "/d", "/c", str(build_command)],
        cwd=temp_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(f"native GEEPAK3 probe compilation failed:\n{result.stdout}\n{result.stderr}")
    return executable


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="xiami-geepak3-probe-") as raw_temp:
        executable = _compile(Path(raw_temp))
        result = subprocess.run([str(executable)], check=True, capture_output=True, text=True)

    observed = {}
    for line in result.stdout.splitlines():
        fields = line.strip().split("|")
        if len(fields) != 8:
            raise RuntimeError(f"unexpected native GEEPAK3 vector row: {line!r}")
        password, key_block, header_cipher, image_key_0, image_key_63, resource_cipher_0, directory_0, directory_64 = fields
        observed[password] = {
            "key_sha256": hashlib.sha256(bytes.fromhex(key_block)).hexdigest(),
            "header_cipher": header_cipher,
            "image_key_0": image_key_0,
            "image_key_63": image_key_63,
            "resource_cipher_0": resource_cipher_0,
            "directory_0": directory_0,
            "directory_64": directory_64,
        }

    if observed != VECTORS:
        raise AssertionError(f"native GEEPAK3 vector mismatch:\nexpected={VECTORS!r}\nobserved={observed!r}")
    print("native GEEPAK3 vectors: PASS (V8M2, 123456)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

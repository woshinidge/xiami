#include "xiami_mir_palette.hpp"

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <wincrypt.h>

#include <stdexcept>
#include <vector>

namespace xiami::mir_palette {
namespace {

constexpr char kPaletteBase64[] =
    "AAAAAIAAAP8AgAD/gIAA/wAAgP+AAID/AICA/8DAwP9VgJf/nbnI/3tzc/8tKSn/WlJS/2NaWv9COTn/HRgY/xgQEP8pGBj/EAgI//J5cf/hZ1///1pa//8xMf/WWlL/lBAA/5QpGP85CAD/cxAA/7UYAP+9Y1L/QhgQ//+qmf9aEAD/czkp/6VKMf+Ue3P/vVIx/1IhEP97MRj/LRgQ/4xKMf+UKQD/vTEA/8ZzUv9rMRj/xmtC/85KAP+lYzn/WjEY/yoQAP8VCAD/OhgA/wgAAP8pAAD/SgAA/50AAP/cAAD/3gAA//sAAP+cc1L/lGtK/3NKKf9SMRj/jEoY/4hEEf9KIQD/IRgQ/9aUWv/GayH/72sA//93AP+llIT/QjEh/xgQCP8pGAj/IRAA/zkpGP+MYzn/QikQ/2tCGP97Shj/lEoA/4yEe/9rY1r/SkI5/ykhGP9GOSn/taWU/3trWv/OsZT/pYxz/4xzWv+1lHP/1qVz/++lSv/vxoz/e2NC/2tWOf+9lFr/YzkA/9bGrf9SQin/lGMY/+/Wrf+ljGP/Y1pK/72le/9aQhj/vYwx/zUxKf+UhGP/e2tK/6WMWv9aSin/nHs5/0IxEP/vrSH/GBAA/ykhAP+cawD/lIRa/1JCGP9rWin/e2Mh/5x7If/epQD/WlI5/zEpEP/OvXv/Y1o5/5SESv/GpSn/EJwY/0KMSv8xjEL/EJQp/wgYEP8IGBj/CCkQ/xhCKf+lta3/a3Nz/xgpKf8YQkr/MUJK/2PG3v9E3f//jNbv/3NrOf/33jn/9++M//fnAP9ra1r/Woyl/zm17/9KnM7/MYS1/zFSa//e3tb/vb21/4yMhP/3997/AAgY/wgYOf8IECn/CBgA/wgpAP8AUqX/AHve/xApSv8QOWv/EFKM/yFapf8QMVr/EEKE/zFShP8YITH/Slp7/1Jrpf8pOWP/EEre/ykpIf9KSjn/KSkY/0pKKf97e0L/nJxK/1paKf9CQhT/OTkA/1lZAP/KNSz/a3Mh/ykxAP8xORD/MTkY/0JKAP9SYxj/WnMp/zFKGP8YIQD/GDEA/xg5EP9jhEr/a71K/2O1Sv9jvUr/WpxK/0qMOf9jxkr/Y9ZK/1KESv8xcyn/Y8Za/1K9Sv8Q/wD/GCkY/0qISv9K50r/AFoA/wCIAP8AlAD/AN4A/wDuAP8A+wD/SlqU/2Nztf97jNb/a3vW/3eI///Gxs7/lJSc/5yUxv8xMTn/KRiE/xgAhP9KQlL/UkJ7/2Nac//Otff/jHuc/3cizP/dqv//8LQq/98An//jF7P///vw/6CgpP+AgID//wAA/wD/AP///wD/AAD///8A//8A/////////w==";

std::array<Color, 256> decode() {
    DWORD size = 0;
    if (!CryptStringToBinaryA(kPaletteBase64, 0, CRYPT_STRING_BASE64, nullptr, &size, nullptr, nullptr) || size != 1024U) {
        throw std::runtime_error("MIR palette metadata is invalid");
    }
    std::vector<unsigned char> raw(size);
    if (!CryptStringToBinaryA(kPaletteBase64, 0, CRYPT_STRING_BASE64, raw.data(), &size, nullptr, nullptr) || size != raw.size()) {
        throw std::runtime_error("MIR palette decode failed");
    }
    std::array<Color, 256> result{};
    for (std::size_t index = 0; index < result.size(); ++index) {
        result[index] = {raw[index * 4U], raw[index * 4U + 1U], raw[index * 4U + 2U], raw[index * 4U + 3U]};
    }
    return result;
}

}  // namespace

const std::array<Color, 256>& rgba() {
    static const auto value = decode();
    return value;
}

}  // namespace xiami::mir_palette

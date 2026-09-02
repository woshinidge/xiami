#include "xiami_asset_decoder.hpp"

#include <array>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>

namespace {

constexpr std::uint8_t kZlibData[] = {
    0x78, 0x9c, 0xed, 0xc9, 0xb1, 0x09, 0x00, 0x20, 0x0c, 0x00, 0xc1, 0x55,
    0x32, 0x56, 0x0a, 0x9b, 0x08, 0x11, 0x02, 0x1a, 0x45, 0xc4, 0xf9, 0xdd,
    0x43, 0xfe, 0xda, 0xd3, 0xb0, 0x11, 0x92, 0x76, 0xe2, 0xba, 0x44, 0xb6,
    0x6e, 0xc7, 0x65, 0xed, 0x59, 0xbd, 0xa4, 0x72, 0x1c, 0xc7, 0x71, 0x1c,
    0xc7, 0x71, 0x1c, 0xc7, 0x71, 0xf3, 0x97, 0x7b, 0x0e, 0xde, 0x52, 0x4c,
};

void put_u16(std::array<std::uint8_t, 16>* header, std::size_t offset, std::uint16_t value) {
    (*header)[offset] = static_cast<std::uint8_t>(value);
    (*header)[offset + 1U] = static_cast<std::uint8_t>(value >> 8U);
}

void put_u32(std::array<std::uint8_t, 16>* header, std::size_t offset, std::uint32_t value) {
    for (unsigned int i = 0; i < 4U; ++i) {
        (*header)[offset + i] = static_cast<std::uint8_t>(value >> (i * 8U));
    }
}

}  // namespace

int main() {
    const auto path = std::filesystem::temp_directory_path() / "xiami-native-frame-scan-probe.pak";
    std::array<std::uint8_t, 16> header{};
    header[0] = 0x62; header[1] = 0xAD; header[2] = 0x43; header[3] = 0xD9;
    put_u16(&header, 4, static_cast<std::uint16_t>(28U ^ 16046U));
    put_u16(&header, 6, static_cast<std::uint16_t>(128U ^ 3041U));
    put_u16(&header, 8, static_cast<std::uint16_t>(static_cast<std::uint16_t>(-3) ^ 36751U));
    put_u16(&header, 10, static_cast<std::uint16_t>(4U ^ 36751U));
    put_u32(&header, 12, static_cast<std::uint32_t>(sizeof(kZlibData)) ^ 2408550287U);
    {
        std::ofstream output(path, std::ios::binary);
        output.write(reinterpret_cast<const char*>(header.data()), header.size());
        output.write(reinterpret_cast<const char*>(kZlibData), sizeof(kZlibData));
    }

    try {
        xiami::asset_decoder::Profile profile;
        profile.path = path.string();
        profile.magic = "GOMPACK";
        profile.format_version = "frame-scan-v1";
        const auto index = xiami::asset_decoder::load_index(profile);
        if (index.records.size() != 1U || index.records[0].pixel_format != "gray8") {
            throw std::runtime_error("frame index mismatch");
        }
        const auto image = xiami::asset_decoder::decode_image(profile, index.records[0]);
        if (image.width != 28U || image.height != 128U || image.origin_x != -3 || image.origin_y != 4 ||
            image.bgra.size() != 28U * 128U * 4U || image.bgra[0] != 'X' ||
            image.bgra[1] != 'X' || image.bgra[2] != 'X' || image.bgra[3] != 255U) {
            throw std::runtime_error("frame BGRA mismatch");
        }
    } catch (const std::exception& exception) {
        std::filesystem::remove(path);
        std::cerr << "native frame scan probe failed: " << exception.what() << '\n';
        return 1;
    }
    std::filesystem::remove(path);
    std::cout << "native frame scan probe: PASS\n";
    return 0;
}

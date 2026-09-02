#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace xiami::asset_decoder {

struct Profile {
    std::string path;
    std::string password;
    std::string header_password;
    std::string magic;
    std::string format_version;
    std::uint32_t prefix_size = 0;
    std::uint32_t data_base = 0;
};

struct Record {
    std::uint32_t index = 0;
    std::string pixel_format;
    std::uint32_t offset = 0;
    std::uint32_t data_offset = 0;
    std::uint32_t data_length = 0;
    std::int32_t width = 0;
    std::int32_t height = 0;
    std::int32_t origin_x = 0;
    std::int32_t origin_y = 0;
    std::uint8_t image_type = 0;
    std::uint8_t alpha = 0;
    std::uint32_t packed_size = 0;
};

struct Index {
    std::string magic;
    std::vector<Record> records;
};

struct Image {
    std::uint32_t width = 0;
    std::uint32_t height = 0;
    std::uint32_t stride = 0;
    std::int32_t origin_x = 0;
    std::int32_t origin_y = 0;
    std::vector<unsigned char> bgra;
};

Index load_index(const Profile& profile);
Index load_wil_index(const Profile& data_profile, const Profile& index_profile);
Image decode_image(const Profile& profile, const Record& record, bool transparent_zero = true);

}  // namespace xiami::asset_decoder

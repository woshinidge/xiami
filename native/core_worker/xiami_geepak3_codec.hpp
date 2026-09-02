#pragma once

#include <array>
#include <cstdint>
#include <vector>

namespace xiami::geepak3 {

using Bytes = std::vector<unsigned char>;
using AesKey = std::array<unsigned char, 16>;
using ResourceHeader = std::array<unsigned char, 16>;
using KeyWords = std::array<std::uint32_t, 64>;

struct KeyMaterial {
    std::array<unsigned char, 256> key_block{};
    KeyWords words{};
};

KeyMaterial derive_key_material(const Bytes& password);
Bytes aes_ctr_crypt(const AesKey& key, const Bytes& data);
std::uint32_t decode_directory_offset(
    std::uint32_t encoded_offset,
    std::uint32_t index,
    const KeyWords& key_words);
AesKey resource_header_key(const KeyWords& key_words, std::uint32_t index);
ResourceHeader decode_resource_header(
    const ResourceHeader& encrypted_header,
    const KeyWords& key_words,
    std::uint32_t index);

}  // namespace xiami::geepak3

#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace xiami::compression {

enum class StreamFormat {
    kZlib,
    kRawDeflate,
};

// Inflates a complete memory buffer while enforcing a hard output limit.
// expected_output_size may be zero when the format does not carry that value.
bool inflate(
    const std::uint8_t* compressed,
    std::size_t compressed_size,
    StreamFormat format,
    std::size_t expected_output_size,
    std::size_t max_output_size,
    std::vector<std::uint8_t>* output,
    std::string* error);

inline bool inflate_zlib(
    const std::uint8_t* compressed,
    std::size_t compressed_size,
    std::size_t expected_output_size,
    std::size_t max_output_size,
    std::vector<std::uint8_t>* output,
    std::string* error) {
    return inflate(
        compressed,
        compressed_size,
        StreamFormat::kZlib,
        expected_output_size,
        max_output_size,
        output,
        error);
}

inline bool inflate_raw_deflate(
    const std::uint8_t* compressed,
    std::size_t compressed_size,
    std::size_t expected_output_size,
    std::size_t max_output_size,
    std::vector<std::uint8_t>* output,
    std::string* error) {
    return inflate(
        compressed,
        compressed_size,
        StreamFormat::kRawDeflate,
        expected_output_size,
        max_output_size,
        output,
        error);
}

}  // namespace xiami::compression


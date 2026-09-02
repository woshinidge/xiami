#include "xiami_compression.hpp"

#include <limits>
#include <new>

extern "C" {
#include "miniz_tinfl.h"
}

namespace xiami::compression {
namespace {

struct OutputContext {
    std::vector<std::uint8_t>* output = nullptr;
    std::size_t limit = 0;
    bool limit_exceeded = false;
    bool allocation_failed = false;
};

int append_output(const void* data, int length, void* user) noexcept {
    auto* context = static_cast<OutputContext*>(user);
    if (context == nullptr || context->output == nullptr || length < 0) {
        return 0;
    }

    const auto chunk_size = static_cast<std::size_t>(length);
    if (chunk_size > context->limit - context->output->size()) {
        context->limit_exceeded = true;
        return 0;
    }

    const auto* begin = static_cast<const std::uint8_t*>(data);
    try {
        context->output->insert(context->output->end(), begin, begin + chunk_size);
    } catch (const std::bad_alloc&) {
        context->allocation_failed = true;
        return 0;
    } catch (...) {
        context->allocation_failed = true;
        return 0;
    }
    return 1;
}

void set_error(std::string* error, const char* message) {
    if (error != nullptr) {
        *error = message;
    }
}

}  // namespace

bool inflate(
    const std::uint8_t* compressed,
    std::size_t compressed_size,
    StreamFormat format,
    std::size_t expected_output_size,
    std::size_t max_output_size,
    std::vector<std::uint8_t>* output,
    std::string* error) {
    if (output == nullptr) {
        set_error(error, "inflate output is null");
        return false;
    }
    output->clear();
    if (error != nullptr) {
        error->clear();
    }
    if (compressed == nullptr && compressed_size != 0) {
        set_error(error, "inflate input is null");
        return false;
    }
    if (compressed_size == 0) {
        set_error(error, "inflate input is empty");
        return false;
    }
    if (max_output_size == 0) {
        set_error(error, "inflate output limit is zero");
        return false;
    }
    if (expected_output_size > max_output_size) {
        set_error(error, "inflate expected size exceeds output limit");
        return false;
    }
    if (expected_output_size > output->max_size()) {
        set_error(error, "inflate expected size is not representable");
        return false;
    }

    try {
        if (expected_output_size != 0) {
            output->reserve(expected_output_size);
        }
    } catch (const std::bad_alloc&) {
        set_error(error, "inflate output allocation failed");
        return false;
    }

    OutputContext context{output, max_output_size, false, false};
    std::size_t consumed = compressed_size;
    const int flags = format == StreamFormat::kZlib ? TINFL_FLAG_PARSE_ZLIB_HEADER : 0;
    const int result = tinfl_decompress_mem_to_callback(
        compressed,
        &consumed,
        append_output,
        &context,
        flags);

    if (result == 0) {
        output->clear();
        if (context.limit_exceeded) {
            set_error(error, "inflate output exceeds configured limit");
        } else if (context.allocation_failed) {
            set_error(error, "inflate output allocation failed");
        } else {
            set_error(error, "inflate stream is truncated or corrupt");
        }
        return false;
    }
    if (consumed != compressed_size) {
        output->clear();
        set_error(error, "inflate stream has trailing data");
        return false;
    }
    if (expected_output_size != 0 && output->size() != expected_output_size) {
        output->clear();
        set_error(error, "inflate output size does not match record metadata");
        return false;
    }
    return true;
}

}  // namespace xiami::compression

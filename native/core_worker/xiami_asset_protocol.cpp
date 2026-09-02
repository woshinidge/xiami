#include "xiami_asset_protocol.hpp"

#include <algorithm>
#include <array>
#include <cstring>
#include <iostream>
#include <limits>
#include <stdexcept>

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>

namespace xiami::asset {
namespace {

constexpr std::array<unsigned char, 4> kMagic{{'X', 'A', 'W', '1'}};
constexpr std::size_t kHeaderBytes = 28;

std::uint16_t load_u16(const unsigned char* value) {
    return static_cast<std::uint16_t>(value[0]) |
        static_cast<std::uint16_t>(value[1]) << 8U;
}

std::uint32_t load_u32(const unsigned char* value) {
    return static_cast<std::uint32_t>(value[0]) |
        static_cast<std::uint32_t>(value[1]) << 8U |
        static_cast<std::uint32_t>(value[2]) << 16U |
        static_cast<std::uint32_t>(value[3]) << 24U;
}

std::uint64_t load_u64(const unsigned char* value) {
    std::uint64_t result = 0;
    for (unsigned int index = 0; index < 8U; ++index) {
        result |= static_cast<std::uint64_t>(value[index]) << (index * 8U);
    }
    return result;
}

void store_u16(unsigned char* target, std::uint16_t value) {
    target[0] = static_cast<unsigned char>(value);
    target[1] = static_cast<unsigned char>(value >> 8U);
}

void store_u32(unsigned char* target, std::uint32_t value) {
    for (unsigned int index = 0; index < 4U; ++index) {
        target[index] = static_cast<unsigned char>(value >> (index * 8U));
    }
}

void store_u64(unsigned char* target, std::uint64_t value) {
    for (unsigned int index = 0; index < 8U; ++index) {
        target[index] = static_cast<unsigned char>(value >> (index * 8U));
    }
}

void read_exact(std::istream& input, unsigned char* target, std::size_t size) {
    if (size > static_cast<std::size_t>(std::numeric_limits<std::streamsize>::max())) {
        throw std::runtime_error("asset frame is too large");
    }
    input.read(reinterpret_cast<char*>(target), static_cast<std::streamsize>(size));
    if (input.gcount() != static_cast<std::streamsize>(size)) {
        throw std::runtime_error("asset frame is truncated");
    }
}

bool supported_type(FrameType type) {
    switch (type) {
    case FrameType::hello:
    case FrameType::ping:
    case FrameType::pong:
    case FrameType::shutdown:
    case FrameType::shutdown_ack:
    case FrameType::error:
    case FrameType::authorize_open:
    case FrameType::challenge:
    case FrameType::authorize_commit:
    case FrameType::open_result:
    case FrameType::close_asset:
    case FrameType::close_result:
    case FrameType::stats:
    case FrameType::stats_result:
    case FrameType::list_records:
    case FrameType::records_result:
    case FrameType::decode_image:
    case FrameType::pixels_inline:
    case FrameType::release_buffer:
    case FrameType::release_result:
    case FrameType::pixels_mapping:
    case FrameType::prefetch_images:
    case FrameType::prefetch_result:
    case FrameType::build_item_tooltip:
    case FrameType::tooltip_result:
    case FrameType::open_local_tooltip:
        return true;
    default:
        return false;
    }
}

Frame response(FrameType type, std::uint64_t request_id, const std::string& text) {
    Frame frame;
    frame.type = type;
    frame.request_id = request_id;
    frame.payload = encode_text(text);
    return frame;
}

}  // namespace

Frame read_frame(std::istream& input) {
    std::array<unsigned char, kHeaderBytes> header{};
    read_exact(input, header.data(), header.size());
    if (!std::equal(kMagic.begin(), kMagic.end(), header.begin())) {
        throw std::runtime_error("asset frame magic is invalid");
    }
    const std::uint16_t version = load_u16(header.data() + 4U);
    const FrameType type = static_cast<FrameType>(load_u16(header.data() + 6U));
    const std::uint32_t flags = load_u32(header.data() + 8U);
    const std::uint64_t request_id = load_u64(header.data() + 12U);
    const std::uint64_t payload_size = load_u64(header.data() + 20U);
    if (version != kProtocolVersion || !supported_type(type)) {
        throw std::runtime_error("asset frame version or type is unsupported");
    }
    if (request_id == 0 || payload_size > kMaxControlPayloadBytes) {
        throw std::runtime_error("asset frame identifier or payload is invalid");
    }
    Frame frame;
    frame.type = type;
    frame.flags = flags;
    frame.request_id = request_id;
    frame.payload.resize(static_cast<std::size_t>(payload_size));
    if (!frame.payload.empty()) {
        read_exact(input, frame.payload.data(), frame.payload.size());
    }
    return frame;
}

void write_frame(std::ostream& output, const Frame& frame) {
    if (!supported_type(frame.type) || frame.request_id == 0 ||
        frame.payload.size() > kMaxControlPayloadBytes) {
        throw std::runtime_error("asset response frame is invalid");
    }
    std::array<unsigned char, kHeaderBytes> header{};
    std::copy(kMagic.begin(), kMagic.end(), header.begin());
    store_u16(header.data() + 4U, kProtocolVersion);
    store_u16(header.data() + 6U, static_cast<std::uint16_t>(frame.type));
    store_u32(header.data() + 8U, frame.flags);
    store_u64(header.data() + 12U, frame.request_id);
    store_u64(header.data() + 20U, static_cast<std::uint64_t>(frame.payload.size()));
    output.write(reinterpret_cast<const char*>(header.data()), static_cast<std::streamsize>(header.size()));
    if (!frame.payload.empty()) {
        output.write(
            reinterpret_cast<const char*>(frame.payload.data()),
            static_cast<std::streamsize>(frame.payload.size()));
    }
    output.flush();
    if (!output) {
        throw std::runtime_error("asset response write failed");
    }
}

std::vector<unsigned char> encode_text(const std::string& value) {
    return std::vector<unsigned char>(value.begin(), value.end());
}

std::string decode_text(const std::vector<unsigned char>& value) {
    return std::string(value.begin(), value.end());
}

int run_protocol_loop(std::istream& input, std::ostream& output, const RequestHandler& handler) {
    const std::string hello =
        std::string("protocol=1\npid=") + std::to_string(GetCurrentProcessId()) +
        "\ntransport=anonymous-pipe\npixels=inline,mapping\n";
    write_frame(output, response(FrameType::hello, 1U, hello));
    while (true) {
        const Frame request = read_frame(input);
        if (request.type == FrameType::ping) {
            write_frame(output, response(FrameType::pong, request.request_id, decode_text(request.payload)));
            continue;
        }
        if (request.type == FrameType::shutdown) {
            write_frame(output, response(FrameType::shutdown_ack, request.request_id, "ok"));
            return 0;
        }
        if (handler) {
            Frame reply = handler(request);
            if (reply.request_id == 0) {
                reply.request_id = request.request_id;
            }
            write_frame(output, reply);
            continue;
        }
        write_frame(output, response(FrameType::error, request.request_id, "unsupported request"));
    }
}

}  // namespace xiami::asset

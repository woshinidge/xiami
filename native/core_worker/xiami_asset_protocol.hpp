#pragma once

#include <cstddef>
#include <cstdint>
#include <iosfwd>
#include <functional>
#include <string>
#include <vector>

namespace xiami::asset {

constexpr std::uint16_t kProtocolVersion = 1;
constexpr std::uint64_t kMaxControlPayloadBytes = 1024U * 1024U;
constexpr std::uint64_t kMaxInlinePayloadBytes = 1024U * 1024U;

enum class FrameType : std::uint16_t {
    hello = 1,
    ping = 2,
    pong = 3,
    shutdown = 4,
    shutdown_ack = 5,
    error = 6,
    authorize_open = 10,
    challenge = 11,
    authorize_commit = 12,
    open_result = 13,
    close_asset = 14,
    close_result = 15,
    stats = 16,
    stats_result = 17,
    list_records = 20,
    records_result = 21,
    decode_image = 22,
    pixels_inline = 23,
    release_buffer = 24,
    release_result = 25,
    pixels_mapping = 26,
    prefetch_images = 27,
    prefetch_result = 28,
    build_item_tooltip = 29,
    tooltip_result = 30,
    open_local_tooltip = 31,
};

struct Frame {
    FrameType type{};
    std::uint32_t flags = 0;
    std::uint64_t request_id = 0;
    std::vector<unsigned char> payload;
};

Frame read_frame(std::istream& input);
void write_frame(std::ostream& output, const Frame& frame);
std::vector<unsigned char> encode_text(const std::string& value);
std::string decode_text(const std::vector<unsigned char>& value);
using RequestHandler = std::function<Frame(const Frame&)>;

int run_protocol_loop(std::istream& input, std::ostream& output, const RequestHandler& handler = {});

}  // namespace xiami::asset

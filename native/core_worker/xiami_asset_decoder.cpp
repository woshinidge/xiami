#include "xiami_asset_decoder.hpp"
#include "xiami_compression.hpp"
#include "xiami_geepak3_codec.hpp"
#include "xiami_mir_palette.hpp"

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <bcrypt.h>

#include <algorithm>
#include <array>
#include <filesystem>
#include <fstream>
#include <limits>
#include <stdexcept>

#pragma comment(lib, "bcrypt.lib")

namespace xiami::asset_decoder {
namespace {

using Bytes = std::vector<unsigned char>;

[[noreturn]] void fail(const char* message) { throw std::runtime_error(message); }

Bytes ansi_bytes(const std::string& value) {
    if (value.empty()) return {};
    const int wide_size = MultiByteToWideChar(
        CP_UTF8, MB_ERR_INVALID_CHARS, value.data(), static_cast<int>(value.size()), nullptr, 0);
    if (wide_size <= 0) return Bytes(value.begin(), value.end());
    std::wstring wide(static_cast<std::size_t>(wide_size), L'\0');
    if (MultiByteToWideChar(
            CP_UTF8, MB_ERR_INVALID_CHARS, value.data(), static_cast<int>(value.size()),
            wide.data(), wide_size) != wide_size) {
        return Bytes(value.begin(), value.end());
    }
    const int ansi_size = WideCharToMultiByte(
        CP_ACP, 0, wide.data(), wide_size, nullptr, 0, nullptr, nullptr);
    if (ansi_size <= 0) return Bytes(value.begin(), value.end());
    Bytes result(static_cast<std::size_t>(ansi_size));
    if (WideCharToMultiByte(
            CP_ACP, 0, wide.data(), wide_size, reinterpret_cast<char*>(result.data()),
            ansi_size, nullptr, nullptr) != ansi_size) {
        return Bytes(value.begin(), value.end());
    }
    return result;
}

std::uint16_t u16(const unsigned char* p) {
    return static_cast<std::uint16_t>(p[0]) | static_cast<std::uint16_t>(p[1]) << 8U;
}

std::uint32_t u32(const unsigned char* p) {
    return static_cast<std::uint32_t>(p[0]) |
        static_cast<std::uint32_t>(p[1]) << 8U |
        static_cast<std::uint32_t>(p[2]) << 16U |
        static_cast<std::uint32_t>(p[3]) << 24U;
}

std::int32_t i16(const unsigned char* p) { return static_cast<std::int16_t>(u16(p)); }

Bytes read_file(const std::string& path, std::uint64_t offset, std::uint64_t size) {
    std::ifstream stream(std::filesystem::u8path(path), std::ios::binary);
    if (!stream) fail("unable to open native asset");
    stream.seekg(0, std::ios::end);
    const auto file_size = static_cast<std::uint64_t>(stream.tellg());
    if (offset > file_size || size > file_size - offset || size > 128U * 1024U * 1024U) {
        fail("native asset read range is invalid");
    }
    stream.seekg(static_cast<std::streamoff>(offset), std::ios::beg);
    Bytes data(static_cast<std::size_t>(size));
    if (!data.empty()) stream.read(reinterpret_cast<char*>(data.data()), static_cast<std::streamsize>(data.size()));
    if (stream.gcount() != static_cast<std::streamsize>(data.size())) fail("native asset read is incomplete");
    return data;
}

Bytes sha1(const Bytes& input) {
    BCRYPT_ALG_HANDLE algorithm = nullptr;
    BCRYPT_HASH_HANDLE hash = nullptr;
    DWORD object_length = 0;
    DWORD written = 0;
    if (BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA1_ALGORITHM, nullptr, 0) != 0 ||
        BCryptGetProperty(algorithm, BCRYPT_OBJECT_LENGTH, reinterpret_cast<PUCHAR>(&object_length), sizeof(object_length), &written, 0) != 0) {
        if (algorithm) BCryptCloseAlgorithmProvider(algorithm, 0);
        fail("SHA1 provider is unavailable");
    }
    Bytes object(object_length);
    if (BCryptCreateHash(algorithm, &hash, object.data(), object_length, nullptr, 0, 0) != 0 ||
        BCryptHashData(hash, const_cast<PUCHAR>(input.data()), static_cast<ULONG>(input.size()), 0) != 0) {
        if (hash) BCryptDestroyHash(hash);
        BCryptCloseAlgorithmProvider(algorithm, 0);
        fail("SHA1 hashing failed");
    }
    Bytes result(20);
    if (BCryptFinishHash(hash, result.data(), static_cast<ULONG>(result.size()), 0) != 0) {
        BCryptDestroyHash(hash); BCryptCloseAlgorithmProvider(algorithm, 0); fail("SHA1 finalization failed");
    }
    BCryptDestroyHash(hash);
    BCryptCloseAlgorithmProvider(algorithm, 0);
    return result;
}

Bytes des_block(const Bytes& key, const unsigned char* block, bool encrypt) {
    if (key.size() != 8U) fail("DES key size is invalid");
    BCRYPT_ALG_HANDLE algorithm = nullptr;
    BCRYPT_KEY_HANDLE handle = nullptr;
    DWORD object_length = 0;
    DWORD written = 0;
    if (BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_3DES_ALGORITHM, nullptr, 0) != 0 ||
        BCryptGetProperty(algorithm, BCRYPT_OBJECT_LENGTH, reinterpret_cast<PUCHAR>(&object_length), sizeof(object_length), &written, 0) != 0) {
        if (algorithm) BCryptCloseAlgorithmProvider(algorithm, 0); fail("3DES provider is unavailable");
    }
    Bytes object(object_length);
    Bytes key24(24);
    std::copy(key.begin(), key.end(), key24.begin());
    std::copy(key.begin(), key.end(), key24.begin() + 8);
    std::copy(key.begin(), key.end(), key24.begin() + 16);
    if (BCryptGenerateSymmetricKey(algorithm, &handle, object.data(), object_length, key24.data(), static_cast<ULONG>(key24.size()), 0) != 0) {
        BCryptCloseAlgorithmProvider(algorithm, 0); fail("3DES key creation failed");
    }
    Bytes output(8);
    ULONG result_length = 0;
    const NTSTATUS status = encrypt
        ? BCryptEncrypt(handle, const_cast<PUCHAR>(block), 8, nullptr, nullptr, 0, output.data(), 8, &result_length, 0)
        : BCryptDecrypt(handle, const_cast<PUCHAR>(block), 8, nullptr, nullptr, 0, output.data(), 8, &result_length, 0);
    BCryptDestroyKey(handle);
    BCryptCloseAlgorithmProvider(algorithm, 0);
    if (status != 0 || result_length != 8) fail("3DES block operation failed");
    return output;
}

Bytes crypt_buffer(const Bytes& data, const std::string& password, bool decode, unsigned char iv_fill = 143) {
    Bytes pass = ansi_bytes(password);
    const Bytes digest = sha1(pass);
    Bytes key(digest.begin(), digest.begin() + 8);
    Bytes out = data;
    Bytes iv(20, iv_fill);
    const Bytes iv_block = des_block(key, iv.data(), true);
    std::copy(iv_block.begin(), iv_block.end(), iv.begin());
    std::size_t pos = 0;
    while (out.size() - pos >= 20U) {
        Bytes old(out.begin() + static_cast<std::ptrdiff_t>(pos), out.begin() + static_cast<std::ptrdiff_t>(pos + 20));
        if (decode) {
            const Bytes plain = des_block(key, out.data() + pos, false);
            std::copy(plain.begin(), plain.end(), out.begin() + static_cast<std::ptrdiff_t>(pos));
        }
        for (std::size_t i = 0; i < 20U; ++i) out[pos + i] ^= iv[i];
        if (!decode) {
            const Bytes cipher = des_block(key, out.data() + pos, true);
            std::copy(cipher.begin(), cipher.end(), out.begin() + static_cast<std::ptrdiff_t>(pos));
        }
        if (decode) iv = old; else std::copy(out.begin() + static_cast<std::ptrdiff_t>(pos), out.begin() + static_cast<std::ptrdiff_t>(pos + 20), iv.begin());
        pos += 20;
    }
    if (pos < out.size()) {
        Bytes stream(20, 0);
        const Bytes stream_head = des_block(key, iv.data(), true);
        std::copy(stream_head.begin(), stream_head.end(), stream.begin());
        std::copy(iv.begin() + 8, iv.end(), stream.begin() + 8);
        for (std::size_t i = 0; i < out.size() - pos; ++i) out[pos + i] ^= stream[i];
    }
    return out;
}

std::uint32_t geepak2_mix_crc(const Bytes& data) {
    std::uint32_t crc = 0x24399977U;
    for (unsigned char byte : data) {
        crc ^= byte;
        for (unsigned int i = 0; i < 8U; ++i) crc = (crc >> 1U) ^ ((crc & 1U) ? 0xEDB88320U : 0U);
    }
    return crc ^ 0xFFFFFFFFU;
}

std::array<std::uint32_t, 3> geepak2_mix_block(std::uint32_t a, std::uint32_t b, std::uint32_t c) {
    a = a - b - c; a ^= c >> 13U; b = b - c - a; b ^= a << 8U; c = c - a - b; c ^= b >> 19U;
    a = a - b - c; a ^= c >> 12U; b = b - c - a; b ^= a << 11U; c = c - a - b; c ^= b >> 5U;
    a = a - b - c; a ^= c >> 3U; b = b - c - a; b ^= a << 10U; c = c - a - b; c ^= b >> 15U;
    return {a, b, c};
}

std::array<std::uint32_t, 3> geepak2_mix_final(std::uint32_t a, std::uint32_t b, std::uint32_t c) {
    a = a - b - c; a ^= c >> 13U; b = b - c - a; b ^= a << 8U; c = c - a - b; c ^= b >> 11U;
    a = a - b - c; a ^= c >> 12U; b = b - c - a; b ^= a << 17U; c = c - a - b; c ^= b >> 5U;
    a = a - b - c; a ^= c >> 3U; b = b - c - a; b ^= a << 10U; c = c - a - b; c ^= b >> 15U;
    return {a, b, c};
}

Bytes geepak2_header_key(const std::string& password) {
    Bytes value = ansi_bytes(password);
    if (value.empty()) return Bytes(8, 0);
    const std::uint32_t crc = geepak2_mix_crc(value);
    std::uint32_t a = 0xAD2832E3U, b = 0x50FF46DEU, c = 0xF07BB613U;
    std::size_t offset = 0;
    std::size_t remaining = value.size();
    while (remaining >= 12U) {
        a += u32(value.data() + offset);
        b += static_cast<std::uint32_t>(value[offset + 5]) + (static_cast<std::uint32_t>(value[offset + 4]) << 8U) + (static_cast<std::uint32_t>(value[offset + 6]) << 16U) + (static_cast<std::uint32_t>(value[offset + 7]) << 24U);
        c += u32(value.data() + offset + 8U);
        const auto mixed = geepak2_mix_block(a, b, c); a = mixed[0]; b = mixed[1]; c = mixed[2];
        offset += 12U; remaining -= 12U;
    }
    c += static_cast<std::uint32_t>(value.size());
    if (remaining >= 11U) c += static_cast<std::uint32_t>(value[offset + 10]) << 24U;
    if (remaining >= 10U) c += static_cast<std::uint32_t>(value[offset + 9]) << 16U;
    if (remaining >= 9U) c += static_cast<std::uint32_t>(value[offset + 8]) << 8U;
    if (remaining >= 8U) b += static_cast<std::uint32_t>(value[offset + 7]) << 24U;
    if (remaining >= 7U) b += static_cast<std::uint32_t>(value[offset + 6]) << 16U;
    if (remaining >= 6U) b += value[offset + 5];
    if (remaining >= 5U) b += static_cast<std::uint32_t>(value[offset + 4]) << 8U;
    if (remaining >= 4U) a += static_cast<std::uint32_t>(value[offset + 3]) << 24U;
    if (remaining >= 3U) a += static_cast<std::uint32_t>(value[offset + 2]) << 16U;
    if (remaining >= 2U) a += static_cast<std::uint32_t>(value[offset + 1]) << 8U;
    if (remaining >= 1U) a += value[offset];
    const auto mixed = geepak2_mix_final(a, b, c);
    c = mixed[2];
    Bytes key(8);
    for (unsigned int i = 0; i < 4U; ++i) key[i] = static_cast<unsigned char>(c >> (i * 8U));
    const std::uint32_t tail = crc ^ c;
    for (unsigned int i = 0; i < 4U; ++i) key[4U + i] = static_cast<unsigned char>(tail >> (i * 8U));
    return key;
}

Bytes geepak2_password_header(const Bytes& data, const std::string& password) {
    if (data.size() != 256U) fail("GEEPAK2 header size is invalid");
    const Bytes key = geepak2_header_key(password);
    Bytes chain(20, 0x8F);
    const Bytes first = des_block(key, chain.data(), true);
    std::copy(first.begin(), first.end(), chain.begin());
    Bytes output(data.size());
    std::size_t position = 0;
    while (data.size() - position >= 20U) {
        const Bytes block = des_block(key, data.data() + position, false);
        for (unsigned int i = 0; i < 8U; ++i) output[position + i] = block[i] ^ chain[i];
        for (unsigned int i = 8U; i < 20U; ++i) output[position + i] = data[position + i] ^ chain[i];
        std::copy(data.begin() + static_cast<std::ptrdiff_t>(position), data.begin() + static_cast<std::ptrdiff_t>(position + 20U), chain.begin());
        position += 20U;
    }
    if (position < data.size()) {
        const Bytes stream_head = des_block(key, chain.data(), false);
        for (std::size_t i = 0; i < data.size() - position; ++i) output[position + i] = data[position + i] ^ (i < 8U ? stream_head[i] : chain[i]);
    }
    return output;
}

Bytes geepak2_feedback(const Bytes& data, const Bytes& key, const Bytes& initial_chain) {
    Bytes output(data.size());
    Bytes chain = initial_chain;
    std::size_t position = 0;
    while (data.size() - position >= 20U) {
        const Bytes block = des_block(key, data.data() + position, false);
        for (unsigned int i = 0; i < 8U; ++i) output[position + i] = block[i] ^ chain[i];
        for (unsigned int i = 8U; i < 20U; ++i) output[position + i] = data[position + i] ^ chain[i];
        std::copy(data.begin() + static_cast<std::ptrdiff_t>(position), data.begin() + static_cast<std::ptrdiff_t>(position + 20U), chain.begin());
        position += 20U;
    }
    if (position < data.size()) {
        const Bytes stream_head = des_block(key, chain.data(), true);
        for (std::size_t i = 0; i < data.size() - position; ++i) output[position + i] = data[position + i] ^ (i < 8U ? stream_head[i] : chain[i]);
    }
    return output;
}

int base64_value(unsigned char value) {
    if (value >= 'A' && value <= 'Z') return value - 'A';
    if (value >= 'a' && value <= 'z') return value - 'a' + 26;
    if (value >= '0' && value <= '9') return value - '0' + 52;
    if (value == '+') return 62;
    if (value == '/') return 63;
    return -1;
}

std::array<std::uint32_t, 512> decode_u32_table(const char* encoded) {
    Bytes raw;
    std::uint32_t accumulator = 0;
    int bits = -8;
    for (const auto* cursor = reinterpret_cast<const unsigned char*>(encoded); *cursor != 0; ++cursor) {
        const int value = base64_value(*cursor);
        if (value < 0) continue;
        accumulator = (accumulator << 6U) | static_cast<std::uint32_t>(value);
        bits += 6;
        if (bits >= 0) {
            raw.push_back(static_cast<unsigned char>((accumulator >> bits) & 0xFFU));
            bits -= 8;
        }
    }
    if (raw.size() != 512U * sizeof(std::uint32_t)) fail("DES lookup table is invalid");
    std::array<std::uint32_t, 512> result{};
    for (std::size_t i = 0; i < result.size(); ++i) result[i] = u32(raw.data() + i * 4U);
    return result;
}

const std::array<std::uint32_t, 512>& des_key_table() {
    static const auto table = decode_u32_table("AAAAABAAAAAAAAAgEAAAIAAAAQAQAAEAAAABIBAAASAACAAAEAgAAAAIACAQCAAgAAgBABAIAQAACAEgEAgBICAAAAAwAAAAIAAAIDAAACAgAAEAMAABACAAASAwAAEgIAgAADAIAAAgCAAgMAgAICAIAQAwCAEAIAgBIDAIASAAAAgAEAAIAAAACCAQAAggAAAJABAACQAAAAkgEAAJIAAICAAQCAgAAAgIIBAICCAACAkAEAgJAAAICSAQCAkgIAAIADAACAAgAAggMAAIICAACQAwAAkAIAAJIDAACSAgCAgAMAgIACAICCAwCAggIAgJADAICQAgCAkgMAgJIAAAAAAAAAACACAAAAAgAAIAACAAAAAgAgAgIAAAICACBAAAAAQAAAIEIAAABCAAAgQAIAAEACACBCAgAAQgIAIABAAAAAQAAgAkAAAAJAACAAQgAAAEIAIAJCAAACQgAgQEAAAEBAACBCQAAAQkAAIEBCAABAQgAgQkIAAEJCACAAAAEAAAABIAIAAQACAAEgAAIBAAACASACAgEAAgIBIEAAAQBAAAEgQgABAEIAASBAAgEAQAIBIEICAQBCAgEgAEABAABAASACQAEAAkABIABCAQAAQgEgAkIBAAJCASBAQAEAQEABIEJAAQBCQAEgQEIBAEBCASBCQgEAQkIBIAAAAAAQAAAAAABAABAAQAAAAAAQEAAAEAAAQBAQAEAQIAAAADAAAAAgAEAAMABAACAAABAwAAAQIABAEDAAQBAAIAAAECAAAAAgQAAQIEAAACAAEBAgABAAIEAQECBAECAgAAAwIAAAICBAADAgQAAgIAAQMCAAECAgQBAwIEAQAAAAgBAAAIAAAECAEABAgAAAAJAQAACQAABAkBAAQJAgAACAMAAAgCAAQIAwAECAIAAAkDAAAJAgAECQMABAkAAgAIAQIACAACBAgBAgQIAAIACQECAAkAAgQJAQIECQICAAgDAgAIAgIECAMCBAgCAgAJAwIACQICBAkDAgQJAAAAAAAAEAAAAQAAAAEQAAgAAAAIABAACAEAAAgBEAAAEAAAABAQAAARAAAAERAACBAAAAgQEAAIEQAACBEQAAAAAAQAABAEAAEABAABEAQIAAAECAAQBAgBAAQIARAEABAABAAQEAQAEQAEABEQBAgQAAQIEBAECBEABAgREAQAAAIAAAASAAABAgAAARIACAACAAgAEgAIAQIACAESAAAQAgAAEBIAABECAAAREgAIEAIACBASAAgRAgAIERIAAAACBAAAEgQAAQIEAAESBAgAAgQIABIECAECBAgBEgQAEAIEABASBAARAgQAERIECBACBAgQEgQIEQIECBESBAAAAAAAAAAQAAABAAAAARAEAAAABAAAEAQAAQAEAAEQAAAAIAAAADAAAAEgAAABMAQAACAEAAAwBAABIAQAATAAABAAAAAQEAAAEQAAABEQBAAQAAQAEBAEABEABAAREAAAECAAABAwAAARIAAAETAEABAgBAAQMAQAESAEABEwABAAAAAQABAAEAEAABABEAQQAAAEEAAQBBABAAQQARAAEAAgABAAMAAQASAAEAEwBBAAIAQQADAEEAEgBBABMAAQEAAAEBAQABARAAAQERAEEBAABBAQEAQQEQAEEBEQABAQIAAQEDAAEBEgABARMAQQECAEEBAwBBARIAQQETAAAAAAAAAACAgAAAAIAAAIAAQAAAAEAAgIBAAACAQACAAAAgAAAAIICAACAAgAAggABAIAAAQCCAgEAgAIBAIIAQAAAAEAAAgJAAAACQAACAEEAAABBAAICQQAAAkEAAgBAAIAAQACCAkAAgAJAAIIAQQCAAEEAggJBAIACQQCCAAAAAIAAAAKCAAAAggAAAoABAACAAQACggEAAIIBAAKAAACAgAAAgoIAAICCAACCgAEAgIABAIKCAQCAggEAgoBAAACAQAACgkAAAIJAAAKAQQAAgEEAAoJBAACCQQACgEAAgIBAAIKCQACAgkAAgoBBAICAQQCCgkEAgIJBAIKAAAAAAABAAAAAAgAAAEIAAAAAAEAAQABAAAIAQABCAEQAAAAEAEAABAACAAQAQgAEAAAARABAAEQAAgBEAEIAQAAIAAAASAAAAAoAAABKAAAACABAAEgAQAAKAEAASgBEAAgABABIAAQACgAEAEoABAAIAEQASABEAAoARABKAEAAgAAAAMAAAACCAAAAwgAAAIAAQADAAEAAggBAAMIARACAAAQAwAAEAIIABADCAAQAgABEAMAARACCAEQAwgBAAIgAAADIAAAAigAAAMoAAACIAEAAyABAAIoAQADKAEQAiAAEAMgABACKAAQAygAEAIgARADIAEQAigBEAMoAQAAAAAAAAAEAAAEAAAABAQCAAAAAgAABAIABAACAAQEACAAAAAgAAQAIAQAACAEBAIgAAACIAAEAiAEAAIgBAQgAAAAIAAABCAABAAgAAQEIgAAACIAAAQiAAQAIgAEBCAgAAAgIAAEICAEACAgBAQiIAAAIiAABCIgBAAiIAQEAAgAAAAIAAQACAQAAAgEBAIIAAACCAAEAggEAAIIBAQAKAAAACgABAAoBAAAKAQEAigAAAIoAAQCKAQAAigEBCAIAAAgCAAEIAgEACAIBAQiCAAAIggABCIIBAAiCAQEICgAACAoAAQgKAQAICgEBCIoAAAiKAAEIigEACIoBAQ=");
    return table;
}

const std::array<std::uint32_t, 512>& des_sp_table() {
    static const auto table = decode_u32_table("AAgIAgAACAACAAACAggIAgAAAAICCAgAAgAIAAIAAAICCAgAAAgIAgAACAICCAAAAggAAgAAAAIAAAAAAgAIAAAACAACAAAAAAgAAgAICAACCAgCAAAIAgIIAAAACAACAgAAAAAIAAAACAgAAgAIAgAIAAACCAACAgAIAgAAAAAAAAAAAggIAgAIAAICAAgAAAgIAgAACAACCAAAAAgAAgIACAIACAAAAAgIAAIAAAICCAgAAgAAAAIAAAIAAAgCAggIAgAICAAAAAgCAggAAgAAAAICCAAAAgAIAAAAAAAAAAgAAAAAAgIIAAIACAgCAgAAAAIACAIACAAAAggIABCAEEAAAAAAAIAQAAAAEEAQAABAEIAAAACAAEAAgBAAAIAAABAAEEAQAAAAAIAAQBAAEAAAgBBAAAAQQBAAAAAAABAAEIAAQBAAEEAAgAAAEIAQAAAAAEAAAAAAEAAQABCAAEAQgBAAAIAQQBAAAEAAAABAAAAQABCAAAAQgBBAEAAQAACAEEAAgABAEIAQABCAEEAQABAAEAAAQAAAAAAAAABAEIAAAAAAEAAQABBAAIAAAAAAAEAQgBAAEIAAQACAEEAAgAAAAAAAABAAAEAQAAAAEIAQQACAEAAAABBAEAAQQAAAEAAQgAAAAIAAQBCAAEAQAAAAAAAQQACAEAABAAAEAAEEBAABAAABAQAEAQAEAAAAAAQBAQAEAAEEAAABAAQAAAQAAAAEBAEAAAABAQQEAQEAAAEAAAABAAQEAAAAAAEABAAAAQQEAAEAAAEBAAABAQQEAAAEAAEAAAQBAAQEAAEABAEBBAAAAAQEAAEEAAAAAAAAAAAEAQEEAAABBAQAAQAAAQAAAAAABAABAQAAAQAEAAAABAQBAQAEAAAAAAABBAQAAQQAAQAEBAEABAAAAAAEAQEEBAEAAAABAQQAAQAABAAAAAQBAQQEAAAEAAABAAQBAQAEAAEEAAABAAQAAAAAAQAEBAEBAAABAAAEAQEEAAABAAAAAAQECBBAAAAQABAIAAAACBBAEAAAAAAAAEAQCBAAEAgAQAAAEEAQCAAAEAAAABAIEAAACAAAEAgQQAAAAEAAAAAAEAgAQBAAEEAAABAAAAgAAAAAEEAACBAAEAAAQBAAEAAACBAAAAAAAAAIAEAAABBAEAAQABAIAEAQCBBAEAAAQAAIAEAQCBAAAAAAQAAIAAAQABBAAAAQABAIAAAAAABAEAgQABAAAAAAABAAAAgAQAAAAAAACABAEAAQQBAAEAAAAAAAEAgQQBAIEEAAAABAAAgQQBAIAAAAABAAEAgQQAAIAEAAABBAAAAAQBAIEAAQCBAAAAAAABAIAAAQABBAEAAAAAgAAAEAAAQAACAEAQggAAEIAAQACCAEAQAAAAEIAAABACAAAAAgAAAIAAQBACAEAAggAAEIAAQBCAAAAAAABAEAAAAACCAAAQAgBAAAAAQACCAEAQAAAAAAIAAACCAAAAAgBAAIIAQBCCAAAQAAAAEIAAQAACAEAAAABAEIAAQBCCAEAAggAAEAAAABCAAAAQAgAAAAIAAACAAEAAgAAAAIAAQBACAEAQgAAAAAIAQBAAAAAAgABAAAIAABACAEAAgABAAAAAAAACAEAQggAAEIAAQBCCAEAAAAAAEAAAQBACAAAQgABAAIIAQAACAAAAAgBAEAAAABCCAAAAhAAACAQAAgAAAAAAAAICCAQAAgAAAgAABAIACAAAAgAEAgAABAICCAACAgAAAAAIAAIACAQAAAgAAAIIBAICAAAAAgAEAgAIBAACCAAAAAAAAgAABAAAAAACAggEAAIIBAICCAAAAggAAAAIBAIAAAQAAAAAAgIABAICAAACAAgEAgAAAAAACAACAAgEAgIAAAICCAQAAgAAAAAAAAIACAAAAAgAAgAABAACCAAAAgAEAAIABAICCAACAgAEAAAABAICCAACAgAAAAIABAIACAQAAAgAAAIIBAICAAAAAAAAAgAABAAACAQCAAgAAgIIAAACCAQCAAAEAAAABAACCAAEAAAAACAAAAAgABBAAAAQRCAAEEQAAAAEIAAAAAAAAAAAABBAIAAQQCAAAAQAABBAAAAABCAAEAQAABBAIAAAQCAAEAQAAABEAAAARCAAEAAAAAAAIAAQQAAAEAQgAABEAAAQRCAAAAQgABBAAAAARCAAAEQAABAAIAAAAAAAEEQgAAAEAAAQRAAAEEAgAAAEAAAAACAAAAAAABBEAAAQQCAAEEQgAAAEIAAAAAAAAAAgAABAAAAQQAAAAAAgABAAAAAAQCAAEAAgABAEIAAAQCAAAAQAAABEIAAQAAAAEAQgABBAAAAARAAAAEQgABBAAAAQBCAAEAQAABBEAAAIAAgCAAAIIggAACAAAAAAAAAAIggACAAAAAgCCAAIIggAAAAAAAACAAAIIAgAACAIAAggCAAAIggAAAIAAAgCAAAAIAgACCAIAAgAAAAAIggACCIIAAACAAAAAAAACCAAAAACAAAIAAgAACIIAAgCAAAIAAAAACAAAAgiCAAAAAAACAAAAAAgCAAAAggACCIIAAAgAAAAAgAAAAAAAAggCAAIAggAACIAAAAiCAAIAAAACCIIAAAACAAIAAAAACIIAAgiAAAIAAAACAIIAAACAAAIIAgAACAIAAAiAAAIAggAAAAAAAgiCAAIIAAAAAAAAAACCAAIAgAAACAIAAggA=");
    return table;
}

std::uint32_t rol32(std::uint32_t value, unsigned int bits) {
    bits &= 31U;
    return bits == 0U ? value : (value << bits) | (value >> (32U - bits));
}

std::uint32_t ror32(std::uint32_t value, unsigned int bits) {
    bits &= 31U;
    return bits == 0U ? value : (value >> bits) | (value << (32U - bits));
}

std::uint32_t ror28(std::uint32_t value, unsigned int bits) {
    return ((value >> bits) | (value << (28U - bits))) & 0x0FFFFFFFU;
}

std::pair<std::uint32_t, std::uint32_t> des_swap_right(
    std::uint32_t a, std::uint32_t b, std::uint32_t mask, unsigned int shift
) {
    const std::uint32_t temp = ((a >> shift) ^ b) & mask;
    return {a ^ (temp << shift), b ^ temp};
}

std::pair<std::uint32_t, std::uint32_t> des_swap_left(
    std::uint32_t value, std::uint32_t mask, int shift
) {
    const unsigned int count = static_cast<unsigned int>(16 - shift) & 31U;
    const std::uint32_t temp = ((value << count) ^ value) & mask;
    return {(temp >> count) ^ (value ^ temp), temp};
}

std::array<std::uint32_t, 32> expand_des_schedule(const Bytes& key) {
    if (key.size() != 8U) fail("DES schedule key size is invalid");
    std::uint32_t left = u32(key.data());
    std::uint32_t right = u32(key.data() + 4U);
    auto swapped = des_swap_right(right, left, 0x0F0F0F0FU, 4U);
    right = swapped.first; left = swapped.second;
    left = des_swap_left(left, 0xCCCC0000U, -2).first;
    right = des_swap_left(right, 0xCCCC0000U, -2).first;
    swapped = des_swap_right(right, left, 0x55555555U, 1U);
    right = swapped.first; left = swapped.second;
    swapped = des_swap_right(left, right, 0x00FF00FFU, 8U);
    left = swapped.first; right = swapped.second;
    swapped = des_swap_right(right, left, 0x55555555U, 1U);
    right = swapped.first; left = swapped.second;
    right = ((right & 0xFFU) << 16U) | (right & 0xFF00U) |
        ((right & 0xFF0000U) >> 16U) | ((left & 0xF0000000U) >> 4U);
    left &= 0x0FFFFFFFU;

    static constexpr std::array<unsigned char, 16> rotations = {
        0, 0, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 0
    };
    const auto& table = des_key_table();
    std::array<std::uint32_t, 32> schedule{};
    for (std::size_t i = 0; i < rotations.size(); ++i) {
        const unsigned int shift = rotations[i] ? 2U : 1U;
        left = ror28(left, shift);
        right = ror28(right, shift);
        const std::uint32_t t0 =
            table[64U + ((left >> 6U & 3U) | (left >> 7U & 60U))] |
            table[left & 63U] |
            table[128U + ((left >> 13U & 15U) | (left >> 14U & 48U))] |
            table[192U + ((left >> 20U & 1U) | (left >> 21U & 6U) | (left >> 22U & 56U))];
        const std::uint32_t t1 =
            table[320U + ((right >> 7U & 3U) | (right >> 8U & 60U))] |
            table[256U + (right & 63U)] |
            table[384U + (right >> 15U & 63U)] |
            table[448U + ((right >> 21U & 15U) | (right >> 22U & 48U))];
        schedule[i * 2U] = rol32((t1 << 16U) | (t0 & 0xFFFFU), 2U);
        schedule[i * 2U + 1U] = rol32((t0 >> 16U) | (t1 & 0xFFFF0000U), 6U);
    }
    return schedule;
}

std::uint32_t des_schedule_round(
    std::uint32_t value, std::uint32_t schedule_a, std::uint32_t schedule_b
) {
    const auto& table = des_sp_table();
    const std::uint32_t u = schedule_a ^ value;
    const std::uint32_t t = ror32(schedule_b ^ value, 4U);
    return table[(u >> 2U) & 0x3FU] ^
        table[128U + ((u >> 10U) & 0x3FU)] ^
        table[256U + ((u >> 18U) & 0x3FU)] ^
        table[384U + ((u >> 26U) & 0x3FU)] ^
        table[64U + ((t >> 2U) & 0x3FU)] ^
        table[192U + ((t >> 10U) & 0x3FU)] ^
        table[320U + ((t >> 18U) & 0x3FU)] ^
        table[448U + ((t >> 26U) & 0x3FU)];
}

Bytes des_schedule_block(
    const unsigned char* block, const std::array<std::uint32_t, 32>& schedule, bool decrypt
) {
    std::uint32_t left = u32(block);
    std::uint32_t right = u32(block + 4U);
    std::uint32_t temp = ((right >> 4U) ^ left) & 0x0F0F0F0FU;
    left ^= temp; right ^= temp << 4U;
    temp = ((left >> 16U) ^ right) & 0x0000FFFFU;
    right ^= temp; left ^= temp << 16U;
    temp = ((right >> 2U) ^ left) & 0x33333333U;
    left ^= temp; right ^= temp << 2U;
    temp = ((left >> 8U) ^ right) & 0x00FF00FFU;
    right ^= temp; left ^= temp << 8U;
    temp = ((right >> 1U) ^ left) & 0x55555555U;
    left ^= temp; right ^= temp << 1U;
    left = rol32(left, 3U);
    right = rol32(right, 3U);
    for (unsigned int round = 0; round < 16U; ++round) {
        const unsigned int index = decrypt ? 30U - round * 2U : round * 2U;
        if ((round & 1U) != 0U) {
            left ^= des_schedule_round(right, schedule[index], schedule[index + 1U]);
        } else {
            right ^= des_schedule_round(left, schedule[index], schedule[index + 1U]);
        }
    }
    left = ror32(left, 3U);
    right = ror32(right, 3U);
    temp = ((left >> 1U) ^ right) & 0x55555555U;
    right ^= temp; left ^= temp << 1U;
    temp = ((right >> 8U) ^ left) & 0x00FF00FFU;
    left ^= temp; right ^= temp << 8U;
    temp = ((left >> 2U) ^ right) & 0x33333333U;
    right ^= temp; left ^= temp << 2U;
    temp = ((right >> 16U) ^ left) & 0x0000FFFFU;
    left ^= temp; right ^= temp << 16U;
    temp = ((left >> 4U) ^ right) & 0x0F0F0F0FU;
    right ^= temp; left ^= temp << 4U;
    Bytes output(8U);
    for (unsigned int i = 0; i < 4U; ++i) {
        output[i] = static_cast<unsigned char>(right >> (i * 8U));
        output[4U + i] = static_cast<unsigned char>(left >> (i * 8U));
    }
    return output;
}

Bytes geepak2_schedule_feedback(
    const Bytes& data,
    const std::array<std::uint32_t, 32>& schedule,
    const Bytes& initial_chain
) {
    Bytes output(data.size());
    Bytes chain = initial_chain;
    std::size_t position = 0;
    while (data.size() - position >= 20U) {
        const Bytes block = des_schedule_block(data.data() + position, schedule, true);
        for (unsigned int i = 0; i < 8U; ++i) output[position + i] = block[i] ^ chain[i];
        for (unsigned int i = 8U; i < 20U; ++i) output[position + i] = data[position + i] ^ chain[i];
        std::copy(data.begin() + static_cast<std::ptrdiff_t>(position),
                  data.begin() + static_cast<std::ptrdiff_t>(position + 20U), chain.begin());
        position += 20U;
    }
    if (position < data.size()) {
        const Bytes stream_head = des_schedule_block(chain.data(), schedule, false);
        for (std::size_t i = 0; i < data.size() - position; ++i) {
            output[position + i] = data[position + i] ^ (i < 8U ? stream_head[i] : chain[i]);
        }
    }
    return output;
}

Bytes geepak2_resource_header(
    const Bytes& raw_header, const Bytes& key, const Bytes& initial_chain
) {
    if (raw_header.size() != 16U) fail("GEEPAK2 resource header size is invalid");
    const auto schedule = expand_des_schedule(key);
    auto altered = schedule;
    for (std::size_t i = 0; i < altered.size(); i += 2U) altered[i] ^= altered[i + 1U];
    return geepak2_schedule_feedback(
        geepak2_schedule_feedback(raw_header, altered, initial_chain),
        schedule,
        initial_chain
    );
}

std::uint32_t dib_stride(std::uint8_t bits, std::int32_t width) {
    if (width <= 0) return 0;
    return static_cast<std::uint32_t>((width * bits + 31) & ~31) / 8U;
}

std::string gameofmir_frame_format(const Bytes& header) {
    if (header.size() < 4U || header[1] != 0xADU || header[2] != 0x43U) return {};
    if (header[0] == 0x64U && header[3] == 0xD9U) return "rgb565";
    if (header[0] == 0x62U && header[3] == 0xD9U) return "gray8";
    if (header[0] == 0x66U && header[3] == 0xD9U) return "bgrx32";
    if (header[0] == 0x67U && header[3] == 0xD9U) return "bgr24";
    if (header[0] == 0x67U && header[3] == 0xD8U) return "bgr24a8";
    return {};
}

std::uint32_t gameofmir_frame_size(
    std::int32_t width, std::int32_t height, const std::string& format
) {
    if (width <= 0 || height <= 0 || width > 4096 || height > 4096) return 0;
    const std::uint64_t w = static_cast<std::uint32_t>(width);
    const std::uint64_t h = static_cast<std::uint32_t>(height);
    const auto align4 = [](std::uint64_t value) { return (value + 3U) & ~std::uint64_t{3U}; };
    std::uint64_t size = 0;
    if (format == "rgb565") size = align4(w * 2U) * h;
    else if (format == "gray8") size = align4(w) * h;
    else if (format == "bgr24") size = align4(w * 3U) * h;
    else if (format == "bgr24a8") size = (align4(w * 3U) + align4(w)) * h;
    else if (format == "bgrx32") size = w * h * 4U;
    return size == 0 || size > 128U * 1024U * 1024U ? 0U : static_cast<std::uint32_t>(size);
}

Index load_gameofmir_frame_index(const Profile& profile) {
    std::ifstream stream(std::filesystem::u8path(profile.path), std::ios::binary);
    if (!stream) fail("unable to open native frame asset");
    stream.seekg(0, std::ios::end);
    const auto end = stream.tellg();
    if (end <= 0) fail("native frame asset is empty");
    const std::uint64_t file_size = static_cast<std::uint64_t>(end);
    constexpr std::size_t kScanChunk = 1024U * 1024U;
    Bytes scan(kScanChunk);
    Index result;
    result.magic = profile.magic;
    std::uint64_t scan_offset = 0;
    std::uint64_t last_candidate = std::numeric_limits<std::uint64_t>::max();
    while (scan_offset < file_size) {
        const std::size_t request = static_cast<std::size_t>(
            std::min<std::uint64_t>(scan.size(), file_size - scan_offset));
        stream.clear();
        stream.seekg(static_cast<std::streamoff>(scan_offset), std::ios::beg);
        stream.read(reinterpret_cast<char*>(scan.data()), static_cast<std::streamsize>(request));
        const std::size_t received = static_cast<std::size_t>(stream.gcount());
        if (received == 0) break;
        for (std::size_t pos = 0; pos + 1U < received; ++pos) {
            if (scan[pos] != 0x78U ||
                (scan[pos + 1U] != 0x9CU && scan[pos + 1U] != 0xDAU && scan[pos + 1U] != 0x01U)) continue;
            const std::uint64_t candidate = scan_offset + pos;
            if (candidate == last_candidate || candidate < 16U ||
                candidate > std::numeric_limits<std::uint32_t>::max()) continue;
            last_candidate = candidate;
            const Bytes header = read_file(profile.path, candidate - 16U, 16U);
            const std::string format = gameofmir_frame_format(header);
            if (format.empty()) continue;
            const std::int32_t width = static_cast<std::int32_t>(u16(header.data() + 4U) ^ 16046U);
            const std::int32_t height = static_cast<std::int32_t>(u16(header.data() + 6U) ^ 3041U);
            const std::int32_t origin_x = static_cast<std::int16_t>(u16(header.data() + 8U) ^ 36751U);
            const std::int32_t origin_y = static_cast<std::int16_t>(u16(header.data() + 10U) ^ 36751U);
            const std::uint32_t compressed_size = u32(header.data() + 12U) ^ 2408550287U;
            const std::uint32_t expected_size = gameofmir_frame_size(width, height, format);
            if (expected_size == 0 || compressed_size < 8U || compressed_size > 128U * 1024U * 1024U ||
                compressed_size > file_size - candidate) continue;
            const Bytes compressed = read_file(profile.path, candidate, compressed_size);
            Bytes decoded;
            std::string error;
            if (!xiami::compression::inflate_zlib(
                    compressed.data(), compressed.size(), expected_size,
                    128U * 1024U * 1024U, &decoded, &error)) continue;
            Record record;
            record.index = static_cast<std::uint32_t>(result.records.size());
            record.pixel_format = format;
            record.offset = static_cast<std::uint32_t>(candidate);
            record.data_offset = record.offset;
            record.data_length = compressed_size;
            record.width = width;
            record.height = height;
            record.origin_x = origin_x;
            record.origin_y = origin_y;
            record.packed_size = compressed_size;
            if (format == "gray8") record.image_type = 3U;
            else if (format == "rgb565") record.image_type = 4U;
            else if (format == "bgr24" || format == "bgr24a8") record.image_type = 6U;
            else record.image_type = 7U;
            record.alpha = format == "bgr24a8" ? 1U : 0U;
            result.records.push_back(std::move(record));
        }
        if (received < scan.size()) break;
        scan_offset += received - 1U;
    }
    if (result.records.empty()) fail("native frame scan found no valid zlib resources");
    return result;
}

Image decode_gameofmir_frame(
    const Profile& profile, const Record& record, bool transparent_zero
) {
    const std::uint32_t expected_size = gameofmir_frame_size(
        record.width, record.height, record.pixel_format);
    if (expected_size == 0) fail("native frame metadata is invalid");
    const Bytes compressed = read_file(profile.path, record.data_offset, record.data_length);
    Bytes raw;
    std::string error;
    if (!xiami::compression::inflate_zlib(
            compressed.data(), compressed.size(), expected_size,
            128U * 1024U * 1024U, &raw, &error)) {
        throw std::runtime_error("native frame inflate failed: " + error);
    }
    const std::uint32_t width = static_cast<std::uint32_t>(record.width);
    const std::uint32_t height = static_cast<std::uint32_t>(record.height);
    Image image{width, height, width * 4U, record.origin_x, record.origin_y,
        Bytes(static_cast<std::size_t>(width) * height * 4U)};
    const std::uint32_t color_stride = record.pixel_format == "gray8" ? dib_stride(8, record.width)
        : record.pixel_format == "rgb565" ? dib_stride(16, record.width)
        : record.pixel_format == "bgr24" || record.pixel_format == "bgr24a8" ? dib_stride(24, record.width)
        : width * 4U;
    const std::uint32_t alpha_stride = record.pixel_format == "bgr24a8" ? dib_stride(8, record.width) : 0U;
    const std::size_t alpha_base = static_cast<std::size_t>(color_stride) * height;
    for (std::uint32_t y = 0; y < height; ++y) {
        const unsigned char* color = raw.data() + static_cast<std::size_t>(y) * color_stride;
        const unsigned char* alpha = alpha_stride ? raw.data() + alpha_base + static_cast<std::size_t>(y) * alpha_stride : nullptr;
        for (std::uint32_t x = 0; x < width; ++x) {
            unsigned char b = 0, g = 0, r = 0, a = 255;
            if (record.pixel_format == "gray8") {
                r = g = b = color[x];
                a = transparent_zero && color[x] == 0 ? 0 : 255;
            } else if (record.pixel_format == "rgb565") {
                const std::uint16_t value = u16(color + x * 2U);
                r = static_cast<unsigned char>(((value >> 11U) & 31U) * 255U / 31U);
                g = static_cast<unsigned char>(((value >> 5U) & 63U) * 255U / 63U);
                b = static_cast<unsigned char>((value & 31U) * 255U / 31U);
                a = transparent_zero && value == 0 ? 0 : 255;
            } else if (record.pixel_format == "bgr24" || record.pixel_format == "bgr24a8") {
                b = color[x * 3U]; g = color[x * 3U + 1U]; r = color[x * 3U + 2U];
                a = alpha ? alpha[x] : 255;
            } else {
                b = color[x * 4U]; g = color[x * 4U + 1U]; r = color[x * 4U + 2U]; a = 255;
            }
            const std::size_t out = (static_cast<std::size_t>(y) * width + x) * 4U;
            image.bgra[out] = b; image.bgra[out + 1U] = g;
            image.bgra[out + 2U] = r; image.bgra[out + 3U] = a;
        }
    }
    return image;
}

}  // namespace

Index load_index(const Profile& profile) {
    if (profile.path.empty() || profile.format_version.empty()) fail("native asset profile is incomplete");
    if (profile.format_version == "frame-scan-v1") return load_gameofmir_frame_index(profile);
    const Bytes header_cipher = read_file(profile.path, profile.prefix_size, 256);
    if (profile.format_version == "geepak3-v1") {
        const std::string password = profile.password.empty() ? "V8M2" : profile.password;
        const xiami::geepak3::Bytes password_bytes = ansi_bytes(password);
        const auto material = xiami::geepak3::derive_key_material(password_bytes);
        xiami::geepak3::AesKey header_key{};
        std::copy_n(material.key_block.begin(), header_key.size(), header_key.begin());
        const Bytes header = xiami::geepak3::aes_ctr_crypt(header_key, header_cipher);
        const std::uint32_t count = u32(header.data() + 46U);
        const std::uint8_t mode = header[50U];
        const std::uint32_t index_offset = u32(header.data() + 54U);
        if (count > 2000000U || mode != 2U) fail("GEEPAK3 header is invalid");
        std::ifstream stream(std::filesystem::u8path(profile.path), std::ios::binary);
        stream.seekg(0, std::ios::end);
        const std::uint64_t file_size = static_cast<std::uint64_t>(stream.tellg());
        const std::uint64_t index_size = static_cast<std::uint64_t>(count) * 4U;
        if (index_offset < profile.data_base || index_offset > file_size || index_size > file_size - index_offset) {
            fail("GEEPAK3 directory range is invalid");
        }
        const Bytes raw_index = read_file(profile.path, index_offset, index_size);
        const std::uint64_t data_start = static_cast<std::uint64_t>(index_offset) + index_size;
        Index result;
        result.magic = profile.magic;
        result.records.reserve(count);
        for (std::uint32_t i = 0; i < count; ++i) {
            Record record;
            record.index = i;
            record.offset = xiami::geepak3::decode_directory_offset(
                u32(raw_index.data() + static_cast<std::size_t>(i) * 4U), i, material.words);
            if (record.offset != 0) {
                if (record.offset < data_start || static_cast<std::uint64_t>(record.offset) + 16U > file_size) {
                    fail("GEEPAK3 resource offset is invalid");
                }
                const Bytes encrypted = read_file(profile.path, record.offset, 16U);
                xiami::geepak3::ResourceHeader encrypted_header{};
                std::copy(encrypted.begin(), encrypted.end(), encrypted_header.begin());
                const auto plain = xiami::geepak3::decode_resource_header(encrypted_header, material.words, i);
                record.image_type = plain[0];
                record.alpha = plain[3];
                record.width = i16(plain.data() + 4U);
                record.height = i16(plain.data() + 6U);
                record.origin_x = i16(plain.data() + 8U);
                record.origin_y = i16(plain.data() + 10U);
                const auto packed = static_cast<std::int32_t>(u32(plain.data() + 12U));
                record.packed_size = packed > 0 ? static_cast<std::uint32_t>(packed) : 0U;
                const std::uint8_t bits = record.image_type == 3 ? 8 : record.image_type == 4 || record.image_type == 5 ? 16 : record.image_type == 6 ? 24 : record.image_type == 7 || record.image_type == 9 ? 32 : 0;
                if (bits == 0 || record.width <= 0 || record.height <= 0) fail("GEEPAK3 resource header is invalid");
                const std::uint32_t raw_size = dib_stride(bits, record.width) * static_cast<std::uint32_t>(record.height) + (record.alpha ? dib_stride(8, record.width) * static_cast<std::uint32_t>(record.height) : 0U);
                record.data_offset = record.offset + 16U;
                record.data_length = record.packed_size ? record.packed_size : raw_size;
                if (static_cast<std::uint64_t>(record.data_offset) + record.data_length > file_size) fail("GEEPAK3 payload range is invalid");
            }
            result.records.push_back(record);
        }
        return result;
    }
    const bool geepak2 = profile.format_version == "geepak2-v1";
    const bool geem2lp = profile.format_version == "geem2lp-v1";
    const std::string header_password = profile.header_password.empty() ? profile.password : profile.header_password;
    const Bytes header = geepak2
        ? geepak2_password_header(header_cipher, header_password)
        : crypt_buffer(header_cipher, header_password, true, profile.format_version == "geem2lp-v1" ? 96 : 143);
    const std::uint32_t count = u32(header.data() + 46);
    const std::uint8_t mode = geepak2 ? static_cast<std::uint8_t>(u32(header.data() + 0x32)) : header[50];
    const std::uint32_t index_offset = u32(header.data() + 54);
    if ((!geem2lp && count == 0) || count > 2000000U || mode > 2U) fail("native PAK header is invalid");
    Bytes directory_key;
    Bytes directory_chain(20, geepak2 ? 0x60 : 0x00);
    if (geepak2) {
        Bytes pass = ansi_bytes(profile.password);
        const Bytes digest = sha1(pass);
        directory_key.assign(digest.begin(), digest.begin() + 8);
        const Bytes first = des_block(directory_key, directory_chain.data(), true);
        std::copy(first.begin(), first.end(), directory_chain.begin());
        const Bytes declared = read_file(profile.path, index_offset, static_cast<std::uint64_t>(count) * 4U);
        const Bytes first_pass = geepak2_feedback(declared, directory_key, directory_chain);
        const Bytes second_pass = geepak2_feedback(first_pass, directory_key, directory_chain);
        std::uint32_t table_end = 0;
        for (std::size_t i = 0; i + 4U <= second_pass.size(); i += 4U) {
            const std::uint32_t offset = u32(second_pass.data() + i) ^ directory_chain[0];
            if (offset != 0) { table_end = offset; break; }
        }
        if (table_end <= index_offset) fail("GEEPAK2 directory boundary is invalid");
        const std::uint32_t table_size = table_end - index_offset;
        if (table_size % 20U != 0U || table_size > count * 4U) fail("GEEPAK2 directory size is invalid");
        const Bytes table_cipher = read_file(profile.path, index_offset, table_size);
        const Bytes table_first = geepak2_feedback(table_cipher, directory_key, directory_chain);
        const Bytes table_plain = geepak2_feedback(table_first, directory_key, directory_chain);
        Index result;
        result.magic = profile.magic;
        result.records.reserve(table_size / 4U);
        for (std::uint32_t i = 0; i < table_size / 4U; ++i) {
            Record record;
            record.index = i;
            record.offset = u32(table_plain.data() + i * 4U) ^ directory_chain[0];
            if (record.offset != 0) {
                const Bytes raw_header = read_file(profile.path, record.offset, 16U);
                const Bytes plain_header = geepak2_resource_header(
                    raw_header, directory_key, directory_chain
                );
                record.image_type = plain_header[0];
                record.alpha = plain_header[3];
                record.width = i16(plain_header.data() + 4);
                record.height = i16(plain_header.data() + 6);
                record.origin_x = i16(plain_header.data() + 8);
                record.origin_y = i16(plain_header.data() + 10);
                const auto packed = static_cast<std::int32_t>(u32(plain_header.data() + 12));
                record.packed_size = packed > 0 ? static_cast<std::uint32_t>(packed) : 0U;
                const std::uint8_t bits = record.image_type == 3 ? 8 : record.image_type == 4 || record.image_type == 5 ? 16 : record.image_type == 6 ? 24 : record.image_type == 7 || record.image_type == 9 ? 32 : 0;
                if (bits == 0 || record.width <= 0 || record.height <= 0) fail("GEEPAK2 resource header is invalid");
                const std::uint32_t raw_size = dib_stride(bits, record.width) * static_cast<std::uint32_t>(record.height) + (record.alpha ? dib_stride(8, record.width) * static_cast<std::uint32_t>(record.height) : 0U);
                record.data_offset = record.offset + 16U;
                record.data_length = record.packed_size ? record.packed_size : raw_size;
            }
            result.records.push_back(record);
        }
        return result;
    }
    if (geem2lp) {
        if (mode != 2U || index_offset != profile.data_base) fail("GEEM2LP header layout is invalid");
        std::ifstream stream(std::filesystem::u8path(profile.path), std::ios::binary);
        stream.seekg(0, std::ios::end);
        const std::uint64_t file_size = static_cast<std::uint64_t>(stream.tellg());
        const std::uint64_t available = file_size - index_offset;
        const std::array<std::uint64_t, 5> probes = {4U, 8U, 12U, 16U, std::min<std::uint64_t>(available, 4096U * 4U) / 20U * 20U};
        std::uint32_t selected_count = 0, data_start = 0;
        Bytes selected_offsets;
        for (const auto probe_size : probes) {
            if (probe_size == 0 || probe_size > available) continue;
            const Bytes probe = crypt_buffer(read_file(profile.path, index_offset, probe_size), profile.password, true, 96);
            for (std::size_t pos = 0; pos + 4U <= probe.size(); pos += 4U) {
                const std::uint32_t candidate_start = u32(probe.data() + pos);
                const std::uint64_t index_size = static_cast<std::uint64_t>(candidate_start) - index_offset;
                if (candidate_start <= profile.data_base || candidate_start >= file_size || index_size == 0 || index_size % 4U != 0U || index_size > available) continue;
                const std::uint32_t candidate_count = static_cast<std::uint32_t>(index_size / 4U);
                if (candidate_count == 0 || candidate_count >= 2000000U) continue;
                const Bytes plain_index = crypt_buffer(read_file(profile.path, index_offset, index_size), profile.password, true, 96);
                bool valid = true;
                std::uint32_t previous = 0;
                for (std::uint32_t i = 0; i < candidate_count; ++i) {
                    const std::uint32_t offset = u32(plain_index.data() + i * 4U);
                    if (offset != 0 && (offset < candidate_start || offset >= file_size || (previous != 0 && offset < previous))) { valid = false; break; }
                    if (offset != 0) previous = offset;
                }
                if (valid) { selected_count = candidate_count; data_start = candidate_start; selected_offsets = plain_index; break; }
            }
            if (selected_count != 0) break;
        }
        if (selected_count == 0) fail("GEEM2LP index boundary is invalid");
        Index result;
        result.magic = profile.magic;
        result.records.reserve(selected_count);
        for (std::uint32_t i = 0; i < selected_count; ++i) {
            Record record; record.index = i; record.offset = u32(selected_offsets.data() + i * 4U);
            if (record.offset != 0) {
                const Bytes plain = crypt_buffer(read_file(profile.path, record.offset, 16U), profile.password, true, 96);
                record.image_type = plain[0]; record.alpha = plain[3]; record.width = i16(plain.data() + 4); record.height = i16(plain.data() + 6); record.origin_x = i16(plain.data() + 8); record.origin_y = i16(plain.data() + 10);
                const auto packed = static_cast<std::int32_t>(u32(plain.data() + 12)); record.packed_size = packed > 0 ? static_cast<std::uint32_t>(packed) : 0U;
                const std::uint8_t bits = record.image_type == 3 ? 8 : record.image_type == 4 || record.image_type == 5 ? 16 : record.image_type == 6 ? 24 : record.image_type == 7 || record.image_type == 9 ? 32 : 0;
                if (bits == 0 || record.width <= 0 || record.height <= 0) fail("GEEM2LP image header is invalid");
                const std::uint32_t raw_size = dib_stride(bits, record.width) * static_cast<std::uint32_t>(record.height) + (record.alpha ? dib_stride(8, record.width) * static_cast<std::uint32_t>(record.height) : 0U);
                record.data_offset = record.offset + 16U; record.data_length = record.packed_size ? record.packed_size : raw_size;
            }
            result.records.push_back(record);
        }
        return result;
    }
    const std::uint32_t unit = mode == 0 ? 8U : 4U;
    const Bytes raw_index = read_file(profile.path, index_offset, static_cast<std::uint64_t>(count) * unit);
    const Bytes index_plain = crypt_buffer(raw_index, profile.password.empty() ? "gameofmir" : profile.password, true, profile.format_version == "geem2lp-v1" ? 96 : 143);
    Index result;
    result.magic = profile.magic;
    result.records.reserve(count);
    for (std::uint32_t i = 0; i < count; ++i) {
        const std::size_t pos = static_cast<std::size_t>(i) * unit;
        const std::uint32_t offset = u32(index_plain.data() + pos);
        Record record;
        record.index = i;
        record.offset = offset;
        if (offset != 0) {
            if (offset < profile.data_base || offset + 16U > 0xFFFFFFFFU) fail("native PAK offset is invalid");
            const Bytes cipher = read_file(profile.path, offset, 16);
            const Bytes plain = crypt_buffer(cipher, profile.password.empty() ? "gameofmir" : profile.password, true, profile.format_version == "geem2lp-v1" ? 96 : 143);
            record.image_type = plain[0];
            record.alpha = plain[3];
            record.width = i16(plain.data() + 4);
            record.height = i16(plain.data() + 6);
            record.origin_x = i16(plain.data() + 8);
            record.origin_y = i16(plain.data() + 10);
            record.packed_size = static_cast<std::uint32_t>(static_cast<std::int32_t>(u32(plain.data() + 12)));
            const std::uint8_t bits = record.image_type == 3 ? 8 : record.image_type == 4 || record.image_type == 5 ? 16 : record.image_type == 6 ? 24 : record.image_type == 7 || record.image_type == 9 ? 32 : 0;
            if (bits == 0 || record.width <= 0 || record.height <= 0) fail("native PAK image header is invalid");
            const std::uint32_t raw_size = dib_stride(bits, record.width) * static_cast<std::uint32_t>(record.height) + (record.alpha ? dib_stride(8, record.width) * static_cast<std::uint32_t>(record.height) : 0U);
            record.data_offset = offset + 16U;
            record.data_length = record.packed_size ? record.packed_size : raw_size;
        }
        result.records.push_back(record);
    }
    return result;
}

Index load_wil_index(const Profile& data_profile, const Profile& index_profile) {
    std::ifstream data_stream(std::filesystem::u8path(data_profile.path), std::ios::binary);
    if (!data_stream) fail("unable to open native WIL data");
    data_stream.seekg(0, std::ios::end);
    const auto data_size = static_cast<std::uint64_t>(data_stream.tellg());
    if (data_size < 64U) fail("native WIL data size is invalid");
    std::ifstream index_stream(std::filesystem::u8path(index_profile.path), std::ios::binary);
    if (!index_stream) fail("unable to open native WZX index");
    index_stream.seekg(0, std::ios::end);
    const auto index_size = static_cast<std::uint64_t>(index_stream.tellg());
    if (index_size < 48U || index_size > 256U * 1024U * 1024U) fail("native WZX index size is invalid");
    const Bytes raw_index = read_file(index_profile.path, 0, index_size);
    const std::uint32_t count = u32(raw_index.data() + 44U);
    if (count > 2000000U || 48U + static_cast<std::uint64_t>(count) * 4U > raw_index.size()) fail("native WZX table is invalid");
    Index result;
    result.magic = data_profile.magic;
    result.records.reserve(count);
    std::size_t candidate_count = 0;
    std::size_t valid_count = 0;
    for (std::uint32_t i = 0; i < count; ++i) {
        Record record;
        record.index = i;
        record.offset = u32(raw_index.data() + 48U + i * 4U);
        if (record.offset < 64U) {
            record.offset = 0;
        } else {
            ++candidate_count;
            try {
                if (static_cast<std::uint64_t>(record.offset) + 16U > data_size) {
                    throw std::runtime_error("native WIL record header is outside the data file");
                }
                const Bytes header = read_file(data_profile.path, record.offset, 16U);
                record.image_type = header[0]; record.alpha = header[3]; record.width = i16(header.data() + 4); record.height = i16(header.data() + 6);
                record.origin_x = i16(header.data() + 8); record.origin_y = i16(header.data() + 10);
                const auto packed = static_cast<std::int32_t>(u32(header.data() + 12));
                record.packed_size = packed > 0 ? static_cast<std::uint32_t>(packed) : 0U;
                const std::uint8_t bits = record.image_type == 3 ? 8 : record.image_type == 4 || record.image_type == 5 ? 16 : record.image_type == 6 ? 24 : record.image_type == 7 || record.image_type == 9 ? 32 : 0;
                if (bits == 0 || record.width <= 0 || record.height <= 0 || record.width > 8192 || record.height > 8192) {
                    throw std::runtime_error("native WIL image header is invalid");
                }
                const std::uint64_t raw_size = static_cast<std::uint64_t>(dib_stride(bits, record.width)) * static_cast<std::uint32_t>(record.height) +
                    (record.alpha ? static_cast<std::uint64_t>(dib_stride(8, record.width)) * static_cast<std::uint32_t>(record.height) : 0U);
                record.data_offset = record.offset + 16U;
                record.data_length = record.packed_size ? record.packed_size : static_cast<std::uint32_t>(raw_size);
                if (raw_size == 0 || raw_size > 128U * 1024U * 1024U ||
                    static_cast<std::uint64_t>(record.data_offset) + record.data_length > data_size) {
                    throw std::runtime_error("native WIL image payload range is invalid");
                }
                ++valid_count;
            } catch (const std::exception&) {
                record = Record{};
                record.index = i;
            }
        }
        result.records.push_back(record);
    }
    if (candidate_count != 0 && valid_count == 0) fail("native WIL index contains no valid records");
    return result;
}

Image decode_image(const Profile& profile, const Record& record, bool transparent_zero) {
    if (record.offset == 0 || record.width <= 0 || record.height <= 0) fail("native asset record is empty");
    if (profile.format_version == "frame-scan-v1") {
        if (record.pixel_format.empty()) fail("native frame record format is missing");
        return decode_gameofmir_frame(profile, record, transparent_zero);
    }
    const std::uint8_t bits = record.image_type == 3 ? 8 : record.image_type == 4 || record.image_type == 5 ? 16 : record.image_type == 6 ? 24 : record.image_type == 7 || record.image_type == 9 ? 32 : 0;
    if (bits == 0) fail("native image record type is unsupported");
    const std::uint32_t color_stride = dib_stride(bits, record.width);
    const std::uint32_t alpha_stride = record.alpha ? dib_stride(8, record.width) : 0U;
    const std::uint32_t height = static_cast<std::uint32_t>(record.height);
    const std::uint64_t expected_size64 =
        (static_cast<std::uint64_t>(color_stride) + alpha_stride) * height;
    if (expected_size64 == 0 || expected_size64 > 128U * 1024U * 1024U) {
        fail("native image payload size is invalid");
    }
    Bytes raw;
    const Bytes stored = read_file(profile.path, record.data_offset, record.data_length);
    if (record.packed_size != 0) {
        std::string error;
        const std::size_t expected_size = static_cast<std::size_t>(expected_size64);
        if (!xiami::compression::inflate_zlib(
                stored.data(), stored.size(), expected_size, 128U * 1024U * 1024U,
                &raw, &error) &&
            !xiami::compression::inflate_raw_deflate(
                stored.data(), stored.size(), expected_size, 128U * 1024U * 1024U,
                &raw, &error)) {
            throw std::runtime_error("native image inflate failed: " + error);
        }
    } else {
        raw = stored;
    }
    if (raw.size() != expected_size64) fail("native image payload is incomplete");
    Image image{static_cast<std::uint32_t>(record.width), height, static_cast<std::uint32_t>(record.width) * 4U, record.origin_x, record.origin_y, Bytes(static_cast<std::size_t>(record.width) * height * 4U)};
    const bool wzl_alpha4 = profile.magic == "WZL" && bits == 16U && record.alpha == 9U;
    for (std::uint32_t y = 0; y < height; ++y) {
        const std::uint32_t source_y = height - y - 1U;
        const std::uint32_t color_pitch = wzl_alpha4 ? color_stride / 2U : color_stride;
        const std::uint32_t alpha_pitch = wzl_alpha4 ? std::max<std::uint32_t>(1U, image.width / 2U) : alpha_stride;
        const std::uint32_t alpha_y = wzl_alpha4 ? y : source_y;
        const unsigned char* color = raw.data() + static_cast<std::size_t>(source_y) * color_pitch;
        const unsigned char* alpha = alpha_stride ? raw.data() + static_cast<std::size_t>(color_pitch) * height + static_cast<std::size_t>(alpha_y) * alpha_pitch : nullptr;
        for (std::uint32_t x = 0; x < image.width; ++x) {
            unsigned char b = 0, g = 0, r = 0, a = 255;
            if (bits == 8) { const unsigned char value = color[x]; const auto& palette = xiami::mir_palette::rgba()[value]; r = palette[0]; g = palette[1]; b = palette[2]; a = alpha ? alpha[x] : palette[3]; if (transparent_zero && value == 0) a = 0; }
            else if (bits == 16) { const std::uint16_t value = u16(color + x * 2U); r = static_cast<unsigned char>(((value >> 11U) & 31U) * 255U / 31U); g = static_cast<unsigned char>(((value >> 5U) & 63U) * 255U / 63U); b = static_cast<unsigned char>((value & 31U) * 255U / 31U); if (wzl_alpha4 && alpha) { const unsigned char packed = alpha[x / 2U]; const unsigned char nibble = x % 2U == 0 ? packed & 15U : (packed >> 4U) & 15U; a = static_cast<unsigned char>(nibble * 16U); } else { a = alpha ? alpha[x] : (transparent_zero && value == 0 ? 0 : 255); } }
            else if (bits == 24) { b = color[x * 3U]; g = color[x * 3U + 1U]; r = color[x * 3U + 2U]; a = alpha ? alpha[x] : (transparent_zero && r == 0 && g == 0 && b == 0 ? 0 : 255); }
            else { b = color[x * 4U]; g = color[x * 4U + 1U]; r = color[x * 4U + 2U]; a = alpha ? alpha[x] : color[x * 4U + 3U]; }
            const std::size_t out = (static_cast<std::size_t>(y) * image.width + x) * 4U;
            image.bgra[out] = b; image.bgra[out + 1U] = g; image.bgra[out + 2U] = r; image.bgra[out + 3U] = a;
        }
    }
    return image;
}

}  // namespace xiami::asset_decoder

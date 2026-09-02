#include "xiami_geepak3_codec.hpp"

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <bcrypt.h>

#include <algorithm>
#include <array>
#include <stdexcept>
#include <string>

#pragma comment(lib, "bcrypt.lib")

namespace xiami::geepak3 {
namespace {

[[noreturn]] void fail(const char* message) { throw std::runtime_error(message); }

constexpr char kDesKeyTableBase64[] =
    "AAAAABAAAAAAAAAgEAAAIAAAAQAQAAEAAAABIBAAASAACAAAEAgAAAAIACAQCAAgAAgBABAIAQAACAEgEAgBICAAAAAwAAAAIAAAIDAAACAgAAEAMAABACAAASAwAAEgIAgAADAIAAAgCAAgMAgAICAIAQAwCAEAIAgBIDAIASAAAAgAEAAIAAAACCAQAAggAAAJABAACQAAAAkgEAAJIAAICAAQCAgAAAgIIBAICCAACAkAEAgJAAAICSAQCAkgIAAIADAACAAgAAggMAAIICAACQAwAAkAIAAJIDAACSAgCAgAMAgIACAICCAwCAggIAgJADAICQAgCAkgMAgJIAAAAAAAAAACACAAAAAgAAIAACAAAAAgAgAgIAAAICACBAAAAAQAAAIEIAAABCAAAgQAIAAEACACBCAgAAQgIAIABAAAAAQAAgAkAAAAJAACAAQgAAAEIAIAJCAAACQgAgQEAAAEBAACBCQAAAQkAAIEBCAABAQgAgQkIAAEJCACAAAAEAAAABIAIAAQACAAEgAAIBAAACASACAgEAAgIBIEAAAQBAAAEgQgABAEIAASBAAgEAQAIBIEICAQBCAgEgAEABAABAASACQAEAAkABIABCAQAAQgEgAkIBAAJCASBAQAEAQEABIEJAAQBCQAEgQEIBAEBCASBCQgEAQkIBIAAAAAAQAAAAAABAABAAQAAAAAAQEAAAEAAAQBAQAEAQIAAAADAAAAAgAEAAMABAACAAABAwAAAQIABAEDAAQBAAIAAAECAAAAAgQAAQIEAAACAAEBAgABAAIEAQECBAECAgAAAwIAAAICBAADAgQAAgIAAQMCAAECAgQBAwIEAQAAAAgBAAAIAAAECAEABAgAAAAJAQAACQAABAkBAAQJAgAACAMAAAgCAAQIAwAECAIAAAkDAAAJAgAECQMABAkAAgAIAQIACAACBAgBAgQIAAIACQECAAkAAgQJAQIECQICAAgDAgAIAgIECAMCBAgCAgAJAwIACQICBAkDAgQJAAAAAAAAEAAAAQAAAAEQAAgAAAAIABAACAEAAAgBEAAAEAAAABAQAAARAAAAERAACBAAAAgQEAAIEQAACBEQAAAAAAQAABAEAAEABAABEAQIAAAECAAQBAgBAAQIARAEABAABAAQEAQAEQAEABEQBAgQAAQIEBAECBEABAgREAQAAAIAAAASAAABAgAAARIACAACAAgAEgAIAQIACAESAAAQAgAAEBIAABECAAAREgAIEAIACBASAAgRAgAIERIAAAACBAAAEgQAAQIEAAESBAgAAgQIABIECAECBAgBEgQAEAIEABASBAARAgQAERIECBACBAgQEgQIEQIECBESBAAAAAAAAAAQAAABAAAAARAEAAAABAAAEAQAAQAEAAEQAAAAIAAAADAAAAEgAAABMAQAACAEAAAwBAABIAQAATAAABAAAAAQEAAAEQAAABEQBAAQAAQAEBAEABEABAAREAAAECAAABAwAAARIAAAETAEABAgBAAQMAQAESAEABEwABAAAAAQABAAEAEAABABEAQQAAAEEAAQBBABAAQQARAAEAAgABAAMAAQASAAEAEwBBAAIAQQADAEEAEgBBABMAAQEAAAEBAQABARAAAQERAEEBAABBAQEAQQEQAEEBEQABAQIAAQEDAAEBEgABARMAQQECAEEBAwBBARIAQQETAAAAAAAAAACAgAAAAIAAAIAAQAAAAEAAgIBAAACAQACAAAAgAAAAIICAACAAgAAggABAIAAAQCCAgEAgAIBAIIAQAAAAEAAAgJAAAACQAACAEEAAABBAAICQQAAAkEAAgBAAIAAQACCAkAAgAJAAIIAQQCAAEEAggJBAIACQQCCAAAAAIAAAAKCAAAAggAAAoABAACAAQACggEAAIIBAAKAAACAgAAAgoIAAICCAACCgAEAgIABAIKCAQCAggEAgoBAAACAQAACgkAAAIJAAAKAQQAAgEEAAoJBAACCQQACgEAAgIBAAIKCQACAgkAAgoBBAICAQQCCgkEAgIJBAIKAAAAAAABAAAAAAgAAAEIAAAAAAEAAQABAAAIAQABCAEQAAAAEAEAABAACAAQAQgAEAAAARABAAEQAAgBEAEIAQAAIAAAASAAAAAoAAABKAAAACABAAEgAQAAKAEAASgBEAAgABABIAAQACgAEAEoABAAIAEQASABEAAoARABKAEAAgAAAAMAAAACCAAAAwgAAAIAAQADAAEAAggBAAMIARACAAAQAwAAEAIIABADCAAQAgABEAMAARACCAEQAwgBAAIgAAADIAAAAigAAAMoAAACIAEAAyABAAIoAQADKAEQAiAAEAMgABACKAAQAygAEAIgARADIAEQAigBEAMoAQAAAAAAAAAEAAAEAAAABAQCAAAAAgAABAIABAACAAQEACAAAAAgAAQAIAQAACAEBAIgAAACIAAEAiAEAAIgBAQgAAAAIAAABCAABAAgAAQEIgAAACIAAAQiAAQAIgAEBCAgAAAgIAAEICAEACAgBAQiIAAAIiAABCIgBAAiIAQEAAgAAAAIAAQACAQAAAgEBAIIAAACCAAEAggEAAIIBAQAKAAAACgABAAoBAAAKAQEAigAAAIoAAQCKAQAAigEBCAIAAAgCAAEIAgEACAIBAQiCAAAIggABCIIBAAiCAQEICgAACAoAAQgKAQAICgEBCIoAAAiKAAEIigEACIoBAQ=";

std::uint32_t load_le32(const unsigned char* p) {
    return static_cast<std::uint32_t>(p[0]) |
        (static_cast<std::uint32_t>(p[1]) << 8U) |
        (static_cast<std::uint32_t>(p[2]) << 16U) |
        (static_cast<std::uint32_t>(p[3]) << 24U);
}

void store_le32(unsigned char* p, std::uint32_t value) {
    p[0] = static_cast<unsigned char>(value);
    p[1] = static_cast<unsigned char>(value >> 8U);
    p[2] = static_cast<unsigned char>(value >> 16U);
    p[3] = static_cast<unsigned char>(value >> 24U);
}

int base64_value(char value) {
    if (value >= 'A' && value <= 'Z') return value - 'A';
    if (value >= 'a' && value <= 'z') return value - 'a' + 26;
    if (value >= '0' && value <= '9') return value - '0' + 52;
    if (value == '+') return 62;
    if (value == '/') return 63;
    return -1;
}

std::array<std::uint32_t, 512> build_des_key_table() {
    Bytes decoded;
    decoded.reserve(2048);
    std::uint32_t accumulator = 0;
    unsigned int bits = 0;
    for (const char* cursor = kDesKeyTableBase64; *cursor && *cursor != '='; ++cursor) {
        const int value = base64_value(*cursor);
        if (value < 0) continue;
        accumulator = (accumulator << 6U) | static_cast<std::uint32_t>(value);
        bits += 6U;
        if (bits >= 8U) {
            bits -= 8U;
            decoded.push_back(static_cast<unsigned char>(accumulator >> bits));
            accumulator &= bits == 0U ? 0U : ((1U << bits) - 1U);
        }
    }
    if (decoded.size() != 2048U) fail("GEEPAK3 DES key table is invalid");
    std::array<std::uint32_t, 512> table{};
    for (std::size_t index = 0; index < table.size(); ++index) {
        table[index] = load_le32(decoded.data() + index * 4U);
    }
    return table;
}

const std::array<std::uint32_t, 512>& des_key_table() {
    static const auto table = build_des_key_table();
    return table;
}

Bytes sha1(const Bytes& input) {
    BCRYPT_ALG_HANDLE algorithm = nullptr;
    BCRYPT_HASH_HANDLE hash = nullptr;
    DWORD object_length = 0;
    DWORD written = 0;
    if (BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA1_ALGORITHM, nullptr, 0) != 0 ||
        BCryptGetProperty(algorithm, BCRYPT_OBJECT_LENGTH, reinterpret_cast<PUCHAR>(&object_length), sizeof(object_length), &written, 0) != 0) {
        if (algorithm) BCryptCloseAlgorithmProvider(algorithm, 0);
        fail("GEEPAK3 SHA1 provider is unavailable");
    }
    Bytes object(object_length);
    if (BCryptCreateHash(algorithm, &hash, object.data(), object_length, nullptr, 0, 0) != 0 ||
        BCryptHashData(hash, const_cast<PUCHAR>(input.data()), static_cast<ULONG>(input.size()), 0) != 0) {
        if (hash) BCryptDestroyHash(hash);
        BCryptCloseAlgorithmProvider(algorithm, 0);
        fail("GEEPAK3 SHA1 hashing failed");
    }
    Bytes output(20);
    const NTSTATUS status = BCryptFinishHash(hash, output.data(), static_cast<ULONG>(output.size()), 0);
    BCryptDestroyHash(hash);
    BCryptCloseAlgorithmProvider(algorithm, 0);
    if (status != 0) fail("GEEPAK3 SHA1 finalization failed");
    return output;
}

Bytes encrypt_des_block(const Bytes& key8, const unsigned char* block8) {
    BCRYPT_ALG_HANDLE algorithm = nullptr;
    BCRYPT_KEY_HANDLE key = nullptr;
    DWORD object_length = 0;
    DWORD written = 0;
    if (BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_3DES_ALGORITHM, nullptr, 0) != 0 ||
        BCryptSetProperty(algorithm, BCRYPT_CHAINING_MODE,
            reinterpret_cast<PUCHAR>(const_cast<wchar_t*>(BCRYPT_CHAIN_MODE_ECB)),
            static_cast<ULONG>(sizeof(BCRYPT_CHAIN_MODE_ECB)), 0) != 0 ||
        BCryptGetProperty(algorithm, BCRYPT_OBJECT_LENGTH, reinterpret_cast<PUCHAR>(&object_length), sizeof(object_length), &written, 0) != 0) {
        if (algorithm) BCryptCloseAlgorithmProvider(algorithm, 0);
        fail("GEEPAK3 3DES provider is unavailable");
    }
    Bytes object(object_length);
    Bytes key24(24);
    for (std::size_t offset = 0; offset < key24.size(); offset += 8U) {
        std::copy(key8.begin(), key8.end(), key24.begin() + static_cast<std::ptrdiff_t>(offset));
    }
    if (BCryptGenerateSymmetricKey(algorithm, &key, object.data(), object_length,
            key24.data(), static_cast<ULONG>(key24.size()), 0) != 0) {
        BCryptCloseAlgorithmProvider(algorithm, 0);
        fail("GEEPAK3 3DES key creation failed");
    }
    Bytes output(8);
    ULONG output_length = 0;
    const NTSTATUS status = BCryptEncrypt(key, const_cast<PUCHAR>(block8), 8, nullptr,
        nullptr, 0, output.data(), static_cast<ULONG>(output.size()), &output_length, 0);
    BCryptDestroyKey(key);
    BCryptCloseAlgorithmProvider(algorithm, 0);
    if (status != 0 || output_length != output.size()) fail("GEEPAK3 3DES encryption failed");
    return output;
}

std::uint32_t rotate_left(std::uint32_t value, unsigned int bits) {
    return (value << bits) | (value >> (32U - bits));
}

std::uint32_t rotate_right28(std::uint32_t value, unsigned int bits) {
    return ((value >> bits) | (value << (28U - bits))) & 0x0FFFFFFFU;
}

std::array<std::uint32_t, 2> swap_right(
    std::uint32_t a, std::uint32_t b, std::uint32_t mask, unsigned int shift) {
    const std::uint32_t temporary = ((a >> shift) ^ b) & mask;
    b ^= temporary;
    a ^= temporary << shift;
    return {a, b};
}

std::array<std::uint32_t, 2> swap_left(
    std::uint32_t a, std::uint32_t mask, int shift) {
    const unsigned int count = static_cast<unsigned int>(16 - shift) & 31U;
    const std::uint32_t temporary = ((a << count) ^ a) & mask;
    return {(temporary >> count) ^ (a ^ temporary), temporary};
}

std::array<std::uint32_t, 32> expand_des_key(const Bytes& key8) {
    if (key8.size() != 8U) fail("GEEPAK3 DES derivation key is invalid");
    const auto& table = des_key_table();
    std::uint32_t left = load_le32(key8.data());
    std::uint32_t right = load_le32(key8.data() + 4U);
    auto pair = swap_right(right, left, 0x0F0F0F0FU, 4U); right = pair[0]; left = pair[1];
    left = swap_left(left, 0xCCCC0000U, -2)[0];
    right = swap_left(right, 0xCCCC0000U, -2)[0];
    pair = swap_right(right, left, 0x55555555U, 1U); right = pair[0]; left = pair[1];
    pair = swap_right(left, right, 0x00FF00FFU, 8U); left = pair[0]; right = pair[1];
    pair = swap_right(right, left, 0x55555555U, 1U); right = pair[0]; left = pair[1];
    right = ((right & 0xFFU) << 16U) | (right & 0xFF00U) |
        ((right & 0xFF0000U) >> 16U) | ((left & 0xF0000000U) >> 4U);
    left &= 0x0FFFFFFFU;

    constexpr std::array<unsigned char, 16> rotate_two = {
        0, 0, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 0};
    std::array<std::uint32_t, 32> subkeys{};
    for (std::size_t index = 0; index < 16U; ++index) {
        const unsigned int rotation = rotate_two[index] ? 2U : 1U;
        left = rotate_right28(left, rotation);
        right = rotate_right28(right, rotation);
        const std::uint32_t t0 =
            table[64U + (((left >> 6U) & 3U) | ((left >> 7U) & 60U))] |
            table[left & 63U] |
            table[128U + (((left >> 13U) & 15U) | ((left >> 14U) & 48U))] |
            table[192U + (((left >> 20U) & 1U) | ((left >> 21U) & 6U) | ((left >> 22U) & 56U))];
        const std::uint32_t t1 =
            table[320U + (((right >> 7U) & 3U) | ((right >> 8U) & 60U))] |
            table[256U + (right & 63U)] |
            table[384U + ((right >> 15U) & 63U)] |
            table[448U + (((right >> 21U) & 15U) | ((right >> 22U) & 48U))];
        subkeys[index * 2U] = rotate_left((t1 << 16U) | (t0 & 0xFFFFU), 2U);
        subkeys[index * 2U + 1U] = rotate_left((t0 >> 16U) | (t1 & 0xFFFF0000U), 6U);
    }
    return subkeys;
}

std::array<std::uint32_t, 3> mix_a(std::uint32_t a, std::uint32_t b, std::uint32_t c) {
    a = a - b - c; a ^= c >> 8U; b = b - c - a; b ^= a << 9U; c = c - a - b; c ^= b >> 13U;
    a = a - b - c; a ^= c >> 9U; b = b - c - a; b ^= a << 6U; c = c - a - b; c ^= b >> 4U;
    a = a - b - c; a ^= c >> 8U; b = b - c - a; b ^= a << 3U; c = c - a - b; c ^= b >> 15U;
    return {a, b, c};
}

std::array<std::uint32_t, 3> mix_a_tail(std::uint32_t a, std::uint32_t b, std::uint32_t c) {
    a = a - b - c; a ^= c >> 4U; b = b - c - a; b ^= a << 9U; c = c - a - b; c ^= b >> 19U;
    a = a - b - c; a ^= c >> 11U; b = b - c - a; b ^= a << 14U; c = c - a - b; c ^= b >> 5U;
    a = a - b - c; a ^= c >> 9U; b = b - c - a; b ^= a << 12U; c = c - a - b; c ^= b >> 3U;
    return {a, b, c};
}

std::array<std::uint32_t, 3> mix_b(std::uint32_t a, std::uint32_t b, std::uint32_t c) {
    a = a - b - c; a ^= c >> 9U; b = b - c - a; b ^= a << 3U; c = c - a - b; c ^= b >> 12U;
    a = a - b - c; a ^= c >> 11U; b = b - c - a; b &= a << 7U; c = c - a - b; c ^= b >> 10U;
    a = a - b - c; a ^= c >> 4U; b = b - c - a; b ^= a << 1U; c = c - a - b; c ^= b >> 8U;
    return {a, b, c};
}

std::array<std::uint32_t, 3> mix_b_tail(std::uint32_t a, std::uint32_t b, std::uint32_t c) {
    a = a - b - c; a ^= c >> 11U; b = b - c - a; b ^= a << 1U; c = c - a - b; c ^= b >> 15U;
    a = a - b - c; a ^= c >> 2U; b = b - c - a; b ^= a << 7U; c = c - a - b; c ^= b >> 9U;
    a = a - b - c; a ^= c >> 1U; b = b - c - a; b ^= a << 3U; c = c - a - b; c |= b >> 5U;
    return {a, b, c};
}

class AesEcbKey final {
public:
    explicit AesEcbKey(const AesKey& key) {
        DWORD written = 0;
        if (BCryptOpenAlgorithmProvider(&algorithm_, BCRYPT_AES_ALGORITHM, nullptr, 0) != 0 ||
            BCryptSetProperty(algorithm_, BCRYPT_CHAINING_MODE,
                reinterpret_cast<PUCHAR>(const_cast<wchar_t*>(BCRYPT_CHAIN_MODE_ECB)),
                static_cast<ULONG>(sizeof(BCRYPT_CHAIN_MODE_ECB)), 0) != 0 ||
            BCryptGetProperty(algorithm_, BCRYPT_OBJECT_LENGTH, reinterpret_cast<PUCHAR>(&object_length_), sizeof(object_length_), &written, 0) != 0) {
            close();
            fail("GEEPAK3 AES provider is unavailable");
        }
        object_.resize(object_length_);
        if (BCryptGenerateSymmetricKey(algorithm_, &key_, object_.data(), object_length_,
                const_cast<PUCHAR>(key.data()), static_cast<ULONG>(key.size()), 0) != 0) {
            close();
            fail("GEEPAK3 AES key creation failed");
        }
    }

    ~AesEcbKey() { close(); }
    AesEcbKey(const AesEcbKey&) = delete;
    AesEcbKey& operator=(const AesEcbKey&) = delete;

    std::array<unsigned char, 16> encrypt(const std::array<unsigned char, 16>& block) const {
        std::array<unsigned char, 16> output{};
        ULONG output_length = 0;
        const NTSTATUS status = BCryptEncrypt(key_, const_cast<PUCHAR>(block.data()),
            static_cast<ULONG>(block.size()), nullptr, nullptr, 0, output.data(),
            static_cast<ULONG>(output.size()), &output_length, 0);
        if (status != 0 || output_length != output.size()) fail("GEEPAK3 AES encryption failed");
        return output;
    }

private:
    void close() noexcept {
        if (key_) BCryptDestroyKey(key_);
        if (algorithm_) BCryptCloseAlgorithmProvider(algorithm_, 0);
        key_ = nullptr;
        algorithm_ = nullptr;
    }

    BCRYPT_ALG_HANDLE algorithm_ = nullptr;
    BCRYPT_KEY_HANDLE key_ = nullptr;
    DWORD object_length_ = 0;
    Bytes object_;
};

}  // namespace

KeyMaterial derive_key_material(const Bytes& password) {
    const Bytes digest = sha1(password);
    const Bytes des_key(digest.begin(), digest.begin() + 8U);
    const auto subkeys = expand_des_key(des_key);

    std::array<unsigned char, 20> iv{};
    iv.fill(0x60U);
    const Bytes encrypted_iv = encrypt_des_block(des_key, iv.data());
    std::copy(encrypted_iv.begin(), encrypted_iv.end(), iv.begin());

    KeyMaterial material;
    for (std::size_t index = 0; index < 32U; ++index) {
        material.words[index * 2U] = subkeys[31U - index];
    }
    constexpr std::array<std::size_t, 5> iv_slots = {1U, 7U, 11U, 13U, 15U};
    for (std::size_t index = 0; index < iv_slots.size(); ++index) {
        material.words[iv_slots[index]] = load_le32(iv.data() + index * 4U);
    }

    std::size_t remaining = 32U;
    std::size_t key_index = 0;
    std::uint32_t a = 0xBCA24215U;
    std::uint32_t b = 0xBD194331U;
    std::uint32_t c = 0xB99EAC12U;
    while (remaining >= 3U) {
        a += subkeys[key_index];
        b += subkeys[key_index + 1U];
        c += subkeys[key_index + 2U];
        const auto mixed = mix_a(a, b, c);
        a = mixed[0]; b = mixed[1]; c = mixed[2];
        key_index += 3U;
        remaining -= 3U;
    }
    c += 32U;
    if (remaining >= 1U) a += subkeys[key_index];
    if (remaining >= 2U) a += subkeys[key_index + 1U];
    auto mixed = mix_a_tail(a, b, c);
    material.words[3] = mixed[0];
    material.words[5] = mixed[1];
    material.words[9] = mixed[2];

    std::uint32_t x = 0x4E67C6A7U;
    for (std::size_t index = 0; index < 17U; ++index) {
        const std::uint32_t value = material.words[index] + (x << 5U) + (x >> 2U);
        x ^= value;
    }
    material.words[17] = x;
    x = 5381U;
    for (std::size_t index = 0; index < 18U; ++index) {
        x = material.words[index] + x + (x << 5U);
    }
    material.words[19] = x;

    for (std::size_t outer = 10U; outer < 32U; ++outer) {
        remaining = outer * 2U;
        key_index = 0;
        a = 0x16B997C8U;
        b = 0x48744D94U;
        c = 0xBA06742FU;
        while (remaining >= 3U) {
            a += material.words[key_index];
            b += material.words[key_index + 1U];
            c += material.words[key_index + 2U];
            mixed = mix_b(a, b, c);
            a = mixed[0]; b = mixed[1]; c = mixed[2];
            key_index += 3U;
            remaining -= 3U;
        }
        c += static_cast<std::uint32_t>(outer * 2U);
        if (remaining >= 1U) a += material.words[key_index];
        if (remaining >= 2U) a += material.words[key_index + 1U];
        mixed = mix_b_tail(a, b, c);
        material.words[outer * 2U + 1U] = mixed[2];
    }

    for (std::size_t index = 0; index < material.words.size(); ++index) {
        store_le32(material.key_block.data() + index * 4U, material.words[index]);
    }
    return material;
}

Bytes aes_ctr_crypt(const AesKey& key, const Bytes& data) {
    AesEcbKey cipher(key);
    std::array<unsigned char, 16> counter{};
    Bytes output(data.size());
    for (std::size_t offset = 0; offset < data.size(); offset += 16U) {
        const auto stream = cipher.encrypt(counter);
        const std::size_t count = std::min<std::size_t>(16U, data.size() - offset);
        for (std::size_t index = 0; index < count; ++index) {
            output[offset + index] = data[offset + index] ^ stream[index];
        }
        for (int index = 7; index >= 0; --index) {
            if (++counter[static_cast<std::size_t>(index)] != 0U) break;
        }
    }
    return output;
}

std::uint32_t decode_directory_offset(
    std::uint32_t encoded_offset,
    std::uint32_t index,
    const KeyWords& key_words) {
    return encoded_offset ^ key_words[index & 63U] ^ ~index;
}

AesKey resource_header_key(const KeyWords& key_words, std::uint32_t index) {
    const std::uint32_t slot = index & 63U;
    const std::array<std::uint32_t, 4> words = {
        key_words[slot] ^ key_words[(slot + 14U) & 63U],
        key_words[(slot + 12U) & 63U] & key_words[(slot + 19U) & 63U],
        key_words[(slot + 28U) & 63U] ^ ~key_words[(slot + 10U) & 63U],
        key_words[(slot + 1U) & 63U]};
    AesKey key{};
    for (std::size_t word = 0; word < words.size(); ++word) {
        store_le32(key.data() + word * 4U, words[word]);
    }
    return key;
}

ResourceHeader decode_resource_header(
    const ResourceHeader& encrypted_header,
    const KeyWords& key_words,
    std::uint32_t index) {
    const Bytes input(encrypted_header.begin(), encrypted_header.end());
    const Bytes output = aes_ctr_crypt(resource_header_key(key_words, index), input);
    ResourceHeader header{};
    std::copy(output.begin(), output.end(), header.begin());
    return header;
}

}  // namespace xiami::geepak3

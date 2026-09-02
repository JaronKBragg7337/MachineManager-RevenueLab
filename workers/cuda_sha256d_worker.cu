// Focused CUDA + Stratum V1 worker for the Revenue Lab acceptance path.
//
// This executable is intentionally small and dependency-light. It speaks only
// the normal line-delimited Stratum messages needed for a first worker,
// performs SHA-256d on the installed CUDA device, and emits an allowlisted
// aggregate progress stream. It never prints credentials or raw protocol
// messages.

#ifndef NOMINMAX
#define NOMINMAX
#endif

#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#pragma comment(lib, "Ws2_32.lib")
#else
#include <arpa/inet.h>
#include <fcntl.h>
#include <netdb.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <unistd.h>
#endif

#include <cuda_runtime.h>

#include <algorithm>
#include <array>
#include <chrono>
#include <cctype>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <sstream>
#include <string>
#include <vector>

namespace {

// ---------------------------------------------------------------------------
// Device SHA-256d implementation
// ---------------------------------------------------------------------------

__device__ __constant__ uint32_t kInitialState[8] = {
    0x6a09e667u, 0xbb67ae85u, 0x3c6ef372u, 0xa54ff53au,
    0x510e527fu, 0x9b05688cu, 0x1f83d9abu, 0x5be0cd19u,
};

__device__ __constant__ uint32_t kRoundConstants[64] = {
    0x428a2f98u, 0x71374491u, 0xb5c0fbcfu, 0xe9b5dba5u, 0x3956c25bu,
    0x59f111f1u, 0x923f82a4u, 0xab1c5ed5u, 0xd807aa98u, 0x12835b01u,
    0x243185beu, 0x550c7dc3u, 0x72be5d74u, 0x80deb1feu, 0x9bdc06a7u,
    0xc19bf174u, 0xe49b69c1u, 0xefbe4786u, 0x0fc19dc6u, 0x240ca1ccu,
    0x2de92c6fu, 0x4a7484aau, 0x5cb0a9dcu, 0x76f988dau, 0x983e5152u,
    0xa831c66du, 0xb00327c8u, 0xbf597fc7u, 0xc6e00bf3u, 0xd5a79147u,
    0x06ca6351u, 0x14292967u, 0x27b70a85u, 0x2e1b2138u, 0x4d2c6dfcu,
    0x53380d13u, 0x650a7354u, 0x766a0abbu, 0x81c2c92eu, 0x92722c85u,
    0xa2bfe8a1u, 0xa81a664bu, 0xc24b8b70u, 0xc76c51a3u, 0xd192e819u,
    0xd6990624u, 0xf40e3585u, 0x106aa070u, 0x19a4c116u, 0x1e376c08u,
    0x2748774cu, 0x34b0bcb5u, 0x391c0cb3u, 0x4ed8aa4au, 0x5b9cca4fu,
    0x682e6ff3u, 0x748f82eeu, 0x78a5636fu, 0x84c87814u, 0x8cc70208u,
    0x90befffau, 0xa4506cebu, 0xbef9a3f7u, 0xc67178f2u,
};

__constant__ uint8_t d_header[80];
__constant__ uint8_t d_target[32];

__device__ __forceinline__ uint32_t rotate_right(uint32_t value, unsigned amount) {
    return (value >> amount) | (value << (32u - amount));
}

__device__ __forceinline__ uint32_t choose(uint32_t e, uint32_t f, uint32_t g) {
    return (e & f) ^ (~e & g);
}

__device__ __forceinline__ uint32_t majority(uint32_t a, uint32_t b, uint32_t c) {
    return (a & b) ^ (a & c) ^ (b & c);
}

__device__ __forceinline__ uint32_t big_sigma_zero(uint32_t value) {
    return rotate_right(value, 2u) ^ rotate_right(value, 13u) ^ rotate_right(value, 22u);
}

__device__ __forceinline__ uint32_t big_sigma_one(uint32_t value) {
    return rotate_right(value, 6u) ^ rotate_right(value, 11u) ^ rotate_right(value, 25u);
}

__device__ __forceinline__ uint32_t small_sigma_zero(uint32_t value) {
    return rotate_right(value, 7u) ^ rotate_right(value, 18u) ^ (value >> 3u);
}

__device__ __forceinline__ uint32_t small_sigma_one(uint32_t value) {
    return rotate_right(value, 17u) ^ rotate_right(value, 19u) ^ (value >> 10u);
}

__device__ __forceinline__ uint32_t read_big_endian(const uint8_t* bytes) {
    return (static_cast<uint32_t>(bytes[0]) << 24u) |
           (static_cast<uint32_t>(bytes[1]) << 16u) |
           (static_cast<uint32_t>(bytes[2]) << 8u) |
           static_cast<uint32_t>(bytes[3]);
}

__device__ __forceinline__ void write_big_endian(uint8_t* bytes, uint32_t value) {
    bytes[0] = static_cast<uint8_t>(value >> 24u);
    bytes[1] = static_cast<uint8_t>(value >> 16u);
    bytes[2] = static_cast<uint8_t>(value >> 8u);
    bytes[3] = static_cast<uint8_t>(value);
}

__device__ __forceinline__ void compress(uint32_t state[8], const uint8_t* block) {
    uint32_t schedule[64];
    for (unsigned index = 0; index < 16; ++index) {
        schedule[index] = read_big_endian(block + index * 4u);
    }
    for (unsigned index = 16; index < 64; ++index) {
        schedule[index] = small_sigma_one(schedule[index - 2u]) + schedule[index - 7u] +
                          small_sigma_zero(schedule[index - 15u]) + schedule[index - 16u];
    }

    uint32_t a = state[0];
    uint32_t b = state[1];
    uint32_t c = state[2];
    uint32_t d = state[3];
    uint32_t e = state[4];
    uint32_t f = state[5];
    uint32_t g = state[6];
    uint32_t h = state[7];
    for (unsigned index = 0; index < 64; ++index) {
        const uint32_t temporary_one = h + big_sigma_one(e) + choose(e, f, g) +
                                       kRoundConstants[index] + schedule[index];
        const uint32_t temporary_two = big_sigma_zero(a) + majority(a, b, c);
        h = g;
        g = f;
        f = e;
        e = d + temporary_one;
        d = c;
        c = b;
        b = a;
        a = temporary_one + temporary_two;
    }
    state[0] += a;
    state[1] += b;
    state[2] += c;
    state[3] += d;
    state[4] += e;
    state[5] += f;
    state[6] += g;
    state[7] += h;
}

__device__ __forceinline__ void sha256d_header(uint32_t nonce, uint8_t digest[32]) {
    uint8_t padded_header[128] = {};
    for (unsigned index = 0; index < 80; ++index) {
        padded_header[index] = d_header[index];
    }
    padded_header[76] = static_cast<uint8_t>(nonce);
    padded_header[77] = static_cast<uint8_t>(nonce >> 8u);
    padded_header[78] = static_cast<uint8_t>(nonce >> 16u);
    padded_header[79] = static_cast<uint8_t>(nonce >> 24u);
    padded_header[80] = 0x80u;
    padded_header[126] = 0x02u;
    padded_header[127] = 0x80u;

    uint32_t first_state[8];
    for (unsigned index = 0; index < 8; ++index) {
        first_state[index] = kInitialState[index];
    }
    compress(first_state, padded_header);
    compress(first_state, padded_header + 64);

    uint8_t first_digest[32];
    for (unsigned index = 0; index < 8; ++index) {
        write_big_endian(first_digest + index * 4u, first_state[index]);
    }

    uint8_t second_block[64] = {};
    for (unsigned index = 0; index < 32; ++index) {
        second_block[index] = first_digest[index];
    }
    second_block[32] = 0x80u;
    second_block[62] = 0x01u;
    second_block[63] = 0x00u;

    uint32_t second_state[8];
    for (unsigned index = 0; index < 8; ++index) {
        second_state[index] = kInitialState[index];
    }
    compress(second_state, second_block);
    for (unsigned index = 0; index < 8; ++index) {
        write_big_endian(digest + index * 4u, second_state[index]);
    }
}

__device__ __forceinline__ bool meets_target(const uint8_t digest[32]) {
    // The raw SHA-256 digest bytes are the little-endian byte representation
    // of Bitcoin's uint256 comparison value. Compare from its high byte down.
    for (int index = 31; index >= 0; --index) {
        if (digest[index] < d_target[index]) return true;
        if (digest[index] > d_target[index]) return false;
    }
    return true;
}

__global__ void scan_nonces(uint32_t starting_nonce, uint32_t count,
                            uint32_t* found_flag, uint32_t* found_nonce,
                            uint8_t* found_digest) {
    const uint64_t thread_id = static_cast<uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
    const uint64_t thread_count = static_cast<uint64_t>(gridDim.x) * blockDim.x;
    for (uint64_t offset = thread_id; offset < count; offset += thread_count) {
        const uint32_t nonce = starting_nonce + static_cast<uint32_t>(offset);
        uint8_t digest[32];
        sha256d_header(nonce, digest);
        if (meets_target(digest) && atomicCAS(found_flag, 0u, 1u) == 0u) {
            *found_nonce = nonce;
            for (unsigned index = 0; index < 32; ++index) {
                found_digest[index] = digest[index];
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Small JSON value/parser used only at the Stratum message boundary
// ---------------------------------------------------------------------------

struct JsonValue {
    enum class Kind { Null, Boolean, Number, String, Array, Object };
    Kind kind = Kind::Null;
    bool boolean_value = false;
    long double number_value = 0.0L;
    std::string string_value;
    std::vector<JsonValue> array_value;
    std::map<std::string, JsonValue> object_value;
};

class JsonParser {
public:
    explicit JsonParser(const std::string& input) : input_(input) {}

    bool parse(JsonValue* output) {
        if (output == nullptr) return false;
        skip_space();
        if (!parse_value(output)) return false;
        skip_space();
        return position_ == input_.size();
    }

private:
    const std::string& input_;
    size_t position_ = 0;

    void skip_space() {
        while (position_ < input_.size() &&
               (input_[position_] == ' ' || input_[position_] == '\t' ||
                input_[position_] == '\r' || input_[position_] == '\n')) {
            ++position_;
        }
    }

    bool consume(char expected) {
        skip_space();
        if (position_ >= input_.size() || input_[position_] != expected) return false;
        ++position_;
        return true;
    }

    static int hex_value(char value) {
        if (value >= '0' && value <= '9') return value - '0';
        if (value >= 'a' && value <= 'f') return value - 'a' + 10;
        if (value >= 'A' && value <= 'F') return value - 'A' + 10;
        return -1;
    }

    bool parse_string(std::string* output) {
        if (output == nullptr || !consume('"')) return false;
        output->clear();
        while (position_ < input_.size()) {
            const char value = input_[position_++];
            if (value == '"') return true;
            if (static_cast<unsigned char>(value) < 0x20u) return false;
            if (value != '\\') {
                output->push_back(value);
                continue;
            }
            if (position_ >= input_.size()) return false;
            const char escaped = input_[position_++];
            switch (escaped) {
                case '"': output->push_back('"'); break;
                case '\\': output->push_back('\\'); break;
                case '/': output->push_back('/'); break;
                case 'b': output->push_back('\b'); break;
                case 'f': output->push_back('\f'); break;
                case 'n': output->push_back('\n'); break;
                case 'r': output->push_back('\r'); break;
                case 't': output->push_back('\t'); break;
                case 'u': {
                    if (position_ + 4 > input_.size()) return false;
                    int codepoint = 0;
                    for (int index = 0; index < 4; ++index) {
                        const int digit = hex_value(input_[position_++]);
                        if (digit < 0) return false;
                        codepoint = (codepoint << 4) | digit;
                    }
                    if (codepoint <= 0x7f) {
                        output->push_back(static_cast<char>(codepoint));
                    } else if (codepoint <= 0x7ff) {
                        output->push_back(static_cast<char>(0xc0 | (codepoint >> 6)));
                        output->push_back(static_cast<char>(0x80 | (codepoint & 0x3f)));
                    } else {
                        output->push_back(static_cast<char>(0xe0 | (codepoint >> 12)));
                        output->push_back(static_cast<char>(0x80 | ((codepoint >> 6) & 0x3f)));
                        output->push_back(static_cast<char>(0x80 | (codepoint & 0x3f)));
                    }
                    break;
                }
                default: return false;
            }
        }
        return false;
    }

    bool parse_number(JsonValue* output) {
        const size_t start = position_;
        if (position_ < input_.size() && input_[position_] == '-') ++position_;
        if (position_ >= input_.size()) return false;
        if (input_[position_] == '0') {
            ++position_;
        } else {
            if (!std::isdigit(static_cast<unsigned char>(input_[position_]))) return false;
            while (position_ < input_.size() &&
                   std::isdigit(static_cast<unsigned char>(input_[position_]))) {
                ++position_;
            }
        }
        if (position_ < input_.size() && input_[position_] == '.') {
            ++position_;
            if (position_ >= input_.size() ||
                !std::isdigit(static_cast<unsigned char>(input_[position_]))) return false;
            while (position_ < input_.size() &&
                   std::isdigit(static_cast<unsigned char>(input_[position_]))) {
                ++position_;
            }
        }
        if (position_ < input_.size() && (input_[position_] == 'e' || input_[position_] == 'E')) {
            ++position_;
            if (position_ < input_.size() && (input_[position_] == '+' || input_[position_] == '-')) {
                ++position_;
            }
            if (position_ >= input_.size() ||
                !std::isdigit(static_cast<unsigned char>(input_[position_]))) return false;
            while (position_ < input_.size() &&
                   std::isdigit(static_cast<unsigned char>(input_[position_]))) {
                ++position_;
            }
        }
        char* end = nullptr;
        const std::string token = input_.substr(start, position_ - start);
        const long double value = std::strtold(token.c_str(), &end);
        if (end == token.c_str() || *end != '\0') return false;
        output->kind = JsonValue::Kind::Number;
        output->number_value = value;
        return true;
    }

    bool parse_array(JsonValue* output) {
        if (!consume('[')) return false;
        output->kind = JsonValue::Kind::Array;
        output->array_value.clear();
        skip_space();
        if (position_ < input_.size() && input_[position_] == ']') {
            ++position_;
            return true;
        }
        while (true) {
            JsonValue item;
            if (!parse_value(&item)) return false;
            output->array_value.push_back(std::move(item));
            skip_space();
            if (position_ < input_.size() && input_[position_] == ']') {
                ++position_;
                return true;
            }
            if (!consume(',')) return false;
        }
    }

    bool parse_object(JsonValue* output) {
        if (!consume('{')) return false;
        output->kind = JsonValue::Kind::Object;
        output->object_value.clear();
        skip_space();
        if (position_ < input_.size() && input_[position_] == '}') {
            ++position_;
            return true;
        }
        while (true) {
            std::string key;
            if (!parse_string(&key) || !consume(':')) return false;
            JsonValue value;
            if (!parse_value(&value)) return false;
            output->object_value.emplace(std::move(key), std::move(value));
            skip_space();
            if (position_ < input_.size() && input_[position_] == '}') {
                ++position_;
                return true;
            }
            if (!consume(',')) return false;
        }
    }

    bool parse_value(JsonValue* output) {
        skip_space();
        if (position_ >= input_.size() || output == nullptr) return false;
        const char first = input_[position_];
        if (first == '"') {
            output->kind = JsonValue::Kind::String;
            return parse_string(&output->string_value);
        }
        if (first == '{') return parse_object(output);
        if (first == '[') return parse_array(output);
        if (first == '-' || std::isdigit(static_cast<unsigned char>(first))) {
            return parse_number(output);
        }
        if (input_.compare(position_, 4, "true") == 0) {
            position_ += 4;
            output->kind = JsonValue::Kind::Boolean;
            output->boolean_value = true;
            return true;
        }
        if (input_.compare(position_, 5, "false") == 0) {
            position_ += 5;
            output->kind = JsonValue::Kind::Boolean;
            output->boolean_value = false;
            return true;
        }
        if (input_.compare(position_, 4, "null") == 0) {
            position_ += 4;
            output->kind = JsonValue::Kind::Null;
            return true;
        }
        return false;
    }
};

const JsonValue* object_field(const JsonValue& object, const char* key) {
    if (object.kind != JsonValue::Kind::Object || key == nullptr) return nullptr;
    const auto found = object.object_value.find(key);
    return found == object.object_value.end() ? nullptr : &found->second;
}

bool string_value(const JsonValue* value, std::string* output) {
    if (value == nullptr || output == nullptr || value->kind != JsonValue::Kind::String) return false;
    *output = value->string_value;
    return true;
}

bool bool_value(const JsonValue* value, bool* output) {
    if (value == nullptr || output == nullptr || value->kind != JsonValue::Kind::Boolean) return false;
    *output = value->boolean_value;
    return true;
}

bool integer_value(const JsonValue* value, uint64_t* output) {
    if (value == nullptr || output == nullptr || value->kind != JsonValue::Kind::Number ||
        value->number_value < 0.0L || value->number_value > static_cast<long double>(UINT64_MAX)) {
        return false;
    }
    const long double rounded = std::floor(value->number_value);
    if (rounded != value->number_value) return false;
    *output = static_cast<uint64_t>(rounded);
    return true;
}

std::string json_escape(const std::string& value) {
    std::ostringstream output;
    for (const unsigned char character : value) {
        switch (character) {
            case '"': output << "\\\""; break;
            case '\\': output << "\\\\"; break;
            case '\b': output << "\\b"; break;
            case '\f': output << "\\f"; break;
            case '\n': output << "\\n"; break;
            case '\r': output << "\\r"; break;
            case '\t': output << "\\t"; break;
            default:
                if (character < 0x20u) {
                    output << "\\u" << std::hex << std::setw(4) << std::setfill('0')
                           << static_cast<unsigned>(character) << std::dec;
                } else {
                    output << static_cast<char>(character);
                }
        }
    }
    return output.str();
}

std::string request_json(uint64_t id, const std::string& method,
                         const std::vector<std::string>& params) {
    std::ostringstream output;
    output << "{\"id\":" << id << ",\"method\":\"" << json_escape(method)
           << "\",\"params\":[";
    for (size_t index = 0; index < params.size(); ++index) {
        if (index != 0) output << ',';
        output << "\"" << json_escape(params[index]) << "\"";
    }
    output << "]}\n";
    return output.str();
}

bool message_id_is(const JsonValue& message, uint64_t expected) {
    const JsonValue* id = object_field(message, "id");
    if (id == nullptr) return false;
    return id->kind == JsonValue::Kind::Number && id->number_value == static_cast<long double>(expected);
}

bool method_is(const JsonValue& message, const char* expected) {
    std::string method;
    return string_value(object_field(message, "method"), &method) && method == expected;
}

// ---------------------------------------------------------------------------
// Hex, SHA-256, and Bitcoin header helpers
// ---------------------------------------------------------------------------

int hex_digit(char value) {
    if (value >= '0' && value <= '9') return value - '0';
    if (value >= 'a' && value <= 'f') return value - 'a' + 10;
    if (value >= 'A' && value <= 'F') return value - 'A' + 10;
    return -1;
}

bool decode_hex(const std::string& value, std::vector<uint8_t>* output, size_t expected_bytes = 0,
                bool allow_empty = false) {
    if (output == nullptr || value.size() % 2 != 0 || (!allow_empty && value.empty()) ||
        (expected_bytes != 0 && value.size() != expected_bytes * 2)) {
        return false;
    }
    output->clear();
    output->reserve(value.size() / 2);
    for (size_t index = 0; index < value.size(); index += 2) {
        const int high = hex_digit(value[index]);
        const int low = hex_digit(value[index + 1]);
        if (high < 0 || low < 0) return false;
        output->push_back(static_cast<uint8_t>((high << 4) | low));
    }
    return true;
}

std::string encode_hex(const uint8_t* bytes, size_t length) {
    static constexpr char digits[] = "0123456789abcdef";
    std::string output;
    output.reserve(length * 2);
    for (size_t index = 0; index < length; ++index) {
        output.push_back(digits[bytes[index] >> 4]);
        output.push_back(digits[bytes[index] & 0x0f]);
    }
    return output;
}

std::string encode_hex(const std::vector<uint8_t>& bytes) {
    return encode_hex(bytes.data(), bytes.size());
}

uint32_t rotate_right_host(uint32_t value, unsigned amount) {
    return (value >> amount) | (value << (32u - amount));
}

constexpr uint32_t kHostRoundConstants[64] = {
    0x428a2f98u, 0x71374491u, 0xb5c0fbcfu, 0xe9b5dba5u, 0x3956c25bu,
    0x59f111f1u, 0x923f82a4u, 0xab1c5ed5u, 0xd807aa98u, 0x12835b01u,
    0x243185beu, 0x550c7dc3u, 0x72be5d74u, 0x80deb1feu, 0x9bdc06a7u,
    0xc19bf174u, 0xe49b69c1u, 0xefbe4786u, 0x0fc19dc6u, 0x240ca1ccu,
    0x2de92c6fu, 0x4a7484aau, 0x5cb0a9dcu, 0x76f988dau, 0x983e5152u,
    0xa831c66du, 0xb00327c8u, 0xbf597fc7u, 0xc6e00bf3u, 0xd5a79147u,
    0x06ca6351u, 0x14292967u, 0x27b70a85u, 0x2e1b2138u, 0x4d2c6dfcu,
    0x53380d13u, 0x650a7354u, 0x766a0abbu, 0x81c2c92eu, 0x92722c85u,
    0xa2bfe8a1u, 0xa81a664bu, 0xc24b8b70u, 0xc76c51a3u, 0xd192e819u,
    0xd6990624u,
    0xf40e3585u, 0x106aa070u, 0x19a4c116u, 0x1e376c08u, 0x2748774cu,
    0x34b0bcb5u, 0x391c0cb3u, 0x4ed8aa4au, 0x5b9cca4fu, 0x682e6ff3u,
    0x748f82eeu, 0x78a5636fu, 0x84c87814u, 0x8cc70208u, 0x90befffau,
    0xa4506cebu, 0xbef9a3f7u, 0xc67178f2u,
};

void host_compress(uint32_t state[8], const uint8_t* block) {
    uint32_t schedule[64];
    for (unsigned index = 0; index < 16; ++index) {
        schedule[index] = (static_cast<uint32_t>(block[index * 4]) << 24u) |
                          (static_cast<uint32_t>(block[index * 4 + 1]) << 16u) |
                          (static_cast<uint32_t>(block[index * 4 + 2]) << 8u) |
                          static_cast<uint32_t>(block[index * 4 + 3]);
    }
    for (unsigned index = 16; index < 64; ++index) {
        const uint32_t s0 = rotate_right_host(schedule[index - 15], 7u) ^
                             rotate_right_host(schedule[index - 15], 18u) ^
                             (schedule[index - 15] >> 3u);
        const uint32_t s1 = rotate_right_host(schedule[index - 2], 17u) ^
                             rotate_right_host(schedule[index - 2], 19u) ^
                             (schedule[index - 2] >> 10u);
        schedule[index] = s1 + schedule[index - 7] + s0 + schedule[index - 16];
    }
    uint32_t a = state[0], b = state[1], c = state[2], d = state[3];
    uint32_t e = state[4], f = state[5], g = state[6], h = state[7];
    for (unsigned index = 0; index < 64; ++index) {
        const uint32_t s1 = rotate_right_host(e, 6u) ^ rotate_right_host(e, 11u) ^ rotate_right_host(e, 25u);
        const uint32_t ch = (e & f) ^ (~e & g);
        const uint32_t temporary_one = h + s1 + ch + kHostRoundConstants[index] + schedule[index];
        const uint32_t s0 = rotate_right_host(a, 2u) ^ rotate_right_host(a, 13u) ^ rotate_right_host(a, 22u);
        const uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
        const uint32_t temporary_two = s0 + maj;
        h = g;
        g = f;
        f = e;
        e = d + temporary_one;
        d = c;
        c = b;
        b = a;
        a = temporary_one + temporary_two;
    }
    state[0] += a; state[1] += b; state[2] += c; state[3] += d;
    state[4] += e; state[5] += f; state[6] += g; state[7] += h;
}

std::array<uint8_t, 32> sha256(const std::vector<uint8_t>& input) {
    static constexpr uint32_t initial[8] = {
        0x6a09e667u, 0xbb67ae85u, 0x3c6ef372u, 0xa54ff53au,
        0x510e527fu, 0x9b05688cu, 0x1f83d9abu, 0x5be0cd19u,
    };
    uint32_t state[8];
    std::memcpy(state, initial, sizeof(state));
    std::vector<uint8_t> padded = input;
    padded.push_back(0x80u);
    while ((padded.size() % 64) != 56) padded.push_back(0);
    const uint64_t bit_length = static_cast<uint64_t>(input.size()) * 8u;
    for (int shift = 56; shift >= 0; shift -= 8) {
        padded.push_back(static_cast<uint8_t>(bit_length >> shift));
    }
    for (size_t offset = 0; offset < padded.size(); offset += 64) {
        host_compress(state, padded.data() + offset);
    }
    std::array<uint8_t, 32> output{};
    for (unsigned index = 0; index < 8; ++index) {
        output[index * 4] = static_cast<uint8_t>(state[index] >> 24u);
        output[index * 4 + 1] = static_cast<uint8_t>(state[index] >> 16u);
        output[index * 4 + 2] = static_cast<uint8_t>(state[index] >> 8u);
        output[index * 4 + 3] = static_cast<uint8_t>(state[index]);
    }
    return output;
}

std::array<uint8_t, 32> double_sha256(const std::vector<uint8_t>& input) {
    const auto first = sha256(input);
    return sha256(std::vector<uint8_t>(first.begin(), first.end()));
}

struct UInt256 {
    std::array<uint32_t, 8> words{};
};

bool target_from_compact(const std::string& compact_hex, std::array<uint8_t, 32>* output) {
    std::vector<uint8_t> bytes;
    if (!decode_hex(compact_hex, &bytes, 4) || output == nullptr) return false;
    const uint32_t compact = (static_cast<uint32_t>(bytes[0]) << 24u) |
                             (static_cast<uint32_t>(bytes[1]) << 16u) |
                             (static_cast<uint32_t>(bytes[2]) << 8u) |
                             static_cast<uint32_t>(bytes[3]);
    const uint32_t exponent = compact >> 24u;
    const uint32_t mantissa = compact & 0x007fffffu;
    if ((compact & 0x00800000u) != 0 || mantissa == 0 || exponent > 34u) return false;
    output->fill(0);
    if (exponent <= 3u) {
        const uint32_t value = mantissa >> (8u * (3u - exponent));
        for (unsigned index = 0; index < 4; ++index) {
            (*output)[index] = static_cast<uint8_t>(value >> (8u * index));
        }
        return true;
    }
    const size_t offset = static_cast<size_t>(exponent - 3u);
    if (offset + 2u >= output->size()) return false;
    (*output)[offset] = static_cast<uint8_t>(mantissa);
    (*output)[offset + 1] = static_cast<uint8_t>(mantissa >> 8u);
    (*output)[offset + 2] = static_cast<uint8_t>(mantissa >> 16u);
    return true;
}

UInt256 target_words(const std::array<uint8_t, 32>& bytes) {
    UInt256 target;
    for (unsigned word = 0; word < 8; ++word) {
        target.words[word] = static_cast<uint32_t>(bytes[word * 4]) |
                             (static_cast<uint32_t>(bytes[word * 4 + 1]) << 8u) |
                             (static_cast<uint32_t>(bytes[word * 4 + 2]) << 16u) |
                             (static_cast<uint32_t>(bytes[word * 4 + 3]) << 24u);
    }
    return target;
}

bool target_from_difficulty(long double difficulty, std::array<uint8_t, 32>* output) {
    if (output == nullptr || !(difficulty > 0.0L) || !std::isfinite(difficulty)) return false;
    std::array<uint8_t, 32> difficulty_one_bytes{};
    if (!target_from_compact("1d00ffff", &difficulty_one_bytes)) return false;
    if (difficulty <= 1.0L) {
        *output = difficulty_one_bytes;
        return true;
    }
    const UInt256 source = target_words(difficulty_one_bytes);
    UInt256 quotient;
    long double remainder = 0.0L;
    constexpr long double radix = 4294967296.0L;
    for (int index = 7; index >= 0; --index) {
        const long double current = remainder * radix + static_cast<long double>(source.words[index]);
        long double digit = std::floor(current / difficulty);
        if (digit < 0.0L) digit = 0.0L;
        if (digit > 4294967295.0L) digit = 4294967295.0L;
        quotient.words[index] = static_cast<uint32_t>(digit);
        remainder = current - digit * difficulty;
    }
    output->fill(0);
    for (unsigned word = 0; word < 8; ++word) {
        (*output)[word * 4] = static_cast<uint8_t>(quotient.words[word]);
        (*output)[word * 4 + 1] = static_cast<uint8_t>(quotient.words[word] >> 8u);
        (*output)[word * 4 + 2] = static_cast<uint8_t>(quotient.words[word] >> 16u);
        (*output)[word * 4 + 3] = static_cast<uint8_t>(quotient.words[word] >> 24u);
    }
    return true;
}

long double uint256_value(const std::array<uint8_t, 32>& bytes) {
    long double value = 0.0L;
    for (int index = 31; index >= 0; --index) {
        value = value * 256.0L + static_cast<long double>(bytes[index]);
    }
    return value;
}

double difficulty_from_digest(const std::array<uint8_t, 32>& digest) {
    std::array<uint8_t, 32> difficulty_one_target{};
    if (!target_from_compact("1d00ffff", &difficulty_one_target)) return 0.0;
    const long double hash_value = uint256_value(digest);
    if (!(hash_value > 0.0L)) return 0.0;
    return static_cast<double>(uint256_value(difficulty_one_target) / hash_value);
}

struct StratumJob {
    std::string job_id;
    std::string prevhash;
    std::string coinbase1;
    std::string coinbase2;
    std::vector<std::string> merkle_branch;
    std::string version;
    std::string nbits;
    std::string ntime;
    bool clean_jobs = false;
};

bool parse_notify(const JsonValue& message, StratumJob* output) {
    if (output == nullptr || !method_is(message, "mining.notify")) return false;
    const JsonValue* params = object_field(message, "params");
    if (params == nullptr || params->kind != JsonValue::Kind::Array || params->array_value.size() != 9) return false;
    const auto& values = params->array_value;
    if (!string_value(&values[0], &output->job_id) || !string_value(&values[1], &output->prevhash) ||
        !string_value(&values[2], &output->coinbase1) || !string_value(&values[3], &output->coinbase2) ||
        !string_value(&values[5], &output->version) || !string_value(&values[6], &output->nbits) ||
        !string_value(&values[7], &output->ntime) || !bool_value(&values[8], &output->clean_jobs)) {
        return false;
    }
    if (values[4].kind != JsonValue::Kind::Array) return false;
    output->merkle_branch.clear();
    for (const JsonValue& branch : values[4].array_value) {
        std::string branch_hex;
        if (!string_value(&branch, &branch_hex)) return false;
        output->merkle_branch.push_back(std::move(branch_hex));
    }
    std::vector<uint8_t> check;
    std::array<uint8_t, 32> target_check{};
    return decode_hex(output->prevhash, &check, 32) &&
           decode_hex(output->version, &check, 4) &&
           decode_hex(output->nbits, &check, 4) &&
           decode_hex(output->ntime, &check, 4) &&
           decode_hex(output->coinbase1, &check, 0, true) &&
           decode_hex(output->coinbase2, &check, 0, true) &&
           target_from_compact(output->nbits, &target_check);
}

bool build_header_base(const StratumJob& job, const std::string& extranonce1,
                       const std::string& extranonce2, std::vector<uint8_t>* output) {
    if (output == nullptr) return false;
    std::vector<uint8_t> prevhash, version, ntime, nbits, coinbase1, coinbase2, ex1, ex2;
    if (!decode_hex(job.prevhash, &prevhash, 32) || !decode_hex(job.version, &version, 4) ||
        !decode_hex(job.ntime, &ntime, 4) || !decode_hex(job.nbits, &nbits, 4) ||
        !decode_hex(job.coinbase1, &coinbase1, 0, true) || !decode_hex(job.coinbase2, &coinbase2, 0, true) ||
        !decode_hex(extranonce1, &ex1, 0, true) || !decode_hex(extranonce2, &ex2, 0, true)) {
        return false;
    }
    std::vector<uint8_t> coinbase;
    coinbase.insert(coinbase.end(), coinbase1.begin(), coinbase1.end());
    coinbase.insert(coinbase.end(), ex1.begin(), ex1.end());
    coinbase.insert(coinbase.end(), ex2.begin(), ex2.end());
    coinbase.insert(coinbase.end(), coinbase2.begin(), coinbase2.end());
    const auto merkle_hash = double_sha256(coinbase);
    std::vector<uint8_t> root(merkle_hash.begin(), merkle_hash.end());
    for (const std::string& branch_hex : job.merkle_branch) {
        std::vector<uint8_t> branch;
        if (!decode_hex(branch_hex, &branch, 32)) return false;
        std::vector<uint8_t> combined = root;
        combined.insert(combined.end(), branch.begin(), branch.end());
        const auto hashed = double_sha256(combined);
        root.assign(hashed.begin(), hashed.end());
    }
    output->clear();
    output->reserve(76);
    output->insert(output->end(), version.rbegin(), version.rend());
    output->insert(output->end(), prevhash.rbegin(), prevhash.rend());
    output->insert(output->end(), root.begin(), root.end());
    output->insert(output->end(), ntime.rbegin(), ntime.rend());
    output->insert(output->end(), nbits.rbegin(), nbits.rend());
    return output->size() == 76;
}

std::string nonce_submit_hex(uint32_t nonce) {
    const std::array<uint8_t, 4> bytes = {
        static_cast<uint8_t>(nonce), static_cast<uint8_t>(nonce >> 8u),
        static_cast<uint8_t>(nonce >> 16u), static_cast<uint8_t>(nonce >> 24u),
    };
    return encode_hex(bytes.data(), bytes.size());
}

std::string fixed_hex(uint64_t value, unsigned byte_count) {
    std::array<uint8_t, 8> bytes{};
    for (unsigned index = 0; index < byte_count; ++index) {
        bytes[byte_count - index - 1] = static_cast<uint8_t>(value >> (index * 8u));
    }
    return encode_hex(bytes.data(), byte_count);
}

// ---------------------------------------------------------------------------
// Cross-platform TCP connection
// ---------------------------------------------------------------------------

class NetworkRuntime {
public:
    NetworkRuntime() {
#ifdef _WIN32
        WSADATA data{};
        ready_ = WSAStartup(MAKEWORD(2, 2), &data) == 0;
#else
        ready_ = true;
#endif
    }
    ~NetworkRuntime() {
#ifdef _WIN32
        if (ready_) WSACleanup();
#endif
    }
    bool ready() const { return ready_; }

private:
    bool ready_ = false;
};

class TcpConnection {
public:
    TcpConnection() = default;
    ~TcpConnection() { close(); }
    TcpConnection(const TcpConnection&) = delete;
    TcpConnection& operator=(const TcpConnection&) = delete;

    bool connect_to(const std::string& host, uint16_t port) {
        char port_text[16];
        std::snprintf(port_text, sizeof(port_text), "%u", static_cast<unsigned>(port));
        addrinfo hints{};
        hints.ai_socktype = SOCK_STREAM;
        hints.ai_family = AF_UNSPEC;
        addrinfo* addresses = nullptr;
        if (getaddrinfo(host.c_str(), port_text, &hints, &addresses) != 0) return false;
        for (addrinfo* current = addresses; current != nullptr; current = current->ai_next) {
            SocketHandle candidate = socket(current->ai_family, current->ai_socktype, current->ai_protocol);
            if (candidate == invalid_socket()) continue;
            if (::connect(candidate, current->ai_addr, static_cast<int>(current->ai_addrlen)) == 0) {
                socket_ = candidate;
                break;
            }
            close_socket(candidate);
        }
        freeaddrinfo(addresses);
        return socket_ != invalid_socket();
    }

    bool send_line(const std::string& line) {
        if (socket_ == invalid_socket()) return false;
        size_t sent = 0;
        while (sent < line.size()) {
#ifdef _WIN32
            const int result = send(socket_, line.data() + sent, static_cast<int>(line.size() - sent), 0);
#else
            const ssize_t result = send(socket_, line.data() + sent, line.size() - sent, 0);
#endif
            if (result <= 0) return false;
            sent += static_cast<size_t>(result);
        }
        return true;
    }

    bool read_line(std::string* output, int timeout_seconds = 15) {
        if (output == nullptr || socket_ == invalid_socket()) return false;
        while (true) {
            const size_t newline = receive_buffer_.find('\n');
            if (newline != std::string::npos) {
                *output = receive_buffer_.substr(0, newline);
                receive_buffer_.erase(0, newline + 1);
                if (!output->empty() && output->back() == '\r') output->pop_back();
                return !output->empty();
            }
            if (!receive_more(timeout_seconds)) return false;
        }
    }

    bool read_available_line(std::string* output) {
        if (output == nullptr || socket_ == invalid_socket()) return false;
        const size_t newline = receive_buffer_.find('\n');
        if (newline != std::string::npos) {
            *output = receive_buffer_.substr(0, newline);
            receive_buffer_.erase(0, newline + 1);
            if (!output->empty() && output->back() == '\r') output->pop_back();
            return !output->empty();
        }
        if (!socket_ready(0)) return false;
        if (!receive_more(0)) return false;
        return read_available_line(output);
    }

    void close() {
        if (socket_ != invalid_socket()) {
            close_socket(socket_);
            socket_ = invalid_socket();
        }
    }

private:
#ifdef _WIN32
    using SocketHandle = SOCKET;
#else
    using SocketHandle = int;
#endif
    SocketHandle socket_ = invalid_socket();
    std::string receive_buffer_;

    static SocketHandle invalid_socket() {
#ifdef _WIN32
        return INVALID_SOCKET;
#else
        return -1;
#endif
    }

    static void close_socket(SocketHandle socket) {
#ifdef _WIN32
        closesocket(socket);
#else
        ::close(socket);
#endif
    }

    bool socket_ready(int timeout_seconds) {
        fd_set set;
        FD_ZERO(&set);
        FD_SET(socket_, &set);
        timeval timeout{};
        timeout.tv_sec = timeout_seconds;
        timeout.tv_usec = 0;
        const int result = select(static_cast<int>(socket_) + 1, &set, nullptr, nullptr, &timeout);
        return result > 0 && FD_ISSET(socket_, &set);
    }

    bool receive_more(int timeout_seconds) {
        if (!socket_ready(timeout_seconds)) return false;
        char buffer[4096];
#ifdef _WIN32
        const int result = recv(socket_, buffer, sizeof(buffer), 0);
#else
        const ssize_t result = recv(socket_, buffer, sizeof(buffer), 0);
#endif
        if (result <= 0) return false;
        receive_buffer_.append(buffer, static_cast<size_t>(result));
        return receive_buffer_.size() <= 1u << 20;
    }
};

// ---------------------------------------------------------------------------
// CUDA scanner and progress output
// ---------------------------------------------------------------------------

class CudaScanner {
public:
    explicit CudaScanner(int device, unsigned threads) : threads_(threads) {
        if (cudaSetDevice(device) != cudaSuccess || cudaGetDeviceProperties(&properties_, device) != cudaSuccess) {
            return;
        }
        if (cudaMalloc(&found_flag_, sizeof(uint32_t)) != cudaSuccess ||
            cudaMalloc(&found_nonce_, sizeof(uint32_t)) != cudaSuccess ||
            cudaMalloc(&found_digest_, 32) != cudaSuccess) {
            release();
            return;
        }
        ready_ = true;
    }

    ~CudaScanner() { release(); }
    CudaScanner(const CudaScanner&) = delete;
    CudaScanner& operator=(const CudaScanner&) = delete;

    bool ready() const { return ready_; }
    const cudaDeviceProp& properties() const { return properties_; }

    bool scan(const std::vector<uint8_t>& header_base, const std::array<uint8_t, 32>& target,
              uint32_t starting_nonce, uint32_t count, uint32_t* found_nonce,
              std::array<uint8_t, 32>* found_digest, double* elapsed_seconds) {
        if (!ready_ || header_base.size() != 76 || count == 0 || found_nonce == nullptr ||
            found_digest == nullptr || elapsed_seconds == nullptr) return false;
        if (cudaMemcpyToSymbol(d_header, header_base.data(), header_base.size()) != cudaSuccess ||
            cudaMemcpyToSymbol(d_target, target.data(), target.size()) != cudaSuccess ||
            cudaMemset(found_flag_, 0, sizeof(uint32_t)) != cudaSuccess) {
            return false;
        }
        const unsigned blocks = std::max(
            1u, std::min(65535u, static_cast<unsigned>((static_cast<uint64_t>(count) + threads_ - 1u) / threads_)));
        const auto start = std::chrono::steady_clock::now();
        scan_nonces<<<blocks, threads_>>>(starting_nonce, count, found_flag_, found_nonce_, found_digest_);
        if (cudaGetLastError() != cudaSuccess || cudaDeviceSynchronize() != cudaSuccess) return false;
        const auto stop = std::chrono::steady_clock::now();
        *elapsed_seconds = std::chrono::duration<double>(stop - start).count();
        uint32_t flag = 0;
        if (cudaMemcpy(&flag, found_flag_, sizeof(flag), cudaMemcpyDeviceToHost) != cudaSuccess) return false;
        if (flag == 0) return true;
        if (cudaMemcpy(found_nonce, found_nonce_, sizeof(*found_nonce), cudaMemcpyDeviceToHost) != cudaSuccess ||
            cudaMemcpy(found_digest->data(), found_digest_, found_digest->size(), cudaMemcpyDeviceToHost) != cudaSuccess) {
            return false;
        }
        return true;
    }

private:
    bool ready_ = false;
    unsigned threads_ = 256;
    cudaDeviceProp properties_{};
    uint32_t* found_flag_ = nullptr;
    uint32_t* found_nonce_ = nullptr;
    uint8_t* found_digest_ = nullptr;

    void release() {
        if (found_flag_ != nullptr) cudaFree(found_flag_);
        if (found_nonce_ != nullptr) cudaFree(found_nonce_);
        if (found_digest_ != nullptr) cudaFree(found_digest_);
        found_flag_ = nullptr;
        found_nonce_ = nullptr;
        found_digest_ = nullptr;
        ready_ = false;
    }
};

struct Options {
    std::string host;
    uint16_t port = 0;
    std::string worker_name;
    std::string password;
    std::string password_file;
    std::string progress_file;
    uint64_t max_shares = 0;
    uint64_t seconds = 0;
    uint64_t batch_nonces = 1u << 20;
    unsigned threads = 256;
    int device = 0;
};

bool parse_unsigned_text(const std::string& value, uint64_t* output) {
    if (output == nullptr || value.empty()) return false;
    char* end = nullptr;
    const unsigned long long parsed = std::strtoull(value.c_str(), &end, 10);
    if (end == value.c_str() || *end != '\0') return false;
    *output = static_cast<uint64_t>(parsed);
    return true;
}

bool next_arg(int argc, char** argv, int* index, std::string* value) {
    if (index == nullptr || value == nullptr || *index + 1 >= argc) return false;
    ++(*index);
    *value = argv[*index];
    return true;
}

void print_usage() {
    std::cerr << "usage: cuda_sha256d_worker --host HOST --port PORT --worker NAME "
                 "[--password TEXT | --password-file PATH] [options]\n"
              << "options: --progress-file PATH --max-shares N --seconds N "
                 "--batch-nonces N --threads N --device N\n";
}

bool parse_options(int argc, char** argv, Options* output) {
    if (output == nullptr) return false;
    for (int index = 1; index < argc; ++index) {
        const std::string argument = argv[index];
        std::string value;
        if (argument == "--help") {
            print_usage();
            return false;
        } else if (argument == "--host") {
            if (!next_arg(argc, argv, &index, &output->host)) return false;
        } else if (argument == "--port") {
            if (!next_arg(argc, argv, &index, &value)) return false;
            uint64_t parsed = 0;
            if (!parse_unsigned_text(value, &parsed) || parsed == 0 || parsed > 65535) return false;
            output->port = static_cast<uint16_t>(parsed);
        } else if (argument == "--worker") {
            if (!next_arg(argc, argv, &index, &output->worker_name)) return false;
        } else if (argument == "--password") {
            if (!next_arg(argc, argv, &index, &output->password)) return false;
        } else if (argument == "--password-file") {
            if (!next_arg(argc, argv, &index, &output->password_file)) return false;
        } else if (argument == "--progress-file") {
            if (!next_arg(argc, argv, &index, &output->progress_file)) return false;
        } else if (argument == "--max-shares") {
            if (!next_arg(argc, argv, &index, &value) || !parse_unsigned_text(value, &output->max_shares)) return false;
        } else if (argument == "--seconds") {
            if (!next_arg(argc, argv, &index, &value) || !parse_unsigned_text(value, &output->seconds)) return false;
        } else if (argument == "--batch-nonces") {
            if (!next_arg(argc, argv, &index, &value) || !parse_unsigned_text(value, &output->batch_nonces) ||
                output->batch_nonces == 0 || output->batch_nonces > 0xFFFFFFFFu) return false;
        } else if (argument == "--threads") {
            uint64_t parsed = 0;
            if (!next_arg(argc, argv, &index, &value) || !parse_unsigned_text(value, &parsed) || parsed == 0 || parsed > 1024) return false;
            output->threads = static_cast<unsigned>(parsed);
        } else if (argument == "--device") {
            uint64_t parsed = 0;
            if (!next_arg(argc, argv, &index, &value) || !parse_unsigned_text(value, &parsed) || parsed > 16) return false;
            output->device = static_cast<int>(parsed);
        } else {
            return false;
        }
    }
    return !output->host.empty() && output->port != 0 && !output->worker_name.empty() &&
           (output->password_file.empty() || output->password.empty());
}

bool read_password_file(const std::string& path, std::string* output) {
    if (output == nullptr || path.empty()) return false;
    std::ifstream input(path, std::ios::in | std::ios::binary);
    if (!input) return false;
    std::getline(input, *output);
    while (!output->empty() && (output->back() == '\r' || output->back() == '\n')) output->pop_back();
    return true;
}

bool write_progress_file(const std::string& path, const std::string& line) {
    if (path.empty()) return true;
    const std::string temporary_path = path + ".tmp";
    {
        std::ofstream output(temporary_path, std::ios::out | std::ios::trunc | std::ios::binary);
        if (!output) return false;
        output << line;
        output.flush();
        if (!output) {
            std::remove(temporary_path.c_str());
            return false;
        }
    }
#ifdef _WIN32
    if (!MoveFileExA(temporary_path.c_str(), path.c_str(),
                     MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)) {
        DeleteFileA(temporary_path.c_str());
        return false;
    }
#else
    if (std::rename(temporary_path.c_str(), path.c_str()) != 0) {
        std::remove(temporary_path.c_str());
        return false;
    }
#endif
    return true;
}

std::string progress_json(const Options& options, const std::string& state,
                           const std::string& cursor, uint64_t hashes, double rate,
                          uint64_t accepted, uint64_t rejected, double best_share_difficulty,
                          bool pool_connected,
                          uint64_t uptime_seconds, const std::string& note) {
    std::ostringstream output;
    output << "{\"worker_id\":\"" << json_escape(options.worker_name)
           << "\",\"state\":\"" << json_escape(state)
           << "\",\"progress_cursor\":\"" << json_escape(cursor)
           << "\",\"rate\":" << std::fixed << std::setprecision(3) << rate
           << ",\"rate_unit\":\"hashes/s\",\"accepted_shares\":" << accepted
           << ",\"rejected_shares\":" << rejected
           << ",\"best_share_difficulty\":" << std::scientific << std::setprecision(12)
           << best_share_difficulty << std::fixed << std::setprecision(3)
           << ",\"pool_connected\":" << (pool_connected ? "true" : "false")
           << ",\"uptime_seconds\":" << uptime_seconds
           << ",\"hashes\":" << hashes
           << ",\"note\":\"" << json_escape(note) << "\"}\n";
    return output.str();
}

void emit_progress(const Options& options, const std::string& state, const std::string& cursor,
                   uint64_t hashes, double rate, uint64_t accepted, uint64_t rejected,
                   double best_share_difficulty, bool pool_connected, uint64_t uptime_seconds,
                   const std::string& note) {
    const std::string line = progress_json(options, state, cursor, hashes, rate, accepted,
                                           rejected, best_share_difficulty, pool_connected,
                                           uptime_seconds, note);
    std::cout << line;
    std::cout.flush();
    write_progress_file(options.progress_file, line);
}

bool parse_message_line(const std::string& line, JsonValue* output) {
    JsonParser parser(line);
    return parser.parse(output);
}

bool server_error(const JsonValue& message) {
    const JsonValue* error = object_field(message, "error");
    return error != nullptr && error->kind != JsonValue::Kind::Null;
}

bool extract_subscription(const JsonValue& message, std::string* extranonce1, unsigned* extranonce2_size) {
    const JsonValue* result = object_field(message, "result");
    if (result == nullptr || result->kind != JsonValue::Kind::Array || result->array_value.size() < 3 ||
        !string_value(&result->array_value[1], extranonce1)) return false;
    uint64_t size = 0;
    if (!integer_value(&result->array_value[2], &size) || size == 0 || size > 8) return false;
    *extranonce2_size = static_cast<unsigned>(size);
    std::vector<uint8_t> check;
    return decode_hex(*extranonce1, &check, 0, false);
}

bool authorize_succeeded(const JsonValue& message) {
    bool result = false;
    return bool_value(object_field(message, "result"), &result) && result;
}

bool difficulty_notification(const JsonValue& message, std::array<uint8_t, 32>* target) {
    if (!method_is(message, "mining.set_difficulty") || target == nullptr) return false;
    const JsonValue* params = object_field(message, "params");
    if (params == nullptr || params->kind != JsonValue::Kind::Array || params->array_value.size() != 1 ||
        params->array_value[0].kind != JsonValue::Kind::Number) return false;
    return target_from_difficulty(params->array_value[0].number_value, target);
}

bool parse_notification(const JsonValue& message, StratumJob* job,
                        std::array<uint8_t, 32>* target, bool* difficulty_set) {
    if (method_is(message, "mining.notify")) {
        if (!parse_notify(message, job)) return false;
        if (difficulty_set != nullptr && !*difficulty_set) {
            if (!target_from_compact(job->nbits, target)) return false;
        }
        return true;
    }
    if (method_is(message, "mining.set_difficulty")) {
        if (!difficulty_notification(message, target)) return false;
        if (difficulty_set != nullptr) *difficulty_set = true;
        return true;
    }
    return false;
}

bool drain_available_notifications(TcpConnection& connection, StratumJob* job,
                                   std::array<uint8_t, 32>* target, bool* difficulty_set,
                                   bool* work_changed) {
    if (job == nullptr || target == nullptr || difficulty_set == nullptr || work_changed == nullptr) return false;
    while (true) {
        std::string line;
        if (!connection.read_available_line(&line)) return true;
        JsonValue message;
        if (!parse_message_line(line, &message)) return false;
        if (method_is(message, "mining.notify")) {
            StratumJob replacement;
            if (!parse_notify(message, &replacement)) return false;
            if (replacement.job_id != job->job_id || replacement.clean_jobs) {
                *work_changed = true;
            }
            *job = std::move(replacement);
            if (!*difficulty_set && !target_from_compact(job->nbits, target)) return false;
        } else if (method_is(message, "mining.set_difficulty")) {
            if (!difficulty_notification(message, target)) return false;
            *difficulty_set = true;
            *work_changed = true;
        }
        // Responses to an earlier request are deliberately left alone here;
        // the handshake and submit paths consume their matching ids.
    }
}

bool wait_for_handshake(TcpConnection& connection, const Options& options,
                        std::string* extranonce1, unsigned* extranonce2_size,
                        StratumJob* job, std::array<uint8_t, 32>* target,
                        bool* difficulty_set, uint64_t* next_id) {
    if (extranonce1 == nullptr || extranonce2_size == nullptr || job == nullptr || target == nullptr ||
        difficulty_set == nullptr || next_id == nullptr) return false;
    const uint64_t subscribe_id = (*next_id)++;
    if (!connection.send_line(request_json(subscribe_id, "mining.subscribe", {}))) return false;
    bool subscribed = false;
    while (!subscribed) {
        std::string line;
        JsonValue message;
        if (!connection.read_line(&line) || !parse_message_line(line, &message)) return false;
        if (method_is(message, "mining.notify") || method_is(message, "mining.set_difficulty")) {
            parse_notification(message, job, target, difficulty_set);
            continue;
        }
        if (message_id_is(message, subscribe_id)) {
            if (server_error(message) || !extract_subscription(message, extranonce1, extranonce2_size)) return false;
            subscribed = true;
        }
    }

    const uint64_t authorize_id = (*next_id)++;
    const std::string password = options.password;
    if (!connection.send_line(request_json(authorize_id, "mining.authorize", {options.worker_name, password}))) return false;
    bool authorized = false;
    while (!authorized || job->job_id.empty()) {
        std::string line;
        JsonValue message;
        if (!connection.read_line(&line) || !parse_message_line(line, &message)) return false;
        if (method_is(message, "mining.notify") || method_is(message, "mining.set_difficulty")) {
            if (!parse_notification(message, job, target, difficulty_set)) return false;
            continue;
        }
        if (message_id_is(message, authorize_id)) {
            if (server_error(message) || !authorize_succeeded(message)) return false;
            authorized = true;
        }
    }
    return true;
}

bool wait_for_submit(TcpConnection& connection, uint64_t submit_id, bool* accepted,
                     StratumJob* job, std::array<uint8_t, 32>* target, bool* difficulty_set) {
    if (accepted == nullptr) return false;
    while (true) {
        std::string line;
        JsonValue message;
        if (!connection.read_line(&line) || !parse_message_line(line, &message)) return false;
        if (method_is(message, "mining.notify") || method_is(message, "mining.set_difficulty")) {
            if (!parse_notification(message, job, target, difficulty_set)) return false;
            continue;
        }
        if (message_id_is(message, submit_id)) {
            *accepted = !server_error(message) && authorize_succeeded(message);
            return true;
        }
    }
}

}  // namespace

int main(int argc, char** argv) {
    Options options;
    if (!parse_options(argc, argv, &options)) {
        print_usage();
        return 64;
    }
    if (!options.password_file.empty() && !read_password_file(options.password_file, &options.password)) {
        std::cerr << "password file could not be read\n";
        return 64;
    }

    NetworkRuntime network;
    if (!network.ready()) {
        std::cerr << "network initialization failed\n";
        return 69;
    }
    TcpConnection connection;
    if (!connection.connect_to(options.host, options.port)) {
        std::cerr << "Stratum connection failed\n";
        return 69;
    }

    CudaScanner scanner(options.device, options.threads);
    if (!scanner.ready()) {
        std::cerr << "CUDA scanner initialization failed\n";
        return 69;
    }

    std::string extranonce1;
    unsigned extranonce2_size = 0;
    StratumJob job;
    std::array<uint8_t, 32> target{};
    bool difficulty_set = false;
    uint64_t next_id = 1;
    if (!wait_for_handshake(connection, options, &extranonce1, &extranonce2_size, &job, &target,
                             &difficulty_set, &next_id)) {
        std::cerr << "Stratum handshake failed\n";
        return 69;
    }

    const auto started = std::chrono::steady_clock::now();
    uint64_t hashes = 0;
    uint64_t accepted_shares = 0;
    uint64_t rejected_shares = 0;
    double best_share_difficulty = 0.0;
    uint64_t extranonce2_counter = 0;
    uint64_t nonce_base = 0;
    std::string cursor = "job-" + job.job_id;
    emit_progress(options, "RUNNING", cursor, hashes, 0.0, accepted_shares, rejected_shares,
                  best_share_difficulty, true, 0,
                  "Authenticated Stratum session; waiting for the first GPU batch.");

    while (true) {
        const uint64_t uptime = static_cast<uint64_t>(
            std::chrono::duration_cast<std::chrono::seconds>(std::chrono::steady_clock::now() - started).count());
        if (options.seconds != 0 && uptime >= options.seconds) break;
        if (options.max_shares != 0 && accepted_shares >= options.max_shares) break;

        bool work_changed = false;
        if (!drain_available_notifications(connection, &job, &target, &difficulty_set, &work_changed)) {
            std::cerr << "Stratum notification failed\n";
            return 69;
        }
        if (work_changed) {
            nonce_base = 0;
            extranonce2_counter = 0;
        }

        std::vector<uint8_t> header_base;
        const std::string extranonce2 = fixed_hex(extranonce2_counter, extranonce2_size);
        if (!build_header_base(job, extranonce1, extranonce2, &header_base)) {
            std::cerr << "Stratum job could not be converted into a Bitcoin header\n";
            return 2;
        }

        const uint64_t remaining = (1ull << 32u) - nonce_base;
        const uint32_t count = static_cast<uint32_t>(std::min<uint64_t>(options.batch_nonces, remaining));
        uint32_t found_nonce = 0;
        std::array<uint8_t, 32> found_digest{};
        double elapsed = 0.0;
        if (!scanner.scan(header_base, target, static_cast<uint32_t>(nonce_base), count,
                          &found_nonce, &found_digest, &elapsed)) {
            std::cerr << "CUDA scan failed\n";
            return 69;
        }
        hashes += count;
        const double rate = elapsed > 0.0 ? static_cast<double>(count) / elapsed : 0.0;
        if (std::any_of(found_digest.begin(), found_digest.end(), [](uint8_t byte) { return byte != 0; })) {
            best_share_difficulty = std::max(best_share_difficulty, difficulty_from_digest(found_digest));
        }
        cursor = "job-" + job.job_id + "-ex2-" + extranonce2 + "-nonce-" + std::to_string(nonce_base + count);
        emit_progress(options, "RUNNING", cursor, hashes, rate, accepted_shares, rejected_shares,
                      best_share_difficulty, true, uptime,
                      "GPU batch completed and aggregate progress advanced.");

        work_changed = false;
        if (!drain_available_notifications(connection, &job, &target, &difficulty_set, &work_changed)) {
            std::cerr << "Stratum notification failed\n";
            return 69;
        }
        if (work_changed) {
            nonce_base = 0;
            extranonce2_counter = 0;
            continue;
        }

        if (found_nonce != 0 || std::any_of(found_digest.begin(), found_digest.end(), [](uint8_t byte) { return byte != 0; })) {
            const std::string submitted_job_id = job.job_id;
            const uint64_t submit_id = next_id++;
            if (!connection.send_line(request_json(submit_id, "mining.submit",
                                                   {options.worker_name, job.job_id, extranonce2, job.ntime,
                                                    nonce_submit_hex(found_nonce)}))) {
                std::cerr << "share submission failed\n";
                return 69;
            }
            bool accepted = false;
            if (!wait_for_submit(connection, submit_id, &accepted, &job, &target, &difficulty_set)) {
                std::cerr << "share response failed\n";
                return 69;
            }
            if (accepted) {
                ++accepted_shares;
            } else {
                ++rejected_shares;
            }
            emit_progress(options, "RUNNING", cursor, hashes, rate, accepted_shares, rejected_shares,
                          best_share_difficulty, true, uptime,
                          accepted ? "Share accepted by the Stratum endpoint."
                                   : "Share rejected by the Stratum endpoint.");
            if (job.job_id != submitted_job_id) {
                nonce_base = 0;
                extranonce2_counter = 0;
            }
            if (options.max_shares != 0 && accepted_shares >= options.max_shares) break;
        }

        nonce_base += count;
        if (nonce_base >= (1ull << 32u)) {
            nonce_base = 0;
            ++extranonce2_counter;
            if (extranonce2_size < 8 && extranonce2_counter == (1ull << (extranonce2_size * 8u))) {
                extranonce2_counter = 0;
            }
        }
    }

    const uint64_t uptime = static_cast<uint64_t>(
        std::chrono::duration_cast<std::chrono::seconds>(std::chrono::steady_clock::now() - started).count());
    const std::string final_state = (options.max_shares != 0 && accepted_shares >= options.max_shares)
                                        ? "COMPLETE" : "STOPPED";
    emit_progress(options, final_state, cursor, hashes, 0.0, accepted_shares, rejected_shares,
                  best_share_difficulty, true, uptime,
                  final_state == "COMPLETE" ? "Configured share acceptance target reached."
                                             : "Worker stopped at its configured local bound.");
    return 0;
}

#include <cuda_runtime.h>

#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <string>

namespace {

__device__ __constant__ uint32_t kInitialState[8] = {
    0x6a09e667u, 0xbb67ae85u, 0x3c6ef372u, 0xa54ff53au,
    0x510e527fu, 0x9b05688cu, 0x1f83d9abu, 0x5be0cd19u,
};

__device__ __constant__ uint32_t kRoundConstants[64] = {
    0x428a2f98u, 0x71374491u, 0xb5c0fbcfu, 0xe9b5dba5u,
    0x3956c25bu, 0x59f111f1u, 0x923f82a4u, 0xab1c5ed5u,
    0xd807aa98u, 0x12835b01u, 0x243185beu, 0x550c7dc3u,
    0x72be5d74u, 0x80deb1feu, 0x9bdc06a7u, 0xc19bf174u,
    0xe49b69c1u, 0xefbe4786u, 0x0fc19dc6u, 0x240ca1ccu,
    0x2de92c6fu, 0x4a7484aau, 0x5cb0a9dcu, 0x76f988dau,
    0x983e5152u, 0xa831c66du, 0xb00327c8u, 0xbf597fc7u,
    0xc6e00bf3u, 0xd5a79147u, 0x06ca6351u, 0x14292967u,
    0x27b70a85u, 0x2e1b2138u, 0x4d2c6dfcu, 0x53380d13u,
    0x650a7354u, 0x766a0abbu, 0x81c2c92eu, 0x92722c85u,
    0xa2bfe8a1u, 0xa81a664bu, 0xc24b8b70u, 0xc76c51a3u,
    0xd192e819u, 0xd6990624u, 0xf40e3585u, 0x106aa070u,
    0x19a4c116u, 0x1e376c08u, 0x2748774cu, 0x34b0bcb5u,
    0x391c0cb3u, 0x4ed8aa4au, 0x5b9cca4fu, 0x682e6ff3u,
    0x748f82eeu, 0x78a5636fu, 0x84c87814u, 0x8cc70208u,
    0x90befffau, 0xa4506cebu, 0xbef9a3f7u, 0xc67178f2u,
};

__constant__ uint8_t d_header[80];

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

    // Bitcoin serializes the nonce as a four-byte little-endian integer.
    padded_header[76] = static_cast<uint8_t>(nonce);
    padded_header[77] = static_cast<uint8_t>(nonce >> 8u);
    padded_header[78] = static_cast<uint8_t>(nonce >> 16u);
    padded_header[79] = static_cast<uint8_t>(nonce >> 24u);
    padded_header[80] = 0x80u;
    // 80-byte header length in bits, encoded big-endian at the end of 128 bytes.
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
    // The first digest is 32 bytes, so its bit length is 256 = 0x100.
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

__global__ void calculate_one(uint32_t nonce, uint8_t* digest) {
    if (blockIdx.x == 0 && threadIdx.x == 0) {
        sha256d_header(nonce, digest);
    }
}

__global__ void benchmark(uint64_t hash_count, uint32_t starting_nonce, uint32_t* checksums) {
    const uint64_t thread_id = static_cast<uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
    const uint64_t thread_count = static_cast<uint64_t>(gridDim.x) * blockDim.x;
    uint32_t checksum = 0;

    for (uint64_t offset = thread_id; offset < hash_count; offset += thread_count) {
        uint8_t digest[32];
        sha256d_header(starting_nonce + static_cast<uint32_t>(offset), digest);
        checksum ^= read_big_endian(digest);
        checksum ^= read_big_endian(digest + 4);
        checksum ^= read_big_endian(digest + 8);
        checksum ^= read_big_endian(digest + 12);
        checksum ^= read_big_endian(digest + 16);
        checksum ^= read_big_endian(digest + 20);
        checksum ^= read_big_endian(digest + 24);
        checksum ^= read_big_endian(digest + 28);
    }

    checksums[thread_id] = checksum;
}

bool cuda_succeeded(cudaError_t result, const char* expression) {
    if (result == cudaSuccess) {
        return true;
    }
    std::cerr << expression << " failed: " << cudaGetErrorString(result) << '\n';
    return false;
}

bool parse_unsigned(const char* value, uint64_t* parsed) {
    char* end = nullptr;
    const unsigned long long candidate = std::strtoull(value, &end, 10);
    if (value == end || *end != '\0' || candidate == 0) {
        return false;
    }
    *parsed = static_cast<uint64_t>(candidate);
    return true;
}

std::string hex_digest(const uint8_t* digest, size_t length) {
    std::ostringstream output;
    output << std::hex << std::setfill('0');
    for (size_t index = 0; index < length; ++index) {
        output << std::setw(2) << static_cast<unsigned>(digest[index]);
    }
    return output.str();
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 2 || argc > 3) {
        std::cerr << "usage: cuda_sha256d_benchmark <hashes> [threads]\n";
        return 64;
    }

    uint64_t hash_count = 0;
    if (!parse_unsigned(argv[1], &hash_count)) {
        std::cerr << "hashes must be a positive unsigned integer\n";
        return 64;
    }

    uint64_t requested_threads = 256;
    if (argc == 3 && !parse_unsigned(argv[2], &requested_threads)) {
        std::cerr << "threads must be a positive unsigned integer\n";
        return 64;
    }
    if (requested_threads > 1024) {
        std::cerr << "threads must be <= 1024\n";
        return 64;
    }
    const unsigned threads = static_cast<unsigned>(requested_threads);

    int device_count = 0;
    if (!cuda_succeeded(cudaGetDeviceCount(&device_count), "cudaGetDeviceCount") || device_count == 0) {
        std::cerr << "no CUDA device is available\n";
        return 69;
    }
    if (!cuda_succeeded(cudaSetDevice(0), "cudaSetDevice")) {
        return 69;
    }

    cudaDeviceProp properties{};
    if (!cuda_succeeded(cudaGetDeviceProperties(&properties, 0), "cudaGetDeviceProperties")) {
        return 69;
    }

    constexpr uint8_t genesis_header[80] = {
        0x01, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x3b, 0xa3, 0xed, 0xfd, 0x7a, 0x7b, 0x12, 0xb2,
        0x7a, 0xc7, 0x2c, 0x3e, 0x67, 0x76, 0x8f, 0x61,
        0x7f, 0xc8, 0x1b, 0xc3, 0x88, 0x8a, 0x51, 0x32,
        0x3a, 0x9f, 0xb8, 0xaa, 0x4b, 0x1e, 0x5e, 0x4a,
        0x29, 0xab, 0x5f, 0x49,
        0xff, 0xff, 0x00, 0x1d,
        0x00, 0x00, 0x00, 0x00,
    };
    constexpr uint32_t genesis_nonce = 0x7c2bac1du;
    constexpr uint8_t expected_genesis_digest[32] = {
        0x6f, 0xe2, 0x8c, 0x0a, 0xb6, 0xf1, 0xb3, 0x72,
        0xc1, 0xa6, 0xa2, 0x46, 0xae, 0x63, 0xf7, 0x4f,
        0x93, 0x1e, 0x83, 0x65, 0xe1, 0x5a, 0x08, 0x9c,
        0x68, 0xd6, 0x19, 0x00, 0x00, 0x00, 0x00, 0x00,
    };

    if (!cuda_succeeded(cudaMemcpyToSymbol(d_header, genesis_header, sizeof(genesis_header)),
                       "cudaMemcpyToSymbol")) {
        return 69;
    }

    uint8_t* device_digest = nullptr;
    if (!cuda_succeeded(cudaMalloc(&device_digest, 32), "cudaMalloc known vector")) {
        return 69;
    }
    calculate_one<<<1, 1>>>(genesis_nonce, device_digest);
    if (!cuda_succeeded(cudaGetLastError(), "calculate_one launch") ||
        !cuda_succeeded(cudaDeviceSynchronize(), "calculate_one synchronize")) {
        cudaFree(device_digest);
        return 69;
    }

    uint8_t actual_genesis_digest[32]{};
    if (!cuda_succeeded(cudaMemcpy(actual_genesis_digest, device_digest, 32, cudaMemcpyDeviceToHost),
                       "cudaMemcpy known vector")) {
        cudaFree(device_digest);
        return 69;
    }
    cudaFree(device_digest);

    const bool known_vector_passed =
        std::memcmp(actual_genesis_digest, expected_genesis_digest, sizeof(expected_genesis_digest)) == 0;
    if (!known_vector_passed) {
        std::cerr << "known vector mismatch: got " << hex_digest(actual_genesis_digest, 32)
                  << ", expected " << hex_digest(expected_genesis_digest, 32) << '\n';
        return 2;
    }

    const unsigned blocks = std::max(
        1u, std::min(2048u, static_cast<unsigned>(properties.multiProcessorCount) * 32u));
    const size_t thread_slots = static_cast<size_t>(blocks) * threads;
    uint32_t* device_checksums = nullptr;
    if (!cuda_succeeded(cudaMalloc(&device_checksums, thread_slots * sizeof(uint32_t)),
                       "cudaMalloc benchmark")) {
        return 69;
    }

    cudaEvent_t start = nullptr;
    cudaEvent_t stop = nullptr;
    if (!cuda_succeeded(cudaEventCreate(&start), "cudaEventCreate start") ||
        !cuda_succeeded(cudaEventCreate(&stop), "cudaEventCreate stop")) {
        cudaFree(device_checksums);
        if (start != nullptr) cudaEventDestroy(start);
        if (stop != nullptr) cudaEventDestroy(stop);
        return 69;
    }

    if (!cuda_succeeded(cudaEventRecord(start), "cudaEventRecord start")) {
        cudaFree(device_checksums);
        cudaEventDestroy(start);
        cudaEventDestroy(stop);
        return 69;
    }
    benchmark<<<blocks, threads>>>(hash_count, 0u, device_checksums);
    if (!cuda_succeeded(cudaGetLastError(), "benchmark launch") ||
        !cuda_succeeded(cudaEventRecord(stop), "cudaEventRecord stop") ||
        !cuda_succeeded(cudaEventSynchronize(stop), "cudaEventSynchronize stop")) {
        cudaFree(device_checksums);
        cudaEventDestroy(start);
        cudaEventDestroy(stop);
        return 69;
    }

    float elapsed_milliseconds = 0.0f;
    if (!cuda_succeeded(cudaEventElapsedTime(&elapsed_milliseconds, start, stop),
                       "cudaEventElapsedTime")) {
        cudaFree(device_checksums);
        cudaEventDestroy(start);
        cudaEventDestroy(stop);
        return 69;
    }

    uint32_t* host_checksums = new uint32_t[thread_slots];
    const bool copied = cuda_succeeded(
        cudaMemcpy(host_checksums, device_checksums, thread_slots * sizeof(uint32_t),
                   cudaMemcpyDeviceToHost),
        "cudaMemcpy benchmark");
    cudaFree(device_checksums);
    cudaEventDestroy(start);
    cudaEventDestroy(stop);
    if (!copied) {
        delete[] host_checksums;
        return 69;
    }

    uint32_t aggregate_checksum = 0;
    for (size_t index = 0; index < thread_slots; ++index) {
        aggregate_checksum ^= host_checksums[index];
    }
    delete[] host_checksums;

    const double elapsed_seconds = static_cast<double>(elapsed_milliseconds) / 1000.0;
    const double hashrate = elapsed_seconds > 0.0
                                ? static_cast<double>(hash_count) / elapsed_seconds
                                : std::numeric_limits<double>::infinity();

    std::cout << std::fixed << std::setprecision(6)
              << "{\"algorithm\":\"SHA-256d\","
              << "\"known_vector\":\"PASS\","
              << "\"known_vector_digest\":\"" << hex_digest(actual_genesis_digest, 32) << "\","
              << "\"device\":\"" << properties.name << "\","
              << "\"compute_capability\":" << properties.major << "." << properties.minor << ","
              << "\"hashes\":" << hash_count << ","
              << "\"threads\":" << threads << ","
              << "\"blocks\":" << blocks << ","
              << "\"elapsed_seconds\":" << elapsed_seconds << ","
              << "\"hashrate_hs\":" << hashrate << ","
              << "\"checksum\":\"" << std::hex << std::setw(8) << std::setfill('0')
              << aggregate_checksum << "\","
              << "\"network\":\"none\","
              << "\"revenue_claim\":false}\n";
    return 0;
}

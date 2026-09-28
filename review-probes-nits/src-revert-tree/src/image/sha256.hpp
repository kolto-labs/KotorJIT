// SHA-256, implemented here rather than linked.
//
// The runtime is an injected DLL that must load before the game's own CRT
// finishes settling, and it is cross-compiled for two targets. Pulling a crypto
// library in for one hash function would cost more than the eighty lines below.
// This is FIPS 180-4, the public-domain construction; it is not novel and is not
// meant to be.
#pragma once

#include <cstddef>
#include <cstdint>
#include <string>

namespace kp::image {

class Sha256 {
  public:
    Sha256();
    void update(const void* data, std::size_t len);
    // Finalises the hash. The object must not be updated afterwards.
    std::string hex();

  private:
    void compress(const std::uint8_t block[64]);

    std::uint32_t state_[8];
    std::uint64_t bits_ = 0;
    std::uint8_t  buf_[64];
    std::size_t   buffered_ = 0;
};

std::string sha256_hex(const void* data, std::size_t len);

// Returns an empty string when the file cannot be read. Callers treat that as
// "unidentifiable", never as a hash of nothing -- the empty input has a real
// digest and confusing the two would let a missing file match a build.
std::string sha256_file(const std::string& path);

}  // namespace kp::image

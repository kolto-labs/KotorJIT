// Telling ciphertext from code, on evidence rather than on a section name.
//
// Entropy alone does not decide it. Measured on the four images this module was
// developed against (bits per byte, whole section):
//
//   Steam swkotor.exe  .text   7.9999   encrypted
//   Steam swkotor.exe  .bind   7.9787   packer stub around an encrypted payload
//   GOG   swkotor.exe  .text   6.4967   plain MSVC code
//   kotor2 (ELF)       .text   6.2332   plain GCC code
//   kotor2             .rodata 6.4671   plain data
//
// So the entropy gate has to sit high, and something else has to carry the rest.
// That something is marker density -- the debris real compiled code always
// leaves. Same four images, frame-setup prologues per KB:
//
//   GOG .text     0.1753   (55 8b ec, MSVC)
//   kotor2 .text  0.3072   (mostly 55 89 e5, GCC)
//   .bind         0.0174
//   Steam .text   0.0000
//
// A floor of 0.05/KB clears real code by 3x and ciphertext by 3x the other way.
// It also sits far above chance: three specific bytes recur roughly 0.2 times in
// 3 MB of random data, which is 0.00006/KB, so a lucky match cannot lift an
// encrypted section over the line.
//
// Both prologue encodings are counted. The contract names 55 8b ec, which is
// what MSVC emitted for the Windows builds; GCC writes the same instruction pair
// as 55 89 e5, and the ELF target is GCC output. Counting only the first would
// have left the ELF with almost no markers.
#include <cmath>
#include <cstring>

#include "internal.hpp"

namespace kp::image {
namespace {

// Near-maximal, with room for the sampling shortfall a finite buffer always has.
constexpr double kCiphertextEntropy = 7.90;

// Per KB. Anything at or above this is real code, whatever the entropy says.
constexpr double kMarkerFloor = 0.05;

// Below this the histogram is too sparse to mean anything: 1 KB of pure random
// bytes measures about 7.82 bits, which would read as "not quite ciphertext" for
// reasons that have nothing to do with the data.
constexpr std::size_t kMinBytes = 4096;

std::size_t count_pattern(const std::uint8_t* d, std::size_t len, const std::uint8_t* pat, std::size_t plen) {
    if (len < plen) return 0;
    std::size_t n = 0;
    for (std::size_t i = 0; i + plen <= len; ++i) {
        if (std::memcmp(d + i, pat, plen) == 0) ++n;
    }
    return n;
}

// Runs, not bytes: MSVC pads between functions with a stretch of int3, and one
// run of forty is one marker, not forty.
std::size_t count_int3_runs(const std::uint8_t* d, std::size_t len) {
    std::size_t runs = 0;
    std::size_t i = 0;
    while (i + 3 <= len) {
        if (d[i] == 0xcc && d[i + 1] == 0xcc && d[i + 2] == 0xcc) {
            ++runs;
            while (i < len && d[i] == 0xcc) ++i;
        } else {
            ++i;
        }
    }
    return runs;
}

}  // namespace

double shannon_entropy(const std::uint8_t* data, std::size_t len) {
    if (data == nullptr || len == 0) return 0.0;

    std::size_t hist[256] = {0};
    for (std::size_t i = 0; i < len; ++i) ++hist[data[i]];

    const double n = static_cast<double>(len);
    double bits = 0.0;
    for (std::size_t c : hist) {
        if (c == 0) continue;
        const double p = static_cast<double>(c) / n;
        bits -= p * std::log2(p);
    }
    return bits;
}

EntropyVerdict classify(const std::uint8_t* data, std::size_t len) {
    EntropyVerdict v;
    if (data == nullptr || len == 0) return v;

    v.bits_per_byte = shannon_entropy(data, len);

    static const std::uint8_t kMsvcPrologue[3] = {0x55, 0x8b, 0xec};  // push ebp; mov ebp,esp
    static const std::uint8_t kGccPrologue[3]  = {0x55, 0x89, 0xe5};  // same pair, GCC encoding
    v.prologue_count = count_pattern(data, len, kMsvcPrologue, 3) +
                       count_pattern(data, len, kGccPrologue, 3);
    v.int3_runs = count_int3_runs(data, len);

    if (len < kMinBytes) return v;

    const double kb = static_cast<double>(len) / 1024.0;
    const bool markers_absent = (static_cast<double>(v.prologue_count) / kb) < kMarkerFloor &&
                                (static_cast<double>(v.int3_runs) / kb) < kMarkerFloor;

    v.is_ciphertext = v.bits_per_byte >= kCiphertextEntropy && markers_absent;
    return v;
}

}  // namespace kp::image

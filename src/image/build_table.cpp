// Which builds we recognise, and what "deciphered" looks like for each.
//
// The table itself is generated. tools/gen_address_tables.py reads the same
// reverse-engineering corpus and reference images that produce
// data/addresses/*.json, and emits src/generated/builds.inc from them, so the
// sentinel and the known-good digests have exactly one source.
//
// This used to be a hand-written array, which meant the sentinel VA and every
// digest existed twice -- here and in the JSON -- with nothing keeping them in
// step. They agreed, right up until they would not have.
//
// Every digest is computed from files on disk, never from a running game. What
// that does and does not prove is set out in docs/steam-gog-equivalence.md.
#include <cstring>

#include "internal.hpp"

namespace kp::image {
namespace {

#include "generated/builds.inc"
#include "generated/builds_macho.inc"

int hex_value(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

}  // namespace

std::vector<std::uint8_t> parse_hex(const char* s) {
    std::vector<std::uint8_t> out;
    if (s == nullptr) return out;
    const std::size_t n = std::strlen(s);
    if (n % 2 != 0) return out;
    for (std::size_t i = 0; i < n; i += 2) {
        const int hi = hex_value(s[i]);
        const int lo = hex_value(s[i + 1]);
        if (hi < 0 || lo < 0) return {};
        out.push_back(static_cast<std::uint8_t>((hi << 4) | lo));
    }
    return out;
}

const BuildRecord* build_table(std::size_t& count) {
    count = sizeof kBuilds / sizeof kBuilds[0];
    return kBuilds;
}

const BuildRecord* macho_build_table(std::size_t& count) {
    count = sizeof kBuildsMachO / sizeof kBuildsMachO[0];
    return kBuildsMachO;
}

const BuildRecord* lookup_build(const std::string& sha256) {
    if (sha256.empty()) return nullptr;
    std::size_t n = 0;
    const BuildRecord* t = build_table(n);
    for (std::size_t i = 0; i < n; ++i) {
        if (sha256 == t[i].sha256) return &t[i];
    }
    t = macho_build_table(n);
    for (std::size_t i = 0; i < n; ++i) {
        if (sha256 == t[i].sha256) return &t[i];
    }
    return nullptr;
}

}  // namespace kp::image

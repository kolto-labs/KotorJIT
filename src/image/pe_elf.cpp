#include "pe_elf.hpp"

#include <cstring>

namespace kp::image {
namespace {

// Little-endian by construction: both targets are i386, and reading through
// these helpers keeps the parsers free of alignment assumptions about the
// buffer they were handed.
bool u16_at(const std::uint8_t* p, std::size_t n, std::size_t off, std::uint16_t& out) {
    if (off + 2 > n) return false;
    out = static_cast<std::uint16_t>(p[off] | (p[off + 1] << 8));
    return true;
}

bool u32_at(const std::uint8_t* p, std::size_t n, std::size_t off, std::uint32_t& out) {
    if (off + 4 > n) return false;
    out = static_cast<std::uint32_t>(p[off]) | (static_cast<std::uint32_t>(p[off + 1]) << 8) |
          (static_cast<std::uint32_t>(p[off + 2]) << 16) | (static_cast<std::uint32_t>(p[off + 3]) << 24);
    return true;
}

}  // namespace

// strnlen is POSIX, not C++, and the Windows half is cross-compiled. Both name
// fields we read are bounded, so bound the read too.
std::size_t bounded_len(const char* p, std::size_t max) {
    std::size_t n = 0;
    while (n < max && p[n] != '\0') ++n;
    return n;
}

namespace pe {

bool looks_like(const std::uint8_t* p, std::size_t n) {
    if (n < 0x40 || p[0] != 'M' || p[1] != 'Z') return false;
    std::uint32_t lfanew = 0;
    if (!u32_at(p, n, 0x3c, lfanew)) return false;
    // Subtraction, not addition: this build's size_t is 32-bit (see
    // CMakeLists' -m32), so "lfanew + 4 > n" wraps for lfanew near
    // UINT32_MAX and lets the bounds check pass, then memcmp reads far out
    // of bounds. n >= 4 is already implied by the n < 0x40 check above.
    if (lfanew > n - 4) return false;
    return std::memcmp(p + lfanew, "PE\0\0", 4) == 0;
}

bool read_headers(const std::uint8_t* p, std::size_t n, Headers& out, std::size_t* needed) {
    if (needed != nullptr) *needed = 0;
    if (!looks_like(p, n)) return false;

    std::uint32_t lfanew = 0;
    u32_at(p, n, 0x3c, lfanew);
    const std::size_t coff = lfanew + 4;

    std::uint16_t nsec = 0, optsz = 0;
    if (!u16_at(p, n, coff + 0, out.machine)) return false;
    if (!u16_at(p, n, coff + 2, nsec)) return false;
    if (!u16_at(p, n, coff + 16, optsz)) return false;

    const std::size_t opt = coff + 20;
    std::uint16_t magic = 0;
    if (!u16_at(p, n, opt, magic)) return false;
    if (magic != 0x10b) return false;  // PE32 only; PE32+ is not a target

    const std::size_t sec_table = opt + optsz;
    const std::size_t end = sec_table + 40u * nsec;
    if (needed != nullptr) *needed = end;
    if (end > n) return false;

    out.pe_offset = lfanew;
    out.optional_header_size = optsz;
    u32_at(p, n, opt + 16, out.entry_rva);
    u32_at(p, n, opt + 28, out.image_base);
    u32_at(p, n, opt + 32, out.section_alignment);
    u32_at(p, n, opt + 36, out.file_alignment);
    u32_at(p, n, opt + 56, out.size_of_image);
    u32_at(p, n, opt + 60, out.size_of_headers);

    out.sections.clear();
    out.sections.reserve(nsec);
    for (std::uint16_t i = 0; i < nsec; ++i) {
        const std::size_t o = sec_table + 40u * i;
        SectionHeader s;
        // The name field is eight bytes and is only NUL-terminated when shorter,
        // so it must be bounded rather than read as a C string.
        char raw[9] = {0};
        std::memcpy(raw, p + o, 8);
        s.name.assign(raw, bounded_len(raw, 8));
        u32_at(p, n, o + 8, s.virtual_size);
        u32_at(p, n, o + 12, s.virtual_address);
        u32_at(p, n, o + 16, s.size_of_raw_data);
        u32_at(p, n, o + 20, s.pointer_to_raw_data);
        u32_at(p, n, o + 36, s.characteristics);
        out.sections.push_back(std::move(s));
    }
    return true;
}

}  // namespace pe

namespace elf {

bool looks_like(const std::uint8_t* p, std::size_t n) {
    if (n < 52) return false;
    if (std::memcmp(p, "\x7f" "ELF", 4) != 0) return false;
    if (p[4] != 1) return false;  // ELFCLASS32
    if (p[5] != 1) return false;  // ELFDATA2LSB
    return true;
}

bool read_headers(const std::uint8_t* p, std::size_t n, Headers& out) {
    if (!looks_like(p, n)) return false;

    u16_at(p, n, 16, out.type);
    u16_at(p, n, 18, out.machine);
    u32_at(p, n, 24, out.entry);
    u32_at(p, n, 28, out.phoff);
    u32_at(p, n, 32, out.shoff);
    u16_at(p, n, 42, out.phentsize);
    u16_at(p, n, 44, out.phnum);
    u16_at(p, n, 46, out.shentsize);
    u16_at(p, n, 48, out.shnum);
    u16_at(p, n, 50, out.shstrndx);

    if (out.phentsize < 32) return false;

    out.loads.clear();
    for (std::uint16_t i = 0; i < out.phnum; ++i) {
        const std::size_t o = out.phoff + static_cast<std::size_t>(out.phentsize) * i;
        Segment s;
        if (!u32_at(p, n, o + 0, s.type)) return false;
        if (s.type != kPtLoad) continue;
        u32_at(p, n, o + 4, s.offset);
        u32_at(p, n, o + 8, s.vaddr);
        u32_at(p, n, o + 16, s.filesz);
        u32_at(p, n, o + 20, s.memsz);
        u32_at(p, n, o + 24, s.flags);
        out.loads.push_back(s);
    }
    return !out.loads.empty();
}

}  // namespace elf

}  // namespace kp::image

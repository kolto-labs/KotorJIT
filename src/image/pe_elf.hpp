// The two on-disk shapes we care about, read defensively.
//
// Only the fields the runtime actually uses are lifted out. Anything read from a
// packed or hostile file is bounds-checked against the buffer it came from,
// because "the header said so" is not a reason to trust an offset.
#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace kp::image {

// Bounded string length, since strnlen is POSIX and one target is not.
std::size_t bounded_len(const char*, std::size_t);

namespace pe {

struct SectionHeader {
    std::string   name;
    std::uint32_t virtual_size = 0;
    std::uint32_t virtual_address = 0;   // RVA
    std::uint32_t size_of_raw_data = 0;
    std::uint32_t pointer_to_raw_data = 0;
    std::uint32_t characteristics = 0;
};

struct Headers {
    std::uint16_t machine = 0;
    std::uint32_t pe_offset = 0;
    std::uint16_t optional_header_size = 0;
    std::uint32_t entry_rva = 0;
    std::uint32_t image_base = 0;
    std::uint32_t section_alignment = 0;
    std::uint32_t file_alignment = 0;
    std::uint32_t size_of_image = 0;
    std::uint32_t size_of_headers = 0;
    std::vector<SectionHeader> sections;
};

constexpr std::uint32_t kMemExecute = 0x20000000u;
constexpr std::uint32_t kCntCode    = 0x00000020u;

bool looks_like(const std::uint8_t*, std::size_t);

// `needed` reports how many bytes from the start of the image must be present
// for the headers to parse, so a caller reading a live image can widen its
// window and retry instead of guessing.
bool read_headers(const std::uint8_t*, std::size_t, Headers&, std::size_t* needed = nullptr);

}  // namespace pe

namespace elf {

struct Segment {
    std::uint32_t type = 0;
    std::uint32_t offset = 0;
    std::uint32_t vaddr = 0;
    std::uint32_t filesz = 0;
    std::uint32_t memsz = 0;
    std::uint32_t flags = 0;
};

struct SectionHeader {
    std::string   name;
    std::uint32_t name_offset = 0;
    std::uint32_t type = 0;
    std::uint32_t flags = 0;
    std::uint32_t addr = 0;
    std::uint32_t offset = 0;
    std::uint32_t size = 0;
};

struct Headers {
    std::uint16_t type = 0;
    std::uint16_t machine = 0;
    std::uint32_t entry = 0;
    std::uint32_t phoff = 0;
    std::uint32_t shoff = 0;
    std::uint16_t phentsize = 0;
    std::uint16_t phnum = 0;
    std::uint16_t shentsize = 0;
    std::uint16_t shnum = 0;
    std::uint16_t shstrndx = 0;
    std::vector<Segment> loads;
};

constexpr std::uint32_t kPtLoad     = 1;
constexpr std::uint32_t kShtNobits  = 8;
constexpr std::uint32_t kShtStrtab  = 3;
constexpr std::uint32_t kShfAlloc   = 0x2;
constexpr std::uint32_t kShfExec    = 0x4;
constexpr std::uint32_t kPfExec     = 0x1;

bool looks_like(const std::uint8_t*, std::size_t);
bool read_headers(const std::uint8_t*, std::size_t, Headers&);

}  // namespace elf

}  // namespace kp::image

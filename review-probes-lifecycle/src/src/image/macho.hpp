// Thin little-endian Mach-O file metadata. No Apple SDK or host-width assumptions.
#pragma once
#include <cstddef>
#include <array>
#include <cstdint>
#include <string>
#include <vector>

namespace kp::image::macho {
struct Section {
    std::string name, segment_name;
    std::uint64_t address = 0, size = 0;
    std::uint32_t file_offset = 0, alignment = 0, flags = 0;
    bool zero_fill = false;
};
struct Segment {
    std::string name;
    std::uint64_t address = 0, size = 0, file_offset = 0, file_size = 0;
    std::uint32_t max_protection = 0, initial_protection = 0, flags = 0;
    std::vector<Section> sections;
};
struct Headers {
    unsigned bits = 0;
    std::uint32_t cpu_type = 0, cpu_subtype = 0, file_type = 0, flags = 0;
    std::uint32_t command_count = 0, command_bytes = 0;
    std::vector<Segment> segments;
    // LC_UUID is optional in the file format. A present one must be exactly
    // one well-formed 24-byte command; a duplicate or odd size refuses.
    bool has_uuid = false;
    std::array<std::uint8_t, 16> uuid{};
};
// Requires a complete on-disk thin image, not a mapped-memory header window.
// Addresses are preferred unslid VAs; caller must establish ASLR separately.
// Unknown commands are bounded and skipped: success is not loader admission.
// Failure leaves out unchanged and supplies a diagnostic.
bool read_file(const std::uint8_t*, std::size_t, Headers& out, std::string& error);

// One architecture's bytes inside a container. For a thin input the slice is
// the whole file and fat is false. Offsets are container-relative and stay
// 64-bit on every host, because FAT_MAGIC_64 entries can exceed size_t on i386.
struct Slice {
    std::uint64_t offset = 0, size = 0;
    std::uint32_t cpu_type = 0, cpu_subtype = 0, align = 0;
    bool fat = false, fat64 = false;
};
// Capability bits (CPU_SUBTYPE_MASK, the high byte) are ignored on both sides.
inline constexpr std::uint32_t kSubtypeCapabilityMask = 0xff000000u;

// Selects the slice for (cpu_type, cpu_subtype) from a big-endian FAT_MAGIC or
// FAT_MAGIC_64 container, or accepts a matching thin image as a whole-file
// slice. Refuses: truncated headers or arch tables, implausible arch counts,
// entries past the file end, entries overlapping the header/table or each
// other, offsets that break their declared alignment, duplicate architectures,
// a missing architecture, and a chosen slice that is not a thin Mach-O of the
// same CPU (nested fat, garbage, or a header that disagrees with its entry).
// Failure leaves out unchanged and supplies a diagnostic.
bool select_slice(const std::uint8_t*, std::size_t, std::uint32_t cpu_type,
                  std::uint32_t cpu_subtype, Slice& out, std::string& error);

// What a caller records to name one architecture of one shipped file. All
// three are needed: the container hash names the download, the slice hash
// names the code that runs, and LC_UUID is what a Darwin loader, crash log or
// dSYM reports. identify refuses a slice without LC_UUID.
struct Identity {
    std::string container_sha256, slice_sha256;
    std::array<std::uint8_t, 16> uuid{};
    Slice slice;
    Headers headers;
};
bool identify(const std::uint8_t*, std::size_t, std::uint32_t cpu_type,
              std::uint32_t cpu_subtype, Identity& out, std::string& error);
}  // namespace kp::image::macho

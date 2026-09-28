#include "macho.hpp"
#include "sha256.hpp"
#include <limits>
#include <utility>

namespace kp::image::macho {
namespace {
std::uint32_t u32(const std::uint8_t* p) {
    return std::uint32_t(p[0]) | (std::uint32_t(p[1]) << 8) |
           (std::uint32_t(p[2]) << 16) | (std::uint32_t(p[3]) << 24);
}
std::uint64_t u64(const std::uint8_t* p) {
    return u32(p) | (std::uint64_t(u32(p + 4)) << 32);
}
bool range(std::uint64_t offset, std::uint64_t size, std::uint64_t limit) {
    return offset <= limit && size <= limit - offset;
}
bool contains(std::uint64_t base, std::uint64_t extent,
              std::uint64_t address, std::uint64_t size) {
    return address >= base && range(address - base, size, extent);
}
std::string name(const std::uint8_t* p) {
    std::size_t n = 0;
    while (n < 16 && p[n]) ++n;
    return std::string(reinterpret_cast<const char*>(p), n);
}
}
bool read_file(const std::uint8_t* p, std::size_t n, Headers& out, std::string& error) {
    auto fail = [&](const char* why) { error = why; return false; };
    if (!p || n < 4) return fail("truncated Mach-O magic");
    const auto magic = u32(p);
    if (magic == 0xbebafeca || magic == 0xcafebabe ||
        magic == 0xbfbafeca || magic == 0xcafebabf)
        return fail("fat Mach-O is unsupported; select a thin slice first");
    if (magic == 0xcefaedfe || magic == 0xcffaedfe)
        return fail("big-endian Mach-O is unsupported");
    if (magic != 0xfeedface && magic != 0xfeedfacf) return fail("not a Mach-O image");
    const bool wide = magic == 0xfeedfacf;
    const std::size_t header = wide ? 32 : 28;
    if (n < header) return fail("truncated Mach-O header");
    Headers h;
    h.bits = wide ? 64 : 32;
    h.cpu_type = u32(p + 4); h.cpu_subtype = u32(p + 8);
    // ABI64_32 uses 64-bit Mach-O containers too; CPU identity is retained raw.
    if (wide != ((h.cpu_type & 0x03000000u) != 0)) return fail("CPU/header bitness mismatch");
    h.file_type = u32(p + 12); h.command_count = u32(p + 16);
    h.command_bytes = u32(p + 20); h.flags = u32(p + 24);
    if (!range(header, h.command_bytes, n) || h.command_count > h.command_bytes / 8)
        return fail("invalid load-command region");
    std::size_t cursor = header, end = header + h.command_bytes;
    for (std::uint32_t i = 0; i < h.command_count; ++i) {
        if (!range(cursor, 8, end)) return fail("truncated load command");
        const auto command = u32(p + cursor), bytes = u32(p + cursor + 4);
        if (bytes < 8 || bytes % (wide ? 8 : 4) || !range(cursor, bytes, end))
            return fail("invalid load-command size");
        if (command == 1 || command == 0x19) {
            if ((command == 0x19) != wide) return fail("segment/header bitness mismatch");
            const std::size_t fixed = wide ? 72 : 56, section_bytes = wide ? 80 : 68;
            if (bytes < fixed) return fail("truncated segment");
            const auto* q = p + cursor;
            Segment s;
            s.name = name(q + 8);
            s.address = wide ? u64(q + 24) : u32(q + 24);
            s.size = wide ? u64(q + 32) : u32(q + 28);
            s.file_offset = wide ? u64(q + 40) : u32(q + 32);
            s.file_size = wide ? u64(q + 48) : u32(q + 36);
            const std::size_t prot = wide ? 56 : 40;
            s.max_protection = u32(q + prot); s.initial_protection = u32(q + prot + 4);
            const auto count = u32(q + prot + 8); s.flags = u32(q + prot + 12);
            const auto max_address = wide ? std::numeric_limits<std::uint64_t>::max() : 0x100000000ull;
            if (!range(s.address, s.size, max_address) || !range(s.file_offset, s.file_size, n) ||
                s.file_size > s.size) return fail("invalid segment extent");
            if (count > (bytes - fixed) / section_bytes || fixed + std::uint64_t(count) * section_bytes != bytes)
                return fail("invalid segment section table");
            for (std::uint32_t j = 0; j < count; ++j) {
                const auto* r = q + fixed + std::size_t(j) * section_bytes;
                Section t;
                t.name = name(r); t.segment_name = name(r + 16);
                t.address = wide ? u64(r + 32) : u32(r + 32);
                t.size = wide ? u64(r + 40) : u32(r + 36);
                const std::size_t off = wide ? 48 : 40;
                t.file_offset = u32(r + off); t.alignment = u32(r + off + 4);
                const auto reloc = u32(r + off + 8), reloc_count = u32(r + off + 12);
                t.flags = u32(r + off + 16);
                const auto type = t.flags & 0xff;
                t.zero_fill = type == 1 || type == 0xc || type == 0x12;
                if (!contains(s.address, s.size, t.address, t.size) || t.alignment >= h.bits)
                    return fail("invalid section virtual extent or alignment");
                // MH_OBJECT has an unnamed enclosing segment, with named sections.
                if (h.file_type != 1 && t.segment_name != s.name) return fail("section segment-name mismatch");
                if (!t.zero_fill && (!range(t.file_offset, t.size, n) ||
                    !contains(s.file_offset, s.file_size, t.file_offset, t.size)))
                    return fail("section bytes outside segment");
                if (reloc_count && !range(reloc, std::uint64_t(reloc_count) * 8, n))
                    return fail("section relocations outside image");
                s.sections.push_back(std::move(t));
            }
            h.segments.push_back(std::move(s));
        } else if (command == 0x1b) {  // LC_UUID
            if (bytes != 24) return fail("invalid LC_UUID size");
            if (h.has_uuid) return fail("duplicate LC_UUID");
            h.has_uuid = true;
            for (std::size_t k = 0; k < 16; ++k) h.uuid[k] = p[cursor + 8 + k];
        }
        cursor += bytes;
    }
    if (cursor != end) return fail("load-command count/size mismatch");
    out = std::move(h); error.clear(); return true;
}
namespace {
std::uint32_t be32(const std::uint8_t* p) {
    return (std::uint32_t(p[0]) << 24) | (std::uint32_t(p[1]) << 16) |
           (std::uint32_t(p[2]) << 8) | std::uint32_t(p[3]);
}
std::uint64_t be64(const std::uint8_t* p) { return (std::uint64_t(be32(p)) << 32) | be32(p + 4); }
bool same_cpu(std::uint32_t type_a, std::uint32_t sub_a, std::uint32_t type_b, std::uint32_t sub_b) {
    return type_a == type_b &&
           (sub_a & ~kSubtypeCapabilityMask) == (sub_b & ~kSubtypeCapabilityMask);
}
// cctools' own heuristic: a real fat file never lists this many slices, and
// Java class files share FAT_MAGIC with their version in the count field.
constexpr std::uint32_t kMaxFatArchs = 32;
// Apple's tools cap slice alignment at 2^15 (MAXSECTALIGN).
constexpr std::uint32_t kMaxFatAlign = 15;
}  // namespace

bool select_slice(const std::uint8_t* p, std::size_t n, std::uint32_t cpu_type,
                  std::uint32_t cpu_subtype, Slice& out, std::string& error) {
    auto fail = [&](const std::string& why) { error = why; return false; };
    if (!p || n < 4) return fail("truncated container magic");
    const auto magic = be32(p);
    if (magic == 0xbebafeca || magic == 0xbfbafeca)
        return fail("little-endian fat header is not a Mach-O container");
    if (magic != 0xcafebabe && magic != 0xcafebabf) {
        // Thin: the image is its own slice if it is this CPU.
        Headers h;
        std::string why;
        if (!read_file(p, n, h, why)) return fail("thin image: " + why);
        if (!same_cpu(h.cpu_type, h.cpu_subtype, cpu_type, cpu_subtype))
            return fail("missing architecture: thin image is another CPU");
        Slice s;
        s.size = n; s.cpu_type = h.cpu_type; s.cpu_subtype = h.cpu_subtype;
        out = s; error.clear(); return true;
    }
    const bool wide = magic == 0xcafebabf;
    const std::uint64_t limit = n, entry = wide ? 32 : 20;
    if (n < 8) return fail("truncated fat header");
    const auto count = be32(p + 4);
    if (count == 0 || count > kMaxFatArchs) return fail("implausible fat arch count");
    const std::uint64_t table_end = 8 + entry * count;
    if (table_end > limit) return fail("truncated fat arch table");
    std::vector<Slice> all;
    all.reserve(count);
    for (std::uint32_t i = 0; i < count; ++i) {
        const auto* q = p + 8 + entry * i;
        Slice s;
        s.fat = true; s.fat64 = wide;
        s.cpu_type = be32(q); s.cpu_subtype = be32(q + 4);
        s.offset = wide ? be64(q + 8) : be32(q + 8);
        s.size = wide ? be64(q + 16) : be32(q + 12);
        s.align = be32(q + (wide ? 24 : 16));
        if (s.size == 0) return fail("empty slice in fat arch table");
        if (!range(s.offset, s.size, limit)) return fail("slice outside container");
        if (s.align > kMaxFatAlign) return fail("implausible slice alignment");
        if (s.offset & ((std::uint64_t(1) << s.align) - 1)) return fail("slice offset breaks its alignment");
        if (s.offset < table_end) return fail("slice overlaps the fat header or arch table");
        for (const auto& o : all) {
            if (s.offset < o.offset + o.size && o.offset < s.offset + s.size)
                return fail("slices overlap");
            if (same_cpu(s.cpu_type, s.cpu_subtype, o.cpu_type, o.cpu_subtype))
                return fail("duplicate architecture in fat arch table");
        }
        all.push_back(s);
    }
    const Slice* chosen = nullptr;
    for (const auto& s : all)
        if (same_cpu(s.cpu_type, s.cpu_subtype, cpu_type, cpu_subtype)) chosen = &s;
    if (!chosen) return fail("missing architecture in fat container");
    // The slice itself must be a complete thin image of the CPU its entry names.
    // Offsets inside it are slice-relative, which is what read_file expects.
    const auto* body = p + chosen->offset;
    const auto size = static_cast<std::size_t>(chosen->size);
    if (size >= 4) {
        const auto inner = be32(body);
        if (inner == 0xcafebabe || inner == 0xcafebabf || inner == 0xbebafeca || inner == 0xbfbafeca)
            return fail("nested fat container inside a slice");
    }
    Headers h;
    std::string why;
    if (!read_file(body, size, h, why)) return fail("selected slice: " + why);
    if (!same_cpu(h.cpu_type, h.cpu_subtype, chosen->cpu_type, chosen->cpu_subtype))
        return fail("slice header CPU disagrees with its fat arch entry");
    out = *chosen; error.clear(); return true;
}

bool identify(const std::uint8_t* p, std::size_t n, std::uint32_t cpu_type,
              std::uint32_t cpu_subtype, Identity& out, std::string& error) {
    Slice s;
    if (!select_slice(p, n, cpu_type, cpu_subtype, s, error)) return false;
    const auto* body = p + s.offset;
    const auto size = static_cast<std::size_t>(s.size);
    Identity id;
    if (!read_file(body, size, id.headers, error)) return false;
    if (!id.headers.has_uuid) { error = "slice has no LC_UUID; identity needs all three names"; return false; }
    id.uuid = id.headers.uuid;
    id.slice = s;
    id.container_sha256 = kp::image::sha256_hex(p, n);
    id.slice_sha256 = kp::image::sha256_hex(body, size);
    out = std::move(id); error.clear(); return true;
}
}  // namespace kp::image::macho

// Building the section map from an address space rather than from a file.
//
// The distinction is the point of the module. On-disk headers describe the
// packed layout, and the offline unpacker renames sections (.text becomes
// .textU), so a file-derived map is wrong in two different ways at once. What is
// resident is the only thing worth patching against.
#include <cstring>

#include "internal.hpp"
#include "pe_elf.hpp"

namespace kp::image {
namespace {

constexpr std::size_t kFirstHeaderWindow = 0x400;
constexpr std::size_t kMaxHeaderWindow   = 0x10000;
constexpr std::size_t kMaxTableBytes     = 1u << 20;

std::uint16_t rd16(const std::uint8_t* p) {
    return static_cast<std::uint16_t>(p[0] | (p[1] << 8));
}

std::uint32_t rd32(const std::uint8_t* p) {
    return static_cast<std::uint32_t>(p[0]) | (static_cast<std::uint32_t>(p[1]) << 8) |
           (static_cast<std::uint32_t>(p[2]) << 16) | (static_cast<std::uint32_t>(p[3]) << 24);
}

}  // namespace

std::optional<pe::Headers> read_pe_headers(const LoadedImage& img) {
    // The DOS stub decides where everything else is, and its length varies: the
    // GOG build puts e_lfanew at 0x910, far outside any fixed first guess. Read
    // it, then size the window from it.
    std::vector<std::uint8_t> dos;
    if (!img.read_vector(img.base(), 0x40, dos)) return std::nullopt;
    if (dos[0] != 'M' || dos[1] != 'Z') return std::nullopt;

    const std::uint32_t lfanew = rd32(dos.data() + 0x3c);
    if (lfanew > kMaxHeaderWindow) return std::nullopt;

    std::vector<std::uint8_t> win;
    if (!img.read_vector(img.base(), lfanew + kFirstHeaderWindow, win)) return std::nullopt;

    pe::Headers h;
    std::size_t needed = 0;
    if (pe::read_headers(win.data(), win.size(), h, &needed)) return h;
    if (needed == 0 || needed > kMaxHeaderWindow) return std::nullopt;

    if (!img.read_vector(img.base(), needed, win)) return std::nullopt;
    if (!pe::read_headers(win.data(), win.size(), h)) return std::nullopt;
    return h;
}

namespace {

std::optional<elf::Headers> read_elf_headers(const LoadedImage& img) {
    std::vector<std::uint8_t> ehdr;
    if (!img.read_vector(img.base(), 52, ehdr)) return std::nullopt;
    if (!elf::looks_like(ehdr.data(), ehdr.size())) return std::nullopt;

    elf::Headers probe;
    // read_headers indexes by file offset. Reading [base, base+phoff+table) and
    // handing it over keeps one parser for files and address spaces; the
    // segment check below is what makes the offset-as-displacement assumption
    // safe rather than hopeful.
    const std::uint32_t phoff     = rd32(ehdr.data() + 28);
    const std::uint16_t phentsize = rd16(ehdr.data() + 42);
    const std::uint16_t phnum     = rd16(ehdr.data() + 44);

    const std::size_t span = static_cast<std::size_t>(phoff) + static_cast<std::size_t>(phentsize) * phnum;
    if (span == 0 || span > kMaxTableBytes) return std::nullopt;

    std::vector<std::uint8_t> buf;
    if (!img.read_vector(img.base(), span, buf)) return std::nullopt;
    if (!elf::read_headers(buf.data(), buf.size(), probe)) return std::nullopt;

    // The program header table must live inside a segment that is actually
    // loaded, or we read it from somewhere the loader never placed it.
    const std::uintptr_t phdr_va = img.base() + phoff;
    bool covered = false;
    for (const elf::Segment& s : probe.loads) {
        if (phdr_va >= s.vaddr && phdr_va < s.vaddr + s.filesz) covered = true;
    }
    if (!covered) return std::nullopt;
    return probe;
}

// Section headers, when they can be reached. They cannot be, in a live process:
// e_shoff sits past the last PT_LOAD in both KOTOR 2 and most linker output.
// Rejecting a table read out of zeroed .bss is what the validation below is for.
bool read_elf_sections(const LoadedImage& img, const elf::Headers& h, std::vector<Section>& out) {
    if (h.shoff == 0 || h.shnum == 0 || h.shentsize < 40) return false;
    if (h.shstrndx >= h.shnum) return false;

    const std::size_t table = static_cast<std::size_t>(h.shentsize) * h.shnum;
    if (table > kMaxTableBytes) return false;

    std::vector<std::uint8_t> raw;
    if (!img.read_vector(img.base() + h.shoff, table, raw)) return false;

    std::vector<elf::SectionHeader> shs;
    shs.reserve(h.shnum);
    for (std::uint16_t i = 0; i < h.shnum; ++i) {
        const std::uint8_t* p = raw.data() + static_cast<std::size_t>(h.shentsize) * i;
        elf::SectionHeader s;
        s.name_offset = rd32(p + 0);
        s.type        = rd32(p + 4);
        s.flags       = rd32(p + 8);
        s.addr        = rd32(p + 12);
        s.offset      = rd32(p + 16);
        s.size        = rd32(p + 20);
        shs.push_back(s);
    }

    const elf::SectionHeader& strtab = shs[h.shstrndx];
    if (strtab.type != elf::kShtStrtab || strtab.size == 0 || strtab.size > kMaxTableBytes) return false;

    std::vector<std::uint8_t> names;
    if (!img.read_vector(img.base() + strtab.offset, strtab.size, names)) return false;
    if (names[0] != 0) return false;

    for (elf::SectionHeader& s : shs) {
        if (s.name_offset >= names.size()) continue;
        const char* p = reinterpret_cast<const char*>(names.data() + s.name_offset);
        s.name.assign(p, bounded_len(p, names.size() - s.name_offset));
    }

    out.clear();
    for (const elf::SectionHeader& s : shs) {
        if ((s.flags & elf::kShfAlloc) == 0) continue;   // not resident, so not our concern
        // NOBITS is .bss and .tbss: resident, but with no bytes in the image.
        // There is nothing to classify, hash or dump, and reading at their
        // addresses in a file-backed view returns whatever follows them.
        if (s.type == elf::kShtNobits) continue;
        if (s.addr == 0 || s.size == 0) continue;
        Section sec;
        sec.name = s.name.empty() ? "<unnamed>" : s.name;
        sec.va = s.addr;
        sec.size = s.size;
        sec.executable = (s.flags & elf::kShfExec) != 0;
        out.push_back(std::move(sec));
    }
    return !out.empty();
}

void elf_sections_from_segments(const elf::Headers& h, std::vector<Section>& out) {
    out.clear();
    for (std::size_t i = 0; i < h.loads.size(); ++i) {
        const elf::Segment& s = h.loads[i];
        Section sec;
        sec.name = "seg" + std::to_string(i);
        sec.va = s.vaddr;
        // filesz, not memsz: the tail of a segment is .bss the loader zeroed,
        // and hashing or classifying zero fill says nothing about the code.
        sec.size = s.filesz;
        sec.executable = (s.flags & elf::kPfExec) != 0;
        out.push_back(std::move(sec));
    }
}

}  // namespace

const char* to_string(ParseRoute r) {
    switch (r) {
        case ParseRoute::PeSectionTable:    return "pe section table";
        case ParseRoute::ElfSectionHeaders: return "elf section headers";
        case ParseRoute::ElfProgramHeaders: return "elf program headers (names synthesised)";
    }
    return "unknown";
}

std::optional<Format> detect_format(const LoadedImage& img) {
    std::uint8_t magic[4] = {0};
    if (!img.read(img.base(), magic, sizeof magic)) return std::nullopt;
    if (magic[0] == 'M' && magic[1] == 'Z') return Format::Pe32;
    if (magic[0] == 0x7f && magic[1] == 'E' && magic[2] == 'L' && magic[3] == 'F') return Format::Elf32;
    // Mach-O 32-bit LE (0xFEEDFACE) or fat (0xCAFEBABE). Recognized so Mac
    // profiles can bind; parse/load remain PE/ELF until a Mach-O loader exists.
    if ((magic[0] == 0xCE && magic[1] == 0xFA && magic[2] == 0xED && magic[3] == 0xFE) ||
        (magic[0] == 0xFE && magic[1] == 0xED && magic[2] == 0xFA && magic[3] == 0xCE) ||
        (magic[0] == 0xCA && magic[1] == 0xFE && magic[2] == 0xBA && magic[3] == 0xBE) ||
        (magic[0] == 0xBE && magic[1] == 0xBA && magic[2] == 0xFE && magic[3] == 0xCA)) {
        return Format::MachO;
    }
    return std::nullopt;
}

std::optional<std::uintptr_t> image_base_of(const LoadedImage& img, Format fmt) {
    if (fmt == Format::Pe32) {
        const std::optional<pe::Headers> h = read_pe_headers(img);
        if (!h) return std::nullopt;
        return static_cast<std::uintptr_t>(h->image_base);
    }
    const std::optional<elf::Headers> h = read_elf_headers(img);
    if (!h) return std::nullopt;
    std::uintptr_t lo = h->loads.front().vaddr;
    for (const elf::Segment& s : h->loads) {
        if (s.vaddr < lo) lo = s.vaddr;
    }
    return lo;
}

std::optional<std::vector<Section>> parse_image(const LoadedImage& img, Format fmt, ParseRoute* route) {
    std::vector<Section> out;

    if (fmt == Format::Pe32) {
        const std::optional<pe::Headers> h = read_pe_headers(img);
        if (!h) return std::nullopt;
        for (const pe::SectionHeader& s : h->sections) {
            Section sec;
            sec.name = s.name.empty() ? "<unnamed>" : s.name;
            // Against where the image actually is, not where it asked to be: a
            // relocated module makes ImageBase a wish rather than a fact.
            sec.va = img.base() + s.virtual_address;
            sec.size = s.virtual_size != 0 ? s.virtual_size : s.size_of_raw_data;
            sec.executable = (s.characteristics & (pe::kMemExecute | pe::kCntCode)) != 0;
            out.push_back(std::move(sec));
        }
        if (out.empty()) return std::nullopt;
        if (route != nullptr) *route = ParseRoute::PeSectionTable;
        return out;
    }

    const std::optional<elf::Headers> h = read_elf_headers(img);
    if (!h) return std::nullopt;
    if (read_elf_sections(img, *h, out)) {
        if (route != nullptr) *route = ParseRoute::ElfSectionHeaders;
        return out;
    }
    elf_sections_from_segments(*h, out);
    if (out.empty()) return std::nullopt;
    if (route != nullptr) *route = ParseRoute::ElfProgramHeaders;
    return out;
}

std::optional<std::vector<Section>> parse_mapped(std::uintptr_t image_base, Format fmt) {
    const LiveImage img(image_base);
    return parse_image(img, fmt, nullptr);
}

}  // namespace kp::image

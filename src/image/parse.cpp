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

    const std::uint64_t span64 =
        static_cast<std::uint64_t>(phoff) +
        static_cast<std::uint64_t>(phentsize) * static_cast<std::uint64_t>(phnum);
    if (span64 == 0 || span64 > kMaxTableBytes) return std::nullopt;
    const std::size_t span = static_cast<std::size_t>(span64);

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

// The mapped Mach-O: dyld maps the header and load commands as the first
// bytes of __TEXT, so both are readable at the image base. Only the 64-bit
// little-endian form is parsed here -- the only Mach-O this runtime is ever
// loaded into. `slide` is the distance between where the image asked to be
// (__TEXT's vmaddr) and where it is (the header address).
struct MachOLive {
    std::uint64_t text_vmaddr = 0;
    bool ok = false;
};

bool macho_sections(const LoadedImage& img, std::vector<Section>* out, MachOLive& live) {
    std::uint32_t hdr[8] = {};
    if (!img.read(img.base(), hdr, sizeof hdr)) return false;
    if (hdr[0] != 0xFEEDFACFu) return false;                 // MH_MAGIC_64
    const std::uint32_t ncmds = hdr[4], sizeofcmds = hdr[5];
    if (ncmds == 0 || ncmds > 4096 || sizeofcmds > 1u << 20) return false;
    std::vector<std::uint8_t> cmds;
    if (!img.read_vector(img.base() + 32, sizeofcmds, cmds)) return false;
    struct Seg { std::uint64_t vmaddr; std::string name; std::int32_t initprot; std::vector<Section> secs; };
    std::vector<Seg> segs;
    std::size_t off = 0;
    for (std::uint32_t i = 0; i < ncmds; ++i) {
        if (off + 8 > cmds.size()) return false;
        std::uint32_t cmd = 0, cmdsize = 0;
        std::memcpy(&cmd, cmds.data() + off, 4);
        std::memcpy(&cmdsize, cmds.data() + off + 4, 4);
        if (cmdsize < 8 || cmdsize > cmds.size() - off) return false;
        if (cmd == 0x19) {                                     // LC_SEGMENT_64
            if (cmdsize < 72) return false;
            const std::uint8_t* c = cmds.data() + off;
            Seg seg;
            seg.name.assign(reinterpret_cast<const char*>(c + 8), strnlen(reinterpret_cast<const char*>(c + 8), 16));
            std::memcpy(&seg.vmaddr, c + 24, 8);
            std::memcpy(&seg.initprot, c + 60, 4);
            std::uint32_t nsects = 0;
            std::memcpy(&nsects, c + 64, 4);
            if (72 + std::uint64_t(nsects) * 80 > cmdsize) return false;
            for (std::uint32_t k = 0; k < nsects; ++k) {
                const std::uint8_t* sp = c + 72 + 80 * k;
                Section sec;
                sec.name.assign(reinterpret_cast<const char*>(sp), strnlen(reinterpret_cast<const char*>(sp), 16));
                std::uint64_t addr = 0, size = 0;
                std::uint32_t flags = 0;
                std::memcpy(&addr, sp + 32, 8);
                std::memcpy(&size, sp + 40, 8);
                std::memcpy(&flags, sp + 64, 4);
                sec.va = static_cast<std::uintptr_t>(addr);   // unslid for now
                sec.size = static_cast<std::size_t>(size);
                // S_ATTR_PURE_INSTRUCTIONS | S_ATTR_SOME_INSTRUCTIONS, in an
                // executable segment. __stubs and __stub_helper count; they
                // are small, and code_section() prefers the largest.
                sec.executable = (flags & 0x80000400u) != 0 && (seg.initprot & 4) != 0;
                seg.secs.push_back(std::move(sec));
            }
            if (seg.name == "__TEXT") live.text_vmaddr = seg.vmaddr;
            segs.push_back(std::move(seg));
        }
        off += cmdsize;
    }
    if (live.text_vmaddr == 0) return false;
    live.ok = true;
    if (out == nullptr) return true;
    const std::uintptr_t slide = img.base() - static_cast<std::uintptr_t>(live.text_vmaddr);
    for (Seg& seg : segs) {
        for (Section& s : seg.secs) {
            s.va += slide;
            out->push_back(std::move(s));
        }
    }
    return !out->empty();
}

}  // namespace

const char* to_string(ParseRoute r) {
    switch (r) {
        case ParseRoute::PeSectionTable:    return "pe section table";
        case ParseRoute::ElfSectionHeaders: return "elf section headers";
        case ParseRoute::ElfProgramHeaders: return "elf program headers (names synthesised)";
        case ParseRoute::MachOLoadCommands: return "mach-o load commands";
    }
    return "unknown";
}

std::optional<Format> detect_format(const LoadedImage& img) {
    std::uint8_t magic[4] = {0};
    if (!img.read(img.base(), magic, sizeof magic)) return std::nullopt;
    if (magic[0] == 'M' && magic[1] == 'Z') return Format::Pe32;
    if (magic[0] == 0x7f && magic[1] == 'E' && magic[2] == 'L' && magic[3] == 'F') return Format::Elf32;
    // Mach-O thin LE (0xFEEDFACE / 0xFEEDFACF), or a fat container on disk
    // (0xCAFEBABE; never what dyld maps, but a file image may start with it).
    if ((magic[0] == 0xCE && magic[1] == 0xFA && magic[2] == 0xED && magic[3] == 0xFE) ||
        (magic[0] == 0xCF && magic[1] == 0xFA && magic[2] == 0xED && magic[3] == 0xFE) ||
        (magic[0] == 0xFE && magic[1] == 0xED && magic[2] == 0xFA && magic[3] == 0xCE) ||
        (magic[0] == 0xCA && magic[1] == 0xFE && magic[2] == 0xBA && magic[3] == 0xBE) ||
        (magic[0] == 0xBE && magic[1] == 0xBA && magic[2] == 0xFE && magic[3] == 0xCA)) {
        return Format::MachO;
    }
    return std::nullopt;
}

std::optional<std::uintptr_t> image_base_of(const LoadedImage& img, Format fmt) {
    if (fmt == Format::MachO) {
        MachOLive live;
        if (!macho_sections(img, nullptr, live)) return std::nullopt;
        return static_cast<std::uintptr_t>(live.text_vmaddr);
    }
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

    if (fmt == Format::MachO) {
        MachOLive live;
        if (!macho_sections(img, &out, live)) return std::nullopt;
        if (route != nullptr) *route = ParseRoute::MachOLoadCommands;
        return out;
    }

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

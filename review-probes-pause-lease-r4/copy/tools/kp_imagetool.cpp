// Exercises the image module against files, with no game running.
//
// The primary target cannot be launched on this machine -- SteamStub refuses
// without Steam, and the harness runs the deciphered copy instead. So the way to
// know classification, parsing and identification are right is to run them
// offline against the encrypted build, its deciphered twin, the GOG build they
// both reduce to, and the ELF target, and read the numbers.
//
//   kp_imagetool classify <file>        per-section entropy and verdict
//   kp_imagetool identify <file>        sha256, build alias, code digest
//   kp_imagetool sections <file>        parsed section map
//   kp_imagetool dump <file> <out>      write the mapped image back out
#include <cstdio>
#include <cinttypes>
#include <fstream>
#include <cstring>
#include <memory>
#include <string>
#include <vector>

#include "../src/image/internal.hpp"
#include "../src/image/loaded_image.hpp"
#include "../src/image/pe_elf.hpp"
#include "../src/image/macho.hpp"
#include "../src/image/sha256.hpp"

using namespace kp::image;

namespace {

constexpr std::size_t kChunk = 64 * 1024;

// Dispatch only by container magic here; all Mach-O decoding stays in macho.
bool macho_file(const std::string& path) {
    std::ifstream f(path, std::ios::binary);
    unsigned char b[4] = {};
    if (!f.read(reinterpret_cast<char*>(b), 4)) return false;
    const std::uint32_t magic = std::uint32_t(b[0]) | (std::uint32_t(b[1]) << 8) |
        (std::uint32_t(b[2]) << 16) | (std::uint32_t(b[3]) << 24);
    return magic == 0xfeedface || magic == 0xfeedfacf || magic == 0xcefaedfe ||
        magic == 0xcffaedfe || magic == 0xcafebabe || magic == 0xbebafeca ||
        magic == 0xcafebabf || magic == 0xbfbafeca;
}

int cmd_macho(const std::string& command, const std::string& path, bool mapped) {
    if (mapped || (command != "identify" && command != "sections")) {
        std::fprintf(stderr, "Mach-O supports only offline identify/sections; mapped, classify and dump are unsupported\n");
        return 2;
    }
    const auto bytes = read_file(path);
    macho::Headers h;
    std::string error;
    if (!macho::read_file(bytes.data(), bytes.size(), h, error)) {
        std::fprintf(stderr, "Mach-O: %s\n", error.c_str());
        return 2;
    }
    const auto hash = sha256_hex(bytes.data(), bytes.size());
    const auto* build = lookup_build(hash);
    const char* arch = h.cpu_type == 7 ? "x86" : h.cpu_type == 0x1000007 ? "x86_64" :
        h.cpu_type == 12 ? "arm" : h.cpu_type == 0x100000c ? "arm64" : "unknown";
    std::printf("%s\n  format      Mach-O%u little-endian\n", path.c_str(), h.bits);
    std::printf("  architecture %s cpu=0x%08x subtype=0x%08x container_bits=%u\n",
                arch, h.cpu_type, h.cpu_subtype, h.bits);
    std::printf("  sha256      %s\n  build       %s\n", hash.c_str(), build ? build->alias : "<unrecognised>");
    std::printf("  metadata-only; preferred unslid VAs; no runtime admission or ASLR mapping\n");
    if (command == "sections") {
        for (const auto& segment : h.segments) {
            std::printf("  segment %s va=0x%016" PRIx64 " size=0x%016" PRIx64
                        " file_offset=0x%016" PRIx64 " file_size=0x%016" PRIx64
                        " protection=0x%x max=0x%x\n", segment.name.c_str(), segment.address,
                        segment.size, segment.file_offset, segment.file_size,
                        segment.initial_protection, segment.max_protection);
            for (const auto& section : segment.sections) {
                std::printf("    section %s,%s va=0x%016" PRIx64 " size=0x%016" PRIx64
                            " file_offset=0x%08x file_size=0x%016" PRIx64 " %s\n",
                            section.segment_name.c_str(), section.name.c_str(), section.address,
                            section.size, section.file_offset, section.zero_fill ? std::uint64_t(0) : section.size,
                            section.zero_fill ? "zero-fill (no file bytes)" : "file-backed");
            }
        }
    }
    return 0; // Successful metadata inspection does not require a supported runtime build.
}


struct Opened {
    std::vector<std::uint8_t>    file;
    std::unique_ptr<BufferImage> img;
    Format                       format = Format::Pe32;
    ParseRoute                   route = ParseRoute::PeSectionTable;
    std::vector<Section>         sections;
};

// ELF section headers sit past the last PT_LOAD, so a loader-shaped image cannot
// see them and the section map degrades to segments. Offline we can do better:
// address the whole file linearly and get real names back. `mapped` forces the
// runtime view instead, which is how the degraded route gets exercised too.
bool open_image(const std::string& path, bool mapped, Opened& out) {
    out.file = read_file(path);
    if (out.file.empty()) {
        std::fprintf(stderr, "cannot read %s\n", path.c_str());
        return false;
    }

    if (elf::looks_like(out.file.data(), out.file.size())) {
        out.format = Format::Elf32;
        if (!mapped) out.img = make_linear_elf_image(out.file);
    } else if (pe::looks_like(out.file.data(), out.file.size())) {
        out.format = Format::Pe32;
    } else {
        std::fprintf(stderr, "%s is not a PE32 or ELF32 image\n", path.c_str());
        return false;
    }

    if (out.img == nullptr) out.img = map_file_image(out.file);
    if (out.img == nullptr) {
        std::fprintf(stderr, "%s did not lay out as an image\n", path.c_str());
        return false;
    }

    std::optional<std::vector<Section>> s = parse_image(*out.img, out.format, &out.route);
    if (!s) {
        std::fprintf(stderr, "%s: headers did not parse\n", path.c_str());
        return false;
    }
    out.sections = std::move(*s);
    return true;
}

const char* state_name(SectionState s) {
    switch (s) {
        case SectionState::Plaintext:  return "Plaintext";
        case SectionState::Ciphertext: return "Ciphertext";
        case SectionState::Deciphered: return "Deciphered";
    }
    return "?";
}

void chunk_entropy(const std::vector<std::uint8_t>& b, double& lo, double& hi, std::size_t& n) {
    lo = 0.0;
    hi = 0.0;
    n = 0;
    if (b.size() < kChunk) {
        lo = hi = shannon_entropy(b.data(), b.size());
        n = b.empty() ? 0 : 1;
        return;
    }
    for (std::size_t off = 0; off + kChunk <= b.size(); off += kChunk) {
        const double e = shannon_entropy(b.data() + off, kChunk);
        if (n == 0 || e < lo) lo = e;
        if (n == 0 || e > hi) hi = e;
        ++n;
    }
}

int cmd_classify(const std::string& path, bool mapped) {
    Opened o;
    if (!open_image(path, mapped, o)) return 2;

    std::printf("%s\n", path.c_str());
    std::printf("  format %s   base 0x%08lx   route %s\n\n",
                o.format == Format::Pe32 ? "PE32" : "ELF32",
                static_cast<unsigned long>(o.img->base()), to_string(o.route));
    std::printf("  %-18s %-10s %-10s %-6s %6s %6s  %-13s %s\n",
                "section", "va", "size", "bits", "prol", "int3", "chunks 64K", "verdict");
    std::printf("  %-18s %-10s %-10s %-6s %6s %6s  %-13s %s\n",
                "------------------", "----------", "----------", "------", "------", "------",
                "-------------", "-------");

    std::vector<std::uint8_t> body;
    for (const Section& s : o.sections) {
        if (!o.img->read_vector(s.va, s.size, body)) {
            std::printf("  %-18s 0x%08lx 0x%08lx  <unreadable through this image>\n",
                        s.name.c_str(), static_cast<unsigned long>(s.va),
                        static_cast<unsigned long>(s.size));
            continue;
        }
        const EntropyVerdict v = classify(body.data(), body.size());
        double lo = 0.0, hi = 0.0;
        std::size_t n = 0;
        chunk_entropy(body, lo, hi, n);

        char chunks[32];
        std::snprintf(chunks, sizeof chunks, "%2zux %.3f-%.3f", n, lo, hi);
        std::printf("  %-18s 0x%08lx 0x%08lx %6.4f %6zu %6zu  %-13s %s%s\n",
                    s.name.c_str(), static_cast<unsigned long>(s.va),
                    static_cast<unsigned long>(s.size), v.bits_per_byte,
                    v.prologue_count, v.int3_runs, chunks,
                    state_name(v.is_ciphertext ? SectionState::Ciphertext : SectionState::Plaintext),
                    s.executable ? "  (x)" : "");
    }
    return 0;
}

int cmd_sections(const std::string& path, bool mapped) {
    Opened o;
    if (!open_image(path, mapped, o)) return 2;

    const std::optional<std::uintptr_t> declared = image_base_of(*o.img, o.format);
    std::printf("%s\n", path.c_str());
    std::printf("  format %s   image base 0x%08lx   declared 0x%08lx   route %s\n\n",
                o.format == Format::Pe32 ? "PE32" : "ELF32",
                static_cast<unsigned long>(o.img->base()),
                static_cast<unsigned long>(declared ? *declared : 0), to_string(o.route));
    std::printf("  %-18s %-10s %-10s %-10s %s\n", "section", "va", "size", "end", "flags");
    for (const Section& s : o.sections) {
        std::printf("  %-18s 0x%08lx 0x%08lx 0x%08lx %s\n", s.name.c_str(),
                    static_cast<unsigned long>(s.va), static_cast<unsigned long>(s.size),
                    static_cast<unsigned long>(s.va + s.size), s.executable ? "x" : "-");
    }

    // The ELF runtime route is worth showing next to the offline one: it is what
    // a live process is limited to, and it is why the build table records a
    // digest per section name.
    if (o.format == Format::Elf32 && o.route == ParseRoute::ElfSectionHeaders) {
        std::unique_ptr<BufferImage> m = map_file_image(o.file);
        ParseRoute r = ParseRoute::ElfProgramHeaders;
        std::optional<std::vector<Section>> segs = m ? parse_image(*m, o.format, &r) : std::nullopt;
        if (segs) {
            std::printf("\n  runtime view (%s)\n", to_string(r));
            for (const Section& s : *segs) {
                std::printf("  %-18s 0x%08lx 0x%08lx 0x%08lx %s\n", s.name.c_str(),
                            static_cast<unsigned long>(s.va), static_cast<unsigned long>(s.size),
                            static_cast<unsigned long>(s.va + s.size), s.executable ? "x" : "-");
            }
        }
    }
    return 0;
}

int cmd_identify(const std::string& path, bool mapped) {
    const std::string sha = sha256_file(path);
    if (sha.empty()) {
        std::fprintf(stderr, "cannot read %s\n", path.c_str());
        return 2;
    }
    const BuildRecord* rec = lookup_build(sha);

    std::printf("%s\n", path.c_str());
    std::printf("  sha256      %s\n", sha.c_str());
    std::printf("  build       %s\n", rec != nullptr ? rec->alias : "<unrecognised>");
    if (rec == nullptr) {
        std::printf("  the runtime refuses to install against a build it cannot name\n");
        return 1;
    }
    std::printf("  format      %s\n", rec->format == Format::Pe32 ? "PE32" : "ELF32");
    std::printf("  image base  0x%08lx\n", static_cast<unsigned long>(rec->image_base));
    std::printf("  encrypted   %s\n", rec->encrypted ? "yes" : "no");
    if (rec->sentinel_va != 0) {
        std::printf("  sentinel    0x%08lx  %s\n", static_cast<unsigned long>(rec->sentinel_va),
                    rec->sentinel_bytes);
        std::printf("              %s\n", rec->sentinel_describes);
    }
    std::printf("  note        %s\n", rec->note);

    Opened o;
    if (!open_image(path, mapped, o)) return 2;

    // Read the sentinel first: whether the code is deciphered decides what a
    // digest mismatch means. On the shipped Steam file it means the file is
    // encrypted, which is the expected state, not a fault.
    bool deciphered = true;
    std::vector<std::uint8_t> at_sentinel;
    if (rec->sentinel_va != 0) {
        const std::vector<std::uint8_t> want = parse_hex(rec->sentinel_bytes);
        deciphered = o.img->read_vector(rec->sentinel_va, want.size(), at_sentinel) &&
                     std::memcmp(at_sentinel.data(), want.data(), want.size()) == 0;
    }

    std::vector<std::uint8_t> body;
    for (const Section& s : o.sections) {
        for (std::size_t i = 0; i < rec->text_count; ++i) {
            if (s.name != rec->texts[i].section) continue;
            if (!o.img->read_vector(s.va, s.size, body)) continue;
            const std::string got = sha256_hex(body.data(), body.size());
            const bool match = got == rec->texts[i].sha256;
            const char* verdict = match ? "MATCH"
                                        : (deciphered ? "MISMATCH -- refuse to install"
                                                      : "differs, as it must: still ciphertext");
            std::printf("\n  %s digest %s\n", s.name.c_str(), got.c_str());
            std::printf("  known good   %s  %s\n", rec->texts[i].sha256, verdict);
        }
    }

    if (rec->sentinel_va != 0) {
        std::printf("\n  sentinel at 0x%08lx reads ", static_cast<unsigned long>(rec->sentinel_va));
        for (std::uint8_t b : at_sentinel) std::printf("%02x ", b);
        std::printf("\n  %s\n", deciphered ? "matches: this image is deciphered"
                                           : "no match: the runtime would wait here, not patch");
    }
    return 0;
}

int cmd_dump(const std::string& path, const std::string& out, bool mapped) {
    Opened o;
    if (!open_image(path, mapped, o)) return 2;

    LoadResult r;
    r.format = o.format;
    r.image_base = o.img->base();
    r.sections = o.sections;

    std::string error;
    if (!dump_from(*o.img, r, out, error)) {
        std::fprintf(stderr, "dump failed: %s\n", error.c_str());
        return 2;
    }
    std::printf("wrote %s\n", out.c_str());
    return 0;
}

int usage() {
    std::fprintf(stderr,
                 "usage: kp_imagetool <command> <file> [--mapped]\n"
                 "  classify <file>      per-section entropy and ciphertext verdict\n"
                 "  identify <file>      sha256, build alias, code-section digest\n"
                 "  sections <file>      parsed section map\n"
                 "  dump <file> <out>    write the mapped image to <out>\n"
                 "\n"
                 "  --mapped             parse the loader-shaped image, as the runtime must\n"
                 "  Mach-O: offline identify/sections only; metadata success does not admit runtime use\n");
    return 2;
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 3) return usage();

    std::vector<std::string> args;
    bool mapped = false;
    for (int i = 1; i < argc; ++i) {
        if (std::strcmp(argv[i], "--mapped") == 0) {
            mapped = true;
        } else {
            args.emplace_back(argv[i]);
        }
    }
    if (args.size() < 2) return usage();

    const std::string& cmd = args[0];
    if ((cmd == "identify" || cmd == "sections" || cmd == "classify" || cmd == "dump") &&
        macho_file(args[1])) return cmd_macho(cmd, args[1], mapped);
    if (cmd == "classify") return cmd_classify(args[1], mapped);
    if (cmd == "identify") return cmd_identify(args[1], mapped);
    if (cmd == "sections") return cmd_sections(args[1], mapped);
    if (cmd == "dump") {
        if (args.size() < 3) return usage();
        return cmd_dump(args[1], args[2], mapped);
    }
    return usage();
}

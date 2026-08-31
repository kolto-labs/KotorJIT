// The load-time sequence, and the refusal that ends it when anything is off.
//
// Order note, against the plan's five steps: classification cannot come before
// parsing, because there are no sections to classify until the headers have been
// read. Headers are plaintext even in the packed Steam build -- SizeOfHeaders is
// 0x1000 and the section table sits inside it -- so parsing first costs nothing
// and reads nothing encrypted. The real order is: identify, parse, classify,
// await decipher, re-parse, verify.
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstring>

#include "internal.hpp"
#include "pe_elf.hpp"
#include "sha256.hpp"

#if defined(_WIN32)
#include <windows.h>
#else
#include <ctime>
#endif

namespace kp::image {
namespace {

// uint64_t on purpose: a crafted SectionAlignment/VirtualSize near UINT32_MAX
// wraps this in 32-bit arithmetic, which previously undersized dump_pe's
// output buffer while the section-body memcpy still used the real (unwrapped)
// size -- a heap buffer overflow. Callers truncate back to uint32_t only after
// dump_pe's own size cap has already rejected anything that wouldn't fit.
std::uint64_t align_up(std::uint64_t v, std::uint64_t a) {
    if (a == 0) return v;
    return (v + a - 1) / a * a;
}

std::string basename_of(const std::string& path) {
    const std::size_t cut = path.find_last_of("/\\");
    return cut == std::string::npos ? path : path.substr(cut + 1);
}

unsigned elapsed_ms(std::chrono::steady_clock::time_point start) {
    using namespace std::chrono;
    return static_cast<unsigned>(duration_cast<milliseconds>(steady_clock::now() - start).count());
}

// Where the module actually sits in this process. On Windows only the loader
// knows; on ELF the answer is in the file, because the target is EXEC rather
// than PIE and therefore is never relocated.
std::optional<std::uintptr_t> find_live_base(const std::string& module_path, Format fmt,
                                             const BuildRecord* record) {
#if defined(_WIN32)
    (void)fmt;
    (void)record;
    HMODULE h = GetModuleHandleA(module_path.c_str());
    if (h == nullptr) h = GetModuleHandleA(basename_of(module_path).c_str());
    if (h == nullptr) return std::nullopt;
    return reinterpret_cast<std::uintptr_t>(h);
#else
    (void)module_path;
    if (record != nullptr) return record->image_base;
    if (fmt != Format::Elf32) return std::nullopt;
    // Unrecognised ELF: the file's own lowest PT_LOAD is the load address for a
    // non-PIE image, which is the only ELF shape we target.
    const std::vector<std::uint8_t> file = read_file(module_path);
    if (file.empty()) return std::nullopt;
    elf::Headers h;
    if (!elf::read_headers(file.data(), file.size(), h)) return std::nullopt;
    std::uintptr_t lo = h.loads.front().vaddr;
    for (const elf::Segment& s : h.loads) {
        if (s.vaddr < lo) lo = s.vaddr;
    }
    return lo;
#endif
}

void classify_sections(const LoadedImage& img, std::vector<Section>& sections) {
    std::vector<std::uint8_t> buf;
    for (Section& s : sections) {
        if (s.size == 0 || !img.read_vector(s.va, s.size, buf)) {
            // Unreadable is not evidence of plaintext. Leaving the entropy at
            // zero and the state untouched keeps the section out of the "safe
            // to read" set without inventing a measurement.
            s.entropy = 0.0;
            continue;
        }
        const EntropyVerdict v = classify(buf.data(), buf.size());
        s.entropy = v.bits_per_byte;
        s.state = v.is_ciphertext ? SectionState::Ciphertext : SectionState::Plaintext;
    }
}

const Section* section_at(const std::vector<Section>& sections, std::uintptr_t va) {
    for (const Section& s : sections) {
        if (va >= s.va && va < s.va + s.size) return &s;
    }
    return nullptr;
}

// The section whose plaintext we verify. Prefer the one the sentinel lives in --
// that is the code the wrapper promised to decipher. Otherwise the largest
// executable section, which on every target here is the real code.
const Section* code_section(const std::vector<Section>& sections, const BuildRecord* record) {
    if (record != nullptr && record->sentinel_va != 0) {
        const Section* s = section_at(sections, record->sentinel_va);
        if (s != nullptr) return s;
    }
    const Section* best = nullptr;
    for (const Section& s : sections) {
        if (!s.executable) continue;
        if (best == nullptr || s.size > best->size) best = &s;
    }
    return best;
}

bool sentinel_matches(const LoadedImage& img, std::uintptr_t va, const std::vector<std::uint8_t>& want) {
    std::vector<std::uint8_t> got;
    if (!img.read_vector(va, want.size(), got)) return false;
    return std::memcmp(got.data(), want.data(), want.size()) == 0;
}

// Poll until the wrapper has written real code at the sentinel, then wait and
// look again: matching once only proves the bytes were right at that instant,
// and the stub may still be working through the section.
bool await_decipher(const LoadedImage& img, const Sentinel& sentinel, const WaitPolicy& policy,
                    unsigned& waited_ms) {
    const auto start = std::chrono::steady_clock::now();
    for (;;) {
        if (sentinel_matches(img, sentinel.va, sentinel.bytes)) {
            sleep_ms(policy.settle_ms);
            if (sentinel_matches(img, sentinel.va, sentinel.bytes)) {
                waited_ms = elapsed_ms(start);
                return true;
            }
        }
        if (elapsed_ms(start) >= policy.timeout_ms) {
            waited_ms = elapsed_ms(start);
            return false;
        }
        sleep_ms(policy.poll_interval_ms);
    }
}

const char* expected_text_sha(const BuildRecord* record, const std::string& section) {
    if (record == nullptr) return nullptr;
    for (std::size_t i = 0; i < record->text_count; ++i) {
        if (section == record->texts[i].section) return record->texts[i].sha256;
    }
    return nullptr;
}

bool write_all(const std::string& path, const std::vector<std::uint8_t>& bytes, std::string& error) {
    std::FILE* f = std::fopen(path.c_str(), "wb");
    if (f == nullptr) {
        error = "cannot open " + path + " for writing";
        return false;
    }
    const std::size_t n = std::fwrite(bytes.data(), 1, bytes.size(), f);
    const bool ok = n == bytes.size() && std::ferror(f) == 0;
    std::fclose(f);
    if (!ok) error = "short write to " + path;
    return ok;
}

bool dump_pe(const LoadedImage& img, const std::string& out_path, std::string& error) {
    const std::optional<pe::Headers> parsed = read_pe_headers(img);
    if (!parsed) {
        error = "PE headers did not parse from the image";
        return false;
    }
    const pe::Headers& h = *parsed;
    if (h.section_alignment == 0) {
        error = "PE SectionAlignment is zero";
        return false;
    }

    // Written with FileAlignment equal to SectionAlignment and every section's
    // raw offset equal to its RVA, so the file is the mapped image flattened. A
    // disassembler reads it directly. Imports are left as the loader resolved
    // them -- the IAT holds live pointers, not thunks -- which is correct for
    // analysis and would need rebuilding before the file could be run.
    std::uint64_t total = h.size_of_headers;
    for (const pe::SectionHeader& s : h.sections) {
        const std::uint32_t vsize = s.virtual_size != 0 ? s.virtual_size : s.size_of_raw_data;
        const std::uint64_t raw = align_up(vsize, h.section_alignment);
        total = std::max<std::uint64_t>(total, static_cast<std::uint64_t>(s.virtual_address) + raw);
    }
    // A legitimate KOTOR-era PE image is a few MB. Refuse anything absurd
    // rather than let a crafted header drive a multi-gigabyte allocation.
    constexpr std::uint64_t kMaxDumpSize = 256ull * 1024 * 1024;
    if (total > kMaxDumpSize) {
        error = "PE image would dump to an unreasonable size (" + std::to_string(total) + " bytes)";
        return false;
    }

    std::vector<std::uint8_t> file(static_cast<std::size_t>(total), 0);
    std::vector<std::uint8_t> headers;
    if (!img.read_vector(img.base(), h.size_of_headers, headers)) {
        error = "cannot read the PE header block from the image";
        return false;
    }
    std::memcpy(file.data(), headers.data(), std::min(headers.size(), file.size()));

    const std::size_t sec_table = h.pe_offset + 4 + 20 + h.optional_header_size;
    const std::size_t falign_off = h.pe_offset + 4 + 20 + 36;
    std::uint32_t falign = h.section_alignment;
    if (falign_off + 4 <= file.size()) {
        std::memcpy(file.data() + falign_off, &falign, 4);
    }

    std::vector<std::uint8_t> body;
    for (std::size_t i = 0; i < h.sections.size(); ++i) {
        const pe::SectionHeader& s = h.sections[i];
        const std::uint32_t vsize = s.virtual_size != 0 ? s.virtual_size : s.size_of_raw_data;
        const std::uint32_t raw = static_cast<std::uint32_t>(align_up(vsize, h.section_alignment));
        const std::size_t o = sec_table + 40u * i;
        if (o + 40 > file.size()) break;
        std::memcpy(file.data() + o + 16, &raw, 4);                    // SizeOfRawData
        std::memcpy(file.data() + o + 20, &s.virtual_address, 4);      // PointerToRawData

        if (vsize == 0) continue;
        if (!img.read_vector(img.base() + s.virtual_address, vsize, body)) continue;  // leave zero fill
        if (static_cast<std::uint64_t>(s.virtual_address) + body.size() > file.size()) continue;
        std::memcpy(file.data() + s.virtual_address, body.data(), body.size());
    }
    return write_all(out_path, file, error);
}

bool dump_elf(const LoadedImage& img, const std::string& out_path, std::string& error) {
    std::vector<std::uint8_t> ehdr;
    if (!img.read_vector(img.base(), 52, ehdr)) {
        error = "cannot read ELF header from the image";
        return false;
    }
    const std::uint32_t phoff = static_cast<std::uint32_t>(ehdr[28]) |
                                (static_cast<std::uint32_t>(ehdr[29]) << 8) |
                                (static_cast<std::uint32_t>(ehdr[30]) << 16) |
                                (static_cast<std::uint32_t>(ehdr[31]) << 24);
    const std::uint16_t phentsize = static_cast<std::uint16_t>(ehdr[42] | (ehdr[43] << 8));
    const std::uint16_t phnum     = static_cast<std::uint16_t>(ehdr[44] | (ehdr[45] << 8));

    std::vector<std::uint8_t> head;
    // phentsize/phnum promote to (signed) int and can overflow before the
    // size_t addition; cast phentsize first, matching parse.cpp's read_elf_headers.
    if (!img.read_vector(img.base(), static_cast<std::size_t>(phoff) +
                          static_cast<std::size_t>(phentsize) * phnum, head)) {
        error = "cannot read ELF program headers from the image";
        return false;
    }
    elf::Headers h;
    if (!elf::read_headers(head.data(), head.size(), h)) {
        error = "ELF program headers did not parse from the image";
        return false;
    }

    std::size_t total = head.size();
    for (const elf::Segment& s : h.loads) {
        total = std::max<std::size_t>(total, static_cast<std::size_t>(s.offset) + s.filesz);
    }

    std::vector<std::uint8_t> file(total, 0);
    std::memcpy(file.data(), head.data(), std::min(head.size(), file.size()));

    std::vector<std::uint8_t> body;
    for (const elf::Segment& s : h.loads) {
        if (s.filesz == 0) continue;
        if (!img.read_vector(s.vaddr, s.filesz, body)) continue;
        if (static_cast<std::size_t>(s.offset) + body.size() > file.size()) continue;
        std::memcpy(file.data() + s.offset, body.data(), body.size());
    }

    // After the segments, not before: the first PT_LOAD starts at file offset 0
    // and carries its own copy of the ELF header, so anything written earlier is
    // overwritten by it. Section headers are dropped because they were never
    // mapped -- keeping e_shoff would point readers at bytes we do not have.
    const std::uint32_t zero = 0;
    std::memcpy(file.data() + 32, &zero, 4);   // e_shoff
    std::memset(file.data() + 46, 0, 6);       // e_shentsize, e_shnum, e_shstrndx
    return write_all(out_path, file, error);
}

}  // namespace

void sleep_ms(unsigned ms) {
    if (ms == 0) return;
#if defined(_WIN32)
    Sleep(ms);
#else
    timespec ts;
    ts.tv_sec = ms / 1000;
    ts.tv_nsec = static_cast<long>(ms % 1000) * 1000000L;
    nanosleep(&ts, nullptr);
#endif
}

const char* to_string(LoadStatus s) {
    switch (s) {
        case LoadStatus::Ok:                return "ok";
        case LoadStatus::UnrecognisedBuild: return "unrecognised build";
        case LoadStatus::DecipherTimeout:   return "decipher timeout";
        case LoadStatus::PlaintextMismatch: return "plaintext mismatch";
        case LoadStatus::ParseFailed:       return "parse failed";
    }
    return "unknown";
}

LoadResult load(const std::string& module_path, const WaitPolicy& policy) {
    LoadResult r;
    r.identity.sha256 = sha256_file(module_path);

    const BuildRecord* record = lookup_build(r.identity.sha256);
    if (record != nullptr) {
        r.identity.recognised = true;
        r.identity.build_alias = record->alias;
        r.identity.expected_encrypted = record->encrypted;
        r.format = record->format;
    }

    // Format comes from the file only to decide how to read memory; every fact
    // that matters afterwards is taken from the image itself.
    const std::vector<std::uint8_t> head = read_file(module_path);
    if (head.empty()) {
        r.status = LoadStatus::ParseFailed;
        r.detail = "cannot read " + module_path;
        return r;
    }
    if (pe::looks_like(head.data(), head.size())) {
        r.format = Format::Pe32;
    } else if (elf::looks_like(head.data(), head.size())) {
        r.format = Format::Elf32;
    } else {
        r.status = LoadStatus::ParseFailed;
        r.detail = "not a PE32 or ELF32 image: " + module_path;
        return r;
    }

    const std::optional<std::uintptr_t> base = find_live_base(module_path, r.format, record);
    if (!base) {
        r.status = LoadStatus::ParseFailed;
        r.detail = "module is not loaded in this process: " + basename_of(module_path);
        return r;
    }
    r.image_base = *base;

    const LiveImage img(*base);
    const std::optional<Format> live_format = detect_format(img);
    if (!live_format || *live_format != r.format) {
        r.status = LoadStatus::ParseFailed;
        r.detail = "the mapped image does not match the file it came from";
        return r;
    }

    std::optional<std::vector<Section>> sections = parse_image(img, r.format);
    if (!sections) {
        r.status = LoadStatus::ParseFailed;
        r.detail = "headers unreadable in memory";
        return r;
    }
    r.sections = std::move(*sections);
    classify_sections(img, r.sections);

    if (record == nullptr) {
        r.status = LoadStatus::UnrecognisedBuild;
        r.detail = "sha256 " + r.identity.sha256 + " is not in the build table";
        return r;
    }

    // Keyed by address, not by index: the wrapper is free to rewrite the section
    // table it deciphers, and matching by position would silently mislabel a
    // section if it did.
    std::vector<std::uintptr_t> was_ciphertext;
    for (const Section& s : r.sections) {
        if (s.state == SectionState::Ciphertext) was_ciphertext.push_back(s.va);
    }

    const std::vector<std::uint8_t> want = parse_hex(record->sentinel_bytes);
    if (!want.empty()) {
        Sentinel sentinel;
        sentinel.va = record->sentinel_va;
        sentinel.bytes = want;
        sentinel.describes = record->sentinel_describes;

        if (!await_decipher(img, sentinel, policy, r.waited_ms)) {
            r.status = LoadStatus::DecipherTimeout;
            r.detail = "sentinel for " + sentinel.describes + " never appeared";
            return r;
        }

        // Re-parse rather than reuse: the wrapper may have rewritten the headers
        // along with the code, and the map we built before is the packed one.
        sections = parse_image(img, r.format);
        if (!sections) {
            r.status = LoadStatus::ParseFailed;
            r.detail = "headers unreadable after decipher";
            return r;
        }
        r.sections = std::move(*sections);
        classify_sections(img, r.sections);

        for (Section& s : r.sections) {
            if (s.state != SectionState::Plaintext) continue;
            if (std::find(was_ciphertext.begin(), was_ciphertext.end(), s.va) != was_ciphertext.end())
                s.state = SectionState::Deciphered;
        }
    }

    const Section* code = code_section(r.sections, record);
    if (code == nullptr) {
        r.status = LoadStatus::ParseFailed;
        r.detail = "no executable section in the mapped image";
        return r;
    }
    if (code->state == SectionState::Ciphertext) {
        r.status = LoadStatus::PlaintextMismatch;
        r.detail = code->name + " is still ciphertext after the sentinel matched";
        return r;
    }

    std::vector<std::uint8_t> body;
    if (!img.read_vector(code->va, code->size, body)) {
        r.status = LoadStatus::ParseFailed;
        r.detail = "cannot read " + code->name + " from memory";
        return r;
    }
    r.text_sha256 = sha256_hex(body.data(), body.size());

    const char* expected = expected_text_sha(record, code->name);
    if (expected == nullptr) {
        r.status = LoadStatus::PlaintextMismatch;
        r.detail = "no known-good digest for section " + code->name + " on build " + record->alias;
        return r;
    }
    if (r.text_sha256 != expected) {
        r.status = LoadStatus::PlaintextMismatch;
        r.detail = code->name + " hashed " + r.text_sha256 + ", expected " + expected;
        if (r.image_base != record->image_base) {
            // Relocation rewrites every absolute operand in the code, so the
            // digest cannot match and the mismatch is explained rather than
            // merely reported.
            r.detail += "; the image is at 0x" + std::to_string(r.image_base) +
                        " rather than its preferred base, so .text was rebased";
        }
        return r;
    }

    r.status = LoadStatus::Ok;
    return r;
}

bool dump_from(const LoadedImage& img, const LoadResult& result, const std::string& out_path,
               std::string& error) {
    error.clear();
    if (result.format == Format::Pe32) return dump_pe(img, out_path, error);
    return dump_elf(img, out_path, error);
}

bool dump(const LoadResult& result, const std::string& out_path, std::string& error) {
    if (result.image_base == 0) {
        error = "load result has no image base to dump from";
        return false;
    }
    const LiveImage img(result.image_base);
    return dump_from(img, result, out_path, error);
}

}  // namespace kp::image

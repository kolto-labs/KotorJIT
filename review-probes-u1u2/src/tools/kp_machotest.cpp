#include "image/macho.hpp"
#include "image/sha256.hpp"
// Unity build of the hash: CMakeLists.txt registers this test with macho.cpp
// only, and that file has other writers right now. When it is free, add
// src/image/sha256.cpp to kp_machotest's sources and delete this include.
#include "image/sha256.cpp"
#include <cstdio>
#include <fstream>
#include <iterator>
#include <vector>
#include <cstdlib>
using namespace kp::image::macho;
using Bytes = std::vector<std::uint8_t>;
void put(Bytes& b, std::size_t at, std::uint64_t v, unsigned width = 4) {
    for (unsigned i = 0; i < width; ++i) b.at(at + i) = (v >> (i * 8)) & 255;
}
Bytes fixture(bool wide) {
    Bytes b(512);
    put(b, 0, wide ? 0xfeedfacf : 0xfeedface); put(b, 4, wide ? 0x1000007 : 7);
    put(b, 12, 2); put(b, 16, 1);
    const auto h = wide ? 32u : 28u, fixed = wide ? 72u : 56u;
    put(b, 20, fixed + (wide ? 80 : 68)); put(b, h, wide ? 0x19 : 1);
    put(b, h + 4, fixed + (wide ? 80 : 68)); b[h + 8] = 'T';
    const auto width = wide ? 8 : 4;
    put(b, h + 24, wide ? 0x100001000ull : 0x1000, width);
    put(b, h + 24 + width, 512, width);
    put(b, h + 24 + width * 3, 512, width);
    put(b, h + (wide ? 56 : 40), 7); put(b, h + (wide ? 60 : 44), 5);
    put(b, h + (wide ? 64 : 48), 1);
    const auto s = h + fixed; b[s] = 't'; b[s + 16] = 'T';
    put(b, s + 32, wide ? 0x100001100ull : 0x1100, width);
    put(b, s + 32 + width, 16, width); put(b, s + 32 + width * 2, 256);
    return b;
}
// ---- M0: fat containers, slice selection, identity. All bytes synthetic. ----
void put_be(Bytes& b, std::size_t at, std::uint64_t v, unsigned width = 4) {
    for (unsigned i = 0; i < width; ++i) b.at(at + i) = (v >> ((width - 1 - i) * 8)) & 255;
}
// A thin fixture with one LC_UUID appended after its segment command.
Bytes with_uuid(bool wide, std::uint8_t tag) {
    auto b = fixture(wide);
    const auto h = wide ? 32u : 28u, seg = wide ? 152u : 124u;
    put(b, 8, 3);  // CPU_SUBTYPE_*_ALL, as a real slice header carries
    put(b, 16, 2); put(b, 20, seg + 24);
    put(b, h + seg, 0x1b); put(b, h + seg + 4, 24);
    for (unsigned i = 0; i < 16; ++i) b[h + seg + 8 + i] = std::uint8_t(tag + i);
    return b;
}
struct Arch { std::uint32_t cpu, sub; std::uint64_t offset, size; std::uint32_t align; Bytes body; };
Bytes fat(bool wide, const std::vector<Arch>& archs, std::size_t total) {
    Bytes b(total);
    put_be(b, 0, wide ? 0xcafebabf : 0xcafebabe); put_be(b, 4, archs.size());
    std::size_t at = 8;
    for (const auto& a : archs) {
        put_be(b, at, a.cpu); put_be(b, at + 4, a.sub);
        if (wide) { put_be(b, at + 8, a.offset, 8); put_be(b, at + 16, a.size, 8); put_be(b, at + 24, a.align); at += 32; }
        else { put_be(b, at + 8, a.offset); put_be(b, at + 12, a.size); put_be(b, at + 16, a.align); at += 20; }
        for (std::size_t i = 0; i < a.body.size() && a.offset + i < total; ++i) b[a.offset + i] = a.body[i];
    }
    return b;
}
constexpr std::uint32_t kI386 = 7, kX64 = 0x01000007, kArm64 = 0x0100000c, kAll = 3;
std::vector<Arch> two_arch() {
    return {{kI386, kAll, 4096, 512, 12, with_uuid(false, 0x10)},
            {kX64, 0x80000003u, 8192, 512, 12, with_uuid(true, 0x40)}};
}
std::string hex_of(const Bytes& b, std::size_t off, std::size_t n) {
    return kp::image::sha256_hex(b.data() + off, n);
}
int main(int argc, char** argv) {
    Headers h; std::string error; unsigned checks = 0;
    auto check = [&](bool ok, const char* what) {
        ++checks; if (!ok) { std::fprintf(stderr, "FAIL %s: %s\n", what, error.c_str()); std::exit(1); }
    };
    for (bool wide : {false, true}) {
        auto good = fixture(wide);
        check(read_file(good.data(), good.size(), h, error), "valid thin image");
        check(h.bits == (wide ? 64u : 32u) && h.segments.size() == 1 &&
              h.segments[0].sections[0].file_offset == 256 &&
              h.segments[0].address == (wide ? 0x100001000ull : 0x1000), "metadata preserves width");
        for (std::size_t n = 0; n < good.size(); ++n)
            check(!read_file(good.data(), n, h, error), "every truncation refuses");
        const auto head = wide ? 32u : 28u, fixed = wide ? 72u : 56u;
        const auto sec = head + fixed, off = sec + (wide ? 48 : 40);
        auto bad = [&](std::size_t at, std::uint64_t value, unsigned width = 4) {
            auto b = good; put(b, at, value, width);
            check(!read_file(b.data(), b.size(), h, error), "malformed image refuses");
            check(h.bits == (wide ? 64u : 32u), "failure preserves output");
        };
        bad(20, 0xffffffff); bad(16, 0xffffffff); bad(head + 4, 0); bad(head + 4, 9);
        bad(head, wide ? 1 : 0x19); bad(4, wide ? 7 : 0x1000007);
        bad(head + (wide ? 64 : 48), 0xffffffff);
        bad(head + 24, wide ? ~0ull : 0xfffffff0, wide ? 8 : 4);
        bad(head + (wide ? 40 : 32), ~0ull, wide ? 8 : 4);
        bad(sec + 32, 0, wide ? 8 : 4); bad(off, 500); bad(off + 4, 64);
        auto reloc = good; put(reloc, off + 8, 511); put(reloc, off + 12, 1);
        check(!read_file(reloc.data(), reloc.size(), h, error), "relocation extent refuses");
        auto outside = good; put(outside, head + (wide ? 48 : 36), 128, wide ? 8 : 4);
        check(!read_file(outside.data(), outside.size(), h, error), "file-valid section outside segment refuses");
        auto virtual_outside = good; put(virtual_outside, sec + (wide ? 40 : 36), 300, wide ? 8 : 4);
        check(!read_file(virtual_outside.data(), virtual_outside.size(), h, error), "section crosses VM segment end");
        auto count = good; put(count, 16, 0);
        check(!read_file(count.data(), count.size(), h, error), "unconsumed command region refuses");
        auto unknown = good; put(unknown, head, 0x12345678);
        check(read_file(unknown.data(), unknown.size(), h, error) && h.segments.empty(),
              "unknown bounded command skipped without loader admission");
        auto zero = good; put(zero, off, 0); put(zero, off + 16, 1);
        check(read_file(zero.data(), zero.size(), h, error) && h.segments[0].sections[0].zero_fill,
              "zero-fill section needs no file bytes");
    }
    check(!read_file(nullptr, 512, h, error), "null refuses");
    for (auto magic : {0xcafebabeu, 0xbebafecau, 0xcafebabfu, 0xbfbafecau, 0xcefaedfeu, 0xcffaedfeu}) {
        auto b = fixture(false); put(b, 0, magic);
        check(!read_file(b.data(), b.size(), h, error), "unsupported encoding refuses");
    }

    // ---- M0 ----
    {
        // LC_UUID is optional; a present one is parsed; malformed/duplicate refuse.
        for (bool wide : {false, true}) {
            auto u = with_uuid(wide, 0x20);
            check(read_file(u.data(), u.size(), h, error) && h.has_uuid && h.uuid[0] == 0x20 && h.uuid[15] == 0x2f,
                  "LC_UUID parsed");
            auto g = fixture(wide);
            check(read_file(g.data(), g.size(), h, error) && !h.has_uuid, "thin image without LC_UUID still parses");
            const auto hd = wide ? 32u : 28u, seg = wide ? 152u : 124u;
            auto odd = u; put(odd, hd + seg + 4, 16); put(odd, 20, seg + 16);
            check(!read_file(odd.data(), odd.size(), h, error), "short LC_UUID refuses");
            auto dup = u; put(dup, 16, 3); put(dup, 20, seg + 48);
            put(dup, hd + seg + 24, 0x1b); put(dup, hd + seg + 28, 24);
            check(!read_file(dup.data(), dup.size(), h, error), "duplicate LC_UUID refuses");
        }
        for (bool wide64 : {false, true}) {
            auto c = fat(wide64, two_arch(), 8192 + 512);
            Slice s; Identity id;
            check(select_slice(c.data(), c.size(), kI386, kAll, s, error) && s.fat && s.fat64 == wide64 &&
                  s.offset == 4096 && s.size == 512 && s.cpu_type == kI386 && s.align == 12,
                  wide64 ? "fat64 selects i386 slice" : "fat selects i386 slice");
            check(select_slice(c.data(), c.size(), kX64, kAll, s, error) && s.offset == 8192 && s.size == 512 &&
                  s.cpu_subtype == 0x80000003u, wide64 ? "fat64 selects x86_64 slice (cap bits ignored)"
                                                        : "fat selects x86_64 slice (cap bits ignored)");
            check(identify(c.data(), c.size(), kX64, kAll, id, error) &&
                  id.container_sha256 == hex_of(c, 0, c.size()) && id.slice_sha256 == hex_of(c, 8192, 512) &&
                  id.container_sha256 != id.slice_sha256 && id.uuid[0] == 0x40 && id.headers.bits == 64 &&
                  id.slice.offset == 8192, "identity keeps container sha, slice sha and LC_UUID (x86_64)");
            check(identify(c.data(), c.size(), kI386, kAll, id, error) &&
                  id.slice_sha256 == hex_of(c, 4096, 512) && id.uuid[0] == 0x10 && id.headers.bits == 32,
                  "identity keeps container sha, slice sha and LC_UUID (i386)");
            // Refusals. Each keeps the previous output untouched.
            auto refuse = [&](const Bytes& b, std::uint32_t cpu, const char* why, const char* what) {
                Slice keep; keep.offset = 0x5a5a;
                check(!select_slice(b.data(), b.size(), cpu, kAll, keep, error) && keep.offset == 0x5a5a &&
                      error.find(why) != std::string::npos, what);
                Identity idk; idk.container_sha256 = "keep";
                check(!identify(b.data(), b.size(), cpu, kAll, idk, error) && idk.container_sha256 == "keep", what);
            };
            refuse(c, kArm64, "missing architecture", "missing arch refuses");
            refuse(c, kI386 | 0x02000000u, "missing architecture", "wrong ABI bits refuse");
            for (std::size_t n = 0; n < c.size(); ++n) {
                Slice keep;
                check(!select_slice(c.data(), n, kX64, kAll, keep, error), "every fat truncation refuses (x86_64)");
                if (n < 4096 + 512) check(!select_slice(c.data(), n, kI386, kAll, keep, error), "every fat truncation refuses (i386)");
            }
            auto a = two_arch(); a[1].offset = 4096 + 256; a[1].align = 8;
            refuse(fat(wide64, a, 8192 + 512), kX64, "overlap", "overlapping slices refuse");
            a = two_arch(); a[1].offset = 4096; a[1].size = 512;
            refuse(fat(wide64, a, 8192 + 512), kI386, "overlap", "identical-extent slices refuse");
            a = two_arch(); a[0].offset = 0; a[0].align = 0; a[0].body.clear();
            refuse(fat(wide64, a, 8192 + 512), kX64, "overlap", "slice over the fat header refuses");
            a = two_arch(); a[0].offset = 4100;
            refuse(fat(wide64, a, 8192 + 512), kI386, "alignment", "misaligned slice offset refuses");
            a = two_arch(); a[0].align = 16;
            refuse(fat(wide64, a, 8192 + 512), kI386, "alignment", "implausible alignment refuses");
            a = two_arch(); a[1].cpu = kI386; a[1].sub = kAll; a[1].body = with_uuid(false, 0x50);
            refuse(fat(wide64, a, 8192 + 512), kI386, "duplicate architecture", "duplicate architecture refuses");
            a = two_arch(); a[1].size = 0;
            refuse(fat(wide64, a, 8192 + 512), kX64, "empty slice", "empty slice refuses");
            a = two_arch(); a[1].size = 1024;
            refuse(fat(wide64, a, 8192 + 512), kX64, "outside container", "slice past end of file refuses");
            if (wide64) {
                a = two_arch(); a[1].offset = 0x100002000ull;
                refuse(fat(true, a, 8192 + 512), kX64, "outside container", "fat64 offset beyond 4GiB refuses");
                a = two_arch(); a[1].offset = ~0ull - 4095; a[1].size = 8192;
                refuse(fat(true, a, 8192 + 512), kX64, "outside container", "fat64 offset+size overflow refuses");
            }
            a = two_arch(); a[1].body = c;  // nested fat container as the x86_64 slice
            a[1].size = 512;
            refuse(fat(wide64, a, 8192 + 512), kX64, "nested fat", "nested fat slice refuses");
            a = two_arch(); a[1].body = Bytes(512, 0x90);
            refuse(fat(wide64, a, 8192 + 512), kX64, "not a Mach-O", "garbage slice refuses");
            a = two_arch(); a[1].body = with_uuid(false, 0x40);
            refuse(fat(wide64, a, 8192 + 512), kX64, "disagrees", "slice header CPU disagreeing with entry refuses");
            a = two_arch(); a[1].body = fixture(true); put(a[1].body, 8, 3);
            check(select_slice(fat(wide64, a, 8192 + 512).data(), 8192 + 512, kX64, kAll, s, error),
                  "slice without LC_UUID is still selectable");
            auto nouuid = fat(wide64, a, 8192 + 512);
            Identity idk;
            check(!identify(nouuid.data(), nouuid.size(), kX64, kAll, idk, error), "identity refuses slice without LC_UUID");
            auto zero = c; put_be(zero, 4, 0);
            refuse(zero, kX64, "arch count", "zero arch count refuses");
            auto java = c; put_be(java, 4, 52);
            refuse(java, kX64, "arch count", "implausible arch count (Java class) refuses");
        }
        auto le = fat(false, two_arch(), 8192 + 512); put(le, 0, 0xcafebabe);  // bytes be ba fe ca
        { Slice keep; check(!select_slice(le.data(), le.size(), kX64, kAll, keep, error), "little-endian fat magic refuses"); }
        { Slice keep; check(!select_slice(nullptr, 64, kX64, kAll, keep, error), "null container refuses"); }
        auto thin = with_uuid(true, 0x70); Slice s; Identity id;
        check(select_slice(thin.data(), thin.size(), kX64, kAll, s, error) && !s.fat && s.offset == 0 &&
              s.size == thin.size(), "thin image is its own slice");
        check(identify(thin.data(), thin.size(), kX64, kAll, id, error) && id.container_sha256 == id.slice_sha256 &&
              id.uuid[0] == 0x70, "thin identity: container and slice hash agree");
        { Slice keep; check(!select_slice(thin.data(), thin.size(), kI386, kAll, keep, error), "thin image of another CPU refuses"); }
    }
    for (int i = 1; i < argc; ++i) {
        std::ifstream in(argv[i], std::ios::binary);
        check(bool(in), "open real image");
        Bytes b((std::istreambuf_iterator<char>(in)), {});
        const bool is_fat = b.size() >= 4 && b[0] == 0xca && b[1] == 0xfe && b[2] == 0xba && (b[3] & 0xfe) == 0xbe;
        if (!is_fat) {
            check(read_file(b.data(), b.size(), h, error), "real image parses");
            std::printf("%s: bits=%u cpu=0x%x segments=%zu uuid=%s\n", argv[i], h.bits, h.cpu_type,
                        h.segments.size(), h.has_uuid ? "present" : "absent");
        }
        // Hashes, offsets and UUID presence only: never the image bytes or the UUID value.
        bool any = false;
        for (auto cpu : {kI386, kX64}) for (auto sub : {kAll, 8u}) {
            Identity id;
            if (!identify(b.data(), b.size(), cpu, sub, id, error)) continue;
            any = true;
            std::printf("%s: %s cpu=0x%x sub=0x%x offset=%llu size=%llu container_sha256=%s slice_sha256=%s uuid=present\n",
                        argv[i], id.slice.fat ? (id.slice.fat64 ? "fat64" : "fat") : "thin", cpu, id.slice.cpu_subtype,
                        (unsigned long long)id.slice.offset, (unsigned long long)id.slice.size,
                        id.container_sha256.c_str(), id.slice_sha256.c_str());
            break;
        }
        check(any, "real image yields at least one identity");
    }
    std::printf("PASS %u checks\n", checks);
}

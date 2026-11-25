// kp_manifesttest -- hookmanifest/v1 masked-pattern resolution, no game.
//
//   kp_manifesttest selftest
//   kp_manifesttest image <swkotor.exe> <hookmanifest.json> [--overlay <addresses.json>]
//                         [--dump <out.tsv>]
//
// `selftest` builds synthetic code regions and checks the refusal rules: a
// masked pattern binds on exactly one hit, refuses on zero or two, never
// reads entry_va, and an overlay cannot reintroduce an address.
//
// `image` maps the executable sections of a real PE file into this process at
// a base that is NOT its image_base, binds them as the scan regions, loads the
// manifest and resolves every site by pattern. --dump writes one row per site
// (name, status, image VA) for an external comparison against the manifest's
// entry_va, which the loader itself never sees.

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include <string>
#include <vector>

#include "api/memory.hpp"
#include "hooks/registry.hpp"

using namespace kp::hooks;
namespace mem = kp::api::memory;

namespace {

int g_failures = 0;

void check(bool ok, const char* what) {
    std::printf("  [%s] %s\n", ok ? "PASS" : "FAIL", what);
    if (!ok) ++g_failures;
}

std::string manifest_doc(const std::string& functions, const char* slug = "synthetic") {
    return std::string(R"({"format":"agentdecompile.hookmanifest/v1",)") +
           R"("program":{"slug":")" + slug + R"(","game":"K1","platform":"win","arch":"x86",)" +
           R"("image_base":4194304,"sha256":"00"},"functions":[)" + functions + "]}";
}

std::string fn(const char* id, const char* entry_va, const char* primary_json,
               const char* expected, int unmasked, const char* extra = "") {
    return std::string(R"({"id":")") + id + R"(","cls":"","method":")" + id +
           R"(","entry_va":")" + entry_va + R"(","locate":{"primary":)" + primary_json +
           R"(,"expected_bytes":")" + expected + R"(","expected_bytes_unmasked_count":)" +
           std::to_string(unmasked) + R"(},"hook":{"safe":"static_ok"},"callable":{"safe":false},)" +
           R"("confidence":{"overall":0.9})" + extra + "}";
}

void selftest() {
    std::printf("\n== masked pattern resolution ==\n");

    // A 4 KiB code region at a heap address. Two copies of the same prologue
    // whose masked rel32 differs; one unique masked prologue; one masked
    // prologue whose concrete bytes appear twice.
    std::vector<std::uint8_t> hay(4096, 0xCC);
    const std::uint8_t uniq[]  = {0x6A, 0xFF, 0x68, 0x11, 0x22, 0x33, 0x44, 0x64, 0xA1, 0x00, 0x00, 0x00, 0x00, 0x50};
    const std::uint8_t twin1[] = {0x55, 0x8B, 0xEC, 0xE8, 0x01, 0x00, 0x00, 0x00, 0x5D, 0xC3};
    const std::uint8_t twin2[] = {0x55, 0x8B, 0xEC, 0xE8, 0x99, 0x88, 0x00, 0x00, 0x5D, 0xC3};
    const std::uint8_t exact[] = {0x8B, 0x09, 0xE9, 0xB9, 0x14, 0x00, 0x00, 0x90, 0x90, 0x90};
    std::memcpy(hay.data() + 0x100, uniq, sizeof uniq);
    std::memcpy(hay.data() + 0x200, twin1, sizeof twin1);
    std::memcpy(hay.data() + 0x300, twin2, sizeof twin2);
    std::memcpy(hay.data() + 0x400, exact, sizeof exact);
    const std::uintptr_t live = reinterpret_cast<std::uintptr_t>(hay.data());
    mem::bind_scan_regions(live, {{live, hay.size(), "synthetic"}});

    const std::string funcs =
        // Masked SEH push binds uniquely; its entry_va is a lie on purpose.
        fn("Uniq", "0x00DEAD00",
           R"({"pattern":"6a ff 68 ?? ?? ?? ?? 64 a1 00 00 00 00 50","mask":"ffffff00000000ffffffffffffff","anchor":"entry","offset":0,"len":14})",
           "6aff6811223344", 1) + "," +
        // Masked rel32 makes twin1 and twin2 identical: ambiguous, refused.
        fn("Twin", "0x00401200",
           R"({"pattern":"55 8b ec e8 ?? ?? ?? ?? 5d c3","mask":"ffffffff00000000ffff","anchor":"entry","offset":0,"len":10})",
           "558bece8010000005dc3", 1) + "," +
        // Pattern absent from the region: missing, refused.
        fn("Gone", "0x00401300",
           R"({"pattern":"53 55 56 57 8b 7c 24 14 ?? ??","mask":"ffffffffffffffff0000","anchor":"entry","offset":0,"len":10})",
           "", 0) + "," +
        // No primary, but the generator proved the exact bytes unique.
        fn("Exact", "0x00401400", "null", "8b09e9b9140000909090", 1) + "," +
        // No primary and exact bytes not unique: no locator, refused.
        fn("NoLoc", "0x00401500", "null", "cccccccccccccccc", 2) + "," +
        // A malformed primary (first byte wild) must not bind.
        fn("BadPat", "0x00401100",
           R"({"pattern":"?? ff 68 11 22 33 44","mask":"00ffffffffffff","anchor":"entry","offset":0,"len":7})",
           "", 0) + "," +
        // Under half the bytes concrete: invalid per SPEC 3.3.
        fn("Sparse", "0x00401100",
           R"({"pattern":"6a ?? ?? ?? ?? ff","mask":"ff00000000ff","anchor":"entry","offset":0,"len":6})",
           "", 0) + "," +
        // Overloads share an id; the second gets an ordinal suffix.
        fn("Uniq", "0x00401400", "null", "8b09e9b914000090909090", 1, R"(,"kp_site_aliases":[])");

    AddressTable t;
    std::string error;
    check(AddressTable::parse_manifest(manifest_doc(funcs), "synthetic", t, error), "parse manifest");
    if (!error.empty()) std::printf("    error: %s\n", error.c_str());
    check(t.scan_only(), "manifest table is scan-only");
    for (const Site& s : t.sites()) {
        if (s.kind != SiteKind::Field && s.addr != 0) {
            check(false, "no site carries an address before the scan");
            break;
        }
    }
    check(t.find("Uniq#2") != nullptr, "duplicate id gets an ordinal suffix");

    // The region lives at a heap address, not image_base: a hit at hay+off
    // must come back as image VA image_base+off (delta applied exactly once).
    t.resolve_from_signatures(live);
    auto at = [&](const char* name) { return t.find(name); };

    const Site* u = at("Uniq");
    check(u && u->resolved && u->bound_from_pattern && u->addr == t.image_base() + 0x100,
          "masked pattern binds the single hit (entry_va ignored)");
    check(u && u->addr != 0x00DEAD00, "a bogus entry_va is never used");
    const Site* tw = at("Twin");
    check(tw && !tw->resolved && tw->addr == 0 && tw->locate_error == "ambiguous",
          "two masked hits refuse as ambiguous");
    const Site* g = at("Gone");
    check(g && !g->resolved && g->addr == 0 && g->locate_error == "missing",
          "zero hits refuse as missing");
    const Site* e = at("Exact");
    check(e && e->resolved && e->addr == t.image_base() + 0x400,
          "unique exact expected_bytes bind when there is no primary");
    const Site* n = at("NoLoc");
    check(n && !n->resolved && n->locate_error == "no_locator", "no locator refuses");
    const Site* b = at("BadPat");
    check(b && !b->resolved && b->locate_error == "no_locator", "first-byte wildcard pattern is rejected");
    const Site* sp = at("Sparse");
    check(sp && !sp->resolved && sp->locate_error == "no_locator", "under-50%-concrete pattern is rejected");

    // Overlay: may mark required / detour and supply bytes, never an address.
    const char* overlay = R"({"build":"synthetic","sites":{
        "Twin":  {"kind":"detour","required":true,"addr":4198912,"expected_bytes":"558bece8010000005dc3"},
        "Uniq":  {"kind":"detour","required":true,"addr":4194560},
        "Extra": {"kind":"call","required":false,"addr":4195328,"expected_bytes":"8b09e9b9140000909090"},
        "Blind": {"kind":"call","required":false,"addr":4195584}
    }})";
    AddressTable ov;
    check(AddressTable::parse(overlay, ov, error), "parse overlay");
    AddressTable merged;
    check(AddressTable::parse_manifest(manifest_doc(funcs), "synthetic", merged, error), "re-parse manifest");
    merged.merge_overlay(ov);
    const Site* mt = merged.find("Twin");
    check(mt && mt->addr == 0 && !mt->resolved, "overlay addr is not adopted by a scan-only table");
    const Site* mb = merged.find("Blind");
    check(mb && mb->addr == 0 && !mb->resolved, "overlay-only site without bytes stays unbound");
    merged.resolve_from_signatures(live);
    mt = merged.find("Twin");
    check(mt && !mt->resolved && mt->required, "required ambiguous site stays refused after overlay");
    const Site* mx = merged.find("Extra");
    check(mx && mx->resolved && mx->addr == merged.image_base() + 0x400,
          "overlay-only site binds through its exact bytes, not its addr");
    const std::vector<std::string> missing = merged.unresolved_required();
    check(missing.size() == 1 && missing[0] == "Twin", "unresolved_required names exactly the refused site");

    HookSet set;
    set.add(HookRequest{"Twin", reinterpret_cast<void*>(&selftest), {}});
    std::string err;
    check(!set.install(merged, live, err) && err.find("Twin") != std::string::npos,
          "install refuses with nothing patched");

    // Wrong build slug and wrong format refuse at parse time.
    AddressTable bad;
    check(!AddressTable::parse_manifest(manifest_doc(funcs, "k1_gog_103"), "k1_steam_103", bad, error),
          "manifest for another build refuses");
    check(!AddressTable::parse_manifest(R"({"format":"agentdecompile.hookpack/v1","program":{},"functions":[]})",
                                        "", bad, error),
          "non-manifest format refuses");

    // A refused-prologue site cannot be promoted to detour by the overlay.
    const std::string refused = std::string(R"({"id":"R","cls":"","method":"R","locate":{"primary":null,)") +
        R"("expected_bytes":"8b09e9b9140000909090","expected_bytes_unmasked_count":1},)" +
        R"("hook":{"safe":"refuse"},"callable":{"safe":false},"confidence":{"overall":0.5}})";
    AddressTable r;
    check(AddressTable::parse_manifest(manifest_doc(refused), "", r, error), "parse refused-hook site");
    AddressTable rov;
    AddressTable::parse(R"({"sites":{"R":{"kind":"detour"}}})", rov, error);
    r.merge_overlay(rov);
    check(r.find("R") && r.find("R")->kind == SiteKind::Reference, "overlay cannot detour a refused prologue");
}

// ---------------------------------------------------------------------------
// Real image
// ---------------------------------------------------------------------------

bool read_file(const char* path, std::vector<std::uint8_t>& out) {
    std::FILE* f = std::fopen(path, "rb");
    if (!f) return false;
    std::fseek(f, 0, SEEK_END);
    const long n = std::ftell(f);
    std::fseek(f, 0, SEEK_SET);
    out.resize(n > 0 ? std::size_t(n) : 0);
    const bool ok = n > 0 && std::fread(out.data(), 1, out.size(), f) == out.size();
    std::fclose(f);
    return ok;
}

template <class T> T rd(const std::vector<std::uint8_t>& b, std::size_t off) {
    T v{};
    std::memcpy(&v, b.data() + off, sizeof v);
    return v;
}

int cmd_image(const char* exe, const char* manifest, const char* overlay, const char* dump) {
    std::vector<std::uint8_t> file;
    if (!read_file(exe, file) || file.size() < 0x400 || file[0] != 'M' || file[1] != 'Z') {
        std::fprintf(stderr, "cannot read PE %s\n", exe);
        return 2;
    }
    const std::uint32_t pe = rd<std::uint32_t>(file, 0x3C);
    const std::uint16_t nsec = rd<std::uint16_t>(file, pe + 6);
    const std::uint16_t opt = rd<std::uint16_t>(file, pe + 20);
    const std::uint32_t image_base = rd<std::uint32_t>(file, pe + 24 + 28);
    const std::uint32_t image_size = rd<std::uint32_t>(file, pe + 24 + 56);
    const std::size_t sec0 = pe + 24 + opt;

    // Lay the image out at its virtual size, page-aligned, at a heap address:
    // the runtime base deliberately differs from image_base.
    std::vector<std::uint8_t> mapped(std::size_t(image_size) + 4096, 0);
    std::uintptr_t live = (reinterpret_cast<std::uintptr_t>(mapped.data()) + 4095) & ~std::uintptr_t(4095);
    auto* base = reinterpret_cast<std::uint8_t*>(live);
    std::vector<mem::ScanRegion> regions;
    for (std::uint16_t i = 0; i < nsec; ++i) {
        const std::size_t h = sec0 + std::size_t(i) * 40;
        char name[9] = {0};
        std::memcpy(name, file.data() + h, 8);
        const std::uint32_t vsize = rd<std::uint32_t>(file, h + 8);
        const std::uint32_t va = rd<std::uint32_t>(file, h + 12);
        const std::uint32_t rsize = rd<std::uint32_t>(file, h + 16);
        const std::uint32_t raw = rd<std::uint32_t>(file, h + 20);
        const std::uint32_t chars = rd<std::uint32_t>(file, h + 36);
        const std::uint32_t copy = std::min(rsize, vsize ? vsize : rsize);
        if (raw + std::size_t(copy) <= file.size() && va + std::size_t(copy) <= image_size)
            std::memcpy(base + va, file.data() + raw, copy);
        if (chars & 0x20000000u) regions.push_back({live + va, std::size_t(vsize ? vsize : rsize), name});
    }
    mem::bind_scan_regions(live, regions);
    std::printf("image %s: image_base 0x%08X, mapped at 0x%08lX, %zu executable section(s)\n",
                exe, image_base, (unsigned long)live, regions.size());

    AddressTable t;
    std::string error;
    if (!AddressTable::load_manifest(manifest, "", overlay ? overlay : "", t, error)) {
        std::fprintf(stderr, "load_manifest: %s\n", error.c_str());
        return 2;
    }
    check(t.image_base() == image_base, "manifest image_base matches the PE header");
    t.resolve_from_signatures(live);

    std::map<std::string, std::size_t> status;
    std::size_t pattern_bound = 0;
    for (const Site& s : t.sites()) {
        if (s.kind == SiteKind::Field) { ++status["field"]; continue; }
        if (s.resolved) {
            ++status[s.bound_from_pattern ? "bound" : "bound_other"];
            if (s.bound_from_pattern) ++pattern_bound;
        } else {
            ++status[s.locate_error.empty() ? "unbound" : s.locate_error];
        }
    }
    std::printf("sites %zu:", t.sites().size());
    for (const auto& [k, v] : status) std::printf(" %s=%zu", k.c_str(), v);
    std::printf("\n");
    check(status["bound_other"] == 0, "every resolved code site was bound by the pattern scan");

    const std::vector<std::string> missing = t.unresolved_required();
    std::printf("required unresolved: %zu", missing.size());
    for (const std::string& m : missing) std::printf(" %s(%s)", m.c_str(), t.find(m)->locate_error.c_str());
    std::printf("\n");
    // Required refusals are reported, not judged here: whether a refusal is
    // the right answer depends on the image (tools/manifest_resolve_check.py).

    if (dump) {
        std::FILE* f = std::fopen(dump, "wb");
        if (!f) { std::fprintf(stderr, "cannot write %s\n", dump); return 2; }
        for (const Site& s : t.sites()) {
            std::fprintf(f, "%s\t%s\t0x%08lX\t%s\n", s.name.c_str(),
                         s.resolved ? "bound" : (s.locate_error.empty() ? "unbound" : s.locate_error.c_str()),
                         (unsigned long)s.addr, to_string(s.kind));
        }
        std::fclose(f);
    }
    std::printf("\n%s: %d failure(s), %zu site(s) pattern-bound\n", g_failures ? "FAILED" : "OK", g_failures,
                pattern_bound);
    return g_failures ? 1 : 0;
}

}  // namespace

int main(int argc, char** argv) {
    const std::string cmd = argc > 1 ? argv[1] : "selftest";
    if (cmd == "selftest") {
        selftest();
        std::printf("\n%s: %d failure(s)\n", g_failures ? "FAILED" : "OK", g_failures);
        return g_failures ? 1 : 0;
    }
    if (cmd == "image" && argc >= 4) {
        const char* overlay = nullptr;
        const char* dump = nullptr;
        for (int i = 4; i + 1 < argc; i += 2) {
            if (std::strcmp(argv[i], "--overlay") == 0) overlay = argv[i + 1];
            else if (std::strcmp(argv[i], "--dump") == 0) dump = argv[i + 1];
        }
        return cmd_image(argv[2], argv[3], overlay, dump);
    }
    std::fprintf(stderr,
                 "usage: kp_manifesttest selftest\n"
                 "       kp_manifesttest image <exe> <hookmanifest.json> [--overlay <json>] [--dump <tsv>]\n");
    return 2;
}

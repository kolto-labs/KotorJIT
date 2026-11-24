// Offline checks for image::lookup_build_by_text (src/image/build_table.cpp).
//
// A loader-dependency edit -- DT_NEEDED on ELF (tools/elf_needed.py) or
// LC_LOAD_DYLIB on Mach-O -- changes an executable's file hash while its code
// section stays byte-identical. The loader then identifies the build by that
// code section instead. These checks pin what that lookup may and may not
// match: exact section name and digest, never PE, and never two different
// builds for one digest.
#include <cstdio>
#include <string>

#include "image/image.hpp"
#include "image/internal.hpp"

namespace {

int g_failures = 0;
void check(bool ok, const char* what) {
    std::printf("%s %s\n", ok ? "ok  " : "FAIL", what);
    if (!ok) ++g_failures;
}

using kp::image::Format;
using kp::image::lookup_build_by_text;

const char* kK1MacText = "800420f20c0b8e7732464bf24d9b074520d29759e7b4b31a6c0e31a1b11add18";
const char* kK2MacText = "148939e1662a1728888f586bd1a2086203a920c6e846da6aae14c7cdf638840c";

std::string alias_of(const kp::image::BuildRecord* r) { return r ? r->alias : "(none)"; }

}  // namespace

int main() {
    check(alias_of(lookup_build_by_text(Format::MachO, "__text", kK1MacText)) == "k1_mac_steam_x64",
          "K1 macOS is identified by its __text digest");
    // K2 macOS is listed twice (universal container and x86_64 slice) under
    // one alias: that is one build, not an ambiguity.
    check(alias_of(lookup_build_by_text(Format::MachO, "__text", kK2MacText)) == "k2_mac_steam_x64",
          "K2 macOS, listed under two file digests, still resolves to its one alias");
    check(lookup_build_by_text(Format::MachO, "__text", std::string(64, '0')) == nullptr,
          "an unknown digest matches nothing");
    check(lookup_build_by_text(Format::MachO, "__TEXT", kK1MacText) == nullptr,
          "the section name must match exactly");
    check(lookup_build_by_text(Format::Elf32, "__text", kK1MacText) == nullptr,
          "the format must match the record's");
    check(lookup_build_by_text(Format::Pe32, "__text", kK1MacText) == nullptr &&
              lookup_build_by_text(Format::Pe32, ".text", kK1MacText) == nullptr,
          "PE images never use the code-section fallback (their file hash is authoritative)");
    check(lookup_build_by_text(Format::MachO, "", kK1MacText) == nullptr &&
              lookup_build_by_text(Format::MachO, "__text", "") == nullptr,
          "empty inputs match nothing");

    if (g_failures) std::printf("%d failure(s)\n", g_failures);
    else std::printf("all build-lookup checks passed\n");
    return g_failures ? 1 : 0;
}

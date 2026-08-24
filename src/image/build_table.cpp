// Which builds we recognise, and what "deciphered" looks like for each.
//
// KNOWN DEVIATION from plan invariant 2 ("addresses are data"): the sentinel VA
// below is a literal in a .cpp file. It is here because the generated tables in
// data/addresses/*.json carry no sentinel and no expected .text digest -- there
// are no fields for them yet. The right fix is for tools/gen_address_tables.py
// to emit `sentinel.va`, `sentinel.bytes`, `sentinel.describes` and `text_sha256`
// per build, after which this array is deleted and the loader reads the JSON.
// The shape below is deliberately a flat static array so that swap is mechanical.
//
// Every digest here was computed from files on disk, not from a running game.
// See the note on each entry.
#include <cstring>

#include "internal.hpp"

namespace kp::image {
namespace {

// Steam and the offline unpack of it are the same code once deciphered: 828 of
// 828 4 KB pages of .text match the GOG build. This digest covers the first
// VirtualSize (0x33b1d0) bytes of that section, which is what the PE header
// claims is resident; the GOG build declares a larger VirtualSize for the same
// bytes, hence its separate entry below.
constexpr char kK1DecipheredText[] = "39bcd9f2c21de0e24aef77bcc2912f313fe9ed57803f505819d19a59ee0d4135";

const KnownText kK1SteamTexts[] = {
    {".text", kK1DecipheredText},
};

// The unpacker renames every section it rewrites, so the deciphered artifact on
// disk carries .textU where the running image carries .text.
const KnownText kK1UnpackedTexts[] = {
    {".textU", kK1DecipheredText},
    {".text",  kK1DecipheredText},
};

const KnownText kK1GogTexts[] = {
    {".text", "7f3fba60ecc641347e38de046be047239dd8ccb463ffca5e45fe889dd56ba3d3"},
};

// Two entries because the ELF yields two different code-section identities
// depending on how it was parsed, and both are legitimate: a live process cannot
// reach the section headers (e_shoff 0x8a8ecc sits past the last PT_LOAD), so it
// sees the r-x segment; an offline read sees .text proper.
const KnownText kK2LinuxTexts[] = {
    {".text", "79df1007e09581fb9f487d71a36c9402627e86d41a37bf3859eedbbbb5d326ad"},
    {"seg0",  "223d2684747cae6bc1c116dcdee7a85cd2dc9ce2315fb36d37fa55efc7e1dd81"},
};

const BuildRecord kBuilds[] = {
    {
        "k1_steam_103",
        "34e6d971c034222a417995d8e1e8fdd9f8781795c9c289bd86c499a439f34c88",
        Format::Pe32, 0x400000, true,
        // CSWVirtualMachineCommands::ExecuteCommand: mov edx,[esp+4]; cmp edx,0x304.
        // The bounds check against the 772-entry routine table -- a shape that
        // exists nowhere else in the image and cannot survive encryption.
        0x0052C0D0, "8b54240481fa04030000", "CSWVirtualMachineCommands::ExecuteCommand",
        kK1SteamTexts, sizeof kK1SteamTexts / sizeof kK1SteamTexts[0],
        "Steam build. .text is ciphertext on disk; identical to GOG once deciphered.",
    },
    {
        "k1_steam_103_unpacked",
        "2719ed2cb678e2c1ff5b2a787f9804d8e5f8dd52a02c2279080f031636e03a05",
        Format::Pe32, 0x400000, false,
        0, "", "",
        kK1UnpackedTexts, sizeof kK1UnpackedTexts / sizeof kK1UnpackedTexts[0],
        "Offline unpack of the Steam build. What the headless harness runs, since "
        "the shipped executable will not start without Steam.",
    },
    {
        "k1_gog_103",
        "9c10e0450a6eeca417e036e3cde7474fed1f0a92aab018446d156944dea91435",
        Format::Pe32, 0x400000, false,
        0, "", "",
        kK1GogTexts, sizeof kK1GogTexts / sizeof kK1GogTexts[0],
        "GOG build. Four sections, no wrapper. The symbol source for all K1 addresses.",
    },
    {
        "k2_steam_linux",
        "ed043d21a4578fd1c6f1557f0f72bde5589ba3572a5b6f1a687ed9feeab49ac3",
        Format::Elf32, 0x08048000, false,
        0, "", "",
        kK2LinuxTexts, sizeof kK2LinuxTexts / sizeof kK2LinuxTexts[0],
        "Native Aspyr ELF, EXEC not PIE, so addresses are fixed.",
    },
};

int hex_value(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

}  // namespace

std::vector<std::uint8_t> parse_hex(const char* s) {
    std::vector<std::uint8_t> out;
    if (s == nullptr) return out;
    const std::size_t n = std::strlen(s);
    if (n % 2 != 0) return out;
    for (std::size_t i = 0; i < n; i += 2) {
        const int hi = hex_value(s[i]);
        const int lo = hex_value(s[i + 1]);
        if (hi < 0 || lo < 0) return {};
        out.push_back(static_cast<std::uint8_t>((hi << 4) | lo));
    }
    return out;
}

const BuildRecord* build_table(std::size_t& count) {
    count = sizeof kBuilds / sizeof kBuilds[0];
    return kBuilds;
}

const BuildRecord* lookup_build(const std::string& sha256) {
    if (sha256.empty()) return nullptr;
    std::size_t n = 0;
    const BuildRecord* t = build_table(n);
    for (std::size_t i = 0; i < n; ++i) {
        if (sha256 == t[i].sha256) return &t[i];
    }
    return nullptr;
}

}  // namespace kp::image

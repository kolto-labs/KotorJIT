// Ciphertext detection, decipher-wait, and runtime image parsing.
//
// The primary KOTOR 1 target ships with its code section encrypted. Nothing may
// read an address, scan a byte, or install a hook until the wrapper has
// deciphered that section in memory and we have re-read the image from memory to
// confirm it. This module owns that sequence; the rest of the runtime waits on
// it.
//
// The same path serves unencrypted targets. Classification simply finds no
// ciphertext, the wait collapses to nothing, and verification is a plain hash.
// A packed build appearing later needs no new architecture.
#pragma once

#include <cstddef>
#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace kp::image {

enum class Format { Pe32, Elf32, MachO };

enum class SectionState {
    Plaintext,   // real code or data; safe to read
    Ciphertext,  // high entropy, no prologues; must not be read
    Deciphered,  // was Ciphertext, has since been decrypted in memory
};

struct Section {
    std::string  name;
    std::uintptr_t va    = 0;   // absolute virtual address once mapped
    std::size_t    size  = 0;   // virtual size
    bool           executable = false;
    SectionState   state = SectionState::Plaintext;
    double         entropy = 0.0;
};

// Why a section was judged ciphertext. Kept so diagnostics can explain the
// verdict rather than asserting it.
struct EntropyVerdict {
    double        bits_per_byte = 0.0;
    std::size_t   prologue_count = 0;   // 55 8b ec sequences
    std::size_t   int3_runs = 0;        // cc cc cc padding runs
    bool          is_ciphertext = false;
};

// A section is ciphertext when entropy is near-maximal AND the structural
// markers real x86 always leaves behind are absent. Entropy alone is not
// enough: compressed data and some resource blobs score high too.
EntropyVerdict classify(const std::uint8_t* data, std::size_t len);

struct Identity {
    std::string sha256;          // of the file on disk
    std::string build_alias;     // "k1_steam_103", or empty if unrecognised
    bool        recognised = false;
    bool        expected_encrypted = false;
};

// One byte pattern that must appear at one address before the image is
// considered deciphered. Comes from the build table, never hardcoded.
struct Sentinel {
    std::uintptr_t       va = 0;
    std::vector<std::uint8_t> bytes;
    std::string          describes;   // e.g. "CSWVirtualMachineCommands::ExecuteCommand"
};

struct WaitPolicy {
    unsigned poll_interval_ms = 50;
    unsigned timeout_ms       = 120'000;
    // After the sentinel first matches, wait this long and check again. The
    // wrapper may still be writing; matching once does not mean it has settled.
    unsigned settle_ms        = 100;
};

enum class LoadStatus {
    Ok,
    UnrecognisedBuild,     // hash not in the build table
    DecipherTimeout,       // sentinel never appeared
    PlaintextMismatch,     // deciphered, but not the code we expected
    ParseFailed,           // headers unreadable in memory
};

const char* to_string(LoadStatus);

struct LoadResult {
    LoadStatus            status = LoadStatus::ParseFailed;
    Identity              identity;
    Format                format = Format::Pe32;
    std::uintptr_t        image_base = 0;
    std::vector<Section>  sections;
    std::string           text_sha256;   // of the deciphered code section
    unsigned              waited_ms = 0;
    std::string           detail;        // human-readable failure explanation
};

// The whole load-time sequence, in order:
//   identify -> classify -> await decipher -> parse from memory -> verify.
//
// Returns non-Ok rather than throwing. A caller that gets anything but Ok must
// not proceed to resolve addresses; refusing to install is the correct outcome
// and is preferable to installing against an image we cannot vouch for.
LoadResult load(const std::string& module_path, const WaitPolicy& = {});

// Parse headers out of the live mapped image rather than the file. This is the
// distinction that matters: on-disk headers describe the packed layout, and an
// unpacker rewrites section names (.text becomes .textU), so a file-derived
// section map is wrong in two different ways.
std::optional<std::vector<Section>> parse_mapped(std::uintptr_t image_base, Format);

// Write the deciphered image to disk. Turns "we had to decipher this to run"
// into a reusable artifact for offline analysis, which is also what an
// encrypted binary needs before it can be matched against anything.
bool dump(const LoadResult&, const std::string& out_path, std::string& error);

}  // namespace kp::image

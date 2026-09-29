// Logical hook site names -> addresses -> installed detours.
//
// Invariant 2 of the plan is "addresses are data": no virtual address appears in
// a .cpp file. A site is named `vm.run_script` in code, and the number behind it
// comes from data/addresses/<build>.json, which a generator emits from the RE
// corpus. Supporting another game build is adding a JSON file.
//
// ALL OR NOTHING, and it is two different sets
// ============================================
// A partially installed hook set is worse than none: some events fire and some
// silently do not, and the difference is invisible from Lua. So installation is
// atomic. But "required" and "gets patched" are NOT the same set, and conflating
// them is the easy bug here:
//
//   * RESOLUTION covers every site regardless of kind. `vm.execute_command` is
//     required and is a `reference` -- we never patch it, we need its address to
//     find the routine dispatch table. A missing required reference must abort
//     the whole install just as a missing required detour does.
//   * INSTALLATION covers only `detour` sites. A `call` or `reference` site
//     resolves to an address and stops there. Patching one would be a bug.
//
// Resolution is checked first, before a single byte is written. If it fails,
// nothing was touched. If a later detour fails to install, the ones already
// installed are rolled back.
#pragma once

#include <cstdint>
#include <memory>
#include <string>
#include <string_view>
#include <vector>

#include "hooks/native_detour.hpp"

namespace kp::hooks {

enum class SiteKind {
    Detour,     // we patch it
    Reference,  // we only need the address
    Call,       // we call it; still never patched
    // A struct member, not code: `offset` bytes into an object the caller
    // already holds, `size` bytes wide. `addr` is the owning global when the
    // field is anchored at one (g_pAppManager) and 0 when it is reached through
    // a pointer chain. Never patched, never scanned for -- there are no bytes
    // to verify, so the generator emits no expected_bytes and
    // resolve_from_signatures leaves it alone.
    Field,
    Unknown,
};

SiteKind site_kind_from_string(std::string_view);
const char* to_string(SiteKind);

struct Site {
    std::string    name;      // logical key, e.g. "vm.run_script"
    // Runtime adapter role emitted by AgentDecompile.  This is separate from
    // a logical display name: generated consumers bind roles, not labels.
    std::string    adapter_key;
    std::vector<std::string> aliases;
    std::string    cls;       // "CVirtualMachineInternal"; empty for free functions
    std::string    method;    // "RunScript"
    SiteKind       kind = SiteKind::Unknown;
    bool           required = false;
    bool           resolved = false;   // false when the generator could not bind it
    bool           bound_from_scan = false; // true when unique bytes won over the hint
    std::uintptr_t addr = 0;           // absolute VA, as recorded against image_base
    double         confidence = 0.0;
    // Bytes the generator read at this address from a plaintext reference image.
    // The hook engine verifies against these before patching, so a stale table
    // or a mismatched build fails at the site instead of corrupting it.
    std::vector<std::uint8_t> expected;
    // Field sites only: byte offset into the owning object and width in bytes.
    // Zero on every other kind. A Field with size 0 is unresolved.
    std::uint32_t  offset = 0;
    std::uint32_t  size = 0;
};

// A parsed data/addresses/<build>.json, or an AgentDecompile hook pack
// (`agentdecompile.hookpack/v1`) flattened for one build slug.
class AddressTable {
public:
    static bool load_file(const std::string& path, AddressTable& out, std::string& error);
    static bool parse(std::string_view json, AddressTable& out, std::string& error);
    static bool parse(std::string_view json, const std::string& build_slug,
                      AddressTable& out, std::string& error);
    // Flatten instances for `build_slug`. Overlay is the optional
    // data/addresses/<build>.json — expected_bytes / kind / required only.
    // Does not invent bytes.
    static bool load_hookpack(const std::string& pack_path,
                              const std::string& build_slug,
                              const std::string& overlay_path,
                              AddressTable& out,
                              std::string& error);

    const Site* find(std::string_view name) const;
    // Exact adapter-key/alias lookup.  Returns null on an absent or ambiguous
    // role so a generated operation can fail closed rather than choose a site.
    const Site* find_adapter(std::string_view adapter_key) const;
    // True only for an operation whose selected target, declared roles and
    // byte-bound site entries all agreed while parsing this hook pack.
    bool has_operation(std::string_view operation_id) const;
    const std::vector<Site>& sites() const { return sites_; }

    const std::string& build() const { return build_; }
    const std::string& game() const { return game_; }
    const std::string& platform_name() const { return platform_; }
    const std::string& expected_sha256() const { return sha256_; }

    // The base the recorded addresses are relative to. The K1 PE declares
    // 0x400000 and cannot relocate, so the delta is zero in practice -- but it
    // is carried explicitly so a relocatable image is a data question.
    std::uintptr_t image_base() const { return image_base_; }

    std::vector<std::string> unresolved_required() const;

    // Recorded VA is a hint. Unique expected_bytes bind the site.
    // `runtime_base` 0 means the table's image_base (no reloc).
    // A hit is stored as an image VA so install() still applies delta once.
    void resolve_from_signatures(std::uintptr_t runtime_base);

    void merge_overlay(const AddressTable& overlay);

private:
    std::string    build_;
    std::string    game_;
    std::string    platform_;
    std::string    sha256_;
    std::uintptr_t image_base_ = 0;
    std::vector<Site> sites_;
    std::vector<std::string> operations_;
};

// One thing the caller wants done to one site.
struct HookRequest {
    std::string               site;    // logical name
    void*                     detour = nullptr;
    // Bytes the caller expects to find at the site. Leave empty to use the ones
    // the address table recorded, which is the normal case and the stronger
    // guarantee -- the generator writes the site's full displaced prologue, and
    // verification is only as wide as the pattern it is given.
    std::vector<std::uint8_t> expect;
};

// A set of hooks that install and uninstall together.
class HookSet {
public:
    HookSet() = default;
    ~HookSet();

    HookSet(const HookSet&) = delete;
    HookSet& operator=(const HookSet&) = delete;

    void add(HookRequest);

    // `runtime_base` is where the image actually loaded. Pass 0 to mean "the
    // table's own image_base", i.e. no relocation.
    //
    // Returns false with `error` filled and NOTHING installed if any required
    // site is unresolved, or rolls everything back if a patch fails.
    bool install(const AddressTable&, std::uintptr_t runtime_base, std::string& error);

    void uninstall();

    // Trampoline entry for a site: the address a hook body calls to reach the
    // untouched original. Null when the site is not installed.
    void* original(std::string_view site) const;

    std::size_t installed_count() const { return installed_.size(); }
    bool installed() const { return !installed_.empty(); }

private:
    struct Installed {
        std::string name;
        std::unique_ptr<Detour> detour;
    };

    std::vector<HookRequest> requests_;
    std::vector<Installed>   installed_;
};

}  // namespace kp::hooks

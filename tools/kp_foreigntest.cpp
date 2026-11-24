// Offline checks for living alongside other modules' hooks (hooks/foreign.hpp).
//
// No game. The "other mod" is simulated the way MinHook and Detours actually
// work: a function in executable memory has its first instruction replaced by
// `jmp rel32` to the other mod's detour, and the displaced instruction is
// copied into a trampoline that jumps back. Then Hyperstim's resolver and
// detour engine are pointed at it:
//
//   * decode_stub recognises every stub form a hooking library writes
//   * match_tolerant accepts a replaced head only when the rest is original
//   * find_relocated_prologue finds the other mod's trampoline
//   * AddressTable binds the site on evidence B, C or D -- and refuses under
//     Policy::Refuse, on a non-stub head, and on a changed tail
//   * HookSet chains in front of the other detour: ours -> theirs -> original
//   * the dispatcher bound is read from the relocated original prologue
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#include "api/enginestruct.hpp"
#include "api/memory.hpp"
#include "hooks/foreign.hpp"
#include "hooks/registry.hpp"
#include "platform/platform.hpp"

namespace {

namespace F = kp::hooks::foreign;
using kp::hooks::AddressTable;
using kp::hooks::HookRequest;
using kp::hooks::HookSet;
using kp::hooks::Site;

int g_failures = 0;
void check(bool ok, const char* what) {
    std::printf("%s %s\n", ok ? "ok  " : "FAIL", what);
    if (!ok) ++g_failures;
}

std::vector<std::uint8_t> hex(const char* s) {
    std::vector<std::uint8_t> out;
    auto nib = [](char c) { return c <= '9' ? c - '0' : (c | 0x20) - 'a' + 10; };
    for (; s[0] && s[1]; s += 2) out.push_back(static_cast<std::uint8_t>(nib(s[0]) << 4 | nib(s[1])));
    return out;
}

void put_rel32(std::uint8_t* at_insn, std::size_t insn_len, std::uintptr_t target) {
    const std::uintptr_t next = reinterpret_cast<std::uintptr_t>(at_insn) + insn_len;
    const std::int32_t rel = static_cast<std::int32_t>(target - next);
    std::memcpy(at_insn + insn_len - 4, &rel, 4);
}

std::string to_hex(std::uintptr_t v) {
    char b[24];
    std::snprintf(b, sizeof b, "%lu", static_cast<unsigned long>(v));
    return b;
}

// A one-site plain address table at a live address (image_base 0, so the
// recorded VA is the live address).
AddressTable table_for(std::uintptr_t addr, const char* expected_hex, const char* kind) {
    const std::string json = std::string(R"({"build":"test","game":"k1","platform":"linux","image_base":0,)") +
        R"("sites":{"test.site":{"kind":")" + kind + R"(","required":true,"addr":)" + to_hex(addr) +
        R"(,"expected_bytes":")" + expected_hex + R"("}}})";
    AddressTable t;
    std::string error;
    if (!AddressTable::parse(json, t, error)) std::printf("     parse error: %s\n", error.c_str());
    return t;
}

// --------------------------------------------------------------- stubs ----

void stub_forms() {
    F::Stub s;
    const std::uintptr_t at = 0x00401000;

    auto e9 = hex("e9fb0f0000");   // jmp +0xffb -> at+5+0xffb = 0x402000
    check(F::decode_stub(e9.data(), e9.size(), at, s, false) && s.kind == F::StubKind::JmpRel32 &&
              s.length == 5 && s.destination == 0x402000,
          "E9 rel32 decodes with its destination");
    auto eb = hex("ebfe");
    check(F::decode_stub(eb.data(), eb.size(), at, s, false) && s.kind == F::StubKind::JmpRel8 &&
              s.length == 2 && s.destination == at,
          "EB rel8 decodes (a jump to itself is still a stub)");
    auto pr = hex("6878563412c3");
    check(F::decode_stub(pr.data(), pr.size(), at, s, false) && s.kind == F::StubKind::PushRet &&
              s.destination == 0x12345678,
          "push imm32; ret decodes");
    auto mj = hex("b878563412ffe0");
    check(F::decode_stub(mj.data(), mj.size(), at, s, false) && s.kind == F::StubKind::MovRegJmpReg &&
              s.length == 7 && s.destination == 0x12345678,
          "mov eax, imm32; jmp eax decodes");
    auto mj_bad = hex("b878563412ffe1");
    check(!F::decode_stub(mj_bad.data(), mj_bad.size(), at, s, false),
          "mov eax then jmp ecx is not a stub (registers must agree)");
    static std::uint32_t slot = 0x0BADF00D;
    std::uint8_t ind[6] = {0xFF, 0x25, 0, 0, 0, 0};
    const auto slot_va = static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(&slot));
    std::memcpy(ind + 2, &slot_va, 4);
    check(F::decode_stub(ind, 6, at, s, false) && s.kind == F::StubKind::JmpMemAbs32 &&
              s.destination == 0x0BADF00D,
          "jmp [abs32] decodes through a readable slot");
    auto abs64 = hex("ff25000000000102030405060708");
    check(F::decode_stub(abs64.data(), abs64.size(), at, s, true) && s.kind == F::StubKind::JmpAbs64 &&
              s.length == 14,
          "x86-64 jmp [rip+0]; dq abs64 decodes (14 bytes)");
    auto movabs = hex("48b80102030405060708ffe0");
    check(F::decode_stub(movabs.data(), movabs.size(), at, s, true) &&
              s.kind == F::StubKind::MovAbsRegJmpReg && s.length == 12,
          "x86-64 mov rax, imm64; jmp rax decodes");
    auto prologue = hex("8b54240481fa04030000");
    check(!F::decode_stub(prologue.data(), prologue.size(), at, s, false),
          "an ordinary prologue is not a stub");
}

// ------------------------------------------------------- tolerant match ----

// K1 ExecuteCommand as recorded in data/addresses/k1_*_103.json:
//   8B 54 24 04        mov edx, [esp+4]
//   81 FA 04 03 00 00  cmp edx, 0x304
//   7D 17 8B 41 0C 8B  (original tail)
const char* kExecuteCommand = "8b54240481fa040300007d178b410c8b";

void tolerant() {
    const auto expected = hex(kExecuteCommand);
    const std::uintptr_t at = 0x0052C0D0;

    auto live = expected;
    live[0] = 0xE9; live[1] = 0x11; live[2] = 0x22; live[3] = 0x33; live[4] = 0x04;   // MinHook
    F::TolerantMatch m = F::match_tolerant(live.data(), expected.data(), expected.size(), at, false);
    check(m.ok && m.stub.kind == F::StubKind::JmpRel32 && m.boundary == 10 && m.tail == 6,
          "MinHook-style 5-byte jmp over ExecuteCommand: boundary 10, 6 original bytes prove it");

    auto filled = live;
    for (int i = 5; i < 10; ++i) filled[i] = 0xCC;   // Detours pads with int3
    m = F::match_tolerant(filled.data(), expected.data(), expected.size(), at, false);
    check(m.ok, "Detours-style int3 filler after the stub is accepted");

    auto tail_changed = live;
    tail_changed[12] ^= 0xFF;
    m = F::match_tolerant(tail_changed.data(), expected.data(), expected.size(), at, false);
    check(!m.ok && m.refusal != nullptr, "a changed byte after the displaced head refuses");

    auto junk = live;
    junk[7] = 0x12;   // neither original (0x04) nor filler
    m = F::match_tolerant(junk.data(), expected.data(), expected.size(), at, false);
    check(!m.ok, "garbage between the stub and the boundary refuses");

    auto not_stub = expected;
    not_stub[0] = 0x31; not_stub[1] = 0xC0;   // xor eax, eax
    m = F::match_tolerant(not_stub.data(), expected.data(), expected.size(), at, false);
    check(!m.ok, "a changed head that is not a detour stub refuses (wrong function or build)");

    m = F::match_tolerant(expected.data(), expected.data(), expected.size(), at, false);
    check(!m.ok, "unpatched bytes are not this module's business");

    auto jmp_orig = hex("e900000000909090909090");
    auto jmp_live = hex("e911111111909090909090");
    m = F::match_tolerant(jmp_live.data(), jmp_orig.data(), jmp_orig.size(), at, false);
    check(!m.ok, "a function that itself starts with a jump is never treated as hooked");

    auto thin = hex("8b54240481fa0403000090");   // boundary 10, tail 1
    auto thin_live = thin;
    thin_live[0] = 0xE9;
    m = F::match_tolerant(thin_live.data(), thin.data(), thin.size(), at, false, true);
    check(!m.ok, "a one-byte tail is not enough on its own");
    m = F::match_tolerant(thin_live.data(), thin.data(), thin.size(), at, false, false);
    check(m.ok && m.tail == 1, "...but is reported to a caller that brings other evidence");

    F::Policy p;
    check(F::parse_policy("chain", p) && p == F::Policy::Chain && F::parse_policy("REFUSE", p) &&
              p == F::Policy::Refuse && !F::parse_policy("maybe", p),
          "policy parses chain / refuse and rejects anything else");
}

// ------------------------------------------- executable-memory scenarios ----

using Fn = int (*)();

struct Pages {
    std::uint8_t* site = nullptr;   // "the game"
    std::uint8_t* mod = nullptr;    // "the other mod": trampolines and detour
    std::size_t len = 4096;
};

// Function bodies in `site` page:
//   +0x000  long:  B8 07 00 00 00  90 x8  C3      (tail 9 -> evidence B)
//   +0x100  thin:  B8 08 00 00 00  90 90  C3      (tail 3 -> needs C or D)
//   +0x200  thin2: B8 09 00 00 00  90 90  C3      (tail 3, no trampoline -> D)
// Each is hooked by "the other mod": head -> jmp mod_detour_N, whose body is
//   call trampoline_N ; add eax, 100 ; ret
// and trampoline_N is the displaced `mov eax, imm` followed by jmp back.
constexpr std::size_t kLong = 0x000, kThin = 0x100, kThin2 = 0x200;
const char* kLongHex  = "b8070000009090909090909090c3";
const char* kThinHex  = "b8080000009090c3";
const char* kThin2Hex = "b8090000009090c3";

Pages build_scene() {
    Pages p;
    p.site = static_cast<std::uint8_t*>(kp::platform::alloc_exec(p.len));
    p.mod = static_cast<std::uint8_t*>(kp::platform::alloc_exec(p.len));
    if (!p.site || !p.mod) return {};
    std::memset(p.site, 0xCC, p.len);
    std::memset(p.mod, 0xCC, p.len);

    struct Fn3 { std::size_t at; const char* body; std::size_t tramp; std::size_t detour; bool write_tramp; };
    const Fn3 fns[] = {
        {kLong,  kLongHex,  0x000, 0x080, true},
        {kThin,  kThinHex,  0x100, 0x180, true},
        {kThin2, kThin2Hex, 0x200, 0x280, false},   // trampoline elsewhere (not a copy we can find)
    };
    for (const Fn3& f : fns) {
        const auto body = hex(f.body);
        std::memcpy(p.site + f.at, body.data(), body.size());

        std::uint8_t* tramp = p.mod + f.tramp;
        if (f.write_tramp) {
            std::memcpy(tramp, body.data(), 5);                  // displaced mov eax, imm
            tramp[5] = 0xE9;                                     // jmp back to site+5
            put_rel32(tramp + 5, 5, reinterpret_cast<std::uintptr_t>(p.site + f.at + 5));
        } else {
            // Same behaviour, but the copy is not byte-identical (mov via
            // ecx then xchg), as when a hooking library rewrote the prologue.
            const std::uint8_t alt[] = {0xB9, body[1], body[2], body[3], body[4], 0x91};
            std::memcpy(tramp, alt, sizeof alt);
            tramp[6] = 0xE9;
            put_rel32(tramp + 6, 5, reinterpret_cast<std::uintptr_t>(p.site + f.at + 5));
        }

        std::uint8_t* det = p.mod + f.detour;
        det[0] = 0xE8;                                           // call trampoline
        put_rel32(det, 5, reinterpret_cast<std::uintptr_t>(tramp));
        det[5] = 0x83; det[6] = 0xC0; det[7] = 0x64;             // add eax, 100
        det[8] = 0xC3;                                           // ret

        std::uint8_t* head = p.site + f.at;                      // the other mod's patch
        head[0] = 0xE9;
        put_rel32(head, 5, reinterpret_cast<std::uintptr_t>(det));
    }
    kp::platform::commit_exec(p.site, p.len);
    kp::platform::commit_exec(p.mod, p.len);
    kp::platform::flush_instruction_cache(p.site, p.len);
    kp::platform::flush_instruction_cache(p.mod, p.len);
    return p;
}

Fn g_orig = nullptr;
int our_detour() { return g_orig() + 1000; }

void scenes() {
    Pages p = build_scene();
    check(p.site != nullptr && p.mod != nullptr, "executable pages for the scene");
    if (!p.site || !p.mod) return;
    const auto site_va = reinterpret_cast<std::uintptr_t>(p.site);
    auto fn = [&](std::size_t off) { return reinterpret_cast<Fn>(p.site + off); };

    check(fn(kLong)() == 107 && fn(kThin)() == 108 && fn(kThin2)() == 109,
          "scene: the other mod's detours are live (original + 100)");

    // --- relocated prologue search -----------------------------------------
    const auto long_body = hex(kLongHex);
    const std::uintptr_t copy =
        F::find_relocated_prologue(long_body.data(), 5, site_va + kLong + 5, false);
    check(copy == reinterpret_cast<std::uintptr_t>(p.mod + 0x000),
          "the other mod's trampoline is found by its displaced bytes and jump back");
    check(F::find_relocated_prologue(long_body.data(), 5, site_va + kLong + 6, false) == 0,
          "a copy that jumps back anywhere else is not accepted");

    // --- resolution under each policy ---------------------------------------
    F::set_policy(F::Policy::Refuse);
    {
        AddressTable t = table_for(site_va + kLong, kLongHex, "detour");
        t.resolve_from_signatures(0);
        check(!t.find("test.site")->resolved, "refuse policy: a detoured site stays unresolved (old behaviour)");
    }
    F::set_policy(F::Policy::Chain);
    {
        AddressTable t = table_for(site_va + kLong, kLongHex, "detour");
        t.resolve_from_signatures(0);
        const Site* s = t.find("test.site");
        check(s->resolved && s->foreign_patched && s->foreign_evidence == 'B' && s->foreign_boundary == 5,
              "chain: bound on evidence B (stub + 9 intact original bytes)");
        check(s->relocated_prologue == copy && s->original_prologue.size() == 5,
              "chain: the relocated original prologue is recorded too");
    }
    {
        AddressTable t = table_for(site_va + kThin, kThinHex, "reference");
        t.resolve_from_signatures(0);
        const Site* s = t.find("test.site");
        check(s->resolved && s->foreign_evidence == 'C',
              "thin tail: bound on evidence C (displaced original found relocated)");
    }
    {
        AddressTable t = table_for(site_va + kThin2, kThin2Hex, "reference");
        t.resolve_from_signatures(0);
        const Site* s = t.find("test.site");
        check(s->resolved && s->foreign_evidence == 'D' && s->relocated_prologue == 0,
              "thin tail, no findable copy: bound on evidence D (build-selected address)");
    }
    {
        // Stale hint: the site moves only by scan, and only on B or C.
        kp::api::memory::bind_scan_regions(site_va, {{site_va, p.len, "scene"}});
        AddressTable t = table_for(1, kLongHex, "detour");
        t.resolve_from_signatures(0);
        const Site* s = t.find("test.site");
        check(s->resolved && s->bound_from_scan && s->addr == site_va + kLong && s->foreign_evidence == 'B',
              "stale hint: found by the surviving tail, proven by the stub");
        AddressTable thin = table_for(1, kThin2Hex, "reference");
        thin.resolve_from_signatures(0);
        check(!thin.find("test.site")->resolved,
              "stale hint + thin tail + no copy: refused (D needs the recorded address)");
    }
    {
        AddressTable t = table_for(site_va + kLong, "b8070000009090909090909090c4", "detour");
        t.resolve_from_signatures(0);
        check(!t.find("test.site")->resolved, "a site whose original tail differs is refused even with a stub");
    }

    // --- chaining in front of the other mod -----------------------------------
    {
        AddressTable t = table_for(site_va + kLong, kLongHex, "detour");
        t.resolve_from_signatures(0);
        HookSet set;
        HookRequest r;
        r.site = "test.site";
        r.detour = reinterpret_cast<void*>(&our_detour);
        set.add(r);
        std::string error;
        const bool installed = set.install(t, 0, error);
        if (!installed) std::printf("     install error: %s\n", error.c_str());
        check(installed, "HookSet installs over another module's detour");
        g_orig = reinterpret_cast<Fn>(set.original("test.site"));
        check(installed && fn(kLong)() == 1107,
              "chain order: ours (+1000) -> theirs (+100) -> original (7)");
        set.uninstall();
        check(fn(kLong)() == 107, "uninstall restores the other mod's detour untouched");
    }
}

// ------------------------------------------------------ dispatcher bound ----

void dispatcher_bound() {
    // KPM grows the table to 1000: cmp edx, 0x3E8. Then another mod detours it.
    const auto original = hex("8b54240481fae80300007d178b410c8b9090909090909090909090909090909090");
    auto live = original;
    live[0] = 0xE9; live[1] = 0x81; live[2] = 0xFA; live[3] = 0x00; live[4] = 0x10;   // decoy 81 FA
    kp::api::VmSites s;
    s.execute_command = reinterpret_cast<std::uintptr_t>(live.data());

    s.execute_command_foreign = true;
    s.execute_command_head = 10;
    s.execute_command_prologue.assign(original.begin(), original.begin() + 10);
    check(kp::api::discover_command_count(s) == 1000,
          "bound read from the relocated original prologue (1000), not the other mod's jump");

    s.execute_command_prologue.clear();
    check(kp::api::discover_command_count(s) == 0x304,
          "no relocated copy: never decoded out of the stub; falls back to the stock bound");

    kp::api::VmSites plain;
    plain.execute_command = reinterpret_cast<std::uintptr_t>(original.data());
    check(kp::api::discover_command_count(plain) == 1000, "unpatched dispatcher still reads its own bound");
}

}  // namespace

int main() {
    stub_forms();
    tolerant();
    scenes();
    dispatcher_bound();
    if (g_failures) std::printf("%d failure(s)\n", g_failures);
    else std::printf("all foreign-patch checks passed\n");
    return g_failures ? 1 : 0;
}

// kp_hooktool -- exercise the detour engine against this process.
//
//   kp_hooktool selftest [--table <path>]
//   kp_hooktool lendis [<hex bytes>...]
//
// Why a self-hosted harness. The engine's failure mode is a wrong instruction
// length, and a wrong length does not fail where it was computed -- it corrupts
// a function and the game dies later, somewhere else. Waiting for a live game to
// tell us that is a slow and ambiguous feedback loop. A native 32-bit Linux
// binary that detours its own functions gives the same answer in milliseconds,
// with a debugger attached if needed, before Wine is involved at all.
//
// The lendis vectors are not synthetic. They are the real first 32 bytes of five
// K1 functions, read out of the deciphered image at
// agentdecompile/target/swkotor-unpack/swkotor.exe.unpacked.exe (.textU at VA
// 0x401000, raw 0x1000, so file offset = VA - 0x400000). Expected lengths were
// checked against objdump, not against this decoder.

#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include "hooks/registry.hpp"
#include "hooks/thiscall.hpp"
#include "hooks/trampoline.hpp"
#include "platform/platform.hpp"

using namespace kp::hooks;

namespace {

int g_failures = 0;

void check(bool ok, const char* what) {
    std::printf("  [%s] %s\n", ok ? "PASS" : "FAIL", what);
    if (!ok) ++g_failures;
}

void section(const char* title) {
    std::printf("\n== %s ==\n", title);
}

// ---------------------------------------------------------------------------
// Length-disassembler vectors
// ---------------------------------------------------------------------------

struct Vector {
    const char*  name;
    unsigned     va;
    std::vector<std::uint8_t> bytes;
    // Expected length of each instruction, in order. Zero-terminated.
    std::vector<std::uint8_t> lengths;
    const char*  note;
};

std::vector<Vector> game_vectors() {
    return {
        {"CVirtualMachineInternal::RunScript", 0x005D45D0,
         {0x53, 0x55, 0x56, 0x57, 0x8B, 0x7C, 0x24, 0x14, 0x33, 0xED,
          0x3B, 0xFD, 0x8B, 0xF1, 0x0F, 0x84, 0xAE, 0x01, 0x00, 0x00},
         {1, 1, 1, 1, 4, 2, 2, 2, 6},
         "push x4; mov edi,[esp+14] (SIB+disp8); xor; cmp; mov; jz rel32"},

        {"CSWVirtualMachineCommands::ExecuteCommand", 0x0052C0D0,
         {0x8B, 0x54, 0x24, 0x04, 0x81, 0xFA, 0x04, 0x03, 0x00, 0x00,
          0x7D, 0x17, 0x8B, 0x41, 0x0C, 0x8B, 0x04, 0x90, 0x85, 0xC0},
         {4, 6, 2, 3, 3, 2},
         "the 772-routine bounds check; 8B 04 90 is ModRM+SIB with no disp"},

        {"CSWSCreature::EventHandler", 0x004FECE0,
         {0x6A, 0xFF, 0x64, 0xA1, 0x00, 0x00, 0x00, 0x00, 0x68, 0xA6,
          0xB6, 0x71, 0x00, 0x50, 0x64, 0x89, 0x25, 0x00, 0x00, 0x00,
          0x00, 0x83, 0xEC, 0x20},
         {2, 6, 5, 1, 7, 3},
         "SEH frame setup: 64 A1 is moffs32 (no ModRM); 64 89 25 is mod=00 rm=101 disp32"},

        {"CServerExoAppInternal::MainLoop", 0x004BABB0,
         {0x55, 0x8B, 0xEC, 0x83, 0xE4, 0xF8, 0x6A, 0xFF, 0x68, 0x33,
          0x93, 0x71, 0x00, 0x64, 0xA1, 0x00, 0x00, 0x00, 0x00, 0x50},
         {1, 2, 3, 2, 5, 6, 1},
         "classic 55 8B EC frame, then esp alignment"},

        {"DoConsole", 0x00401F00,
         {0x6A, 0xFF, 0x68, 0x68, 0x3F, 0x71, 0x00, 0x64, 0xA1, 0x00,
          0x00, 0x00, 0x00, 0x50, 0x64, 0x89, 0x25, 0x00, 0x00, 0x00,
          0x00, 0x83, 0xEC, 0x0C},
         {2, 5, 6, 1, 7, 3},
         "console entry point"},

        {"endbr32 + modern prologue", 0,
         {0xF3, 0x0F, 0x1E, 0xFB, 0x55, 0x89, 0xE5, 0x83, 0xEC, 0x18},
         {4, 1, 2, 3},
         "not from the game: control-flow-enforcement prologue GCC emits, "
         "decoded by the generic 0F 18..1F ModRM path"},
    };
}

// Decode a byte run and print it. Returns the decoded lengths.
std::vector<std::uint8_t> disassemble(const std::uint8_t* bytes, std::size_t len,
                                      unsigned base_va, bool verbose) {
    std::vector<std::uint8_t> lengths;
    std::size_t off = 0;
    while (off < len) {
        const Insn in = decode(bytes + off, len - off);
        if (!in.valid) {
            if (verbose) {
                // A fixed-size byte window usually ends mid-instruction. That is
                // the same refusal as an unknown opcode, but it means something
                // different, so it is labelled differently.
                const bool ran_out = in.refusal &&
                                     std::strncmp(in.refusal, "truncated", 9) == 0;
                std::printf("  %04zx  %-26s %s: %s\n", off,
                            hex_bytes(bytes + off, len - off).c_str(),
                            ran_out ? "window ends" : "REFUSED",
                            in.refusal ? in.refusal : "?");
            }
            lengths.push_back(0);
            break;
        }
        if (verbose) {
            std::string rel;
            if (in.rel != RelKind::None) {
                const std::uintptr_t t = branch_target(bytes + off, in, base_va + off);
                char buf[64];
                std::snprintf(buf, sizeof(buf), "  %s -> %08X",
                              in.rel == RelKind::Rel8 ? "rel8 " : "rel32",
                              static_cast<unsigned>(t));
                rel = buf;
            }
            std::printf("  %04zx  %-26s len=%-2u%s\n", off,
                        hex_bytes(bytes + off, in.length).c_str(), in.length, rel.c_str());
        }
        lengths.push_back(in.length);
        off += in.length;
    }
    return lengths;
}

// ---------------------------------------------------------------------------
// Phase 1 -- decode the real game prologues
// ---------------------------------------------------------------------------

void phase_lendis() {
    section("phase 1: length disassembly of real K1 prologues");
    for (const Vector& v : game_vectors()) {
        if (v.va) std::printf("\n%s  (K1 %08X)\n", v.name, v.va);
        else      std::printf("\n%s\n", v.name);
        std::printf("  %s\n", v.note);

        const std::vector<std::uint8_t> got =
            disassemble(v.bytes.data(), v.bytes.size(), v.va, true);

        // The vector's expected list may stop short of the byte run, because the
        // run is a fixed 20-24 byte window and the last instruction in it is
        // often truncated. Compare only the prefix we vouched for.
        bool ok = got.size() >= v.lengths.size();
        for (std::size_t i = 0; ok && i < v.lengths.size(); ++i) {
            ok = got[i] == v.lengths[i];
        }
        check(ok, v.name);
    }

    section("phase 1b: the decoder must refuse what it does not know");
    struct Bad { const char* name; std::vector<std::uint8_t> bytes; };
    const Bad bad[] = {
        {"0F 38 three-byte escape", {0x0F, 0x38, 0x00, 0xC0}},
        {"0F 3A three-byte escape", {0x0F, 0x3A, 0x0F, 0xC1, 0x04}},
        {"67 address-size prefix",  {0x67, 0x8B, 0x07}},
        {"truncated 8B with no ModRM", {0x8B}},
    };
    for (const Bad& b : bad) {
        const Insn in = decode(b.bytes.data(), b.bytes.size());
        std::printf("  %-30s -> %s\n", b.name,
                    in.valid ? "ACCEPTED" : (in.refusal ? in.refusal : "refused"));
        check(!in.valid, b.name);
    }
}

// ---------------------------------------------------------------------------
// Phase 2 -- detour a real __thiscall-shaped function in this process
// ---------------------------------------------------------------------------

struct Widget {
    int base;
};

// noinline+noclone so -O2 cannot fold this away; the whole test depends on there
// being a real function at a real address with a real prologue.
int KP_THISCALL __attribute__((noinline, noclone))
widget_sum(Widget* self, int a, int b) {
    volatile int base = self->base;
    return base + a + b;
}

using WidgetSumFn = int(KP_THISCALL*)(Widget*, int, int);

WidgetSumFn g_widget_orig = nullptr;
int         g_widget_hook_calls = 0;

// The hook has the SAME signature as the target, which is what makes the
// callee-pop amount identical. See thiscall.hpp.
int KP_THISCALL widget_sum_hook(Widget* self, int a, int b) {
    return kp::hooks::guard(-1, [&] {
        ++g_widget_hook_calls;
        return g_widget_orig(self, a, b) * 10;
    });
}

// Called through a volatile pointer so the compiler cannot devirtualise the call
// into a direct one it then inlines -- which would bypass the patched bytes.
volatile WidgetSumFn g_widget_call = widget_sum;

void phase_detour() {
    section("phase 2: detour a __thiscall function in this process");

    Widget w{100};
    auto* target = reinterpret_cast<void*>(widget_sum);

    std::uint8_t before[16];
    std::memcpy(before, target, sizeof(before));
    std::printf("  target  %p\n", target);
    std::printf("  prologue %s\n", hex_bytes(before, 12).c_str());
    disassemble(before, sizeof(before), reinterpret_cast<std::uintptr_t>(target), true);

    const int baseline = g_widget_call(&w, 3, 4);
    std::printf("  unhooked call -> %d\n", baseline);
    check(baseline == 107, "unhooked result is 100+3+4");

    // An address that is not mapped must be refused without dereferencing it.
    // This is the "wrong build" case: a table entry that points nowhere.
    {
        Detour probe;
        std::string detail;
        const HookStatus st = probe.install(reinterpret_cast<void*>(0x00D0D0D0),
                                            reinterpret_cast<void*>(widget_sum_hook),
                                            nullptr, 0, &detail);
        std::printf("  unmapped-address install -> %s\n    %s\n",
                    to_string(st), detail.c_str());
        check(st == HookStatus::Unreadable, "an unmapped target address is refused");
    }

    // Verification must reject a wrong pattern before it patches anything.
    {
        Detour probe;
        const std::uint8_t wrong[] = {0xDE, 0xAD, 0xBE, 0xEF, 0xCA};
        std::string detail;
        const HookStatus st = probe.install(target, reinterpret_cast<void*>(widget_sum_hook),
                                            wrong, sizeof(wrong), &detail);
        std::printf("  wrong-bytes install -> %s\n", to_string(st));
        std::printf("    %s\n", detail.c_str());
        check(st == HookStatus::ByteMismatch, "mismatched original bytes are refused");
        check(std::memcmp(before, target, sizeof(before)) == 0,
              "a refused install left the target untouched");
    }

    Detour hook;
    std::string detail;
    const HookStatus st = hook.install(target, reinterpret_cast<void*>(widget_sum_hook),
                                       before, 8, &detail);
    std::printf("  install -> %s %s\n", to_string(st), detail.c_str());
    check(st == HookStatus::Ok, "install succeeded with verified original bytes");
    if (st != HookStatus::Ok) return;

    g_widget_orig = reinterpret_cast<WidgetSumFn>(hook.original());
    std::printf("  displaced %zu bytes, trampoline %p\n",
                hook.stolen_bytes(), hook.original());
    std::printf("  patched  %s\n",
                hex_bytes(static_cast<std::uint8_t*>(target), hook.stolen_bytes()).c_str());
    std::printf("  trampoline %s\n",
                hex_bytes(static_cast<std::uint8_t*>(hook.original()), 24).c_str());

    g_widget_hook_calls = 0;
    const int hooked = g_widget_call(&w, 3, 4);
    std::printf("  hooked call -> %d (hook ran %d time(s))\n", hooked, g_widget_hook_calls);
    check(g_widget_hook_calls == 1, "the hook body ran");
    check(hooked == 1070, "the trampoline reached the original (107 * 10)");

    // Stack discipline: if the callee-pop amount were wrong, ESP would drift by
    // that amount per call and this loop would corrupt the frame. A thousand
    // calls with a correct result at the end is the evidence.
    int accumulator = 0;
    for (int i = 0; i < 1000; ++i) accumulator += g_widget_call(&w, 1, 1);
    check(accumulator == 1020 * 1000, "1000 hooked calls kept the stack balanced");

    const HookStatus un = hook.uninstall();
    std::printf("  uninstall -> %s\n", to_string(un));
    check(un == HookStatus::Ok, "uninstall succeeded");
    check(std::memcmp(before, target, sizeof(before)) == 0,
          "original bytes were restored exactly");

    g_widget_hook_calls = 0;
    const int restored = g_widget_call(&w, 3, 4);
    std::printf("  post-uninstall call -> %d (hook ran %d time(s))\n",
                restored, g_widget_hook_calls);
    check(restored == 107, "behaviour is back to normal");
    check(g_widget_hook_calls == 0, "the hook no longer runs");
}

// ---------------------------------------------------------------------------
// Phase 3 -- relocation, proven on hand-built code
//
// Compiler output is not a reliable way to get a `call rel32` or a `jmp short`
// into the first five bytes of a function, and the point of these cases is that
// the displacement must change when the instruction moves. So the functions are
// assembled by hand into executable memory, where the prologue is exactly what
// the test needs it to be.
// ---------------------------------------------------------------------------

// Internal linkage so its address is the function itself rather than a PLT
// entry -- the relocated `call` must be seen to reach the real target.
int __attribute__((noinline, noclone)) helper_seven() {
    return 7;
}

void write_i32(std::uint8_t* p, std::int32_t v) { std::memcpy(p, &v, 4); }

// Builds a function body into executable memory and returns it. `code` is
// emitted verbatim; call sites patch their own displacements first.
std::uint8_t* make_stub(const std::vector<std::uint8_t>& code) {
    auto* p = static_cast<std::uint8_t*>(kp::platform::alloc_exec(code.size()));
    if (!p) return nullptr;
    std::memcpy(p, code.data(), code.size());
    kp::platform::commit_exec(p, code.size());
    kp::platform::flush_instruction_cache(p, code.size());
    return p;
}

using StubFn = int (*)();

int g_stub_hook_calls = 0;
StubFn g_stub_orig = nullptr;

int stub_hook() {
    ++g_stub_hook_calls;
    return g_stub_orig() + 1000;
}

// One relocation case. Every stub ends in `call helper_seven; add eax,5; ret`,
// so a correct run returns 12 and a hooked run returns 1012 -- the number is the
// same across cases, which keeps the interesting difference in the prologue.
struct RelocCase {
    const char*  name;
    const char*  form;                    // the encoding under test
    std::vector<std::uint8_t> code;
    std::size_t  call_disp_at;            // where the E8 displacement goes
    std::size_t  expect_len;              // bytes to verify before patching
    // Bytes the trampoline must begin with. This is what distinguishes "the
    // right answer" from "an answer that happened to work": a widened branch has
    // to actually BE the long encoding, not merely land somewhere plausible.
    std::vector<std::pair<std::size_t, std::uint8_t>> tramp_assert;
    std::size_t  tramp_show;
    const char*  note;
};

void run_reloc_case(const RelocCase& c) {
    std::uint8_t* stub = make_stub(c.code);
    if (!stub) { check(false, "stub allocation"); return; }

    // The call displacement can only be computed once the stub has an address.
    kp::platform::set_protection(stub, c.code.size(), kp::platform::Protect::ReadWrite);
    write_i32(stub + c.call_disp_at,
              static_cast<std::int32_t>(reinterpret_cast<std::uintptr_t>(&helper_seven) -
                                        (reinterpret_cast<std::uintptr_t>(stub) +
                                         c.call_disp_at + 4)));
    kp::platform::commit_exec(stub, c.code.size());

    auto fn = reinterpret_cast<StubFn>(stub);
    std::printf("\n  %s -- %s\n    %s\n", c.name, c.form, c.note);
    std::printf("    at %p: %s\n", stub, hex_bytes(stub, c.code.size()).c_str());

    std::string label = std::string(c.name) + ": ";
    check(fn() == 12, (label + "returns 12 before hooking").c_str());

    Detour d;
    std::string detail;
    const HookStatus st = d.install(stub, reinterpret_cast<void*>(stub_hook),
                                    c.code.data(), c.expect_len, &detail);
    std::printf("    install -> %s %s\n", to_string(st), detail.c_str());
    check(st == HookStatus::Ok, (label + "install").c_str());
    if (st != HookStatus::Ok) {
        kp::platform::free_exec(stub, c.code.size());
        return;
    }

    auto* tramp = static_cast<std::uint8_t*>(d.original());
    std::printf("    displaced %zu bytes, trampoline %s\n",
                d.stolen_bytes(), hex_bytes(tramp, c.tramp_show).c_str());
    bool encoding_ok = true;
    for (const auto& [off, byte] : c.tramp_assert) encoding_ok &= tramp[off] == byte;
    check(encoding_ok, (label + "trampoline holds the expected encoding").c_str());

    g_stub_orig = reinterpret_cast<StubFn>(tramp);
    g_stub_hook_calls = 0;
    const int r = fn();
    std::printf("    hooked -> %d\n", r);
    check(g_stub_hook_calls == 1, (label + "hook ran").c_str());
    check(r == 1012, (label + "the relocated branch reached its original target").c_str());

    d.uninstall();
    check(fn() == 12, (label + "restored").c_str());
    kp::platform::free_exec(stub, c.code.size());
}

void phase_relocation() {
    section("phase 3: relocating displaced branches");

    // Each of the five relative forms the engine claims to relocate gets its own
    // case. The sentinel `mov eax, 99; ret` in the widening cases is the point:
    // if a widened displacement lands one instruction off, the stub returns 99
    // rather than 12, which a "did it crash?" check would miss entirely.
    const RelocCase cases[] = {
        {"stub A", "E8 rel32 (call), fixed up in place",
         {
             0xE8, 0, 0, 0, 0,          // +0  call helper_seven
             0x83, 0xC0, 0x05,          // +5  add eax, 5
             0xC3,                      // +8  ret
         },
         1, 1, {{0, 0xE8}}, 10,
         "the call is the entire 5-byte displaced range"},

        {"stub B", "EB rel8 (jmp short) widened to E9 rel32",
         {
             0xEB, 0x03,                // +0  jmp -> +5
             0x90, 0x90, 0x90,          // +2  displaced range ends at +5
             0xE8, 0, 0, 0, 0,          // +5  call helper_seven
             0x83, 0xC0, 0x05,
             0xC3,
         },
         6, 5, {{0, 0xE9}}, 13,
         "target is +5, the first byte after the patch, so it is legal"},

        {"stub C", "7x rel8 (jcc short) widened to 0F 8x rel32",
         {
             0x33, 0xC0,                // +0  xor eax, eax   (sets ZF)
             0x74, 0x07,                // +2  jz -> +11
             0x90,                      // +4  displaced range ends at +5
             0xB8, 0x63, 0x00, 0x00, 0x00,  // +5  mov eax, 99  <- sentinel
             0xC3,                      // +10 ret 99 if the branch is mis-aimed
             0xE8, 0, 0, 0, 0,          // +11 call helper_seven
             0x83, 0xC0, 0x05,
             0xC3,
         },
         12, 5, {{2, 0x0F}, {3, 0x84}}, 14,
         "74 must become 0F 84; a wrong target falls through and returns 99"},

        {"stub D", "0F 8x rel32 (jcc near), fixed up in place",
         {
             0x33, 0xC0,                // +0  xor eax, eax
             0x0F, 0x84, 0x06, 0, 0, 0, // +2  jz -> +14   (already the long form)
             0xB8, 0x63, 0x00, 0x00, 0x00,  // +8  mov eax, 99  <- sentinel
             0xC3,                      // +13 ret 99
             0xE8, 0, 0, 0, 0,          // +14 call helper_seven
             0x83, 0xC0, 0x05,
             0xC3,
         },
         15, 8, {{2, 0x0F}, {3, 0x84}}, 13,
         "displacement sits at offset 2, not 1 -- a different write offset from E8/E9"},

        {"stub E", "E9 rel32 (jmp near), fixed up in place",
         {
             0xE9, 0x05, 0, 0, 0,       // +0  jmp -> +10
             0xB8, 0x63, 0x00, 0x00, 0x00,  // +5  mov eax, 99  <- sentinel
             0xE8, 0, 0, 0, 0,          // +10 call helper_seven
             0x83, 0xC0, 0x05,
             0xC3,
         },
         11, 5, {{0, 0xE9}}, 10,
         "an unfixed E9 would jump into the trampoline itself"},
    };

    for (const RelocCase& c : cases) run_reloc_case(c);

    // --- a branch back into the patch area must be refused -----------------
    //
    //   xor eax, eax           ; +0, 2 bytes
    //   jz  -4                 ; +2, 2 bytes, target is +0 -- INSIDE the patch
    //   inc eax                ; +4
    {
        std::vector<std::uint8_t> code = {
            0x33, 0xC0,
            0x74, 0xFC,
            0x40,
            0xC3,
        };
        std::uint8_t* stub = make_stub(code);
        if (!stub) { check(false, "stub allocation"); return; }
        std::printf("\n  stub F -- a displaced branch aimed back into the patch\n");
        std::printf("    at %p: %s\n", stub, hex_bytes(stub, code.size()).c_str());

        Detour d;
        std::string detail;
        const HookStatus st = d.install(stub, reinterpret_cast<void*>(stub_hook),
                                        code.data(), code.size(), &detail);
        std::printf("    install -> %s\n      %s\n", to_string(st), detail.c_str());
        check(st == HookStatus::BranchIntoPatchArea,
              "stub F: a displaced branch into the patch area is refused");
        check(std::memcmp(stub, code.data(), code.size()) == 0,
              "stub F: the refused target was left untouched");
        kp::platform::free_exec(stub, code.size());
    }
}

// ---------------------------------------------------------------------------
// Phase 4 -- the address table
// ---------------------------------------------------------------------------

void phase_table(const std::string& path) {
    section("phase 4: address table");
    AddressTable table;
    std::string error;
    if (!AddressTable::load_file(path, table, error)) {
        std::printf("  %s\n", error.c_str());
        check(false, "load address table");
        return;
    }
    std::printf("  build       %s (%s/%s)\n", table.build().c_str(),
                table.game().c_str(), table.platform_name().c_str());
    std::printf("  image_base  0x%08X\n", static_cast<unsigned>(table.image_base()));
    std::printf("  sha256      %s\n", table.expected_sha256().c_str());
    std::printf("  sites       %zu\n", table.sites().size());

    unsigned detours = 0, required = 0;
    for (const Site& s : table.sites()) {
        if (s.kind == SiteKind::Detour) ++detours;
        if (s.required) ++required;
    }
    std::printf("  detours %u, required %u, unresolved-required %zu\n",
                detours, required, table.unresolved_required().size());

    const Site* run_script = table.find("vm.run_script");
    check(run_script != nullptr, "vm.run_script is present");
    if (run_script) {
        std::printf("  vm.run_script -> 0x%08X (%s::%s, kind=%s, required=%s)\n",
                    static_cast<unsigned>(run_script->addr), run_script->cls.c_str(),
                    run_script->method.c_str(), to_string(run_script->kind),
                    run_script->required ? "yes" : "no");
        // The generator writes absolute VAs, not RVAs. Checking the address sits
        // above the image base catches the day someone starts writing offsets --
        // an RVA would land far below it. Asserting one literal address would
        // only ever hold for one build; this holds for every table, including
        // the ELF at base 0x08048000.
        check(run_script->addr > table.image_base(),
              "vm.run_script address is an absolute VA, not an RVA");
        check(run_script->kind == SiteKind::Detour, "vm.run_script is a detour site");
    }

    const Site* exec_cmd = table.find("vm.execute_command");
    check(exec_cmd != nullptr, "vm.execute_command is present");
    if (exec_cmd) {
        // The case that makes "required" and "installable" different sets.
        check(exec_cmd->required && exec_cmd->kind == SiteKind::Reference,
              "vm.execute_command is required but is a reference, not a detour");
    }

    check(table.unresolved_required().empty(),
          "every required site resolves, so this build is installable");

    // A detour request against a non-detour site must be refused rather than
    // quietly skipped.
    HookSet set;
    set.add({"vm.execute_command", reinterpret_cast<void*>(&stub_hook), {}});
    std::string install_error;
    const bool ok = set.install(table, 0, install_error);
    std::printf("  detour on a reference site -> %s\n", install_error.c_str());
    check(!ok, "detouring a reference site is refused");
    check(set.installed_count() == 0, "nothing was installed");
}

// ---------------------------------------------------------------------------

int cmd_selftest(const std::string& table_path) {
    std::printf("kp_hooktool selftest -- %u-bit build\n",
                static_cast<unsigned>(sizeof(void*) * 8));
    std::printf("main image base 0x%08X\n",
                static_cast<unsigned>(kp::platform::module_base(nullptr)));

    phase_lendis();
    phase_detour();
    phase_relocation();
    if (!table_path.empty()) phase_table(table_path);

    std::printf("\n%s: %d failure(s)\n", g_failures ? "FAILED" : "OK", g_failures);
    return g_failures ? 1 : 0;
}

int cmd_lendis(int argc, char** argv) {
    if (argc == 0) {
        // No arguments: decode the built-in vectors, which is what makes the
        // real game prologues inspectable without a copy of the binary.
        for (const Vector& v : game_vectors()) {
            if (v.va) std::printf("\n%s  (K1 %08X)\n", v.name, v.va);
            else      std::printf("\n%s\n", v.name);
            disassemble(v.bytes.data(), v.bytes.size(), v.va, true);
        }
        return 0;
    }

    std::vector<std::uint8_t> bytes;
    for (int i = 0; i < argc; ++i) {
        // Accept "8B 7C 24 14", "8b7c2414", and "0x8b,0x7c" alike -- pasting a
        // hex dump out of a disassembler should just work.
        const char* p = argv[i];
        while (*p) {
            if (*p == ' ' || *p == ',' || *p == '\t') { ++p; continue; }
            if (p[0] == '0' && (p[1] == 'x' || p[1] == 'X')) { p += 2; continue; }
            char digits[3] = {p[0], p[1], 0};
            if (!std::isxdigit(static_cast<unsigned char>(digits[0])) ||
                !std::isxdigit(static_cast<unsigned char>(digits[1]))) {
                std::fprintf(stderr, "not a hex byte pair: %s\n", p);
                return 2;
            }
            bytes.push_back(static_cast<std::uint8_t>(std::strtoul(digits, nullptr, 16)));
            p += 2;
        }
    }
    if (bytes.empty()) {
        std::fprintf(stderr, "no bytes given\n");
        return 2;
    }
    disassemble(bytes.data(), bytes.size(), 0, true);
    return 0;
}

void usage() {
    std::fprintf(stderr,
                 "kp_hooktool selftest [--table <address-table.json>]\n"
                 "kp_hooktool lendis [<hex bytes>...]\n");
}

}  // namespace

int main(int argc, char** argv) {
    // Results go to stdout and log lines to stderr. Buffered stdout would let
    // the two interleave out of order, which makes the evidence hard to read and
    // easy to misread.
    std::setvbuf(stdout, nullptr, _IONBF, 0);

    if (argc < 2) { usage(); return 2; }

    const std::string cmd = argv[1];
    if (cmd == "selftest") {
        std::string table;
        for (int i = 2; i < argc; ++i) {
            if (std::strcmp(argv[i], "--table") == 0 && i + 1 < argc) table = argv[++i];
        }
        return cmd_selftest(table);
    }
    if (cmd == "lendis") return cmd_lendis(argc - 2, argv + 2);

    usage();
    return 2;
}

// Self-test for the x86_64 detour engine (src/hooks/x64/).
//
//   kp_hooktool_x64 selftest
//
// Three tiers. All instruction bytes are synthesised here; no game bytes.
//   1. Decoder: lengths, RIP-relative/rel32 detection and refusals for
//      hand-assembled prologue instructions.
//   2. Relocation and planning: re-aimed displacements still name the same
//      absolute address at a different location; plans refuse short
//      functions, early jumps and branches into the stolen range.
//   3. Native self-hook on this x86_64 Linux host: a hand-written assembly
//      function (fixed bytes, not compiler codegen) is hooked, called
//      through, unhooked and checked byte-for-byte, twice.
#include <sys/mman.h>
#include <unistd.h>

#include <cinttypes>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <initializer_list>
#include <string>
#include <vector>

#include "hooks/x64/decode.hpp"
#include "hooks/x64/trampoline.hpp"

using namespace kp::hooks::x64;
using Bytes = std::vector<std::uint8_t>;

namespace {
int g_failures = 0, g_checks = 0;
void check(bool ok, const char* what, const std::string& extra = {}) {
    ++g_checks;
    if (!ok) {
        ++g_failures;
        std::fprintf(stderr, "FAIL %s %s\n", what, extra.c_str());
    }
}
std::string hex(const Bytes& b) {
    std::string s;
    char t[4];
    for (auto x : b) { std::snprintf(t, sizeof t, "%02x ", x); s += t; }
    return s;
}

// ---- tier 1: decoder -------------------------------------------------------
struct Case { Bytes bytes; unsigned len; Rel rel; unsigned rel_offset; };

void test_decoder() {
    const std::vector<Case> good = {
        {{0x55}, 1, Rel::None, 0},                                          // push rbp
        {{0x41, 0x57}, 2, Rel::None, 0},                                    // push r15
        {{0x48, 0x89, 0xe5}, 3, Rel::None, 0},                              // mov rbp,rsp
        {{0x48, 0x83, 0xec, 0x20}, 4, Rel::None, 0},                        // sub rsp,0x20
        {{0x48, 0x81, 0xec, 0x00, 0x01, 0x00, 0x00}, 7, Rel::None, 0},      // sub rsp,0x100
        {{0xf3, 0x0f, 0x1e, 0xfa}, 4, Rel::None, 0},                        // endbr64
        {{0x48, 0x8b, 0x05, 1, 2, 3, 4}, 7, Rel::RipDisp32, 3},             // mov rax,[rip+d]
        {{0x41, 0x8b, 0x05, 1, 2, 3, 4}, 7, Rel::RipDisp32, 3},             // REX.B: still RIP
        {{0x4c, 0x8b, 0x1d, 1, 2, 3, 4}, 7, Rel::RipDisp32, 3},             // mov r11,[rip+d]
        {{0x8b, 0x04, 0x25, 0x10, 0, 0, 0}, 7, Rel::None, 0},               // SIB base=101: absolute
        {{0x64, 0x48, 0x8b, 0x04, 0x25, 0x28, 0, 0, 0}, 9, Rel::None, 0},   // stack protector load
        {{0x80, 0x3d, 1, 2, 3, 4, 0x00}, 7, Rel::RipDisp32, 2},             // cmp byte [rip+d],0
        {{0x48, 0xc7, 0x05, 1, 2, 3, 4, 5, 6, 7, 8}, 11, Rel::RipDisp32, 3},// mov qword [rip+d],imm32
        {{0x66, 0xc7, 0x05, 1, 2, 3, 4, 5, 6}, 9, Rel::RipDisp32, 3},       // mov word [rip+d],imm16
        {{0x48, 0xb8, 1, 2, 3, 4, 5, 6, 7, 8}, 10, Rel::None, 0},           // mov rax,imm64
        {{0x66, 0xb8, 1, 2}, 4, Rel::None, 0},                              // mov ax,imm16
        {{0xb8, 1, 2, 3, 4}, 5, Rel::None, 0},                              // mov eax,imm32
        {{0x48, 0xc7, 0xc0, 1, 2, 3, 4}, 7, Rel::None, 0},                  // C7 with REX.W: imm32
        {{0xf6, 0x05, 1, 2, 3, 4, 0x80}, 7, Rel::RipDisp32, 2},             // test byte [rip+d],imm8
        {{0xf6, 0x15, 1, 2, 3, 4}, 6, Rel::RipDisp32, 2},                   // not byte [rip+d]: no imm
        {{0xf7, 0xc0, 1, 2, 3, 4}, 6, Rel::None, 0},                        // test eax,imm32
        {{0x66, 0xf7, 0xc0, 1, 2}, 5, Rel::None, 0},                        // test ax,imm16
        {{0xf7, 0xd8}, 2, Rel::None, 0},                                    // neg eax
        {{0xe8, 1, 2, 3, 4}, 5, Rel::Rel32, 1},                             // call rel32
        {{0xe9, 1, 2, 3, 4}, 5, Rel::Rel32, 1},                             // jmp rel32
        {{0x0f, 0x84, 1, 2, 3, 4}, 6, Rel::Rel32, 2},                       // je rel32
        {{0x0f, 0x1f, 0x44, 0x00, 0x00}, 5, Rel::None, 0},                  // nopl 0(rax,rax)
        {{0x66, 0x0f, 0x1f, 0x84, 0, 0, 0, 0, 0}, 9, Rel::None, 0},         // nopw 0(rax,rax,1)
        {{0x48, 0x8d, 0x3d, 1, 2, 3, 4}, 7, Rel::RipDisp32, 3},             // lea rdi,[rip+d]
        {{0xff, 0x25, 1, 2, 3, 4}, 6, Rel::RipDisp32, 2},                   // jmp [rip+d]
        {{0xff, 0x15, 1, 2, 3, 4}, 6, Rel::RipDisp32, 2},                   // call [rip+d]
        {{0x48, 0x63, 0xc7}, 3, Rel::None, 0},                              // movsxd rax,edi
        {{0x66, 0x0f, 0x3a, 0x0f, 0xc1, 0x08}, 6, Rel::None, 0},            // palignr xmm0,xmm1,8
        {{0x0f, 0x28, 0x05, 1, 2, 3, 4}, 7, Rel::RipDisp32, 3},             // movaps xmm0,[rip+d]
        {{0x48, 0x8b, 0x44, 0x24, 0x08}, 5, Rel::None, 0},                  // mov rax,[rsp+8]
        {{0x48, 0x8b, 0x84, 0x24, 0, 1, 0, 0}, 8, Rel::None, 0},            // mov rax,[rsp+0x100]
        {{0x31, 0xc0}, 2, Rel::None, 0},                                    // xor eax,eax
        {{0x6a, 0x01}, 2, Rel::None, 0},                                    // push 1
        {{0x68, 1, 2, 3, 4}, 5, Rel::None, 0},                              // push imm32
        {{0xc9}, 1, Rel::None, 0},                                          // leave
        {{0x0f, 0xb6, 0xc0}, 3, Rel::None, 0},                              // movzx eax,al
        {{0x0f, 0x44, 0xc1}, 3, Rel::None, 0},                              // cmove eax,ecx
    };
    for (const auto& c : good) {
        auto padded = c.bytes;
        padded.resize(c.bytes.size() + 8, 0x90);
        const auto i = decode(padded.data(), padded.size());
        check(i.ok() && i.len == c.len && i.rel == c.rel && i.rel_offset == c.rel_offset,
              "decoder: length/rel", hex(c.bytes) + "-> len=" + std::to_string(i.len) +
              " rel=" + std::to_string(int(i.rel)) + " off=" + std::to_string(i.rel_offset) +
              (i.refusal ? std::string(" refusal=") + i.refusal : std::string()));
        // Exactly len bytes available is enough; one fewer is not.
        check(decode(c.bytes.data(), c.bytes.size()).len == c.len, "decoder: exact-length input", hex(c.bytes));
        check(!decode(c.bytes.data(), c.bytes.size() - 1).ok(), "decoder: truncated input refuses", hex(c.bytes));
    }
    const std::vector<Bytes> refused = {
        {0x67, 0x8b, 0x00},             // address-size prefix
        {0xeb, 0x00},                   // jmp rel8
        {0x74, 0x00},                   // je rel8
        {0xe0, 0x00}, {0xe3, 0x00},     // loopne, jrcxz
        {0xc3}, {0xc2, 0, 0}, {0xcc}, {0xcd, 0x80}, {0xf4}, {0xf1}, {0xcf},
        {0xc4, 0xe2, 0x79, 0x18, 0x00}, // VEX
        {0xc5, 0xf8, 0x77},             // VEX vzeroupper
        {0x62, 0xf1, 0x7c, 0x48, 0x10, 0x00},  // EVEX
        {0x0f, 0x0b},                   // ud2
        {0xff, 0xf8},                   // FF /7
        {0xff, 0x1d, 0, 0, 0, 0},       // FF /3 far call
        {0xc7, 0xf8, 0, 0, 0, 0},       // xbegin rel32
        {0xa1, 0, 0, 0, 0, 0, 0, 0, 0}, // mov eax,moffs64
        {0xe4, 0x60},                   // in al,imm8
        {0x06}, {0x27}, {0x9a},         // invalid in 64-bit mode
        {0x40, 0x66, 0x90},             // REX not immediately before opcode
        {0x0f, 0xff},                   // unlisted two-byte opcode
    };
    for (const auto& r : refused) {
        auto padded = r;
        padded.resize(r.size() + 8, 0x90);
        const auto i = decode(padded.data(), padded.size());
        check(!i.ok() && i.refusal, "decoder: refuses", hex(r));
    }
    check(!decode(nullptr, 16).ok(), "decoder: null refuses");
    Bytes prefixes(16, 0x66);
    check(!decode(prefixes.data(), prefixes.size()).ok(), "decoder: 15-byte limit");
}

// ---- tier 2: relocation and planning --------------------------------------
void test_relocation() {
    const std::vector<Bytes> rel = {
        {0x48, 0x8b, 0x05, 0x10, 0x00, 0x00, 0x00},
        {0x80, 0x3d, 0xf0, 0xff, 0xff, 0xff, 0x01},       // negative disp, imm after disp
        {0x48, 0xc7, 0x05, 0x00, 0x10, 0x00, 0x00, 1, 2, 3, 4},
        {0xe8, 0x00, 0x01, 0x00, 0x00},
        {0x0f, 0x85, 0xfb, 0xff, 0xff, 0xff},
        {0xff, 0x25, 0x00, 0x00, 0x00, 0x00},
    };
    const std::uint64_t from = 0x0000'5555'1234'0000ull;
    for (std::int64_t delta : {std::int64_t(0x1000), -std::int64_t(0x7000'0000), std::int64_t(0x7fff'0000)}) {
        for (const auto& b : rel) {
            const auto i = decode(b.data(), b.size());
            const auto want = referent(b.data(), i, from);
            Bytes out(b.size(), 0);
            const std::uint64_t to = from + delta;
            const bool ok = relocate(b.data(), from, i, out.data(), to);
            check(ok && referent(out.data(), i, to) == want && out.size() == b.size() &&
                  std::memcmp(out.data(), b.data(), i.rel_offset) == 0 &&
                  std::memcmp(out.data() + i.rel_offset + 4, b.data() + i.rel_offset + 4,
                              b.size() - i.rel_offset - 4) == 0,
                  "relocate: same referent, other bytes untouched", hex(b));
        }
    }
    // Out of range: 3GiB away does not fit a signed 32-bit displacement.
    for (const auto& b : rel) {
        const auto i = decode(b.data(), b.size());
        Bytes out(b.size(), 0xaa);
        check(!relocate(b.data(), from, i, out.data(), from + 0xc000'0000ull) &&
              out == Bytes(b.size(), 0xaa), "relocate: out-of-range refuses, writes nothing", hex(b));
    }
    // Non-relative instructions copy verbatim.
    Bytes mov = {0x48, 0x89, 0xe5}, out(3);
    auto i = decode(mov.data(), mov.size());
    check(relocate(mov.data(), from, i, out.data(), from + 0x123456789ull) && out == mov, "relocate: plain copy");

    // Plans.
    const std::uint64_t at = 0x0000'7000'0000'0000ull;
    auto pad = [](Bytes b) { b.resize(b.size() + 32, 0xcc); return b; };
    Bytes std_prologue = pad({0x55, 0x48, 0x89, 0xe5, 0x48, 0x83, 0xec, 0x10, 0x8b, 0x05, 1, 2, 3, 4});
    auto p = plan(std_prologue.data(), std_prologue.size(), at);
    check(p.status == HookStatus::Ok && p.stolen == 14 && p.needs_near, "plan: frame + RIP load = 14, needs near");
    Bytes endbr = pad({0xf3, 0x0f, 0x1e, 0xfa, 0x55, 0x48, 0x89, 0xe5, 0x41, 0x57, 0x41, 0x56, 0x53, 0x48, 0x83, 0xec, 0x28});
    p = plan(endbr.data(), endbr.size(), at);
    check(p.status == HookStatus::Ok && p.stolen == 17 && !p.needs_near, "plan: endbr64 prologue = 17 (4+1+3+2+2+1+4), no relocation");
    Bytes short_fn = pad({0x31, 0xc0, 0xc3});
    p = plan(short_fn.data(), short_fn.size(), at);
    check(p.status == HookStatus::DecodeFailed, "plan: ret before 14 bytes refuses");
    Bytes thunk = pad({0xe9, 1, 2, 3, 4, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90});
    p = plan(thunk.data(), thunk.size(), at);
    check(p.status == HookStatus::FlowEnds, "plan: jmp before 14 bytes refuses");
    Bytes tail_jmp = pad({0x48, 0x83, 0xec, 0x08, 0x48, 0x89, 0xe5, 0x48, 0x89, 0xe5, 0x48, 0x89, 0xe5, 0xff, 0x25, 0, 0, 0, 0});
    p = plan(tail_jmp.data(), tail_jmp.size(), at);
    check(p.status == HookStatus::Ok && p.stolen == 19, "plan: jmp that ends past the window is allowed");
    // je back to offset 4 (inside the stolen window).
    Bytes loop = pad({0x55, 0x48, 0x89, 0xe5, 0x48, 0x85, 0xff, 0x0f, 0x84, 0xf7, 0xff, 0xff, 0xff, 0x90});
    p = plan(loop.data(), loop.size(), at);
    check(p.status == HookStatus::BranchIntoPatch, "plan: branch into stolen range refuses");
    Bytes vex = pad({0x55, 0xc5, 0xf8, 0x77, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90});
    p = plan(vex.data(), vex.size(), at);
    check(p.status == HookStatus::DecodeFailed && p.detail, "plan: unsupported opcode refuses with detail");
    p = plan(std_prologue.data(), 13, at);
    check(p.status == HookStatus::DecodeFailed, "plan: fewer than 14 readable bytes refuses");
}

// ---- tier 3: native self-hook ----------------------------------------------
extern "C" {
int kp_x64_global = 100;
int kp_x64_target(int);         // assembly below
extern const std::uint8_t kp_x64_target_bytes[];
}
// Fixed bytes, own page. Written in assembly so compiler flags (endbr64,
// stack protector, -O level) cannot change what the decoder sees, and on its
// own page so flipping it RW never makes the patcher's code non-executable.
//   55                push rbp
//   48 89 e5          mov rbp,rsp
//   48 83 ec 10       sub rsp,0x10
//   8b 05 <rel32>     mov eax,[rip+kp_x64_global]   <- relocated in the trampoline
//   01 f8             add eax,edi
//   c9                leave
//   c3                ret
asm(R"(
    .pushsection .text.kp_x64_hook_target,"ax",@progbits
    .p2align 12
    .globl kp_x64_target
    .globl kp_x64_target_bytes
    .type kp_x64_target,@function
kp_x64_target:
kp_x64_target_bytes:
    pushq %rbp
    movq %rsp, %rbp
    subq $0x10, %rsp
    movl kp_x64_global(%rip), %eax
    addl %edi, %eax
    leave
    ret
    .size kp_x64_target, .-kp_x64_target
    .p2align 12, 0xcc
    .popsection
)");

Detour* g_detour = nullptr;
int g_calls = 0;
extern "C" __attribute__((noinline)) int kp_x64_detour(int x) {
    ++g_calls;
    auto orig = reinterpret_cast<int (*)(int)>(g_detour->original());
    return orig(x) * 2 + 1;
}

std::string perms_of(const void* addr) {
    std::ifstream maps("/proc/self/maps");
    std::string line;
    const auto a = reinterpret_cast<std::uintptr_t>(addr);
    while (std::getline(maps, line)) {
        std::uintptr_t lo = 0, hi = 0;
        char perms[5] = {};
        if (std::sscanf(line.c_str(), "%" SCNxPTR "-%" SCNxPTR " %4s", &lo, &hi, perms) == 3 && a >= lo && a < hi)
            return perms;
    }
    return "?";
}
bool any_wx_mapping() {
    std::ifstream maps("/proc/self/maps");
    std::string line;
    while (std::getline(maps, line)) {
        char perms[5] = {};
        if (std::sscanf(line.c_str(), "%*s %4s", perms) == 1 && perms[1] == 'w' && perms[2] == 'x') return true;
    }
    return false;
}

void test_native() {
    int (*volatile fn)(int) = kp_x64_target;
    const Bytes pristine(kp_x64_target_bytes, kp_x64_target_bytes + 17);
    check(pristine[0] == 0x55 && pristine[8] == 0x8b && pristine[9] == 0x05, "native: target bytes are the asm prologue");
    check(fn(5) == 105, "native: unhooked call", std::to_string(fn(5)));
    for (int cycle = 0; cycle < 2; ++cycle) {
        Detour d;
        g_detour = &d;
        g_calls = 0;
        kp_x64_global = 100;
        const char* detail = nullptr;
        const std::uint8_t wrong[] = {0x90};
        check(d.install(reinterpret_cast<void*>(kp_x64_target), reinterpret_cast<void*>(kp_x64_detour),
                        wrong, 1, &detail) == HookStatus::ByteMismatch, "native: expected-bytes mismatch refuses");
        check(Bytes(kp_x64_target_bytes, kp_x64_target_bytes + 17) == pristine, "native: refusal wrote nothing");
        const auto st = d.install(reinterpret_cast<void*>(kp_x64_target), reinterpret_cast<void*>(kp_x64_detour),
                                  pristine.data(), 14, &detail);
        check(st == HookStatus::Ok, "native: install", std::string(to_string(st)) + " " + (detail ? detail : ""));
        if (st != HookStatus::Ok) return;
        check(d.stolen_bytes() == 14, "native: stole exactly the 14-byte frame + RIP load");
        check(kp_x64_target_bytes[0] == 0xff && kp_x64_target_bytes[1] == 0x25, "native: jmp [rip+0] written");
        check(d.install(reinterpret_cast<void*>(kp_x64_target), reinterpret_cast<void*>(kp_x64_detour)) ==
              HookStatus::AlreadyInstalled, "native: double install refuses");
        const auto tramp = reinterpret_cast<std::uintptr_t>(d.original());
        const auto tgt = reinterpret_cast<std::uintptr_t>(kp_x64_target);
        const auto dist = tramp > tgt ? tramp - tgt : tgt - tramp;
        check(dist < 0x7fff0000u, "native: trampoline within +/-2GiB of target");
        check(perms_of(kp_x64_target_bytes) == "r-xp", "native: target page back to r-x", perms_of(kp_x64_target_bytes));
        check(perms_of(d.original()) == "r-xp", "native: trampoline page sealed r-x", perms_of(d.original()));
        check(!any_wx_mapping(), "native: no writable+executable mapping in the process");
        check(fn(5) == 211 && g_calls == 1, "native: call goes through the detour", std::to_string(g_calls));
        kp_x64_global = 1000;  // the relocated RIP load must read the live global
        check(fn(5) == 2011 && g_calls == 2, "native: relocated RIP-relative load reads the same global");
        auto orig = reinterpret_cast<int (*)(int)>(d.original());
        check(orig(7) == 1007 && g_calls == 2, "native: original() bypasses the detour");
        check(d.uninstall() == HookStatus::Ok, "native: uninstall");
        check(Bytes(kp_x64_target_bytes, kp_x64_target_bytes + 17) == pristine, "native: bytes restored exactly");
        check(perms_of(kp_x64_target_bytes) == "r-xp", "native: target page r-x after uninstall");
        check(fn(5) == 1005 && g_calls == 2, "native: restored call skips the detour");
        check(d.uninstall() == HookStatus::NotInstalled, "native: double uninstall refuses");
    }
    // Uninstall refuses if someone else overwrote our patch.
    {
        Detour d;
        g_detour = &d;
        if (d.install(reinterpret_cast<void*>(kp_x64_target), reinterpret_cast<void*>(kp_x64_detour)) == HookStatus::Ok) {
            const auto page = reinterpret_cast<std::uintptr_t>(kp_x64_target_bytes) & ~std::uintptr_t(4095);
            auto* p = const_cast<std::uint8_t*>(kp_x64_target_bytes);
            mprotect(reinterpret_cast<void*>(page), 4096, PROT_READ | PROT_WRITE);
            p[13] ^= 0xff;
            mprotect(reinterpret_cast<void*>(page), 4096, PROT_READ | PROT_EXEC);
            check(d.uninstall() == HookStatus::PatchClobbered && d.installed(), "native: clobbered patch refuses uninstall");
            mprotect(reinterpret_cast<void*>(page), 4096, PROT_READ | PROT_WRITE);
            p[13] ^= 0xff;
            mprotect(reinterpret_cast<void*>(page), 4096, PROT_READ | PROT_EXEC);
            check(d.uninstall() == HookStatus::Ok, "native: uninstall after repair");
        } else {
            check(false, "native: install for clobber test");
        }
    }
    // Refusal on real memory: a function that returns inside the window.
    {
        void* page = mmap(nullptr, 4096, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        auto* code = static_cast<std::uint8_t*>(page);
        std::memset(code, 0xcc, 4096);
        const std::uint8_t short_fn[] = {0x55, 0x48, 0x89, 0xe5, 0x8b, 0x05, 0, 0, 0, 0, 0x5d, 0xc3};
        std::memcpy(code + 64, short_fn, sizeof short_fn);
        mprotect(page, 4096, PROT_READ | PROT_EXEC);
        Detour d;
        check(d.install(code + 64, reinterpret_cast<void*>(kp_x64_detour)) == HookStatus::DecodeFailed &&
              std::memcmp(code + 64, short_fn, sizeof short_fn) == 0 && !d.installed(),
              "native: short function refuses without writing");
        munmap(page, 4096);
    }
    // The patcher refuses to flip its own page.
    {
        Detour d;
        const auto st = d.install(reinterpret_cast<void*>(&plan), reinterpret_cast<void*>(kp_x64_detour));
        check(st == HookStatus::UnsafePage && !d.installed(), "native: hooking the engine's own page refuses",
              to_string(st));
    }
    check(fn(5) == 1005, "native: target intact at exit");
}
}  // namespace

int main(int argc, char** argv) {
    if (argc < 2 || std::strcmp(argv[1], "selftest") != 0) {
        std::fprintf(stderr, "usage: %s selftest\n", argv[0]);
        return 2;
    }
    test_decoder();
    test_relocation();
    test_native();
    if (g_failures) {
        std::fprintf(stderr, "%d of %d checks FAILED\n", g_failures, g_checks);
        return 1;
    }
    std::printf("PASS %d checks\n", g_checks);
    return 0;
}

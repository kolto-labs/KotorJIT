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
//      through, unhooked and checked byte-for-byte, twice. Failure paths
//      that leave a page non-executable or crash on purpose (a refused
//      mprotect, a foreign hook chained over ours) run in a forked child so
//      the parent's copy of the target stays intact.
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <unistd.h>

#include <cerrno>
#include <cinttypes>
#include <cstdlib>
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

// Immediate size under every operand-size prefix / REX combination. REX.W
// wins over 66: the immediate stays 32 bits (64 for B8+r). Expected lengths
// are capstone 5.0.7's, from kp-live-20260922/fixround-m1/table.py; they are
// literals here so the test does not re-derive them with the decoder's rule.
void test_immz_table() {
    const std::vector<Bytes> prefixes = {
        {}, {0x66}, {0x48}, {0x66, 0x48}, {0x41}, {0x66, 0x41}, {0x66, 0x49}, {0xf3, 0x48},
    };
    struct Row { Bytes op; unsigned len[8]; };
    const std::vector<Row> rows = {
        {{0x05}, {5, 4, 6, 7, 6, 5, 7, 7}},        // add eAX,immz
        {{0x0d}, {5, 4, 6, 7, 6, 5, 7, 7}},        // or
        {{0x15}, {5, 4, 6, 7, 6, 5, 7, 7}},        // adc
        {{0x1d}, {5, 4, 6, 7, 6, 5, 7, 7}},        // sbb
        {{0x25}, {5, 4, 6, 7, 6, 5, 7, 7}},        // and
        {{0x2d}, {5, 4, 6, 7, 6, 5, 7, 7}},        // sub
        {{0x35}, {5, 4, 6, 7, 6, 5, 7, 7}},        // xor
        {{0x3d}, {5, 4, 6, 7, 6, 5, 7, 7}},        // cmp
        {{0xa9}, {5, 4, 6, 7, 6, 5, 7, 7}},        // test eAX,immz
        {{0x68}, {5, 4, 6, 7, 6, 5, 7, 7}},        // push immz
        {{0x69, 0xc0}, {6, 5, 7, 8, 7, 6, 8, 8}},  // imul r,r/m,immz
        {{0x81, 0xc0}, {6, 5, 7, 8, 7, 6, 8, 8}},  // grp1 r/m,immz
        {{0xc7, 0xc0}, {6, 5, 7, 8, 7, 6, 8, 8}},  // mov r/m,immz
        {{0xf7, 0xc0}, {6, 5, 7, 8, 7, 6, 8, 8}},  // test r/m,immz (/0)
        {{0xf7, 0xc8}, {6, 5, 7, 8, 7, 6, 8, 8}},  // test r/m,immz (/1)
        {{0xb8}, {5, 4, 10, 11, 6, 5, 11, 11}},    // mov r,immz / imm64
    };
    for (const auto& r : rows) {
        for (std::size_t k = 0; k < prefixes.size(); ++k) {
            Bytes b = prefixes[k];
            b.insert(b.end(), r.op.begin(), r.op.end());
            for (std::uint8_t t = 0x11; t < 0x11 + 12; ++t) b.push_back(t);
            const auto i = decode(b.data(), b.size());
            check(i.ok() && i.len == r.len[k], "decoder: immz table",
                  hex(Bytes(b.begin(), b.begin() + r.len[k])) + "-> len=" + std::to_string(i.len) +
                  " want " + std::to_string(r.len[k]));
            check(decode(b.data(), r.len[k]).len == r.len[k], "decoder: immz table, exact length", hex(b));
            check(!decode(b.data(), r.len[k] - 1).ok(), "decoder: immz table, one byte short refuses", hex(b));
        }
    }
    // 66 after REX: the REX is ignored by the CPU. The decoder refuses instead.
    for (const Bytes& b : {Bytes{0x48, 0x66, 0x05, 1, 2, 3, 4, 5, 6}, Bytes{0x48, 0x66, 0xb8, 1, 2, 3, 4, 5, 6, 7, 8, 9}})
        check(!decode(b.data(), b.size()).ok(), "decoder: REX before 66 refuses", hex(b));
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

    // A call followed by NOP padding inside the window is the tail of a
    // noreturn wrapper; the bytes after the padding belong to the next
    // function. Each padding form GCC/Clang emit refuses.
    const Bytes call = {0xe8, 1, 2, 3, 4};
    const Bytes got_call = {0xff, 0x15, 1, 2, 3, 4};
    const std::vector<Bytes> paddings = {
        {0x90},
        {0x66, 0x90},
        {0x0f, 0x1f, 0x00},
        {0x0f, 0x1f, 0x40, 0x00},
        {0x0f, 0x1f, 0x44, 0x00, 0x00},
        {0x66, 0x0f, 0x1f, 0x44, 0x00, 0x00},
        {0x0f, 0x1f, 0x80, 0, 0, 0, 0},
        {0x66, 0x2e, 0x0f, 0x1f, 0x84, 0, 0, 0, 0, 0},
        {0x66, 0x66, 0x2e, 0x0f, 0x1f, 0x84, 0, 0, 0, 0, 0},
    };
    for (const auto& c : {call, got_call}) {
        for (const auto& pad_bytes : paddings) {
            Bytes b = c;
            b.insert(b.end(), pad_bytes.begin(), pad_bytes.end());
            b.resize(b.size() + 24, 0x90);
            p = plan(b.data(), b.size(), at);
            check(p.status == HookStatus::FlowEnds, "plan: call + NOP padding inside the window refuses",
                  hex(Bytes(b.begin(), b.begin() + c.size() + pad_bytes.size())) + to_string(p.status));
        }
    }
    // 41 90 is xchg r8d,eax, not a NOP: a call followed by it is ordinary code.
    Bytes call_xchg = pad({0xe8, 1, 2, 3, 4, 0x41, 0x90, 0x48, 0x89, 0xe5, 0x48, 0x83, 0xec, 0x10});
    p = plan(call_xchg.data(), call_xchg.size(), at);
    check(p.status == HookStatus::Ok && p.stolen == 14, "plan: call + 41 90 (xchg r8d) is not padding", to_string(p.status));
    Bytes call_code = pad({0xe8, 1, 2, 3, 4, 0x48, 0x89, 0xc7, 0x48, 0x83, 0xc4, 0x08, 0x31, 0xc0});
    p = plan(call_code.data(), call_code.size(), at);
    check(p.status == HookStatus::Ok && p.stolen == 14, "plan: call followed by real code is fine", to_string(p.status));
    Bytes call_at_end = {0x48, 0x89, 0xe5, 0x48, 0x89, 0xe5, 0x48, 0x89, 0xe5, 0xe8, 1, 2, 3, 4};
    call_at_end.resize(call_at_end.size() + 24, 0x90);
    p = plan(call_at_end.data(), call_at_end.size(), at);
    check(p.status == HookStatus::Ok && p.stolen == 14, "plan: padding after the window is not stolen", to_string(p.status));
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

// Detours for the lifetime tests. They must not read a Detour object: the
// point of those tests is that the Detour is gone.
void* g_orig = nullptr;
extern "C" __attribute__((noinline)) int kp_x64_detour_cached(int x) {
    ++g_calls;
    return reinterpret_cast<int (*)(int)>(g_orig)(x) * 2 + 1;
}
void* g_foreign_orig = nullptr;
int g_foreign_calls = 0;
extern "C" __attribute__((noinline)) int kp_x64_foreign(int x) {
    ++g_foreign_calls;
    return reinterpret_cast<int (*)(int)>(g_foreign_orig)(x) + 10000;
}

// Writes bytes into code with the real mprotect, around the engine.
void poke(const void* at, const Bytes& bytes) {
    const auto page = reinterpret_cast<std::uintptr_t>(at) & ~std::uintptr_t(4095);
    mprotect(reinterpret_cast<void*>(page), 4096, PROT_READ | PROT_WRITE);
    std::memcpy(const_cast<void*>(at), bytes.data(), bytes.size());
    mprotect(reinterpret_cast<void*>(page), 4096, PROT_READ | PROT_EXEC);
}
Bytes abs_jmp(const void* to) {
    Bytes j = {0xff, 0x25, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
    const auto a = reinterpret_cast<std::uint64_t>(to);
    std::memcpy(j.data() + 6, &a, 8);
    return j;
}
// A second hooking library chains on top of ours the usual way: it copies
// the 14 bytes it finds (our jmp [rip+0]; position-independent) into its own
// stub and points the target at its detour.
void chain_foreign() {
    void* stub = mmap(nullptr, 4096, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    std::memcpy(stub, kp_x64_target_bytes, 14);
    mprotect(stub, 4096, PROT_READ | PROT_EXEC);
    g_foreign_orig = stub;
    poke(kp_x64_target_bytes, abs_jmp(reinterpret_cast<void*>(kp_x64_foreign)));
}

// mprotect seam: refuses (EACCES, like SELinux execmod) calls that cover
// the target page, according to g_fail_mode.
enum FailMode { FailNone, FailAll, FailExecOnce, FailExecAlways, FailAfterFirst };
FailMode g_fail_mode = FailNone;
int g_target_page_calls = 0;
bool g_exec_failed_once = false;
int fake_protect(void* addr, std::size_t len, int prot) {
    const auto lo = reinterpret_cast<std::uintptr_t>(addr);
    const auto page = reinterpret_cast<std::uintptr_t>(kp_x64_target_bytes) & ~std::uintptr_t(4095);
    if (page >= lo && page < lo + len) {
        ++g_target_page_calls;
        bool fail = false;
        switch (g_fail_mode) {
            case FailNone: break;
            case FailAll: fail = true; break;
            case FailExecOnce: fail = (prot & PROT_EXEC) && !g_exec_failed_once; g_exec_failed_once |= fail; break;
            case FailExecAlways: fail = (prot & PROT_EXEC) != 0; break;
            case FailAfterFirst: fail = g_target_page_calls > 1; break;
        }
        if (fail) { errno = EACCES; return -1; }
    }
    return mprotect(addr, len, prot);
}
void arm(FailMode m) {
    g_fail_mode = m;
    g_target_page_calls = 0;
    g_exec_failed_once = false;
    kp::hooks::x64::testing::set_protect_hook(m == FailNone ? nullptr : fake_protect);
}

// Runs body in a forked child; the parent records one check for it.
template <class F>
void in_child(const char* what, F body) {
    std::fflush(stdout);
    std::fflush(stderr);
    const pid_t pid = fork();
    if (pid == 0) {
        g_failures = 0;
        g_calls = g_foreign_calls = 0;
        body();
        std::fflush(stderr);
        _exit(g_failures ? 1 : 0);
    }
    int status = 0;
    if (pid > 0) waitpid(pid, &status, 0);
    const std::string why = pid < 0 ? "fork failed"
                          : WIFSIGNALED(status) ? "child killed by signal " + std::to_string(WTERMSIG(status))
                                                : "child exit " + std::to_string(WEXITSTATUS(status));
    check(pid > 0 && WIFEXITED(status) && WEXITSTATUS(status) == 0, what, why);
}

// Calls fn(5) in a forked grandchild and returns the signal that killed it
// (0 if it returned). For pages the engine documents as left non-executable.
int call_dies_with(int (*fn)(int)) {
    std::fflush(stderr);
    const pid_t pid = fork();
    if (pid == 0) {
        (void)fn(5);
        _exit(0);
    }
    int status = 0;
    if (pid > 0) waitpid(pid, &status, 0);
    return pid > 0 && WIFSIGNALED(status) ? WTERMSIG(status) : 0;
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
// Bytes in anonymous mappings: a trampoline page shows up here.
unsigned long anon_bytes() {
    std::ifstream maps("/proc/self/maps");
    std::string line;
    unsigned long total = 0;
    while (std::getline(maps, line)) {
        unsigned long lo = 0, hi = 0, inode = 0;
        int end = 0;
        if (std::sscanf(line.c_str(), "%lx-%lx %*s %*s %*s %lu %n", &lo, &hi, &inode, &end) >= 3 && inode == 0 &&
            line.find_first_not_of(' ', std::size_t(end)) == std::string::npos)
            total += hi - lo;
    }
    return total;
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

// ---- tier 3b: failure paths, each in a forked child ------------------------
void test_failure_paths() {
    int (*volatile fn)(int) = kp_x64_target;
    void* const target = reinterpret_cast<void*>(kp_x64_target);
    void* const cached = reinterpret_cast<void*>(kp_x64_detour_cached);
    const Bytes pristine(kp_x64_target_bytes, kp_x64_target_bytes + 17);
    auto bytes_now = [] { return Bytes(kp_x64_target_bytes, kp_x64_target_bytes + 17); };
    auto patched = [] { return kp_x64_target_bytes[0] == 0xff && kp_x64_target_bytes[1] == 0x25; };

    // I2. A foreign hook chains over ours, uninstall refuses, the Detour is
    // destroyed. The trampoline must stay mapped: the chain still reaches it.
    in_child("I2: destructor after PatchClobbered keeps the trampoline", [&] {
        kp_x64_global = 100;
        const auto leaks = leaked_trampoline_pages();
        void* tramp = nullptr;
        {
            Detour d;
            check(d.install(target, cached) == HookStatus::Ok, "I2 dtor: install");
            g_orig = tramp = d.original();
            chain_foreign();
            check(d.uninstall() == HookStatus::PatchClobbered && d.installed(), "I2 dtor: uninstall refuses");
        }
        check(leaked_trampoline_pages() == leaks + 1, "I2 dtor: trampoline recorded as leaked");
        check(perms_of(tramp) == "r-xp", "I2 dtor: trampoline still mapped r-x", perms_of(tramp));
        check(fn(5) == 10211 && g_calls == 1 && g_foreign_calls == 1, "I2 dtor: chained call runs",
              std::to_string(g_calls));
    });
    in_child("I2: move-assign after PatchClobbered keeps the trampoline", [&] {
        kp_x64_global = 100;
        const auto leaks = leaked_trampoline_pages();
        Detour d;
        check(d.install(target, cached) == HookStatus::Ok, "I2 move: install");
        void* tramp = g_orig = d.original();
        chain_foreign();
        d = Detour();
        check(!d.installed() && leaked_trampoline_pages() == leaks + 1, "I2 move: trampoline recorded as leaked");
        check(perms_of(tramp) == "r-xp", "I2 move: trampoline still mapped r-x", perms_of(tramp));
        check(fn(5) == 10211 && g_calls == 1 && g_foreign_calls == 1, "I2 move: chained call runs");
    });
    in_child("I2: destructor after ProtectFailed keeps the trampoline", [&] {
        kp_x64_global = 100;
        const auto leaks = leaked_trampoline_pages();
        void* tramp = nullptr;
        {
            Detour d;
            check(d.install(target, cached) == HookStatus::Ok, "I2 protect: install");
            g_orig = tramp = d.original();
            arm(FailAll);
            const char* detail = nullptr;
            check(d.uninstall(&detail) == HookStatus::ProtectFailed && d.installed() && patched(),
                  "I2 protect: uninstall refused, patch still in place", detail ? detail : "");
        }  // destructor runs with the seam still refusing
        arm(FailNone);
        check(leaked_trampoline_pages() == leaks + 1, "I2 protect: trampoline recorded as leaked");
        check(perms_of(tramp) == "r-xp", "I2 protect: trampoline still mapped r-x", perms_of(tramp));
        const int r = fn(5);
        check(r == 211 && g_calls == 1, "I2 protect: patched call still runs", std::to_string(r));
    });

    // I3. The kernel refuses the protection restore after the write.
    in_child("I3: install, restore refused once: rolled back and resealed", [&] {
        kp_x64_global = 100;
        Detour d;
        arm(FailExecOnce);
        const char* detail = nullptr;
        const auto st = d.install(target, cached, nullptr, 0, &detail);
        arm(FailNone);
        check(st == HookStatus::ProtectFailed && !d.installed(), "I3 install once: ProtectFailed, not installed",
              std::string(to_string(st)) + " " + (detail ? detail : ""));
        check(detail && std::strstr(detail, "EACCES"), "m9: the refusal's EACCES reaches the detail",
              detail ? detail : "");
        check(bytes_now() == pristine, "I3 install once: original bytes rolled back", hex(bytes_now()));
        check(perms_of(kp_x64_target_bytes) == "r-xp", "I3 install once: page resealed r-x",
              perms_of(kp_x64_target_bytes));
        check(fn(5) == 105 && g_calls == 0, "I3 install once: target runs unhooked");
    });
    in_child("I3: install, restore always refused: original bytes, page left RW", [&] {
        Detour d;
        arm(FailExecAlways);
        const char* detail = nullptr;
        const auto st = d.install(target, cached, nullptr, 0, &detail);
        arm(FailNone);
        check(st == HookStatus::ProtectFailed && !d.installed() && detail, "I3 install always: ProtectFailed",
              std::string(to_string(st)) + " " + (detail ? detail : ""));
        check(bytes_now() == pristine, "I3 install always: original bytes rolled back", hex(bytes_now()));
        // Documented: the page stays non-executable. Not called.
        check(perms_of(kp_x64_target_bytes) == "rw-p", "I3 install always: page left rw-",
              perms_of(kp_x64_target_bytes));
        // m8. A retry on the dead page refuses instead of recording rw- as
        // the protection to restore.
        const char* retry_detail = nullptr;
        const auto retry = d.install(target, cached, nullptr, 0, &retry_detail);
        check(retry == HookStatus::NotExecutable && !d.installed(), "m8: retry on the dead page refuses",
              std::string(to_string(retry)) + " " + (retry_detail ? retry_detail : ""));
        check(bytes_now() == pristine && perms_of(kp_x64_target_bytes) == "rw-p",
              "m8: retry wrote nothing and left the page as it was", perms_of(kp_x64_target_bytes));
    });
    in_child("I3: install, rollback also refused: patch live, still installed", [&] {
        kp_x64_global = 100;
        const auto leaks = leaked_trampoline_pages();
        Detour d;
        arm(FailAfterFirst);
        const char* detail = nullptr;
        const auto st = d.install(target, cached, nullptr, 0, &detail);
        arm(FailNone);
        check(st == HookStatus::ProtectFailed && d.installed() && patched(), "I3 stuck: ProtectFailed but installed",
              std::string(to_string(st)) + " " + (detail ? detail : ""));
        check(d.original() && perms_of(d.original()) == "r-xp", "I3 stuck: trampoline kept");
        // m7. The patch is live but the page is RW, not executable, until
        // uninstall succeeds: calling the target faults.
        check(perms_of(kp_x64_target_bytes) == "rw-p", "m7: stuck install leaves the page rw-",
              perms_of(kp_x64_target_bytes));
        check(detail && std::strstr(detail, "not executable"), "m7: stuck install detail says not executable",
              detail ? detail : "");
        const int sig = call_dies_with(kp_x64_target);
        check(sig == SIGSEGV, "m7: calling the target in that state faults", std::to_string(sig));
        g_orig = d.original();
        check(d.uninstall() == HookStatus::Ok && !d.installed(), "I3 stuck: uninstall recovers");
        check(bytes_now() == pristine, "I3 stuck: original bytes back", hex(bytes_now()));
        check(perms_of(kp_x64_target_bytes) == "r-xp", "I3 stuck: page back to the recorded r-x",
              perms_of(kp_x64_target_bytes));
        check(fn(5) == 105 && leaked_trampoline_pages() == leaks, "I3 stuck: target runs unhooked");
    });
    in_child("I3: uninstall, restore refused once: patch rolled back, still installed", [&] {
        kp_x64_global = 100;
        Detour d;
        check(d.install(target, cached) == HookStatus::Ok, "I3 uninstall once: install");
        g_orig = d.original();
        arm(FailExecOnce);
        const char* detail = nullptr;
        const auto st = d.uninstall(&detail);
        arm(FailNone);
        check(st == HookStatus::ProtectFailed && d.installed() && patched(), "I3 uninstall once: refused, patch kept",
              std::string(to_string(st)) + " " + (detail ? detail : ""));
        check(perms_of(kp_x64_target_bytes) == "r-xp", "I3 uninstall once: page resealed r-x");
        check(fn(5) == 211 && g_calls == 1, "I3 uninstall once: hooked call still runs");
        check(d.uninstall() == HookStatus::Ok && bytes_now() == pristine, "I3 uninstall once: retry succeeds");
        check(fn(5) == 105, "I3 uninstall once: unhooked");
    });
    in_child("I3: uninstall, restore always refused: patch rolled back, trampoline leaked on destroy", [&] {
        const auto leaks = leaked_trampoline_pages();
        void* tramp = nullptr;
        {
            Detour d;
            check(d.install(target, cached) == HookStatus::Ok, "I3 uninstall always: install");
            tramp = d.original();
            arm(FailExecAlways);
            check(d.uninstall() == HookStatus::ProtectFailed && d.installed() && patched(),
                  "I3 uninstall always: refused, patch bytes kept");
            check(perms_of(kp_x64_target_bytes) == "rw-p", "I3 uninstall always: page left rw-",
                  perms_of(kp_x64_target_bytes));
        }
        arm(FailNone);
        check(leaked_trampoline_pages() == leaks + 1 && perms_of(tramp) == "r-xp",
              "I3 uninstall always: destroy leaks the trampoline", perms_of(tramp));
    });

    // m7. Uninstall whose restore and rollback are both refused: the
    // original bytes are back, so the Detour is uninstalled, but the page
    // stays RW and not executable. Nothing will put it back.
    in_child("m7: uninstall, rollback also refused: uninstalled, page left RW", [&] {
        const auto leaks = leaked_trampoline_pages();
        Detour d;
        check(d.install(target, cached) == HookStatus::Ok, "m7 uninstall: install");
        g_orig = d.original();
        arm(FailAfterFirst);
        const char* detail = nullptr;
        const auto st = d.uninstall(&detail);
        arm(FailNone);
        check(st == HookStatus::ProtectFailed && !d.installed() && d.original() == nullptr,
              "m7 uninstall: ProtectFailed, uninstalled", std::string(to_string(st)) + " " + (detail ? detail : ""));
        check(bytes_now() == pristine, "m7 uninstall: original bytes back", hex(bytes_now()));
        check(perms_of(kp_x64_target_bytes) == "rw-p", "m7 uninstall: page left rw-", perms_of(kp_x64_target_bytes));
        check(detail && std::strstr(detail, "not executable"), "m7 uninstall: detail says not executable",
              detail ? detail : "");
        check(leaked_trampoline_pages() == leaks, "m7 uninstall: trampoline released, not leaked");
        const int sig = call_dies_with(kp_x64_target);
        check(sig == SIGSEGV, "m7 uninstall: calling the target faults", std::to_string(sig));
    });

    // m8. A target page that is not executable now is not code, or was left
    // dead by an earlier failed write. install refuses before it maps a
    // trampoline or changes any protection.
    in_child("m8: install on a non-executable page refuses", [&] {
        const std::uint8_t fn_bytes[] = {0x55, 0x48, 0x89, 0xe5, 0x48, 0x83, 0xec, 0x10,
                                         0x48, 0x89, 0x7d, 0xf8, 0x90, 0x90, 0xc9, 0xc3};
        for (const int prot : {PROT_READ, PROT_READ | PROT_WRITE}) {
            void* page = mmap(nullptr, 4096, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
            auto* code = static_cast<std::uint8_t*>(page);
            std::memset(code, 0xcc, 4096);
            std::memcpy(code + 64, fn_bytes, sizeof fn_bytes);
            mprotect(page, 4096, prot);
            const auto before = perms_of(code);
            const auto anon = anon_bytes();
            {
                Detour d;
                const char* detail = nullptr;
                const auto st = d.install(code + 64, cached, nullptr, 0, &detail);
                check(st == HookStatus::NotExecutable && !d.installed(), "m8: non-executable page refuses",
                      before + " " + to_string(st) + " " + (detail ? detail : ""));
                check(std::memcmp(code + 64, fn_bytes, sizeof fn_bytes) == 0 && perms_of(code) == before &&
                      anon_bytes() == anon, "m8: refusal wrote nothing, changed no protection, mapped nothing",
                      before + " -> " + perms_of(code));
            }
            munmap(page, 4096);
        }
        // Only the second page of a straddling patch is not executable.
        void* map = mmap(nullptr, 8192, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        auto* base = static_cast<std::uint8_t*>(map);
        std::memset(base, 0xcc, 8192);
        std::uint8_t* code = base + 4096 - 6;
        std::memcpy(code, fn_bytes, sizeof fn_bytes);
        mprotect(base, 4096, PROT_READ | PROT_EXEC);
        mprotect(base + 4096, 4096, PROT_READ);
        Detour d;
        const auto st = d.install(code, cached);
        check(st == HookStatus::NotExecutable && !d.installed(), "m8 split: r-x | r-- refuses", to_string(st));
        check(std::memcmp(code, fn_bytes, sizeof fn_bytes) == 0 && perms_of(base) == "r-xp" &&
              perms_of(base + 4096) == "r--p", "m8 split: nothing written or changed",
              perms_of(base) + " " + perms_of(base + 4096));
    });
    // m10. install reads the target (the expected-bytes compare, plan()).
    // A target on an unmapped or PROT_NONE page, or whose patch window runs
    // into one, must refuse before any read instead of faulting.
    const std::uint8_t fn16[] = {0x55, 0x48, 0x89, 0xe5, 0x48, 0x83, 0xec, 0x10,
                                 0x48, 0x89, 0x7d, 0xf8, 0x90, 0x90, 0xc9, 0xc3};
    in_child("m10: install on a PROT_NONE page refuses", [&] {
        void* page = mmap(nullptr, 4096, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        auto* code = static_cast<std::uint8_t*>(page);
        std::memcpy(code + 64, fn16, sizeof fn16);
        mprotect(page, 4096, PROT_NONE);
        const auto anon = anon_bytes();
        for (const bool with_expect : {false, true}) {
            Detour d;
            const char* detail = nullptr;
            const auto st = with_expect ? d.install(code + 64, cached, fn16, sizeof fn16, &detail)
                                        : d.install(code + 64, cached, nullptr, 0, &detail);
            check(st == HookStatus::Unreadable && !d.installed(), "m10: PROT_NONE target refuses",
                  std::string(with_expect ? "expect " : "") + to_string(st) + " " + (detail ? detail : ""));
        }
        check(perms_of(code) == "---p" && anon_bytes() == anon, "m10: nothing changed or mapped", perms_of(code));
        mprotect(page, 4096, PROT_READ);
        check(std::memcmp(code + 64, fn16, sizeof fn16) == 0, "m10: bytes untouched");
    });
    in_child("m10: install on an unmapped address refuses", [&] {
        void* page = mmap(nullptr, 4096, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        munmap(page, 4096);
        Detour d;
        const char* detail = nullptr;
        const auto st = d.install(static_cast<std::uint8_t*>(page) + 64, cached, nullptr, 0, &detail);
        check(st == HookStatus::Unreadable && !d.installed(), "m10: unmapped target refuses",
              std::string(to_string(st)) + " " + (detail ? detail : ""));
        check(perms_of(page) == "?", "m10: still unmapped", perms_of(page));
    });
    in_child("m10: patch window crossing into a PROT_NONE page refuses", [&] {
        void* map = mmap(nullptr, 8192, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        auto* base = static_cast<std::uint8_t*>(map);
        std::memset(base, 0xcc, 8192);
        std::uint8_t* code = base + 4096 - 6;  // 6 bytes readable, the rest behind PROT_NONE
        std::memcpy(code, fn16, sizeof fn16);
        mprotect(base, 4096, PROT_READ | PROT_EXEC);
        mprotect(base + 4096, 4096, PROT_NONE);
        const auto anon = anon_bytes();
        for (const bool with_expect : {false, true}) {
            Detour d;
            const char* detail = nullptr;
            const auto st = with_expect ? d.install(code, cached, fn16, sizeof fn16, &detail)
                                        : d.install(code, cached, nullptr, 0, &detail);
            check(st == HookStatus::Unreadable && !d.installed(), "m10 split: r-x | --- refuses",
                  std::string(with_expect ? "expect " : "") + to_string(st) + " " + (detail ? detail : ""));
        }
        check(perms_of(base) == "r-xp" && perms_of(base + 4096) == "---p" && anon_bytes() == anon,
              "m10 split: nothing changed or mapped", perms_of(base) + " " + perms_of(base + 4096));
        check(std::memcmp(code, fn16, 6) == 0, "m10 split: bytes untouched");
    });
    in_child("m10: stolen bytes that end before a PROT_NONE guard page still install", [&] {
        void* map = mmap(nullptr, 8192, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        auto* base = static_cast<std::uint8_t*>(map);
        std::memset(base, 0xcc, 8192);
        std::uint8_t* code = base + 4096 - sizeof fn16;  // stolen = 14, leave+ret end the page
        std::memcpy(code, fn16, sizeof fn16);
        mprotect(base, 4096, PROT_READ | PROT_EXEC);
        mprotect(base + 4096, 4096, PROT_NONE);
        Detour d;
        const char* detail = nullptr;
        const auto st = d.install(code, cached, fn16, sizeof fn16, &detail);
        check(st == HookStatus::Ok && d.stolen_bytes() == 14, "m10 guard: install next to a guard page",
              std::string(to_string(st)) + " " + (detail ? detail : ""));
        if (st != HookStatus::Ok) return;
        g_orig = d.original();
        reinterpret_cast<int (*)(int)>(code)(5);
        check(g_calls == 1, "m10 guard: call goes through the detour");
        check(d.uninstall() == HookStatus::Ok && std::memcmp(code, fn16, sizeof fn16) == 0 &&
              perms_of(base) == "r-xp" && perms_of(base + 4096) == "---p", "m10 guard: uninstall restores",
              perms_of(base) + " " + perms_of(base + 4096));
    });
    // m10/grill#2. A genuinely over-15-byte instruction sits entirely on
    // readable, executable bytes, but the patch window still gets cut short
    // by a guard page further along (the window is capped at kMaxStolen, not
    // at the instruction's own length). decode() must say the instruction is
    // too long on its own terms; it must not let the unrelated guard page
    // relabel that DecodeFailed as Unreadable. 10x 66 (operand-size prefix)
    // + 8b (mov) + ModRM 0x84 (mod=2, rm=4: SIB + disp32) + SIB 0x00 + disp32
    // = 17 bytes, all inside the first 20 readable bytes.
    in_child("grill#2: an over-length instruction inside the readable window is DecodeFailed, not Unreadable", [&] {
        const std::uint8_t insn17[] = {0x66, 0x66, 0x66, 0x66, 0x66, 0x66, 0x66, 0x66, 0x66, 0x66,
                                       0x8b, 0x84, 0x00, 0x00, 0x00, 0x00, 0x00};
        void* map = mmap(nullptr, 8192, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        auto* base = static_cast<std::uint8_t*>(map);
        std::memset(base, 0xcc, 8192);
        std::uint8_t* code = base + 4096 - 20;  // 20 bytes readable, then a PROT_NONE guard page
        std::memcpy(code, insn17, sizeof insn17);
        mprotect(base, 4096, PROT_READ | PROT_EXEC);
        mprotect(base + 4096, 4096, PROT_NONE);
        Detour d;
        const char* detail = nullptr;
        const auto st = d.install(code, cached, nullptr, 0, &detail);
        check(st == HookStatus::DecodeFailed, "grill#2: over-length instruction is DecodeFailed, not Unreadable",
              std::string(to_string(st)) + " " + (detail ? detail : ""));
        check(detail && std::strstr(detail, "15 bytes") != nullptr,
              "grill#2: detail names the 15-byte instruction cap, not the guard page",
              detail ? detail : "(null)");
        check(!d.installed(), "grill#2: nothing installed");
    });
    // m10/grill#2, REX path. The review also named decode.cpp's old :132 (the REX path, now :144)
    // alongside :229: 14x 0x66 (operand-size prefix, any order/count) then 0x48 (REX.W) burns the
    // whole 15-byte budget in prefixes before an opcode is even read, so `need(1)` fails there too.
    // Same guard-page layout as the case above; only the byte pattern (and which site inside
    // decode() refuses) differs.
    in_child("grill#2 REX path: prefixes + REX alone overrun 15 bytes -> DecodeFailed, not Unreadable", [&] {
        std::uint8_t insn15[15];
        std::memset(insn15, 0x66, 14);
        insn15[14] = 0x48;  // REX.W, no opcode follows within the 15-byte cap
        void* map = mmap(nullptr, 8192, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        auto* base = static_cast<std::uint8_t*>(map);
        std::memset(base, 0xcc, 8192);
        std::uint8_t* code = base + 4096 - 20;  // 20 bytes readable, then a PROT_NONE guard page
        std::memcpy(code, insn15, sizeof insn15);
        mprotect(base, 4096, PROT_READ | PROT_EXEC);
        mprotect(base + 4096, 4096, PROT_NONE);
        Detour d;
        const char* detail = nullptr;
        const auto st = d.install(code, cached, nullptr, 0, &detail);
        check(st == HookStatus::DecodeFailed, "grill#2 REX: over-length prefixes+REX is DecodeFailed, not Unreadable",
              std::string(to_string(st)) + " " + (detail ? detail : ""));
        check(detail && std::strstr(detail, "15 bytes") != nullptr,
              "grill#2 REX: detail names the 15-byte instruction cap, not the guard page",
              detail ? detail : "(null)");
        check(!d.installed(), "grill#2 REX: nothing installed");
    });
    // m4. The recorded protection comes back, not a hard-coded r-x. An rwx
    // page (a JIT arena) is put back rwx; the engine never creates one. In a
    // child, so the W+X mapping never exists in the parent.
    in_child("m4: rwx page and r-x | rwx split keep their protection", [&] {
        const std::uint8_t fn_bytes[] = {0x55, 0x48, 0x89, 0xe5, 0x48, 0x83, 0xec, 0x10,
                                         0x48, 0x89, 0x7d, 0xf8, 0x90, 0x90, 0xc9, 0xc3};
        void* page = mmap(nullptr, 4096, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        auto* code = static_cast<std::uint8_t*>(page);
        std::memset(code, 0xcc, 4096);
        std::memcpy(code + 64, fn_bytes, sizeof fn_bytes);
        const int rwx = mprotect(page, 4096, PROT_READ | PROT_WRITE | PROT_EXEC);
        check(rwx == 0, "m4: this host allows an rwx page (SELinux execmem?)", std::to_string(errno));
        if (rwx != 0) return;
        {
            Detour d;
            check(d.install(code + 64, cached) == HookStatus::Ok, "m4: install on an rwx page");
            check(perms_of(code) == "rwxp", "m4: rwx page restored as rwx", perms_of(code));
            check(d.uninstall() == HookStatus::Ok && std::memcmp(code + 64, fn_bytes, sizeof fn_bytes) == 0,
                  "m4: uninstall restores bytes");
            check(perms_of(code) == "rwxp", "m4: rwx after uninstall", perms_of(code));
        }
        munmap(page, 4096);
        // Each page of a straddling patch gets its own protection back.
        void* map = mmap(nullptr, 8192, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        auto* base = static_cast<std::uint8_t*>(map);
        std::memset(base, 0xcc, 8192);
        std::uint8_t* split = base + 4096 - 6;
        std::memcpy(split, fn_bytes, sizeof fn_bytes);
        mprotect(base, 4096, PROT_READ | PROT_EXEC);
        mprotect(base + 4096, 4096, PROT_READ | PROT_WRITE | PROT_EXEC);
        Detour d;
        check(d.install(split, cached) == HookStatus::Ok && d.stolen_bytes() == 14,
              "m4 split: install across two mappings");
        check(perms_of(base) == "r-xp" && perms_of(base + 4096) == "rwxp", "m4 split: r-x | rwx after install",
              perms_of(base) + " " + perms_of(base + 4096));
        check(d.uninstall() == HookStatus::Ok && std::memcmp(split, fn_bytes, sizeof fn_bytes) == 0,
              "m4 split: uninstall restores bytes");
        check(perms_of(base) == "r-xp" && perms_of(base + 4096) == "rwxp", "m4 split: r-x | rwx after uninstall",
              perms_of(base) + " " + perms_of(base + 4096));
    });
    // m6. A real kernel refusing the RW flip halfway through a two-mapping
    // span: page 0 is a private anonymous r-x page, page 1 a MAP_SHARED page
    // of a file opened O_RDONLY, which can never be made writable. mprotect
    // works mapping by mapping, so it changes page 0 to RW and then refuses
    // page 1. The engine must put page 0 back before it reports the refusal.
    in_child("m6: real two-mapping RW flip refused: page 0 resealed, nothing written", [&] {
        const std::size_t pg = 4096;
        // fn(x) = x + 100, 17 bytes; 15 are stolen. It crosses into page 1
        // after 6 bytes.
        const std::uint8_t fn_bytes[] = {0x55, 0x48, 0x89, 0xe5, 0x89, 0xf8, 0x05, 0x64, 0, 0, 0,
                                         0x0f, 0x1f, 0x40, 0x00, 0x5d, 0xc3};
        const std::size_t head = 6;
        auto* base = static_cast<std::uint8_t*>(
            mmap(nullptr, 2 * pg, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0));
        std::vector<std::uint8_t> tail(pg, 0xcc);
        std::memcpy(tail.data(), fn_bytes + head, sizeof fn_bytes - head);
        // /tmp may be mounted noexec; the directory holding this binary is not.
        std::string exe_dir;
        {
            char buf[4096] = {};
            const auto n = readlink("/proc/self/exe", buf, sizeof buf - 1);
            exe_dir = n > 0 ? std::string(buf, std::size_t(n)) : std::string();
            exe_dir = exe_dir.substr(0, exe_dir.rfind('/'));
        }
        const char* tmpdir = std::getenv("TMPDIR");
        std::string tried;
        std::uint8_t* p1 = nullptr;
        for (const std::string& dir : {std::string(tmpdir ? tmpdir : ""), std::string("/tmp"), exe_dir}) {
            if (dir.empty()) continue;
            std::string path = dir + "/kp_hooktool_x64.XXXXXX";
            const int wfd = mkstemp(path.data());
            if (wfd < 0) { tried += dir + ": mkstemp failed; "; continue; }
            const bool wrote = write(wfd, tail.data(), pg) == static_cast<ssize_t>(pg);
            close(wfd);
            const int fd = open(path.c_str(), O_RDONLY | O_CLOEXEC);
            unlink(path.c_str());
            if (!wrote || fd < 0) { tried += dir + ": write/open failed; "; if (fd >= 0) close(fd); continue; }
            void* m = mmap(base + pg, pg, PROT_READ | PROT_EXEC, MAP_SHARED | MAP_FIXED, fd, 0);
            close(fd);
            if (m == MAP_FAILED) { tried += dir + ": mmap r-x failed (noexec?); "; continue; }
            p1 = static_cast<std::uint8_t*>(m);
            break;
        }
        check(p1 == base + pg, "m6: shared read-only r-x file page mapped", tried);
        if (p1 != base + pg) return;
        auto* p0 = static_cast<std::uint8_t*>(
            mmap(base, pg, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0));
        std::memset(p0, 0xcc, pg);
        std::memcpy(p0 + pg - head, fn_bytes, head);
        mprotect(p0, pg, PROT_READ | PROT_EXEC);
        auto* code = base + pg - head;
        int (*volatile f)(int) = reinterpret_cast<int (*)(int)>(code);
        check(f(5) == 105, "m6: unhooked call");
        // Precondition: this kernel really does apply the change halfway.
        // If it refused all at once, the test below would prove nothing.
        const int raw = mprotect(base, 2 * pg, PROT_READ | PROT_WRITE);
        check(raw != 0 && perms_of(base) == "rw-p" && perms_of(p1) == "r-xs",
              "m6: kernel mprotect is partial across the two mappings",
              std::to_string(raw) + " " + perms_of(base) + " " + perms_of(p1));
        mprotect(base, pg, PROT_READ | PROT_EXEC);
        Detour d;
        const char* detail = nullptr;
        const auto st = d.install(code, cached, nullptr, 0, &detail);
        check(st == HookStatus::ProtectFailed && !d.installed(), "m6: install refuses",
              std::string(to_string(st)) + " " + (detail ? detail : ""));
        check(perms_of(base) == "r-xp" && perms_of(p1) == "r-xs", "m6: page 0 resealed r-x, page 1 untouched",
              perms_of(base) + " " + perms_of(p1));
        check(std::memcmp(code, fn_bytes, sizeof fn_bytes) == 0, "m6: nothing written");
        check(f(5) == 105 && g_calls == 0, "m6: target still runs unhooked");
    });

    // m4. The own-page guard covers libc's mprotect, which runs while the
    // target page is writable.
    in_child("m4: hooking libc mprotect refuses", [&] {
        Detour d;
        const auto st = d.install(reinterpret_cast<void*>(&::mprotect), cached);
        check(st == HookStatus::UnsafePage && !d.installed(), "m4: mprotect's page refuses", to_string(st));
    });
}
}  // namespace

int main(int argc, char** argv) {
    if (argc < 2 || std::strcmp(argv[1], "selftest") != 0) {
        std::fprintf(stderr, "usage: %s selftest\n", argv[0]);
        return 2;
    }
    test_decoder();
    test_immz_table();
    test_relocation();
    test_native();
    test_failure_paths();
    if (g_failures) {
        std::fprintf(stderr, "%d of %d checks FAILED\n", g_failures, g_checks);
        return 1;
    }
    std::printf("PASS %d checks\n", g_checks);
    return 0;
}

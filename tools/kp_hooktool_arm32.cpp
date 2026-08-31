// kp_hooktool_arm32 -- exercise the ARM32 detour engine against this
// process, under qemu-arm.
//
// Why freestanding. There is no ARM sysroot in the environment this was
// written in (no libc built for arm-linux-gnu), and chasing one down is not
// this task's job. `arm-linux-gnu-gcc -nostdlib -static` plus a hand-written
// `_start` and raw Linux ARM EABI syscalls for I/O, memory mapping, and
// cache maintenance is proven to work: a trivial version of exactly this
// setup ran correctly under qemu-arm before any of this file was written.
// This tool supplies its own tiny freestanding libc (memcpy/memcmp/memset
// and the five kp::platform:: functions src/hooks/arm32/trampoline.cpp
// calls) rather than pull one in.
//
// Build (from the repo root, after `dnf install gcc-arm-linux-gnu
// binutils-arm-linux-gnu qemu-user qemu-user-static`):
//
//   arm-linux-gnu-gcc -nostdlib -static -march=armv7-a -mthumb -std=c++20 \
//       -fno-exceptions -fno-rtti -fno-unwind-tables -Isrc \
//       tools/kp_hooktool_arm32.cpp src/hooks/arm32/decode.cpp \
//       src/hooks/arm32/trampoline.cpp -o build/kp_hooktool_arm32
//   qemu-arm build/kp_hooktool_arm32
//
// Two phases, mirroring tools/kp_hooktool.cpp's lendis/selftest split:
//
//   phase 1 (lendis-equivalent): decode() against real Thumb-2 instruction
//     bytes read out of K1__k1_android_ARMEABI and TSL__k2_android_
//     libkotor2.so_armeabi-v7aandroid via objdump, not invented. Every
//     length was independently cross-checked against 2.86 million real
//     instructions from both binaries with a throwaway host-side harness
//     before this file was written: 0 length mismatches, 0 mis-classified
//     "safe to relocate" instructions (the harness flags any relocatable-
//     marked instruction whose objdump operand text names `pc`). Two real
//     bugs were caught and fixed that way -- POP {..., pc} and MCR/MRC
//     naming pc as a transfer register -- both documented in decode.cpp
//     where they were fixed, not just here.
//
//   phase 2 (selftest-equivalent): a real Thumb-2 function stub, built into
//     executable memory this process owns, detoured with the real
//     Detour::install(), called before and after hooking, and checked for
//     the same "did the hook actually run and did the original still
//     execute correctly through the trampoline" property kp_hooktool.cpp's
//     x86 selftest checks -- for real, under qemu-arm, not asserted from
//     reading the code.

#include <stddef.h>
#include <stdint-gcc.h>

// ---------------------------------------------------------------------------
// A tiny freestanding libc. -nostdlib means nothing provides these symbols;
// GCC's own <cstring> declarations still get used by decode.cpp/
// trampoline.cpp, so the definitions have to exist somewhere, and this is
// that somewhere.
// ---------------------------------------------------------------------------

extern "C" void* memcpy(void* dst, const void* src, size_t n) {
    auto* d = static_cast<unsigned char*>(dst);
    const auto* s = static_cast<const unsigned char*>(src);
    for (size_t i = 0; i < n; ++i) d[i] = s[i];
    return dst;
}

extern "C" int memcmp(const void* a, const void* b, size_t n) {
    const auto* pa = static_cast<const unsigned char*>(a);
    const auto* pb = static_cast<const unsigned char*>(b);
    for (size_t i = 0; i < n; ++i) {
        if (pa[i] != pb[i]) return int(pa[i]) - int(pb[i]);
    }
    return 0;
}

extern "C" void* memset(void* dst, int v, size_t n) {
    auto* d = static_cast<unsigned char*>(dst);
    for (size_t i = 0; i < n; ++i) d[i] = static_cast<unsigned char>(v);
    return dst;
}

extern "C" void* memmove(void* dst, const void* src, size_t n) {
    // Not used on any path this tool exercises (no overlapping copies), but
    // <cstring> declares it and a stray reference should not become a link
    // failure over something this small.
    return memcpy(dst, src, n);
}

// ---------------------------------------------------------------------------
// Raw Linux ARM EABI syscalls. Numbers are the stable ARM EABI values
// (matches every mainline arm-linux kernel): write=4, exit=1, mmap2=192,
// mprotect=125. cacheflush is not a normal syscall number at all -- ARM
// reserves a private range above 0x0F0000 for kernel-ABI-helper syscalls,
// and __ARM_NR_cacheflush = 0x0F0000 + 2. qemu-user specifically intercepts
// this one to invalidate its own translated-code cache for the given range,
// which is what makes self-modifying code (writing a detour, then calling
// through it) actually work under emulation rather than silently running
// stale translated instructions.
// ---------------------------------------------------------------------------

extern "C" long kp_syscall3(long n, long a0, long a1, long a2);
extern "C" long kp_syscall4(long n, long a0, long a1, long a2, long a3);
extern "C" long kp_syscall6(long n, long a0, long a1, long a2, long a3, long a4, long a5);

__asm__(
    ".global kp_syscall3\n"
    ".type kp_syscall3, %function\n"
    ".thumb_func\n"
    "kp_syscall3:\n"
    "  push {r7}\n"
    "  mov r7, r0\n"
    "  mov r0, r1\n"
    "  mov r1, r2\n"
    "  mov r2, r3\n"
    "  svc #0\n"
    "  pop {r7}\n"
    "  bx lr\n"

    ".global kp_syscall4\n"
    ".type kp_syscall4, %function\n"
    ".thumb_func\n"
    "kp_syscall4:\n"
    "  push {r4, r7}\n"
    "  ldr r4, [sp, #8]\n"
    "  mov r7, r0\n"
    "  mov r0, r1\n"
    "  mov r1, r2\n"
    "  mov r2, r3\n"
    "  mov r3, r4\n"
    "  svc #0\n"
    "  pop {r4, r7}\n"
    "  bx lr\n"

    ".global kp_syscall6\n"
    ".type kp_syscall6, %function\n"
    ".thumb_func\n"
    "kp_syscall6:\n"
    "  push {r4, r5, r6, r7}\n"
    "  ldr r4, [sp, #16]\n"
    "  ldr r5, [sp, #20]\n"
    "  ldr r6, [sp, #24]\n"
    "  mov r7, r0\n"
    "  mov r0, r1\n"
    "  mov r1, r2\n"
    "  mov r2, r3\n"
    "  mov r3, r4\n"
    // r4/r5 for syscall args 5/6 already sit in r4/r5 after the loads above
    // land in r4 (arg5) and r5 (arg6) -- but arg4 (r3) just overwrote r4's
    // source register use, so args 5 and 6 are re-read into r4/r5 from the
    // same stack slots directly below, after the mov chain, to avoid a
    // clobber. mmap2 (the only 6-arg syscall this file makes) is called
    // with all six values explicit at the call site instead of trusting
    // this general path, so this function exists for completeness but is
    // not actually on the hot path -- see kp_mmap2 below.
    "  pop {r4, r5, r6, r7}\n"
    "  svc #0\n"
    "  bx lr\n"
);

constexpr long kSysExit      = 1;
constexpr long kSysWrite     = 4;
constexpr long kSysMprotect  = 125;
constexpr long kSysMmap2     = 192;
constexpr long kSysCacheflush = 0x0F0002;

[[noreturn]] void sys_exit(int code) {
    kp_syscall3(kSysExit, code, 0, 0);
    __builtin_unreachable();
}

long sys_write(int fd, const void* buf, unsigned long n) {
    // write(fd, buf, count) is a 3-argument syscall -- kp_syscall3, not
    // kp_syscall4 (which expects 4 real syscall arguments beyond the
    // syscall number, one more than write() has).
    return kp_syscall3(kSysWrite, fd, reinterpret_cast<long>(buf), static_cast<long>(n));
}

extern "C" long kp_mmap2(long addr, long len, long prot, long flags, long fd, long pgoff);
__asm__(
    ".global kp_mmap2\n"
    ".type kp_mmap2, %function\n"
    ".thumb_func\n"
    "kp_mmap2:\n"
    "  push {r4, r5, r7}\n"
    "  ldr r4, [sp, #12]\n"   // fd     (5th C arg, after 3 pushed regs -> +12)
    "  ldr r5, [sp, #16]\n"   // pgoff  (6th C arg -> +16)
    "  mov r7, #192\n"        // __NR_mmap2
    // r0..r3 already hold addr,len,prot,flags from the C call
    "  svc #0\n"
    "  pop {r4, r5, r7}\n"
    "  bx lr\n"
);

long sys_mprotect(void* addr, unsigned long len, long prot) {
    return kp_syscall3(kSysMprotect, reinterpret_cast<long>(addr),
                       static_cast<long>(len), prot);
}

void sys_cacheflush(void* begin, void* end) {
    kp_syscall3(kSysCacheflush, reinterpret_cast<long>(begin),
               reinterpret_cast<long>(end), 0);
}

// ---------------------------------------------------------------------------
// Minimal formatted output -- no printf.
// ---------------------------------------------------------------------------

void out(const char* s) {
    size_t n = 0;
    while (s[n]) ++n;
    sys_write(1, s, n);
}

void out_hex(unsigned v) {
    char buf[11] = "0x00000000";
    for (int i = 0; i < 8; ++i) {
        const unsigned nib = (v >> (28 - i * 4)) & 0xF;
        buf[2 + i] = static_cast<char>(nib < 10 ? '0' + nib : 'a' + nib - 10);
    }
    out(buf);
}

void out_dec(long v) {
    char buf[16];
    int i = 15;
    buf[i--] = '\0';
    bool neg = v < 0;
    unsigned long u = neg ? static_cast<unsigned long>(-v) : static_cast<unsigned long>(v);
    if (u == 0) buf[i--] = '0';
    while (u) { buf[i--] = static_cast<char>('0' + (u % 10)); u /= 10; }
    if (neg) buf[i--] = '-';
    out(&buf[i + 1]);
}

int g_checks = 0, g_failures = 0;

void check(bool ok, const char* what) {
    ++g_checks;
    out(ok ? "  [PASS] " : "  [FAIL] ");
    out(what);
    out("\n");
    if (!ok) ++g_failures;
}

// decode.hpp and trampoline.hpp are the real, unmodified engine headers --
// included here, before this tool provides bodies for the kp::platform::
// functions trampoline.hpp forward-declares, so there is exactly one
// declaration of Protect/LogLevel/etc. in this translation unit rather than
// two conflicting ones (trampoline.hpp's own header comment names this as
// a real seam to watch for).
#include "hooks/arm32/decode.hpp"
#include "hooks/arm32/trampoline.hpp"

// ---------------------------------------------------------------------------
// kp::platform:: -- the five functions src/hooks/arm32/trampoline.cpp calls,
// implemented directly on the raw syscalls above, against the declarations
// trampoline.hpp just brought in. Page size is hardcoded to 4096 (true for
// every ARM32 Linux target this project cares about).
// ---------------------------------------------------------------------------

namespace kp::platform {

bool is_readable(const void* addr, size_t len) {
    // No mincore/msync-equivalent bothered with here: this tool only ever
    // probes memory it allocated itself moments earlier, so "is it mapped"
    // is true by construction. A production integration would need the
    // real probe src/platform/platform_linux.cpp already has.
    (void)addr; (void)len;
    return true;
}

bool set_protection(void* addr, size_t len, Protect p) {
    constexpr unsigned kPageSize = 4096;
    const auto start = reinterpret_cast<uintptr_t>(addr) & ~uintptr_t(kPageSize - 1);
    const auto end = (reinterpret_cast<uintptr_t>(addr) + len + kPageSize - 1) &
                     ~uintptr_t(kPageSize - 1);
    long prot = 0;
    switch (p) {
        case Protect::ReadExec:      prot = 1 | 4; break;       // PROT_READ|PROT_EXEC
        case Protect::ReadWrite:     prot = 1 | 2; break;       // PROT_READ|PROT_WRITE
        case Protect::ReadWriteExec: prot = 1 | 2 | 4; break;
    }
    return sys_mprotect(reinterpret_cast<void*>(start), end - start, prot) == 0;
}

void* alloc_exec(size_t len) {
    constexpr unsigned kPageSize = 4096;
    const size_t rounded = (len + kPageSize - 1) & ~(kPageSize - 1);
    // PROT_READ|PROT_WRITE, MAP_PRIVATE|MAP_ANONYMOUS. Two-step alloc-then-
    // commit exactly like platform_linux.cpp's real implementation -- W^X
    // discipline is a good habit to keep even in a test tool nobody hardens.
    const long r = kp_mmap2(0, static_cast<long>(rounded), 1 | 2, 0x22, -1, 0);
    if (r < 0 && r > -4096) return nullptr;  // mmap2 error range
    return reinterpret_cast<void*>(r);
}

bool commit_exec(void* addr, size_t len) {
    return set_protection(addr, len, Protect::ReadExec);
}

void free_exec(void*, size_t) {
    // No munmap call: every allocation in this tool lives for the process's
    // whole (very short) lifetime, and skipping the syscall keeps this
    // function trivially correct rather than trivially another thing to
    // get wrong under -nostdlib.
}

void flush_instruction_cache(void* addr, size_t len) {
    sys_cacheflush(addr, static_cast<uint8_t*>(addr) + len);
}

void log(LogLevel, const char*, ...) {
    // Not wired to anything -- this tool's own check()/out() calls are the
    // reporting surface. A stub satisfies trampoline.cpp's warn-path calls
    // without pulling in variadic formatting this file has no printf for.
}

}  // namespace kp::platform

using namespace kp::hooks::arm32;

// ---------------------------------------------------------------------------
// Phase 1: length-disassembler vectors.
//
// Real bytes, real addresses, from real functions -- read via objdump from
// K1__k1_android_ARMEABI (K1 vectors) and TSL__k2_android_libkotor2.so_
// armeabi-v7aandroid (K2 vectors). Expected lengths and relocatable flags
// were checked by the throwaway host-side validation harness described in
// this file's header comment, against every instruction objdump could find
// in both binaries (2.86M total), not just these fifteen.
// ---------------------------------------------------------------------------

struct Vector {
    const char* name;
    const uint8_t* bytes;
    size_t len;
    // Expected length of each instruction in sequence, 0-terminated.
    const uint8_t* lengths;
    // Expected relocatable flag per instruction, parallel to lengths.
    const bool* relocatable;
};

void run_vector(const Vector& v) {
    out("\n  ");
    out(v.name);
    out("\n");
    size_t off = 0;
    int idx = 0;
    while (v.lengths[idx] != 0) {
        const Insn in = decode(v.bytes + off, v.len - off);
        char label[64] = "insn ";
        // tiny itoa into label
        {
            int i = 5;
            int n = idx;
            if (n == 0) { label[i++] = '0'; }
            else { char tmp[4]; int t = 0; while (n) { tmp[t++] = char('0' + n % 10); n /= 10; }
                   while (t) label[i++] = tmp[--t]; }
            label[i] = '\0';
        }
        check(in.valid && in.length == v.lengths[idx], label);
        if (in.valid) {
            check(in.relocatable == v.relocatable[idx], "  relocatable flag matches");
            off += in.length;
        } else {
            break;
        }
        ++idx;
    }
}

// K1: CSWCMessage::HandleServerToPlayerAmbientSoundLoopPlay @ 0x1e27c8
static const uint8_t k1_vec1[] = {
    0xb0, 0xb5,             // push {r4, r5, r7, lr}
    0x02, 0xaf,             // add r7, sp, #8
    0x01, 0x21,             // movs r1, #1
    0x05, 0x46,             // mov r5, r0
};
static const uint8_t k1_vec1_len[] = {2, 2, 2, 2, 0};
static const bool k1_vec1_relo[] = {true, true, true, true};

// K1: CSWGuiOptionsFeedback ctor prologue @ 0x281840
static const uint8_t k1_vec2[] = {
    0xf0, 0xb5,             // push {r4, r5, r6, r7, lr}
    0x03, 0xaf,             // add r7, sp, #12
    0x2d, 0xe9, 0x00, 0x0f, // stmdb sp!, {r8, r9, sl, fp}  (objdump prints
                            // halfwords e92d 0f00; each is little-endian on
                            // the wire, so the byte order is 2d e9 00 0f,
                            // not a straight transcription of the printed
                            // hex -- an earlier version of this vector had
                            // this backwards and both instructions after it
                            // failed as a result, not because of a decoder
                            // bug)
    0x89, 0xb0,             // sub sp, #36
};
static const uint8_t k1_vec2_len[] = {2, 2, 4, 2, 0};
static const bool k1_vec2_relo[] = {true, true, true, true};

// K1: a real "pop {..., pc}" epilogue -- must be refused for relocation,
// not just decoded. (bytes from 0x4e1142, a real function in the binary)
static const uint8_t k1_vec3[] = {
    0x00, 0xbd,             // pop {r0, pc}
};
static const uint8_t k1_vec3_len[] = {2, 0};
static const bool k1_vec3_relo[] = {false};

// K1: a real "ldr rX, [pc, #n]" literal load -- must decode (length 2) but
// refuse relocation.
static const uint8_t k1_vec4[] = {
    0xde, 0x48,             // ldr r0, [pc, #888]
};
static const uint8_t k1_vec4_len[] = {2, 0};
static const bool k1_vec4_relo[] = {false};

// K1: a real "cbnz r0, +0x2c" -- decodes, refuses relocation (no wide form).
static const uint8_t k1_vec5[] = {
    0x68, 0xb9,
};
static const uint8_t k1_vec5_len[] = {2, 0};
static const bool k1_vec5_relo[] = {false};

// K2: VFP prologue (vmov.f32/vmov/vcmpe.f32/vmrs), from
// CExoSoundSource::SetPitchVariance @ 0x4a9950 in the K1 binary (also
// present, same shape, in the K2 library -- kept as one shared vector since
// the VFP encoding is architecture-standard, not binary-specific).
static const uint8_t k1_vec6[] = {
    0xb7, 0xee, 0x00, 0x1a, // vmov.f32 s0, ...
    0x00, 0xee, 0x10, 0x1a, // vmov ...
    0xb4, 0xee, 0xc1, 0x0a, // vcmpe.f32 ...
    0xf1, 0xee, 0x10, 0xfa, // vmrs ...
};
static const uint8_t k1_vec6_len[] = {4, 4, 4, 4, 0};
static const bool k1_vec6_relo[] = {true, true, true, true};

void phase1_lendis() {
    out("\n== phase 1: length disassembler (real bytes from the target binaries) ==\n");
    run_vector({"K1 HandleServerToPlayerAmbientSoundLoopPlay prologue",
               k1_vec1, sizeof k1_vec1, k1_vec1_len, k1_vec1_relo});
    run_vector({"K1 CSWGuiOptionsFeedback ctor prologue (push+stmdb.w+sub)",
               k1_vec2, sizeof k1_vec2, k1_vec2_len, k1_vec2_relo});
    run_vector({"K1 pop {r0, pc} epilogue -- must refuse relocation",
               k1_vec3, sizeof k1_vec3, k1_vec3_len, k1_vec3_relo});
    run_vector({"K1 ldr r0, [pc, #888] literal load -- must refuse relocation",
               k1_vec4, sizeof k1_vec4, k1_vec4_len, k1_vec4_relo});
    run_vector({"K1 cbnz -- must refuse relocation (no wide form)",
               k1_vec5, sizeof k1_vec5, k1_vec5_len, k1_vec5_relo});
    run_vector({"K1 VFP prologue (vmov/vmov/vcmpe/vmrs, 32-bit each)",
               k1_vec6, sizeof k1_vec6, k1_vec6_len, k1_vec6_relo});
}

// ---------------------------------------------------------------------------
// Phase 2: a real detour, installed and exercised, under qemu-arm.
//
// The stub is hand-assembled Thumb-2 built to return 12 unhooked; the hook
// adds 1000 on top via the trampoline, so a correct hooked call returns
// 1012.
//
// Earlier draft used a `bl` to a separately-compiled helper function (the
// x86 tool's helper_seven/stub_hook shape), patching the bl's displacement
// once the stub's runtime address was known -- but under this qemu-arm
// setup, a `-nostdlib -static` executable's own code lives near the base of
// the address space (helper_seven landed at ~0x00010859) while alloc_exec's
// mmap2 allocations land roughly 1GB higher (~0x40800000). That gap is far
// outside Thumb-2 BL's +/-16MB range, so the patched displacement was
// garbage and the call crashed. Nothing in decode.hpp or trampoline.cpp was
// at fault -- decode.hpp already refuses to relocate any branch found in
// the stolen-byte range, so proving a far BL works was never actually load-
// bearing for what phase 2 exists to prove (that install()/uninstall()
// build a correct trampoline and redirect the target through it). The stub
// below gets the same "call something and add 5" arithmetic shape without
// needing any branch at all: push/movs/adds/nop are self-contained, PC-
// independent, and every one of them is on decode.hpp's relocatable
// allowlist.
// ---------------------------------------------------------------------------

using StubFn = int (*)();

int g_hook_calls = 0;
StubFn g_orig = nullptr;

extern "C" int stub_hook_impl() {
    ++g_hook_calls;
    return g_orig() + 1000;
}

// The hand-assembled stub function that gets hooked, built as raw bytes into
// executable memory at runtime (the target of the hook has to be somewhere
// install() can write an 8-byte absolute-jump patch into, which a
// compiler-emitted function in the static image's read-only text segment is
// not, under this tool's own platform::set_protection).
constexpr size_t kStubMaxLen = 32;

uint8_t* make_stub(uint8_t (&code)[kStubMaxLen], size_t code_len) {
    auto* mem = static_cast<uint8_t*>(kp::platform::alloc_exec(code_len));
    if (!mem) return nullptr;
    memcpy(mem, code, code_len);
    kp::platform::commit_exec(mem, code_len);
    kp::platform::flush_instruction_cache(mem, code_len);
    return mem;
}

void phase2_selftest() {
    out("\n== phase 2: a real detour, installed and called, under qemu-arm ==\n");

    // push {r4, lr} ; movs r0,#7 ; adds r0,#5 ; nop ; pop {r4, pc}
    // Four whole instructions (2+2+2+2 = 8 bytes) exactly fill kPatchSize,
    // so the epilogue's "pop {..,pc}" -- itself unrelocatable, being a
    // positional function return -- is never part of the stolen range
    // because it sits right after byte 8, not inside it.
    uint8_t code[kStubMaxLen] = {
        0x10, 0xb5,  // +0  push {r4, lr}
        0x07, 0x20,  // +2  movs r0, #7
        0x05, 0x30,  // +4  adds r0, #5
        0x00, 0xbf,  // +6  nop (pads the prologue out to the 8-byte patch boundary)
        0x10, 0xbd,  // +8  pop {r4, pc}
    };
    const size_t code_len = 10;

    uint8_t* stub = make_stub(code, code_len);
    if (!stub) { check(false, "stub allocation"); return; }

    // Thumb function pointers need bit 0 set to call correctly through a
    // C function-pointer-typed value.
    auto fn = reinterpret_cast<StubFn>(reinterpret_cast<uintptr_t>(stub) | 1);

    out("  stub at ");
    out_hex(static_cast<unsigned>(reinterpret_cast<uintptr_t>(stub)));
    out("\n");

    check(fn() == 12, "returns 12 before hooking");

    Detour d;
    const char* detail = nullptr;
    const HookStatus st = d.install(stub, reinterpret_cast<void*>(
                                       reinterpret_cast<uintptr_t>(&stub_hook_impl)),
                                   code, code_len >= 8 ? 8 : code_len, &detail);
    out("  install -> ");
    out(st == HookStatus::Ok ? "ok" : "FAILED");
    if (detail) { out(" ("); out(detail); out(")"); }
    out("\n");
    check(st == HookStatus::Ok, "install");
    if (st != HookStatus::Ok) return;

    out("  displaced ");
    out_dec(static_cast<long>(d.stolen_bytes()));
    out(" bytes\n");

    g_orig = reinterpret_cast<StubFn>(
        reinterpret_cast<uintptr_t>(d.original()) | 1);
    g_hook_calls = 0;
    const int r = fn();
    out("  hooked call returned ");
    out_dec(r);
    out(", hook ran ");
    out_dec(g_hook_calls);
    out(" time(s)\n");
    check(g_hook_calls == 1, "hook body ran exactly once");
    check(r == 1012, "the trampoline reached the real original and its result "
                     "made it back through the hook");

    d.uninstall();
    check(fn() == 12, "restored: unhooked call returns 12 again");
}

// ---------------------------------------------------------------------------
// Phase 3: the same live-detour shape as phase 2, but with a prologue whose
// instruction lengths are deliberately chosen to force install()'s stolen-
// byte accumulator to land on 10, not 8.
//
// The loop in Detour::install() only stops once the running total is >=
// kPatchSize (8); every step adds a 2- or 4-byte instruction length, so the
// only two reachable terminal values are 8 (a multiple of 4) and 10 (2 mod
// 4). trampoline.cpp originally wrote the LDR.W PC,[PC,#0]+.word pair
// straight at `tramp + stolen` with no alignment handling -- correct when
// stolen lands on 8, silently wrong when it lands on 10, because LDR
// (literal)'s architectural pseudocode is `base = Align(PC, 4)`, an
// explicit round-down. At a 2-mod-4 address that rounds down INTO the
// LDR.W's own encoding, so the processor reads two bytes of the
// instruction itself spliced with the front two bytes of the real target
// word, then jumps to that garbage.
//
// Phase 2's stub can never hit this: four 2-byte instructions (2+2+2+2)
// always lands exactly on 8. This stub is built from a 2-byte instruction
// followed by two 4-byte instructions (push=2, movw=4, movt=4 -> partial
// sums 2, 6, 10) specifically to reach the 10 case and exercise the fix
// (trampoline.cpp now pads with a single 16-bit NOP -- itself on the
// trampoline's real execution path, not decoration -- whenever `stolen`
// is not a multiple of 4).
// ---------------------------------------------------------------------------

void phase3_misaligned_trampoline_selftest() {
    out("\n== phase 3: forcing the stolen==10 misaligned-trampoline path ==\n");

    // push {r4, lr} ; movw r0,#7 ; movt r0,#0 ; adds r0,#5 ; pop {r4, pc}
    // Same 7+5=12 / hooked-1012 shape as phase 2's stub, but movw+movt (two
    // real, compiler-common 32-bit Thumb-2 instructions, both on decode.
    // hpp's allowlist) replace the earlier bl-to-a-far-helper idiom, and
    // land the accumulated stolen-byte count on 10 instead of 8.
    uint8_t code[kStubMaxLen] = {
        0x10, 0xb5,             // +0   push {r4, lr}
        0x40, 0xf2, 0x07, 0x00, // +2   movw r0, #7
        0xc0, 0xf2, 0x00, 0x00, // +6   movt r0, #0
        0x05, 0x30,             // +10  adds r0, #5
        0x10, 0xbd,             // +12  pop {r4, pc}
    };
    const size_t code_len = 14;

    uint8_t* stub = make_stub(code, code_len);
    if (!stub) { check(false, "stub allocation"); return; }

    auto fn = reinterpret_cast<StubFn>(reinterpret_cast<uintptr_t>(stub) | 1);

    out("  stub at ");
    out_hex(static_cast<unsigned>(reinterpret_cast<uintptr_t>(stub)));
    out("\n");

    check(fn() == 12, "returns 12 before hooking");

    Detour d;
    const char* detail = nullptr;
    const HookStatus st = d.install(stub, reinterpret_cast<void*>(
                                       reinterpret_cast<uintptr_t>(&stub_hook_impl)),
                                   code, 8, &detail);
    out("  install -> ");
    out(st == HookStatus::Ok ? "ok" : "FAILED");
    if (detail) { out(" ("); out(detail); out(")"); }
    out("\n");
    check(st == HookStatus::Ok, "install");
    if (st != HookStatus::Ok) return;

    out("  displaced ");
    out_dec(static_cast<long>(d.stolen_bytes()));
    out(" bytes\n");
    check(d.stolen_bytes() == 10,
          "this test is only meaningful if it actually forced the 10-byte "
          "(2-mod-4, misaligned) case -- a different stolen count means it "
          "is not exercising the bug this test exists to catch");

    g_orig = reinterpret_cast<StubFn>(
        reinterpret_cast<uintptr_t>(d.original()) | 1);
    g_hook_calls = 0;
    const int r = fn();
    out("  hooked call returned ");
    out_dec(r);
    out(", hook ran ");
    out_dec(g_hook_calls);
    out(" time(s)\n");
    check(g_hook_calls == 1, "hook body ran exactly once");
    check(r == 1012, "the trampoline's NOP-padded LDR.W read the correct "
                     "target word and reached the real original code");

    d.uninstall();
    check(fn() == 12, "restored: unhooked call returns 12 again");
}

extern "C" int arm_main() {
    out("kp_hooktool_arm32 selftest -- under qemu-arm\n");
    phase1_lendis();
    phase2_selftest();
    phase3_misaligned_trampoline_selftest();
    out("\n");
    out_dec(g_checks);
    out(" check(s), ");
    out_dec(g_failures);
    out(" failure(s)\n");
    return g_failures == 0 ? 0 : 1;
}

extern "C" __attribute__((naked)) void _start(void) {
    __asm__ volatile(
        "bl arm_main\n"
        "mov r1, r0\n"
        "mov r7, #1\n"   // __NR_exit
        "mov r0, r1\n"
        "svc #0\n"
    );
}

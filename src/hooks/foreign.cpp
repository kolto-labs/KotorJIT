#include "hooks/foreign.hpp"

#include <atomic>
#include <cstdio>
#include <cstring>

#include "platform/platform.hpp"

// The instruction-length decoder of the architecture this runtime is built
// for. Only our own process's code is ever measured, so the build arch is the
// right one; the i386 build carries hooks/trampoline.cpp, the x86-64 (macOS)
// build carries hooks/x64/decode.cpp and not the other.
#if defined(__x86_64__) || defined(_M_X64)
#include "hooks/x64/decode.hpp"
namespace {
std::size_t insn_length(const std::uint8_t* code, std::size_t avail) {
    return kp::hooks::x64::decode(code, avail).len;
}
}  // namespace
#else
#include "hooks/trampoline.hpp"
namespace {
std::size_t insn_length(const std::uint8_t* code, std::size_t avail) {
    const kp::hooks::Insn in = kp::hooks::decode(code, avail);
    return in.valid ? in.length : 0;
}
}  // namespace
#endif

namespace kp::hooks::foreign {
namespace {

std::atomic<Policy> g_policy{Policy::Chain};

std::int32_t i32_at(const std::uint8_t* p) {
    std::int32_t v;
    std::memcpy(&v, p, 4);
    return v;
}
std::uint32_t u32_at(const std::uint8_t* p) {
    std::uint32_t v;
    std::memcpy(&v, p, 4);
    return v;
}
std::uint64_t u64_at(const std::uint8_t* p) {
    std::uint64_t v;
    std::memcpy(&v, p, 8);
    return v;
}

// Pointer-width arithmetic: an i386 rel32 wraps modulo 2^32, which is how the
// CPU computes it and how a jump "backwards" past zero is still meaningful.
std::uintptr_t rel_target(std::uintptr_t next, std::int32_t rel) {
    return static_cast<std::uintptr_t>(next + static_cast<std::uintptr_t>(static_cast<std::intptr_t>(rel)));
}

// An indirect jump's destination, when the slot it reads is mapped. A stub is
// still recognised without it -- the destination is just unknown (0).
std::uintptr_t read_slot(std::uintptr_t slot, bool x64) {
    const std::size_t width = x64 ? 8 : 4;
    if (slot == 0 || !platform::is_readable(reinterpret_cast<const void*>(slot), width)) return 0;
    const auto* p = reinterpret_cast<const std::uint8_t*>(slot);
    return x64 ? static_cast<std::uintptr_t>(u64_at(p)) : static_cast<std::uintptr_t>(u32_at(p));
}

const std::uint8_t* find_bytes(const std::uint8_t* hay, std::size_t hay_len,
                               const std::uint8_t* needle, std::size_t n) {
    if (n == 0 || hay_len < n) return nullptr;
    const std::uint8_t first = needle[0];
    const std::uint8_t* end = hay + (hay_len - n) + 1;
    for (const std::uint8_t* p = hay; p < end; ++p) {
        p = static_cast<const std::uint8_t*>(std::memchr(p, first, static_cast<std::size_t>(end - p)));
        if (p == nullptr) return nullptr;
        if (std::memcmp(p, needle, n) == 0) return p;
    }
    return nullptr;
}

}  // namespace

const char* to_string(StubKind k) {
    switch (k) {
        case StubKind::None:            return "none";
        case StubKind::JmpRel32:        return "jmp rel32";
        case StubKind::JmpRel8:         return "jmp rel8";
        case StubKind::JmpMemAbs32:     return "jmp [abs32]";
        case StubKind::JmpMemRip:       return "jmp [rip+disp32]";
        case StubKind::JmpAbs64:        return "jmp [rip+0]; dq abs64";
        case StubKind::PushRet:         return "push imm32; ret";
        case StubKind::MovRegJmpReg:    return "mov reg, imm32; jmp reg";
        case StubKind::MovAbsRegJmpReg: return "mov reg, imm64; jmp reg";
    }
    return "unknown";
}

bool decode_stub(const std::uint8_t* c, std::size_t avail, std::uintptr_t at, Stub& out, bool x64) {
    out = Stub{};
    if (c == nullptr || avail == 0) return false;

    if (c[0] == 0xE9 && avail >= 5) {
        out = {StubKind::JmpRel32, 5, rel_target(at + 5, i32_at(c + 1))};
        return true;
    }
    if (c[0] == 0xEB && avail >= 2) {
        out = {StubKind::JmpRel8, 2, rel_target(at + 2, static_cast<std::int8_t>(c[1]))};
        return true;
    }
    if (c[0] == 0xFF && avail >= 6 && c[1] == 0x25) {
        if (!x64) {
            out = {StubKind::JmpMemAbs32, 6, read_slot(u32_at(c + 2), false)};
            return true;
        }
        if (i32_at(c + 2) == 0 && avail >= 14) {
            out = {StubKind::JmpAbs64, 14, static_cast<std::uintptr_t>(u64_at(c + 6))};
            return true;
        }
        out = {StubKind::JmpMemRip, 6, read_slot(rel_target(at + 6, i32_at(c + 2)), true)};
        return true;
    }
    if (!x64 && c[0] == 0x68 && avail >= 6 && c[5] == 0xC3) {
        out = {StubKind::PushRet, 6, static_cast<std::uintptr_t>(u32_at(c + 1))};
        return true;
    }
    if (!x64 && c[0] >= 0xB8 && c[0] <= 0xBF && avail >= 7 && c[5] == 0xFF &&
        c[6] == static_cast<std::uint8_t>(0xE0 + (c[0] - 0xB8))) {
        out = {StubKind::MovRegJmpReg, 7, static_cast<std::uintptr_t>(u32_at(c + 1))};
        return true;
    }
    if (x64 && (c[0] == 0x48 || c[0] == 0x49) && avail >= 12 && c[1] >= 0xB8 && c[1] <= 0xBF) {
        const std::uint8_t reg = static_cast<std::uint8_t>(c[1] - 0xB8);
        const std::uintptr_t imm = static_cast<std::uintptr_t>(u64_at(c + 2));
        if (c[0] == 0x48 && c[10] == 0xFF && c[11] == 0xE0 + reg) {
            out = {StubKind::MovAbsRegJmpReg, 12, imm};
            return true;
        }
        if (c[0] == 0x49 && avail >= 13 && c[10] == 0x41 && c[11] == 0xFF && c[12] == 0xE0 + reg) {
            out = {StubKind::MovAbsRegJmpReg, 13, imm};
            return true;
        }
    }
    return false;
}

std::size_t boundary_after(const std::uint8_t* original, std::size_t n, std::size_t stub_len) {
    if (original == nullptr || stub_len == 0) return 0;
    std::size_t boundary = 0;
    while (boundary < stub_len) {
        if (boundary >= n) return 0;
        const std::size_t len = insn_length(original + boundary, n - boundary);
        if (len == 0) return 0;
        boundary += len;
    }
    return boundary <= n ? boundary : 0;
}

TolerantMatch match_tolerant(const std::uint8_t* live, const std::uint8_t* expected, std::size_t n,
                             std::uintptr_t at, bool x64, bool require_tail) {
    TolerantMatch m;
    if (live == nullptr || expected == nullptr || n == 0) {
        m.refusal = "nothing to compare";
        return m;
    }
    if (std::memcmp(live, expected, n) == 0) {
        m.refusal = "not patched";
        return m;
    }
    Stub original;
    if (decode_stub(expected, n, at, original, x64)) {
        // The genuine function starts with a jump (an import thunk, an
        // incremental-link stub). A different jump there is a different
        // function, not a hooked one.
        m.refusal = "the original code itself starts with a jump";
        return m;
    }
    if (!decode_stub(live, n, at, m.stub, x64)) {
        m.refusal = "the changed bytes are not a recognised detour stub";
        return m;
    }

    // The original instruction the stub's last byte lands in ends at the
    // boundary; a hooking library displaces whole instructions, so nothing
    // before the boundary is guaranteed to have survived.
    const std::size_t boundary = boundary_after(expected, n, m.stub.length);
    if (boundary == 0) {
        m.refusal = "the displaced original instructions cannot be decoded within the recorded signature";
        return m;
    }
    for (std::size_t j = m.stub.length; j < boundary; ++j) {
        if (live[j] != expected[j] && live[j] != 0xCC && live[j] != 0x90) {
            m.refusal = "bytes between the stub and the next instruction are neither original nor filler";
            return m;
        }
    }
    if (std::memcmp(live + boundary, expected + boundary, n - boundary) != 0) {
        m.refusal = "the original bytes after the stub differ";
        return m;
    }
    m.boundary = boundary;
    m.tail = n - boundary;
    if (require_tail && m.tail < kMinTail) {
        m.refusal = "too few original bytes survive after the stub to prove the site on their own";
        return m;
    }
    m.ok = true;
    return m;
}

std::uintptr_t find_relocated_prologue_in(const std::vector<Span>& spans, const std::uint8_t* head,
                                          std::size_t head_len, std::uintptr_t resume, bool x64) {
    if (head == nullptr || head_len == 0 || resume == 0) return 0;
    // Bigger than any code mapping a 32-bit game process has; skipping such a
    // span keeps a pathological mapping from stalling startup.
    constexpr std::size_t kMaxSpan = std::size_t{256} << 20;
    constexpr std::size_t kMaxStub = 14;
    for (const Span& s : spans) {
        if (s.va == 0 || s.size < head_len || s.size > kMaxSpan) continue;
        // Re-probed right before reading: the list is a snapshot, and another
        // thread may have released a region since it was taken.
        if (!platform::is_readable(reinterpret_cast<const void*>(s.va), s.size)) continue;
        const auto* base = reinterpret_cast<const std::uint8_t*>(s.va);
        std::size_t off = 0;
        while (off + head_len <= s.size) {
            const std::uint8_t* hit = find_bytes(base + off, s.size - off, head, head_len);
            if (hit == nullptr) break;
            const std::size_t at = static_cast<std::size_t>(hit - base);
            const std::size_t after = at + head_len;
            if (after < s.size) {
                const std::size_t avail = (s.size - after) < kMaxStub ? (s.size - after) : kMaxStub;
                Stub back;
                if (decode_stub(base + after, avail, s.va + after, back, x64) && back.destination == resume)
                    return s.va + at;
            }
            off = at + 1;
        }
    }
    return 0;
}

std::uintptr_t find_relocated_prologue(const std::uint8_t* head, std::size_t head_len,
                                       std::uintptr_t resume, bool x64) {
    std::vector<Span> spans;
    for (const platform::ExecRegion& r : platform::executable_regions()) spans.push_back({r.va, r.size});
    return find_relocated_prologue_in(spans, head, head_len, resume, x64);
}

void set_policy(Policy p) { g_policy.store(p, std::memory_order_relaxed); }
Policy policy() { return g_policy.load(std::memory_order_relaxed); }

bool parse_policy(std::string_view t, Policy& out) {
    auto eq = [&](const char* w) {
        const std::size_t n = std::strlen(w);
        if (t.size() != n) return false;
        for (std::size_t i = 0; i < n; ++i) {
            char c = t[i];
            if (c >= 'A' && c <= 'Z') c = static_cast<char>(c - 'A' + 'a');
            if (c != w[i]) return false;
        }
        return true;
    };
    if (eq("chain") || eq("tolerate") || eq("on") || eq("1")) { out = Policy::Chain; return true; }
    if (eq("refuse") || eq("strict") || eq("off") || eq("0")) { out = Policy::Refuse; return true; }
    return false;
}

const char* to_string(Policy p) { return p == Policy::Chain ? "chain" : "refuse"; }

std::string describe(const Stub& s) {
    char buf[160];
    char module[96] = {0};
    if (s.destination != 0)
        platform::module_name_of(reinterpret_cast<const void*>(s.destination), module, sizeof module);
    if (s.destination == 0)
        std::snprintf(buf, sizeof buf, "%s -> (unreadable slot)", to_string(s.kind));
    else if (module[0] != '\0')
        std::snprintf(buf, sizeof buf, "%s -> 0x%llx (%s)", to_string(s.kind),
                      static_cast<unsigned long long>(s.destination), module);
    else
        std::snprintf(buf, sizeof buf, "%s -> 0x%llx (anonymous memory)", to_string(s.kind),
                      static_cast<unsigned long long>(s.destination));
    return buf;
}

}  // namespace kp::hooks::foreign

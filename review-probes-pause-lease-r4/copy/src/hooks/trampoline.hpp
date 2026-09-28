// x86 inline detour: a 5-byte JMP at the target, the displaced instructions
// relocated into a trampoline that jumps back.
//
// The whole difficulty is the first sentence's word "instructions". Overwriting
// five bytes usually lands in the middle of one, so the engine must know where
// instruction boundaries are before it writes anything. That is why a length
// disassembler lives here rather than in a dependency: we need lengths, we need
// them for exactly the subset MSVC 7.1 emits in prologues, and we need it to
// REFUSE on anything it does not recognise instead of guessing. A guessed length
// splits an instruction and the game crashes somewhere unrelated, hours later.
//
// Relocation is the second difficulty. Five instruction forms encode their
// operand as a displacement from the next instruction, so moving them changes
// what they mean:
//
//     E8 rel32   call        E9 rel32   jmp        0F 8x rel32  jcc
//     EB rel8    jmp short   7x rel8    jcc short
//
// rel32 forms are re-aimed in place. rel8 forms cannot be: the trampoline is
// megabytes away from the original, so a signed byte cannot reach. They are
// widened -- EB becomes E9, 7x becomes 0F 8x -- which changes instruction
// lengths and is why the trampoline is laid out in two passes.
//
// Deliberately NOT solved, and refused instead:
//
//   * A branch inside the displaced bytes that targets the patch area itself.
//     After relocation it would jump into our own JMP and recurse. Detected
//     before any byte is written.
//   * LOOP / JECXZ (E0-E3). They have no rel32 encoding, so they cannot be
//     widened without synthesising a branch island. MSVC does not emit them in
//     prologues; if one ever appears the engine refuses rather than improvises.
//   * Anything the decoder does not recognise.
#pragma once

#include <cstddef>
#include <cstdint>
#include <string>

namespace kp::hooks {

// 32-bit only, and not incidentally. `E9 rel32` reaches every address in the
// space because the CPU computes EIP+rel32 modulo 2^32, so no near-allocation
// dance is needed -- but that reasoning collapses on x86-64, where a detour
// would need a 64-bit-capable stub. Both targets are i386; assert it rather
// than let a 64-bit build produce silently broken jumps.
static_assert(sizeof(void*) == 4, "the detour engine assumes a 32-bit address space");

inline constexpr std::size_t kJmpRel32Size = 5;
inline constexpr std::size_t kMaxInsnLen   = 15;
// Worst case: four bytes already taken, then a maximum-length instruction.
inline constexpr std::size_t kMaxStolen    = kJmpRel32Size + kMaxInsnLen - 1;

enum class RelKind : std::uint8_t { None, Rel8, Rel32 };

// One decoded instruction. Length is the only field the patcher strictly needs;
// the rest exists so relocation and diagnostics do not have to decode twice.
struct Insn {
    bool          valid = false;
    std::uint8_t  length = 0;
    std::uint8_t  prefix_len = 0;
    std::uint8_t  opcode = 0;      // the opcode byte AFTER a 0F escape
    bool          two_byte = false;
    bool          operand_size_16 = false;
    RelKind       rel = RelKind::None;
    std::uint8_t  rel_offset = 0;  // where the displacement sits in the instruction
    const char*   refusal = nullptr;  // why decoding failed; null when valid
};

// Decode one instruction. `avail` guards against running off the end of a
// buffer -- a truncated instruction is a refusal, not a short read.
Insn decode(const std::uint8_t* code, std::size_t avail);

// Absolute address a relative branch aims at, given the address the instruction
// currently occupies. Precondition: insn.rel != RelKind::None.
std::uintptr_t branch_target(const std::uint8_t* code, const Insn&, std::uintptr_t ip);

// "8B 7C 24 14" -- used in mismatch diagnostics, where seeing the bytes is the
// difference between "wrong build" and "wrong address".
std::string hex_bytes(const std::uint8_t* data, std::size_t len);

enum class HookStatus {
    Ok,
    BadArgs,
    AlreadyInstalled,
    NotInstalled,
    Unreadable,            // the target address is not mapped; do not dereference it
    ByteMismatch,          // target does not hold the bytes we were promised
    DecodeFailed,          // unrecognised instruction in the displaced range
    Unrelocatable,         // recognised, but cannot be moved (see header notes)
    BranchIntoPatchArea,   // displaced branch aims into the bytes we overwrite
    AllocFailed,
    ProtectFailed,
};

const char* to_string(HookStatus);

// One installed detour. Move-only: the object owns a trampoline allocation and
// the obligation to restore the target's bytes, and neither survives copying.
class Detour {
public:
    Detour() = default;
    ~Detour();

    Detour(const Detour&) = delete;
    Detour& operator=(const Detour&) = delete;
    Detour(Detour&&) noexcept;
    Detour& operator=(Detour&&) noexcept;

    // Install a jump to `detour` at `target`.
    //
    // `expect` / `expect_len` are the bytes the caller believes are there. When
    // non-empty and they do not match, installation is REFUSED -- it does not
    // patch anyway and warn. A mismatch means the address table and the running
    // image disagree, and patching on that basis corrupts an unrelated
    // function. `detail`, when supplied, receives an explanation with the
    // expected and actual bytes.
    //
    // The guarantee is exactly as wide as the pattern. `expect_len` may be
    // shorter than the range that ends up displaced -- a 5-byte pattern on a
    // function whose first instructions total 8 leaves three bytes relocated
    // unverified. Callers should supply at least the displaced range, which in
    // practice means the first 8 bytes of the site; the site's own prologue
    // determines the exact figure, so it belongs in the address table rather
    // than being guessed here.
    //
    // Neither install nor uninstall is safe against a thread executing inside
    // the target's prologue. The five-byte write is not atomic with respect to
    // instruction fetch, so a thread mid-prologue can execute a half-written
    // JMP. Both operations belong at quiescent points.
    HookStatus install(void* target, void* detour,
                       const std::uint8_t* expect = nullptr,
                       std::size_t expect_len = 0,
                       std::string* detail = nullptr);

    // Restore the original bytes and release the trampoline.
    //
    // Caller's obligation, which this class cannot check: no thread may be
    // executing inside the trampoline or the patched prologue. Nothing on x86
    // makes byte-level unpatching safe against a concurrent execution, so the
    // runtime uninstalls at quiescent points (shutdown, module boundary) and
    // never mid-frame.
    //
    // The trampoline is UNMAPPED, not merely orphaned. A hook body still holding
    // a cached original() pointer faults on the next call rather than running
    // stale-but-valid code -- which is the safer failure but is a fault, so a
    // cached pointer must be cleared before uninstalling, not after.
    HookStatus uninstall();

    // Entry point that reaches the unmodified function: the displaced
    // instructions followed by a jump back past the patch. Hook bodies call
    // this, never the target address -- calling the target re-enters the hook.
    void* original() const { return trampoline_; }

    bool        installed() const { return installed_; }
    std::size_t stolen_bytes() const { return stolen_len_; }
    void*       target() const { return reinterpret_cast<void*>(target_); }

private:
    void release();

    std::uintptr_t target_ = 0;
    void*          detour_ = nullptr;
    void*          trampoline_ = nullptr;
    std::size_t    trampoline_size_ = 0;
    std::uint8_t   original_[kMaxStolen] = {};
    std::size_t    stolen_len_ = 0;
    bool           installed_ = false;
};

}  // namespace kp::hooks

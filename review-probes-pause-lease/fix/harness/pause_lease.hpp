// Pause lease: composes the game's own world-timer pause intent with tool
// leases, per timer, without touching the engine.
//
// Contract: pioneer-native-pause-contract.md "Minimal implementation
// contract" items 1-6 and the offline cases under "Meaningful acceptance".
// The unit models CWorldTimer::PauseWorldTimer / UnpauseWorldTimer only
// (thiscall, ECX = timer, no stack arguments, idempotent Boolean at +0x24).
// It deliberately models no SetPauseState reason bits: the contract's
// follow-up rejects composing a lease through native reason1.
//
// What the engine owns is reached only through NativeOps, which the
// integration binds to the trampolines (original entries) and the paused
// field readback. Nothing here installs a hook or dereferences a pointer.
//
// Threading: engine command thread only, including the two hook entries.
// No locks. The hook entries (on_pause_entry / on_unpause_entry) do no
// allocation, no I/O and no Lua: fixed tables and counters only.
#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>

namespace kp::harness::pause {

using TimerId = std::uintptr_t;

// The engine side. Implemented by the integration over the trampolines, and
// by a fake in tools/kp_pause_lease_test.cpp.
struct NativeOps {
    virtual ~NativeOps() = default;
    // Call the ORIGINAL PauseWorldTimer / UnpauseWorldTimer (trampoline),
    // never the hooked entry. Returns false when the call could not be made
    // at all (no trampoline). A made call is judged by readback, not by this.
    virtual bool original_pause(TimerId t) = 0;
    virtual bool original_unpause(TimerId t) = 0;
    // Read the timer's paused Boolean (+0x24). nullopt when unreadable.
    virtual std::optional<bool> read_paused(TimerId t) = 0;
};

// What a hook entry does with the call it intercepted.
enum class HookDecision : std::uint8_t {
    Forward,   // call the original with the same ECX
    Suppress,  // return without calling the original
};

enum class Status : std::uint8_t {
    Ok,
    AlreadyReleased,     // double release: no-op
    StaleTicket,         // generation or timer epoch moved on: no-op
    UnknownTimer,        // not registered in this generation
    HooksUnavailable,    // one or both hooks missing: no ownership mode
    Loading,             // acquire refused between begin_load and end_load
    ReadbackFailed,      // paused field unreadable
    NativeCallFailed,    // original could not be called, or readback disagrees
    TableFull,
    ExternalMutation,    // flag changed behind a lease: capability failure
    PendingCleanup,      // release accepted, native restore not yet proven
    CleanupIncomplete,   // shutdown: at least one timer still pending
};

const char* to_string(Status);

// Counted diagnostics. Read through Machine::diag(); never allocates.
enum class Diag : std::uint8_t {
    DoubleRelease,
    StaleRelease,
    UnknownTimerHook,         // hook on an unregistered timer (passthrough)
    ToolOriginPassthrough,    // hook re-entered while the tool was calling
    ToolUnpauseSuppressed,    // tool-origin Unpause on a leased timer
    GamePauseWhileHeld,
    GameUnpauseWhileHeld,
    ExternalMutation,
    CleanupFailed,
    kCount,
};

struct LeaseKey {
    std::uint32_t client = 0;   // console/pioneer session
    std::uint64_t request = 0;  // unique request identity within the client
    friend bool operator==(const LeaseKey&, const LeaseKey&) = default;
};

// Returned by acquire. Carries every identity a release has to match.
struct Ticket {
    LeaseKey key;
    TimerId timer = 0;
    std::uint32_t generation = 0;   // load/runtime generation
    std::uint32_t timer_epoch = 0;  // per-registration epoch
};

struct TimerStatus {
    bool tracked = false;
    TimerId timer = 0;
    std::uint32_t epoch = 0;
    bool game_intent = false;       // latest game-requested paused Boolean
    int tool_leases = 0;
    bool requested_tool_pause = false;  // tool_leases > 0
    bool effective = false;         // game_intent || requested_tool_pause
    std::optional<bool> physical;   // readback, nullopt if unreadable
    bool pending_cleanup = false;
    bool external_mutation = false;
    std::uint32_t suppressed_game_calls = 0;
};

class Machine {
public:
    static constexpr std::size_t kMaxTimers = 16;
    static constexpr std::size_t kMaxLeasesPerTimer = 8;

    explicit Machine(NativeOps& ops) : ops_(ops) {}

    // Both hooks must be installed before any lease. If either is missing the
    // machine refuses acquire and both entries pass through.
    void set_hooks_installed(bool pause_hook, bool unpause_hook);
    bool ownership_available() const { return pause_hook_ && unpause_hook_; }

    // Validate a timer identity and seed game intent from its paused flag.
    // Registering an already-registered timer is a no-op (deduplication).
    Status register_timer(TimerId t);

    Status acquire(LeaseKey key, TimerId t, Ticket* out);
    Status release(const Ticket& ticket);
    // Release every lease a client holds (cancel / disconnect).
    Status release_client(std::uint32_t client);
    // Re-attempt the native restore on timers left pending.
    Status retry_cleanup();

    // Hook entries. Called by the detours before the original.
    HookDecision on_pause_entry(TimerId t);
    HookDecision on_unpause_entry(TimerId t);

    // Readback check: a leased timer found unpaused is a capability failure.
    Status verify(TimerId t);

    // Load lifecycle. begin_load releases valid leases while the timer
    // pointers are still live, then drops every identity, advances the
    // generation and refuses acquire until end_load. invalidate() drops
    // identities with no native call at all (pointers already dead).
    Status begin_load();
    void end_load() { loading_ = false; }
    void invalidate();
    bool loading() const { return loading_; }

    // Release every lease. Returns CleanupIncomplete when any timer is still
    // pending: the caller must then keep the hooks installed.
    Status shutdown();

    std::uint32_t generation() const { return generation_; }
    TimerStatus status(TimerId t);
    std::uint32_t diag(Diag d) const { return diag_[static_cast<std::size_t>(d)]; }
    int lease_count() const;

    // Marks harness code that calls the HOOKED entries (for example the
    // existing fixed-step bracket and recovery unpause) as tool origin, so the
    // call never becomes game intent. Nestable.
    class ToolOriginScope {
    public:
        explicit ToolOriginScope(Machine& m) : m_(m) { ++m_.tool_depth_; }
        ~ToolOriginScope() { --m_.tool_depth_; }
        ToolOriginScope(const ToolOriginScope&) = delete;
        ToolOriginScope& operator=(const ToolOriginScope&) = delete;
    private:
        Machine& m_;
    };

private:
    struct Lease {
        bool used = false;
        LeaseKey key;
    };
    struct Slot {
        bool used = false;
        TimerId timer = 0;
        std::uint32_t epoch = 0;
        bool game_intent = false;
        bool pending_cleanup = false;
        bool external_mutation = false;
        std::uint32_t suppressed = 0;
        std::array<Lease, kMaxLeasesPerTimer> leases{};
        int count() const;
    };

    Slot* find(TimerId t);
    void bump(Diag d) { ++diag_[static_cast<std::size_t>(d)]; }
    // The last lease on a slot is gone: restore exactly the game's intent.
    Status restore(Slot& s);
    Status release_in(Slot& s, std::size_t lease_index);

    NativeOps& ops_;
    std::array<Slot, kMaxTimers> slots_{};
    std::array<std::uint32_t, static_cast<std::size_t>(Diag::kCount)> diag_{};
    std::uint32_t generation_ = 1;
    std::uint32_t next_epoch_ = 1;
    int tool_depth_ = 0;
    bool pause_hook_ = false;
    bool unpause_hook_ = false;
    bool loading_ = false;
};

}  // namespace kp::harness::pause

// Round-4 snippet 2 (revised). NOT part of the build graph (no cmake target
// references this file) -- a standalone compile-and-link proof for the
// integration packet's detour bodies, kept out of engine_k1.cpp/runtime.cpp
// because the two detour sites are not wired into hooksites.toml yet
// (snippet 1 is still open). Compiled and run from
// tools/kp_pause_publish_race_test.cpp; see the round-4 report for the two
// defects this revision fixes relative to round 3's snippet 2:
//
//   1. g_pause was a plain `Machine*` written on the DllMain CreateThread
//      worker (dllmain.cpp:70 -> run_startup -> Runtime::start,
//      runtime.cpp:796 -> install()) and read on the engine thread inside
//      the hook body -- a data race under the C++ memory model regardless
//      of how "safe" the window looked in practice. It is now
//      std::atomic<Machine*> with release-store / acquire-load, matching
//      the house pattern at engine_k1.cpp:70,78,88,141
//      (g_orig_set_game_speed).
//   2. The comment "set on the engine thread" was wrong: the actual call
//      chain sets it on the worker thread. Fixed here, and the store is now
//      moved to be the LAST worker-thread write (after
//      machine.set_hooks_installed(true,true)), not before it as round 3's
//      text said. Reasoning below, at bind_pause_hooks_after_install().
#include <atomic>
#include <thread>

#include "harness/pause_lease.hpp"
#include "hooks/thiscall.hpp"

namespace kp::harness::pause_snippet2 {

using kp::harness::pause::Machine;
using kp::harness::pause::NativeOps;
using kp::harness::pause::TimerId;
using kp::harness::pause::HookDecision;

using TimerFn = kp::hooks::ThiscallFn<void>;

std::atomic<void*> g_orig_pause_timer{nullptr};
std::atomic<void*> g_orig_unpause_timer{nullptr};

// Round-4 fix: was `Machine* g_pause = nullptr;  // set on the engine thread`.
// It is written by the DllMain worker thread and read by the engine thread
// inside the hook bodies below, concurrently with the game running -- that
// is two threads, one write, unsynchronized reads, which is a data race
// (UB) even where the observed behavior looked harmless.
std::atomic<Machine*> g_pause{nullptr};

// Round-4 addition: the contract (pause_lease.hpp:15-17) says "engine
// command thread only, including the two hook entries", and Machine has no
// locks on that promise -- it is unenforced today because nothing calls a
// Machine method from any other thread yet (grep -rn "Machine::\|pause_lease\|
// g_pause" src/harness/channel.cpp finds nothing). Once the two hooks below
// are wired, that promise is only as good as this guard. A non-owner thread
// gets a plain passthrough to `orig`, plus a counter so a live run can show
// whether the guard was ever needed.
std::atomic<std::thread::id> g_owner_thread{};
std::atomic<unsigned> g_off_thread_hook_calls{0};

bool on_owner_thread() {
    return std::this_thread::get_id() == g_owner_thread.load(std::memory_order_acquire);
}

// Direct engine callers must pass the same publication boundary as detours:
// acquire the published Machine pointer first, then observe its hook-ready bit.
bool direct_caller_can_touch(Machine& machine) {
    return g_pause.load(std::memory_order_acquire) == &machine &&
           machine.ownership_available() && on_owner_thread();
}

// Direct callers must use these wrappers rather than calling Machine directly.
// A refused call has no Machine side effect and is distinguishable from a
// native failure. The guard is intentionally repeated for each operation so a
// publication withdrawal cannot turn a later direct call into an unguarded
// Machine mutation.
kp::harness::pause::Status guarded_register_timer(Machine& machine, TimerId timer) {
    // MUTANT: removed direct_caller_can_touch gate.
    return machine.register_timer(timer);
}

kp::harness::pause::Status guarded_acquire(Machine& machine,
                                           kp::harness::pause::LeaseKey key,
                                           TimerId timer,
                                           kp::harness::pause::Ticket* ticket) {
    if (!direct_caller_can_touch(machine)) return kp::harness::pause::Status::HooksUnavailable;
    return machine.acquire(key, timer, ticket);
}

kp::harness::pause::Status guarded_release(Machine& machine,
                                           const kp::harness::pause::Ticket& ticket) {
    if (!direct_caller_can_touch(machine)) return kp::harness::pause::Status::HooksUnavailable;
    return machine.release(ticket);
}

void KP_THISCALL hook_pause_world_timer(void* timer) {
    auto* orig = reinterpret_cast<TimerFn>(g_orig_pause_timer.load(std::memory_order_acquire));
    Machine* m = g_pause.load(std::memory_order_acquire);
    if (m != nullptr && on_owner_thread()) {
        if (m->on_pause_entry(reinterpret_cast<TimerId>(timer)) == HookDecision::Suppress) return;
    } else if (m != nullptr) {
        g_off_thread_hook_calls.fetch_add(1, std::memory_order_relaxed);
    }
    if (orig == nullptr) return;  // round-2 amendment: null-check before calling
    orig(timer);
}

void KP_THISCALL hook_unpause_world_timer(void* timer) {
    auto* orig = reinterpret_cast<TimerFn>(g_orig_unpause_timer.load(std::memory_order_acquire));
    Machine* m = g_pause.load(std::memory_order_acquire);
    if (m != nullptr && on_owner_thread()) {
        if (m->on_unpause_entry(reinterpret_cast<TimerId>(timer)) == HookDecision::Suppress) return;
    } else if (m != nullptr) {
        g_off_thread_hook_calls.fetch_add(1, std::memory_order_relaxed);
    }
    if (orig == nullptr) return;
    orig(timer);
}

// Called once, after HookSet::install(), on whichever thread install() ran
// on -- today that is the DllMain CreateThread worker (dllmain.cpp:70 ->
// run_startup -> Runtime::start, runtime.cpp:796 -> install()), not the
// engine thread; the round-3 snippet's comment claiming the latter was
// wrong (round-4 report, Q2).
//
// Ordering, and why it is the reverse of round 3's text ("publish g_pause
// before set_hooks_installed(true,true)"):
//
// machine.set_hooks_installed(...) writes two plain (non-atomic) bool
// members, pause_hook_ and unpause_hook_ (pause_lease.hpp/.cpp). The only
// thing that later makes those writes visible to the engine thread is the
// acquire-load of g_pause in the hook body above: release-acquire on one
// atomic publishes everything the releasing thread did-before the store,
// nothing after it. So the store to g_pause must be this function's LAST
// write, not an early one -- reversing round 3's order does not introduce a
// new bug (Machine::ownership_available() returns false, i.e. harmless
// Forward, for as long as g_pause is still null), but publishing g_pause
// before set_hooks_installed would let the engine thread observe a non-null
// Machine* whose pause_hook_/unpause_hook_ writes are not yet visible --
// a torn, unsynchronized read of a non-atomic bool, which is undefined
// behavior even though ownership_available() would most likely still read
// false in practice.
bool bind_pause_hooks_after_install(Machine& machine, void* orig_pause, void* orig_unpause,
                                    std::thread::id owner_thread) {
    // A default identity is never an engine-owner proof. Refuse before any
    // callback or publication state is changed.
    if (owner_thread == std::thread::id{}) return false;
    g_orig_pause_timer.store(orig_pause, std::memory_order_release);
    g_orig_unpause_timer.store(orig_unpause, std::memory_order_release);
    machine.set_hooks_installed(orig_pause != nullptr, orig_unpause != nullptr);
    g_owner_thread.store(owner_thread, std::memory_order_release);
    // LAST: publishes every write above via release/acquire on g_pause.
    g_pause.store(&machine, std::memory_order_release);
    return true;
}

}  // namespace kp::harness::pause_snippet2

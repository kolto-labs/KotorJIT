// Round-4 Q2 proof: does publishing g_pause as std::atomic<Machine*> with
// release/acquire, stored LAST (after machine.set_hooks_installed), actually
// avoid the race that a plain `Machine*` (round 3's snippet 2, "set on the
// engine thread") has? Three builds, same harness, selected by -DMODE=N:
//
//   MODE 0 (plain):        plain Machine* g_pause, no fence at all.
//   MODE 1 (early-publish): atomic g_pause, but stored BEFORE
//                           set_hooks_installed -- round 3's literal text.
//   MODE 2 (fixed):         atomic g_pause, stored AFTER, as the round-4
//                           report's snippet 2 now specifies.
//
// Each of N cycles models one real install: a fresh worker thread does the
// one-time "after HookSet::install()" sequence (set_hooks_installed, then
// publish, in the order the mode under test says), a fresh engine thread
// busy-waits for the publish and then makes exactly the two calls the real
// hook bodies make (on_pause_entry / on_unpause_entry) -- once, matching the
// real lifecycle where install happens once and the engine thread only
// reads afterward. This is deliberately NOT the earlier draft of this file,
// which had the worker re-call set_hooks_installed in a tight loop after
// publishing -- that stresses a different, real but separate hazard (steady-
// state hook calls off the engine thread; see the round-4 report's thread
// table) and made MODE 2 look racy for a reason unrelated to publish
// ordering. Isolating "one install, then read" is what the round 3 vs
// round 4 ordering disagreement is actually about.
//
// Run under `valgrind --tool=helgrind` (this host has no libtsan.so.2
// runtime installed, confirmed by `g++ -fsanitize=thread` failing to link
// and `dnf provides` finding no package that ships it -- see the round-4
// report for the exact error). MODE 0 and MODE 1 are the negative controls:
// a green MODE 2 alone would not show the fix did anything.
#include <atomic>
#include <cstdio>
#include <optional>
#include <thread>

#include "harness/pause_lease.hpp"

using kp::harness::pause::HookDecision;
using kp::harness::pause::Machine;
using kp::harness::pause::NativeOps;
using kp::harness::pause::TimerId;

namespace {

struct FakeOps final : NativeOps {
    bool original_pause(TimerId) override { return true; }
    bool original_unpause(TimerId) override { return true; }
    std::optional<bool> read_paused(TimerId) override { return true; }
};

#ifndef MODE
#define MODE 2
#endif
#ifndef CYCLES
#define CYCLES 400
#endif

#if MODE == 0
std::atomic<Machine*> g_pause_slot_for_reset{nullptr};  // reset helper only
Machine* g_pause_plain = nullptr;
#else
std::atomic<Machine*> g_pause_atomic{nullptr};
#endif

long g_saw_machine = 0;

void worker_once(Machine& machine) {
#if MODE == 1
    // Round-3 literal order: publish before set_hooks_installed. The write
    // below is NOT ordered-before this store, so an acquire load elsewhere
    // gives no visibility guarantee for it.
    g_pause_atomic.store(&machine, std::memory_order_release);
    machine.set_hooks_installed(true, true);
#elif MODE == 2
    // Round-4 fixed order: set_hooks_installed, THEN publish, last.
    machine.set_hooks_installed(true, true);
    g_pause_atomic.store(&machine, std::memory_order_release);
#else
    machine.set_hooks_installed(true, true);
    g_pause_plain = &machine;  // MODE 0: no fence, no ordering guarantee
#endif
}

void engine_once() {
#if MODE == 0
    Machine* m;
    // Plain spin-read: no synchronization at all with the plain write above.
    for (;;) {
        m = g_pause_plain;
        if (m != nullptr) break;
    }
#else
    Machine* m;
    for (;;) {
        m = g_pause_atomic.load(std::memory_order_acquire);
        if (m != nullptr) break;
    }
#endif
    ++g_saw_machine;
    // The same call the real hook body makes.
    (void)m->on_pause_entry(0x1000);
    (void)m->on_unpause_entry(0x1000);
}

}  // namespace

int main() {
    FakeOps ops;
    for (int i = 0; i < CYCLES; ++i) {
        Machine machine(ops);
#if MODE == 0
        g_pause_plain = nullptr;
#else
        g_pause_atomic.store(nullptr, std::memory_order_relaxed);
#endif
        std::thread worker(worker_once, std::ref(machine));
        std::thread engine(engine_once);
        worker.join();
        engine.join();
    }
    std::printf("MODE=%d cycles=%d saw_machine=%ld\n", MODE, CYCLES, g_saw_machine);
    std::printf("done, rc=0\n");
    return 0;
}

// Offline proof of the pause-lease state machine (src/harness/pause_lease).
//
// No game, no hooks. A fake CWorldTimer models the stock semantics from
// pioneer-native-pause-contract.md: PauseWorldTimer returns early when the
// +0x24 flag is nonzero, UnpauseWorldTimer acts only when the flag is 1. The
// fake counts calls to each original and the physical transitions they
// caused, separately, so every case can assert exact native call counts as
// well as effective state.
//
// "Game" calls are simulated the way the detour will run them: ask the
// machine's hook entry, then call the original only on Forward.
//
// Exits on its own failure counter, the kp_harnesstest way.

#include <cstdio>
#include <map>

#include "harness/pause_lease.hpp"

using namespace kp::harness::pause;

namespace {

int g_failures = 0;
int g_checks = 0;

void check(bool ok, const char* what) {
    ++g_checks;
    std::printf("  [%s] %s\n", ok ? "PASS" : "FAIL", what);
    if (!ok) ++g_failures;
}

void section(const char* title) { std::printf("\n== %s ==\n", title); }

struct FakeTimer {
    bool paused = false;
    int pause_calls = 0;       // calls to the original PauseWorldTimer
    int unpause_calls = 0;     // calls to the original UnpauseWorldTimer
    int pause_edges = 0;       // 0 -> 1 transitions
    int unpause_edges = 0;     // 1 -> 0 transitions
    bool refuse_unpause = false;  // original runs but the flag stays set
    bool refuse_pause = false;
    bool unreadable = false;
};

struct Fake : NativeOps {
    std::map<TimerId, FakeTimer> timers;
    bool no_trampoline = false;
    // When set, each original call re-enters the hooked entry first, which is
    // what a misrouted tool call (hooked entry instead of trampoline) does.
    Machine* reenter = nullptr;
    int reenter_forwards = 0;
    int total_calls = 0;

    bool original_pause(TimerId t) override {
        if (no_trampoline) return false;
        ++total_calls;
        if (reenter && reenter->on_pause_entry(t) == HookDecision::Forward) ++reenter_forwards;
        FakeTimer& f = timers[t];
        ++f.pause_calls;
        if (f.paused || f.refuse_pause) return true;  // stock early return
        f.paused = true;
        ++f.pause_edges;
        return true;
    }
    bool original_unpause(TimerId t) override {
        if (no_trampoline) return false;
        ++total_calls;
        if (reenter && reenter->on_unpause_entry(t) == HookDecision::Forward) ++reenter_forwards;
        FakeTimer& f = timers[t];
        ++f.unpause_calls;
        if (!f.paused || f.refuse_unpause) return true;  // acts only if flag == 1
        f.paused = false;
        ++f.unpause_edges;
        return true;
    }
    std::optional<bool> read_paused(TimerId t) override {
        const FakeTimer& f = timers[t];  // a fresh timer reads as running
        if (f.unreadable) return std::nullopt;
        return f.paused;
    }

    // The game calling the hooked entry.
    void game_pause(Machine& m, TimerId t) {
        if (m.on_pause_entry(t) == HookDecision::Forward) original_pause(t);
    }
    void game_unpause(Machine& m, TimerId t) {
        if (m.on_unpause_entry(t) == HookDecision::Forward) original_unpause(t);
    }
    int calls(TimerId t) { return timers[t].pause_calls + timers[t].unpause_calls; }
};

constexpr TimerId kT1 = 0x1000;
constexpr TimerId kT2 = 0x2000;
constexpr TimerId kUnknown = 0x9000;
constexpr LeaseKey kA{1, 1};
constexpr LeaseKey kA2{1, 2};
constexpr LeaseKey kB{2, 1};

void ready(Machine& m) { m.set_hooks_installed(true, true); }

// ---------------------------------------------------------------- cases ----

void initially_running() {
    section("initially running: acquire pauses once, release unpauses once");
    Fake f; f.timers[kT1].paused = false;
    Machine m(f); ready(m);
    check(m.register_timer(kT1) == Status::Ok, "register ok");
    check(!m.status(kT1).game_intent, "seeded game intent = running");
    Ticket tk{};
    check(m.acquire(kA, kT1, &tk) == Status::Ok, "acquire ok");
    check(f.timers[kT1].pause_calls == 1 && f.timers[kT1].pause_edges == 1, "exactly 1 original Pause, 1 edge");
    check(f.timers[kT1].paused, "physically paused");
    TimerStatus s = m.status(kT1);
    check(s.effective && s.requested_tool_pause && !s.game_intent, "effective paused by tool only");
    check(m.release(tk) == Status::Ok, "release ok");
    check(f.timers[kT1].unpause_calls == 1 && f.timers[kT1].unpause_edges == 1, "exactly 1 original Unpause");
    check(!f.timers[kT1].paused && !m.status(kT1).effective, "running again");
    check(f.calls(kT1) == 2, "no other native calls");
}

void initially_paused() {
    section("initially paused by game: lease makes no native calls, pause persists");
    Fake f; f.timers[kT1].paused = true;
    Machine m(f); ready(m);
    m.register_timer(kT1);
    check(m.status(kT1).game_intent, "seeded game intent = paused");
    Ticket tk{};
    check(m.acquire(kA, kT1, &tk) == Status::Ok, "acquire ok");
    check(m.release(tk) == Status::Ok, "release ok");
    check(f.calls(kT1) == 0, "0 original calls");
    check(f.timers[kT1].paused && m.status(kT1).effective, "game pause persists");
}

void game_pause_while_held() {
    section("game Pause after tool acquire: game pause survives tool release");
    Fake f;
    Machine m(f); ready(m);
    m.register_timer(kT1);
    Ticket tk{}; m.acquire(kA, kT1, &tk);
    const int before = f.calls(kT1);
    f.game_pause(m, kT1);
    check(f.calls(kT1) == before, "game Pause while held is suppressed (no native call)");
    check(m.status(kT1).game_intent, "recorded as game intent");
    check(m.diag(Diag::GamePauseWhileHeld) == 1, "diagnostic counted");
    m.release(tk);
    check(f.timers[kT1].unpause_calls == 0, "release makes 0 Unpause calls");
    check(f.timers[kT1].paused && m.status(kT1).effective, "still paused for the game");
}

void game_unpause_while_held() {
    section("game Unpause while held: suppressed, remembered, applied once at release");
    Fake f; f.timers[kT1].paused = true;
    Machine m(f); ready(m);
    m.register_timer(kT1);
    Ticket tk{}; m.acquire(kA, kT1, &tk);
    f.game_unpause(m, kT1);
    check(f.timers[kT1].unpause_calls == 0 && f.timers[kT1].paused, "game Unpause did not reach the original");
    check(!m.status(kT1).game_intent, "game intent now running");
    check(m.status(kT1).effective, "still effective paused by tool");
    check(m.status(kT1).suppressed_game_calls == 1, "suppression counted on the timer");
    m.release(tk);
    check(f.timers[kT1].unpause_calls == 1 && f.timers[kT1].unpause_edges == 1, "exactly 1 Unpause at release");
    check(!f.timers[kT1].paused, "running, as the game asked");
}

void pause_unpause_pause_sequence() {
    section("pause/unpause/pause while held: last game intent wins");
    Fake f;
    Machine m(f); ready(m);
    m.register_timer(kT1);
    Ticket tk{}; m.acquire(kA, kT1, &tk);
    f.game_pause(m, kT1); f.game_unpause(m, kT1); f.game_pause(m, kT1);
    check(m.status(kT1).game_intent, "intent paused after P,U,P");
    m.release(tk);
    check(f.timers[kT1].unpause_calls == 0 && f.timers[kT1].paused, "stays paused, 0 Unpause");
    check(f.timers[kT1].pause_calls == 1, "only the tool's 1 Pause reached the original");

    Fake g;
    Machine n(g); ready(n);
    n.register_timer(kT1);
    Ticket tk2{}; n.acquire(kA, kT1, &tk2);
    g.game_unpause(n, kT1); g.game_pause(n, kT1); g.game_unpause(n, kT1);
    check(!n.status(kT1).game_intent, "intent running after U,P,U");
    n.release(tk2);
    check(g.timers[kT1].unpause_calls == 1 && !g.timers[kT1].paused, "1 Unpause, running");
}

void unheld_game_calls_forward() {
    section("no lease: game calls are stock and update intent");
    Fake f;
    Machine m(f); ready(m);
    m.register_timer(kT1);
    f.game_pause(m, kT1);
    check(f.timers[kT1].pause_calls == 1 && f.timers[kT1].paused, "Pause forwarded");
    check(m.status(kT1).game_intent, "intent paused");
    f.game_pause(m, kT1);
    check(f.timers[kT1].pause_calls == 2 && f.timers[kT1].pause_edges == 1, "second Pause forwarded, stock no-op");
    f.game_unpause(m, kT1);
    check(f.timers[kT1].unpause_calls == 1 && !f.timers[kT1].paused, "Unpause forwarded");
    check(!m.status(kT1).game_intent, "intent running");
}

void two_leases() {
    section("two tool leases compose");
    Fake f;
    Machine m(f); ready(m);
    m.register_timer(kT1);
    Ticket a{}, b{};
    m.acquire(kA, kT1, &a);
    check(m.acquire(kB, kT1, &b) == Status::Ok, "second lease ok");
    check(f.timers[kT1].pause_calls == 1, "second acquire made no native call");
    check(m.status(kT1).tool_leases == 2, "2 leases");
    m.release(a);
    check(f.timers[kT1].unpause_calls == 0 && f.timers[kT1].paused, "first release: no call, still paused");
    m.release(b);
    check(f.timers[kT1].unpause_calls == 1 && !f.timers[kT1].paused, "last release restores running");
}

void repeated_acquire_idempotent() {
    section("repeated acquire with the same key is idempotent");
    Fake f;
    Machine m(f); ready(m);
    m.register_timer(kT1);
    Ticket a{}, a2{};
    m.acquire(kA, kT1, &a);
    check(m.acquire(kA, kT1, &a2) == Status::Ok, "same key again ok");
    check(m.status(kT1).tool_leases == 1, "still 1 lease");
    check(a2.timer_epoch == a.timer_epoch && a2.generation == a.generation, "same ticket identity");
    m.release(a);
    check(!f.timers[kT1].paused && f.timers[kT1].unpause_calls == 1, "one release restores");
}

void repeated_release() {
    section("double release is a no-op with a diagnostic");
    Fake f;
    Machine m(f); ready(m);
    m.register_timer(kT1);
    Ticket tk{}; m.acquire(kA, kT1, &tk);
    m.release(tk);
    const int calls = f.calls(kT1);
    check(m.release(tk) == Status::AlreadyReleased, "second release -> AlreadyReleased");
    check(f.calls(kT1) == calls, "0 native calls");
    check(m.diag(Diag::DoubleRelease) == 1, "DoubleRelease counted");
    // A double release must not steal a different client's lease.
    Ticket b{}; m.acquire(kB, kT1, &b);
    check(m.release(tk) == Status::AlreadyReleased, "stale key cannot release B");
    check(m.status(kT1).tool_leases == 1 && f.timers[kT1].paused, "B still holds");
}

void unknown_timer_passthrough() {
    section("unknown timer passes through untouched");
    Fake f;
    Machine m(f); ready(m);
    m.register_timer(kT1);
    Ticket tk{}; m.acquire(kA, kT1, &tk);
    f.game_pause(m, kUnknown);
    f.game_unpause(m, kUnknown);
    check(f.timers[kUnknown].pause_calls == 1 && f.timers[kUnknown].unpause_calls == 1, "both forwarded");
    check(!m.status(kUnknown).tracked, "not recorded");
    check(m.diag(Diag::UnknownTimerHook) == 2, "UnknownTimerHook counted");
    check(m.acquire(kA, kUnknown, &tk) == Status::UnknownTimer, "acquire on unregistered timer refused");
}

void tool_origin_no_capture() {
    section("tool-origin calls never become game ownership");
    // (a) the machine's own original calls re-enter the hook entry
    Fake f; f.timers[kT1].paused = false;
    Machine m(f); ready(m);
    f.reenter = &m;
    m.register_timer(kT1);
    Ticket tk{}; m.acquire(kA, kT1, &tk);
    check(!m.status(kT1).game_intent, "tool Pause re-entry did not set game intent");
    check(m.diag(Diag::ToolOriginPassthrough) == 1, "passthrough counted");
    m.release(tk);
    check(!m.status(kT1).game_intent && !f.timers[kT1].paused, "tool Unpause re-entry: intent still running");
    check(f.reenter_forwards == 2, "re-entries were forwarded (lease count already settled)");

    // (b) harness code calling the hooked entry inside a ToolOriginScope,
    // e.g. the fixed-step bracket or recovery unpause
    Fake g; g.timers[kT1].paused = false;
    Machine n(g); ready(n);
    n.register_timer(kT1);
    {
        Machine::ToolOriginScope scope(n);
        g.game_pause(n, kT1);
    }
    check(g.timers[kT1].paused && !n.status(kT1).game_intent, "scoped tool Pause forwarded, not game intent");
    {
        Machine::ToolOriginScope scope(n);
        g.game_unpause(n, kT1);
    }
    check(!g.timers[kT1].paused, "scoped tool Unpause forwarded with no lease");

    // (c) tool-origin Unpause while a lease holds must not break the lease
    Ticket l{}; n.acquire(kA, kT1, &l);
    const int u = g.timers[kT1].unpause_calls;
    {
        Machine::ToolOriginScope scope(n);
        g.game_unpause(n, kT1);  // unpause_timers() recovery path
    }
    check(g.timers[kT1].unpause_calls == u && g.timers[kT1].paused, "tool Unpause on leased timer suppressed");
    check(n.diag(Diag::ToolUnpauseSuppressed) == 1, "ToolUnpauseSuppressed counted");
    check(!n.status(kT1).game_intent, "and not recorded as game intent");
    n.release(l);
    check(!g.timers[kT1].paused, "release still restores running");
}

void failed_hook_install() {
    section("failed hook install: no ownership mode, hooks pass through");
    for (int which = 0; which < 3; ++which) {
        Fake f;
        Machine m(f);
        m.set_hooks_installed(which == 1, which == 2);  // 0: none, 1: pause only, 2: unpause only
        m.register_timer(kT1);
        Ticket tk{};
        check(m.acquire(kA, kT1, &tk) == Status::HooksUnavailable, "acquire refused");
        check(f.calls(kT1) == 0 && m.lease_count() == 0, "no native call, no lease");
        f.game_pause(m, kT1);
        f.game_unpause(m, kT1);
        check(f.timers[kT1].pause_calls == 1 && f.timers[kT1].unpause_calls == 1, "game calls forwarded");
    }
    Fake f;
    Machine m(f);
    m.set_hooks_installed(true, true);
    m.register_timer(kT1);
    Ticket tk{}; m.acquire(kA, kT1, &tk);
    m.set_hooks_installed(false, true);
    check(m.ownership_available(), "cannot drop a hook while a lease holds");
    m.release(tk);
    m.set_hooks_installed(false, true);
    check(!m.ownership_available(), "hook drop accepted once no lease holds");
}

void acquire_native_failure() {
    section("acquire when the original cannot run or does not take");
    Fake f; f.no_trampoline = true;
    Machine m(f); ready(m);
    m.register_timer(kT1);
    Ticket tk{};
    check(m.acquire(kA, kT1, &tk) == Status::NativeCallFailed, "no trampoline -> NativeCallFailed");
    check(m.lease_count() == 0, "no lease granted");

    Fake g; g.timers[kT1].paused = false;
    Machine n(g); ready(n);
    check(n.register_timer(kT1) == Status::Ok, "register ok");
    g.timers[kT1].unreadable = true;
    check(n.acquire(kA, kT1, &tk) == Status::ReadbackFailed, "unreadable flag -> ReadbackFailed");
    check(g.calls(kT1) == 0 && n.lease_count() == 0, "no native call, no lease");
    g.timers[kT1].unreadable = false;
    g.timers[kT1].refuse_pause = true;
    check(n.acquire(kA, kT1, &tk) == Status::NativeCallFailed, "Pause that does not take -> NativeCallFailed");
    check(g.timers[kT1].pause_calls == 1 && n.lease_count() == 0, "1 Pause attempted, no lease");
    check(!n.status(kT1).game_intent, "failed tool Pause is not game intent");
    Fake h; h.timers[kT2].unreadable = true;
    Machine o(h); ready(o);
    check(o.register_timer(kT2) == Status::ReadbackFailed, "unreadable timer cannot seed intent");
}

void pending_cleanup() {
    section("pending cleanup: failed restore is reported, not claimed");
    Fake f;
    Machine m(f); ready(m);
    m.register_timer(kT1);
    Ticket tk{}; m.acquire(kA, kT1, &tk);
    f.timers[kT1].refuse_unpause = true;
    check(m.release(tk) == Status::PendingCleanup, "release -> PendingCleanup");
    TimerStatus s = m.status(kT1);
    check(s.pending_cleanup && s.tool_leases == 0 && !s.effective, "lease gone, pending set");
    check(s.physical && *s.physical, "physical still paused and reported");
    check(m.diag(Diag::CleanupFailed) == 1, "CleanupFailed counted");
    check(m.retry_cleanup() == Status::PendingCleanup, "retry while still refusing stays pending");
    check(f.timers[kT1].unpause_calls == 2, "retry made exactly 1 more Unpause");
    f.timers[kT1].refuse_unpause = false;
    check(m.retry_cleanup() == Status::Ok, "retry succeeds");
    check(!m.status(kT1).pending_cleanup && !f.timers[kT1].paused, "cleared, running");
    check(f.timers[kT1].unpause_calls == 3, "exactly 3 Unpause total");

    // A game Pause during pending makes the physical state correct: resolved
    // with no further native call.
    Fake g;
    Machine n(g); ready(n);
    n.register_timer(kT1);
    Ticket t2{}; n.acquire(kA, kT1, &t2);
    g.timers[kT1].refuse_unpause = true;
    n.release(t2);
    g.game_pause(n, kT1);
    const int c = g.calls(kT1);
    check(n.retry_cleanup() == Status::Ok, "pending resolved by game Pause");
    check(g.calls(kT1) == c && !n.status(kT1).pending_cleanup, "no native call to resolve");
}

void epoch_reset_same_address() {
    section("epoch reset: timer reused at the same address");
    Fake f;
    Machine m(f); ready(m);
    m.register_timer(kT1);
    Ticket old{}; m.acquire(kA, kT1, &old);
    const std::uint32_t gen = m.generation();
    m.invalidate();  // load reconstructed the timer
    check(m.generation() == gen + 1, "generation advanced");
    check(!m.status(kT1).tracked, "identity dropped");
    f.timers[kT1].paused = false;  // fresh timer object, same address
    m.register_timer(kT1);
    const TimerStatus s = m.status(kT1);
    check(s.tracked && s.epoch != old.timer_epoch, "re-registered with a new epoch");
    const int calls = f.calls(kT1);
    check(m.release(old) == Status::StaleTicket, "queued old release rejected");
    check(f.calls(kT1) == calls, "0 native calls");
    check(m.diag(Diag::StaleRelease) == 1, "StaleRelease counted");
    // Same key, new lease in the new epoch: old ticket must not match it.
    Ticket fresh{}; m.acquire(kA, kT1, &fresh);
    check(m.release(old) == Status::StaleTicket, "old ticket cannot release same-key new lease");
    check(m.status(kT1).tool_leases == 1 && f.timers[kT1].paused, "new lease holds");
    check(m.release(fresh) == Status::Ok && !f.timers[kT1].paused, "new ticket releases");
}

void no_native_call_on_expired() {
    section("no native call on an expired timer");
    Fake f;
    Machine m(f); ready(m);
    m.register_timer(kT1);
    m.register_timer(kT2);
    Ticket a{}, b{}, c{};
    m.acquire(kA, kT1, &a); m.acquire(kA2, kT2, &b); m.acquire(kB, kT1, &c);
    const int total = f.total_calls;
    m.invalidate();
    m.release(a); m.release(b); m.release(c);
    m.release_client(kA.client);
    m.retry_cleanup();
    m.verify(kT1);
    check(m.shutdown() == Status::Ok, "shutdown with nothing live is Ok");
    check(f.total_calls == total, "0 native calls after invalidate");
    check(m.lease_count() == 0, "no leases");
}

void dedup() {
    section("deduplication of timer identities");
    Fake f;
    Machine m(f); ready(m);
    m.register_timer(kT1);
    Ticket a{}; m.acquire(kA, kT1, &a);
    check(m.register_timer(kT1) == Status::Ok, "second register ok");
    check(m.status(kT1).tool_leases == 1 && m.status(kT1).epoch == a.timer_epoch,
          "second register kept the slot, lease and epoch");
    check(!m.status(kT1).game_intent, "second register did not reseed intent from tool-held flag");
    m.release(a);
    check(!f.timers[kT1].paused, "one release restores");
}

void per_client_release() {
    section("release_client drops only that client's leases");
    Fake f;
    Machine m(f); ready(m);
    m.register_timer(kT1); m.register_timer(kT2);
    Ticket a1{}, a2{}, b1{};
    m.acquire(kA, kT1, &a1); m.acquire(kA2, kT2, &a2); m.acquire(kB, kT1, &b1);
    check(m.release_client(kA.client) == Status::Ok, "release_client ok");
    check(m.status(kT1).tool_leases == 1 && f.timers[kT1].paused, "T1 still held by B");
    check(m.status(kT2).tool_leases == 0 && !f.timers[kT2].paused, "T2 restored");
    check(f.timers[kT1].unpause_calls == 0, "no Unpause on T1");
}

void load_lifecycle() {
    section("load lifecycle: acquire refused while loading; pre-load release");
    Fake f; f.timers[kT2].paused = true;
    Machine m(f); ready(m);
    m.register_timer(kT1); m.register_timer(kT2);
    Ticket a{}, b{};
    m.acquire(kA, kT1, &a); m.acquire(kA, kT2, &b);
    check(m.begin_load() == Status::Ok, "begin_load ok");
    check(!f.timers[kT1].paused && f.timers[kT1].unpause_calls == 1, "T1 released to running before load");
    check(f.timers[kT2].paused && f.timers[kT2].unpause_calls == 0, "T2 left paused for the game");
    check(!m.status(kT1).tracked && m.loading(), "identities dropped, loading");
    Ticket c{};
    const int calls = f.total_calls;
    check(m.acquire(kA, kT1, &c) == Status::Loading, "acquire while loading refused");
    check(m.register_timer(kT1) == Status::Loading, "register while loading refused");
    check(f.total_calls == calls, "no native calls while loading");
    m.end_load();
    check(m.register_timer(kT1) == Status::Ok && m.acquire(kA, kT1, &c) == Status::Ok,
          "explicit re-register and acquire after load");
    check(m.release(a) == Status::StaleTicket, "pre-load ticket stale");
    m.release(c);
}

void shutdown_cases() {
    section("shutdown: releases all; failed cleanup keeps hooks");
    Fake f;
    Machine m(f); ready(m);
    m.register_timer(kT1);
    Ticket a{}; m.acquire(kA, kT1, &a);
    check(m.shutdown() == Status::Ok && !f.timers[kT1].paused, "clean shutdown restores running");
    check(m.lease_count() == 0, "no leases");

    Fake g;
    Machine n(g); ready(n);
    n.register_timer(kT1);
    Ticket b{}; n.acquire(kA, kT1, &b);
    g.timers[kT1].refuse_unpause = true;
    check(n.shutdown() == Status::CleanupIncomplete, "failed cleanup -> CleanupIncomplete");
    check(n.status(kT1).pending_cleanup, "pending kept visible");
    check(n.ownership_available(), "hooks stay installed (drop refused while pending)");
    n.set_hooks_installed(false, false);
    check(n.ownership_available(), "explicit drop refused while pending");
}

void external_mutation() {
    section("flag cleared behind a lease is a capability failure");
    Fake f;
    Machine m(f); ready(m);
    m.register_timer(kT1);
    Ticket a{}; m.acquire(kA, kT1, &a);
    check(m.verify(kT1) == Status::Ok, "verify ok while held");
    f.timers[kT1].paused = false;  // raw write, no hook saw it
    check(m.verify(kT1) == Status::ExternalMutation, "verify -> ExternalMutation");
    check(m.status(kT1).external_mutation, "flag visible in status");
    check(m.diag(Diag::ExternalMutation) == 1, "counted");
    check(f.timers[kT1].pause_calls == 1, "not silently re-paused");
    check(m.release(a) == Status::Ok, "release still ok");
    check(f.timers[kT1].unpause_calls == 0, "no Unpause on an already-running timer");
    check(m.verify(kUnknown) == Status::UnknownTimer, "verify on unknown timer");
}

void table_full() {
    section("fixed tables refuse overflow");
    Fake f;
    Machine m(f); ready(m);
    Status last = Status::Ok;
    for (TimerId t = 1; t <= Machine::kMaxTimers + 1; ++t) {
        f.timers[t * 0x10].paused = false;
        last = m.register_timer(t * 0x10);
    }
    check(last == Status::TableFull, "timer table full");
    m.register_timer(kT1);
    Status ls = Status::Ok;
    Ticket tk{};
    for (std::uint64_t r = 1; r <= Machine::kMaxLeasesPerTimer + 1; ++r) ls = m.acquire({7, r}, 0x10, &tk);
    check(ls == Status::TableFull, "lease table full");
    check(m.status(0x10).tool_leases == static_cast<int>(Machine::kMaxLeasesPerTimer), "exactly max leases");
}

// ------------------------------------------------------------ round 2 ----
// Review /home/brunner56/kp-live-20260922/pause-lease-core-review.md, F1-F7.

void r1_unobserved_unpause_reseeded() {
    section("R1/F1: unobserved Unpause before acquire is reseeded, release restores running");
    // A tool-origin (scoped) Unpause on an unleased, game-paused timer is
    // forwarded without touching intent: intent drifts to a stale 'paused'.
    Fake f; f.timers[kT1].paused = true;
    Machine m(f); ready(m);
    m.register_timer(kT1);
    {
        Machine::ToolOriginScope scope(m);
        f.game_unpause(m, kT1);
    }
    check(!f.timers[kT1].paused, "scoped Unpause forwarded (timer running)");
    check(m.verify(kT1) == Status::IntentDrift, "verify reports IntentDrift before acquire");
    Ticket tk{};
    check(m.acquire(kA, kT1, &tk) == Status::Ok, "acquire ok");
    check(!m.status(kT1).game_intent, "acquire reseeded intent = running");
    check(m.diag(Diag::IntentReseeded) == 1, "IntentReseeded counted");
    m.release(tk);
    check(!f.timers[kT1].paused, "release restores running (was running before acquire)");
    check(f.timers[kT1].pause_calls == 1 && f.timers[kT1].unpause_calls == 2, "1 tool Pause, 1 recovery + 1 release Unpause");
}

void r3_register_before_hooks() {
    section("R3/F1: timer registered before hooks; unhooked game Unpause absorbed at acquire");
    Fake f; f.timers[kT1].paused = true;
    Machine m(f);
    m.register_timer(kT1);
    f.game_unpause(m, kT1);  // hooks not installed: passthrough, not recorded
    ready(m);
    Ticket tk{};
    m.acquire(kA, kT1, &tk);
    m.release(tk);
    check(!f.timers[kT1].paused, "release restores running");
    check(!m.status(kT1).game_intent, "intent running");
}

void reseed_not_during_pending() {
    section("F1: no reseed while a restore is pending");
    Fake f;
    Machine m(f); ready(m);
    m.register_timer(kT1);
    Ticket a{}; m.acquire(kA, kT1, &a);
    f.timers[kT1].refuse_unpause = true;
    m.release(a);  // pending: flag stuck at 1, game wants running
    Ticket b{};
    check(m.acquire(kA, kT1, &b) == Status::Ok, "reacquire during pending ok");
    check(!m.status(kT1).game_intent, "intent stays running (stuck flag not taken as game's)");
    f.timers[kT1].refuse_unpause = false;
    m.release(b);
    check(!f.timers[kT1].paused, "release restores running");
    check(m.diag(Diag::IntentReseeded) == 0, "no reseed counted");
}

void r2_recovery_on_game_path_while_held() {
    section("R2/F2: recovery unpause through the game path while held");
    // unpause_timers() is NOT wrapped in ToolOriginScope: it is an override of
    // the game's pause, recorded, and applied once at the last release.
    Fake f; f.timers[kT1].paused = true;  // autopaused
    Machine m(f); ready(m);
    m.register_timer(kT1);
    Ticket tk{}; m.acquire(kA, kT1, &tk);
    f.game_unpause(m, kT1);  // recovery
    check(f.timers[kT1].paused && f.timers[kT1].unpause_calls == 0, "suppressed while held");
    check(!m.status(kT1).game_intent, "recorded: game intent running");
    m.release(tk);
    check(!f.timers[kT1].paused && f.timers[kT1].unpause_calls == 1, "release applies it: 1 Unpause, running");
}

void r4_game_pause_repairs_external_clear() {
    section("R4/F3: game Pause on a held timer found unpaused is forwarded");
    Fake f;
    Machine m(f); ready(m);
    m.register_timer(kT1);
    Ticket tk{}; m.acquire(kA, kT1, &tk);
    f.game_pause(m, kT1);
    check(f.timers[kT1].pause_calls == 1, "flag set: game Pause still suppressed (0 calls)");
    f.timers[kT1].paused = false;  // raw clear behind the lease
    f.game_pause(m, kT1);
    check(f.timers[kT1].pause_calls == 2 && f.timers[kT1].paused, "flag clear: forwarded, paused again");
    check(m.diag(Diag::GamePauseRepaired) == 1, "GamePauseRepaired counted");
    check(m.status(kT1).game_intent && m.status(kT1).tool_leases == 1, "intent paused, lease kept");
    m.release(tk);
    check(f.timers[kT1].paused && f.timers[kT1].unpause_calls == 0, "game pause persists after release");
}

void r5_set_hooks_status() {
    section("R5/F4: set_hooks_installed reports refusal");
    Fake f;
    Machine m(f);
    check(m.set_hooks_installed(true, true) == Status::Ok, "install ok");
    m.register_timer(kT1);
    Ticket tk{}; m.acquire(kA, kT1, &tk);
    check(m.set_hooks_installed(false, false) == Status::LeasesHeld, "withdraw while leased -> LeasesHeld");
    check(m.ownership_available(), "state unchanged");
    m.release(tk);
    check(m.set_hooks_installed(false, false) == Status::Ok, "withdraw after release ok");
}

void r6_begin_load_failure_kept() {
    section("R6/F5: failed begin_load restore stays visible");
    Fake f;
    Machine m(f); ready(m);
    m.register_timer(kT1);
    m.register_timer(kT2);
    Ticket tk{}; m.acquire(kA, kT1, &tk);
    f.timers[kT1].refuse_unpause = true;
    const std::uint32_t gen = m.generation();
    check(m.begin_load() == Status::CleanupIncomplete, "begin_load -> CleanupIncomplete");
    const auto fails = m.load_cleanup_failures();
    check(fails.size() == 1 && fails[0].timer == kT1 && fails[0].generation == gen,
          "failure kept: timer id and generation");
    check(m.diag(Diag::LoadCleanupFailed) == 1, "LoadCleanupFailed counted");
    const int calls = f.total_calls;
    m.retry_cleanup();
    m.end_load();
    m.retry_cleanup();
    check(f.total_calls == calls, "no native call on the expired timer afterwards");
}

void r7_shutdown_latch() {
    section("R7/F6: acquire and register refused after shutdown");
    Fake f;
    Machine m(f); ready(m);
    m.register_timer(kT1);
    m.shutdown();
    Ticket tk{};
    check(m.acquire(kA, kT1, &tk) == Status::ShutDown, "acquire -> ShutDown");
    check(m.register_timer(kT2) == Status::ShutDown, "register -> ShutDown");
    check(f.calls(kT1) == 0 && m.shut_down(), "no native call, latched");
}

void f7_acquire_all() {
    section("F7: all-or-nothing multi-timer acquire");
    constexpr TimerId kT3 = 0x3000;
    Fake f;
    Machine m(f); ready(m);
    m.register_timer(kT1); m.register_timer(kT2); m.register_timer(kT3);
    const TimerId ts[3] = {kT1, kT2, kT3};
    Ticket out[3]{};
    check(m.acquire_all(kA, ts, out) == Status::Ok, "acquire_all ok");
    check(f.timers[kT1].paused && f.timers[kT2].paused && f.timers[kT3].paused, "all paused");
    check(out[2].timer == kT3 && out[2].timer_epoch == m.status(kT3).epoch, "tickets filled");
    for (const Ticket& t : out) m.release(t);
    check(m.lease_count() == 0 && !f.timers[kT1].paused, "released");

    // Key already holds T1; T3 unreadable -> roll back T2 only.
    Ticket pre{}; m.acquire(kB, kT1, &pre);
    f.timers[kT3].unreadable = true;
    const int p2 = f.timers[kT2].pause_calls, u2 = f.timers[kT2].unpause_calls;
    std::size_t bad = 99;
    check(m.acquire_all(kB, ts, out, &bad) == Status::ReadbackFailed, "failure status propagated");
    check(bad == 2, "failed index = 2");
    check(m.status(kT1).tool_leases == 1 && f.timers[kT1].paused, "pre-held T1 lease kept");
    check(m.status(kT2).tool_leases == 0 && !f.timers[kT2].paused, "T2 rolled back to running");
    check(f.timers[kT2].pause_calls == p2 + 1 && f.timers[kT2].unpause_calls == u2 + 1, "T2: 1 Pause + 1 Unpause");
    check(m.status(kT3).tool_leases == 0, "T3 no lease");
    Ticket small[2]{};
    check(m.acquire_all(kA, ts, small) == Status::TableFull, "out span too small refused");
    check(m.status(kT2).tool_leases == 0, "no lease from a refused call");
}

void verify_intent_drift() {
    section("F1: verify reports unleased drift");
    Fake f;
    Machine m(f); ready(m);
    m.register_timer(kT1);
    check(m.verify(kT1) == Status::Ok, "consistent -> Ok");
    f.timers[kT1].paused = true;  // raw write
    check(m.verify(kT1) == Status::IntentDrift, "drift -> IntentDrift");
    check(!m.status(kT1).game_intent, "verify does not reseed");
}

}  // namespace

int main() {
    initially_running();
    initially_paused();
    game_pause_while_held();
    game_unpause_while_held();
    pause_unpause_pause_sequence();
    unheld_game_calls_forward();
    two_leases();
    repeated_acquire_idempotent();
    repeated_release();
    unknown_timer_passthrough();
    tool_origin_no_capture();
    failed_hook_install();
    acquire_native_failure();
    pending_cleanup();
    epoch_reset_same_address();
    no_native_call_on_expired();
    dedup();
    per_client_release();
    load_lifecycle();
    shutdown_cases();
    external_mutation();
    table_full();
    r1_unobserved_unpause_reseeded();
    r3_register_before_hooks();
    reseed_not_during_pending();
    r2_recovery_on_game_path_while_held();
    r4_game_pause_repairs_external_clear();
    r5_set_hooks_status();
    r6_begin_load_failure_kept();
    r7_shutdown_latch();
    f7_acquire_all();
    verify_intent_drift();
    std::printf("\n%d checks, %d failures\n", g_checks, g_failures);
    return g_failures == 0 ? 0 : 1;
}

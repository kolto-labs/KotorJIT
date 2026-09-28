// Round-2 reviewer probe: the two cases the Grill #1 policy choice turns on.
// S1 misuse: recovery unpause_timers wrapped in ToolOriginScope while leased.
// S2 legit-scope worst case: fixed-step bracket on a held timer whose flag was
//    raw-cleared behind the lease (ExternalMutation), game intent = paused.
// S3 = S2 with game intent running. S4 = S2 then a game Pause (F3 path).
// "tool-absent" = the flag the timer would hold if the tool never existed.
#include <cstdio>
#include <map>
#include "harness/pause_lease.hpp"
using namespace kp::harness::pause;
struct FT { bool paused = false; int p = 0, u = 0; };
struct Fake : NativeOps {
    std::map<TimerId, FT> t;
    bool original_pause(TimerId id) override { ++t[id].p; t[id].paused = true; return true; }
    bool original_unpause(TimerId id) override { ++t[id].u; t[id].paused = false; return true; }
    std::optional<bool> read_paused(TimerId id) override { return t[id].paused; }
};
static const TimerId T = 0x1000;
static void hooked_pause(Machine& m, Fake& f) { if (m.on_pause_entry(T) == HookDecision::Forward) f.original_pause(T); }
static void hooked_unpause(Machine& m, Fake& f) { if (m.on_unpause_entry(T) == HookDecision::Forward) f.original_unpause(T); }
static void bracket(Machine& m, Fake& f) {  // engine_k1.cpp:2652-2656 under ToolOriginScope
    const bool was = f.t[T].paused;
    Machine::ToolOriginScope s(m);
    if (!was) hooked_pause(m, f);
    if (!was) hooked_unpause(m, f);
}
int main() {
    {   Fake f; f.t[T].paused = true; Machine m(f); m.set_hooks_installed(true, true); m.register_timer(T);
        Ticket k{}; m.acquire({1, 1}, T, &k);
        { Machine::ToolOriginScope s(m); hooked_unpause(m, f); }   // misuse
        m.release(k);
        std::printf("S1 misuse (autopaused, lease, scoped recovery, release): physical=%d tool-absent=0 intent=%d ToolUnpauseSuppressed=%u\n",
                    f.t[T].paused, m.status(T).game_intent, m.diag(Diag::ToolUnpauseSuppressed)); }
    for (int gi = 1; gi >= 0; --gi) {
        Fake f; f.t[T].paused = gi; Machine m(f); m.set_hooks_installed(true, true); m.register_timer(T);
        Ticket k{}; m.acquire({1, 1}, T, &k);
        f.t[T].paused = false;                   // raw clear behind the lease
        const Status v = m.verify(T);
        bracket(m, f);
        const bool held_ok = f.t[T].paused;
        m.release(k);
        std::printf("S%d bracket after raw clear (game intent %d): verify=%s held-after-bracket=%d; after release physical=%d intent=%d tool-absent=0 ToolUnpauseSuppressed=%u\n",
                    gi ? 2 : 3, gi, to_string(v), held_ok, f.t[T].paused, m.status(T).game_intent, m.diag(Diag::ToolUnpauseSuppressed)); }
    {   Fake f; f.t[T].paused = true; Machine m(f); m.set_hooks_installed(true, true); m.register_timer(T);
        Ticket k{}; m.acquire({1, 1}, T, &k);
        f.t[T].paused = false; bracket(m, f); hooked_pause(m, f); m.release(k);
        std::printf("S4 = S2 then game Pause while held: physical=%d intent=%d tool-absent=1\n", f.t[T].paused, m.status(T).game_intent); }
    {   // S5: legal usage only (game-path recovery while leased) -- both cores must agree
        Fake f; f.t[T].paused = true; Machine m(f); m.set_hooks_installed(true, true); m.register_timer(T);
        Ticket k{}; m.acquire({1, 1}, T, &k); hooked_unpause(m, f); bracket(m, f); m.release(k);
        std::printf("S5 legal (autopaused, lease, game-path recovery, bracket, release): physical=%d unpause_calls=%d tool-absent=0\n", f.t[T].paused, f.t[T].u); }
}

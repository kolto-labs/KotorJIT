// Reviewer probe: deterministic reproducers for findings in the pause-lease core.
#include <cstdio>
#include <map>
#include "harness/pause_lease.hpp"
using namespace kp::harness::pause;

struct FT { bool paused = false; int p = 0, u = 0; };
struct Fake : NativeOps {
    std::map<TimerId, FT> t;
    bool original_pause(TimerId id) override { auto& f = t[id]; ++f.p; f.paused = true; return true; }
    bool original_unpause(TimerId id) override { auto& f = t[id]; ++f.u; if (f.paused) f.paused = false; return true; }
    std::optional<bool> read_paused(TimerId id) override { return t[id].paused; }
    void game_pause(Machine& m, TimerId id) { if (m.on_pause_entry(id) == HookDecision::Forward) original_pause(id); }
    void game_unpause(Machine& m, TimerId id) { if (m.on_unpause_entry(id) == HookDecision::Forward) original_unpause(id); }
    void tool_unpause(Machine& m, TimerId id) { Machine::ToolOriginScope s(m); game_unpause(m, id); }
};
constexpr TimerId T = 0x1000;

int main() {
    {   // R1: recovery unpause_timers (ToolOriginScope per report snippet 4) on an unleased timer
        Fake f; f.t[T].paused = true;           // combat autopause holds the world timer
        Machine m(f); m.set_hooks_installed(true, true); m.register_timer(T);
        f.tool_unpause(m, T);                    // operator runs recovery: world runs
        std::printf("R1 after recovery: physical=%d machine.game_intent=%d\n", f.t[T].paused, m.status(T).game_intent);
        Ticket tk{}; m.acquire({1, 1}, T, &tk);
        m.release(tk);
        std::printf("R1 after acquire+release: physical=%d (was running before acquire), pause calls=%d unpause calls=%d\n",
                    f.t[T].paused, f.t[T].p, f.t[T].u);
    }
    {   // R2: recovery during a lease is dropped entirely
        Fake f; f.t[T].paused = true;
        Machine m(f); m.set_hooks_installed(true, true); m.register_timer(T);
        Ticket tk{}; m.acquire({1, 1}, T, &tk);
        f.tool_unpause(m, T);
        m.release(tk);
        std::printf("R2 recovery-while-held then release: physical=%d intent=%d\n", f.t[T].paused, m.status(T).game_intent);
    }
    {   // R3: registered before hooks installed; game unpause unseen
        Fake f; f.t[T].paused = true;
        Machine m(f); m.register_timer(T);
        f.game_unpause(m, T);                    // hooks not yet installed: forwarded, intent not updated
        m.set_hooks_installed(true, true);
        Ticket tk{}; m.acquire({1, 1}, T, &tk);
        m.release(tk);
        std::printf("R3 register-before-hooks: physical=%d (was running before acquire)\n", f.t[T].paused);
    }
    {   // R4: game Pause suppressed while held after an external clear
        Fake f;
        Machine m(f); m.set_hooks_installed(true, true); m.register_timer(T);
        Ticket tk{}; m.acquire({1, 1}, T, &tk);
        f.t[T].paused = false;                   // raw write behind the lease
        f.game_pause(m, T);                      // game wants paused; suppressed
        std::printf("R4 game Pause after external clear: physical=%d intent=%d leases=%d (both want paused)\n",
                    f.t[T].paused, m.status(T).game_intent, m.status(T).tool_leases);
    }
    {   // R5: set_hooks_installed refusal is silent; after shutdown CleanupIncomplete machine still claims hooks
        Fake f;
        Machine m(f); m.set_hooks_installed(true, true); m.register_timer(T);
        Ticket tk{}; m.acquire({1, 1}, T, &tk);
        m.set_hooks_installed(false, false);     // integration reports hooks gone (e.g. uninstall happened)
        std::printf("R5 ownership_available after reporting hooks removed while leased: %d\n", m.ownership_available());
    }
    {   // R6: begin_load with a failing restore drops the pending state
        struct Refuse : Fake { bool original_unpause(TimerId id) override { ++t[id].u; return true; } } f;
        Machine m(f); m.set_hooks_installed(true, true); m.register_timer(T);
        Ticket tk{}; m.acquire({1, 1}, T, &tk);
        Status s = m.begin_load();
        std::printf("R6 begin_load failing restore: status=%s, tracked after=%d, physical=%d\n",
                    to_string(s), m.status(T).tracked, f.t[T].paused);
    }
    {   // R7: acquire after shutdown is still accepted
        Fake f;
        Machine m(f); m.set_hooks_installed(true, true); m.register_timer(T);
        m.shutdown();
        Ticket tk{};
        std::printf("R7 acquire after shutdown: %s\n", to_string(m.acquire({1, 1}, T, &tk)));
    }
    return 0;
}

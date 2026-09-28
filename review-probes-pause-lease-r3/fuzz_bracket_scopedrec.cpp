// Reviewer probe: randomized model check of kp::harness::pause::Machine
// against an independent reference model. Not part of the worktree.
//
// Reference: per timer, shadow = the paused Boolean the timer would have if
// the tool did not exist (receives every game-origin call). Expected
// physical = shadow || leases non-empty. Expected native calls:
//  - acquire, new key, leases empty, !shadow  -> exactly 1 Pause
//  - last release, !shadow                   -> exactly 1 Unpause
//  - game call, leases empty                  -> forwarded (1 call)
//  - game call, leases held                   -> 0 calls
//  - begin_load: drop leases, Unpause iff held && !shadow
// Mode A: hooks installed first, game ops only (plus loads, client release,
//         table overflow, stale tickets).
// Mode B: adds (1) hooks installed after register and (2) tool-origin
//         recovery Unpause (unpause_timers wrapped in ToolOriginScope as the
//         report's snippet 4 says), where the reference treats recovery as an
//         override of the game's state (shadow=false).
#include <cstdio>
#include <cstdlib>
#include <map>
#include <random>
#include <set>
#include <vector>

#include "harness/pause_lease.hpp"

using namespace kp::harness::pause;

struct FT { bool paused = false; int p = 0, u = 0; };
struct Fake : NativeOps {
    std::map<TimerId, FT> t;
    bool original_pause(TimerId id) override { auto& f = t[id]; ++f.p; f.paused = true; return true; }
    bool original_unpause(TimerId id) override { auto& f = t[id]; ++f.u; f.paused = false; return true; }
    std::optional<bool> read_paused(TimerId id) override { return t[id].paused; }
};

struct RefTimer { bool shadow = false; std::set<std::pair<unsigned, unsigned long long>> leases; };
struct RefTicket { Ticket tk; unsigned gen; };

static const TimerId kTimers[2] = {0x1000, 0x2000};

int run(int mode, unsigned seed, int steps, bool verbose) {
    std::mt19937 rng(seed);
    auto rnd = [&](int n) { return static_cast<int>(rng() % n); };
    Fake f;
    Machine m(f);
    std::map<TimerId, RefTimer> ref;
    unsigned ref_gen = 1;
    std::vector<RefTicket> tickets;
    bool hooks = false;

    for (TimerId id : kTimers) f.t[id].paused = rnd(2);
    if (mode == 0 || rnd(2)) { m.set_hooks_installed(true, true); hooks = true; }
    for (TimerId id : kTimers) { m.register_timer(id); ref[id].shadow = f.t[id].paused; }

    for (int step = 0; step < steps; ++step) {
        const TimerId id = kTimers[rnd(2)];
        RefTimer& r = ref[id];
        FT before = f.t[id];
        int exp_p = 0, exp_u = 0;
        int op = rnd(mode == 0 ? 8 : 11);
        const char* name = "";
        if (!hooks && op != 8) { m.set_hooks_installed(true, true); hooks = true; }
        switch (op) {
        case 0: case 1: {  // acquire
            name = "acquire";
            LeaseKey k{static_cast<std::uint32_t>(1 + rnd(3)), static_cast<std::uint64_t>(1 + rnd(4))};
            std::pair<unsigned, unsigned long long> kk{k.client, k.request};
            Ticket tk{};
            Status s = m.acquire(k, id, &tk);
            Status es;
            if (r.leases.count(kk)) es = Status::Ok;
            else if (r.leases.size() >= Machine::kMaxLeasesPerTimer) es = Status::TableFull;
            else { if (r.leases.empty() && !r.shadow) exp_p = 1; r.leases.insert(kk); es = Status::Ok; }
            if (s != es) { std::printf("seed %u step %d acquire status %s want %s\n", seed, step, to_string(s), to_string(es)); return 1; }
            if (s == Status::Ok) tickets.push_back({tk, ref_gen});
            break; }
        case 2: {  // release a random remembered ticket
            name = "release";
            if (tickets.empty()) break;
            RefTicket rt = tickets[rnd(static_cast<int>(tickets.size()))];
            RefTimer& rr = ref[rt.tk.timer];
            before = f.t[rt.tk.timer];
            std::pair<unsigned, unsigned long long> kk{rt.tk.key.client, rt.tk.key.request};
            Status es;
            if (rt.gen != ref_gen) es = Status::StaleTicket;
            else if (!rr.leases.count(kk)) es = Status::AlreadyReleased;
            else { rr.leases.erase(kk); es = Status::Ok; if (rr.leases.empty() && !rr.shadow) exp_u = 1; }
            Status s = m.release(rt.tk);
            if (s != es) { std::printf("seed %u step %d release status %s want %s\n", seed, step, to_string(s), to_string(es)); return 1; }
            if (rt.tk.timer != id) {  // check the released timer instead
                const FT& a = f.t[rt.tk.timer];
                if (a.p - before.p != 0 || a.u - before.u != exp_u) { std::printf("seed %u step %d release calls\n", seed, step); return 1; }
                exp_u = 0; before = f.t[id];
            }
            break; }
        case 3: {  // release_client
            name = "release_client";
            unsigned c = 1 + rnd(3);
            std::map<TimerId, int> eu;
            std::map<TimerId, FT> b;
            for (TimerId t : kTimers) {
                b[t] = f.t[t];
                RefTimer& x = ref[t];
                bool had = false;
                for (auto it = x.leases.begin(); it != x.leases.end();) if (it->first == c) { it = x.leases.erase(it); had = true; } else ++it;
                eu[t] = (had && x.leases.empty() && !x.shadow) ? 1 : 0;
            }
            m.release_client(c);
            for (TimerId t : kTimers) if (f.t[t].u - b[t].u != eu[t] || f.t[t].p != b[t].p) { std::printf("seed %u step %d release_client calls\n", seed, step); return 1; }
            before = f.t[id];
            break; }
        case 4: case 5: {  // game pause
            name = "game_pause";
            r.shadow = true;
            if (m.on_pause_entry(id) == HookDecision::Forward) f.original_pause(id);
            if (r.leases.empty()) exp_p = 1;
            break; }
        case 6: {  // game unpause
            name = "game_unpause";
            r.shadow = false;
            if (m.on_unpause_entry(id) == HookDecision::Forward) f.original_unpause(id);
            if (r.leases.empty()) exp_u = 1;
            break; }
        case 7: {  // load with same-address reuse
            name = "load";
            std::map<TimerId, FT> b;
            std::map<TimerId, int> eu;
            for (TimerId t : kTimers) { b[t] = f.t[t]; eu[t] = (!ref[t].leases.empty() && !ref[t].shadow) ? 1 : 0; }
            m.begin_load();
            for (TimerId t : kTimers) if (f.t[t].u - b[t].u != eu[t] || f.t[t].p != b[t].p) { std::printf("seed %u step %d begin_load calls\n", seed, step); return 1; }
            ++ref_gen;
            for (TimerId t : kTimers) { f.t[t].paused = rnd(2); ref[t] = RefTimer{}; ref[t].shadow = f.t[t].paused; }
            m.end_load();
            for (TimerId t : kTimers) m.register_timer(t);
            before = f.t[id];
            break; }
        case 8: {  // mode B: game call while hooks absent (only before install)
            name = "game_unpause_unhooked";
            if (hooks) { name = "noop"; break; }
            r.shadow = false;
            if (m.on_unpause_entry(id) == HookDecision::Forward) f.original_unpause(id);
            exp_u = 1;
            break; }
        case 9: {  // mode B: recovery unpause_timers under ToolOriginScope
            name = "recovery_unpause";
            { Machine::ToolOriginScope s(m);
              if (m.on_unpause_entry(id) == HookDecision::Forward) f.original_unpause(id); }
            r.shadow = false;
            if (r.leases.empty()) exp_u = 1;
            break; }
        case 10: {  // fixed-step bracket, engine_k1.cpp:2652-2656, inside ToolOriginScope
            name = "fixed_step_bracket";
            const bool was_paused = f.t[id].paused;
            { Machine::ToolOriginScope s(m);
              if (!was_paused && m.on_pause_entry(id) == HookDecision::Forward) f.original_pause(id);
              /* SetFixedSnapshotRate here */
              if (!was_paused && m.on_unpause_entry(id) == HookDecision::Forward) f.original_unpause(id); }
            if (!was_paused) { exp_p = 1; exp_u = 1; }
            break; }
        }
        const FT& a = f.t[id];
        const bool exp_phys = r.shadow || !r.leases.empty();
        if (a.p - before.p != exp_p || a.u - before.u != exp_u || a.paused != exp_phys) {
            if (verbose) std::printf("DIVERGE mode %d seed %u step %d op %s timer %x: calls p%+d u%+d want p%+d u%+d, phys %d want %d (shadow %d leases %zu, machine intent %d)\n",
                mode, seed, step, name, (unsigned)id, a.p - before.p, a.u - before.u, exp_p, exp_u, a.paused, exp_phys,
                r.shadow, r.leases.size(), m.status(id).game_intent);
            return 2;
        }
        if (static_cast<int>(r.leases.size()) != m.status(id).tool_leases) { std::printf("seed %u lease count\n", seed); return 1; }
    }
    return 0;
}

int main(int argc, char** argv) {
    const int seeds = argc > 1 ? std::atoi(argv[1]) : 20000;
    for (int mode = 0; mode < 2; ++mode) {
        int fails = 0, first = -1;
        for (int s = 1; s <= seeds; ++s) {
            int rc = run(mode, s, 400, false);
            if (rc) { ++fails; if (first < 0) first = s; }
        }
        std::printf("mode %c: %d seeds x 400 steps, %d diverging seeds\n", mode ? 'B' : 'A', seeds, fails);
        if (first > 0) run(mode, first, 400, true);
    }
    return 0;
}

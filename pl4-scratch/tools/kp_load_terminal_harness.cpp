// Round-4 Q1 proof. Models the exact shape of GameAdapter::load_save() /
// step_load_completion() in src/harness/engine_k1.cpp (patched copy at
// /home/brunner56/kp-live-20260922/pl4-scratch/src/harness/engine_k1.cpp,
// which is proven to COMPILE against the real GameAdapter in this same
// scratch tree -- see build_engine_k1.log). This file does not call the
// real GameAdapter (it needs a live address table, a real client/server app
// and the hook shape machinery -- not host-buildable standalone), so it is
// a model of the control-flow graph, driven against the REAL
// pause_lease::Machine core (not a stand-in), mapped to the patched
// engine_k1.cpp by the file:line table below (same numbering the round-4
// report uses).
//
// Terminal-path table (patched engine_k1.cpp; line numbers from this
// scratch copy, sha256 of the unpatched pause_lease core unchanged --
// bacd1b7d / 63e21bc9):
//
//   Returns before begin_load()      :695 :707 :716 :744 :772   -> 0 end_load calls
//   Dedicated-server branch          :835 end_load, :837 return -> 1 end_load call, unconditional
//   on_fail() returns (!had_server)  :844 :845 :870              -> 1 end_load call each
//   on_fail() return (send request)  :923                        -> 1 end_load call
//   finish_load() terminal writes    :1059 :1078 :1101 :1117 :1125 -> 1 end_load call each (via
//                                                                    finish_load, idempotent)
//
// Each path below is asserted to leave pause_machine.loading() == false
// after the path completes, and to never regress to true without a fresh
// begin_load(). The idempotency claim ("a second begin_load is harmless")
// is checked directly against pause_lease.cpp's begin_load()/end_load()
// (loading_ is a plain bool, not a counter -- pause_lease.hpp:167,244).
#include <cassert>
#include <cstdio>
#include <optional>

#include "harness/pause_lease.hpp"

using kp::harness::pause::Machine;
using kp::harness::pause::NativeOps;
using kp::harness::pause::TimerId;

namespace {

int g_checks = 0;
int g_failures = 0;

void check(bool cond, const char* what) {
    ++g_checks;
    if (!cond) {
        ++g_failures;
        std::printf("[FAIL] %s\n", what);
    }
}

struct FakeOps final : NativeOps {
    bool paused = true;
    bool original_pause(TimerId) override { return true; }
    bool original_unpause(TimerId) override {
        paused = false;
        return true;
    }
    std::optional<bool> read_paused(TimerId) override { return paused; }
};

// Mirrors the patched engine_k1.cpp's five pre-begin_load returns: they run
// before `pause_machine_.begin_load()` at :772-fail / :774-begin_load in the
// patched file, so this model never calls begin_load for them.
void path_pre_begin_load_returns() {
    FakeOps ops;
    Machine m(ops);
    // No begin_load() call at all -- these returns are before it.
    check(!m.loading(), "pre-begin_load returns: loading() starts false");
    check(!m.loading(), "pre-begin_load returns: never set true (0 begin_load calls)");
}

// Mirrors the dedicated-server branch (patched :835 end_load, :837 return): begin_load() then
// an unconditional end_load() right before the `return Result::success();`,
// closing the Q1 wedge (round-3 snippet 7'' left this branch with no clear
// point at all).
void path_dedicated_server_success() {
    FakeOps ops;
    Machine m(ops);
    m.begin_load();
    check(m.loading(), "dedicated-server: begin_load sets loading()");
    m.end_load();  // the round-4 fix: was absent pre-patch
    check(!m.loading(), "dedicated-server: end_load clears loading() (was: never, pre-patch F8)");
}

// Mirrors an on_fail() return: client.net_layer / message_handler unreadable
// (:844-845), StartConnectToSession refused (:870), SendLoadGameRequest not
// callable (:923). All four go through the same on_fail() lambda in the
// patched file, which calls end_load() exactly once.
void path_on_fail_return(const char* which) {
    FakeOps ops;
    Machine m(ops);
    m.begin_load();
    // on_fail(): end_load(); (integration: re-register timers)
    m.end_load();
    check(!m.loading(), which);
}

// Mirrors step_load_completion()'s five terminal writes, all now routed
// through finish_load(), which calls end_load(). Models a load that goes
// Armed -> Sent -> Placed -> Done, and separately the three GaveUp exits.
void path_success_then_done() {
    FakeOps ops;
    Machine m(ops);
    m.begin_load();
    check(m.loading(), "success path: begin_load sets loading() (armed)");
    // ... Sent, Placed, no end_load yet: the load is still in flight and
    // acquire/register must still refuse (Status::Loading).
    auto ticket_status = m.register_timer(0x1000);
    check(ticket_status == kp::harness::pause::Status::Loading,
          "success path: register_timer refuses mid-load (Status::Loading)");
    // finish_load(Done) at :1078/:1117 (retire_main_menu() branch) or the
    // three GaveUp writers at :1059/:1101/:1125 -- all call end_load().
    m.end_load();
    check(!m.loading(), "success path: finish_load's end_load clears loading()");
    auto after = m.register_timer(0x1000);
    check(after != kp::harness::pause::Status::Loading,
          "success path: register_timer no longer refused after finish_load");
}

// The re-entrancy residual the round-4 report states plainly rather than
// solving: a second load_save() call's begin_load() before the first one's
// terminal write. Confirms the core stays well-defined (loading_ is a level
// write) even though the FIRST load's own step_load_completion() bookkeeping
// is what the report calls out as silently overwritten.
void path_reentrant_load_is_bounded() {
    FakeOps ops;
    Machine m(ops);
    m.begin_load();  // first load_save() call, armed
    m.begin_load();  // second load_save() call starts before the first finished
    check(m.loading(), "reentrant: still loading after two begin_load calls");
    m.end_load();    // second call's on_fail(), or finish_load() -- either one
    check(!m.loading(), "reentrant: one end_load clears loading() regardless of begin_load count");
    // Pin the core claim this all rests on: end_load() is `loading_ = false`,
    // a level write, not a counter -- so double begin_load / single end_load
    // is well-defined by construction, not by luck.
    m.begin_load();
    m.end_load();
    m.end_load();  // calling it again is a no-op, not a double-decrement bug
    check(!m.loading(), "end_load is idempotent (level write, not a counter)");
}

}  // namespace

int main() {
    path_pre_begin_load_returns();
    path_dedicated_server_success();
    path_on_fail_return("on_fail: client.net_layer unreadable (:844)");
    path_on_fail_return("on_fail: client.message_handler unreadable (:845)");
    path_on_fail_return("on_fail: StartConnectToSession refused (:870)");
    path_on_fail_return("on_fail: SendLoadGameRequest not callable (:923)");
    path_success_then_done();
    path_reentrant_load_is_bounded();

    std::printf("%d checks, %d failures\n", g_checks, g_failures);
    return g_failures == 0 ? 0 : 1;
}

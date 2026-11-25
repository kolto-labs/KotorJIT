// Deferred work: registertimer / removetimer, driven from the OnTick hook.
//
// This is the replacement for DelayCommand, and that is not a convenience --
// routine 7 DelayCommand takes an `action`, which the NWScript compiler emits
// as STORE_STATE bytecode capturing a closure. There is no value a Lua script
// can push that the VM will accept there. DelayCommand, AssignCommand (6) and
// ActionDoCommand (294) are the three K1 routines the bridge cannot marshal,
// and this is what a script uses instead.
//
//   local id = kp.registertimer(1500, "on_bang", { n = 3 })
//   function on_bang(id, count, data)
//       kp.feedback("bang " .. count)
//       return count < data.n            -- true renews, anything else stops
//   end
//   kp.removetimer(id)
//
// The callback is either a STRING or a FUNCTION.
//
//   A name is resolved at fire time against the script's globals, so a typo is
//   invisible until the timer expires, and redefining the global changes what
//   the next firing runs.
//
//   A function is held by a registry reference from registration until the
//   timer ends, so a closure keeps its upvalues across firings:
//
//     local hits = 0
//     kp.registertimer(500, function(id, count) hits = hits + 1; return count < 3 end)
//
//   The reference is released exactly once: on completion (anything but true
//   or 1 returned), on removetimer, on a throw, or with the state when it
//   closes. A function value cannot leak into the next generation of a
//   reloaded script, because timers never cross a state close (below).
//   Errors from a function timer are charged to "function <source>:<line>",
//   the place the function was defined, so every timer made from one closure
//   definition shares one error budget, as every timer naming one global does.
//   A C function (kp.registertimer(ms, error)) has no source line, so it is
//   charged to "function [C] <address>": one budget per C function.
//
//   A name is looked up inside a protected call, so a strict-globals __index
//   on _G that raises is an ordinary timer error: reported, charged to the
//   name, and the timer is cancelled. It is not counted as a firing.
//
// Anything else in the callback slot is an argument error at the call site.
//
// THE DELAY is a finite number of milliseconds from 0 to kMaxDelayMs
// (2^32 - 1, about 49.7 days). NaN, infinity, negatives and anything larger
// are an argument error; they used to be accepted and, for infinity, fire at
// once.
// Both forms share one scheduler, one id space and the same arguments
// (id, count, data).
//
// SCHEDULING. Timers fire from pump(), which the OnTick hook body calls once
// per frame with a millisecond clock. Everything due at that instant is
// collected first and fired afterwards, one at a time, with each timer looked
// up again immediately before it runs -- a callback is allowed to register
// timers, cancel timers, or get its own script quarantined, and none of those
// may invalidate the loop that is walking them. A renewed timer is rescheduled
// from now, not from when it was due, so a frame hitch does not turn into a
// burst of catch-up firings.
//
// OWNERSHIP AND RELOAD. A timer belongs to one lua_State. Ids are unique across
// the whole process, but removetimer only matches ids belonging to the calling
// state, so one script cannot cancel another's timer. Ids live with the
// lua_State that registered them.
//
// A reload drops that script's timers, and the script re-registers whatever it
// wants when its chunk runs again. This is the sensible answer rather than the
// lazy one: a timer holds a Lua registry reference to its userdata and names a
// global function, and both of those live in the lua_State that a reload
// closes. Carrying an id across generations would mean handing a script back an
// id whose callback and userdata are gone, and letting removetimer(id) cancel a
// timer belonging to a different generation of the same file. Re-registration
// at the top of the chunk is a line of Lua; a timer that survives into a state
// where its callback does not exist is a bug that fires later, somewhere else.
//
// Nothing here needs the runtime to remember to clean up. Each state carries a
// finalised sentinel in its own registry, so lua_close -- from unload, reload
// or quarantine -- drops that state's timers on the way out. Once the sentinel
// has been finalised, registertimer on that state raises: a script's own __gc
// can run after the sentinel's during lua_close, and a timer registered there
// would otherwise outlive its state.
//
// TWO DIVERGENCES FROM data/hostapi.toml, which declares this surface as
// kp.timer.* and has no generator yet. That file makes cancelling the running
// timer a no-op; here it raises, because removing a timer from inside its own
// callback is a bug a script should see at the call site. A throwing callback
// is fatal to that timer: the error is charged to the script's budget AND the
// timer is cancelled, so quarantine is reached across several timers rather
// than by one repeater failing over and over. Cancelling is what actually
// stops the forever-traceback; the budget is what stops the script.
//
// The same file corroborates the renewal rule independently: "a slow frame does
// not fire the timer twice to catch up -- it fires once and the next due time
// is measured from now."
#pragma once

#include <cstddef>
#include <cstdint>

struct lua_State;

namespace kp::api {

// Installs kp.registertimer and kp.removetimer into this state, and the
// sentinel that drops this state's timers when it closes.
void register_timers(lua_State*);

namespace timers {

// The largest delay kp.registertimer accepts, in milliseconds.
inline constexpr std::uint64_t kMaxDelayMs = 0xFFFFFFFFull;

// Fire everything due at `now_ms`. Returns how many callbacks ran.
//
// `game_tick` is stamped onto any error a callback raises, so a script error
// from a timer reads the same as one from an event callback. The OnTick body
// has both numbers to hand, and calls this after it dispatches OnTick:
//
//     h.dispatch(*ev, args);
//     kp::api::timers::pump(kp::api::timers::now_ms(), h.tick());
//     h.advance_tick();
//
// After dispatch rather than before, so a script that registers a timer from
// OnTick does not have that timer fire on the same frame.
unsigned pump(std::uint64_t now_ms, std::uint64_t game_tick);

// A monotonic millisecond clock, for a caller that has no better one. Monotonic
// on purpose: a wall clock that steps backwards would leave every timer due.
std::uint64_t now_ms();

// The scheduler's notion of "now", which is the caller's to define.
//
// registertimer schedules at clock() + delay and pump() sets clock() to the
// time it was handed, so the two always agree. That matters more than it looks:
// if registration read a real clock while pump was driven from a synthetic one,
// every timer would be due immediately or never, and the difference would only
// show up outside the game. Until someone sets it, clock() is now_ms().
void          set_clock(std::uint64_t now_ms);
std::uint64_t clock();
std::uint64_t tick();

// A callback that throws counts against its script's error budget and is
// quarantined at the same threshold as any event callback. The budget lives in
// HostConfig, which has no accessor, so the runtime passes it here. The default
// matches HostConfig's own.
void set_error_budget(unsigned);

// Drop every timer belonging to this state. The finaliser calls this, so the
// runtime does not have to; it is exposed for a caller that wants to cancel a
// script's timers without closing it.
//
// Registry references held by those timers (data and function callbacks) are
// not released, because the only caller that matters is a state on its way out
// and releasing them there would touch a half-torn-down state. Calling this on
// a live state leaks those refs until the state closes.
void forget_state(lua_State*);

// How many timers are scheduled, in total or for one state. Diagnostics.
std::size_t pending();
std::size_t pending(lua_State*);

}  // namespace timers
}  // namespace kp::api

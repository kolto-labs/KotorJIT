// How several scripts share one event.
//
// The rule, stated once so the implementation and the docs cannot drift:
//
//   Every loaded script that defines the callback is called, in priority order.
//   The FIRST script to return a usable value claims the result. Later scripts
//   still run, and are told their answer will not be used. A script that returns
//   nothing, or something that will not convert, is abstaining -- not voting.
//   If nobody claims, a per-event fallback applies.
//
// Two consequences that surprise people, both deliberate:
//
//   * Abstaining is a failed conversion, not a nil check. Returning a
//     non-numeric string abstains. Returning "5" where a number is wanted
//     succeeds. Returning 2 where a boolean is wanted yields false, because the
//     test is `== 1`.
//   * Multi-value results are all-or-nothing. If the first slot will not
//     convert, the whole tuple is discarded and the script abstained.
//
// Blocking an event and telling the engine it failed are different decisions --
// see EngineReturn.
#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace kp::events {

enum class ValueType { None, Bool, Int, Float, String, Object };

// What happens when no script claims the result.
enum class Fallback {
    None,      // event has no result
    True,      // allow (most blockable events)
    False,     // deny -- fail closed
    Identity,  // return the input unchanged
};

// What the ENGINE sees when a script blocks the event.
//
// This is separate from blocking on purpose. CVirtualMachineInternal::RunScript
// returns 1 for "ran" and 0 for "did not", and 0 propagates into the caller's
// failure path. A script returning false means "do not run the game's handler",
// which is not the same as "the script failed to run".
//
// Default is ReportSuccess: blocking stays invisible to the engine. Claiming
// failure invites error handling to fire and produces bugs that surface far
// from their cause. A script that genuinely wants to signal failure asks for it.
enum class EngineReturn {
    ReportSuccess,  // default: suppress the handler, tell the engine it ran
    ReportFailure,  // suppress and report failure; opt-in only
    Passthrough,    // event is not blockable
};

struct Argument {
    std::string name;
    ValueType   type = ValueType::None;
    // How the EventHandler cave fills this slot. Empty for events the runtime
    // raises itself (OnTick, OnRunScript, ...). Values match the draft:
    // "this", "caller", "calendar_day", "time_of_day", "int_params[N]",
    // "float_params[N]", "string_params[N]", "object_params[N]".
    std::string source;
};

// Layer-1 id that carries a CScriptEvent*. event_type is only meaningful then.
// 0x18 and 0x1A also carry a CScriptEvent, but those match on outer id alone.
inline constexpr int kSignalEvent = 10;
inline constexpr std::uint32_t kObjectInvalid = 0x7f000000;

struct EventContract {
    std::string            lua_name;      // e.g. "OnCreatureDeath"
    std::string            hook_site;     // key into the address table
    std::vector<Argument>  args;
    std::vector<ValueType> results;       // empty = void event
    Fallback               fallback = Fallback::None;
    bool                   blocking = false;
    EngineReturn           engine_return = EngineReturn::Passthrough;
    // -1 = not keyed by EventHandler identity (OnRunScript, OnTick, lifecycle).
    int                    outer_event_id = -1;
    // -1 = unused. Meaningful only when outer_event_id == kSignalEvent.
    int                    event_type = -1;
};

// A void event has zero results, so the conversion that decides "claimed"
// trivially succeeds and the first script to define it always claims. That is
// faithful to the model we are matching, but it means every later script sees
// relevant == false, which surprises people.
//
// 29 of the current events are void. Defined in dispatch.cpp so tools can report
// it rather than each rediscovering the rule.
bool always_claimed_by_first(const EventContract&);

// The outcome of dispatching one event across all loaded scripts.
struct Outcome {
    bool        claimed = false;
    std::string claimed_by;     // script name, for diagnostics
    bool        bool_result = false;
    std::int64_t int_result = 0;
    std::string string_result;

    // These reconcile: called == abstained + errored + (claimed ? 1 : 0) + ignored.
    // Counting only abstentions before a claim, as an earlier version did, made
    // called=2/abstained=0 mean either "one script voted and lost" or "one
    // script crashed" -- the two an operator most needs to tell apart.
    unsigned called = 0;        // scripts invoked
    unsigned abstained = 0;     // returned nothing usable, before OR after a claim
    unsigned errored = 0;       // threw; its answer, if any, was discarded
    unsigned ignored = 0;        // answered, but someone had already claimed
};

// Whether Lua claimed a block, and what a returning cave should tell the engine.
// EventHandler is void -- skip_original is the only lever there.
struct BlockVerdict {
    bool skip_original = false;
    int  engine_result = 1;
};

BlockVerdict blocking_verdict(const EventContract&, const Outcome&);

}  // namespace kp::events

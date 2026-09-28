// kp.scripts, kp.scriptname and kp.scriptdir: the Lua face of the script host.
//
//   kp.scripts.list()          -> { {name, path, state, generation, priority,
//                                    errors, timers, last_error}, ... }
//   kp.scripts.load(name)      -> request id
//   kp.scripts.unload(name)    -> request id
//   kp.scripts.reload(name)    -> request id
//   kp.scripts.result(id)      -> "pending" | {ok, error, generation, name, op} | nil
//   kp.scriptname()            -> the calling script's name, nil in the console
//   kp.scriptdir()             -> the directory scripts load from, "" before start
//
// load, unload and reload never act on the spot. They queue a request on the
// host and return its id; the runtime services the queue from the tick, outside
// every Lua callback. A script can therefore unload or reload itself from its
// own handler or timer: its state stays valid until the callback has returned
// and the tick reaches the service point. The console sees "pending" until then.
//
// `name` is a script's file stem ("10_cover", not "10_cover.lua" or a path).
// load of a name the host does not hold must match a .lua file in the script
// directory listing; the script is held under the on-disk spelling, and a name
// that is the same file as a held script (case variant, alias) is refused.
//
// The queue is bounded (lua::Host::request): a repeat of a still-queued
// request returns the same id, at most 64 wait, at most 16 run per tick, and a
// script cannot load or reload itself from its own OnScriptLoad. Refused
// requests still return an id whose result says why.
//
// Reload order: the new chunk's top level runs, then the old generation's
// OnScriptUnload, then the old state closes, then the new OnScriptLoad. Do
// native setup in OnScriptLoad, not at top level, or the old OnScriptUnload
// undoes it.
//
// result(id) answers nil for anything that is not a positive integer id
// (fractions, infinities, NaN, out-of-range numbers), the same as an unknown id.
//
// None of these names is an NWScript routine name in any case spelling. NWScript
// stays reachable only through nwscript.call.
#pragma once

struct lua_State;

namespace kp::lua { class Host; }

namespace kp::api::scripts {

// The host every state's kp.scripts talks to. The runtime binds it once the
// host exists and binds nullptr before the host goes away. While unbound,
// kp.scripts.* raise a Lua error and kp.scriptdir() returns "".
void bind_host(lua::Host*);
lua::Host* bound_host();

// Install kp.scripts, kp.scriptname and kp.scriptdir into this state.
void register_all(lua_State*);

}  // namespace kp::api::scripts

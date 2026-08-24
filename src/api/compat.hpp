// Both API dialects, natively.
//
// Scripts for this kind of runtime were written against one of two Halo server
// mods, and the two never agreed on anything. Names differ -- `readbyte` versus
// `read_byte`, `say` versus `say_all` -- and so does the event model: one finds
// `function OnTick()` by looking for it, the other expects
// `register_callback(cb.EVENT_TICK, "handler")` at runtime.
//
// The usual answer is a compatibility module written in Lua that people paste
// into their script. It costs a table lookup on every call, it can only wrap
// what already exists, and it breaks whenever either side moves. Doing it here
// instead means the bridging happens once, at registration, and a script author
// writes whichever dialect they already know without requiring anything.
//
// Everything below is installed on every script state. Nothing is opt-in,
// because a script that has to ask for compatibility has not got it.
#pragma once

struct lua_State;

namespace kp::lua { class Script; }

namespace kp::api::compat {

// Aliases, the cb table, register_callback, and the small version globals the
// two dialects expect to find. Call after every other module has registered,
// since an alias can only point at a function that already exists.
void install(lua_State*);

// Route Lua's print through the runtime log.
//
// Worth doing even though print already "works": under Wine the game's stdout is
// block-buffered to a redirected file, so a script's output sits in a 4 KB
// buffer and appears minutes late or not at all. That is indistinguishable from
// the script never running, and it cost real debugging time. The runtime log is
// flushed per line and is where someone looks anyway.
void install_print(lua_State*);

// Map a SAPP event constant to the event name this runtime raises. Empty means
// the constant exists but nothing raises it -- a Halo concept with no KOTOR
// counterpart, like teams or vehicles.
const char* event_for_constant(int constant);
const char* event_for_name(const char* sapp_name);

// How many aliases and event constants are installed, for the log line and for
// anything that wants to report the surface.
unsigned alias_count();
unsigned event_constant_count();

}  // namespace kp::api::compat

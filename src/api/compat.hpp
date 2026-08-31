// Odyssey host names, plus a second spelling of each, installed natively.
//
// The C modules register the names the corpus uses: readbyte, registertimer,
// GetFirstPC, SendMessageToPC. Scripts may also write the underscored form.
// Both spellings point at the same C function, bound once at registration.
//
// Events use the lua_name values from data/events.toml, taken from the
// decompiled dispatch: function OnTick(), or
// register_callback(cb.OnModulePlayerEnter, "handler"). The player attaching
// is OnModulePlayerEnter, not EVENT_JOIN. The PC is GetFirstPCObject, not
// getplayer(slot).
//
// Everything below is installed on every script state. Nothing is opt-in,
// because a script that has to ask for compatibility has not got it.
#pragma once

#include <string>

struct lua_State;

namespace kp::lua { class Script; }

namespace kp::api::compat {

// Aliases, the cb table, register_callback, and the host identity globals.
// Call after every other module has registered, since an alias can only point
// at a function that already exists.
//
// `game_dir` becomes kp.gamedir()'s return value, captured once as a Lua
// upvalue rather than recomputed per call: the directory the executable lives
// in cannot change during a process's lifetime, and runtime.cpp already knows
// it from Config, which is where every other module's install() also gets its
// state.
void install(lua_State*, const std::string& game_dir);

// Route Lua's print through the runtime log.
//
// Worth doing even though print already "works": under Wine the game's stdout is
// block-buffered to a redirected file, so a script's output sits in a 4 KB
// buffer and appears minutes late or not at all. That is indistinguishable from
// the script never running, and it cost real debugging time. The runtime log is
// flushed per line and is where someone looks anyway.
void install_print(lua_State*);

// Map a cb constant to the event name this runtime raises. Empty means the
// constant exists but nothing raises it yet.
const char* event_for_constant(int constant);
const char* event_for_name(const char* name);

// How many aliases and event constants are installed, for the log line and for
// anything that wants to report the surface.
unsigned alias_count();
unsigned event_constant_count();

}  // namespace kp::api::compat

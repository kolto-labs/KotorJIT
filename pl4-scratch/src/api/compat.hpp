// Native events, host identity and harness facilities under kp only.
// The dispatcher still discovers script-defined global On* handlers for legacy
// compatibility. Explicit bindings use kp.events.register(kp.events.OnTick, fn).
#pragma once

#include <string>

struct lua_State;

namespace kp::api::compat {

// Reuse kp and install events, metadata, kp.print and harness controls.
// game_dir is captured once as the return value of kp.gamedir().
void install(lua_State*, const std::string& game_dir);

// Empty means the constant exists but nothing raises it yet.
const char* event_for_constant(int constant);
const char* event_for_name(const char* name);
unsigned event_constant_count();

}  // namespace kp::api::compat

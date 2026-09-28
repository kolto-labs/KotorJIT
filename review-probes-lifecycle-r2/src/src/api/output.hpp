// Saying things: the log file, the in-game console, and the screen.
//
// The local server has one hardcoded client (GetFirstPC /
// CServerExoApp::GetPlayerCreatureId). Feedback goes through SendMessageToPC
// and AurPostString to that creature. Three routes into the game, which is
// why they are not one function with a channel argument:
//
//   log       src/platform logging, which the runtime points at kotorphasor.log.
//             Always available, including before hooks are installed.
//   console   the console.do_console detour, which owns the input line and its
//             reply path. There is no engine routine for this surface, so the
//             runtime binds a writer here (bind_console) and until it does the
//             text goes to the log.
//   feedback  engine routines. 374 SendMessageToPC(object, string) for a plain
//             message, 582 AurPostString(string, int, int, float) when the
//             caller asks for a screen position. 548 GetFirstPC() supplies the
//             recipient 374 needs.
//
// data/hostapi.toml also includes proposed facilities. The implemented output
// surface is kp.diagnostic, kp.console and kp.feedback here, plus kp.print in compat.
// kp.console writes text; it does not execute a console command.
//
// Routines are reached BY NAME through `nwscript.call`, not by id and not by
// linking the routines bridge. Two reasons, both load-bearing:
// ids are per-game data (K1 and K2 disagree) while names are not, and looking
// the name up at call time means this module does not care whether the routines
// bridge registered before or after it. When the name is not there -- routines
// not registered, VM not bound, a build where it does not exist -- the text
// falls back to the log rather than erroring. Output that disappears because a
// diagnostic path was unavailable is worse than output in the wrong place.
#pragma once

struct lua_State;

namespace kp::api {

// Push the shared `kp` table, creating it only if this state has none.
//
// Every api module registers into one table, and they register in an order
// nobody controls, so each has to check first. Shared here rather than copied
// into each module so there is one definition of what "the kp table" means.
// Leaves the table on the stack.
void push_kp_table(lua_State*);

// Where kp.console() sends its text. The runtime binds this once the console
// detour is installed; unbound, console output goes to the log.
//
// One line per call: the writer never receives an embedded newline, because a
// multi-line message is split before it gets here. A console surface that
// scrolls by lines should not be handed a paragraph.
using ConsoleWriter = void (*)(const char* line, void* user);

void bind_console(ConsoleWriter, void* user);
void unbind_console();
bool console_bound();

// Write one message to the console surface from C++. Splits on newlines and
// falls back to the log exactly as kp.console() does, so the console
// command handler and a script produce identical output.
void console_write(const char* text);

// Installs kp.diagnostic, kp.console and kp.feedback into this state.
void register_output(lua_State*);

// The whole support module in one call: output, timers and strings.
//
// The runtime calls this once per script, on that script's lua_State, after
// luaL_openlibs and BEFORE the chunk runs -- a script's top level is the
// natural place to call registertimer, and a function registered afterwards is
// not there yet when the chunk executes.
void register_support(lua_State*);

}  // namespace kp::api

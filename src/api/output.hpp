// Saying things: the log file, the in-game console, and the screen.
//
// Phasor has six output functions and every one of them is shaped by a server
// talking to sixteen clients. KOTOR is one machine with one player, so the
// recipient argument has nothing to address and the six collapse to three
// surfaces that actually exist:
//
//   Phasor                     here          why
//   ------------------------   -----------   ------------------------------
//   hprintf(msg)               console       diagnostic echo; no server console
//   log_msg(stream, msg)       log           one log, not four streams
//   sendconsoletext(p, msg)    console       the player IS the console
//   respond(msg)               console       the console line's own reply path
//   say(msg)                   feedback      no broadcast channel exists
//   privatesay(p, msg)         feedback      one player, so "private" is moot
//
// Collapsing is the honest move rather than keeping six names that would differ
// only in which one lied about reaching somebody else.
//
// The three surfaces reach the game by three different routes, and that is why
// they are three functions rather than one with a channel argument:
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
// UNRECONCILED, AND WORTH KNOWING BEFORE ANYONE BUILDS ON THIS. data/hostapi.toml
// declares the same three surfaces under different names -- kp.print, kp.log,
// kp.echo, kp.tell, kp.say -- to be emitted by tools/gen_hostapi_glue.py into
// src/generated/hostapi.inc. Neither the generator nor the .inc exists yet, and
// several of that file's rows (kp.speak needs kp.as, kp.str.cexo needs the
// memory probe) depend on modules that do not exist either. So this module is
// hand-written under the names the module brief asked for, and the two want
// reconciling by whoever writes the generator.
//
// One name in that overlap means opposite things and will bite: kp.console
// there RUNS a line as if it had been typed into the cheat console, which is
// Phasor's svcmd. kotor.console here WRITES a line to the console. Same word,
// opposite direction.
//
// Routines are reached BY NAME through the script's own `kotor` table, not by
// id and not by linking the routines bridge. Two reasons, both load-bearing:
// ids are per-game data (K1 and K2 disagree) while names are not, and looking
// the name up at call time means this module does not care whether the routines
// bridge registered before or after it. When the name is not there -- routines
// not registered, VM not bound, a build where it does not exist -- the text
// falls back to the log rather than erroring. Output that disappears because a
// diagnostic path was unavailable is worse than output in the wrong place.
#pragma once

struct lua_State;

namespace kp::api {

// Push the shared `kotor` table, creating it only if this state has none.
//
// Every api module registers into one table, and they register in an order
// nobody controls, so each has to check first. Shared here rather than copied
// into each module so there is one definition of what "the kotor table" means.
// Leaves the table on the stack.
void push_kotor_table(lua_State*);

// Where kotor.console() sends its text. The runtime binds this once the console
// detour is installed; unbound, console output goes to the log.
//
// One line per call: the writer never receives an embedded newline, because a
// multi-line message is split before it gets here. Phasor does the same thing
// (its ProcessedString pop splits on '\n' into independent messages) and the
// reason is the same -- a console surface that scrolls by lines should not be
// handed a paragraph.
using ConsoleWriter = void (*)(const char* line, void* user);

void bind_console(ConsoleWriter, void* user);
void unbind_console();
bool console_bound();

// Write one message to the console surface from C++. Splits on newlines and
// falls back to the log exactly as kotor.console() does, so the console
// command handler and a script produce identical output.
void console_write(const char* text);

// Installs kotor.log, kotor.console and kotor.feedback into this state.
void register_output(lua_State*);

// The whole support module in one call: output, timers and strings.
//
// The runtime calls this once per script, on that script's lua_State, after
// luaL_openlibs and BEFORE the chunk runs -- a script's top level is the
// natural place to call registertimer, and a function registered afterwards is
// not there yet when the chunk executes.
void register_support(lua_State*);

}  // namespace kp::api

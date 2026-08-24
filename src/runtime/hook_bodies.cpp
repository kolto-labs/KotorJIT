// The three hook bodies.
//
// Signatures come from the recovered C for these specific functions, one per
// site, and they are the thing in this file that must not be edited casually:
// __thiscall is callee-cleans, so a body that pops a different number of bytes
// than the function it replaced skews ESP on that thread permanently, and the
// crash lands somewhere unrelated hours later. See hooks/thiscall.hpp.
//
//   K1 0x005D45D0  int  __thiscall CVirtualMachineInternal::RunScript(
//                          CExoString* name, uint32_t objectId, int hasObject)
//   K1 0x004BABB0  void* __thiscall CServerExoAppInternal::MainLoop()
//   K1 0x00401F00  void __cdecl DoConsole(char c)
//
// Every body has the same shape, and the shape is the safety argument:
//
//   1. If we are not live, or this site is poisoned, forward to the original
//      and do nothing else. This is the resting state after a fault and during
//      startup, and it makes the game behave exactly as it would unpatched.
//   2. Do our work inside a nested scope with a fault guard armed.
//   3. Leave that scope, THEN call the original. A fault inside game code is
//      the game's business and must not be claimed by us.
#include <atomic>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>

#include "events/contract.hpp"
#include "hooks/registry.hpp"
#include "hooks/thiscall.hpp"
#include "lua/host.hpp"
#include "lua/value.hpp"
#include "platform/platform.hpp"
#include "runtime/internal.hpp"
#include "runtime/runtime.hpp"

extern "C" {
#include "lauxlib.h"
#include "lua.h"
#include "lualib.h"
}

namespace kp::runtime {
namespace {

// The engine's string: a pointer and an explicit length. NOT NUL-terminated by
// contract, which is why nothing here calls strlen on it.
struct CExoString {
    char*         c_string;
    std::uint32_t length;
};
static_assert(sizeof(CExoString) == 8, "CExoString is two 32-bit fields");

// A script name is a ResRef-ish thing; anything past this is a wild pointer
// that happened to land on plausible bytes, not a string.
constexpr std::uint32_t kMaxEngineString = 64 * 1024;

std::string read_exostring(const CExoString* s) {
    // The pointer came out of the engine through a patched prologue. It is
    // almost always fine, and "almost always" is exactly the case that has to
    // be probed rather than trusted -- the fault guard can recover from reading
    // it, but a refusal is cheaper and loses nothing.
    if (s == nullptr || !platform::is_readable(s, sizeof *s)) return {};
    if (s->c_string == nullptr || s->length == 0 || s->length > kMaxEngineString) return {};
    if (!platform::is_readable(s->c_string, s->length)) return {};
    return std::string(s->c_string, s->length);
}

// ------------------------------------------------------- site-local state ---

std::atomic<void*> g_orig_run_script{nullptr};
std::atomic<void*> g_orig_main_loop{nullptr};
std::atomic<void*> g_orig_do_console{nullptr};

std::atomic<bool> g_poison_run_script{false};
std::atomic<bool> g_poison_main_loop{false};
std::atomic<bool> g_poison_do_console{false};

using RunScriptFn = int (KP_THISCALL*)(void*, CExoString*, std::uint32_t, int);
using MainLoopFn  = void* (KP_THISCALL*)(void*);
using DoConsoleFn = void (__attribute__((cdecl)) *)(char);

// An argument list built to whatever shape the contract declares, matched by
// name. Used for events whose contract this code does not get to assume --
// if the table gains OnRunScriptDone with a different argument list, this
// fills what it can and passes none for the rest rather than pushing the
// wrong things in the wrong order.
struct NamedArg {
    const char* name;
    lua::Value  value;
};

std::vector<lua::Value> shape_args(const events::EventContract& ev,
                                   const std::vector<NamedArg>& have) {
    std::vector<lua::Value> out;
    out.reserve(ev.args.size());
    for (const events::Argument& want : ev.args) {
        const lua::Value* found = nullptr;
        for (const NamedArg& h : have)
            if (want.name == h.name) { found = &h.value; break; }
        out.push_back(found != nullptr ? *found : lua::Value::none());
    }
    return out;
}

// ------------------------------------------------------------- RunScript ----

// The blocking decision, separated so the guarded region has one job.
struct ScriptVerdict {
    bool block = false;
    int  engine_result = 1;
};

ScriptVerdict decide(const events::EventContract& ev, const events::Outcome& outcome) {
    ScriptVerdict v;
    if (!outcome.claimed || outcome.bool_result) return v;   // nobody blocked

    v.block = true;
    // What the engine is told is a property of the event, not of this call.
    // RunScript returns 1 for "ran" and 0 for "did not", and 0 propagates into
    // the caller's failure path -- so suppressing the handler and reporting
    // failure are two different decisions and the contract holds which one.
    switch (ev.engine_return) {
    case events::EngineReturn::ReportSuccess: v.engine_result = 1; break;
    case events::EngineReturn::ReportFailure: v.engine_result = 0; break;
    case events::EngineReturn::Passthrough:   v.block = false;     break;
    }
    return v;
}

// `self` is the CVirtualMachineInternal, which is the only place the two live
// VM objects the routine bridge needs can be reached from. Capturing here costs
// one relaxed atomic load per script once bound.
int KP_THISCALL run_script_body(void* self, CExoString* name, std::uint32_t object_id,
                                int has_object) {
    if (!vm_bound()) capture_vm(self);

    auto orig = reinterpret_cast<RunScriptFn>(g_orig_run_script.load(std::memory_order_acquire));

    // One load, used for the whole call. Reading the published pointer twice
    // would let it be null on the second read, which is the bug the check was
    // there to prevent.
    lua::Host* const host = active_host();

    ScriptVerdict verdict;
    if (live() && host != nullptr && !g_poison_run_script.load(std::memory_order_acquire)) {
        // `verdict` is written inside the guarded region, so its value after a
        // fault is indeterminate and the fallback re-states it. The default is
        // "do not block", which is the right answer when our own dispatch just
        // faulted: the game's handler runs as it always would.
        KP_HOOK_GUARD_BEGIN("vm.run_script", g_poison_run_script, verdict = ScriptVerdict{})

        const events::EventContract* ev = find_contract("OnRunScript");
        if (ev != nullptr) {
            const std::string script_name = read_exostring(name);
            const std::vector<lua::Value> args = {
                lua::Value::str(script_name),
                lua::Value::object(object_id),
                lua::Value::integer(has_object),
            };
            const events::Outcome outcome = host->dispatch(*ev, args);
            verdict = decide(*ev, outcome);

            // Absent from the generated table today. Dispatching only when the
            // contract exists means the day it is added this works, and until
            // then nothing here pretends to raise an event nobody can receive.
            if (const events::EventContract* done = find_contract("OnRunScriptDone");
                done != nullptr) {
                const std::vector<NamedArg> have = {
                    {"script_name", lua::Value::str(script_name)},
                    {"object_id", lua::Value::object(object_id)},
                    {"has_object", lua::Value::integer(has_object)},
                    {"ran", lua::Value::boolean(!verdict.block)},
                    {"blocked", lua::Value::boolean(verdict.block)},
                    {"claimed_by", lua::Value::str(outcome.claimed_by)},
                };
                host->dispatch(*done, shape_args(*done, have));
            }
        }

        KP_HOOK_GUARD_END
    }

    if (verdict.block) return verdict.engine_result;
    if (orig == nullptr) return 0;   // unpatched: we have nothing to forward to
    return orig(self, name, object_id, has_object);
}

// -------------------------------------------------------------- MainLoop ----

// Hot-reload stats every script file, so it cannot run on every server frame.
// 64 frames is around a second at the rate the server loop actually turns,
// which is fast enough that a player editing a script does not wait for it.
constexpr std::uint64_t kReloadEvery = 64;

void* KP_THISCALL main_loop_body(void* self) {
    auto orig = reinterpret_cast<MainLoopFn>(g_orig_main_loop.load(std::memory_order_acquire));

    lua::Host* const host = active_host();

    if (live() && host != nullptr && !g_poison_main_loop.load(std::memory_order_acquire)) {
        KP_HOOK_GUARD_BEGIN("app.server_main_loop", g_poison_main_loop, {})

        lua::Host& h = *host;
        const std::uint64_t tick = h.tick();

        if (const events::EventContract* ev = find_contract("OnTick"); ev != nullptr) {
            const std::vector<lua::Value> args = {
                lua::Value::integer(static_cast<std::int64_t>(tick)),
            };
            h.dispatch(*ev, args);
        }
        h.advance_tick();

        if (tick % kReloadEvery == 0) {
            const unsigned n = h.reload_changed();
            if (n != 0) Runtime::instance().log("hot reload: %u script(s)", n);
        }

        KP_HOOK_GUARD_END
    }

    if (orig == nullptr) return nullptr;
    return orig(self);
}

// ------------------------------------------------------------- DoConsole ----
//
// A keystroke handler, not a line handler: the engine calls this once per
// character while the console is open.
//
// That forces buffer-and-replay rather than pass-through-and-suppress. To
// swallow a line we have to still be holding it when the Enter arrives, so
// nothing is forwarded while a line is being typed; on Enter the line is either
// consumed by us or replayed to the original character by character.
//
// The cost, stated because it will be visible: the game's own echo is deferred
// until Enter, so a player types the line blind. Whether the engine echoes from
// here at all needs confirming against a running game.

// Console input is single-threaded -- it is the game's input thread and there
// is exactly one console. No atomics, because adding them would suggest a
// concurrency that does not exist.
char        g_line[512];
std::size_t g_line_len = 0;

lua_State* g_console_L = nullptr;

int console_print(lua_State* L) {
    std::string out;
    const int n = lua_gettop(L);
    for (int i = 1; i <= n; ++i) {
        if (i > 1) out += "\t";
        const char* s = lua_tostring(L, i);
        out += (s != nullptr) ? s : luaL_typename(L, i);
    }
    Runtime::instance().log("lua: %s", out.c_str());
    return 0;
}

// A state of our own, so `lua exec` works with no script loaded. Sharing a
// script's state instead would let a console typo quarantine that script.
lua_State* console_state() {
    if (g_console_L != nullptr) return g_console_L;
    g_console_L = luaL_newstate();
    if (g_console_L == nullptr) return nullptr;
    luaL_openlibs(g_console_L);
    // The same API every script gets. Without this the console can evaluate Lua
    // and not reach the game, so `lua exec kotor.GetFirstPC()` -- the obvious
    // first thing anyone types -- would answer "attempt to index a nil value".
    init_lua_state(g_console_L);
    // After the API, so this wins over the one compat installs: console output
    // reads better tagged as console output. The game has no stdout worth
    // writing to, so print goes to the log either way. That is what makes this
    // drivable: type in the game, read kotorphasor.log.
    lua_pushcfunction(g_console_L, console_print);
    lua_setglobal(g_console_L, "print");
    return g_console_L;
}

void console_exec(const std::string& code) {
    lua_State* L = console_state();
    if (L == nullptr) { Runtime::instance().log("lua exec: no lua state"); return; }

    const int base = lua_gettop(L);
    // Try the text as an expression first so `lua exec 1+1` answers 2 rather
    // than failing to parse. Falling back to a statement keeps `lua exec x = 1`
    // working too.
    const std::string as_expr = "return " + code;
    if (luaL_loadbuffer(L, as_expr.c_str(), as_expr.size(), "=console") != 0) {
        lua_pop(L, 1);
        if (luaL_loadbuffer(L, code.c_str(), code.size(), "=console") != 0) {
            const char* msg = lua_tostring(L, -1);
            Runtime::instance().log("lua exec: %s", msg != nullptr ? msg : "(parse failed)");
            lua_settop(L, base);
            return;
        }
    }

    if (lua_pcall(L, 0, LUA_MULTRET, 0) != 0) {
        const char* msg = lua_tostring(L, -1);
        Runtime::instance().log("lua exec: %s", msg != nullptr ? msg : "(error)");
        lua_settop(L, base);
        return;
    }

    const int nres = lua_gettop(L) - base;
    if (nres <= 0) { Runtime::instance().log("lua exec: ok"); return; }
    for (int i = 1; i <= nres; ++i) {
        const char* s = lua_tostring(L, base + i);
        Runtime::instance().log("lua exec: %s", s != nullptr ? s : luaL_typename(L, base + i));
    }
    lua_settop(L, base);
}

void console_status() {
    Runtime& rt = Runtime::instance();
    rt.log("status: phase=%s build=%s live=%s", to_string(rt.phase()),
           rt.build().empty() ? "(none)" : rt.build().c_str(), live() ? "yes" : "no");
    if (!rt.failure().empty()) rt.log("status: failure=%s", rt.failure().c_str());

    if (hooks::HookSet* hs = rt.hooks(); hs != nullptr)
        rt.log("status: %zu hook(s) installed", hs->installed_count());

    rt.log("status: poisoned run_script=%s main_loop=%s do_console=%s",
           g_poison_run_script.load() ? "yes" : "no",
           g_poison_main_loop.load() ? "yes" : "no",
           g_poison_do_console.load() ? "yes" : "no");

    // Point at the way out, rather than leaving the player to read "live=no"
    // and conclude the mod is broken.
    if (!live() && rt.phase() == Phase::Running)
        rt.log("status: scripting is off after a fault; `lua reload` turns it back on");

    lua::Host* h = active_host();
    if (h == nullptr) { rt.log("status: no lua host"); return; }
    rt.log("status: tick=%llu, %zu script(s)", static_cast<unsigned long long>(h->tick()),
           h->scripts().size());
    for (const auto& s : h->scripts()) {
        const char* st = "?";
        switch (s->state()) {
        case lua::ScriptState::Loaded:       st = "loaded"; break;
        case lua::ScriptState::FailedToLoad: st = "failed"; break;
        case lua::ScriptState::Quarantined:  st = "quarantined"; break;
        case lua::ScriptState::Unloaded:     st = "unloaded"; break;
        }
        rt.log("status:   %s priority=%d state=%s errors=%u", s->name().c_str(), s->priority(),
               st, s->error_count());
    }
}

void console_reload() {
    lua::Host* h = active_host();
    if (h == nullptr) { Runtime::instance().log("lua reload: no lua host"); return; }
    std::vector<std::string> errors;
    const unsigned loaded = h->load_all(errors);
    for (const std::string& e : errors) Runtime::instance().log("lua reload: %s", e.c_str());
    Runtime::instance().log("lua reload: %u script(s) loaded", loaded);

    // The one command that can bring scripting back after a fault.
    //
    // A fault takes the whole runtime out of service, because the longjmp that
    // recovered from it can leave a lua_State unwound part-way through a
    // pcall. Reloading builds every state from scratch, which is exactly the
    // thing that was suspect -- so re-arming here is sound, and without it this
    // command would report "N scripts loaded" while nothing ever fires again.
    if (!live()) {
        set_live(true);
        Runtime::instance().log("lua reload: scripting re-armed after a fault");
    }

    // Poison is per site and it stays. That body faulted in native code, and a
    // fresh set of Lua states does not make running it again safe. Said out
    // loud, because "reloaded but this event still will not fire" is exactly
    // the kind of half-recovery that wastes an evening.
    if (g_poison_run_script.load() || g_poison_main_loop.load() || g_poison_do_console.load()) {
        Runtime::instance().log("lua reload: still poisoned (run_script=%s main_loop=%s "
                                "do_console=%s); those events stay silent until the game restarts",
                                g_poison_run_script.load() ? "yes" : "no",
                                g_poison_main_loop.load() ? "yes" : "no",
                                g_poison_do_console.load() ? "yes" : "no");
    }
}

// Returns true when the line was consumed and must not reach the game.
bool handle_line(const std::string& line) {
    // Built-ins first, and unconditionally: they have to work when no script is
    // loaded, when the Lua host failed to start, and when a site is poisoned.
    // That is the whole point of having them.
    if (line.rfind("lua", 0) == 0 && (line.size() == 3 || line[3] == ' ')) {
        const std::string rest = line.size() > 3 ? line.substr(4) : std::string();
        std::size_t begin = rest.find_first_not_of(' ');
        const std::string args = begin == std::string::npos ? std::string() : rest.substr(begin);

        if (args == "reload")                 console_reload();
        else if (args == "status")            console_status();
        else if (args.rfind("exec ", 0) == 0) console_exec(args.substr(5));
        else Runtime::instance().log("lua: commands are `lua reload`, `lua status`, "
                                     "`lua exec <code>`");
        return true;
    }

    lua::Host* h = active_host();
    if (!live() || h == nullptr) return false;

    const events::EventContract* ev = find_contract("OnConsoleCommand");
    if (ev == nullptr) return false;   // no contract, so no script can claim it

    const std::vector<lua::Value> args = {lua::Value::str(line)};
    const events::Outcome outcome = h->dispatch(*ev, args);
    return outcome.claimed && !outcome.bool_result;   // false means swallow
}

void replay(DoConsoleFn orig, const char* text, std::size_t len, char terminator) {
    if (orig == nullptr) return;
    for (std::size_t i = 0; i < len; ++i) orig(text[i]);
    orig(terminator);
}

void __attribute__((cdecl)) do_console_body(char c) {
    auto orig = reinterpret_cast<DoConsoleFn>(g_orig_do_console.load(std::memory_order_acquire));

    if (g_poison_do_console.load(std::memory_order_acquire)) {
        if (orig != nullptr) orig(c);
        return;
    }

    // Backspace edits our buffer instead of the game's. The game's buffer is
    // empty until Enter, so forwarding a backspace would delete nothing there
    // and desynchronise the two.
    if (c == '\b' || c == 0x7f) {
        if (g_line_len > 0) --g_line_len;
        return;
    }

    if (c != '\r' && c != '\n') {
        // Anything that is not text is the game's to interpret -- escape,
        // arrow-key encodings, whatever else the console reads. Buffering those
        // would break editing we do not implement.
        const auto uc = static_cast<unsigned char>(c);
        if (uc < 0x20) { if (orig != nullptr) orig(c); return; }

        if (g_line_len < sizeof g_line) {
            g_line[g_line_len++] = c;
        } else {
            // Longer than we will hold. Give the line back to the game rather
            // than silently truncating what the player typed.
            replay(orig, g_line, g_line_len, c);
            g_line_len = 0;
        }
        return;
    }

    const std::size_t len = g_line_len;
    g_line_len = 0;   // reset before anything can fail

    bool consumed = false;
    {
        const std::string line(g_line, len);
        KP_HOOK_GUARD_BEGIN("console.do_console", g_poison_do_console, consumed = false)
        consumed = handle_line(line);
        KP_HOOK_GUARD_END
    }

    if (!consumed) replay(orig, g_line, len, c);
}

}  // namespace

// ------------------------------------------------------------- wiring in ----

void* run_script_detour() { return reinterpret_cast<void*>(&run_script_body); }
void* main_loop_detour()  { return reinterpret_cast<void*>(&main_loop_body); }
void* do_console_detour() { return reinterpret_cast<void*>(&do_console_body); }

void bind_originals(hooks::HookSet& set) {
    g_orig_run_script.store(set.original("vm.run_script"), std::memory_order_release);
    g_orig_main_loop.store(set.original("app.server_main_loop"), std::memory_order_release);
    g_orig_do_console.store(set.original("console.do_console"), std::memory_order_release);
}

void clear_originals() {
    // Uninstalling unmaps the trampolines, so these have to be dropped before
    // the uninstall and not after. A body holding a stale pointer would fault
    // on a page that is no longer there.
    g_orig_run_script.store(nullptr, std::memory_order_release);
    g_orig_main_loop.store(nullptr, std::memory_order_release);
    g_orig_do_console.store(nullptr, std::memory_order_release);

    if (g_console_L != nullptr) { lua_close(g_console_L); g_console_L = nullptr; }
}

}  // namespace kp::runtime

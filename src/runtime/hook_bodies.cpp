// The hook bodies: RunScript, MainLoop, DoConsole, ten EventHandlers, save/load.
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
#include <fstream>
#include <string>
#include <vector>

#include "api/timers.hpp"
#include "events/contract.hpp"
#include "events/payload.hpp"
#include "events/situation.hpp"
#include "events/table.hpp"
#include "hooks/registry.hpp"
#include "hooks/thiscall.hpp"
#include "lua/host.hpp"
#include "lua/value.hpp"
#include "platform/platform.hpp"
#include "runtime/internal.hpp"
#include "runtime/runtime.hpp"
#include "version.hpp"

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

    // Verified live: RunScript's script-name CExoString reports length 17 for
    // "k_def_attacked01" (16 real characters) -- the engine's length INCLUDES a
    // trailing NUL for this particular string, contrary to the "not NUL-
    // terminated by contract" comment above, which held for every other
    // CExoString this runtime reads but not for this one. The embedded NUL
    // survived into the Lua string unnoticed because it prints identically to
    // the clean name in a terminal; every `script_name == "..."` comparison in
    // every script silently failed until this was found by hex-dumping the
    // bytes. Strip exactly one trailing NUL, and only a NUL -- anything else at
    // that position is real content, not a terminator, and must not be eaten.
    std::uint32_t len = s->length;
    if (len > 0 && s->c_string[len - 1] == '\0') --len;
    return std::string(s->c_string, len);
}

// ------------------------------------------------------- site-local state ---

std::atomic<void*> g_orig_run_script{nullptr};
std::atomic<void*> g_orig_main_loop{nullptr};
std::atomic<void*> g_orig_do_console{nullptr};
std::atomic<void*> g_orig_creature{nullptr};
std::atomic<void*> g_orig_door{nullptr};
std::atomic<void*> g_orig_placeable{nullptr};
std::atomic<void*> g_orig_trigger{nullptr};
std::atomic<void*> g_orig_module{nullptr};
std::atomic<void*> g_orig_area{nullptr};
std::atomic<void*> g_orig_encounter{nullptr};
std::atomic<void*> g_orig_aoe{nullptr};
std::atomic<void*> g_orig_store{nullptr};
std::atomic<void*> g_orig_waypoint{nullptr};
std::atomic<void*> g_orig_save{nullptr};
std::atomic<void*> g_orig_load{nullptr};

std::atomic<bool> g_poison_run_script{false};
std::atomic<bool> g_poison_main_loop{false};
std::atomic<bool> g_poison_do_console{false};
std::atomic<bool> g_poison_event{false};
std::atomic<bool> g_poison_save{false};
std::atomic<bool> g_poison_load{false};
std::atomic<unsigned> g_tick_scale{1};

std::string g_situation_path;
std::string g_situation_blob;

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

void dispatch_run_script_done(lua::Host& host, const std::string& script_name,
                              std::uint32_t object_id, int has_object, bool ran,
                              bool blocked, const events::Outcome& outcome) {
    const events::EventContract* done = find_contract("OnRunScriptDone");
    if (done == nullptr) return;
    const std::vector<NamedArg> have = {
        {"script_name", lua::Value::str(script_name)},
        {"object_id", lua::Value::object(object_id)},
        {"has_object", lua::Value::integer(has_object)},
        {"ran", lua::Value::boolean(ran)},
        {"blocked", lua::Value::boolean(blocked)},
        {"claimed_by", lua::Value::str(outcome.claimed_by)},
    };
    host.dispatch(*done, shape_args(*done, have));
}

// ------------------------------------------------------------- RunScript ----

// The blocking decision, separated so the guarded region has one job.
struct ScriptVerdict {
    bool block = false;
    int  engine_result = 1;
};

ScriptVerdict decide(const events::EventContract& ev, const events::Outcome& outcome) {
    const events::BlockVerdict b = events::blocking_verdict(ev, outcome);
    return {b.skip_original, b.engine_result};
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
    events::Outcome outcome;
    std::string script_name;
    bool saw_run_script = false;
    if (live() && host != nullptr && !g_poison_run_script.load(std::memory_order_acquire)) {
        // `verdict` is written inside the guarded region, so its value after a
        // fault is indeterminate and the fallback re-states it. The default is
        // "do not block", which is the right answer when our own dispatch just
        // faulted: the game's handler runs as it always would.
        KP_HOOK_GUARD_BEGIN("vm.run_script", g_poison_run_script, verdict = ScriptVerdict{})

        const events::EventContract* ev = find_contract("OnRunScript");
        if (ev != nullptr) {
            script_name = read_exostring(name);
            saw_run_script = true;
            const std::vector<lua::Value> args = {
                lua::Value::str(script_name),
                lua::Value::object(object_id),
                lua::Value::integer(has_object),
            };
            outcome = host->dispatch(*ev, args);
            verdict = decide(*ev, outcome);
            if (verdict.block)
                dispatch_run_script_done(*host, script_name, object_id, has_object,
                                         false, true, outcome);
        }

        KP_HOOK_GUARD_END
    }

    if (verdict.block) return verdict.engine_result;
    if (orig == nullptr) return 0;   // unpatched: we have nothing to forward to
    const int rc = orig(self, name, object_id, has_object);

    // After the engine script, with the engine's own 0/1. A Lua fault here
    // must not rewrite the return the game already produced.
    if (saw_run_script && live() && host != nullptr &&
        !g_poison_run_script.load(std::memory_order_acquire)) {
        KP_HOOK_GUARD_BEGIN("vm.run_script", g_poison_run_script, {})
        dispatch_run_script_done(*host, script_name, object_id, has_object,
                                 rc == 1, false, outcome);
        KP_HOOK_GUARD_END
    }
    return rc;
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
        kp::api::timers::pump(kp::api::timers::now_ms(), tick);
        h.advance_tick();

        if (tick % kReloadEvery == 0) {
            std::vector<std::string> errors;
            const unsigned n = h.reload_changed(&errors);
            for (const std::string& e : errors)
                Runtime::instance().log("hot reload: %s", e.c_str());
            if (n != 0) Runtime::instance().log("hot reload: %u script(s)", n);
        }

        KP_HOOK_GUARD_END
    }

    if (orig == nullptr) return nullptr;
    void* result = orig(self);
    unsigned scale = g_tick_scale.load(std::memory_order_acquire);
    if (scale < 1) scale = 1;
    if (scale > 16) scale = 16;
    for (unsigned i = 1; i < scale; ++i) orig(self);
    return result;
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
    rt.log("status: KotorPhasor %s", KP_VERSION);
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

// ---------------------------------------------------------- EventHandler ----
//
// All ten object types share this signature. Five stack arguments after `this`,
// callee-cleans: the compiler must emit `ret $0x14`. A shorter parameter list
// skews ESP on that thread permanently.
//
// pEventData is NOT always a CScriptEvent. Lookup keys on (site, outer id)
// and, when outer id is SIGNAL_EVENT, the script event type. Named slots that
// only ever reach RunScript are not looked up here.

using EventHandlerFn = void (KP_THISCALL*)(void*, unsigned long, unsigned long,
                                           void*, unsigned long, unsigned long);

void persist_situation(const std::string& blob) {
    g_situation_blob = blob;
    events::write_situation_blob(g_situation_path, blob);
}

std::string load_situation() {
    if (!g_situation_path.empty()) {
        const std::string blob = events::read_situation_blob(g_situation_path);
        if (!blob.empty() || g_situation_blob.empty())
            g_situation_blob = blob;
    }
    return g_situation_blob;
}

void event_handler_common(void* self, unsigned long n_event_id,
                          unsigned long n_caller, void* payload,
                          unsigned long day, unsigned long time,
                          const char* site, std::atomic<void*>& orig_slot) {
    auto orig = reinterpret_cast<EventHandlerFn>(
        orig_slot.load(std::memory_order_acquire));

    lua::Host* const host = active_host();
    bool skip = false;
    if (live() && host != nullptr && !g_poison_event.load(std::memory_order_acquire)) {
        KP_HOOK_GUARD_BEGIN(site, g_poison_event, skip = false)

        int script_type = -1;
        if (events::payload_is_script_event(static_cast<int>(n_event_id))) {
            events::ScriptEventView view{payload};
            script_type = events::script_event_type(view);
        }
        const events::EventContract* ev = events::find_by_site(
            site, static_cast<int>(n_event_id), script_type);
        if (ev != nullptr) {
            events::HandlerFrame frame;
            frame.self = self;
            frame.caller = static_cast<std::uint32_t>(n_caller);
            frame.payload = payload;
            frame.calendar_day = static_cast<std::uint32_t>(day);
            frame.time_of_day = static_cast<std::uint32_t>(time);
            frame.hook_site = site;
            frame.outer_event_id = static_cast<int>(n_event_id);
            const events::Outcome outcome =
                host->dispatch(*ev, events::shape_handler_args(*ev, frame));
            if (ev->blocking)
                skip = events::blocking_verdict(*ev, outcome).skip_original;
        }

        KP_HOOK_GUARD_END
    }

    if (skip) return;
    if (orig == nullptr) return;
    orig(self, n_event_id, n_caller, payload, day, time);
}

void KP_THISCALL creature_event_body(void* self, unsigned long id, unsigned long caller,
                                     void* data, unsigned long day, unsigned long time) {
    event_handler_common(self, id, caller, data, day, time, "event.creature", g_orig_creature);
}
void KP_THISCALL door_event_body(void* self, unsigned long id, unsigned long caller,
                                 void* data, unsigned long day, unsigned long time) {
    event_handler_common(self, id, caller, data, day, time, "event.door", g_orig_door);
}
void KP_THISCALL placeable_event_body(void* self, unsigned long id, unsigned long caller,
                                      void* data, unsigned long day, unsigned long time) {
    event_handler_common(self, id, caller, data, day, time, "event.placeable", g_orig_placeable);
}
void KP_THISCALL trigger_event_body(void* self, unsigned long id, unsigned long caller,
                                    void* data, unsigned long day, unsigned long time) {
    event_handler_common(self, id, caller, data, day, time, "event.trigger", g_orig_trigger);
}
void KP_THISCALL module_event_body(void* self, unsigned long id, unsigned long caller,
                                   void* data, unsigned long day, unsigned long time) {
    event_handler_common(self, id, caller, data, day, time, "event.module", g_orig_module);
}
void KP_THISCALL area_event_body(void* self, unsigned long id, unsigned long caller,
                                 void* data, unsigned long day, unsigned long time) {
    event_handler_common(self, id, caller, data, day, time, "event.area", g_orig_area);
}
void KP_THISCALL encounter_event_body(void* self, unsigned long id, unsigned long caller,
                                      void* data, unsigned long day, unsigned long time) {
    event_handler_common(self, id, caller, data, day, time, "event.encounter", g_orig_encounter);
}
void KP_THISCALL aoe_event_body(void* self, unsigned long id, unsigned long caller,
                                void* data, unsigned long day, unsigned long time) {
    event_handler_common(self, id, caller, data, day, time, "event.aoe", g_orig_aoe);
}
void KP_THISCALL store_event_body(void* self, unsigned long id, unsigned long caller,
                                  void* data, unsigned long day, unsigned long time) {
    event_handler_common(self, id, caller, data, day, time, "event.store", g_orig_store);
}
void KP_THISCALL waypoint_event_body(void* self, unsigned long id, unsigned long caller,
                                     void* data, unsigned long day, unsigned long time) {
    event_handler_common(self, id, caller, data, day, time, "event.waypoint", g_orig_waypoint);
}

// Save takes one stack argument. Load takes three: both K1 callers of the
// CVirtualMachine thunk push three, and Internal reads them at [esp+0x38],
// [esp+0x3c], [esp+0x44] after its SEH prologue. A one-arg load body
// forwarded garbage for the last two and popped 4 bytes instead of 12 --
// Wine faulted at 0x41168A (cmp eax, [edx+0xC]) on every save load.
using SaveSituationFn = int (KP_THISCALL*)(void*, void*);
using LoadSituationFn = int (KP_THISCALL*)(void*, void*, void*, void*);

int KP_THISCALL save_situation_body(void* self, void* situation) {
    auto orig = reinterpret_cast<SaveSituationFn>(g_orig_save.load(std::memory_order_acquire));
    lua::Host* const host = active_host();
    if (live() && host != nullptr && !g_poison_save.load(std::memory_order_acquire)) {
        KP_HOOK_GUARD_BEGIN("vm.save_script_situation", g_poison_save, {})
        if (const events::EventContract* ev = find_contract("OnSave")) {
            const events::Outcome outcome = host->dispatch(*ev, {});
            if (outcome.claimed) persist_situation(outcome.string_result);
        }
        KP_HOOK_GUARD_END
    }
    if (orig == nullptr) return 0;
    return orig(self, situation);
}

int KP_THISCALL load_situation_body(void* self, void* a, void* b, void* c) {
    auto orig = reinterpret_cast<LoadSituationFn>(g_orig_load.load(std::memory_order_acquire));
    lua::Host* const host = active_host();
    if (live() && host != nullptr && !g_poison_load.load(std::memory_order_acquire)) {
        KP_HOOK_GUARD_BEGIN("vm.load_script_situation", g_poison_load, {})
        if (const events::EventContract* ev = find_contract("OnLoad")) {
            const std::vector<lua::Value> args = {
                lua::Value::str(load_situation()),
            };
            host->dispatch(*ev, args);
        }
        KP_HOOK_GUARD_END
    }
    if (orig == nullptr) return 0;
    return orig(self, a, b, c);
}

}  // namespace

// ------------------------------------------------------------- wiring in ----

void set_situation_path(std::string path) { g_situation_path = std::move(path); }

void set_tick_scale(unsigned n) {
    if (n < 1) n = 1;
    if (n > 16) n = 16;
    g_tick_scale.store(n, std::memory_order_release);
}

unsigned tick_scale() { return g_tick_scale.load(std::memory_order_acquire); }

namespace {
int l_speed(lua_State* L) {
    if (lua_gettop(L) >= 1) set_tick_scale(static_cast<unsigned>(luaL_checkinteger(L, 1)));
    lua_pushinteger(L, static_cast<lua_Integer>(tick_scale()));
    return 1;
}
}  // namespace

void register_director(lua_State* L) {
    lua_getglobal(L, "kp");
    if (!lua_istable(L, -1)) {
        lua_pop(L, 1);
        lua_newtable(L);
        lua_pushvalue(L, -1);
        lua_setglobal(L, "kp");
    }
    lua_pushcfunction(L, l_speed);
    lua_setfield(L, -2, "speed");
    lua_pop(L, 1);
}

void* run_script_detour() { return reinterpret_cast<void*>(&run_script_body); }
void* main_loop_detour()  { return reinterpret_cast<void*>(&main_loop_body); }
void* do_console_detour() { return reinterpret_cast<void*>(&do_console_body); }
void* creature_event_detour()  { return reinterpret_cast<void*>(&creature_event_body); }
void* door_event_detour()      { return reinterpret_cast<void*>(&door_event_body); }
void* placeable_event_detour() { return reinterpret_cast<void*>(&placeable_event_body); }
void* trigger_event_detour()   { return reinterpret_cast<void*>(&trigger_event_body); }
void* module_event_detour()    { return reinterpret_cast<void*>(&module_event_body); }
void* area_event_detour()      { return reinterpret_cast<void*>(&area_event_body); }
void* encounter_event_detour() { return reinterpret_cast<void*>(&encounter_event_body); }
void* aoe_event_detour()       { return reinterpret_cast<void*>(&aoe_event_body); }
void* store_event_detour()     { return reinterpret_cast<void*>(&store_event_body); }
void* waypoint_event_detour()  { return reinterpret_cast<void*>(&waypoint_event_body); }
void* save_situation_detour()  { return reinterpret_cast<void*>(&save_situation_body); }
void* load_situation_detour()  { return reinterpret_cast<void*>(&load_situation_body); }

void bind_originals(hooks::HookSet& set) {
    g_orig_run_script.store(set.original("vm.run_script"), std::memory_order_release);
    g_orig_main_loop.store(set.original("app.server_main_loop"), std::memory_order_release);
    g_orig_do_console.store(set.original("console.do_console"), std::memory_order_release);
    g_orig_creature.store(set.original("event.creature"), std::memory_order_release);
    g_orig_door.store(set.original("event.door"), std::memory_order_release);
    g_orig_placeable.store(set.original("event.placeable"), std::memory_order_release);
    g_orig_trigger.store(set.original("event.trigger"), std::memory_order_release);
    g_orig_module.store(set.original("event.module"), std::memory_order_release);
    g_orig_area.store(set.original("event.area"), std::memory_order_release);
    g_orig_encounter.store(set.original("event.encounter"), std::memory_order_release);
    g_orig_aoe.store(set.original("event.aoe"), std::memory_order_release);
    g_orig_store.store(set.original("event.store"), std::memory_order_release);
    g_orig_waypoint.store(set.original("event.waypoint"), std::memory_order_release);
    g_orig_save.store(set.original("vm.save_script_situation"), std::memory_order_release);
    g_orig_load.store(set.original("vm.load_script_situation"), std::memory_order_release);
}

void clear_originals() {
    // Uninstalling unmaps the trampolines, so these have to be dropped before
    // the uninstall and not after. A body holding a stale pointer would fault
    // on a page that is no longer there.
    g_orig_run_script.store(nullptr, std::memory_order_release);
    g_orig_main_loop.store(nullptr, std::memory_order_release);
    g_orig_do_console.store(nullptr, std::memory_order_release);
    g_orig_creature.store(nullptr, std::memory_order_release);
    g_orig_door.store(nullptr, std::memory_order_release);
    g_orig_placeable.store(nullptr, std::memory_order_release);
    g_orig_trigger.store(nullptr, std::memory_order_release);
    g_orig_module.store(nullptr, std::memory_order_release);
    g_orig_area.store(nullptr, std::memory_order_release);
    g_orig_encounter.store(nullptr, std::memory_order_release);
    g_orig_aoe.store(nullptr, std::memory_order_release);
    g_orig_store.store(nullptr, std::memory_order_release);
    g_orig_waypoint.store(nullptr, std::memory_order_release);
    g_orig_save.store(nullptr, std::memory_order_release);
    g_orig_load.store(nullptr, std::memory_order_release);

    if (g_console_L != nullptr) { lua_close(g_console_L); g_console_L = nullptr; }
}

}  // namespace kp::runtime

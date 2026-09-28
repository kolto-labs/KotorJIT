#include "api/compat.hpp"
#include "api/output.hpp"

#include <cmath>
#include <cstdint>
#include <climits>
#include <cstdio>
#include <cstring>
#include <string>
#include <type_traits>
#include <vector>

#include "lua/host.hpp"
#include "harness/commands.hpp"
#include "harness/fields.hpp"
#include "events/table.hpp"
#include "harness/ring.hpp"
#include "hooks/registry.hpp"
#include "platform/platform.hpp"
#include "runtime/internal.hpp"
#include "runtime/runtime.hpp"
#include "version.hpp"

#if defined(_WIN32)
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#else
#include <ctime>
#include <unistd.h>
#endif

extern "C" {
#include "lua.h"
#include "lauxlib.h"
}

namespace kp::api::compat {

namespace {

struct EventC { const char* name; const char* lua_name; int value; const char* note; };

const EventC kEvents[] = {
#include "generated/compat_events.inc"
};

constexpr unsigned kEventCount = sizeof kEvents / sizeof kEvents[0];

// ------------------------------------------------------------------ print ---

int lua_print_to_log(lua_State* L) {
    // Same contract as Lua's own print: tostring every argument, tab-separated.
    // Going through the registered `tostring` rather than lua_tostring keeps
    // __tostring metamethods working, which is what a script expects.
    const int n = lua_gettop(L);
    std::string line;
    for (int i = 1; i <= n; ++i) {
        lua_getglobal(L, "tostring");
        lua_pushvalue(L, i);
        if (lua_pcall(L, 1, 1, 0) != 0) {
            lua_pop(L, 1);
            line += "(tostring failed)";
        } else {
            const char* s = lua_tostring(L, -1);
            line += s ? s : "(null)";
            lua_pop(L, 1);
        }
        if (i < n) line += '\t';
    }

    const lua::Script* owner = lua::Script::owner(L);
    platform::log(platform::LogLevel::Info, "[%s] %s",
                  owner ? owner->name().c_str() : "script", line.c_str());
    return 0;
}

// -------------------------------------------------------------- callbacks ---

// Shared by both "registration promises nothing" cases below: same one-line
// Warn, differing only in why the handler will never be called.
void warn_unreachable_registration(lua::Script& owner, int constant, const char* how) {
    const char* why = "";
    for (unsigned i = 0; i < kEventCount; ++i)
        if (kEvents[i].value == constant) { why = kEvents[i].note; break; }
    platform::log(platform::LogLevel::Warn,
                  "[%s] registered for an event %s (%s)%s%s",
                  owner.name().c_str(), how,
                  [&] { for (unsigned i = 0; i < kEventCount; ++i)
                            if (kEvents[i].value == constant) return kEvents[i].name;
                        return "?"; }(),
                  *why ? ": " : "", why);
}

// kp.events.register(event, "handler_name" | function)
//
// A name is resolved now, not at dispatch, so a typo is an error at the call
// site instead of an event that silently never fires. A function value is
// accepted too, for scripts that would rather pass the handler directly.
int l_register_callback(lua_State* L) {
    const int constant = int(luaL_checkinteger(L, 1));
    const char* event = event_for_constant(constant);
    if (event == nullptr)
        return luaL_error(L, "kp.events.register: %d is not an event constant; "
                             "use one of the kp.events.On* values", constant);

    lua::Script* owner = lua::Script::owner(L);
    if (owner == nullptr)
        return luaL_error(L, "kp.events.register: no owning script");

    if (*event == '\0') {
        // The constant is real but nothing raises it here. Say so once rather
        // than accepting a handler that will never be called.
        warn_unreachable_registration(*owner, constant, "this game does not have");
        lua_pushboolean(L, 0);
        return 1;
    }

    // The constant is real and the game has the event, but no hook site in
    // this build ever raises it -- e.g. OnCreatureDamaged, whose contract
    // carries outer_event_id == -1 (see events::dispatchable). A handler
    // registered for it would sit forever, so say so now rather than let the
    // script believe it is armed. Derived from the contract table itself, not
    // a hardcoded name, so it covers K1 and K2 alike.
    const events::EventContract* contract = events::find(event);
    if (contract == nullptr || !events::dispatchable(*contract)) {
        warn_unreachable_registration(*owner, constant,
                                      "no dispatch site in this build raises");
        lua_pushboolean(L, 0);
        return 1;
    }

    if (lua_isfunction(L, 2)) {
        lua_pushvalue(L, 2);
    } else {
        const char* fn = luaL_checkstring(L, 2);
        lua_getglobal(L, fn);
        if (!lua_isfunction(L, -1)) {
            lua_pop(L, 1);
            return luaL_error(L, "kp.events.register: '%s' is not a function", fn);
        }
    }
    owner->bind_callback(event, luaL_ref(L, LUA_REGISTRYINDEX));
    lua_pushboolean(L, 1);
    return 1;
}

int l_unregister_callback(lua_State* L) {
    const int constant = int(luaL_checkinteger(L, 1));
    const char* event = event_for_constant(constant);
    if (event == nullptr || *event == '\0') { lua_pushboolean(L, 0); return 1; }
    if (lua::Script* owner = lua::Script::owner(L))
        owner->bind_callback(event, LUA_NOREF);
    lua_pushboolean(L, 1);
    return 1;
}

// ------------------------------------------------------------- kp.gamedir ---

// The one upvalue is the directory string itself, computed once by runtime.cpp
// (which already has it from Config) rather than recomputed here. See
// data/hostapi.toml's kp.gamedir entry: "the OS rather than reconstructed" --
// GetModuleName/GetModuleFileName answer a different question, the module
// resref, not a filesystem path.
int l_kp_gamedir(lua_State* L) {
    lua_pushvalue(L, lua_upvalueindex(1));
    return 1;
}

// ---------------------------------------------------------------- kp.time ---

// Wall-clock milliseconds, monotonic, and running while the game is paused --
// unlike kp.timer.clock, which is the server tick and stops with it. See
// data/hostapi.toml's kp.time entry.
int l_kp_time(lua_State* L) {
#if defined(_WIN32)
    // GetTickCount64, not GetTickCount: the 32-bit form wraps every 49.7 days,
    // which is a real uptime for a game left running, and the 64-bit form has
    // been available since Vista at no extra linkage cost.
    lua_pushnumber(L, static_cast<lua_Number>(GetTickCount64()));
#else
    struct timespec ts {};
    clock_gettime(CLOCK_MONOTONIC, &ts);
    lua_pushnumber(L, static_cast<lua_Number>(ts.tv_sec) * 1000.0 +
                       static_cast<lua_Number>(ts.tv_nsec) / 1.0e6);
#endif
    return 1;
}

struct HarnessCallResult {
    bool ok = false;
    char error[1024]{};
};

// Copy errors into a trivial buffer before raising: LuaJIT errors longjmp and
// skip destructors for C++ locals still on the stack.
template <typename Fn>
HarnessCallResult invoke_harness(Fn&& fn) {
    HarnessCallResult result;
    auto* a = kp::harness::adapter();
    if (!a) {
        std::snprintf(result.error, sizeof result.error, "%s", "harness: no engine adapter");
        return result;
    }
    kp::harness::Result native = kp::harness::Result::success();
    { kp::harness::HookBodyScope scope; native = fn(*a); }
    result.ok = native.ok;
    if (!native.ok) std::snprintf(result.error, sizeof result.error, "%s", native.error.c_str());
    return result;
}

template <typename Fn>
int harness_call(lua_State* L, Fn&& fn) {
    static_assert(std::is_trivially_destructible_v<std::decay_t<Fn>>,
                  "LuaJIT longjmp cannot unwind a stateful harness callback");
    const HarnessCallResult result = invoke_harness(static_cast<Fn&&>(fn));
    if (!result.ok) return luaL_error(L, "%s", result.error);
    lua_pushboolean(L, 1);
    return 1;
}

std::uint32_t check_u32(lua_State* L, int index, const char* name) {
    const lua_Number raw = luaL_checknumber(L, index);
    if (!std::isfinite(raw) || raw < 0 || raw > 4294967295.0 || std::trunc(raw) != raw)
        luaL_error(L, "%s must be an unsigned 32-bit integer", name);
    return static_cast<std::uint32_t>(raw);
}

void push_u32(lua_State* L, std::uint32_t value) {
    // LuaJIT's lua_Integer is pointer-sized; on the 32-bit game builds it
    // cannot represent handles with bit 31 set. lua_Number is a double and
    // exactly represents every uint32 value.
    lua_pushnumber(L, static_cast<lua_Number>(value));
}

int check_int(lua_State* L, int index, const char* name) {
    const lua_Integer raw = luaL_checkinteger(L, index);
    if (raw < static_cast<lua_Integer>(INT_MIN) || raw > static_cast<lua_Integer>(INT_MAX))
        luaL_error(L, "%s must fit a signed int", name);
    return static_cast<int>(raw);
}

#define KP_H_VOID(name, call) \
int l_h_##name(lua_State* L) { \
    return harness_call(L, [](kp::harness::EngineAdapter& adapter) { \
        auto* a = &adapter; return (call); \
    }); \
}
KP_H_VOID(dialog_skip, a->dialog_skip())
KP_H_VOID(dialog_abort, a->dialog_abort())
KP_H_VOID(dialog_continue, a->dialog_continue())
KP_H_VOID(unpause_timers, a->unpause_timers())
KP_H_VOID(advance_tutorial, a->advance_tutorial())
KP_H_VOID(finish_hidden_tutorial, a->finish_hidden_tutorial())
KP_H_VOID(dismiss_status_summary, a->dismiss_status_summary())
KP_H_VOID(dismiss_messagebox, a->dismiss_messagebox())
KP_H_VOID(dismiss_container, a->dismiss_container())
KP_H_VOID(take_all_container, a->take_all_container())
KP_H_VOID(accept_party_selection, a->accept_party_selection())
KP_H_VOID(new_game, a->new_game())
KP_H_VOID(chargen_begin_play, a->chargen_begin_play())
KP_H_VOID(dialog_clear_sound_wait, a->dialog_clear_sound_wait())
KP_H_VOID(clear_auto_pause, a->clear_auto_pause())

int l_h_speed(lua_State* L) {
    if (lua_gettop(L) == 0) {
        auto* a = kp::harness::adapter();
        if (!a) return luaL_error(L, "harness: no engine adapter");
        float scale;
        { kp::harness::HookBodyScope scope; scale = a->speed(); }
        lua_pushnumber(L, scale);
        return 1;
    }
    double requested = luaL_checknumber(L, 1);
    if (requested > 16.0) requested = 16.0;
    const float scale = static_cast<float>(requested);
    return harness_call(L, [scale](kp::harness::EngineAdapter& a) { return a.set_speed(scale); });
}
int l_h_fixed_step(lua_State* L) {
    int hz = check_int(L, 1, "fixed_step rate");
    if (hz < 0) hz = 0;
    return harness_call(L, [hz](kp::harness::EngineAdapter& a) { return a.set_fixed_step(hz); });
}
int l_h_movies(lua_State* L) {
    luaL_checktype(L, 1, LUA_TBOOLEAN);
    const bool enabled = lua_toboolean(L, 1) != 0;
    return harness_call(L, [enabled](kp::harness::EngineAdapter& a) { return a.set_movies(enabled); });
}
struct HarnessStateSnapshot {
    kp::harness::Phase phase = kp::harness::Phase::Unknown;
    kp::harness::PhaseDetail detail{};
    char module[64]{};
    char stage[16]{};
    char adapter[16]{};
    std::uint64_t server_tick = 0;
    std::uint64_t client_tick = 0;
    bool live = false;
    std::vector<std::string> poisoned;
    kp::harness::DialogState dialog;
    bool has_dialog = false;
    bool globals_ok = false;
    bool journal_ok = false;
    char globals_hash[17]{};
    char journal_hash[17]{};
    unsigned globals_count = 0;
    unsigned journal_count = 0;
};

struct HarnessFnv {
    std::uint64_t value = 1469598103934665603ull;
    void add_byte(std::uint8_t b) { value = (value ^ b) * 1099511628211ull; }
    void add(const char* s) {
        if (!s) return;
        for (; *s; ++s) add_byte(static_cast<std::uint8_t>(*s));
        add_byte(0);
    }
    void add_int(std::int64_t n) {
        const auto u = static_cast<std::uint64_t>(n);
        for (int i = 0; i < 8; ++i) add_byte(static_cast<std::uint8_t>(u >> (i * 8)));
    }
    void hex(char out[17]) const { std::snprintf(out, 17, "%016llx", static_cast<unsigned long long>(value)); }
};

struct HarnessGlobalsHash final : kp::harness::GlobalsVisitor {
    HarnessFnv fnv;
    unsigned count = 0;
    void on_bool(const char* name, bool v) override { fnv.add(name); fnv.add_int(v ? 1 : 0); ++count; }
    void on_number(const char* name, int v) override { fnv.add(name); fnv.add_int(v); ++count; }
    void on_string(const char* name, const char* v) override { fnv.add(name); fnv.add(v); ++count; }
};

struct HarnessJournalHash final : kp::harness::JournalVisitor {
    HarnessFnv fnv;
    unsigned count = 0;
    void on_entry(const char* tag, int state) override { fnv.add(tag); fnv.add_int(state); ++count; }
};

// Same compact live-PC/party oracle as the channel state command. It uses the
// existing routine bridge and runs protected so a missing VM does not corrupt
// the caller's script state.
constexpr char kHarnessPcPartyChunk[] =
    "local pc = nwscript.call('GetFirstPC')\n"
    "if pc == nil or pc == 0x7F000000 then return nil, nil end\n"
    "local pos = nwscript.call('GetPosition',pc)\n"
    "local me = { id = pc, x = pos.x, y = pos.y, z = pos.z, hp = nwscript.call('GetCurrentHitPoints',pc), max_hp = nwscript.call('GetMaxHitPoints',pc) }\n"
    "local party = {}\n"
    "local n = nwscript.call('GetPartyMemberCount')\n"
    "for i = 0, n - 1 do local m = nwscript.call('GetPartyMemberByIndex',i); party[#party + 1] = { id = m, tag = nwscript.call('GetTag',m) } end\n"
    "return me, party\n";

int push_dialog_table(lua_State* L) {
    const auto* d = static_cast<const kp::harness::DialogState*>(lua_touserdata(L, 1));
    lua_newtable(L);
    lua_pushboolean(L, d->active); lua_setfield(L, -2, "active");
    lua_pushinteger(L, d->current_entry); lua_setfield(L, -2, "entry");
    lua_pushinteger(L, d->current_reply); lua_setfield(L, -2, "reply");
    lua_pushboolean(L, d->waiting_for_player); lua_setfield(L, -2, "waiting_for_player");
    lua_pushboolean(L, d->waiting_on_sound); lua_setfield(L, -2, "waiting_on_sound");
    lua_pushlstring(L, d->entry_text.data(), d->entry_text.size()); lua_setfield(L, -2, "text");
    lua_newtable(L);
    for (std::size_t i = 0; i < d->replies.size(); ++i) {
        const auto& reply = d->replies[i];
        lua_newtable(L);
        lua_pushinteger(L, reply.visible_index); lua_setfield(L, -2, "index");
        lua_pushinteger(L, reply.link_index); lua_setfield(L, -2, "link");
        lua_pushlstring(L, reply.text.data(), reply.text.size()); lua_setfield(L, -2, "text");
        lua_pushboolean(L, reply.active); lua_setfield(L, -2, "active");
        lua_rawseti(L, -2, static_cast<int>(i + 1));
    }
    lua_setfield(L, -2, "replies");
    return 1;
}

int push_state_snapshot(lua_State* L) {
    const auto* s = static_cast<const HarnessStateSnapshot*>(lua_touserdata(L, 1));
    const char* phase = "unknown";
    switch (s->phase) {
    case kp::harness::Phase::Menu: phase="menu"; break;
    case kp::harness::Phase::Loading: phase="loading"; break;
    case kp::harness::Phase::Gameplay: phase="gameplay"; break;
    case kp::harness::Phase::Dialog: phase="dialog"; break;
    case kp::harness::Phase::Movie: phase="movie"; break;
    case kp::harness::Phase::Paused: phase="paused"; break;
    case kp::harness::Phase::Minigame: phase="minigame"; break;
    case kp::harness::Phase::GameOver: phase="gameover"; break;
    case kp::harness::Phase::Error: phase="error"; break;
    default: break;
    }
    lua_newtable(L);
    const int state = lua_gettop(L);
#define KP_H_FIELD_STRING(key, value) lua_pushstring(L, value); lua_setfield(L, state, key)
    KP_H_FIELD_STRING("phase", phase);
    KP_H_FIELD_STRING("module", s->module);
    KP_H_FIELD_STRING("adapter", s->adapter);
    KP_H_FIELD_STRING("chargen_stage", s->stage);
#undef KP_H_FIELD_STRING
    lua_pushinteger(L, s->detail.modal_count); lua_setfield(L, state, "modal_count");
    lua_pushinteger(L, s->detail.timers_paused); lua_setfield(L, state, "timers_paused");
    lua_newtable(L);
#define KP_H_DETAIL(name) lua_pushinteger(L, s->detail.name); lua_setfield(L, -2, #name)
    KP_H_DETAIL(server_mode); KP_H_DETAIL(loading_module); KP_H_DETAIL(area_not_ready);
    KP_H_DETAIL(input_class); KP_H_DETAIL(main_menu); KP_H_DETAIL(game_over);
    KP_H_DETAIL(pause); KP_H_DETAIL(controller_pause); KP_H_DETAIL(tutorial);
    KP_H_DETAIL(modal_count); KP_H_DETAIL(status_summary); KP_H_DETAIL(movie); KP_H_DETAIL(load_error);
    KP_H_DETAIL(move_pending); KP_H_DETAIL(chargen); KP_H_DETAIL(timers_paused);
#undef KP_H_DETAIL
    lua_setfield(L, state, "phase_detail");
    lua_pushinteger(L, static_cast<lua_Integer>(s->client_tick)); lua_setfield(L, state, "client_tick");
    lua_pushinteger(L, static_cast<lua_Integer>(s->server_tick)); lua_setfield(L, state, "server_tick");
    lua_pushboolean(L, s->live); lua_setfield(L, state, "live");
    lua_newtable(L);
    for (std::size_t i = 0; i < s->poisoned.size(); ++i) {
        const auto& name = s->poisoned[i];
        lua_pushlstring(L, name.data(), name.size()); lua_rawseti(L, -2, static_cast<int>(i + 1));
    }
    lua_setfield(L, state, "poisoned");
    if (s->has_dialog) {
        lua_pushcfunction(L, push_dialog_table);
        lua_pushlightuserdata(L, const_cast<kp::harness::DialogState*>(&s->dialog));
        if (lua_pcall(L, 1, 1, 0) != 0) return lua_error(L);
        lua_setfield(L, state, "dialog");
    }
    if (s->globals_ok) {
        lua_pushlstring(L, s->globals_hash, 16); lua_setfield(L, state, "globals_hash");
    }
    if (s->journal_ok) {
        lua_pushlstring(L, s->journal_hash, 16); lua_setfield(L, state, "journal_hash");
    }
    lua_newtable(L);
    lua_pushinteger(L, static_cast<lua_Integer>(s->globals_count)); lua_setfield(L, -2, "globals");
    lua_pushinteger(L, static_cast<lua_Integer>(s->journal_count)); lua_setfield(L, -2, "journal");
    lua_setfield(L, state, "counts");

    if (kp::runtime::vm_bound()) {
        if (luaL_loadbuffer(L, kHarnessPcPartyChunk, sizeof(kHarnessPcPartyChunk) - 1, "=harness.state") != 0 ||
            lua_pcall(L, 0, 2, 0) != 0) {
            lua_setfield(L, state, "pc_error");
        } else {
            if (!lua_isnil(L, -2)) { lua_pushvalue(L, -2); lua_setfield(L, state, "pc"); }
            if (!lua_isnil(L, -1)) { lua_pushvalue(L, -1); lua_setfield(L, state, "party"); }
            lua_pop(L, 2);
        }
    }
    return 1;
}

int l_h_state(lua_State* L) {
    auto* a = kp::harness::adapter(); if (!a) return luaL_error(L, "harness: no engine adapter");
    const int base = lua_gettop(L);
    bool serialized = false;
    char error[1024]{};
    {
        HarnessStateSnapshot snapshot;
        {
            kp::harness::HookBodyScope scope;
            snapshot.phase = a->phase(&snapshot.detail);
            const std::string module = a->module_name();
            const std::string stage = a->chargen_stage();
            std::snprintf(snapshot.module, sizeof snapshot.module, "%s", module.c_str());
            std::snprintf(snapshot.stage, sizeof snapshot.stage, "%s", stage.c_str());
            std::snprintf(snapshot.adapter, sizeof snapshot.adapter, "%s", a->name());
        }
        snapshot.client_tick = kp::harness::client_tick();
        if (auto* host = kp::runtime::active_host()) snapshot.server_tick = host->tick();
        snapshot.live = kp::runtime::live();
        snapshot.poisoned = kp::runtime::poisoned_sites();
        {
            kp::harness::Result result = kp::harness::Result::success();
            { kp::harness::HookBodyScope scope; result = a->dialog(&snapshot.dialog); }
            snapshot.has_dialog = result.ok && snapshot.dialog.active;
        }
        {
            HarnessGlobalsHash globals;
            kp::harness::Result result = kp::harness::Result::success();
            { kp::harness::HookBodyScope scope; result = a->walk_globals(globals); }
            snapshot.globals_count = globals.count;
            snapshot.globals_ok = result.ok;
            if (snapshot.globals_ok) globals.fnv.hex(snapshot.globals_hash);
        }
        {
            HarnessJournalHash journal;
            kp::harness::Result result = kp::harness::Result::success();
            { kp::harness::HookBodyScope scope; result = a->walk_journal(journal); }
            snapshot.journal_count = journal.count;
            snapshot.journal_ok = result.ok;
            if (snapshot.journal_ok) journal.fnv.hex(snapshot.journal_hash);
        }
        lua_pushcfunction(L, push_state_snapshot);
        lua_pushlightuserdata(L, &snapshot);
        serialized = lua_pcall(L, 1, 1, 0) == 0;
        if (!serialized) {
            const char* msg = lua_tostring(L, -1);
            std::snprintf(error, sizeof error, "%s", msg ? msg : "cannot serialize harness state");
            lua_settop(L, base);
        }
    }
    if (!serialized) { lua_pushstring(L, error); return lua_error(L); }
    return 1;
}
int l_h_chargen_select_class(lua_State* L) {
    const int index = check_int(L, 1, "chargen class index");
    return harness_call(L, [index](kp::harness::EngineAdapter& a) {
        return a.chargen_select_class(index);
    });
}
int l_h_chargen_stage(lua_State* L) {
    auto* a = kp::harness::adapter();
    if (!a) return luaL_error(L, "harness: no engine adapter");
    std::string stage;
    { kp::harness::HookBodyScope s; stage = a->chargen_stage(); }
    lua_pushlstring(L, stage.data(), stage.size());
    return 1;
}
int l_h_adapter_name(lua_State* L) {
    auto* a = kp::harness::adapter();
    if (!a) return luaL_error(L, "harness: no engine adapter");
    std::string name;
    { kp::harness::HookBodyScope s; name = a->name(); }
    lua_pushlstring(L, name.data(), name.size());
    return 1;
}
int l_h_reply(lua_State* L) {
    const int index = check_int(L, 1, "dialog reply index");
    return harness_call(L, [index](kp::harness::EngineAdapter& a) {
        return a.reply(index);
    });
}
int l_h_dialog(lua_State* L) {
    auto* a = kp::harness::adapter(); if (!a) return luaL_error(L, "harness: no engine adapter");
    const int base = lua_gettop(L);
    char error[1024]{};
    bool ok = false;
    {
        kp::harness::DialogState d;
        kp::harness::Result r;
        { kp::harness::HookBodyScope s; r = a->dialog(&d); }
        if (!r.ok) {
            std::snprintf(error, sizeof error, "%s", r.error.c_str());
        } else {
            lua_pushcfunction(L, push_dialog_table);
            lua_pushlightuserdata(L, &d);
            ok = lua_pcall(L, 1, 1, 0) == 0;
            if (!ok) {
                const char* msg = lua_tostring(L, -1);
                std::snprintf(error, sizeof error, "%s", msg ? msg : "cannot serialize dialog state");
                lua_settop(L, base);
            }
        }
    }
    if (!ok) { lua_pushstring(L, error); return lua_error(L); }
    return 1;
}
int l_h_movies_enabled(lua_State* L) {
    auto* a=kp::harness::adapter(); if(!a) return luaL_error(L,"harness: no engine adapter");
    bool enabled; { kp::harness::HookBodyScope s; enabled=a->movies_enabled(); }
    lua_pushboolean(L,enabled); return 1;
}
int l_h_missing_sites(lua_State* L) {
    auto* a=kp::harness::adapter(); if(!a) return luaL_error(L,"harness: no engine adapter");
    std::vector<std::string> sites; { kp::harness::HookBodyScope s; sites = a->missing_sites(); } lua_newtable(L);
    for (std::size_t i = 0; i < sites.size(); ++i) { lua_pushlstring(L, sites[i].data(), sites[i].size()); lua_rawseti(L, -2, static_cast<int>(i + 1)); }
    return 1;
}
int l_h_events(lua_State* L) {
    lua_Integer since = 0;
    lua_Integer requested_limit = 256;
    if (!lua_isnoneornil(L, 1)) {
        since = luaL_checkinteger(L, 1);
        if (since < 0) return luaL_argerror(L, 1, "event cursor must be non-negative");
    }
    if (!lua_isnoneornil(L, 2)) {
        requested_limit = luaL_checkinteger(L, 2);
        if (requested_limit < 0) return luaL_argerror(L, 2, "event limit must be non-negative");
    }
    const auto normalized_limit = requested_limit == 0 ? 256 : requested_limit;
    const auto limit = static_cast<std::size_t>(normalized_limit > static_cast<lua_Integer>(kp::harness::EventRing::kCapacity)
        ? kp::harness::EventRing::kCapacity : normalized_limit);
    std::vector<kp::harness::EventRecord> records;
    kp::harness::ring().read_since(static_cast<std::uint64_t>(since), limit, records);
    lua_newtable(L);
    lua_pushinteger(L, static_cast<lua_Integer>(kp::harness::ring().last_seq())); lua_setfield(L, -2, "seq");
    lua_pushinteger(L, static_cast<lua_Integer>(kp::harness::ring().oldest_seq())); lua_setfield(L, -2, "oldest");
    lua_newtable(L);
    for (std::size_t i = 0; i < records.size(); ++i) {
        const auto& record = records[i];
        lua_newtable(L);
        lua_pushlstring(L, record.name, std::strlen(record.name)); lua_setfield(L, -2, "event");
        lua_pushinteger(L, static_cast<lua_Integer>(record.server_tick)); lua_setfield(L, -2, "tick");
        lua_pushinteger(L, static_cast<lua_Integer>(record.seq)); lua_setfield(L, -2, "seq");
        for (std::size_t f = 0; f < record.field_count(); ++f) {
            const auto& field = record.fields[f];
            switch (field.kind) {
            case kp::harness::EventField::Kind::Int:
                lua_pushinteger(L, static_cast<lua_Integer>(field.i)); break;
            case kp::harness::EventField::Kind::Uint:
                lua_pushnumber(L, static_cast<lua_Number>(static_cast<std::uint64_t>(field.i))); break;
            case kp::harness::EventField::Kind::Text:
                lua_pushstring(L, field.text); break;
            case kp::harness::EventField::Kind::None:
                lua_pushnil(L); break;
            }
            lua_setfield(L, -2, field.key != nullptr ? field.key : "");
        }
        lua_rawseti(L, -2, static_cast<int>(i + 1));
    }
    lua_setfield(L, -2, "items");
    return 1;
}
int l_h_screenshot(lua_State* L) {
    const char* path = luaL_checkstring(L, 1);
    std::string error;
    if (!kp::harness::request_screenshot(path, error)) {
        lua_pushnil(L);
        lua_pushlstring(L, error.data(), error.size());
        return 2;
    }
    lua_pushboolean(L, 1);
    return 1;
}
int l_h_take_screenshot_result(lua_State* L) {
    kp::harness::ScreenshotResult result;
    if (!kp::harness::take_screenshot_result(result)) { lua_pushnil(L); return 1; }
    lua_newtable(L);
    lua_pushboolean(L, result.ok); lua_setfield(L, -2, "ok");
    lua_pushlstring(L, result.path.data(), result.path.size()); lua_setfield(L, -2, "path");
    if (result.ok) {
        lua_pushinteger(L, result.width); lua_setfield(L, -2, "width");
        lua_pushinteger(L, result.height); lua_setfield(L, -2, "height");
        lua_pushinteger(L, static_cast<lua_Integer>(result.client_tick)); lua_setfield(L, -2, "client_tick");
        lua_pushstring(L, "ppm"); lua_setfield(L, -2, "format");
    } else {
        lua_pushlstring(L, result.error.data(), result.error.size()); lua_setfield(L, -2, "error");
    }
    return 1;
}
int l_h_quit(lua_State* L) {
    (void)L;
    kp::harness::request_quit();
    lua_pushboolean(L, 1);
    return 1;
}
int l_h_reload(lua_State* L) {
    (void)L;
    kp::harness::request_reload();
    lua_pushboolean(L, 1);
    return 1;
}
int l_h_status(lua_State* L) {
    auto& runtime = kp::runtime::Runtime::instance();
    lua_newtable(L);
    lua_pushstring(L, KP_VERSION); lua_setfield(L, -2, "version");
    lua_pushlstring(L, runtime.build().data(), runtime.build().size()); lua_setfield(L, -2, "build");
    if (const auto* table = runtime.table()) {
        lua_pushlstring(L, table->game().data(), table->game().size()); lua_setfield(L, -2, "game");
    }
    lua_pushstring(L, kp::runtime::to_string(runtime.phase())); lua_setfield(L, -2, "phase");
    lua_pushboolean(L, kp::runtime::live()); lua_setfield(L, -2, "live");
    lua_pushboolean(L, kp::runtime::vm_bound()); lua_setfield(L, -2, "vm_bound");
#if defined(_WIN32)
    lua_pushinteger(L, static_cast<lua_Integer>(GetCurrentProcessId()));
#else
    lua_pushinteger(L, static_cast<lua_Integer>(::getpid()));
#endif
    lua_setfield(L, -2, "pid");
    lua_pushinteger(L, static_cast<lua_Integer>(kp::harness::uptime_ms())); lua_setfield(L, -2, "uptime_ms");
    if (!runtime.failure().empty()) {
        lua_pushlstring(L, runtime.failure().data(), runtime.failure().size()); lua_setfield(L, -2, "failure");
    }
    lua_pushinteger(L, static_cast<lua_Integer>(kp::harness::client_tick())); lua_setfield(L, -2, "client_tick");
    auto* host = kp::runtime::active_host();
    lua_pushinteger(L, host ? static_cast<lua_Integer>(host->tick()) : 0); lua_setfield(L, -2, "server_tick");
    lua_pushinteger(L, host ? static_cast<lua_Integer>(host->scripts().size()) : 0); lua_setfield(L, -2, "scripts");
    lua_pushinteger(L, static_cast<lua_Integer>(runtime.hooks() ? runtime.hooks()->installed_count() : 0)); lua_setfield(L, -2, "hooks");
    auto* adapter = kp::harness::adapter();
    std::string adapter_name;
    std::vector<std::string> missing;
    if (adapter) {
        kp::harness::HookBodyScope scope;
        adapter_name = adapter->name();
        missing = adapter->missing_sites();
    }
    lua_pushlstring(L, adapter_name.data(), adapter_name.size()); lua_setfield(L, -2, "adapter");
    lua_pushinteger(L, static_cast<lua_Integer>(kp::harness::ring().last_seq())); lua_setfield(L, -2, "events_seq");
    lua_newtable(L);
    for (std::size_t i = 0; i < missing.size(); ++i) {
        lua_pushlstring(L, missing[i].data(), missing[i].size()); lua_rawseti(L, -2, static_cast<int>(i + 1));
    }
    lua_setfield(L, -2, "missing_sites");
    lua_newtable(L);
    const auto poisoned = kp::runtime::poisoned_sites();
    for (std::size_t i = 0; i < poisoned.size(); ++i) {
        lua_pushlstring(L, poisoned[i].data(), poisoned[i].size()); lua_rawseti(L, -2, static_cast<int>(i + 1));
    }
    lua_setfield(L, -2, "poisoned");
    return 1;
}

int l_h_ping(lua_State* L) {
    auto& runtime = kp::runtime::Runtime::instance();
    lua_newtable(L);
    lua_pushboolean(L, 1); lua_setfield(L, -2, "pong");
    auto* host = kp::runtime::active_host();
    lua_pushinteger(L, host ? static_cast<lua_Integer>(host->tick()) : 0); lua_setfield(L, -2, "tick");
    lua_pushlstring(L, runtime.build().data(), runtime.build().size()); lua_setfield(L, -2, "build");
    lua_pushstring(L, kp::runtime::to_string(runtime.phase())); lua_setfield(L, -2, "phase");
    lua_pushboolean(L, kp::runtime::live()); lua_setfield(L, -2, "live");
    return 1;
}
int l_h_globals(lua_State* L) {
    auto* a=kp::harness::adapter(); if(!a) return luaL_error(L,"harness: no engine adapter");
    struct Collect final : kp::harness::GlobalsVisitor {
        struct Bool { std::string name; bool value; }; struct Number { std::string name; int value; }; struct String { std::string name, value; };
        std::vector<Bool> bools; std::vector<Number> numbers; std::vector<String> strings;
        void on_bool(const char* name, bool value) override { bools.push_back({name ? name : "", value}); }
        void on_number(const char* name, int value) override { numbers.push_back({name ? name : "", value}); }
        void on_string(const char* name, const char* value) override { strings.push_back({name ? name : "", value ? value : ""}); }
    };
    char error[1024]{};
    bool ok = false;
    {
        Collect collect;
        kp::harness::Result r = kp::harness::Result::success();
        { kp::harness::HookBodyScope s; r = a->walk_globals(collect); }
        ok = r.ok;
        if (!r.ok) std::snprintf(error, sizeof error, "%s", r.error.c_str());
        else {
            lua_newtable(L); lua_newtable(L); for (const auto& v : collect.bools) { lua_pushboolean(L,v.value); lua_setfield(L,-2,v.name.c_str()); } lua_setfield(L,-2,"bools");
            lua_newtable(L); for (const auto& v : collect.numbers) { lua_pushinteger(L,v.value); lua_setfield(L,-2,v.name.c_str()); } lua_setfield(L,-2,"numbers");
            lua_newtable(L); for (const auto& v : collect.strings) { lua_pushlstring(L,v.value.data(),v.value.size()); lua_setfield(L,-2,v.name.c_str()); } lua_setfield(L,-2,"strings");
        }
    }
    if (!ok) return luaL_error(L, "%s", error);
    return 1;
}
int l_h_journal(lua_State* L) {
    auto* a=kp::harness::adapter(); if(!a) return luaL_error(L,"harness: no engine adapter");
    struct Collect final : kp::harness::JournalVisitor {
        struct Entry { std::string tag; int state; }; std::vector<Entry> entries;
        void on_entry(const char* tag, int state) override { entries.push_back({tag ? tag : "", state}); }
    };
    char error[1024]{};
    bool ok = false;
    {
        Collect collect;
        kp::harness::Result r = kp::harness::Result::success();
        { kp::harness::HookBodyScope s; r = a->walk_journal(collect); }
        ok = r.ok;
        if (!r.ok) std::snprintf(error, sizeof error, "%s", r.error.c_str());
        else {
            lua_newtable(L);
            for (std::size_t i=0; i<collect.entries.size(); ++i) { const auto& e=collect.entries[i]; lua_newtable(L); lua_pushlstring(L,e.tag.data(),e.tag.size()); lua_setfield(L,-2,"tag"); lua_pushinteger(L,e.state); lua_setfield(L,-2,"state"); lua_rawseti(L,-2,static_cast<int>(i+1)); }
        }
    }
    if (!ok) return luaL_error(L, "%s", error);
    return 1;
}
int l_h_set_party_leader(lua_State* L) {
    const int selector = check_int(L, 1, "party leader index");
    return harness_call(L, [selector](kp::harness::EngineAdapter& a) {
        return a.set_party_leader(selector);
    });
}
int l_h_use_item(lua_State* L) {
    const auto item = check_u32(L, 1, "item id");
    const auto target = (lua_gettop(L) >= 2 && !lua_isnoneornil(L, 2))
        ? check_u32(L, 2, "target id") : 0u;
    return harness_call(L, [item, target](kp::harness::EngineAdapter& a) {
        return a.use_item(item, target);
    });
}
int l_h_equip_item(lua_State* L) {
    const auto item = check_u32(L, 1, "item id");
    const auto slot = check_u32(L, 2, "equipment slot");
    bool instant = true;
    if (lua_gettop(L) >= 3 && !lua_isnoneornil(L, 3)) {
        luaL_checktype(L, 3, LUA_TBOOLEAN);
        instant = lua_toboolean(L, 3) != 0;
    }
    return harness_call(L, [item, slot, instant](kp::harness::EngineAdapter& a) {
        return a.equip_item(item, slot, instant);
    });
}
int l_h_auto_levelup(lua_State* L) {
    return harness_call(L, [](kp::harness::EngineAdapter& a) {
        return a.auto_levelup();
    });
}

template <typename Take, typename Push>
int take_harness_result(lua_State* L, Take&& take, Push&& push) {
    bool ready = false;
    bool ok = true;
    char error[1024]{};
    {
        kp::harness::Result status = kp::harness::Result::success();
        { kp::harness::HookBodyScope scope; ready = take(&status); }
        ok = status.ok;
        if (ready && !status.ok) std::snprintf(error, sizeof error, "%s", status.error.c_str());
    }
    if (!ready) { lua_pushnil(L); return 1; }
    if (!ok) return luaL_error(L, "%s", error);
    push(L); return 1;
}
int l_h_take_door_security_result(lua_State* L) {
    auto* a = kp::harness::adapter();
    if (!a) return luaL_error(L, "harness: no engine adapter");
    kp::harness::DoorSecurityResult out;
    return take_harness_result(L,
        [&](kp::harness::Result* status) { return a->take_door_security_result(status, &out); },
        [&](lua_State* s) {
            lua_newtable(s);
            push_u32(s, out.door_id); lua_setfield(s, -2, "door");
            lua_pushboolean(s, out.locked_before); lua_setfield(s, -2, "locked_before");
            lua_pushboolean(s, out.locked_after); lua_setfield(s, -2, "locked_after");
            push_u32(s, out.open_state_before); lua_setfield(s, -2, "open_state_before");
            push_u32(s, out.open_state_after); lua_setfield(s, -2, "open_state_after");
        });
}
int l_h_take_party_leader_result(lua_State* L) {
    auto* a = kp::harness::adapter();
    if (!a) return luaL_error(L, "harness: no engine adapter");
    kp::harness::PartyLeaderResult out;
    return take_harness_result(L,
        [&](kp::harness::Result* status) { return a->take_party_leader_result(status, &out); },
        [&](lua_State* s) {
            lua_newtable(s);
            push_u32(s, out.leader_before); lua_setfield(s, -2, "leader_before");
            push_u32(s, out.leader_after); lua_setfield(s, -2, "leader_after");
        });
}
int l_h_take_use_item_result(lua_State* L) {
    auto* a = kp::harness::adapter();
    if (!a) return luaL_error(L, "harness: no engine adapter");
    kp::harness::UseItemResult out;
    return take_harness_result(L,
        [&](kp::harness::Result* status) { return a->take_use_item_result(status, &out); },
        [&](lua_State* s) {
            lua_newtable(s);
            push_u32(s, out.item_id); lua_setfield(s, -2, "item");
            push_u32(s, out.target_id); lua_setfield(s, -2, "target");
        });
}
int l_h_take_equip_item_result(lua_State* L) {
    auto* a = kp::harness::adapter();
    if (!a) return luaL_error(L, "harness: no engine adapter");
    kp::harness::EquipItemResult out;
    return take_harness_result(L,
        [&](kp::harness::Result* status) { return a->take_equip_item_result(status, &out); },
        [&](lua_State* s) {
            lua_newtable(s);
            push_u32(s, out.requested_item_id); lua_setfield(s, -2, "requested_item");
            push_u32(s, out.current_item_id); lua_setfield(s, -2, "current_item");
            push_u32(s, out.slot); lua_setfield(s, -2, "slot");
        });
}
int l_h_take_auto_levelup_result(lua_State* L) {
    auto* a = kp::harness::adapter();
    if (!a) return luaL_error(L, "harness: no engine adapter");
    kp::harness::AutoLevelResult out;
    return take_harness_result(L,
        [&](kp::harness::Result* status) { return a->take_auto_levelup_result(status, &out); },
        [&](lua_State* s) {
            lua_newtable(s);
            push_u32(s, out.player_id); lua_setfield(s, -2, "player_id");
            lua_pushinteger(s, out.level_before); lua_setfield(s, -2, "level_before");
            lua_pushinteger(s, out.level_after); lua_setfield(s, -2, "level_after");
            push_u32(s, out.experience); lua_setfield(s, -2, "experience");
            if (out.can_level_up >= 0) {
                lua_pushboolean(s, out.can_level_up != 0); lua_setfield(s, -2, "can_level_up");
            }
        });
}
int l_h_warp(lua_State* L) {
    const char* module = luaL_checkstring(L, 1);
    return harness_call(L, [module](kp::harness::EngineAdapter& a) {
        return a.warp(module);
    });
}
int l_h_load_save(lua_State* L) {
    const char* dir = luaL_checkstring(L, 1);
    return harness_call(L, [dir](kp::harness::EngineAdapter& a) {
        return a.load_save(dir);
    });
}
int l_h_save(lua_State* L) {
    const int slot = check_int(L, 1, "save slot");
    const char* name = luaL_optstring(L, 2, "harness");
    return harness_call(L, [slot, name](kp::harness::EngineAdapter& a) {
        return a.save(slot, name);
    });
}
int l_h_door_use(lua_State* L) {
    const auto door = check_u32(L, 1, "door id");
    return harness_call(L, [door](kp::harness::EngineAdapter& a) { return a.door_use(door); });
}
int l_h_door_commit_open(lua_State* L) {
    const auto door = check_u32(L, 1, "door id");
    return harness_call(L, [door](kp::harness::EngineAdapter& a) { return a.door_commit_open(door); });
}
int l_h_door_security(lua_State* L) {
    const auto door = check_u32(L, 1, "door id");
    return harness_call(L, [door](kp::harness::EngineAdapter& a) { return a.door_security(door); });
}
int l_h_attack(lua_State* L) {
    const auto target = check_u32(L, 1, "target id");
    return harness_call(L, [target](kp::harness::EngineAdapter& a) { return a.attack(target); });
}
int l_h_equipment(lua_State* L) {
    luaL_checktype(L, 1, LUA_TBOOLEAN);
    const bool visible = lua_toboolean(L, 1) != 0;
    return harness_call(L, [visible](kp::harness::EngineAdapter& a) {
        return a.equipment_screen(visible);
    });
}

}  // namespace

const char* event_for_constant(int constant) {
    for (unsigned i = 0; i < kEventCount; ++i)
        if (kEvents[i].value == constant) return kEvents[i].lua_name;
    return nullptr;
}

const char* event_for_name(const char* name) {
    if (name == nullptr) return nullptr;
    for (unsigned i = 0; i < kEventCount; ++i)
        if (std::strcmp(kEvents[i].name, name) == 0) return kEvents[i].lua_name;
    return nullptr;
}

unsigned event_constant_count() { return kEventCount; }

void install(lua_State* L, const std::string& game_dir) {
    push_kp_table(L);
    lua_getfield(L, -1, "events");
    if (!lua_istable(L, -1)) { lua_pop(L, 1); lua_createtable(L, 0, int(kEventCount) + 2); }
    for (unsigned i = 0; i < kEventCount; ++i) {
        lua_pushinteger(L, kEvents[i].value);
        lua_setfield(L, -2, kEvents[i].name);
    }
    lua_pushcfunction(L, l_register_callback);
    lua_setfield(L, -2, "register");
    lua_pushcfunction(L, l_unregister_callback);
    lua_setfield(L, -2, "unregister");
    lua_setfield(L, -2, "events");

    lua_pushcfunction(L, lua_print_to_log); lua_setfield(L, -2, "print");
    lua_pushstring(L, "KotorPhasor"); lua_setfield(L, -2, "host");
    lua_pushstring(L, "KotorPhasor"); lua_setfield(L, -2, "serverapp");
    lua_pushstring(L, "KOTOR"); lua_setfield(L, -2, "game");
    lua_pushinteger(L, 2); lua_setfield(L, -2, "api_version");
    lua_pushstring(L, KP_VERSION);
    lua_setfield(L, -2, "version");

    lua_pushstring(L, game_dir.c_str());
    lua_pushcclosure(L, l_kp_gamedir, 1);
    lua_setfield(L, -2, "gamedir");

    lua_pushcfunction(L, l_kp_time);
    lua_setfield(L, -2, "time");

    lua_getfield(L, -1, "harness");
    if (!lua_istable(L, -1)) { lua_pop(L, 1); lua_newtable(L); }
#define KP_H_REG(n) lua_pushcfunction(L, l_h_##n); lua_setfield(L, -2, #n)
    KP_H_REG(dialog_skip); KP_H_REG(dialog_abort); KP_H_REG(dialog_continue);
    KP_H_REG(unpause_timers); KP_H_REG(advance_tutorial); KP_H_REG(finish_hidden_tutorial);
    KP_H_REG(dismiss_status_summary); KP_H_REG(dismiss_messagebox);
    KP_H_REG(dismiss_container); KP_H_REG(take_all_container);
    KP_H_REG(accept_party_selection); KP_H_REG(speed); KP_H_REG(fixed_step);
    KP_H_REG(new_game); KP_H_REG(chargen_select_class); KP_H_REG(chargen_begin_play);
    KP_H_REG(chargen_stage); KP_H_REG(adapter_name); KP_H_REG(dialog); KP_H_REG(reply);
    KP_H_REG(dialog_clear_sound_wait); KP_H_REG(clear_auto_pause);
    KP_H_REG(warp); KP_H_REG(load_save); KP_H_REG(save);
    KP_H_REG(door_use); KP_H_REG(door_commit_open); KP_H_REG(door_security); KP_H_REG(attack);
    KP_H_REG(take_door_security_result); KP_H_REG(set_party_leader);
    KP_H_REG(take_party_leader_result); KP_H_REG(use_item); KP_H_REG(take_use_item_result);
    KP_H_REG(equip_item); KP_H_REG(take_equip_item_result); KP_H_REG(auto_levelup);
    KP_H_REG(take_auto_levelup_result); KP_H_REG(equipment); KP_H_REG(movies);
    KP_H_REG(movies_enabled); KP_H_REG(state); KP_H_REG(missing_sites);
    KP_H_REG(globals); KP_H_REG(journal);
    KP_H_REG(ping); KP_H_REG(status); KP_H_REG(events); KP_H_REG(screenshot); KP_H_REG(take_screenshot_result);
    KP_H_REG(reload); KP_H_REG(quit);
    lua_pushcfunction(L, l_h_equipment); lua_setfield(L, -2, "equipment_screen");
#undef KP_H_REG
    lua_setfield(L, -2, "harness");
    lua_pop(L, 1);

    platform::log(platform::LogLevel::Info,
                  "api: kp native facilities installed, %u event constants", kEventCount);
}

}  // namespace kp::api::compat

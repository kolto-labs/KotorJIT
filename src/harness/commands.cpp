#include "devtools/console.hpp"
#include "harness/console_protocol.hpp"
// The harness commands. See commands.hpp for the drain's rules.
//
// Every command takes the parsed request and fills an Outcome. Engine work
// goes through the EngineAdapter between enter_hook_body() and
// leave_hook_body(); Lua work runs under the harness's own fault guard; the
// rest is bookkeeping on harness-owned memory and needs neither.
#include "harness/commands.hpp"
#include "api/output.hpp"

#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <utility>

#include "harness/channel.hpp"
#include "harness/engine.hpp"
#include "harness/fields.hpp"   // HookBodyScope
#include "harness/json.hpp"
#include "harness/ring.hpp"
#include "hooks/registry.hpp"
#include "lua/host.hpp"
#include "platform/platform.hpp"
#include "runtime/internal.hpp"
#include "runtime/runtime.hpp"
#include "version.hpp"

extern "C" {
#include "lauxlib.h"
#include "lua.h"
#include "lualib.h"
}

#if defined(_WIN32)
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#else
#include <dlfcn.h>
#include <unistd.h>
#endif

namespace kp::harness {
namespace {

using runtime::Runtime;

std::atomic<bool> g_poison{false};
std::atomic<bool> g_quit{false};
std::atomic<bool> g_lua_reload_requested{false};
std::atomic<std::uint64_t> g_client_tick{0};

// The channel is built on the bootstrap worker and used from the client-loop
// hook on the game thread. Explicitly deleted on quiescent stop() /
// stop_after_flush() rather than via a static unique_ptr destructor, so
// FreeLibrary under DLL_PROCESS_DETACH never joins Channel's thread under the
// OS loader lock.
Channel*                       g_channel = nullptr;
std::atomic<Channel*>          g_channel_ptr{nullptr};
std::mutex                     g_drain_mutex;

Channel* channel() { return g_channel_ptr.load(std::memory_order_acquire); }

std::unique_ptr<EngineAdapter> g_adapter;
std::chrono::steady_clock::time_point g_started;

// Event streaming: which client subscribed and where its cursor is.
std::uint64_t g_stream_client = 0;
std::uint64_t g_stream_cursor = 0;

// The one screenshot that may be pending. The reply is held until the frame
// after the request has rendered, so the file is complete when the driver
// reads the reply.
struct PendingShot {
    bool          active = false;
    bool          lua_request = false;
    std::uint64_t client = 0;
    Json          id;
    std::string   path;
};
PendingShot g_shot;
ScreenshotResult g_lua_shot_result;

struct PendingAutoLevelReply {
    bool active = false;
    std::uint64_t client = 0;
    Json id;
};
PendingAutoLevelReply g_auto_level;
PendingAutoLevelReply g_party_leader;
PendingAutoLevelReply g_use_item;
PendingAutoLevelReply g_equip_item;
PendingAutoLevelReply g_door_security;

// ------------------------------------------------------------ replies -------

struct Outcome {
    bool        ok = true;
    bool        deferred = false;
    std::string error;
    Json        result = Json::object();
};

Json id_of(const Json& req) {
    const Json* id = req.get("id");
    return id != nullptr ? *id : Json::null();
}

Json ok_reply(const Json& id, Json result) {
    Json r = Json::object();
    r.set("id", id);
    r.set("ok", Json::boolean(true));
    r.set("result", std::move(result));
    return r;
}

Json err_reply(const Json& id, std::string error) {
    Json r = Json::object();
    r.set("id", id);
    r.set("ok", Json::boolean(false));
    r.set("error", Json::string(std::move(error)));
    return r;
}

void fail(Outcome& out, std::string error) {
    out.ok = false;
    out.error = std::move(error);
}

void from_result(Outcome& out, const Result& r) {
    if (!r.ok) fail(out, r.error);
}

std::uint64_t server_tick() {
    lua::Host* h = runtime::active_host();
    return h != nullptr ? h->tick() : 0;
}

const char* phase_name(Phase p) {
    switch (p) {
    case Phase::Unknown:  return "unknown";
    case Phase::Menu:     return "menu";
    case Phase::Loading:  return "loading";
    case Phase::Gameplay: return "gameplay";
    case Phase::Dialog:   return "dialog";
    case Phase::Movie:    return "movie";
    case Phase::Paused:   return "paused";
    case Phase::Minigame: return "minigame";
    case Phase::GameOver: return "gameover";
    case Phase::Error:    return "error";
    }
    return "unknown";
}

// A JSON number as an argument the command can use. A finite number outside
// the target range is refused rather than converted: converting it is
// undefined behaviour, and `1e20` is a line a client can send.
bool as_int_arg(const Json& v, int& out) {
    if (!v.is_number()) return false;
    const double d = v.as_number();
    if (std::isnan(d) || std::isinf(d)) return false;
    const double t = std::trunc(d);
    if (t < -2147483648.0 || t > 2147483647.0) return false;
    out = static_cast<int>(t);
    return true;
}

// The same for a count or a cursor: negative and out of range both refuse.
bool as_uint_arg(const Json& v, std::uint64_t& out) {
    if (!v.is_number()) return false;
    const double d = v.as_number();
    if (std::isnan(d) || std::isinf(d)) return false;
    const double t = std::trunc(d);
    if (t < 0.0 || t > 9007199254740992.0) return false;
    out = static_cast<std::uint64_t>(t);
    return true;
}

// Engine work runs in an unarmed hook-body frame: the fault guard knows we
// are inside our own code (so a nested armed frame still claims correctly)
// but claims nothing at this depth. See the header. HookBodyScope leaves the
// frame on every exit, so an allocation failure inside fn cannot leave the
// thread's depth counter raised and its fault-frame state poisoned.
template <typename Fn>
auto engine(Fn&& fn) -> decltype(fn()) {
    HookBodyScope scope;
    return fn();
}

bool need_adapter(Outcome& out) {
    if (g_adapter) return true;
    fail(out, "no engine adapter on this build");
    return false;
}

// FNV-1a over a byte sequence. 64-bit, printed as 16 hex digits.
struct Fnv {
    std::uint64_t h = 1469598103934665603ull;
    void add(const char* s) {
        if (s == nullptr) return;
        for (; *s != '\0'; ++s) add_byte(static_cast<unsigned char>(*s));
        add_byte(0);
    }
    void add_int(std::int64_t v) {
        for (int i = 0; i < 8; ++i) add_byte(static_cast<unsigned char>(v >> (8 * i)));
    }
    void add_byte(unsigned char b) {
        h ^= b;
        h *= 1099511628211ull;
    }
    std::string hex() const {
        char buf[24];
        std::snprintf(buf, sizeof buf, "%016llx", static_cast<unsigned long long>(h));
        return buf;
    }
};

// ------------------------------------------------------------- the Lua ------

// A state of the harness's own, with the same API every script and the
// console get. Not a script's state: a harness typo must not quarantine a
// loaded script, and `reload` closes and rebuilds this one along with theirs.
lua_State*  g_L = nullptr;
std::string g_lua_output;

int harness_print(lua_State* L) {
    const int n = lua_gettop(L);
    for (int i = 1; i <= n; ++i) {
        if (i > 1) g_lua_output += "\t";
        const char* s = lua_tostring(L, i);
        g_lua_output += (s != nullptr) ? s : luaL_typename(L, i);
    }
    g_lua_output += "\n";
    return 0;
}

lua_State* harness_state() {
    if (g_L != nullptr) return g_L;
    g_L = luaL_newstate();
    if (g_L == nullptr) return nullptr;
    luaL_openlibs(g_L);
    runtime::init_lua_state(g_L);
    api::push_kp_table(g_L);
    lua_pushcfunction(g_L, harness_print);
    lua_setfield(g_L, -2, "print");
    lua_pop(g_L, 1);
    return g_L;
}

void close_harness_state() {
    if (g_L != nullptr) { lua_close(g_L); g_L = nullptr; }
}

// Lua value -> JSON. Tables nest to a small depth; anything else that has no
// JSON spelling becomes its type name so the driver sees what it got.
constexpr int kLuaDepth = 4;

Json lua_to_json(lua_State* L, int idx, int depth) {
    // LuaJIT has no lua_absindex; a relative index must be made absolute by
    // hand before lua_next pushes over it.
    if (idx < 0) idx = lua_gettop(L) + idx + 1;
    switch (lua_type(L, idx)) {
    case LUA_TNIL:     return Json::null();
    case LUA_TBOOLEAN: return Json::boolean(lua_toboolean(L, idx) != 0);
    case LUA_TNUMBER:  return Json::number(lua_tonumber(L, idx));
    case LUA_TSTRING: {
        std::size_t len = 0;
        const char* s = lua_tolstring(L, idx, &len);
        return Json::string(std::string(s, len));
    }
    case LUA_TTABLE: {
        if (depth >= kLuaDepth) return Json::string("table");
        // Array iff every key is an integer 1..n.
        std::size_t entries = 0;
        bool array = true;
        lua_pushnil(L);
        while (lua_next(L, idx) != 0) {
            ++entries;
            if (lua_type(L, -2) != LUA_TNUMBER) array = false;
            else {
                const lua_Number k = lua_tonumber(L, -2);
                if (k < 1 || k != static_cast<lua_Number>(static_cast<long long>(k))) array = false;
            }
            lua_pop(L, 1);
        }
        const std::size_t n = lua_objlen(L, idx);
        if (array && entries == n) {
            Json a = Json::array();
            for (std::size_t i = 1; i <= n; ++i) {
                lua_rawgeti(L, idx, static_cast<int>(i));
                a.push(lua_to_json(L, -1, depth + 1));
                lua_pop(L, 1);
            }
            return a;
        }
        Json o = Json::object();
        lua_pushnil(L);
        while (lua_next(L, idx) != 0) {
            std::string key;
            if (lua_type(L, -2) == LUA_TSTRING) {
                key = lua_tostring(L, -2);
            } else if (lua_type(L, -2) == LUA_TNUMBER) {
                char buf[32];
                std::snprintf(buf, sizeof buf, "%.17g", lua_tonumber(L, -2));
                key = buf;
            } else {
                key = luaL_typename(L, -2);
            }
            o.set(std::move(key), lua_to_json(L, -1, depth + 1));
            lua_pop(L, 1);
        }
        return o;
    }
    default: {
        char buf[64];
        std::snprintf(buf, sizeof buf, "%s: %p", luaL_typename(L, idx), lua_topointer(L, idx));
        return Json::string(buf);
    }
    }
}

// Run `code` in the harness state. Returns false with `error` on a parse or
// runtime error; on success `values` holds the chunk's returns and `output`
// whatever it printed. Not guarded here: the caller arms the guard, because
// the fallback has to re-state the caller's own locals.
bool run_lua(const std::string& code, const char* chunk_name, Json& values,
             std::string& output, std::string& error) {
    lua_State* L = harness_state();
    if (L == nullptr) { error = "cannot create the harness lua state"; return false; }
    g_lua_output.clear();
    const int base = lua_gettop(L);

    // An expression first, so `return` is optional the way it is on the
    // console, then the text as a statement.
    const std::string as_expr = "return " + code;
    if (luaL_loadbuffer(L, as_expr.c_str(), as_expr.size(), chunk_name) != 0) {
        lua_pop(L, 1);
        if (luaL_loadbuffer(L, code.c_str(), code.size(), chunk_name) != 0) {
            const char* msg = lua_tostring(L, -1);
            error = msg != nullptr ? msg : "parse failed";
            lua_settop(L, base);
            return false;
        }
    }
    if (lua_pcall(L, 0, LUA_MULTRET, 0) != 0) {
        const char* msg = lua_tostring(L, -1);
        error = msg != nullptr ? msg : "error";
        output = g_lua_output;
        lua_settop(L, base);
        return false;
    }
    const int nres = lua_gettop(L) - base;
    values = Json::array();
    for (int i = 1; i <= nres; ++i) values.push(lua_to_json(L, base + i, 0));
    output = g_lua_output;
    lua_settop(L, base);
    return true;
}

// ----------------------------------------------------------- screenshot -----
//
// GL entry points resolved by name at first use, never linked: the DLL must
// load in a process that has not yet loaded opengl32, and the native build
// must not drag libGL into a link that otherwise needs none.

#if defined(_WIN32)
#define KP_GLAPI __attribute__((stdcall))
#else
#define KP_GLAPI
#endif

using GlGetIntegerv = void (KP_GLAPI*)(unsigned, int*);
using GlReadBuffer  = void (KP_GLAPI*)(unsigned);
using GlPixelStorei = void (KP_GLAPI*)(unsigned, int);
using GlReadPixels  = void (KP_GLAPI*)(int, int, int, int, unsigned, unsigned, void*);
using GlGetError    = unsigned (KP_GLAPI*)();

constexpr unsigned kGlViewport      = 0x0BA2;
constexpr unsigned kGlFront         = 0x0404;
constexpr unsigned kGlPackAlignment = 0x0D05;
constexpr unsigned kGlRgb           = 0x1907;
constexpr unsigned kGlUnsignedByte  = 0x1401;

struct Gl {
    bool          resolved = false;
    GlGetIntegerv get_integerv = nullptr;
    GlReadBuffer  read_buffer = nullptr;
    GlPixelStorei pixel_storei = nullptr;
    GlReadPixels  read_pixels = nullptr;
    GlGetError    get_error = nullptr;
};
Gl g_gl;

void* gl_symbol(const char* name) {
#if defined(_WIN32)
    HMODULE m = GetModuleHandleA("opengl32.dll");
    if (m == nullptr) return nullptr;
    return reinterpret_cast<void*>(GetProcAddress(m, name));
#else
    return ::dlsym(RTLD_DEFAULT, name);
#endif
}

bool resolve_gl(std::string& error) {
    if (g_gl.resolved) return true;
    g_gl.get_integerv = reinterpret_cast<GlGetIntegerv>(gl_symbol("glGetIntegerv"));
    g_gl.read_buffer  = reinterpret_cast<GlReadBuffer>(gl_symbol("glReadBuffer"));
    g_gl.pixel_storei = reinterpret_cast<GlPixelStorei>(gl_symbol("glPixelStorei"));
    g_gl.read_pixels  = reinterpret_cast<GlReadPixels>(gl_symbol("glReadPixels"));
    g_gl.get_error    = reinterpret_cast<GlGetError>(gl_symbol("glGetError"));
    if (g_gl.get_integerv == nullptr || g_gl.read_buffer == nullptr ||
        g_gl.pixel_storei == nullptr || g_gl.read_pixels == nullptr) {
        error = "GL entry points not found; is a GL context loaded in this process?";
        return false;
    }
    g_gl.resolved = true;
    return true;
}

// Front buffer to a binary PPM at `path`. Runs after orig(self) returned in
// the client-loop detour, on the render thread, so the context is current.
bool write_screenshot(const std::string& path, int& width, int& height, std::string& error) {
    if (!resolve_gl(error)) return false;

    int viewport[4] = {0, 0, 0, 0};
    g_gl.get_integerv(kGlViewport, viewport);
    width = viewport[2];
    height = viewport[3];
    if (width <= 0 || height <= 0 || width > 16384 || height > 16384) {
        error = "viewport is empty; no frame to read";
        return false;
    }

    std::vector<unsigned char> pixels(static_cast<std::size_t>(width) * height * 3);
    if (g_gl.get_error != nullptr) g_gl.get_error();   // clear anything stale
    g_gl.read_buffer(kGlFront);
    g_gl.pixel_storei(kGlPackAlignment, 1);
    g_gl.read_pixels(0, 0, width, height, kGlRgb, kGlUnsignedByte, pixels.data());
    if (g_gl.get_error != nullptr) {
        const unsigned e = g_gl.get_error();
        if (e != 0) {
            char buf[64];
            std::snprintf(buf, sizeof buf, "glReadPixels failed: GL error 0x%x", e);
            error = buf;
            return false;
        }
    }

    std::FILE* f = std::fopen(path.c_str(), "wb");
    if (f == nullptr) { error = "cannot open " + path + " for writing"; return false; }
    // Every write is checked. A full disk used to be reported as a successful
    // screenshot, and the driver then compared a truncated file; the partial
    // file is removed so nothing downstream reads half a frame.
    bool wrote = std::fprintf(f, "P6\n%d %d\n255\n", width, height) > 0;
    // GL rows run bottom-up; PPM runs top-down.
    const std::size_t stride = static_cast<std::size_t>(width) * 3;
    for (int y = height - 1; wrote && y >= 0; --y)
        wrote = std::fwrite(pixels.data() + static_cast<std::size_t>(y) * stride, 1, stride, f) == stride;
    if (std::fclose(f) != 0) wrote = false;
    if (!wrote) {
        std::remove(path.c_str());
        error = "cannot write " + path + " (disk full or path not writable)";
        return false;
    }
    return true;
}

// ------------------------------------------------------------- commands -----

void cmd_ping(const Json&, Outcome& out) {
    Runtime& rt = Runtime::instance();
    out.result.set("pong", Json::boolean(true));
    out.result.set("tick", Json::unsigned_(server_tick()));
    out.result.set("build", Json::string(rt.build()));
    out.result.set("phase", Json::string(runtime::to_string(rt.phase())));
    out.result.set("live", Json::boolean(runtime::live()));
}

void cmd_status(const Json&, Outcome& out) {
    Runtime& rt = Runtime::instance();
    Json& r = out.result;
    r.set("version", Json::string(KP_VERSION));
    r.set("build", Json::string(rt.build()));
    r.set("game", Json::string(rt.table() != nullptr ? rt.table()->game() : std::string()));
    r.set("phase", Json::string(runtime::to_string(rt.phase())));
    if (!rt.failure().empty()) r.set("failure", Json::string(rt.failure()));
    r.set("live", Json::boolean(runtime::live()));
    r.set("vm_bound", Json::boolean(runtime::vm_bound()));

    Json poisoned = Json::array();
    for (const std::string& s : runtime::poisoned_sites()) poisoned.push(Json::string(s));
    r.set("poisoned", std::move(poisoned));

    r.set("hooks", Json::unsigned_(rt.hooks() != nullptr ? rt.hooks()->installed_count() : 0));
    r.set("client_tick", Json::unsigned_(client_tick()));
    r.set("server_tick", Json::unsigned_(server_tick()));
#if defined(_WIN32)
    r.set("pid", Json::unsigned_(GetCurrentProcessId()));
#else
    r.set("pid", Json::unsigned_(static_cast<std::uint64_t>(::getpid())));
#endif
    r.set("uptime_ms", Json::unsigned_(uptime_ms()));

    lua::Host* h = runtime::active_host();
    r.set("scripts", Json::unsigned_(h != nullptr ? h->scripts().size() : 0));
    r.set("adapter", Json::string(g_adapter ? g_adapter->name() : ""));
    Json missing = Json::array();
    if (g_adapter) {
        for (const std::string& s : g_adapter->missing_sites()) missing.push(Json::string(s));
    }
    r.set("missing_sites", std::move(missing));
    r.set("events_seq", Json::unsigned_(ring().last_seq()));
}

Json phase_detail_json(const PhaseDetail& d) {
    Json j = Json::object();
    j.set("server_mode", Json::integer(d.server_mode));
    j.set("loading_module", Json::integer(d.loading_module));
    j.set("area_not_ready", Json::integer(d.area_not_ready));
    j.set("input_class", Json::integer(d.input_class));
    j.set("main_menu", Json::integer(d.main_menu));
    j.set("game_over", Json::integer(d.game_over));
    j.set("pause", Json::integer(d.pause));
    j.set("controller_pause", Json::integer(d.controller_pause));
    j.set("tutorial", Json::integer(d.tutorial));
    j.set("modal_count", Json::integer(d.modal_count));
    j.set("status_summary", Json::integer(d.status_summary));
    j.set("movie", Json::integer(d.movie));
    j.set("load_error", Json::integer(d.load_error));
    j.set("move_pending", Json::integer(d.move_pending));
    j.set("timers_paused", Json::integer(d.timers_paused));
    j.set("chargen", Json::integer(d.chargen));
    return j;
}

Json dialog_json(const DialogState& ds) {
    Json j = Json::object();
    j.set("active", Json::boolean(ds.active));
    j.set("entry", Json::integer(ds.current_entry));
    j.set("reply", Json::integer(ds.current_reply));
    j.set("waiting_for_player", Json::boolean(ds.waiting_for_player));
    j.set("waiting_on_sound", Json::boolean(ds.waiting_on_sound));
    j.set("text", Json::string(ds.entry_text));
    Json replies = Json::array();
    for (const DialogReply& r : ds.replies) {
        Json e = Json::object();
        e.set("index", Json::integer(r.visible_index));
        e.set("link", Json::integer(r.link_index));
        e.set("text", Json::string(r.text));
        e.set("active", Json::boolean(r.active));
        replies.push(std::move(e));
    }
    j.set("replies", std::move(replies));
    return j;
}

struct HashingGlobals final : GlobalsVisitor {
    Fnv      fnv;
    unsigned count = 0;
    void on_bool(const char* name, bool v) override { fnv.add(name); fnv.add_int(v ? 1 : 0); ++count; }
    void on_number(const char* name, int v) override { fnv.add(name); fnv.add_int(v); ++count; }
    void on_string(const char* name, const char* v) override { fnv.add(name); fnv.add(v); ++count; }
};

struct HashingJournal final : JournalVisitor {
    Fnv      fnv;
    unsigned count = 0;
    void on_entry(const char* tag, int state) override { fnv.add(tag); fnv.add_int(state); ++count; }
};

// The routine bridge is Lua-facing, so `pc` and `party` come from a fixed
// chunk in the harness state. Null until the VM is bound; a chunk error is
// reported in `pc_error` rather than failing the whole snapshot.
const char kPcChunk[] =
    "local pc = nwscript.call('GetFirstPC')\n"
    "if pc == nil or pc == 0x7F000000 then return nil, nil end\n"
    "local pos = nwscript.call('GetPosition',pc)\n"
    "local me = { id = pc, x = pos.x, y = pos.y, z = pos.z,\n"
    "             hp = nwscript.call('GetCurrentHitPoints',pc), max_hp = nwscript.call('GetMaxHitPoints',pc) }\n"
    "local party = {}\n"
    "local n = nwscript.call('GetPartyMemberCount')\n"
    "for i = 0, n - 1 do\n"
    "  local m = nwscript.call('GetPartyMemberByIndex',i)\n"
    "  party[#party + 1] = { id = m, tag = nwscript.call('GetTag',m) }\n"
    "end\n"
    "return me, party\n";

void cmd_state(const Json&, Outcome& out) {
    Json& r = out.result;

    if (g_adapter) {
        PhaseDetail detail;
        const Phase p = engine([&] { return g_adapter->phase(&detail); });
        r.set("phase", Json::string(phase_name(p)));
        r.set("phase_detail", phase_detail_json(detail));
        r.set("chargen_stage", Json::string(engine([&] { return g_adapter->chargen_stage(); })));
        r.set("module", Json::string(engine([&] { return g_adapter->module_name(); })));
    } else {
        r.set("phase", Json::string("unknown"));
        r.set("phase_detail", Json::null());
        r.set("chargen_stage", Json::string("none"));
        r.set("module", Json::string(""));
    }
    r.set("server_tick", Json::unsigned_(server_tick()));
    r.set("client_tick", Json::unsigned_(client_tick()));

    Json pc = Json::null();
    Json party = Json::null();
    if (runtime::vm_bound()) {
        Json values;
        std::string output, error;
        bool ran = false;
        KP_HOOK_GUARD_BEGIN("harness.state", g_poison, { ran = false; })
        ran = run_lua(kPcChunk, "=harness.state", values, output, error);
        KP_HOOK_GUARD_END
        if (ran && values.is_array() && values.size() >= 1) {
            pc = values.elements()[0];
            if (values.size() >= 2) party = values.elements()[1];
        } else if (!ran) {
            r.set("pc_error", Json::string(error.empty() ? "fault while reading pc" : error));
        }
    }
    r.set("pc", std::move(pc));
    r.set("party", std::move(party));

    Json dialog = Json::null();
    if (g_adapter) {
        DialogState ds;
        const Result dr = engine([&] { return g_adapter->dialog(&ds); });
        if (dr.ok && ds.active) dialog = dialog_json(ds);
    }
    r.set("dialog", std::move(dialog));

    HashingGlobals globals;
    HashingJournal journal;
    Json counts = Json::object();
    if (g_adapter) {
        const Result gr = engine([&] { return g_adapter->walk_globals(globals); });
        const Result jr = engine([&] { return g_adapter->walk_journal(journal); });
        r.set("globals_hash", gr.ok ? Json::string(globals.fnv.hex()) : Json::null());
        r.set("journal_hash", jr.ok ? Json::string(journal.fnv.hex()) : Json::null());
        counts.set("globals", Json::unsigned_(globals.count));
        counts.set("journal", Json::unsigned_(journal.count));
    } else {
        r.set("globals_hash", Json::null());
        r.set("journal_hash", Json::null());
    }
    r.set("counts", std::move(counts));

    r.set("live", Json::boolean(runtime::live()));
    Json poisoned = Json::array();
    for (const std::string& s : runtime::poisoned_sites()) poisoned.push(Json::string(s));
    r.set("poisoned", std::move(poisoned));
}

Json record_json(const EventRecord& rec) {
    Json j = Json::object();
    j.set("event", Json::string(rec.name));
    j.set("tick", Json::unsigned_(rec.server_tick));
    j.set("seq", Json::unsigned_(rec.seq));
    for (std::size_t i = 0; i < rec.field_count(); ++i) {
        const EventField& f = rec.fields[i];
        switch (f.kind) {
        case EventField::Kind::Int:  j.set(f.key, Json::integer(f.i)); break;
        case EventField::Kind::Uint: j.set(f.key, Json::unsigned_(static_cast<std::uint64_t>(f.i))); break;
        case EventField::Kind::Text: j.set(f.key, Json::string(f.text)); break;
        case EventField::Kind::None: break;
        }
    }
    return j;
}

void cmd_events(const Json& req, Outcome& out) {
    const Json* since = req.get("since");
    const Json* limit = req.get("limit");
    std::uint64_t from = 0;
    if (since != nullptr && !as_uint_arg(*since, from)) from = 0;
    std::uint64_t want = 0;
    std::size_t max = (limit != nullptr && as_uint_arg(*limit, want) && want > 0)
                          ? static_cast<std::size_t>(want > EventRing::kCapacity
                                                         ? EventRing::kCapacity : want)
                          : 256;
    if (max > EventRing::kCapacity) max = EventRing::kCapacity;

    std::vector<EventRecord> records;
    ring().read_since(from, max, records);
    Json items = Json::array();
    for (const EventRecord& rec : records) items.push(record_json(rec));
    out.result.set("seq", Json::unsigned_(ring().last_seq()));
    out.result.set("oldest", Json::unsigned_(ring().oldest_seq()));
    out.result.set("items", std::move(items));
}

void cmd_subscribe(const Json& req, Outcome& out, std::uint64_t client) {
    const Json* since = req.get("since");
    std::uint64_t cursor = 0;
    g_stream_cursor = (since != nullptr && as_uint_arg(*since, cursor)) ? cursor : ring().last_seq();
    g_stream_client = client;
    if (Channel* ch = channel(); ch != nullptr) ch->set_subscribed(true);
    out.result.set("subscribed", Json::boolean(true));
    out.result.set("seq", Json::unsigned_(g_stream_cursor));
}

void cmd_unsubscribe(const Json&, Outcome& out) {
    if (Channel* ch = channel(); ch != nullptr) ch->set_subscribed(false);
    g_stream_client = 0;
    out.result.set("subscribed", Json::boolean(false));
}

void cmd_devtools(const Json& req, Outcome& out) {
    if (req.has("protocol")) {
        std::string error;
        if (!console_protocol::dispatch(kp::devtools::console(), req,
                console_protocol::runtime_instance(), kp::devtools::overlay_open(),
                kp::devtools::overlay_input_calls(), out.result, error)) fail(out, error);
        return;
    }
    auto* operation=req.get("op");std::string op=operation?operation->as_string():"status";
    auto& c=kp::devtools::console();Json result=Json::object();
    if(op=="submit") {auto* code=req.get("code");if(!code || !code->is_string()){fail(out,"code must be a string");return;}auto id=c.submit(code->as_string());if(!id){fail(out,"console queue full or command too long");return;}result.set("request",Json::unsigned_(id));}
    else if(op=="output") {Json lines=Json::array();for(auto& l:c.snapshot()){Json row=Json::object();row.set("request",Json::unsigned_(l.request));row.set("kind",Json::string(l.kind));row.set("text",Json::string(l.text));lines.push(std::move(row));}result.set("lines",std::move(lines));}
    else if(op=="complete") {auto* p=req.get("prefix");Json names=Json::array();for(auto& n:c.complete(p?p->as_string():""))names.push(Json::string(n));result.set("names",std::move(names));}
    else if(op=="cancel") c.cancel();
    else if(op!="status"){fail(out,"unknown devtools operation");return;}
    auto status=c.status();result.set("submitted",Json::unsigned_(status.submitted));result.set("completed",Json::unsigned_(status.completed));result.set("running",Json::boolean(status.running));result.set("queued",Json::unsigned_(status.queued));result.set("open",Json::boolean(kp::devtools::overlay_open()));
    result.set("input_calls",Json::unsigned_(kp::devtools::overlay_input_calls()));
    out.result=std::move(result);
}

void cmd_lua(const Json& req, Outcome& out) {
    const Json* code = req.get("code");
    if (code == nullptr || !code->is_string()) { fail(out, "lua: `code` (string) is required"); return; }

    Json values;
    std::string output, error;
    bool ran = false;
    bool faulted = true;
    KP_HOOK_GUARD_BEGIN("harness.lua", g_poison, { ran = false; faulted = true; })
    ran = run_lua(code->as_string(), "=harness", values, output, error);
    faulted = false;
    KP_HOOK_GUARD_END

    if (faulted) { fail(out, "fault while running lua; harness site poisoned"); return; }
    if (!ran) {
        // The routine bridge answers with its own message when nwscript.call is
        // called before the VM is captured; pass it through, it says why.
        fail(out, error);
        if (!output.empty()) out.result.set("output", Json::string(output));
        return;
    }
    out.result.set("values", std::move(values));
    if (!output.empty()) out.result.set("output", Json::string(output));
}

void cmd_reload(const Json&, Outcome& out) {
    lua::Host* h = runtime::active_host();
    if (h == nullptr) { fail(out, "no lua host"); return; }

    unsigned loaded = 0;
    Json errors = Json::array();
    bool faulted = true;
    KP_HOOK_GUARD_BEGIN("harness.reload", g_poison, { faulted = true; })
    {
        std::vector<std::string> errs;
        loaded = h->load_all(errs);
        for (const std::string& e : errs) errors.push(Json::string(e));
        close_harness_state();
        faulted = false;
    }
    KP_HOOK_GUARD_END
    if (faulted) { fail(out, "fault while reloading; harness site poisoned"); return; }

    // The one path that brings scripting back after a fault, the same as the
    // console's `lua reload`: every state was rebuilt, so re-arming is sound.
    const bool rearmed = !runtime::live();
    runtime::set_live(true);
    if (rearmed) Runtime::instance().log("harness reload: scripting re-armed after a fault");

    out.result.set("loaded", Json::unsigned_(loaded));
    out.result.set("errors", std::move(errors));
    out.result.set("rearmed", Json::boolean(rearmed));
    Json poisoned = Json::array();
    for (const std::string& s : runtime::poisoned_sites()) poisoned.push(Json::string(s));
    out.result.set("poisoned", std::move(poisoned));
}

void cmd_load_save(const Json& req, Outcome& out) {
    if (!need_adapter(out)) return;
    const Json* dir = req.get("dir");
    if (dir == nullptr || !dir->is_string()) { fail(out, "load_save: `dir` (string) is required"); return; }
    from_result(out, engine([&] { return g_adapter->load_save(dir->as_string()); }));
    out.result.set("dir", *dir);
}

void cmd_new_game(const Json&, Outcome& out) {
    if (!need_adapter(out)) return;
    from_result(out, engine([&] { return g_adapter->new_game(); }));
}

void cmd_chargen_select_class(const Json& req, Outcome& out) {
    if (!need_adapter(out)) return;
    const Json* index = req.get("index");
    int i = 0;
    if (index == nullptr || !as_int_arg(*index, i) || i < 0 || i > 5) {
        fail(out, "chargen_select_class: `index` must be a number from 0 through 5");
        return;
    }
    from_result(out, engine([&] { return g_adapter->chargen_select_class(i); }));
    out.result.set("index", Json::integer(i));
}

void cmd_chargen_begin_play(const Json&, Outcome& out) {
    if (!need_adapter(out)) return;
    from_result(out, engine([&] { return g_adapter->chargen_begin_play(); }));
}

void cmd_save(const Json& req, Outcome& out) {
    if (!need_adapter(out)) return;
    const Json* slot = req.get("slot");
    const Json* name = req.get("name");
    int s = 0;
    if (slot == nullptr || !as_int_arg(*slot, s)) {
        fail(out, "save: `slot` (number, within int range) is required");
        return;
    }
    const std::string n = name != nullptr ? name->as_string() : std::string("harness");
    from_result(out, engine([&] { return g_adapter->save(s, n); }));
    out.result.set("slot", Json::integer(s));
    out.result.set("name", Json::string(n));
}

void cmd_warp(const Json& req, Outcome& out) {
    if (!need_adapter(out)) return;
    const Json* module = req.get("module");
    if (module == nullptr || !module->is_string()) { fail(out, "warp: `module` (string) is required"); return; }
    from_result(out, engine([&] { return g_adapter->warp(module->as_string()); }));
    out.result.set("module", *module);
}

void cmd_dialog(const Json&, Outcome& out) {
    if (!need_adapter(out)) return;
    DialogState ds;
    const Result r = engine([&] { return g_adapter->dialog(&ds); });
    from_result(out, r);
    if (r.ok) out.result = dialog_json(ds);
}

void cmd_reply(const Json& req, Outcome& out) {
    if (!need_adapter(out)) return;
    const Json* index = req.get("index");
    int i = 0;
    if (index == nullptr || !as_int_arg(*index, i)) {
        fail(out, "reply: `index` (number, within int range) is required");
        return;
    }
    from_result(out, engine([&] { return g_adapter->reply(i); }));
    out.result.set("index", Json::integer(i));
}

void cmd_dialog_continue(const Json&, Outcome& out) {
    if (!need_adapter(out)) return;
    from_result(out, engine([&] { return g_adapter->dialog_continue(); }));
}

void cmd_dialog_skip(const Json&, Outcome& out) {
    if (!need_adapter(out)) return;
    from_result(out, engine([&] { return g_adapter->dialog_skip(); }));
}

void cmd_dialog_abort(const Json&, Outcome& out) {
    if (!need_adapter(out)) return;
    from_result(out, engine([&] { return g_adapter->dialog_abort(); }));
}

void cmd_dialog_clear_sound_wait(const Json&, Outcome& out) {
    if (!need_adapter(out)) return;
    from_result(out, engine([&] { return g_adapter->dialog_clear_sound_wait(); }));
}

void cmd_clear_auto_pause(const Json&, Outcome& out) {
    if (!need_adapter(out)) return;
    from_result(out, engine([&] { return g_adapter->clear_auto_pause(); }));
}

void cmd_speed(const Json& req, Outcome& out) {
    if (!need_adapter(out)) return;
    const Json* scale = req.get("scale");
    if (scale == nullptr || !scale->is_number()) { fail(out, "speed: `scale` (number) is required"); return; }
    double s = scale->as_number();
    // (0, 16]: below 1 is slow motion through the same SetGameSpeed path the
    // engine scales its five timers with; the adapter rejects 0 and negatives.
    if (s > 16.0) s = 16.0;
    from_result(out, engine([&] { return g_adapter->set_speed(static_cast<float>(s)); }));
    out.result.set("scale", Json::number(s));
}

// Unpause the world timers load_save paused. The engine's load-completion
// block does it itself on the path it owns; this is the route for a load that
// reached gameplay some other way, and it exists so no test has to write a
// timer's paused byte by hand -- one that did wedged the control channel while
// the process stayed alive.
void cmd_unpause_timers(const Json&, Outcome& out) {
    if (!need_adapter(out)) return;
    from_result(out, engine([&] { return g_adapter->unpause_timers(); }));
}

void cmd_advance_tutorial(const Json&, Outcome& out) {
    if (!need_adapter(out)) return;
    from_result(out, engine([&] { return g_adapter->advance_tutorial(); }));
}

void cmd_finish_hidden_tutorial(const Json&, Outcome& out) {
    if (!need_adapter(out)) return;
    from_result(out, engine([&] { return g_adapter->finish_hidden_tutorial(); }));
}

void cmd_dismiss_status_summary(const Json&, Outcome& out) {
    if (!need_adapter(out)) return;
    from_result(out, engine([&] { return g_adapter->dismiss_status_summary(); }));
}

void cmd_dismiss_messagebox(const Json&, Outcome& out) {
    if (!need_adapter(out)) return;
    from_result(out, engine([&] { return g_adapter->dismiss_messagebox(); }));
}

void cmd_equipment_screen(const Json& req, Outcome& out) {
    if (!need_adapter(out)) return;
    const Json* visible = req.get("visible");
    if (visible == nullptr || !visible->is_bool()) {
        fail(out, "equipment_screen: `visible` (boolean) is required");
        return;
    }
    from_result(out, engine([&] { return g_adapter->equipment_screen(visible->as_bool()); }));
}

void cmd_door_use(const Json& req, Outcome& out) {
    if (!need_adapter(out)) return;
    const Json* door = req.get("door");
    std::uint64_t door_id = 0;
    if (door == nullptr || !as_uint_arg(*door, door_id) || door_id > 0xffffffffu ||
        door->as_number() != static_cast<double>(door_id)) {
        fail(out, "door_use: `door` must be an exact unsigned 32-bit object id");
        return;
    }
    const Result r = engine([&] { return g_adapter->door_use(static_cast<std::uint32_t>(door_id)); });
    from_result(out, r);
    if (r.ok) {
        out.result.set("door", Json::unsigned_(door_id));
        out.result.set("dispatched", Json::boolean(true));
    }
}

void cmd_door_commit_open(const Json& req, Outcome& out) {
    if (!need_adapter(out)) return;
    const Json* door = req.get("door");
    std::uint64_t door_id = 0;
    if (door == nullptr || !as_uint_arg(*door, door_id) || door_id > 0xffffffffu ||
        door->as_number() != static_cast<double>(door_id)) {
        fail(out, "door_commit_open: `door` must be an exact unsigned 32-bit object id");
        return;
    }
    const Result r = engine([&] { return g_adapter->door_commit_open(static_cast<std::uint32_t>(door_id)); });
    from_result(out, r);
    if (r.ok) {
        out.result.set("door", Json::unsigned_(door_id));
        out.result.set("committed", Json::boolean(true));
    }
}

void cmd_door_security(const Json& req, Outcome& out, std::uint64_t client) {
    if (!need_adapter(out)) return;
    if (g_door_security.active) { fail(out, "door_security: one transaction is already pending"); return; }
    const Json* door = req.get("door");
    std::uint64_t door_id = 0;
    if (door == nullptr || !as_uint_arg(*door, door_id) || door_id > 0xffffffffu ||
        door->as_number() != static_cast<double>(door_id)) {
        fail(out, "door_security: `door` must be an exact unsigned 32-bit object id");
        return;
    }
    const Result r = engine([&] { return g_adapter->door_security(static_cast<std::uint32_t>(door_id)); });
    from_result(out, r);
    if (!r.ok) return;
    g_door_security.active = true;
    g_door_security.client = client;
    g_door_security.id = id_of(req);
    out.deferred = true;
}

void cmd_attack(const Json& req, Outcome& out) {
    if (!need_adapter(out)) return;
    const Json* target = req.get("target");
    std::uint64_t target_id = 0;
    if (target == nullptr || !as_uint_arg(*target, target_id) || target_id > 0xffffffffu ||
        target->as_number() != static_cast<double>(target_id)) {
        fail(out, "attack: `target` must be an exact unsigned 32-bit object id");
        return;
    }
    const Result r = engine([&] { return g_adapter->attack(static_cast<std::uint32_t>(target_id)); });
    from_result(out, r);
    if (r.ok) {
        out.result.set("target", Json::unsigned_(target_id));
        out.result.set("dispatched", Json::boolean(true));
    }
}

void cmd_dismiss_container(const Json&, Outcome& out) {
    if (!need_adapter(out)) return;
    from_result(out, engine([&] { return g_adapter->dismiss_container(); }));
}

void cmd_take_all_container(const Json&, Outcome& out) {
    if (!need_adapter(out)) return;
    from_result(out, engine([&] { return g_adapter->take_all_container(); }));
}

void cmd_accept_party_selection(const Json&, Outcome& out) {
    if (!need_adapter(out)) return;
    from_result(out, engine([&] { return g_adapter->accept_party_selection(); }));
}

void cmd_auto_levelup(const Json& req, Outcome& out, std::uint64_t client) {
    if (!need_adapter(out)) return;
    if (g_auto_level.active) { fail(out, "auto_levelup: one transaction is already pending"); return; }
    const Result r = engine([&] { return g_adapter->auto_levelup(); });
    from_result(out, r);
    if (!r.ok) return;
    g_auto_level.active = true;
    g_auto_level.client = client;
    g_auto_level.id = id_of(req);
    out.deferred = true;
}

void cmd_set_party_leader(const Json& req, Outcome& out, std::uint64_t client) {
    if (!need_adapter(out)) return;
    if (g_party_leader.active) {
        fail(out, "set_party_leader: one transaction is already pending");
        return;
    }
    const Json* index = req.get("index");
    int selector = 0;
    if (index == nullptr || !as_int_arg(*index, selector)) {
        fail(out, "set_party_leader: non-negative `index` is required");
        return;
    }
    const Result r = engine([&] { return g_adapter->set_party_leader(selector); });
    from_result(out, r);
    if (!r.ok) return;
    g_party_leader.active = true;
    g_party_leader.client = client;
    g_party_leader.id = id_of(req);
    out.deferred = true;
}

void cmd_use_item(const Json& req, Outcome& out, std::uint64_t client) {
    if (!need_adapter(out)) return;
    if (g_use_item.active) { fail(out, "use_item: one transaction is already pending"); return; }
    const Json* item = req.get("item");
    std::uint64_t item_id = 0;
    if (item == nullptr || !as_uint_arg(*item, item_id) || item_id > 0xffffffffu) {
        fail(out, "use_item: unsigned 32-bit `item` object id is required");
        return;
    }
    std::uint64_t target_id = 0;
    if (const Json* target = req.get("target"); target != nullptr &&
        (!as_uint_arg(*target, target_id) || target_id > 0xffffffffu)) {
        fail(out, "use_item: `target` must be an unsigned 32-bit object id");
        return;
    }
    const Result r = engine([&] { return g_adapter->use_item(static_cast<std::uint32_t>(item_id),
                                                              static_cast<std::uint32_t>(target_id)); });
    from_result(out, r);
    if (!r.ok) return;
    g_use_item.active = true;
    g_use_item.client = client;
    g_use_item.id = id_of(req);
    out.deferred = true;
}

void cmd_equip_item(const Json& req, Outcome& out, std::uint64_t client) {
    if (!need_adapter(out)) return;
    if (g_equip_item.active) { fail(out, "equip_item: one transaction is already pending"); return; }
    std::uint64_t item_id = 0, slot = 0;
    const Json* item = req.get("item");
    const Json* requested_slot = req.get("slot");
    if (item == nullptr || !as_uint_arg(*item, item_id) || item_id > 0xffffffffu) {
        fail(out, "equip_item: unsigned 32-bit `item` object id is required");
        return;
    }
    if (requested_slot == nullptr || !as_uint_arg(*requested_slot, slot) || slot > 0xffffffffu) {
        fail(out, "equip_item: unsigned 32-bit `slot` index is required");
        return;
    }
    bool instant = true;
    if (const Json* value = req.get("instant"); value != nullptr) {
        if (!value->is_bool()) { fail(out, "equip_item: `instant` must be boolean"); return; }
        instant = value->as_bool();
    }
    const Result r = engine([&] { return g_adapter->equip_item(static_cast<std::uint32_t>(item_id),
                                                                static_cast<std::uint32_t>(slot), instant); });
    from_result(out, r);
    if (!r.ok) return;
    g_equip_item.active = true;
    g_equip_item.client = client;
    g_equip_item.id = id_of(req);
    out.deferred = true;
}

void cmd_fixed_step(const Json& req, Outcome& out) {
    if (!need_adapter(out)) return;
    const Json* hz = req.get("hz");
    int rate = 0;
    if (hz == nullptr || !as_int_arg(*hz, rate)) {
        fail(out, "fixed_step: `hz` (number, 0 to leave) is required");
        return;
    }
    if (rate < 0) rate = 0;
    from_result(out, engine([&] { return g_adapter->set_fixed_step(rate); }));
    out.result.set("hz", Json::integer(rate));
}

void cmd_movies(const Json& req, Outcome& out) {
    if (!need_adapter(out)) return;
    const Json* enabled = req.get("enabled");
    if (enabled == nullptr || !enabled->is_bool()) { fail(out, "movies: `enabled` (boolean) is required"); return; }
    const bool on = enabled->as_bool();
    from_result(out, engine([&] { return g_adapter->set_movies(on); }));
    out.result.set("enabled", Json::boolean(engine([&] { return g_adapter->movies_enabled(); })));
}

void cmd_screenshot(const Json& req, Outcome& out, std::uint64_t client) {
    const Json* path = req.get("path");
    if (path == nullptr || !path->is_string() || path->as_string().empty()) {
        fail(out, "screenshot: `path` (string) is required");
        return;
    }
    if (g_shot.active) { fail(out, "screenshot: one is already pending this frame"); return; }
    g_shot.active = true;
    g_shot.lua_request = false;
    g_shot.client = client;
    g_shot.id = id_of(req);
    g_shot.path = path->as_string();
    out.deferred = true;
}

void cmd_globals(const Json&, Outcome& out) {
    if (!need_adapter(out)) return;
    struct Collect final : GlobalsVisitor {
        Json bools = Json::object();
        Json numbers = Json::object();
        Json strings = Json::object();
        void on_bool(const char* name, bool v) override { bools.set(name, Json::boolean(v)); }
        void on_number(const char* name, int v) override { numbers.set(name, Json::integer(v)); }
        void on_string(const char* name, const char* v) override {
            strings.set(name, Json::string(v != nullptr ? v : ""));
        }
    } collect;
    const Result r = engine([&] { return g_adapter->walk_globals(collect); });
    from_result(out, r);
    if (!r.ok) return;
    out.result.set("bools", std::move(collect.bools));
    out.result.set("numbers", std::move(collect.numbers));
    out.result.set("strings", std::move(collect.strings));
}

void cmd_journal(const Json&, Outcome& out) {
    if (!need_adapter(out)) return;
    struct Collect final : JournalVisitor {
        Json entries = Json::array();
        void on_entry(const char* tag, int state) override {
            Json e = Json::object();
            e.set("tag", Json::string(tag != nullptr ? tag : ""));
            e.set("state", Json::integer(state));
            entries.push(std::move(e));
        }
    } collect;
    const Result r = engine([&] { return g_adapter->walk_journal(collect); });
    from_result(out, r);
    if (!r.ok) return;
    out.result.set("entries", std::move(collect.entries));
}

void cmd_quit(const Json&, Outcome& out) {
    g_quit.store(true, std::memory_order_release);
    out.result.set("quitting", Json::boolean(true));
}

void dispatch(const std::string& cmd, const Json& req, Outcome& out, std::uint64_t client) {
    if (cmd == "ping")              cmd_ping(req, out);
    else if (cmd == "status")       cmd_status(req, out);
    else if (cmd == "state")        cmd_state(req, out);
    else if (cmd == "events")       cmd_events(req, out);
    else if (cmd == "subscribe")    cmd_subscribe(req, out, client);
    else if (cmd == "unsubscribe")  cmd_unsubscribe(req, out);
    else if (cmd == "devtools")     cmd_devtools(req, out);
    else if (cmd == "lua")          cmd_lua(req, out);
    else if (cmd == "reload")       cmd_reload(req, out);
    else if (cmd == "load_save")    cmd_load_save(req, out);
    else if (cmd == "new_game")     cmd_new_game(req, out);
    else if (cmd == "chargen_select_class") cmd_chargen_select_class(req, out);
    else if (cmd == "chargen_begin_play") cmd_chargen_begin_play(req, out);
    else if (cmd == "save")         cmd_save(req, out);
    else if (cmd == "warp")         cmd_warp(req, out);
    else if (cmd == "dialog")       cmd_dialog(req, out);
    else if (cmd == "reply")        cmd_reply(req, out);
    else if (cmd == "dialog_continue") cmd_dialog_continue(req, out);
    else if (cmd == "dialog_skip")  cmd_dialog_skip(req, out);
    else if (cmd == "dialog_abort") cmd_dialog_abort(req, out);
    else if (cmd == "dialog_clear_sound_wait") cmd_dialog_clear_sound_wait(req, out);
    else if (cmd == "clear_auto_pause") cmd_clear_auto_pause(req, out);
    else if (cmd == "speed")        cmd_speed(req, out);
    else if (cmd == "fixed_step")   cmd_fixed_step(req, out);
    else if (cmd == "unpause_timers") cmd_unpause_timers(req, out);
    else if (cmd == "advance_tutorial") cmd_advance_tutorial(req, out);
    else if (cmd == "finish_hidden_tutorial") cmd_finish_hidden_tutorial(req, out);
    else if (cmd == "dismiss_status_summary") cmd_dismiss_status_summary(req, out);
    else if (cmd == "dismiss_messagebox") cmd_dismiss_messagebox(req, out);
    else if (cmd == "equipment_screen") cmd_equipment_screen(req, out);
    else if (cmd == "door_use") cmd_door_use(req, out);
    else if (cmd == "door_commit_open") cmd_door_commit_open(req, out);
    else if (cmd == "door_security") cmd_door_security(req, out, client);
    else if (cmd == "attack") cmd_attack(req, out);
    else if (cmd == "dismiss_container") cmd_dismiss_container(req, out);
    else if (cmd == "take_all_container") cmd_take_all_container(req, out);
    else if (cmd == "accept_party_selection") cmd_accept_party_selection(req, out);
    else if (cmd == "auto_levelup") cmd_auto_levelup(req, out, client);
    else if (cmd == "set_party_leader") cmd_set_party_leader(req, out, client);
    else if (cmd == "use_item")      cmd_use_item(req, out, client);
    else if (cmd == "equip_item")    cmd_equip_item(req, out, client);
    else if (cmd == "movies")       cmd_movies(req, out);
    else if (cmd == "screenshot")   cmd_screenshot(req, out, client);
    else if (cmd == "globals")      cmd_globals(req, out);
    else if (cmd == "journal")      cmd_journal(req, out);
    else if (cmd == "quit")         cmd_quit(req, out);
    else fail(out, "unknown command: " + cmd);
}

// One raw line to one reply line. Empty when the reply is deferred.
//
// Parse and serialise are the two guarded regions. A local written inside a
// guarded region is indeterminate after a claimed fault, so each fallback
// re-states the flag that the code after it reads.
//
// `condemn` comes back true when the line is not a JSON object: an HTTP
// request line, a header, garbage. That line gets its error reply and the
// connection is done; see Channel::condemn.
std::string execute_line(const std::string& raw, std::uint64_t client, bool& condemn) {
    const LineShape shape = screen_request_line(raw);
    condemn = shape != LineShape::Ok;
    Json req;
    std::string parse_error;
    bool parsed = false;
    // parse_error is written inside the guarded region, so after a claimed
    // fault its contents are indeterminate -- reading it, or even clearing it,
    // is not sound. `have_error` is the fallback's own flag: it says whether
    // the string is a message the parser wrote or memory nobody owns.
    bool have_error = false;
    KP_HOOK_GUARD_BEGIN("harness.drain", g_poison, { parsed = false; have_error = false; })
    parsed = Json::parse(raw, req, parse_error);
    have_error = true;
    KP_HOOK_GUARD_END

    Json id = Json::null();
    Json reply;
    if (condemn) {
        reply = err_reply(id, shape == LineShape::Http
                                  ? std::string("HTTP is not spoken here; connection closed")
                                  : std::string("request must be a JSON object; connection closed"));
    } else if (!parsed) {
        condemn = true;
        reply = err_reply(id, (!have_error || parse_error.empty())
                                  ? std::string("fault while parsing; harness site poisoned")
                                  : parse_error);
    } else if (!req.is_object()) {
        condemn = true;
        reply = err_reply(id, "request must be a JSON object");
    } else {
        id = id_of(req);
        const Json* cmd = req.get("cmd");
        if (cmd == nullptr || !cmd->is_string()) {
            reply = err_reply(id, "request needs a string `cmd`");
        } else {
            Outcome out;
            dispatch(cmd->as_string(), req, out, client);
            if (out.deferred) return std::string();
            reply = out.ok ? ok_reply(id, std::move(out.result)) : err_reply(id, std::move(out.error));
        }
    }

    std::string line;
    bool dumped = false;
    KP_HOOK_GUARD_BEGIN("harness.drain", g_poison, { dumped = false; })
    line = reply.dump();
    dumped = true;
    KP_HOOK_GUARD_END
    if (!dumped) {
        const std::string fallback = err_reply(id, "fault while serialising; harness site poisoned").dump();
        return fallback;
    }
    return line;
}

// After `subscribe`, every new ring record goes out as a frame. Bounded per
// frame so a burst of scripts cannot turn one client frame into a flood.
constexpr std::size_t kStreamPerTick = 256;

void stream_events(Channel& ch) {
    if (!ch.subscribed()) return;
    const std::uint64_t client = ch.current_client();
    if (client == 0 || client != g_stream_client) return;

    const std::uint64_t oldest = ring().oldest_seq();
    if (oldest != 0 && g_stream_cursor + 1 < oldest) {
        // The ring wrapped past the cursor: say so rather than pretend the
        // missing records never happened.
        Json gap = Json::object();
        gap.set("event", Json::string("harness.gap"));
        gap.set("tick", Json::unsigned_(server_tick()));
        gap.set("seq", Json::unsigned_(oldest));
        gap.set("dropped", Json::unsigned_(oldest - g_stream_cursor - 1));
        ch.push_reply(client, gap.dump());
        g_stream_cursor = oldest - 1;
    }

    std::vector<EventRecord> records;
    ring().read_since(g_stream_cursor, kStreamPerTick, records);
    for (const EventRecord& rec : records) {
        ch.push_reply(client, record_json(rec).dump());
        g_stream_cursor = rec.seq;
    }
}

}  // namespace

// --------------------------------------------------------------- wiring -----

bool start(const HarnessOptions& opts, std::string& error) {
    if (Channel* ch = channel(); ch != nullptr && ch->running()) { error = "harness already started"; return false; }
    auto ch = std::make_unique<Channel>();
    ChannelOptions co;
    co.bind = opts.bind;
    co.port = opts.port;
    if (!ch->start(co, error)) return false;
    g_started = std::chrono::steady_clock::now();
    g_quit.store(false, std::memory_order_release);
    g_channel = ch.release();
    g_channel_ptr.store(g_channel, std::memory_order_release);
    return true;
}

void stop() {
    if (g_channel != nullptr) {
        g_channel_ptr.store(nullptr, std::memory_order_release);
        g_channel->stop();
        delete g_channel;
        g_channel = nullptr;
    }
    close_harness_state();
    g_adapter.reset();
    g_shot = PendingShot{};
    g_auto_level = PendingAutoLevelReply{};
    g_party_leader = PendingAutoLevelReply{};
    g_use_item = PendingAutoLevelReply{};
    g_equip_item = PendingAutoLevelReply{};
    g_door_security = PendingAutoLevelReply{};
    g_stream_client = 0;
}

bool started() {
    Channel* ch = channel();
    return ch != nullptr && ch->running();
}

unsigned short listening_port() {
    Channel* ch = channel();
    return ch != nullptr ? ch->port() : 0;
}

std::uint64_t uptime_ms() {
    if (!started()) return 0;
    const auto up = std::chrono::steady_clock::now() - g_started;
    return static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::milliseconds>(up).count());
}

void set_adapter(std::unique_ptr<EngineAdapter> a) { g_adapter = std::move(a); }

EngineAdapter* adapter() { return g_adapter.get(); }

std::atomic<bool>& poison_flag() { return g_poison; }

void note_client_frame() { g_client_tick.fetch_add(1, std::memory_order_acq_rel); }

std::uint64_t client_tick() { return g_client_tick.load(std::memory_order_acquire); }

bool quit_requested() { return g_quit.load(std::memory_order_acquire); }
void request_quit() { g_quit.store(true, std::memory_order_release); }
void request_reload() { g_lua_reload_requested.store(true, std::memory_order_release); }

bool request_screenshot(const std::string& path, std::string& error) {
    if (path.empty()) { error = "screenshot: path must not be empty"; return false; }
    if (g_shot.active) { error = "screenshot: one is already pending this frame"; return false; }
    g_lua_shot_result = ScreenshotResult{};
    g_shot.active = true;
    g_shot.lua_request = true;
    g_shot.client = 0;
    g_shot.id = Json::null();
    g_shot.path = path;
    return true;
}

bool take_screenshot_result(ScreenshotResult& result) {
    if (!g_lua_shot_result.ready) return false;
    result = std::move(g_lua_shot_result);
    g_lua_shot_result = ScreenshotResult{};
    return true;
}

void stop_after_flush() {
    if (g_channel == nullptr) return;
    g_channel_ptr.store(nullptr, std::memory_order_release);
    // Half a second is far longer than a loopback write takes; the bound is
    // there so a client that stopped reading cannot hold the exit hostage.
    g_channel->wait_flushed(500);
    g_channel->stop();
    delete g_channel;
    g_channel = nullptr;
}

void drain() {
    // Trivially destructible, so this stays native TLS: the DLL is loaded
    // with LoadLibrary and the simpler the thread-local, the better.
    static thread_local bool draining = false;
    if (draining) return;
    std::unique_lock drain_lock(g_drain_mutex, std::try_to_lock);
    if (!drain_lock.owns_lock()) return;
    if (g_poison.load(std::memory_order_acquire)) return;
    if (g_lua_reload_requested.exchange(false, std::memory_order_acq_rel)) {
        Outcome reload;
        cmd_reload(Json::object(), reload);
        if (!reload.ok) Runtime::instance().log("harness Lua reload: %s", reload.error.c_str());
        else {
            Runtime::instance().log("harness Lua reload completed");
            if (const Json* errors = reload.result.get("errors"); errors != nullptr && errors->is_array()) {
                for (const Json& error : errors->elements())
                    Runtime::instance().log("harness Lua reload: %s", error.as_string().c_str());
            }
        }
    }
    Channel* ch = channel();
    if (ch == nullptr || !ch->running()) return;

    struct Draining {
        bool& flag;
        explicit Draining(bool& f) : flag(f) { flag = true; }
        ~Draining() { flag = false; }
    } scoped(draining);

    // The batch leaves the channel's queue before any guard is armed.
    std::vector<Request> batch;
    ch->take_requests(kMaxPerTick, batch);

    std::vector<std::pair<std::uint64_t, std::string>> replies;
    replies.reserve(batch.size());
    // Condemned inside this batch. Kept local until the replies are pushed:
    // the listener closes on condemn(), and the error reply has to be queued
    // before it looks.
    std::uint64_t condemned = 0;
    for (std::size_t n = 0; n < batch.size(); ++n) {
        const Request& rq = batch[n];
        // A request from a client that left, or one that already sent a line
        // that is not a request, does not run and is not answered.
        if (rq.client == condemned || !ch->admit(rq.client)) continue;
        bool condemn = false;
        std::string line = execute_line(rq.line, rq.client, condemn);
        if (!line.empty()) replies.emplace_back(rq.client, std::move(line));
        if (condemn) condemned = rq.client;
        // A fault poisons the harness; the reply for that request still goes
        // out, and the rest of the batch is answered with a refusal.
        if (g_poison.load(std::memory_order_acquire)) {
            for (std::size_t i = n + 1; i < batch.size(); ++i)
                if (batch[i].client != condemned)
                    replies.emplace_back(batch[i].client,
                                         err_reply(Json::null(), "harness site poisoned").dump());
            break;
        }
    }
    for (auto& r : replies) ch->push_reply(r.first, std::move(r.second));
    if (condemned != 0) ch->condemn(condemned);

    stream_events(*ch);
}

void after_frame() {
    if (g_adapter) {
        engine([&] { return g_adapter->after_frame(); });
    }

    if (g_auto_level.active && g_adapter) {
        Result status = Result::success();
        AutoLevelResult result;
        if (engine([&] { return g_adapter->take_auto_levelup_result(&status, &result); })) {
            PendingAutoLevelReply pending = std::move(g_auto_level);
            g_auto_level = PendingAutoLevelReply{};
            Json reply;
            if (status.ok) {
                Json body = Json::object();
                body.set("player_id", Json::unsigned_(result.player_id));
                body.set("level_before", Json::integer(result.level_before));
                body.set("level_after", Json::integer(result.level_after));
                body.set("experience", Json::unsigned_(result.experience));
                if (result.can_level_up >= 0)
                    body.set("can_level_up", Json::boolean(result.can_level_up != 0));
                reply = ok_reply(pending.id, std::move(body));
            } else {
                reply = err_reply(pending.id, std::move(status.error));
            }
            if (Channel* ch = channel(); ch != nullptr) ch->push_reply(pending.client, reply.dump());
        }
    }


    if (g_party_leader.active && g_adapter) {
        Result status = Result::success();
        PartyLeaderResult result;
        if (engine([&] { return g_adapter->take_party_leader_result(&status, &result); })) {
            PendingAutoLevelReply pending = std::move(g_party_leader);
            g_party_leader = PendingAutoLevelReply{};
            Json reply;
            if (status.ok) {
                Json body = Json::object();
                body.set("leader_before", Json::unsigned_(result.leader_before));
                body.set("leader_after", Json::unsigned_(result.leader_after));
                reply = ok_reply(pending.id, std::move(body));
            } else {
                reply = err_reply(pending.id, std::move(status.error));
            }
            if (Channel* ch = channel(); ch != nullptr) ch->push_reply(pending.client, reply.dump());
        }
    }

    if (g_use_item.active && g_adapter) {
        Result status = Result::success();
        UseItemResult result;
        if (engine([&] { return g_adapter->take_use_item_result(&status, &result); })) {
            PendingAutoLevelReply pending = std::move(g_use_item);
            g_use_item = PendingAutoLevelReply{};
            Json reply;
            if (status.ok) {
                Json body = Json::object();
                body.set("item", Json::unsigned_(result.item_id));
                body.set("target", Json::unsigned_(result.target_id));
                reply = ok_reply(pending.id, std::move(body));
            } else {
                reply = err_reply(pending.id, std::move(status.error));
            }
            if (Channel* ch = channel(); ch != nullptr) ch->push_reply(pending.client, reply.dump());
        }
    }

    if (g_door_security.active && g_adapter) {
        Result status = Result::success();
        DoorSecurityResult result;
        if (engine([&] { return g_adapter->take_door_security_result(&status, &result); })) {
            PendingAutoLevelReply pending = std::move(g_door_security);
            g_door_security = PendingAutoLevelReply{};
            Json reply;
            if (status.ok) {
                Json body = Json::object();
                body.set("door", Json::unsigned_(result.door_id));
                body.set("locked_before", Json::boolean(result.locked_before));
                body.set("locked_after", Json::boolean(result.locked_after));
                body.set("open_state_before", Json::unsigned_(result.open_state_before));
                body.set("open_state_after", Json::unsigned_(result.open_state_after));
                reply = ok_reply(pending.id, std::move(body));
            } else {
                reply = err_reply(pending.id, std::move(status.error));
            }
            if (Channel* ch = channel(); ch != nullptr) ch->push_reply(pending.client, reply.dump());
        }
    }

    if (g_equip_item.active && g_adapter) {
        Result status = Result::success();
        EquipItemResult result;
        if (engine([&] { return g_adapter->take_equip_item_result(&status, &result); })) {
            PendingAutoLevelReply pending = std::move(g_equip_item);
            g_equip_item = PendingAutoLevelReply{};
            Json reply;
            if (status.ok) {
                Json body = Json::object();
                body.set("requested_item", Json::unsigned_(result.requested_item_id));
                body.set("current_item", Json::unsigned_(result.current_item_id));
                body.set("slot", Json::unsigned_(result.slot));
                reply = ok_reply(pending.id, std::move(body));
            } else {
                reply = err_reply(pending.id, std::move(status.error));
            }
            if (Channel* ch = channel(); ch != nullptr) ch->push_reply(pending.client, reply.dump());
        }
    }

    if (!g_shot.active) return;
    PendingShot shot = std::move(g_shot);
    g_shot = PendingShot{};

    int width = 0;
    int height = 0;
    std::string error;
    const bool ok = engine([&] { return write_screenshot(shot.path, width, height, error); });

    Json reply;
    if (ok) {
        Json result = Json::object();
        result.set("path", Json::string(shot.path));
        result.set("width", Json::integer(width));
        result.set("height", Json::integer(height));
        result.set("format", Json::string("ppm"));
        result.set("client_tick", Json::unsigned_(client_tick()));
        reply = ok_reply(shot.id, std::move(result));
    } else {
        reply = err_reply(shot.id, "screenshot: " + error);
    }
    if (shot.lua_request) {
        g_lua_shot_result.ready = true;
        g_lua_shot_result.ok = ok;
        g_lua_shot_result.path = shot.path;
        g_lua_shot_result.error = error;
        g_lua_shot_result.width = width;
        g_lua_shot_result.height = height;
        g_lua_shot_result.client_tick = client_tick();
        return;
    }
    if (Channel* ch = channel(); ch != nullptr) ch->push_reply(shot.client, reply.dump());
}

}  // namespace kp::harness

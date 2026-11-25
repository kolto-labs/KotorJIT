#include "devtools/console.hpp"
#include "platform/naming.hpp"
// The five phases, in the order runtime.hpp declares them.
//
// Every phase either advances or fails, and a failure leaves the game exactly
// as it was found. There is no partial success anywhere in this file: the hook
// set installs atomically, and the phases before it write nothing at all.
#include "runtime/runtime.hpp"
#include "version.hpp"

#include <array>
#include <atomic>
#include <cctype>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <sys/stat.h>
#include <cstring>
#include <string>
#include <string_view>
#include <thread>
#include <vector>

#include "events/contract.hpp"
#include "events/table.hpp"
#include "generated/embedded_addresses.inc"
#include "hooks/registry.hpp"
#if defined(__i386__)
#include "hooks/lua_bridge.hpp"
#endif
#include "image/image.hpp"
#include "image/sha256.hpp"
#include "api/enginestruct.hpp"
#include "api/compat.hpp"
#include "api/routines.hpp"
#include "api/output.hpp"
#include "api/entity.hpp"
#include "api/structs.hpp"
#include "api/memory.hpp"
#include "api/model.hpp"
#include "api/camera.hpp"
#include "api/projectiles.hpp"
#include "api/animation.hpp"
#include "image/loaded_image.hpp"
#include "api/timers.hpp"
#include "api/vector.hpp"
#include "api/motion.hpp"
#include "api/scripts_lua.hpp"
#include "api/engine_gate.hpp"
#include "harness/commands.hpp"
#include "harness/engine.hpp"
extern "C" {
#include "lauxlib.h"
#include "lua.h"
}
#include "lua/host.hpp"
#include "lua/value.hpp"
#include "platform/platform.hpp"
#include "runtime/internal.hpp"

#if defined(_WIN32)
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#elif defined(__APPLE__)
#include <cstdlib>       // realpath
#include <mach-o/dyld.h> // _NSGetExecutablePath
#include <unistd.h>
#else
#include <unistd.h>
#endif

namespace kp::runtime {

namespace {
// kp.game_speed([scale]): read or set the engine's own game-speed scale, the
// one the harness `speed` command uses. Unlike kp.speed (whole extra ticks
// per frame, 1..16) this scales the five world/pause/animation timers, so it
// goes below 1: kp.game_speed(0.25) is real slow motion. Returns the scale in
// force; without a harness adapter it returns nil.
int l_game_speed(lua_State* L) {
    kp::harness::EngineAdapter* a = kp::harness::adapter();
    if (a == nullptr) { lua_pushnil(L); return 1; }
    if (lua_gettop(L) >= 1) {
        const double scale = luaL_checknumber(L, 1);
        const kp::harness::Result r = a->set_speed(static_cast<float>(scale));
        if (!r.ok) return luaL_error(L, "game_speed: %s", r.error.c_str());
    }
    lua_pushnumber(L, static_cast<lua_Number>(a->speed()));
    return 1;
}

void register_game_speed(lua_State* L) {
    lua_getglobal(L, "kp");
    if (!lua_istable(L, -1)) { lua_pop(L, 1); return; }
    lua_pushcfunction(L, l_game_speed);
    lua_setfield(L, -2, "game_speed");
    lua_pop(L, 1);
}
}  // namespace
namespace {

// Not in Runtime's member list because runtime.hpp fixes that list, and this
// has to be readable from hook_bodies.cpp without a Runtime lookup on every
// call. Release/acquire rather than relaxed: it publishes the Lua host and its
// loaded scripts to threads that never synchronised with the worker.
std::atomic<bool> g_live{false};

// Published alongside g_live, and for the same reason: stop() destroys the
// Host, and a game thread already inside a hook body has no synchronisation
// with the thread doing that.
std::atomic<lua::Host*> g_host{nullptr};
std::atomic<multiplayer::Transport*> g_multiplayer_transport{nullptr};

// Log lines come from the worker thread and from game threads inside hook
// bodies. A spin lock rather than a mutex keeps this usable from anywhere,
// including places where taking a real lock would be the wrong idea.
std::atomic_flag g_log_lock = ATOMIC_FLAG_INIT;

const char* kPathSep =
#if defined(_WIN32)
    "\\";
#else
    "/";
#endif

std::string join(const std::string& dir, const std::string& leaf) {
    if (dir.empty()) return leaf;
    const char last = dir.back();
    if (last == '/' || last == '\\') return dir + leaf;
    return dir + kPathSep + leaf;
}

std::string trim(std::string s) {
    const auto notspace = [](unsigned char c) { return std::isspace(c) == 0; };
    while (!s.empty() && !notspace(static_cast<unsigned char>(s.front()))) s.erase(s.begin());
    while (!s.empty() && !notspace(static_cast<unsigned char>(s.back()))) s.pop_back();
    return s;
}

bool truthy(const std::string& v) {
    return v == "1" || v == "true" || v == "yes" || v == "on";
}

bool file_exists(const std::string& path) {
    std::FILE* f = std::fopen(path.c_str(), "rb");
    if (f == nullptr) return false;
    std::fclose(f);
    return true;
}

// A relative path in the ini means "next to the game", which is the only thing
// a player writing that file could reasonably mean.
std::string resolve_against(const std::string& base, const std::string& value) {
    if (value.empty()) return value;
    if (value.front() == '/' || value.front() == '\\') return value;
    if (value.size() > 2 && value[1] == ':') return value;   // C:\...
    return join(base, value);
}

// KOTORJIT_HARNESS_PORT wins over the ini, and it has to win whether or
// not the ini exists: it is how a build directory is driven without staging
// a file next to the game. Applied on both exits from from_game_dir.
void apply_harness_env(Config& c) {
    const char* port = kp::naming::env("HARNESS_PORT");
    if (port != nullptr && *port != '\0')
        c.harness_port = static_cast<unsigned>(std::strtoul(port, nullptr, 10));
}

void apply_multiplayer_env(Config& c) {
    if (const char* host = kp::naming::env("MULTIPLAYER_HOST"); host != nullptr && *host != '\0')
        c.multiplayer_host = host;
    if (const char* port = kp::naming::env("MULTIPLAYER_PORT"); port != nullptr && *port != '\0')
        c.multiplayer_port = static_cast<unsigned>(std::strtoul(port, nullptr, 10));
}

}  // namespace

// ------------------------------------------------------------------ misc ----

const char* to_string(Phase p) {
    switch (p) {
    case Phase::Idle:             return "idle";
    case Phase::Identifying:      return "identifying";
    case Phase::AwaitingDecipher: return "awaiting-decipher";
    case Phase::Resolving:        return "resolving";
    case Phase::Installing:       return "installing";
    case Phase::Running:          return "running";
    case Phase::Failed:           return "failed";
    }
    return "?";
}

bool live() { return g_live.load(std::memory_order_acquire); }
void set_live(bool v) { g_live.store(v, std::memory_order_release); }

namespace {
std::atomic<std::thread::id> g_engine_thread{};

kp::api::motion::Writer motion_owner(lua_State* L, void*) {
    lua::Script* script = lua::Script::owner(L);
    if (script == nullptr) return kp::api::motion::Writer::None;
    return script->staged() ? kp::api::motion::Writer::Staged
                            : kp::api::motion::Writer::Loaded;
}

std::uint64_t motion_tick(void*) {
    lua::Host* h = active_host();
    return h != nullptr ? h->tick() : 0;
}
}

void reset_engine_thread() {
    g_engine_thread.store(std::thread::id{}, std::memory_order_release);
    reset_client_gate_mismatch_log();
}

void latch_engine_thread() {
    std::thread::id unset{};
    g_engine_thread.compare_exchange_strong(
        unset, std::this_thread::get_id(), std::memory_order_acq_rel);
}

bool on_engine_thread() {
    return g_engine_thread.load(std::memory_order_acquire) == std::this_thread::get_id();
}

bool engine_thread_latched() {
    return g_engine_thread.load(std::memory_order_acquire) != std::thread::id{};
}

bool engine_gate_probe(void*) { return live() && on_engine_thread(); }

lua::Host* active_host() { return g_host.load(std::memory_order_acquire); }
void set_active_host(lua::Host* h) { g_host.store(h, std::memory_order_release); }

multiplayer::Transport* active_multiplayer_transport() {
    return g_multiplayer_transport.load(std::memory_order_acquire);
}
void set_active_multiplayer_transport(multiplayer::Transport* transport) {
    g_multiplayer_transport.store(transport, std::memory_order_release);
}

// Written once during boot, on the worker thread, before any hook body can run;
// read afterwards from the console, which is a game thread. Not atomic: the
// publish happens-before the first body through set_live's release, and a
// std::function is not a thing to put in an atomic anyway.
std::function<void(lua_State*)> g_state_init;

void set_state_init(std::function<void(lua_State*)> fn) { g_state_init = std::move(fn); }
void init_lua_state(lua_State* L) { if (g_state_init) g_state_init(L); }

std::string directory_of(const std::string& path) {
    const std::size_t cut = path.find_last_of("/\\");
    return cut == std::string::npos ? std::string(".") : path.substr(0, cut);
}

std::string self_module_path() {
#if defined(_WIN32)
    char buf[MAX_PATH] = {0};
    const DWORD n = GetModuleFileNameA(nullptr, buf, sizeof buf);
    return n > 0 ? std::string(buf, n) : std::string();
#elif defined(__APPLE__)
    // The GAME executable, not this dylib: the runtime derives game_dir,
    // script dir and log path from it. When KotorJIT is loaded through
    // DYLD_INSERT_LIBRARIES, _NSGetExecutablePath still names the host
    // executable (KOTOR_Exe / KOTOR2sub), which is what we want. The path it
    // returns may be non-canonical (symlinks, .. segments); realpath resolves
    // it so directory_of() yields the real app-bundle MacOS directory.
    char buf[4096] = {0};
    std::uint32_t size = sizeof buf;
    if (_NSGetExecutablePath(buf, &size) != 0) return {};
    char resolved[4096] = {0};
    if (::realpath(buf, resolved) != nullptr) return std::string(resolved);
    return std::string(buf);
#else
    char buf[4096] = {0};
    const ssize_t n = ::readlink("/proc/self/exe", buf, sizeof buf - 1);
    return n > 0 ? std::string(buf, static_cast<std::size_t>(n)) : std::string();
#endif
}

const std::vector<events::EventContract>& event_table() {
    return events::table();
}

const events::EventContract* find_contract(std::string_view lua_name) {
    return events::find(lua_name);
}

static bool is_directory(const std::string& path) {
    struct stat st {};
    return ::stat(path.c_str(), &st) == 0 && S_ISDIR(st.st_mode);
}

// A Config built by hand (not through from_game_dir) has no data_dir; fall
// back to the current folder name under game_dir rather than the process cwd.
static std::string data_dir_of(const Config& cfg) {
    return cfg.data_dir.empty() ? join(cfg.game_dir, naming::kDataDir) : cfg.data_dir;
}

// ---------------------------------------------------------------- Config ----

Config Config::from_game_dir(const std::string& game_dir) {
    Config c;
    c.game_dir = game_dir;
    // Current folder name first; an install made under the old name keeps
    // working untouched. Only when the current folder is absent and the legacy
    // one is present does the legacy one win -- a fresh install gets the new
    // name even though neither exists yet.
    const std::string current = join(game_dir, naming::kDataDir);
    const std::string legacy = join(game_dir, naming::kLegacyDataDir);
    c.data_dir = (!is_directory(current) && is_directory(legacy)) ? legacy : current;
    c.script_dir = join(c.data_dir, "scripts");
    c.log_path = join(game_dir, naming::kLogName);

    std::FILE* f = std::fopen(join(game_dir, naming::kIniName).c_str(), "rb");
    if (f == nullptr) f = std::fopen(join(game_dir, naming::kLegacyIniName).c_str(), "rb");
    apply_harness_env(c);
    apply_multiplayer_env(c);
    if (f == nullptr) return c;   // optional, and its absence is not a problem

    char line[1024];
    while (std::fgets(line, sizeof line, f) != nullptr) {
        std::string s = line;
        // Comments and section headers. Sections are accepted and ignored so a
        // player can organise the file without it meaning anything.
        const std::size_t hash = s.find_first_of(";#");
        if (hash != std::string::npos) s.erase(hash);
        s = trim(s);
        if (s.empty() || s.front() == '[') continue;

        const std::size_t eq = s.find('=');
        if (eq == std::string::npos) continue;
        const std::string key = trim(s.substr(0, eq));
        const std::string val = trim(s.substr(eq + 1));

        if (key == "script_dir")        c.script_dir = resolve_against(game_dir, val);
        else if (key == "log_path")     c.log_path = resolve_against(game_dir, val);
        else if (key == "error_budget") c.error_budget = static_cast<unsigned>(std::strtoul(val.c_str(), nullptr, 10));
        else if (key == "hot_reload")   c.hot_reload = truthy(val);
        // [harness] keys. Sections are ignored above, so these are global.
        else if (key == "harness_port") c.harness_port = static_cast<unsigned>(std::strtoul(val.c_str(), nullptr, 10));
        else if (key == "harness_bind") c.harness_bind = val;
        else if (key == "multiplayer_host") c.multiplayer_host = val;
        else if (key == "multiplayer_port") c.multiplayer_port = static_cast<unsigned>(std::strtoul(val.c_str(), nullptr, 10));
    }
    std::fclose(f);
    apply_harness_env(c);
    apply_multiplayer_env(c);
    return c;
}

// --------------------------------------------------------------- Runtime ----

Runtime& Runtime::instance() {
    static Runtime r;
    return r;
}

void Runtime::log(const char* fmt, ...) {
    char raw[1024];
    va_list ap;
    va_start(ap, fmt);
    std::vsnprintf(raw, sizeof raw, fmt, ap);
    va_end(ap);

    // One call, one line. Script text (print, kp.diagnostic, load errors)
    // reaches here, so a line break or other control character in it is
    // written as an escape: it cannot start a new line that looks like the
    // runtime's own (the receipt's banner, host and gl lines). Worst case
    // is four bytes out per byte in, so nothing is cut.
    char body[4 * sizeof raw];
    std::size_t n = 0;
    for (const char* p = raw; *p != '\0'; ++p) {
        const unsigned char c = static_cast<unsigned char>(*p);
        if (c >= 0x20 && c != 0x7f) {
            body[n++] = *p;
            continue;
        }
        body[n++] = '\\';
        switch (c) {
            case '\n': body[n++] = 'n'; break;
            case '\r': body[n++] = 'r'; break;
            case '\t': body[n++] = 't'; break;
            default:
                body[n++] = 'x';
                body[n++] = "0123456789abcdef"[c >> 4];
                body[n++] = "0123456789abcdef"[c & 0x0f];
                break;
        }
    }
    body[n] = '\0';

    while (g_log_lock.test_and_set(std::memory_order_acquire)) {}
    std::FILE* f = std::fopen(log_path_.empty() ? "kotorjit.log" : log_path_.c_str(), "ab");
    if (f != nullptr) {
        std::fprintf(f, "[%s] %s\n", to_string(phase_), body);
        std::fclose(f);
    }
    g_log_lock.clear(std::memory_order_release);
}

namespace {

// Route the hook engine's and the image module's own diagnostics into the same
// file. Without this they go to stderr, which in a Windows game process is
// nowhere.
void runtime_log_sink(platform::LogLevel level, const char* message, void*) {
    Runtime::instance().log("%s: %s", platform::to_string(level), message);
}

}  // namespace

bool Runtime::identify(const Config& cfg) {
    phase_ = Phase::Identifying;

    const std::string exe = self_module_path();
    if (exe.empty()) {
        failure_ = "cannot determine the path of the running executable";
        return false;
    }

    // Hashing here and again inside image::load() is deliberate duplication.
    // image::load() is one call that does identify, await and verify together,
    // and splitting it would mean reaching into image/'s internals; hashing a
    // six-megabyte file twice costs a few tens of milliseconds and keeps this
    // phase able to say something before the decipher wait begins.
    const std::string sha = image::sha256_file(exe);
    if (sha.empty()) {
        failure_ = "cannot read the executable: " + exe;
        return false;
    }

    log("game executable: %s", exe.c_str());
    log("sha256: %s", sha.c_str());
    log("game directory: %s", cfg.game_dir.c_str());
    return true;
}

bool Runtime::await_and_verify(const Config& cfg) {
    (void)cfg;
    phase_ = Phase::AwaitingDecipher;

    const std::string exe = self_module_path();
    log("classifying and, if encrypted, waiting for the code section to decipher");

    const image::LoadResult r = image::load(exe);
    if (r.status != image::LoadStatus::Ok) {
        failure_ = std::string("image: ") + image::to_string(r.status);
        if (!r.detail.empty()) failure_ += " -- " + r.detail;
        return false;
    }

    build_ = r.identity.build_alias;
    image_sha256_ = r.identity.sha256;
    runtime_base_ = r.image_base;

    log("build: %s (image base 0x%08lx, waited %ums)", build_.c_str(),
        static_cast<unsigned long>(runtime_base_), r.waited_ms);
    log("code section verified: %s", r.text_sha256.c_str());
    std::vector<api::memory::ScanRegion> regions;
    for (const image::Section& s : r.sections) {
        if (!s.executable) continue;
        log("  section %s va=0x%08lx size=%lu entropy=%.3f state=%s", s.name.c_str(),
            static_cast<unsigned long>(s.va), static_cast<unsigned long>(s.size), s.entropy,
            s.state == image::SectionState::Ciphertext  ? "ciphertext"
            : s.state == image::SectionState::Deciphered ? "deciphered"
                                                         : "plaintext");
        if (s.state == image::SectionState::Ciphertext || s.size == 0) continue;
        regions.push_back({s.va, s.size, s.name});
    }
    api::memory::bind_scan_regions(runtime_base_, std::move(regions));
    std::string model_error;
    auto read_model = [](api::model::Address address, void* out, std::size_t size, void*) {
        image::LiveImage live(0);
        if(address > UINTPTR_MAX)return false;
        return live.read(static_cast<std::uintptr_t>(address),out,size);
    };
    if(!api::camera::bind_native(image_sha256_,runtime_base_,read_model,nullptr,model_error))
        log("camera: %s",model_error.c_str());
    if(!api::motion::bind_native(image_sha256_,runtime_base_,read_model,nullptr,model_error))
        log("motion: %s",model_error.c_str());
    if(!api::projectiles::bind_native(image_sha256_,runtime_base_,model_error))
        log("projectiles: %s",model_error.c_str());
    // Model/animation binding is intentionally deferred until resolve(): it
    // requires the admitted hook-pack's exact target and generated role table.
    api::animation::operations().unbind();
    api::model::operations().unbind();
    return true;
}

bool Runtime::resolve(const Config& cfg) {
    phase_ = Phase::Resolving;

    if (build_.empty()) {
        failure_ = "no build alias, so no address table to load";
        return false;
    }

    // Hook manifest first (masked patterns, scan-only: no VA is trusted), then
    // hook pack (logical sites + per-build instance cache), then the optional
    // per-build overlay for expected_bytes / kind / required. Address JSON
    // alone still works when neither is staged.
    std::vector<std::string> manifest_candidates;
    manifest_candidates.push_back(join(data_dir_of(cfg), "hookmanifest.json"));
    if (const char* m = kp::naming::env("HOOKMANIFEST"); m != nullptr && *m != '\0')
        manifest_candidates.insert(manifest_candidates.begin(), m);
    if (const char* dir = kp::naming::env("ADDRESSES"); dir != nullptr && *dir != '\0')
        manifest_candidates.push_back(join(dir, "hookmanifest.json"));

    std::vector<std::string> pack_candidates;
    pack_candidates.push_back(join(data_dir_of(cfg), "hookpack.json"));
    if (const char* pack = kp::naming::env("HOOKPACK"); pack != nullptr && *pack != '\0')
        pack_candidates.insert(pack_candidates.begin(), pack);
    if (const char* dir = kp::naming::env("ADDRESSES"); dir != nullptr && *dir != '\0')
        pack_candidates.push_back(join(dir, "hookpack.json"));

    std::vector<std::string> candidates;
    candidates.push_back(join(join(data_dir_of(cfg), "addresses"), build_ + ".json"));
    candidates.push_back(join(data_dir_of(cfg), build_ + ".json"));
    if (const char* dir = kp::naming::env("ADDRESSES"); dir != nullptr && *dir != '\0')
        candidates.push_back(join(dir, build_ + ".json"));

    std::string manifest;
    for (const std::string& p : manifest_candidates) {
        if (file_exists(p)) { manifest = p; break; }
    }
    std::string pack;
    if (manifest.empty()) {
        for (const std::string& p : pack_candidates) {
            if (file_exists(p)) { pack = p; break; }
        }
    }
    std::string chosen;
    for (const std::string& p : candidates) {
        if (file_exists(p)) { chosen = p; break; }
    }
    std::string_view embedded;
    if (chosen.empty()) {
        embedded = kp::generated::find_embedded_address_table(build_);
    }
    if (manifest.empty() && pack.empty() && chosen.empty()) {
        if (embedded.empty()) {
            failure_ = "no hook manifest, hook pack or address table for build \"" + build_ + "\"; looked in";
            for (const std::string& p : manifest_candidates) failure_ += " " + p;
            for (const std::string& p : pack_candidates) failure_ += " " + p;
            for (const std::string& p : candidates) failure_ += " " + p;
            failure_ += " (and no embedded table)";
            return false;
        }
        log("using embedded address table for %s", build_.c_str());
    }

    auto table = std::make_unique<hooks::AddressTable>();
    std::string error;
    if (!manifest.empty()) {
        if (!hooks::AddressTable::load_manifest(manifest, build_, chosen, *table, error)) {
            failure_ = "hook manifest " + manifest + ": " + error;
            return false;
        }
        if (chosen.empty() && !embedded.empty()) {
            hooks::AddressTable overlay;
            if (!hooks::AddressTable::parse(embedded, overlay, error)) {
                failure_ = "embedded address table for " + build_ + ": " + error;
                return false;
            }
            table->merge_overlay(overlay);
            log("merged embedded address table overlay for %s", build_.c_str());
        }
        if (!table->expected_sha256().empty() && table->expected_sha256() != image_sha256_) {
            log("hook manifest %s was generated from sha256 %s; this image is %s -- "
                "binding by pattern only, ambiguous or missing sites refuse",
                manifest.c_str(), table->expected_sha256().c_str(), image_sha256_.c_str());
        }
    } else if (!pack.empty()) {
        if (!hooks::AddressTable::load_hookpack(pack, build_, chosen, *table, error)) {
            failure_ = "hook pack " + pack + ": " + error;
            return false;
        }
        if (chosen.empty() && !embedded.empty()) {
            hooks::AddressTable overlay;
            if (!hooks::AddressTable::parse(embedded, overlay, error)) {
                failure_ = "embedded address table for " + build_ + ": " + error;
                return false;
            }
            table->merge_overlay(overlay);
            log("merged embedded address table overlay for %s", build_.c_str());
        }
    } else if (!chosen.empty()) {
        if (!hooks::AddressTable::load_file(chosen, *table, error)) {
            failure_ = "address table " + chosen + ": " + error;
            return false;
        }
    } else if (!hooks::AddressTable::parse(embedded, *table, error)) {
        failure_ = "embedded address table for " + build_ + ": " + error;
        return false;
    }

    table->resolve_from_signatures(runtime_base_);
    std::size_t bound = 0;
    std::size_t missing_pattern = 0;
    std::size_t ambiguous_pattern = 0;
    for (const hooks::Site& s : table->sites()) {
        if (s.resolved) ++bound;
        if (s.locate_error == "missing") ++missing_pattern;
        if (s.locate_error == "ambiguous") ++ambiguous_pattern;
        if (s.bound_from_scan && !table->scan_only()) {
            log("signature resolve: %s bound from scan (hint stale or missing)", s.name.c_str());
        }
    }
    log("signature resolve: %zu/%zu sites bound (VA is a hint)", bound, table->sites().size());
    if (table->scan_only()) {
        log("pattern resolve: %zu missing, %zu ambiguous (refused, left unbound)",
            missing_pattern, ambiguous_pattern);
    }

    const std::string source = !manifest.empty()
        ? manifest
        : (!pack.empty() ? pack : (!chosen.empty() ? chosen : ("embedded:" + build_)));
    const std::string err_source = !manifest.empty()
        ? ("hook manifest " + manifest)
        : (!pack.empty() ? ("hook pack " + pack)
                         : (!chosen.empty() ? ("address table " + chosen)
                                            : ("embedded address table for " + build_)));
    const std::vector<std::string> missing = table->unresolved_required();
    if (!missing.empty()) {
        failure_ = err_source + " leaves required sites unresolved:";
        for (const std::string& m : missing) {
            failure_ += " " + m;
            if (const hooks::Site* s = table->find(m); s != nullptr && !s->locate_error.empty())
                failure_ += "(" + s->locate_error + ")";
        }
        return false;
    }

    table_ = std::move(table);
    log("address table: %s (%zu sites, build %s, %s)", source.c_str(), table_->sites().size(),
        table_->build().c_str(), table_->platform_name().c_str());

    // A compiled profile establishes the separately-qualified layout and ABI.
    // Its callable sites come from the admitted generated operation, never a
    // profile-only fallback.  Missing/ambiguous/stale roles leave this optional
    // capability unavailable while ordinary hooks continue to start.
    constexpr std::array<const char*, 5> model_roles{{
        "kp.model.convert", "kp.model.creature", "kp.model.model",
        "kp.model.setter", "kp.model.server-object",
    }};
    const bool generated_model = !pack.empty() &&
        table_->expected_sha256() == image_sha256_ &&
        table_->has_operation("kotor.k1.model-scale.v1");
    std::array<api::model::Address, 5> generated_sites{};
    bool roles_resolved = generated_model;
    if (roles_resolved) {
        for (std::size_t i=0; i<model_roles.size(); ++i) {
            const hooks::Site* site = table_->find_adapter(model_roles[i]);
            if (site == nullptr || !site->resolved) { roles_resolved=false; break; }
            generated_sites[i]=static_cast<api::model::Address>(site->addr);
        }
    }
    // The generated-model path above is the Windows hook-pack route. The macOS
    // x86_64 builds ship a JSON address table and no pack, but the native
    // model backend already carries a by-hash profile for the K2 x86_64 image
    // (api/model_profiles.cpp, macos-k2-x86_64), whose five site VAs and
    // expected_bytes were recovered from the corpus (docs/research/
    // mac-model-memory.md). Bind from that profile directly: its own site VAs
    // are the "generated roles", and Operations::bind re-verifies each site's
    // bytes at load, so a wrong image still refuses.
    if (!roles_resolved) {
        if (const api::model::Profile* mp = api::model::profile_for(image_sha256_)) {
            bool complete = true;
            for (std::size_t i = 0; i < generated_sites.size(); ++i) {
                generated_sites[i] = mp->sites[i].va;
                if (mp->sites[i].va == 0 || mp->sites[i].bytes == nullptr) complete = false;
            }
            roles_resolved = complete;
            if (!complete)
                log("model: profile %s has fewer than five sites; native model API unavailable", mp->name);
        }
    }
    if (!roles_resolved) {
        log("model: unavailable; needs the generated model-scale operation (Windows pack) or a "
            "complete by-hash native profile (macOS)");
        return true;
    }
    std::string model_error;
    auto read_model = [](api::model::Address address, void* out, std::size_t size, void*) {
        image::LiveImage live(0);
        if(address > UINTPTR_MAX)return false;
        return live.read(static_cast<std::uintptr_t>(address),out,size);
    };
    auto log_model = [](const std::string& message,void*) { Runtime::instance().log("%s",message.c_str()); };
    if(!api::model::bind_native(image_sha256_,runtime_base_,read_model,log_model,nullptr,&generated_sites,model_error)) {
        log("model: %s",model_error.c_str());
        return true;
    }
    if(!api::animation::bind_native(image_sha256_,runtime_base_,read_model,log_model,nullptr,model_error))
        log("animation: %s",model_error.c_str());
    return true;
}

bool Runtime::start_multiplayer(const Config& cfg) {
    if (role_ == multiplayer::Role::Embedded || cfg.multiplayer_port == 0) return true;
    // A transport receipt is an ABI fact, not a marketing build label.  The
    // Steam and GOG Aspyr binaries share the K2 wrapper and implementer
    // layouts; both facts are resolved from the exact image's signed table.
    const hooks::Site* wrapper_internal = table_->find("vm.wrapper_internal");
    const hooks::Site* command_implementer =
        table_->find("vm.internal_command_implementer");
    const bool k1_receipt = build_ == "k1_gog_103" &&
        wrapper_internal != nullptr && wrapper_internal->resolved &&
        wrapper_internal->offset == 0 && command_implementer != nullptr &&
        command_implementer->resolved && command_implementer->offset == 0x3d4;
    const bool k2_receipt = (build_ == "k2_gog_aspyr" || build_ == "k2_steam_aspyr") &&
        wrapper_internal != nullptr && wrapper_internal->resolved &&
        wrapper_internal->offset == 0x1c && command_implementer != nullptr &&
        command_implementer->resolved && command_implementer->offset == 0x3d4;
    if (!k1_receipt && !k2_receipt) {
        failure_ = "multiplayer transport has no ABI receipt for build " + build_;
        return false;
    }
    if (cfg.multiplayer_port > 65535 || image_sha256_.empty()) {
        failure_ = cfg.multiplayer_port > 65535
            ? "multiplayer port must be 1..65535"
            : "multiplayer transport requires an exact executable identity";
        return false;
    }

    auto transport = std::make_unique<multiplayer::Transport>();
    std::string error;
    const auto port = static_cast<std::uint16_t>(cfg.multiplayer_port);
    const bool started = role_ == multiplayer::Role::Server
        ? transport->start_server(cfg.multiplayer_host, port, image_sha256_, error)
        : transport->start_client(cfg.multiplayer_host, port, image_sha256_, error);
    if (!started) {
        failure_ = "multiplayer transport: " + error;
        return false;
    }
    transport_ = std::move(transport);
    set_active_multiplayer_transport(transport_.get());
    log("multiplayer: %s on %s:%u for exact image %s",
        role_ == multiplayer::Role::Server ? "listening" : "connected socket",
        cfg.multiplayer_host.c_str(), static_cast<unsigned>(transport_->port()),
        image_sha256_.c_str());
    return true;
}

bool Runtime::install(bool multiplayer_enabled) {
    phase_ = Phase::Installing;

    if (!table_) { failure_ = "install called with no address table"; return false; }

    // `expect` is left empty on purpose. The address table carries the bytes
    // the generator read out of a plaintext reference image, and the registry
    // prefers those -- they are wider than a pattern typed here and they cannot
    // drift away from the table they came from.
    auto set = std::make_unique<hooks::HookSet>();
    set->add({"vm.run_script", run_script_detour(), {}});
    set->add({"app.server_main_loop", main_loop_detour(), {}});

    // Optional caves. HookSet::install refuses an unresolved requested site, so
    // only add the ones this build actually bound. Named vm.run_script events
    // stay off this list.
    const struct {
        const char* site;
        void*       detour;
    } optional[] = {
        {"console.do_console", do_console_detour()},
        {"event.creature", creature_event_detour()},
        {"event.door", door_event_detour()},
        {"event.placeable", placeable_event_detour()},
        {"event.trigger", trigger_event_detour()},
        {"event.module", module_event_detour()},
        {"event.area", area_event_detour()},
        {"event.encounter", encounter_event_detour()},
        {"event.aoe", aoe_event_detour()},
        {"event.store", store_event_detour()},
        {"event.waypoint", waypoint_event_detour()},
        {"vm.save_script_situation", save_situation_detour()},
        {"vm.load_script_situation", load_situation_detour()},
        // Harness caves. The client loop is where commands drain -- it is the
        // one per-frame site that runs on the main menu. The other two keep
        // the harness's time scale and movie switch from being undone by the
        // engine's own per-frame calls. All three are kind=detour only in a
        // build's generated JSON, so a table that still says `reference`
        // leaves them uninstalled here rather than refused at install.
        {"app.client_main_loop", client_main_loop_detour()},
        {"app.client_frame_wrapper", client_frame_wrapper_detour()},
        {"client.set_game_speed", kp::harness::client_set_game_speed_detour()},
        {"client.play_movies", kp::harness::client_play_movies_detour()},
        // K1 only. This observes mapped admission fields before the original
        // action runs; builds without the site retain their normal route.
        {"creature.ai_action_move_to_point", creature_move_to_point_detour()},
    };
    for (const auto& o : optional) {
        // Save-situation forwarding is experimentally disableable for live
        // crash isolation. The default remains unchanged; this switch is
        // intentionally process-local and never affects address resolution.
        if (std::getenv("KP_DISABLE_SAVE_HOOK") != nullptr &&
            std::strcmp(o.site, "vm.save_script_situation") == 0)
            continue;
        const hooks::Site* s = table_->find(o.site);
        if (s != nullptr && s->resolved && s->kind == hooks::SiteKind::Detour)
            set->add({o.site, o.detour, {}});
    }

    if (multiplayer_enabled) {
        const struct { const char* site; void* detour; } network[] = {
            {"net.start_connect_to_session", net_start_connect_detour()},
            {"net.start_server_mode", net_start_server_mode_detour()},
            {"net.send_message_to_player", net_send_message_detour()},
            {"net.process_received_frames", net_process_frames_detour()},
            {"client.area_get_server_area", client_area_get_server_area_detour()},
            {"creature.add_move_to_point_action", add_move_to_point_detour()},
        };
        for (const auto& hook : network) {
            const hooks::Site* site = table_->find(hook.site);
            if (site == nullptr || !site->resolved || site->kind != hooks::SiteKind::Detour) {
                failure_ = std::string("multiplayer hook unavailable: ") + hook.site;
                return false;
            }
            set->add({hook.site, hook.detour, {}});
        }
        const hooks::Site* destination = table_->find("net.destination_net_layer");
        if (destination == nullptr || !destination->resolved ||
            destination->kind != hooks::SiteKind::Field || destination->size != 4 ||
            destination->offset == 0) {
            failure_ = "multiplayer field unavailable: net.destination_net_layer";
            return false;
        }
        set_net_destination_offset(destination->offset);
        for (const char* support_site : {"module.get_area", "client_area.attach_from_server",
                                         "server_area.attach_from_client",
                                         "server.get_player_creature_id",
                                         "server.get_game_object", "server_object.set_position",
                                         "object.id"}) {
            const hooks::Site* site = table_->find(support_site);
            if (site == nullptr || !site->resolved) {
                failure_ = std::string("multiplayer support-area site unavailable: ") + support_site;
                return false;
            }
        }
    }

    // The routine bridge's addresses come straight from the table we just
    // resolved, so this needs no installed hook -- and it must run BEFORE
    // set->install() below. The hooked vm.run_script can start firing on the
    // game's own thread the moment install() patches it in, and its body
    // (capture_vm) reads g_sites unconditionally with no "not ready yet"
    // gate. Publishing g_sites afterward left a window where a heartbeat
    // script bound the VM against a zeroed VmSites, failed, and latched
    // g_vm_bound permanently -- killing every nwscript.call routine call for the
    // rest of the process with no retry.
    {
        api::VmSites sites;
        auto at = [&](const char* name) -> std::uintptr_t {
            const hooks::Site* s = table_->find(name);
            return (s != nullptr && s->resolved) ? s->addr : 0;
        };
        sites.execute_command    = at("vm.execute_command");
        sites.stack_push_integer = at("vm.stack_push_integer");
        sites.stack_pop_integer  = at("vm.stack_pop_integer");
        sites.stack_push_float   = at("vm.stack_push_float");
        sites.stack_pop_float    = at("vm.stack_pop_float");
        sites.stack_push_string  = at("vm.stack_push_string");
        sites.stack_pop_string   = at("vm.stack_pop_string");
        sites.stack_push_object  = at("vm.stack_push_object");
        sites.stack_pop_object   = at("vm.stack_pop_object");
        sites.stack_push_vector  = at("vm.stack_push_vector");
        sites.stack_pop_vector   = at("vm.stack_pop_vector");
        sites.stack_push_engine_structure = at("vm.stack_push_engine_structure");
        sites.stack_pop_engine_structure  = at("vm.stack_pop_engine_structure");
        const hooks::Site* wrapper_internal = table_->find("vm.wrapper_internal");
        const hooks::Site* command_implementer =
            table_->find("vm.internal_command_implementer");
        sites.layout_resolved =
            wrapper_internal != nullptr && wrapper_internal->resolved &&
            wrapper_internal->kind == hooks::SiteKind::Field &&
            wrapper_internal->size == sizeof(void*) &&
            command_implementer != nullptr && command_implementer->resolved &&
            command_implementer->kind == hooks::SiteKind::Field &&
            command_implementer->size == sizeof(void*);
        if (sites.layout_resolved) {
            sites.wrapper_internal_offset = wrapper_internal->offset;
            sites.command_implementer_offset = command_implementer->offset;
        }
        set_vm_sites(sites);
        log("vm: %d of 13 stack sites resolved; layout=%s; the two VM objects are captured "
            "from the first script the game runs",
            (sites.execute_command ? 1 : 0) + (sites.stack_push_integer ? 1 : 0) +
            (sites.stack_pop_integer ? 1 : 0) + (sites.stack_push_float ? 1 : 0) +
            (sites.stack_pop_float ? 1 : 0) + (sites.stack_push_string ? 1 : 0) +
            (sites.stack_pop_string ? 1 : 0) + (sites.stack_push_object ? 1 : 0) +
            (sites.stack_pop_object ? 1 : 0) + (sites.stack_push_vector ? 1 : 0) +
            (sites.stack_pop_vector ? 1 : 0) +
            (sites.stack_push_engine_structure ? 1 : 0) +
            (sites.stack_pop_engine_structure ? 1 : 0),
            sites.layout_resolved ? "resolved" : "unresolved");
    }

    std::string error;
    if (!set->install(*table_, runtime_base_, error)) {
        failure_ = "hook install: " + error;
        return false;
    }

    hooks_ = std::move(set);
    bind_originals(*hooks_);
    log("installed %zu hooks", hooks_->installed_count());

    // The harness adapter binds every engine call and field it can from the
    // same resolved table. Built whether or not a listener will open: it is
    // cheap, and it logs its missing sites once, here, where the log is being
    // read. A site that did not resolve makes the matching command answer
    // `unsupported`; nothing is dereferenced that the table did not give.
    kp::harness::set_adapter(kp::harness::make_adapter(*table_, runtime_base_));
    if (kp::harness::EngineAdapter* a = kp::harness::adapter(); a != nullptr) {
        const std::vector<std::string> missing = a->missing_sites();
        std::string list;
        for (const std::string& m : missing) list += (list.empty() ? "" : ", ") + m;
        log("harness: adapter %s, %zu site(s) unbound%s%s", a->name(), missing.size(),
            list.empty() ? "" : ": ", list.c_str());
    }
    return true;
}

bool Runtime::boot_scripts(const Config& cfg) {
#if defined(__i386__)
    hooks::lua_bridge::bind(table_.get(), runtime_base_,
        +[] { return live() && on_engine_thread(); },
        +[] { return on_engine_thread() || (!live() && !engine_thread_latched()); },
        +[](hooks::lua_bridge::Entry& entry, void (*work)(void*), void* arg) {
            volatile bool healthy = true;   // written by the setjmp fault path (-Wclobbered)
            KP_HOOK_GUARD_BEGIN(entry.site.name.c_str(), entry.poisoned, healthy = false)
                work(arg);
            KP_HOOK_GUARD_END
            return healthy;
        },
        +[](const hooks::Site& site) {
            // Inferred ABI confidence is not independent proof. A reviewer must
            // opt each exact site into this experimental bridge after checking
            // its complete calling contract against the binary.
            const char* configured = kp::naming::env("REVIEWED_LUA_HOOKS");
            if (!configured) return false;
            std::string_view ids(configured);
            while (!ids.empty()) {
                const auto end = ids.find(',');
                if (ids.substr(0, end) == site.name) return true;
                if (end == std::string_view::npos) break;
                ids.remove_prefix(end + 1);
            }
            return false;
        });
#endif
    lua::HostConfig hc;
    hc.script_dir = cfg.script_dir;
    hc.error_budget = cfg.error_budget;
    hc.hot_reload = cfg.hot_reload;
    api::timers::set_error_budget(cfg.error_budget);
    set_situation_path(join(data_dir_of(cfg), "lua_situation.dat"));

    // Everything a script can call is registered here, on each fresh state.
    // The Lua host takes this as a hook precisely so it does not have to know
    // what a KOTOR routine is -- see the note on HostConfig.
    hc.on_state_created = [game_dir = cfg.game_dir](lua_State* L) {
        // Order matters in one place only: the engine-structure metatables must
        // exist before anything can hand a script one of those handles.
        api::open_engine_structs(L);      // effect/event/location/talent handles
        api::register_all(L);             // nwscript.call(name, ...), all 769
        api::memory::register_all(L);     // raw read/write, the escape hatch
#if defined(__i386__)
        hooks::lua_bridge::register_all(L);
#endif
        api::structs::register_all(L);    // named typed field access
        api::animation::register_all(L);  // native named clip clocks
        api::projectiles::register_all(L);
        api::model::register_all(L);      // checked native actor scale
        api::camera::register_all(L);     // read-only chase camera snapshot (K1 GOG)
        api::register_vector(L);          // kp.vec value type and operations
        api::motion::register_all(L);     // kp.motion guarded native movement
        api::scripts::register_all(L);    // kp.scripts lifecycle queue
        api::entity::register_all(L);     // objects, party, resolution
        api::register_support(L);         // output, timers and strings together
        register_director(L);             // kp.speed — MainLoop tick scale
        register_game_speed(L);           // kp.game_speed — engine SetGameSpeed scale, (0, 16]

        // Native events, metadata, harness controls and flushed kp.print output.
        api::compat::install(L, game_dir);
    };

    // The console builds a state of its own and needs the same API on it.
    set_state_init(hc.on_state_created);
#if defined(__i386__)
    hc.on_state_closing = hooks::lua_bridge::close_state;
#endif

    // Which routine table nwscript.call binds to. The choice latches the first time
    // a state registers the API, which load_all is about to do, so it has to
    // be made here from the table's own game field ("K1" / "K2"). Without
    // this a K2 process silently got the K1 routine ids.
    if (table_ != nullptr) {
        const std::string& g = table_->game();
        const api::Game game = (g == "K2" || g == "k2") ? api::Game::K2 : api::Game::K1;
        if (!api::select_game(game))
            log("api: could not select the %s routine table; it was already handed out",
                game == api::Game::K2 ? "K2" : "K1");
    }

    host_ = std::make_unique<lua::Host>(hc);
    // Publish the host services before load_all: top-level scripts may call
    // kp.scripts during their initial execution, and those calls must see the
    // same host that owns the state. Failed starts clear these bindings before
    // destroying host_.
    api::scripts::bind_host(host_.get());
    api::motion::bind_owner_probe(motion_owner, nullptr);
    api::motion::bind_tick(motion_tick, nullptr);
    std::vector<std::string> errors;
    const unsigned loaded = host_->load_all(errors);
    for (const std::string& e : errors) log("script: %s", e.c_str());
    log("loaded %u script(s) from %s", loaded, cfg.script_dir.c_str());

    // Publish, host pointer first. Every hook body reads the live flag before
    // it reads the host, so until the second store lands the bodies forward
    // straight to the original and the game runs exactly as it would without us.
    phase_ = Phase::Running;
    set_active_host(host_.get());
    set_live(true);

    if (const events::EventContract* ev = find_contract("OnScriptLoad"); ev != nullptr) {
        const std::vector<lua::Value> args = {
            lua::Value::str(table_ ? table_->game() : std::string()),
            lua::Value::str(build_),
        };
        host_->dispatch(*ev, args);
    }
    host_->set_lifecycle(find_contract("OnScriptLoad"),
                         find_contract("OnScriptUnload"),
                         table_ ? table_->game() : std::string(),
                         build_);
    return true;
}

bool Runtime::start(const Config& cfg) {
    // This is a worker/quiescent transition.  It is deliberately outside
    // DllMain and loader-lock callbacks; no engine thread has been latched yet.
    reset_engine_thread();
    api::engine::bind_gate(engine_gate_probe, nullptr);
    log_path_ = cfg.log_path;
    role_ = cfg.role;
    set_fault_log_path(log_path_.c_str());
    platform::set_log_sink(&runtime_log_sink, nullptr);

    log("KotorJIT %s starting (%s role)", KP_VERSION, multiplayer::to_string(role_));
    if (const std::string dd = data_dir_of(cfg);
        dd.size() >= std::strlen(naming::kLegacyDataDir) &&
        dd.compare(dd.size() - std::strlen(naming::kLegacyDataDir), std::string::npos, naming::kLegacyDataDir) == 0)
        log("note: using the legacy data folder %s (KotorPhasor was renamed to KotorJIT); "
            "renaming it to '%s' is optional and changes nothing else", dd.c_str(), naming::kDataDir);

    // Before anything can fault: the guard has to be in place before the first
    // hook body can run, and installing it is free when nothing faults.
    install_fault_guard();

    const bool ok = identify(cfg) && await_and_verify(cfg) && resolve(cfg) &&
                    start_multiplayer(cfg) && install(transport_ != nullptr) &&
                    boot_scripts(cfg);

    if (!ok) {
        phase_ = Phase::Failed;
        set_live(false);
        set_active_host(nullptr);
        set_active_multiplayer_transport(nullptr);
        if (transport_) transport_->stop();
        log("refusing to install: %s", failure_.c_str());
        log("the game is untouched and will run normally");
        // Anything installed before the failure was rolled back by HookSet, so
        // there is nothing here to undo. Dropping what we built keeps a failed
        // start from leaving a half-initialised runtime addressable.
        if (hooks_) clear_originals();
        hooks_.reset();
#if defined(__i386__)
        hooks::lua_bridge::shutdown();
#endif
        table_.reset();
        if (host_) host_->unload_all();
        api::scripts::bind_host(nullptr);
        api::motion::bind_owner_probe(nullptr, nullptr);
        api::motion::bind_tick(nullptr, nullptr);
        api::motion::operations().unbind();
        api::engine::bind_gate(nullptr, nullptr);
        reset_engine_thread();
        host_.reset();
    api::animation::operations().unbind();
    api::projectiles::unbind_native();
    api::model::operations().unbind();
    api::camera::operations().unbind();
        transport_.reset();
        remove_fault_guard();
        return false;
    }

    // Callbacks this build of the runtime raises that the generated table does
    // not carry. Logged rather than asserted: the table is data, and a missing
    // entry is a data change, not a code bug. Without this line the absence is
    // invisible from inside the game.
    for (const char* wanted : {"OnRunScriptDone", "OnConsoleCommand"}) {
        if (find_contract(wanted) == nullptr)
            log("note: event \"%s\" is not in the generated contract table, so no script "
                "can receive it", wanted);
    }

    log("running: build %s, %zu hooks, %zu script(s)", build_.c_str(),
        hooks_->installed_count(), host_->scripts().size());

    // The harness listener, last: everything a command can touch now exists.
    // A refused or failed start is logged and the game runs without it --
    // the harness is a test surface, never a reason to refuse the player.
    if (cfg.harness_port != 0) {
        kp::harness::HarnessOptions ho;
        ho.bind = cfg.harness_bind;
        ho.port = static_cast<unsigned short>(cfg.harness_port);
        std::string error;
        if (kp::harness::start(ho, error)) {
            log("harness: listening on %s:%u", cfg.harness_bind.c_str(),
                static_cast<unsigned>(kp::harness::listening_port()));
        } else {
            log("harness: not started: %s", error.c_str());
        }
    }
    return true;
}

void Runtime::stop() {
    kp::devtools::overlay_shutdown();
    // The listener first: it was started last, and once it is gone no new
    // request can reach a drain that is about to lose its host and hooks.
    kp::harness::stop();

    // Order matters and is the reverse of start(). Stop dispatching first, drop
    // the cached trampoline pointers second, and only then unpatch -- uninstall
    // unmaps the trampolines, so a body still holding one would fault.
    set_live(false);
    set_active_multiplayer_transport(nullptr);
    if (transport_) transport_->stop();

    // Host::unload_all raises OnScriptUnload per script. Do not also
    // broadcast here -- that would fire the callback twice on shutdown.
    set_active_host(nullptr);
    clear_originals();

    // Not safe against a thread executing inside a patched prologue. The
    // trampoline header says so and this cannot check it; stop() belongs at a
    // quiescent point, which in practice means process shutdown.
    if (hooks_) hooks_->uninstall();
#if defined(__i386__)
    hooks::lua_bridge::shutdown();
#endif

    // Run unload callbacks while the host service is still bound.  The
    // callbacks may inspect kp.scripts; after unload_all the host is empty and
    // the service can be withdrawn before destruction.
    if (host_) host_->unload_all();
    api::scripts::bind_host(nullptr);
    api::motion::bind_owner_probe(nullptr, nullptr);
    api::motion::bind_tick(nullptr, nullptr);
    api::motion::operations().unbind();
    api::engine::bind_gate(nullptr, nullptr);
    reset_engine_thread();
    host_.reset();
    api::animation::operations().unbind();
    api::projectiles::unbind_native();
    api::model::operations().unbind();
    api::camera::operations().unbind();
    hooks_.reset();
    table_.reset();
    transport_.reset();
    set_vm_sites({});
    remove_fault_guard();

    phase_ = Phase::Idle;
    log("stopped");
}

}  // namespace kp::runtime

// ------------------------------------------------------ binding the VM ------

namespace kp::runtime {

namespace {

api::VmSites      g_sites;
std::atomic<bool> g_vm_bound{false};

// The live singleton is not needed: stack accessors only read the per-build
// internal-pointer field from the CVirtualMachine wrapper.
std::array<std::byte, 64> g_vm_wrapper{};

}  // namespace

void set_vm_sites(const api::VmSites& s) {
    g_vm_bound.store(false, std::memory_order_release);
    api::bind({});
    api::bind_engine_access({});
    g_vm_wrapper.fill(std::byte{});
    g_sites = s;
}
bool vm_bound() { return g_vm_bound.load(std::memory_order_acquire); }

void capture_vm(void* internal) {
    if (api::vm_binding_live()) return;
    const void* old_internal = api::binding().virtual_machine == nullptr
        ? nullptr
        : *reinterpret_cast<void* const*>(g_vm_wrapper.data() +
                                          g_sites.wrapper_internal_offset);
    const void* old_implementer = api::binding().command_implementer;
    const void* old_table = api::engine_access().commands;
    g_vm_bound.store(false, std::memory_order_release);
    api::bind({});
    api::bind_engine_access({});
    g_vm_wrapper.fill(std::byte{});
    if (internal == nullptr) return;

    if (!g_sites.layout_resolved ||
        g_sites.wrapper_internal_offset > g_vm_wrapper.size() - sizeof(void*) ||
        !platform::is_readable(internal,
                               g_sites.command_implementer_offset + sizeof(void*))) return;
    void* implementer = *reinterpret_cast<void* const*>(
        static_cast<const char*>(internal) + g_sites.command_implementer_offset);
    if (implementer == nullptr) return;   // not wired up yet; try again next script

    std::memcpy(g_vm_wrapper.data() + g_sites.wrapper_internal_offset,
                &internal, sizeof(internal));
    g_sites.virtual_machine     = g_vm_wrapper.data();
    g_sites.command_implementer = implementer;

    std::string error;
    if (!api::bind_sites(g_sites, error)) {
        g_vm_wrapper.fill(std::byte{});
        // Initialization and teardown can temporarily expose no command table.
        // Leave the context unavailable so a later trusted script retries.
        return;
    }
    g_vm_bound.store(true, std::memory_order_release);
    Runtime::instance().log("vm: routine bridge refreshed (internal %p -> %p, implementer %p -> %p, table %p -> %p, %u commands)",
        old_internal, internal, old_implementer, implementer,
        old_table, api::engine_access().commands, api::engine_access().command_count);
}

}  // namespace kp::runtime

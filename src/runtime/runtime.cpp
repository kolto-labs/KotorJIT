// The five phases, in the order runtime.hpp declares them.
//
// Every phase either advances or fails, and a failure leaves the game exactly
// as it was found. There is no partial success anywhere in this file: the hook
// set installs atomically, and the phases before it write nothing at all.
#include "runtime/runtime.hpp"

#include <atomic>
#include <cctype>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include "events/contract.hpp"
#include "hooks/registry.hpp"
#include "image/image.hpp"
#include "image/sha256.hpp"
#include "api/enginestruct.hpp"
#include "api/routines.hpp"
#include "lua/host.hpp"
#include "lua/value.hpp"
#include "platform/platform.hpp"
#include "runtime/internal.hpp"

#if defined(_WIN32)
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#else
#include <unistd.h>
#endif

namespace kp::runtime {
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

lua::Host* active_host() { return g_host.load(std::memory_order_acquire); }
void set_active_host(lua::Host* h) { g_host.store(h, std::memory_order_release); }

std::string directory_of(const std::string& path) {
    const std::size_t cut = path.find_last_of("/\\");
    return cut == std::string::npos ? std::string(".") : path.substr(0, cut);
}

std::string self_module_path() {
#if defined(_WIN32)
    char buf[MAX_PATH] = {0};
    const DWORD n = GetModuleFileNameA(nullptr, buf, sizeof buf);
    return n > 0 ? std::string(buf, n) : std::string();
#else
    char buf[4096] = {0};
    const ssize_t n = ::readlink("/proc/self/exe", buf, sizeof buf - 1);
    return n > 0 ? std::string(buf, static_cast<std::size_t>(n)) : std::string();
#endif
}

const std::vector<events::EventContract>& event_table() {
    using events::ValueType;
    using events::Fallback;
    using events::EngineReturn;
    static const std::vector<events::EventContract> kEvents = {
#include "generated/events.inc"
    };
    return kEvents;
}

const events::EventContract* find_contract(std::string_view lua_name) {
    for (const auto& ev : event_table())
        if (ev.lua_name == lua_name) return &ev;
    return nullptr;
}

// ---------------------------------------------------------------- Config ----

Config Config::from_game_dir(const std::string& game_dir) {
    Config c;
    c.game_dir = game_dir;
    c.script_dir = join(join(game_dir, "kotorphasor"), "scripts");
    c.log_path = join(game_dir, "kotorphasor.log");

    std::FILE* f = std::fopen(join(game_dir, "kotorphasor.ini").c_str(), "rb");
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
    }
    std::fclose(f);
    return c;
}

// --------------------------------------------------------------- Runtime ----

Runtime& Runtime::instance() {
    static Runtime r;
    return r;
}

void Runtime::log(const char* fmt, ...) {
    char body[1024];
    va_list ap;
    va_start(ap, fmt);
    std::vsnprintf(body, sizeof body, fmt, ap);
    va_end(ap);

    while (g_log_lock.test_and_set(std::memory_order_acquire)) {}
    std::FILE* f = std::fopen(log_path_.empty() ? "kotorphasor.log" : log_path_.c_str(), "ab");
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
    runtime_base_ = r.image_base;

    log("build: %s (image base 0x%08lx, waited %ums)", build_.c_str(),
        static_cast<unsigned long>(runtime_base_), r.waited_ms);
    log("code section verified: %s", r.text_sha256.c_str());
    for (const image::Section& s : r.sections) {
        if (!s.executable) continue;
        log("  section %s va=0x%08lx size=%lu entropy=%.3f state=%s", s.name.c_str(),
            static_cast<unsigned long>(s.va), static_cast<unsigned long>(s.size), s.entropy,
            s.state == image::SectionState::Ciphertext  ? "ciphertext"
            : s.state == image::SectionState::Deciphered ? "deciphered"
                                                         : "plaintext");
    }
    return true;
}

bool Runtime::resolve(const Config& cfg) {
    phase_ = Phase::Resolving;

    if (build_.empty()) {
        failure_ = "no build alias, so no address table to load";
        return false;
    }

    // Where a player's install would carry it, then where a working tree does.
    // The env var is last and exists for driving the runtime out of a build
    // directory without staging files next to the game.
    std::vector<std::string> candidates;
    candidates.push_back(join(join(join(cfg.game_dir, "kotorphasor"), "addresses"), build_ + ".json"));
    candidates.push_back(join(join(cfg.game_dir, "kotorphasor"), build_ + ".json"));
    if (const char* dir = std::getenv("KOTORPHASOR_ADDRESSES"); dir != nullptr && *dir != '\0')
        candidates.push_back(join(dir, build_ + ".json"));

    std::string chosen;
    for (const std::string& p : candidates) {
        if (file_exists(p)) { chosen = p; break; }
    }
    if (chosen.empty()) {
        failure_ = "no address table for build \"" + build_ + "\"; looked in";
        for (const std::string& p : candidates) failure_ += " " + p;
        return false;
    }

    auto table = std::make_unique<hooks::AddressTable>();
    std::string error;
    if (!hooks::AddressTable::load_file(chosen, *table, error)) {
        failure_ = "address table " + chosen + ": " + error;
        return false;
    }

    const std::vector<std::string> missing = table->unresolved_required();
    if (!missing.empty()) {
        failure_ = "address table " + chosen + " leaves required sites unresolved:";
        for (const std::string& m : missing) failure_ += " " + m;
        return false;
    }

    table_ = std::move(table);
    log("address table: %s (%zu sites, build %s, %s)", chosen.c_str(), table_->sites().size(),
        table_->build().c_str(), table_->platform_name().c_str());
    return true;
}

bool Runtime::install() {
    phase_ = Phase::Installing;

    if (!table_) { failure_ = "install called with no address table"; return false; }

    // `expect` is left empty on purpose. The address table carries the bytes
    // the generator read out of a plaintext reference image, and the registry
    // prefers those -- they are wider than a pattern typed here and they cannot
    // drift away from the table they came from.
    auto set = std::make_unique<hooks::HookSet>();
    set->add({"vm.run_script", run_script_detour(), {}});
    set->add({"app.server_main_loop", main_loop_detour(), {}});
    set->add({"console.do_console", do_console_detour(), {}});

    std::string error;
    if (!set->install(*table_, runtime_base_, error)) {
        failure_ = "hook install: " + error;
        return false;
    }

    hooks_ = std::move(set);
    bind_originals(*hooks_);
    log("installed %zu hooks", hooks_->installed_count());

    // The routine bridge's addresses come straight from the table we just
    // resolved. Doing it here means a missing site is reported while someone is
    // reading the install log, not on the first script the game happens to run.
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
        set_vm_sites(sites);
        log("vm: %d of 13 stack sites resolved; the two VM objects are captured "
            "from the first script the game runs",
            (sites.execute_command ? 1 : 0) + (sites.stack_push_integer ? 1 : 0) +
            (sites.stack_pop_integer ? 1 : 0) + (sites.stack_push_float ? 1 : 0) +
            (sites.stack_pop_float ? 1 : 0) + (sites.stack_push_string ? 1 : 0) +
            (sites.stack_pop_string ? 1 : 0) + (sites.stack_push_object ? 1 : 0) +
            (sites.stack_pop_object ? 1 : 0) + (sites.stack_push_vector ? 1 : 0) +
            (sites.stack_pop_vector ? 1 : 0) +
            (sites.stack_push_engine_structure ? 1 : 0) +
            (sites.stack_pop_engine_structure ? 1 : 0));
    }
    return true;
}

bool Runtime::boot_scripts(const Config& cfg) {
    lua::HostConfig hc;
    hc.script_dir = cfg.script_dir;
    hc.error_budget = cfg.error_budget;
    hc.hot_reload = cfg.hot_reload;

    // Everything a script can call is registered here, on each fresh state.
    // The Lua host takes this as a hook precisely so it does not have to know
    // what a KOTOR routine is -- see the note on HostConfig.
    hc.on_state_created = [](lua_State* L) {
        api::register_all(L);          // kotor.<RoutineName> for every routine
        api::open_engine_structs(L);   // effect/event/location/talent handles
    };

    auto host = std::make_unique<lua::Host>(hc);
    std::vector<std::string> errors;
    const unsigned loaded = host->load_all(errors);
    for (const std::string& e : errors) log("script: %s", e.c_str());
    log("loaded %u script(s) from %s", loaded, cfg.script_dir.c_str());

    host_ = std::move(host);

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
    return true;
}

bool Runtime::start(const Config& cfg) {
    log_path_ = cfg.log_path;
    set_fault_log_path(log_path_.c_str());
    platform::set_log_sink(&runtime_log_sink, nullptr);

    log("KotorPhasor starting");

    // Before anything can fault: the guard has to be in place before the first
    // hook body can run, and installing it is free when nothing faults.
    install_fault_guard();

    const bool ok = identify(cfg) && await_and_verify(cfg) && resolve(cfg) && install() &&
                    boot_scripts(cfg);

    if (!ok) {
        phase_ = Phase::Failed;
        set_live(false);
        set_active_host(nullptr);
        log("refusing to install: %s", failure_.c_str());
        log("the game is untouched and will run normally");
        // Anything installed before the failure was rolled back by HookSet, so
        // there is nothing here to undo. Dropping what we built keeps a failed
        // start from leaving a half-initialised runtime addressable.
        hooks_.reset();
        table_.reset();
        host_.reset();
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
    return true;
}

void Runtime::stop() {
    // Order matters and is the reverse of start(). Stop dispatching first, drop
    // the cached trampoline pointers second, and only then unpatch -- uninstall
    // unmaps the trampolines, so a body still holding one would fault.
    set_live(false);

    if (host_) {
        if (const events::EventContract* ev = find_contract("OnScriptUnload"); ev != nullptr)
            host_->dispatch(*ev, {});
    }

    set_active_host(nullptr);
    clear_originals();

    // Not safe against a thread executing inside a patched prologue. The
    // trampoline header says so and this cannot check it; stop() belongs at a
    // quiescent point, which in practice means process shutdown.
    if (hooks_) hooks_->uninstall();

    host_.reset();
    hooks_.reset();
    table_.reset();
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

// CVirtualMachineInternal is size-asserted at 0x3D8 and command_implementer is
// its last member, so it sits at 0x3D4. Carried as a constant here rather than
// in the address table because it is a struct layout, not an address -- a build
// where it moves needs a different recovered layout, not a different table.
constexpr std::uint32_t kCommandImplementerOffset = 0x3D4;

// A CVirtualMachine is one pointer to its internal. The stack accessors are
// thunks that do `mov ecx,[ecx]` and tail-jump into the internal version --
// confirmed by disassembling K1's StackPopInteger at 0x5D1000. So rather than
// hunting for the real singleton, we hold the internal in a variable and hand
// out its address: dereferencing that gives exactly what the thunk wants.
void* g_vm_wrapper = nullptr;

}  // namespace

void set_vm_sites(const api::VmSites& s) { g_sites = s; }
bool vm_bound() { return g_vm_bound.load(std::memory_order_acquire); }

void capture_vm(void* internal) {
    if (g_vm_bound.load(std::memory_order_acquire) || internal == nullptr) return;

    if (!platform::is_readable(internal, kCommandImplementerOffset + sizeof(void*))) return;
    void* implementer = *reinterpret_cast<void* const*>(
        static_cast<const char*>(internal) + kCommandImplementerOffset);
    if (implementer == nullptr) return;   // not wired up yet; try again next script

    g_vm_wrapper = internal;
    g_sites.virtual_machine     = &g_vm_wrapper;
    g_sites.command_implementer = implementer;

    std::string error;
    if (!api::bind_sites(g_sites, error)) {
        Runtime::instance().log("vm: cannot bind the routine bridge: %s", error.c_str());
        // Latch anyway. Retrying on every script would repeat this line forever,
        // and the reason will not change between calls.
        g_vm_bound.store(true, std::memory_order_release);
        return;
    }
    g_vm_bound.store(true, std::memory_order_release);
    Runtime::instance().log("vm: routine bridge bound (implementer %p, %u commands)",
                            implementer, g_sites.commands_count);
}

}  // namespace kp::runtime

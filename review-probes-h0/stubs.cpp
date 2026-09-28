// Link stubs for the real src/harness/commands.cpp. Anything the devtools /
// drain path must never reach aborts loudly with its name.
#include <atomic>
#include <condition_variable>
#include <csetjmp>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <mutex>
#include <new>
#include <string>
#include <vector>

#include "api/output.hpp"
#include "devtools/console.hpp"
#include "harness/engine.hpp"
#include "lua/host.hpp"
#include "platform/platform.hpp"
#include "runtime/internal.hpp"
#include "runtime/runtime.hpp"

#include "stubs.hpp"

#define LOUD(name)                                                  \
    do {                                                            \
        std::fprintf(stderr, "STUB REACHED (must not): %s\n", name); \
        std::abort();                                               \
    } while (0)

namespace probe {
std::atomic<int> submit_plain{0};
std::atomic<int> submit_session{0};
std::function<void()> on_submit;
std::atomic<int> connected{0};
std::atomic<int> disconnected{0};
std::atomic<int> doomed_logs{0};
std::atomic<bool> park_enabled{false};
std::atomic<bool> parked{false};
std::mutex park_mu;
std::condition_variable park_cv;
bool park_release = false;
bool verbose = false;

void release_park() {
    std::lock_guard<std::mutex> l(park_mu);
    park_release = true;
    park_cv.notify_all();
}
void arm_park() {
    std::lock_guard<std::mutex> l(park_mu);
    park_release = false;
    parked.store(false);
    park_enabled.store(true);
}
}  // namespace probe

// ---------------------------------------------------------------- platform
namespace kp::platform {
void log(LogLevel, const char* fmt, ...) {
    char buf[512];
    va_list ap;
    va_start(ap, fmt);
    std::vsnprintf(buf, sizeof buf, fmt, ap);
    va_end(ap);
    if (probe::verbose) std::fprintf(stderr, "  [log] %s\n", buf);
    if (std::strstr(buf, "client connected")) probe::connected.fetch_add(1);
    if (std::strstr(buf, "client disconnected")) probe::disconnected.fetch_add(1);
    if (std::strstr(buf, "not a JSON request")) {
        probe::doomed_logs.fetch_add(1);
        // Park the listener between "sent the error" and close_client(): the
        // connection is still current, condemned_gen_ == gen, and anything
        // not yet taken is still queued. Only admit() stands in the way.
        if (probe::park_enabled.load()) {
            std::unique_lock<std::mutex> l(probe::park_mu);
            probe::parked.store(true);
            probe::park_cv.wait(l, [] { return probe::park_release; });
            probe::park_enabled.store(false);
        }
    }
}
}  // namespace kp::platform

// ---------------------------------------------------------------- devtools
namespace kp::devtools {
Console::Console() {}
Console::~Console() {}
Request Console::submit(std::string) {
    probe::submit_plain.fetch_add(1);
    if (probe::on_submit) probe::on_submit();
    return static_cast<Request>(probe::submit_plain.load() + probe::submit_session.load());
}
Submission Console::submit(Session s, std::string) {
    probe::submit_session.fetch_add(1);
    if (probe::on_submit) probe::on_submit();
    Submission r;
    r.session = s;
    r.request = static_cast<Request>(probe::submit_plain.load() + probe::submit_session.load());
    return r;
}
Status Console::status() {
    Status s{};
    s.submitted = static_cast<Request>(probe::submit_plain.load() + probe::submit_session.load());
    s.session = 1;
    return s;
}
OutcomeLookup Console::outcome(Session, Request) { return {}; }
OutputSnapshot Console::snapshot(Session, std::uint64_t) { return {}; }
std::vector<Line> Console::snapshot() { return {}; }
Cancellation Console::cancel(Session, Request) { return Cancellation::Unavailable; }
void Console::cancel() {}
std::vector<std::string> Console::complete(const std::string&) { return {}; }
Console& console() {
    static Console c;
    return c;
}
bool overlay_open() { return false; }
unsigned long overlay_input_calls() { return 0; }
}  // namespace kp::devtools

// ---------------------------------------------------------------- harness / api / lua
namespace kp::harness {
Result Result::success() { return Result{true, {}}; }
}  // namespace kp::harness
namespace kp::api {
void push_kp_table(lua_State*) { LOUD("api::push_kp_table"); }
}  // namespace kp::api
namespace kp::lua {
unsigned Host::load_all(std::vector<std::string>&) { LOUD("lua::Host::load_all"); }
}  // namespace kp::lua

// ---------------------------------------------------------------- runtime
namespace kp::runtime {
namespace {
thread_local jmp_buf g_jb;
}
FaultFrame::FaultFrame(const char* site, std::atomic<bool>* poison)
    : site_(site), poison_(poison), slot_(0) {}
FaultFrame::~FaultFrame() {}
void* FaultFrame::buf() { return &g_jb; }
void FaultFrame::note_fault() { LOUD("FaultFrame::note_fault"); }
lua::Host* active_host() { LOUD("runtime::active_host"); }
void enter_hook_body() {}
void leave_hook_body() {}
void init_lua_state(lua_State*) { LOUD("runtime::init_lua_state"); }
bool live() { return false; }
void set_live(bool) { LOUD("runtime::set_live"); }
bool vm_bound() { return false; }
std::vector<std::string> poisoned_sites() { return {}; }
const char* to_string(Phase) { return "Idle"; }
alignas(Runtime) static unsigned char g_rt_storage[sizeof(Runtime)];
Runtime& Runtime::instance() { return *reinterpret_cast<Runtime*>(g_rt_storage); }
void Runtime::log(const char*, ...) {}
}  // namespace kp::runtime

// ---------------------------------------------------------------- lua C API
extern "C" {
#define LUA_STUB(ret, name, ...) \
    ret name(__VA_ARGS__) { LOUD(#name); }
struct lua_State;
LUA_STUB(void, lua_close, lua_State*)
LUA_STUB(int, lua_gettop, lua_State*)
LUA_STUB(int, luaL_loadbuffer, lua_State*, const char*, unsigned, const char*)
LUA_STUB(lua_State*, luaL_newstate, void)
LUA_STUB(void, luaL_openlibs, lua_State*)
LUA_STUB(int, lua_next, lua_State*, int)
LUA_STUB(unsigned, lua_objlen, lua_State*, int)
LUA_STUB(int, lua_pcall, lua_State*, int, int, int)
LUA_STUB(void, lua_pushcclosure, lua_State*, void*, int)
LUA_STUB(void, lua_pushnil, lua_State*)
LUA_STUB(void, lua_rawgeti, lua_State*, int, int)
LUA_STUB(void, lua_setfield, lua_State*, int, const char*)
LUA_STUB(void, lua_settop, lua_State*, int)
LUA_STUB(int, lua_toboolean, lua_State*, int)
LUA_STUB(const char*, lua_tolstring, lua_State*, int, unsigned*)
LUA_STUB(double, lua_tonumber, lua_State*, int)
LUA_STUB(const void*, lua_topointer, lua_State*, int)
LUA_STUB(int, lua_type, lua_State*, int)
LUA_STUB(const char*, lua_typename, lua_State*, int)
}

// Exercises src/runtime/fault_guard.cpp against a real hardware fault in this
// tool's own process.
//
// Nothing in the repository drives FaultFrame/KP_HOOK_GUARD/install_fault_guard
// with an actual SIGSEGV before this file: a search across every test and
// harness script turns up zero references to any of the three. The mechanism
// is exercised only by the game crashing for real, which is a slow and
// ambiguous way to find out whether the recovery it is supposed to provide
// actually works. This tool triggers a genuine access violation inside a real
// guarded region and checks what the guard actually did, not what the header
// comments say it should do.
//
// What is demonstrated, in order:
//
//   1. a fault inside a guarded hook body is caught: the fallback statement
//      runs, that site's poison flag is set, and the whole runtime's live()
//      flag flips false -- not "that one routine", the whole runtime. This is
//      the corrected understanding from docs/ideation/2026-08-31-kotorphasor-
//      ideation.html's idea 1: the poison flag is per site, but the recovery
//      it enables is global.
//   2. poison does not lift when live() is manually restored (the `lua
//      reload` case): the site stays permanently poisoned, a second site
//      stays clean, proving the granularity really is per site even though
//      the safety stop is not.
//   3. the negative case, which is the half most likely to regress silently:
//      a fault with NO FaultFrame armed (depth 0, "the game's business") is
//      NOT claimed and the process dies exactly as it would have without this
//      file existing. Proven with a real child process, not a description.
//
// This tool links the real src/runtime/fault_guard.cpp unmodified. What it
// does NOT link is runtime.cpp, because fault_guard.cpp's only external call
// is Runtime::instance().log(...) plus the free functions live()/set_live(),
// and runtime.cpp's Runtime::start() transitively needs the Lua host, the
// hook set, and the image parser just to compile -- none of which a fault-
// recovery test has anything to do with. The stub below supplies exactly
// those two things and nothing else.
//
// Linux and 32-bit only: fault_guard.cpp's non-Windows path reads
// uc_mcontext.gregs[REG_EIP], which is an i386 ucontext layout.
//
// Build (from the repo root):
//   g++ -m32 -std=c++20 -O0 -g -Isrc \
//       tools/kp_faulttest.cpp src/runtime/fault_guard.cpp \
//       -o build/kp_faulttest
//
// Verified at -O2 too: the store through `bad` is `volatile`, which is what
// actually keeps it from being proven unreachable and deleted. -O0 here is
// just for a readable stack when something needs a debugger, not a
// requirement for the fault to fire.

#include <atomic>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <csignal>

#include <sys/wait.h>
#include <unistd.h>

// Runtime's three unique_ptr members are only ever forward-declared in
// runtime.hpp -- but Runtime()'s implicitly-defined default constructor still
// needs each member type COMPLETE, to know how to unwind already-constructed
// members if a later one's constructor threw. That is true even though this
// file never destroys a Runtime and none of these constructors can actually
// throw; the compiler cannot know that. Empty placeholders, defined before
// runtime.hpp's forward declarations of the same names, satisfy that without
// pulling in the real Host/AddressTable/HookSet and everything they need.
namespace kp::hooks { class AddressTable {}; class HookSet {}; }
namespace kp::lua { class Host {}; }

#include "runtime/internal.hpp"
#include "runtime/runtime.hpp"

// --------------------------------------------------------- runtime stub -----
//
// Not a mock of the real behaviour -- log() really does print, and
// live()/set_live() really do hold the flag fault_guard.cpp reads and writes.
// The only thing faked is that Runtime::instance() never lets its Runtime
// destruct, so this file never has to prove AddressTable/HookSet/Host are
// complete types it has no other reason to include.
namespace kp::runtime {

namespace {
std::atomic<bool> g_live_stub{false};
}  // namespace

bool live() { return g_live_stub.load(std::memory_order_acquire); }
void set_live(bool v) { g_live_stub.store(v, std::memory_order_release); }

Runtime& Runtime::instance() {
    static Runtime* r = new Runtime();  // leaked on purpose; see header note
    return *r;
}

void Runtime::log(const char* fmt, ...) {
    std::va_list ap;
    va_start(ap, fmt);
    std::vprintf(fmt, ap);
    va_end(ap);
    std::printf("\n");
}

}  // namespace kp::runtime

namespace {

int g_failures = 0;

void check(bool ok, const char* what) {
    std::printf("  [%s] %s\n", ok ? "PASS" : "FAIL", what);
    if (!ok) ++g_failures;
}

void section(const char* title) {
    std::printf("\n== %s ==\n", title);
}

// ---------------------------------------------------------------------------
// Scenario A + B: two distinct sites, one guarded region faults for real.
// ---------------------------------------------------------------------------

std::atomic<bool> g_poison_site1{false};
std::atomic<bool> g_poison_site2{false};
bool g_fallback_ran = false;

void fault_in_site1() {
    volatile int* bad = nullptr;
    KP_HOOK_GUARD_BEGIN("test.site1", g_poison_site1, g_fallback_ran = true)
        *bad = 42;  // a real access violation, not a simulated one
    KP_HOOK_GUARD_END
}

void run_in_process_scenarios() {
    section("A: a fault inside a guarded region is caught");

    kp::runtime::set_live(true);
    g_fallback_ran = false;
    check(kp::runtime::in_hook_body() == false, "not inside a hook body before the guard");

    fault_in_site1();

    check(g_fallback_ran, "fallback statement ran after the fault");
    check(g_poison_site1.load(), "site1's poison flag was set");
    check(!kp::runtime::live(), "live() flipped false -- the WHOLE runtime, not just site1");
    check(kp::runtime::in_hook_body() == false, "depth unwound correctly after the fault path");

    section("B: poison is per-site; the safety stop is not");

    check(!g_poison_site2.load(), "site2 is untouched by site1's fault");

    // The `lua reload` case: live() comes back, poison does not.
    kp::runtime::set_live(true);
    check(kp::runtime::live(), "live() can be restored (what `lua reload` does)");
    check(g_poison_site1.load(), "site1 stays poisoned after live() is restored -- permanent");

    // The caller-side convention every real hook body follows (see
    // hook_bodies.cpp's event_handler_common): check poison BEFORE entering
    // the guard again, so a known-bad site is never re-armed.
    bool would_skip = g_poison_site1.load(std::memory_order_acquire);
    check(would_skip, "a caller checking poison first would skip re-running site1");

    // And a clean site keeps working after another site's fault and after a
    // reload -- this is the actual, correct meaning of "per site": which
    // sites get re-armed on the NEXT reload, not concurrent isolation.
    bool site2_ran = false;
    KP_HOOK_GUARD_BEGIN("test.site2", g_poison_site2, site2_ran = false)
        site2_ran = true;  // no fault here
    KP_HOOK_GUARD_END
    check(site2_ran, "site2 runs normally: it was never poisoned");
    check(!g_poison_site2.load(), "site2 still has no poison of its own");
}

// ---------------------------------------------------------------------------
// Scenario C: the negative case. A fault with NO FaultFrame armed must NOT be
// claimed -- "a fault in the game's code is the game's business" -- and the
// process must die exactly as it would without this file existing.
// ---------------------------------------------------------------------------

bool unguarded_fault_is_fatal() {
    const pid_t pid = fork();
    if (pid < 0) {
        std::perror("fork");
        return false;
    }
    if (pid == 0) {
        // Child: install the real guard, same as the game process would, then
        // fault with no FaultFrame anywhere on the stack (depth == 0).
        kp::runtime::install_fault_guard();
        volatile int* bad = nullptr;
        *bad = 7;
        // Unreachable if claim() correctly refused at depth 0.
        std::_Exit(66);
    }

    int status = 0;
    if (waitpid(pid, &status, 0) != pid) {
        std::perror("waitpid");
        return false;
    }
    if (!WIFSIGNALED(status)) {
        std::printf("    child did not die by signal (status=0x%x)\n", status);
        return false;
    }
    const int sig = WTERMSIG(status);
    std::printf("    child died by signal %d (%s)\n", sig,
                sig == SIGSEGV ? "SIGSEGV, expected" : "unexpected");
    return sig == SIGSEGV;
}

}  // namespace

int main() {
    std::printf("kp_faulttest: src/runtime/fault_guard.cpp against a real fault\n");

    kp::runtime::install_fault_guard();
    run_in_process_scenarios();

    section("C: an unguarded fault is NOT claimed, and kills the process");
    check(unguarded_fault_is_fatal(),
          "a fault at hook-body depth 0 passes through and is fatal, as documented");

    std::printf("\n%d failure(s)\n", g_failures);
    return g_failures == 0 ? 0 : 1;
}

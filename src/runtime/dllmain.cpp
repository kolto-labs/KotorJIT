// Entry point, and the reason it does almost nothing.
//
// DllMain runs holding the loader lock. Everything the runtime needs to do is
// forbidden there: LoadLibrary deadlocks against the lock we are already
// holding, LuaJIT's initialisation allocates and can pull in a DLL, waiting on
// a thread deadlocks against a thread that cannot start until we return, and
// the game's own imports are not all resolved yet. So the entry point starts a
// worker and returns, and the worker does the work.
//
// The deferral is not only a loader-lock question. On the primary target the
// game's code section is still ciphertext at this point -- reading an address
// here would read noise, and installing a hook here would corrupt the wrapper's
// output. image/ owns the wait; this file just makes sure it happens somewhere
// a wait is legal.
//
// The Linux ELF target has no DllMain, so it gets a constructor that starts the
// same worker. One runtime, two entry points, and nothing platform-specific
// past this file.
#include <string>

#include "runtime/internal.hpp"
#include "platform/naming.hpp"
#include "runtime/runtime.hpp"

#if defined(_WIN32)
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#else
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <pthread.h>
#include <unistd.h>
#endif

namespace {

// One runtime per process, however many copies of this module get loaded.
// The proxy, the launcher's injection, KPM's DLL-only patch, DT_NEEDED and
// LD_PRELOAD can each bring the runtime in, and two of them can be set up at
// once with different files (a game-folder scriptforge.dll and KPM's extracted
// windows_x86.dll). Each copy would otherwise start its own runtime and hook
// every site a second time. The first copy to reach its entry point claims the
// process; a later copy stays loaded and inert. Claimed from the entry point,
// which the loader runs one module at a time, so two copies cannot both win.
// tools/kp_singleinstance_test.cpp.
bool claim_process() {
#if defined(_WIN32)
    char name[64];
    wsprintfA(name, "Local\\scriptforge-runtime-%lu", GetCurrentProcessId());
    // Deliberately never closed: the claim lasts as long as the process.
    HANDLE m = CreateMutexA(nullptr, FALSE, name);
    return m != nullptr && GetLastError() != ERROR_ALREADY_EXISTS;
#else
    // The environment is one per process and shared by every copy loaded in
    // it. The value is the pid, so a claim inherited from a parent process
    // (which also hosted a runtime) is not taken for a claim on this one.
    char pid[24];
    std::snprintf(pid, sizeof pid, "%ld", static_cast<long>(getpid()));
    const char* owner = std::getenv("SCRIPTFORGE_RUNTIME_PID");
    if (owner != nullptr && std::strcmp(owner, pid) == 0) return false;
    setenv("SCRIPTFORGE_RUNTIME_PID", pid, 1);
    return true;
#endif
}

// The whole startup sequence, off the loader lock.
void run_startup() {
    using namespace kp::runtime;
    const std::string exe = self_module_path();
    const std::string game_dir = exe.empty() ? std::string(".") : directory_of(exe);
    Config cfg = Config::from_game_dir(game_dir);
    cfg.role = kp::multiplayer::role_from_executable(exe);
    Runtime::instance().start(cfg);
}

}  // namespace

#if defined(_WIN32)

namespace {

DWORD WINAPI worker(LPVOID) {
    run_startup();
    return 0;
}

}  // namespace

BOOL APIENTRY DllMain(HMODULE self, DWORD reason, LPVOID) {
    switch (reason) {
    case DLL_PROCESS_ATTACH: {
        // Thread attach and detach tell us nothing and cost a loader-lock
        // acquisition on every thread the game creates, of which there are
        // many.
        DisableThreadLibraryCalls(self);
        if (!claim_process()) break;   // another copy already runs in this process

        // CreateThread rather than std::thread: this is the one thing that is
        // documented as safe to do under the loader lock. The thread does not
        // begin running until the lock is released, which is exactly the
        // behaviour we want.
        HANDLE t = CreateThread(nullptr, 0, &worker, nullptr, 0, nullptr);
        if (t != nullptr) CloseHandle(t);
        break;
    }
    case DLL_PROCESS_DETACH:
        // Deliberately empty. Unpatching here would mean writing to the game's
        // code section while other threads may still be executing in it, under
        // the loader lock, during teardown. The process is going away; leaving
        // the patches in place is the safer of the two wrongs. Runtime::stop()
        // exists for a caller that can guarantee quiescence.
        break;
    default:
        break;
    }
    return TRUE;
}

#else

namespace {

void* worker(void*) {
    run_startup();
    return nullptr;
}

// A constructor rather than an exported init function: the ELF target is
// reached through LD_PRELOAD, which gives us no call site of our own.
//
// A thread here, and not a direct call, for the same reason as the Windows
// side: constructors run while the dynamic linker is still finishing, and the
// decipher wait would block the process from starting at all.
__attribute__((constructor)) void kp_elf_entry() {
    // Native host tests link the real runtime to exercise its APIs. They must
    // control its lifecycle themselves: an implicit startup worker would race
    // their Host bindings and engine-owner latch. The production preload path
    // keeps automatic startup unless explicitly disabled before process start.
    const char* disabled = kp::naming::env("NO_AUTOSTART");
    if (disabled != nullptr && std::strcmp(disabled, "1") == 0) return;
    if (!claim_process()) return;   // another copy already runs in this process
    pthread_t t{};
    if (pthread_create(&t, nullptr, &worker, nullptr) == 0) pthread_detach(t);
}

}  // namespace

#endif

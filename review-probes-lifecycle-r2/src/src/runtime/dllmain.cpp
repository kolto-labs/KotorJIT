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
#include "runtime/runtime.hpp"

#if defined(_WIN32)
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#else
#include <pthread.h>
#endif

namespace {

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
    pthread_t t{};
    if (pthread_create(&t, nullptr, &worker, nullptr) == 0) pthread_detach(t);
}

}  // namespace

#endif

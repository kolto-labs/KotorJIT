// A stand-in for the game's binkw32.dll that loads KotorPhasor and then gets
// out of the way.
//
// Both games import binkw32 statically, and under Wine or Proton there is no
// builtin to compete with, so the loader picks this one out of the game folder
// before the executable's entry point runs. That makes it the earliest hook
// available without asking the player to launch through anything special, and
// it is the only vector that works the same on Windows and on Proton.
//
// Every Bink export is forwarded declaratively through binkw32.def, so there is
// no thunk code here and nothing to keep in sync when an export list changes.
// Install by renaming the original to binkw32_real.dll and dropping this in its
// place.
//
// This does NOT install hooks. At DllMain time the game's code section may still
// be ciphertext, and the loader lock is held -- so even loading kphasor.dll is
// deferred to a worker thread here; the real work happens on a further worker
// thread the runtime starts for itself once it is in.

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>

namespace {

// Written next to the game so a failure to load is visible without a debugger.
// A player whose mod silently does nothing has no way to tell this apart from a
// mod that loaded and found nothing to do.
void note(const char* what) {
    HANDLE f = CreateFileA("kotorphasor-proxy.log", FILE_APPEND_DATA, FILE_SHARE_READ,
                           nullptr, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (f == INVALID_HANDLE_VALUE) return;
    DWORD written = 0;
    WriteFile(f, what, static_cast<DWORD>(lstrlenA(what)), &written, nullptr);
    WriteFile(f, "\r\n", 2, &written, nullptr);
    CloseHandle(f);
}

void load_runtime() {
    if (GetModuleHandleA("kphasor.dll") != nullptr) return;   // already in

    if (LoadLibraryA("kphasor.dll") != nullptr) {
        note("kphasor.dll loaded");
        return;
    }

    const DWORD err = GetLastError();
    char msg[128];
    wsprintfA(msg, "kphasor.dll failed to load (GetLastError=%lu)", err);
    note(msg);
    // Deliberately not fatal. Without the runtime the player still gets their
    // game, just without scripting -- which beats refusing to start.
}

DWORD WINAPI worker(LPVOID) {
    load_runtime();
    return 0;
}

}  // namespace

BOOL APIENTRY DllMain(HMODULE self, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        // We never care about thread attach/detach, and turning the
        // notifications off keeps us out of the loader lock on every thread the
        // game creates.
        DisableThreadLibraryCalls(self);

        // LoadLibraryA deadlocks against the loader lock DllMain already holds
        // -- the same rule runtime/dllmain.cpp documents for kphasor.dll's own
        // entry point. This proxy happened to be safe only because kphasor.dll's
        // DllMain defers its own work to a worker thread and returns quickly;
        // that safety was incidental to this file, not guaranteed by it. Defer
        // here too, the same way: CreateThread is documented as safe under the
        // loader lock, and the thread does not start running until the lock is
        // released.
        HANDLE t = CreateThread(nullptr, 0, &worker, nullptr, 0, nullptr);
        if (t != nullptr) {
            CloseHandle(t);
        } else {
            // Every other failure path in this file logs through note();
            // silently giving up here would be the one exception.
            char msg[96];
            wsprintfA(msg, "CreateThread failed (GetLastError=%lu); kphasor.dll will not load", GetLastError());
            note(msg);
        }
    }
    return TRUE;
}

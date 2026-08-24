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
// be ciphertext, and the loader lock is held. All the real work happens on a
// worker thread the runtime starts for itself.

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

}  // namespace

BOOL APIENTRY DllMain(HMODULE self, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        // We never care about thread attach/detach, and turning the
        // notifications off keeps us out of the loader lock on every thread the
        // game creates.
        DisableThreadLibraryCalls(self);
        load_runtime();
    }
    return TRUE;
}

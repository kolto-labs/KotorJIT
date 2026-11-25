// A stand-in for the game's binkw32.dll that loads KotorJIT and then gets
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
// be ciphertext, and the loader lock is held -- so even loading kotorjit.dll is
// deferred to a worker thread here; the real work happens on a further worker
// thread the runtime starts for itself once it is in.

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>

namespace {

HMODULE g_self = nullptr;

// Resolve `leaf` inside the directory containing this binkw32.dll so neither
// the proxy log nor runtime DLL lookup depends on process CWD. Returns true if
// resolved relative to g_self; falls back to bare `leaf` otherwise.
bool sibling_path(const char* leaf, char* out, DWORD cap) {
    if (out == nullptr || cap == 0 || leaf == nullptr) return false;
    if (g_self != nullptr) {
        char mod[MAX_PATH * 2] = {};
        const DWORD n = GetModuleFileNameA(g_self, mod, sizeof(mod));
        if (n > 0 && n < sizeof(mod)) {
            DWORD cut = n;
            while (cut > 0 && mod[cut - 1] != '\\' && mod[cut - 1] != '/') --cut;
            const int leaf_len = lstrlenA(leaf);
            if (cut > 0 && cut + static_cast<DWORD>(leaf_len) + 1 <= cap) {
                for (DWORD i = 0; i < cut; ++i) out[i] = mod[i];
                for (int i = 0; i <= leaf_len; ++i) out[cut + static_cast<DWORD>(i)] = leaf[i];
                return true;
            }
        }
    }
    lstrcpynA(out, leaf, static_cast<int>(cap));
    return false;
}

// Written next to the game so a failure to load is visible without a debugger.
// A player whose mod silently does nothing has no way to tell this apart from a
// mod that loaded and found nothing to do.
void note(const char* what) {
    char log_path[MAX_PATH * 2] = {};
    sibling_path("kotorjit-proxy.log", log_path, sizeof(log_path));
    HANDLE f = CreateFileA(log_path, FILE_APPEND_DATA, FILE_SHARE_READ,
                           nullptr, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (f == INVALID_HANDLE_VALUE) return;
    DWORD written = 0;
    WriteFile(f, what, static_cast<DWORD>(lstrlenA(what)), &written, nullptr);
    WriteFile(f, "\r\n", 2, &written, nullptr);
    CloseHandle(f);
}

// Current name first, then the name the runtime shipped under before the
// KotorPhasor -> KotorJIT rename, so a game folder that only received a new
// proxy (or only kept an old DLL) still starts scripting. Exactly one runtime
// is ever loaded: if either is already resident, nothing more happens.
constexpr const char* kRuntimeNames[] = {"kotorjit.dll", "kphasor.dll"};

void load_runtime() {
    for (const char* name : kRuntimeNames)
        if (GetModuleHandleA(name) != nullptr) return;   // already in

    DWORD first_error = 0;
    for (const char* name : kRuntimeNames) {
        char dll_path[MAX_PATH * 2] = {};
        const bool resolved = sibling_path(name, dll_path, sizeof(dll_path));
        if (LoadLibraryA(dll_path) != nullptr) {
            char msg[96];
            wsprintfA(msg, "%s loaded", name);
            note(msg);
            return;
        }
        DWORD err = GetLastError();
        if (resolved && err == ERROR_MOD_NOT_FOUND) {
            if (LoadLibraryA(name) != nullptr) {
                char msg[96];
                wsprintfA(msg, "%s loaded", name);
                note(msg);
                return;
            }
            err = GetLastError();
        }
        if (first_error == 0) first_error = err;
        // ERROR_MOD_NOT_FOUND just means "not installed under this name"; any
        // other error means the file is there and broken, which is worth
        // recording even if a later name loads.
        if (err != ERROR_MOD_NOT_FOUND) {
            char msg[128];
            wsprintfA(msg, "%s failed to load (GetLastError=%lu)", name, err);
            note(msg);
        }
    }

    char msg[160];
    wsprintfA(msg, "no runtime loaded: kotorjit.dll and kphasor.dll both failed (first GetLastError=%lu)",
              first_error);
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
        g_self = self;
        // We never care about thread attach/detach, and turning the
        // notifications off keeps us out of the loader lock on every thread the
        // game creates.
        DisableThreadLibraryCalls(self);

        // LoadLibraryA deadlocks against the loader lock DllMain already holds
        // -- the same rule runtime/dllmain.cpp documents for kotorjit.dll's own
        // entry point. This proxy happened to be safe only because kotorjit.dll's
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
            wsprintfA(msg, "CreateThread failed (GetLastError=%lu); kotorjit.dll will not load", GetLastError());
            note(msg);
        }
    }
    return TRUE;
}

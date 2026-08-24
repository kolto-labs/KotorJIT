// Glue between the four runtime translation units. Not a public interface:
// runtime.hpp is what the rest of the project sees, and everything here exists
// only because the runtime is split across files that have to agree.
#pragma once

#include <atomic>
#include <cstdint>
#include <string>
#include <string_view>

#include "events/contract.hpp"
#include "runtime/runtime.hpp"

namespace kp::hooks { class HookSet; }

namespace kp::runtime {

// Path of the GAME executable, from the OS rather than from Config::game_dir.
// Reconstructing "swkotor.exe" from a directory would guess wrong on the TSL
// ELF, and the guess would fail as an unreadable file rather than as a
// recognisable mistake.
std::string self_module_path();
std::string directory_of(const std::string& path);

// The generated contract table, and a lookup by Lua callback name.
//
// Returns null for a name the table does not carry. Hook bodies check for null
// rather than assuming: the table is generated from data/events.toml, so a
// callback this code wants can legitimately not exist yet, and a synthesised
// stand-in would dispatch to nobody -- Host::dispatch only calls scripts that
// Script::defines(), and that set comes from the same generated list.
const std::vector<events::EventContract>& event_table();
const events::EventContract* find_contract(std::string_view lua_name);

// True once the Lua host is fully built and its scripts are loaded.
//
// Hooks install before the host exists, per the phase order in runtime.hpp, so
// a game thread can enter a patched body while the worker thread is still in
// load_all(). A null check on host() is not enough for that -- load_all mutates
// the script vector after host_ becomes non-null. This flag is set with release
// semantics once boot is complete and read with acquire at the top of every
// body, and clearing it is also how a fault takes every body out of service.
bool live();
void set_live(bool);

// The Lua host a hook body should dispatch into, or null.
//
// Separate from Runtime::host() because that reads a unique_ptr that stop()
// resets, and a game thread inside a hook body has no synchronisation with the
// thread doing the reset. This is the published pointer: set once boot is
// complete, cleared before the host is destroyed, and read with acquire.
lua::Host* active_host();
void       set_active_host(lua::Host*);

// Called by the runtime once hooks are installed, and again before they are
// removed. The trampoline is unmapped on uninstall, so a cached original()
// pointer must be cleared BEFORE the uninstall rather than after.
void bind_originals(hooks::HookSet&);
void clear_originals();

// Detour entry points, handed to HookSet::add. Void* rather than typed
// pointers because that is what HookRequest takes and the types are private to
// hook_bodies.cpp.
void* run_script_detour();
void* main_loop_detour();
void* do_console_detour();

// ------------------------------------------------------------ fault guard ---

// One armed recovery point, one per hook body invocation.
//
// setjmp has to run in the frame it will return to, so the buffer lives here
// and the setjmp itself is written at the hook body through KP_HOOK_GUARD.
// Where the fault handler writes. Set before install_fault_guard() so the
// handler never has to ask the Runtime for anything: a fault handler that
// allocates or takes a lock can deadlock against the thing that faulted.
void set_fault_log_path(const char* path);

class FaultFrame {
public:
    FaultFrame(const char* site, std::atomic<bool>* poison);
    ~FaultFrame();

    FaultFrame(const FaultFrame&) = delete;
    FaultFrame& operator=(const FaultFrame&) = delete;

    void* buf();          // jmp_buf for this frame; always valid
    void  note_fault();   // after setjmp returns non-zero: log and poison

private:
    const char*        site_;
    std::atomic<bool>* poison_;
    int                slot_;
};

}  // namespace kp::runtime

// The recovery point a hook body arms around its own work.
//
//     KP_HOOK_GUARD_BEGIN("vm.run_script", g_poison, verdict = Verdict{})
//         ... the work ...
//     KP_HOOK_GUARD_END
//
// `fallback` runs after a hardware fault unwound us back here. It is a
// statement, not an expression, so a void body can use `{}` and a value-
// returning one can assign the result it will hand the engine.
//
// BEGIN/END rather than one macro, and this is not a style choice. setjmp
// returns twice, so a single macro would let a recovered fault fall straight
// back into the statement that faulted -- and it faults again, forever. The
// body has to be the ELSE of the recovery branch, which needs two macros to
// spell. Observed, not theorised: the one-macro version spun a million faults
// per second until the harness was killed.
//
// Deliberately NOT wrapped around the call to the original: a fault inside game
// code is the game's business, and claiming it would swallow a crash we did not
// cause. Bodies arm this over their own work and disarm before forwarding.
//
// A local written inside the guarded region has an indeterminate value after a
// longjmp, so `fallback` must re-state anything the body was going to set. And
// nothing constructed inside the region has its destructor run on the fault
// path; see fault_guard.cpp for why that is accepted rather than solved.
#include <csetjmp>
#define KP_HOOK_GUARD_BEGIN(site, poison, fallback)                       \
    {                                                                     \
        ::kp::runtime::FaultFrame kp_guard_frame_((site), &(poison));     \
        if (setjmp(*static_cast<jmp_buf*>(kp_guard_frame_.buf())) != 0) { \
            kp_guard_frame_.note_fault();                                 \
            fallback;                                                     \
        } else {

#define KP_HOOK_GUARD_END \
        }                 \
    }

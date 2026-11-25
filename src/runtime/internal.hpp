// Glue between the four runtime translation units. Not a public interface:
// runtime.hpp is what the rest of the project sees, and everything here exists
// only because the runtime is split across files that have to agree.
#pragma once

#include <atomic>
#include <cstdint>
#include <functional>
#include <string>
#include <string_view>
#include <thread>

#include "api/enginestruct.hpp"
#include "events/contract.hpp"
#include "multiplayer/transport.hpp"
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

// Sidecar written by the save cave and read by the load cave. Set once the
// game directory is known; empty means in-memory only for this process.
void set_situation_path(std::string path);

// Extra MainLoop orig() calls per hook. 1 = realtime. Capped at 16.
void set_tick_scale(unsigned n);
unsigned tick_scale();
void register_director(lua_State* L);

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

// The server MainLoop is the sole owner of Lua engine access.  The latch is
// armed at the top of that hook, before console pumping or script dispatch;
// lifecycle code resets it only at a worker/quiescent transition.
void reset_engine_thread();
void latch_engine_thread();
bool on_engine_thread();
bool engine_thread_latched();
bool engine_gate_probe(void*);
void reset_client_gate_mismatch_log();

// How a fresh lua_State gets the host API installed on it.
//
// The console keeps a state of its own so that a typo there cannot quarantine a
// loaded script. But a bare state can only do arithmetic: `lua exec` could parse
// Lua and never reach the game, which is a strange thing for a game console to
// be. The runtime publishes the same initialiser it hands every script state and
// the console runs it, so both surfaces share one definition of "the API"
// instead of drifting apart.
void set_state_init(std::function<void(lua_State*)>);
void init_lua_state(lua_State*);

// The Lua host a hook body should dispatch into, or null.
//
// Separate from Runtime::host() because that reads a unique_ptr that stop()
// resets, and a game thread inside a hook body has no synchronisation with the
// thread doing the reset. This is the published pointer: set once boot is
// complete, cleared before the host is destroyed, and read with acquire.
lua::Host* active_host();
void       set_active_host(lua::Host*);

// Published before the multiplayer hooks install and cleared before they are
// removed. Socket work never calls engine code; hook bodies drain it on the
// engine thread.
multiplayer::Transport* active_multiplayer_transport();
void set_active_multiplayer_transport(multiplayer::Transport*);

// Called by the runtime once hooks are installed, and again before they are
// removed. The trampoline is unmapped on uninstall, so a cached original()
// pointer must be cleared BEFORE the uninstall rather than after.
// Returns the per-site atomic original pointer slot so HookSet::install()
// populates g_orig_* before activating each detour.
std::atomic<void*>* hook_original_slot(std::string_view site);
void bind_originals(hooks::HookSet&);
void clear_originals();

// Detour entry points, handed to HookSet::add. Void* rather than typed
// pointers because that is what HookRequest takes and the types are private to
// hook_bodies.cpp.
void* run_script_detour();
void* main_loop_detour();
void* do_console_detour();
void* creature_event_detour();
void* door_event_detour();
void* placeable_event_detour();
void* trigger_event_detour();
void* module_event_detour();
void* area_event_detour();
void* encounter_event_detour();
void* aoe_event_detour();
void* store_event_detour();
void* waypoint_event_detour();
void* save_situation_detour();
void* load_situation_detour();
void* creature_move_to_point_detour();
void* add_move_to_point_detour();
void* net_start_connect_detour();
void* net_start_server_mode_detour();
void* net_send_message_detour();
void* net_process_frames_detour();
void* client_area_get_server_area_detour();
void  set_net_destination_offset(std::uint32_t);

// ------------------------------------------------------------ fault guard ---

// One armed recovery point, one per hook body invocation.
//
// setjmp has to run in the frame it will return to, so the buffer lives here
// and the setjmp itself is written at the hook body through KP_HOOK_GUARD.
// Where the fault handler writes. Set before install_fault_guard() so the
// handler never has to ask the Runtime for anything: a fault handler that
// allocates or takes a lock can deadlock against the thing that faulted.
void set_fault_log_path(const char* path);

// ------------------------------------------------------ binding the VM ------
//
// The routine bridge needs two live pointers that no address table can carry,
// because they are objects rather than code: the CVirtualMachine the stack
// accessors are called on, and the CSWVirtualMachineCommands the dispatcher
// indexes. Both are reachable from the CVirtualMachineInternal that
// CVirtualMachineInternal::RunScript is called on, so they are captured the
// first time that hook fires rather than hunted for at startup.
//
// Called from the RunScript body. Cheap after the first success.
void capture_vm(void* virtual_machine_internal);

// Address-only half, filled from the address table at install time. Kept apart
// from capture_vm so a missing site is reported during installation, when
// someone is reading the log, rather than on the first script the game runs.
void set_vm_sites(const api::VmSites&);
bool vm_bound();

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

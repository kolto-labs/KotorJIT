// The runtime: what happens between "our DLL got loaded" and "Lua is receiving
// game events".
//
// The order below is not arbitrary. On the primary target the game's code
// section is still ciphertext when our DllMain runs, so every step that reads an
// address has to wait for the wrapper to finish. Nothing here touches game
// memory until image/ says the image is real and matches what we expect.
//
//   1. identify the build from the executable's hash
//   2. wait for the code section to decipher, then verify it
//   3. load that build's address table
//   4. install hooks, all or nothing
//   5. start the Lua host and load scripts
//
// Any step failing leaves the game untouched and running. A mod that refuses to
// start is a bad afternoon; a mod that patches the wrong bytes is a corrupted
// save.
#pragma once

#include <cstdint>
#include <memory>
#include <string>

#include "multiplayer/role.hpp"
#include "multiplayer/transport.hpp"

namespace kp::lua { class Host; }
namespace kp::hooks { class AddressTable; class HookSet; }

namespace kp::runtime {

enum class Phase {
    Idle,
    Identifying,
    AwaitingDecipher,
    Resolving,
    Installing,
    Running,
    Failed,
};

const char* to_string(Phase);

struct Config {
    std::string game_dir;      // where the executable lives
    // <game_dir>/scriptforge, or <game_dir>/kotorphasor when only the folder an
    // older install created exists (see platform/naming.hpp). Hook packs,
    // manifests, address overlays and the situation file live here.
    std::string data_dir;
    std::string script_dir;    // defaults to <data_dir>/scripts
    std::string log_path;      // defaults to <game_dir>/scriptforge.log
    unsigned    error_budget = 8;
    bool        hot_reload = true;
    multiplayer::Role role = multiplayer::Role::Embedded;
    std::string multiplayer_host = "127.0.0.1";
    unsigned    multiplayer_port = 0;

    // The headless harness listener. Off unless `harness_port` is set in the
    // ini or SCRIPTFORGE_HARNESS_PORT is in the environment; players never
    // run it. The ini parser ignores section headers, so the keys are the
    // global `harness_port` and `harness_bind`. Anything but loopback is
    // refused when the listener starts.
    unsigned    harness_port = 0;
    std::string harness_bind = "127.0.0.1";

    // Read from scriptforge.ini next to the game if present, so a player can
    // change these without rebuilding.
    static Config from_game_dir(const std::string& game_dir);
};

class Runtime {
public:
    static Runtime& instance();

    // Runs the whole sequence. Safe to call from a worker thread; NOT safe from
    // DllMain, which holds the loader lock and would deadlock on LoadLibrary.
    bool start(const Config&);
    void stop();

    Phase              phase() const { return phase_; }
    const std::string& failure() const { return failure_; }
    const std::string& build() const { return build_; }
    multiplayer::Role role() const { return role_; }

    lua::Host*              host()  { return host_.get(); }
    hooks::HookSet*         hooks() { return hooks_.get(); }
    const hooks::AddressTable* table() const { return table_.get(); }

    // Appends to the log file. Cheap and unconditional: when something goes
    // wrong inside somebody else's process, the log is usually all there is.
    void log(const char* fmt, ...);

private:
    Runtime() = default;

    bool identify(const Config&);
    bool await_and_verify(const Config&);
    bool resolve(const Config&);
    bool start_multiplayer(const Config&);
    bool install(bool multiplayer);
    bool boot_scripts(const Config&);

    Phase       phase_ = Phase::Idle;
    std::string failure_;
    std::string build_;
    std::string image_sha256_;
    multiplayer::Role role_ = multiplayer::Role::Embedded;
    std::string log_path_;
    std::uintptr_t runtime_base_ = 0;

    std::unique_ptr<hooks::AddressTable> table_;
    std::unique_ptr<hooks::HookSet>      hooks_;
    std::unique_ptr<lua::Host>           host_;
    std::unique_ptr<multiplayer::Transport> transport_;
};

// Installed once, before any hook. Turns a hardware fault inside our own code
// into a logged, contained failure instead of a crash the player reports as the
// game being broken.
//
// This is what invariant 1 needs and what a try/catch cannot give: MinGW's C++
// front end has no __try/__except, and a null dereference in a hook body is not
// a C++ exception, so it would otherwise sail straight past guard() and take the
// process down.
void install_fault_guard();
void remove_fault_guard();

// True while a hook body is running, which is when a fault is ours to own.
bool in_hook_body();
void enter_hook_body();
void leave_hook_body();

}  // namespace kp::runtime

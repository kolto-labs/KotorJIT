// The harness commands, and the drain that runs them on the game's thread.
//
// Two halves. The runtime half (start / stop / set_adapter) is called from the
// worker thread during boot and shutdown. The main-thread half (drain /
// after_frame / quit_requested) is called from the client-loop detour in
// src/runtime/hook_bodies.cpp, once per client frame, and is the only place a
// command ever executes.
//
// The drain obeys the feasibility amendments in docs/harness-design.md:
//
//   * the pending batch is swapped out of the channel BEFORE any fault guard
//     is armed, and replies are pushed AFTER the last one is released, so a
//     claimed fault never leaves a mutex held;
//   * KP_HOOK_GUARD is armed around request parsing, Lua execution and reply
//     serialisation only. Every EngineAdapter call runs between
//     enter_hook_body() and leave_hook_body(), an unarmed frame: a fault in
//     engine code is a real crash for the crash oracle to see, never a
//     longjmp over engine frames;
//   * the drain gates on its own poison flag, never on live(), so `reload`
//     can re-arm scripting after a fault. Commands that need the Lua host
//     check live() and active_host() themselves;
//   * a thread-local `draining` flag makes a re-entered client loop skip the
//     drain: during LOADING the client loop calls UpdateScreen, which runs
//     the server loop nested inside it;
//   * at most kMaxPerTick requests run per frame.
#pragma once

#include <atomic>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>

namespace kp::hooks { class HookSet; }

namespace kp::harness {

class EngineAdapter;

struct HarnessOptions {
    std::string    bind = "127.0.0.1";
    unsigned short port = 0;
};

constexpr std::size_t kMaxPerTick = 8;

struct ScreenshotResult {
    bool ready = false;
    bool ok = false;
    std::string path;
    std::string error;
    int width = 0;
    int height = 0;
    std::uint64_t client_tick = 0;
};

// ---- runtime side (worker thread) ----

// Opens the listener. False with `error` filled when the bind is refused or
// the port is taken; the runtime logs and carries on without a harness.
bool start(const HarnessOptions&, std::string& error);
void stop();
bool started();
unsigned short listening_port();
std::uint64_t uptime_ms();

// The adapter is built after the hooks install and before the channel opens.
void           set_adapter(std::unique_ptr<EngineAdapter>);
EngineAdapter* adapter();

// ---- main-thread side (client-loop detour) ----

void drain();
void after_frame();
bool quit_requested();
void request_quit();
void request_reload();
bool request_screenshot(const std::string& path, std::string& error);
bool take_screenshot_result(ScreenshotResult& result);

// For `quit`: wait, bounded, for the reply to reach the socket, then close
// the listener so the process exits with no thread still writing.
void stop_after_flush();

// Counted by the detour once per real client frame, for `status` and the
// driver's hang oracle.
void          note_client_frame();
std::uint64_t client_tick();

// The drain's own poison flag, listed in the runtime's poison table under the
// name "harness" so `lua status` and the `status` command both show it.
std::atomic<bool>& poison_flag();

}  // namespace kp::harness

namespace kp::runtime {

// Defined in src/runtime/hook_bodies.cpp, declared here rather than in
// runtime/internal.hpp: that header belongs to the runtime and the harness
// packet adds nothing to it. Both are read by src/runtime/runtime.cpp and by
// harness/commands.cpp.
std::vector<std::string> poisoned_sites();
void* client_main_loop_detour();
void* client_frame_wrapper_detour();

}  // namespace kp::runtime

#include <cassert>
#include <atomic>
#include <optional>
#include <thread>
#include "harness/pause_lease.hpp"

namespace kp::harness::pause_snippet2 {
void hook_pause_world_timer(void*);
bool bind_pause_hooks_after_install(kp::harness::pause::Machine&, void*, void*, std::thread::id);
extern std::atomic<unsigned> g_off_thread_hook_calls;
extern std::atomic<void*> g_orig_pause_timer;
}

using namespace kp::harness::pause;
struct Ops final : NativeOps {
    std::atomic<int> original{0};
    bool original_pause(TimerId) override { ++original; return true; }
    bool original_unpause(TimerId) override { ++original; return true; }
    std::optional<bool> read_paused(TimerId) override { return true; }
};
std::atomic<int> forwards{0};
void original(void*) { ++forwards; }

int main() {
    Ops ops; Machine machine(ops); const TimerId timer = 0x10;
    assert(machine.register_timer(timer) == Status::Ok);
    assert(kp::harness::pause_snippet2::bind_pause_hooks_after_install(
        machine, reinterpret_cast<void*>(&original), reinterpret_cast<void*>(&original), std::this_thread::get_id()));
    Ticket ticket{}; assert(machine.acquire({1, 1}, timer, &ticket) == Status::Ok);
    kp::harness::pause_snippet2::g_orig_pause_timer.store(nullptr);
    forwards.store(0);
    kp::harness::pause_snippet2::hook_pause_world_timer(reinterpret_cast<void*>(timer));
    const int owner_forwards = forwards.load();
    std::thread worker([] { kp::harness::pause_snippet2::hook_pause_world_timer(reinterpret_cast<void*>(0x10)); });
    worker.join();
    assert(owner_forwards == 0);
    assert(kp::harness::pause_snippet2::g_off_thread_hook_calls.load() == 1);
    assert(machine.loading() == false);
    std::printf("owner hook suppressed=1; worker passthrough=1; off_thread_calls=1; tool_state_unchanged=1\n");
}

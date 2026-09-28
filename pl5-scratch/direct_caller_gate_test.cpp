#include <cassert>
#include <cstdio>
#include <optional>
#include <atomic>
#include <thread>
#include "harness/pause_lease.hpp"
namespace kp::harness::pause_snippet2 {
bool direct_caller_can_touch(kp::harness::pause::Machine&);
extern std::atomic<kp::harness::pause::Machine*> g_pause;
extern std::atomic<std::thread::id> g_owner_thread;
}
using namespace kp::harness::pause;
struct Ops final : NativeOps {
    bool original_pause(TimerId) override { return true; }
    bool original_unpause(TimerId) override { return true; }
    std::optional<bool> read_paused(TimerId) override { return true; }
};
int main() {
    Ops ops; Machine m(ops);
    kp::harness::pause_snippet2::g_pause.store(nullptr);
    kp::harness::pause_snippet2::g_owner_thread.store(std::this_thread::get_id());
    m.set_hooks_installed(true, true);
    assert(!kp::harness::pause_snippet2::direct_caller_can_touch(m));
    kp::harness::pause_snippet2::g_pause.store(&m, std::memory_order_release);
    assert(kp::harness::pause_snippet2::direct_caller_can_touch(m));
    kp::harness::pause_snippet2::g_pause.store(nullptr);
    m.set_hooks_installed(false, false);
    kp::harness::pause_snippet2::g_pause.store(&m, std::memory_order_release);
    assert(!kp::harness::pause_snippet2::direct_caller_can_touch(m));
    std::printf("direct caller before publish=refused; after publish=allowed; reordered publish=refused\n");
}

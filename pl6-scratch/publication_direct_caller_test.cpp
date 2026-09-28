#include <cassert>
#include <cstdio>
#include <optional>
#include <thread>
#include "harness/pause_lease.hpp"
#include "hooks/thiscall.hpp"

namespace kp::harness::pause_snippet2 {
bool bind_pause_hooks_after_install(kp::harness::pause::Machine&, void*, void*, std::thread::id);
bool direct_caller_can_touch(kp::harness::pause::Machine&);
kp::harness::pause::Status guarded_register_timer(kp::harness::pause::Machine&, kp::harness::pause::TimerId);
kp::harness::pause::Status guarded_acquire(kp::harness::pause::Machine&, kp::harness::pause::LeaseKey,
                                           kp::harness::pause::TimerId, kp::harness::pause::Ticket*);
kp::harness::pause::Status guarded_release(kp::harness::pause::Machine&, const kp::harness::pause::Ticket&);
extern std::atomic<kp::harness::pause::Machine*> g_pause;
extern std::atomic<std::thread::id> g_owner_thread;
}

using namespace kp::harness::pause;
struct Ops final : NativeOps {
    bool paused = false;
    bool original_pause(TimerId) override { paused = true; return true; }
    bool original_unpause(TimerId) override { paused = false; return true; }
    std::optional<bool> read_paused(TimerId) override { return paused; }
};

void KP_THISCALL original(void*) {}

int main() {
    Ops ops;
    Machine m(ops);
    constexpr TimerId timer = 0x10;
    const LeaseKey key{7, 1};
    Ticket ticket{};

    // No publication: neither registration nor acquisition may mutate state.
    assert(kp::harness::pause_snippet2::guarded_register_timer(m, timer) == Status::HooksUnavailable);
    assert(kp::harness::pause_snippet2::guarded_acquire(m, key, timer, &ticket) == Status::HooksUnavailable);
    assert(!m.status(timer).tracked && m.lease_count() == 0 && !ops.paused);

    // Reordered publication: pointer visible but readiness false is refused.
    kp::harness::pause_snippet2::g_owner_thread.store(std::this_thread::get_id());
    kp::harness::pause_snippet2::g_pause.store(&m, std::memory_order_release);
    assert(kp::harness::pause_snippet2::guarded_register_timer(m, timer) == Status::HooksUnavailable);
    assert(kp::harness::pause_snippet2::guarded_acquire(m, key, timer, &ticket) == Status::HooksUnavailable);
    assert(!m.status(timer).tracked && m.lease_count() == 0 && !ops.paused);
    kp::harness::pause_snippet2::g_pause.store(nullptr, std::memory_order_release);

    // Unset owner is refused before publication and leaves the prior state.
    m.set_hooks_installed(false, false);
    assert(!kp::harness::pause_snippet2::bind_pause_hooks_after_install(
        m, reinterpret_cast<void*>(&original), reinterpret_cast<void*>(&original), std::thread::id{}));
    assert(kp::harness::pause_snippet2::g_pause.load() == nullptr);
    assert(kp::harness::pause_snippet2::guarded_register_timer(m, timer) == Status::HooksUnavailable);
    assert(kp::harness::pause_snippet2::guarded_acquire(m, key, timer, &ticket) == Status::HooksUnavailable);
    assert(!m.status(timer).tracked && m.lease_count() == 0 && !ops.paused);

    // Valid owner after publication can use real Machine operations.
    assert(kp::harness::pause_snippet2::bind_pause_hooks_after_install(
        m, reinterpret_cast<void*>(&original), reinterpret_cast<void*>(&original), std::this_thread::get_id()));
    assert(kp::harness::pause_snippet2::guarded_register_timer(m, timer) == Status::Ok);
    assert(kp::harness::pause_snippet2::guarded_acquire(m, key, timer, &ticket) == Status::Ok);
    assert(m.lease_count() == 1);
    assert(ops.paused);
    assert(kp::harness::pause_snippet2::guarded_release(m, ticket) == Status::Ok);
    assert(m.lease_count() == 0);
    assert(!ops.paused);

    // An off-thread direct caller is refused and cannot register/acquire.
    Status worker_register = Status::Ok;
    Status worker_acquire = Status::Ok;
    std::thread worker([&] {
        worker_register = kp::harness::pause_snippet2::guarded_register_timer(m, 0x20);
        Ticket off{};
        worker_acquire = kp::harness::pause_snippet2::guarded_acquire(m, key, 0x20, &off);
    });
    worker.join();
    assert(worker_register == Status::HooksUnavailable && worker_acquire == Status::HooksUnavailable);
    assert(!m.status(0x20).tracked && m.lease_count() == 0 && !ops.paused);
    std::printf("prepublish=register+acquire_refused; reordered=register+acquire_refused; unset_owner=register+acquire_refused; valid_owner=register_acquire_release_paused_restored; off_thread=register+acquire_refused; no_mutation=1\n");
}

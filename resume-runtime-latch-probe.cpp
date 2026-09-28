#include "runtime/internal.hpp"
#include <atomic>
#include <thread>
#include <cassert>
#include <cstdio>
int main() {
    for (unsigned round=0; round<100; ++round) {
        kp::runtime::reset_engine_thread();
        assert(!kp::runtime::engine_thread_latched());
        assert(!kp::runtime::on_engine_thread());
        std::atomic<unsigned> ready{0}, winners{0};
        std::atomic<bool> go{false}, checked{false};
        auto race = [&] {
            ready.fetch_add(1);
            while (!go.load()) std::this_thread::yield();
            kp::runtime::latch_engine_thread();
            const bool own = kp::runtime::on_engine_thread();
            if (own) winners.fetch_add(1);
            for (unsigned i=0; i<100; ++i) {
                kp::runtime::latch_engine_thread();
                assert(kp::runtime::on_engine_thread() == own);
            }
            while (!checked.load()) std::this_thread::yield();
        };
        std::thread a(race), b(race);
        while (ready.load() != 2) std::this_thread::yield();
        go.store(true);
        while (winners.load() == 0) std::this_thread::yield();
        assert(!kp::runtime::on_engine_thread());
        checked.store(true);
        a.join(); b.join();
        assert(winners.load() == 1);
        assert(kp::runtime::engine_thread_latched());
        assert(!kp::runtime::on_engine_thread());
        kp::runtime::reset_engine_thread();
        assert(!kp::runtime::on_engine_thread());
        kp::runtime::latch_engine_thread();
        assert(kp::runtime::on_engine_thread());
        kp::runtime::reset_engine_thread();
    }
    std::puts("PASS runtime exact-owner latch: 100 simultaneous two-thread races, stable owner/refusal, reset/relatch");
}

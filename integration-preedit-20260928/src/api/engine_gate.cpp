#include "api/engine_gate.hpp"
#include <atomic>
#include <cstdint>
#include <mutex>
// A sequence counter guards the (probe, context) pair so a reader never pairs
// one bind's probe with another bind's context. Odd = rebind in progress. A
// reader that sees an odd count, or a count that changed while it read the
// pair, is refused rather than retried: refusing is always safe here.
//
// bind_gate itself is not lock-free: a plain mutex serializes the three
// stores below so two concurrent binders can never interleave their
// fetch_add pairs (which would let one binder's "odd" marker be cancelled by
// the other's, and a reader could then observe a probe/context pair spliced
// from both binds -- see review-probes-motion-m2/gate_twowriters.cpp and
// kp_enginegatetest.cpp's concurrent_two_writers_never_tear, which
// reproduces the tear against the un-mutexed version). bind_gate is not a
// hot path (it runs at most a few times per Runtime lifecycle: bind at
// start, unbind at stop, plus any future rebind), so this costs nothing
// where it matters. on_engine_thread(), the hot read path, takes no lock at
// all: it only ever loads the three atomics below, exactly as before.
namespace kp::api::engine {
namespace {
std::atomic<std::uint32_t> g_sequence{0};
std::atomic<Probe> g_probe{nullptr};
std::atomic<void*> g_context{nullptr};
std::mutex g_bind_mutex;   // serializes bind_gate only; on_engine_thread never takes it
}

void bind_gate(Probe probe, void* context) {
    std::lock_guard<std::mutex> lock(g_bind_mutex);
    g_sequence.fetch_add(1);             // odd: readers refuse
    g_probe.store(nullptr);
    g_context.store(context);
    g_probe.store(probe);
    g_sequence.fetch_add(1);             // even again
}

bool on_engine_thread() {
    std::uint32_t before = g_sequence.load();
    if (before & 1u) return false;
    Probe probe = g_probe.load();
    void* context = g_context.load();
    if (g_sequence.load() != before) return false;
    if (!probe) return false;
    return probe(context);
}

const char* gate_refusal() { return "unsupported: not on the engine thread"; }
} // namespace kp::api::engine

#include "api/engine_gate.hpp"
#include <atomic>
#include <cstdint>
// A sequence counter guards the (probe, context) pair so a reader never pairs
// one bind's probe with another bind's context. Odd = rebind in progress. A
// reader that sees an odd count, or a count that changed while it read the
// pair, is refused rather than retried: refusing is always safe here.
namespace kp::api::engine {
namespace {
std::atomic<std::uint32_t> g_sequence{0};
std::atomic<Probe> g_probe{nullptr};
std::atomic<void*> g_context{nullptr};
}

void bind_gate(Probe probe, void* context) {
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

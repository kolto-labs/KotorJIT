#pragma once
// Engine-thread gate, shared by every native reader and writer that calls into
// or reads live engine memory (motion now; camera, model and others later).
//
// The runtime binds one probe. The probe answers "may this thread touch the
// engine right now?" and is expected to be `live() && current thread == the
// latched server MainLoop thread`. Nothing here knows about Lua, the runtime or
// a domain module.
//
// Fail closed: with no probe bound, or while a (re)bind is in progress, every
// caller is refused. A caller asks the gate FIRST, before any memory read or
// engine call, so a refusal costs zero reads and zero calls.
namespace kp::api::engine {
using Probe = bool (*)(void* context);
// Bind a probe; nullptr unbinds. bind_gate may be called from any thread,
// including concurrently with other bind_gate calls: it is internally
// serialized (a plain mutex), so two overlapping binds can never interleave
// and hand a reader a torn (probe, context) pair. The bound probe itself,
// and on_engine_thread() below, take no lock and may run concurrently with
// bind_gate and with each other at any time.
// bind_gate does not wait for in-flight on_engine_thread() calls to finish:
// a reader that already read the old (probe, context) pair before this call
// returns may still invoke the old probe with the old context afterward.
// context must therefore outlive the bind that installs it (the runtime's
// own binds pass nullptr, which trivially satisfies this).
void bind_gate(Probe, void* context);
// False when unbound, when the probe says no, or when a concurrent rebind
// was observed while asking.
bool on_engine_thread();
// "unsupported: not on the engine thread"
const char* gate_refusal();
} // namespace kp::api::engine

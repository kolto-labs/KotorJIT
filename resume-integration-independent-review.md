# Resume integration independent review

Date: 2026-09-28

Scope: read-only API-boundary review of the current validation worktree against
`/home/brunner56/kp-live-20260922/resume-integration-readiness.md`, the Lua
lifecycle Round 3 report, the vector U1/U2 review, and the motion M2 review.
No product, writer scratch, shared build, Wine, live-game, or lock state was
modified.

## Verdict

**PARTIAL / integration gate remains open.** The current worktree contains
the standalone `kp.scripts`, `kp.vec`, and `kp.motion` implementations and
their host tests, but the runtime initializer and production source list do
not yet register or bind the three surfaces. The existing `kp.scripts` global
host pointer is therefore never connected to the active `lua::Host`; motion's
engine gate and native binding have no runtime lifecycle caller; and vector is
not in the runtime API source list. Existing namespace/lifecycle receipts are
host/static evidence and do not establish runtime registration.

## Claim blocks

claim: `kp.scripts` uses the active Host across create/reset/reload states.
referent: `src/api/scripts_lua.cpp` defines `g_host`, `bind_host`,
`bound_host`, and `register_all`; `src/runtime/runtime.cpp:718-746` is the
state-created callback and Host construction path.
checked: `scripts_lua.cpp` reads a raw process-global `g_host`; however the
runtime callback calls `api::register_all`, memory, structs, animation,
projectiles, model, camera, entity, support, director, game-speed, and compat,
but never `api::scripts::register_all` and never `api::scripts::bind_host`.
`rg` over current `src/runtime`, `src/api`, and `src/lua` finds no production
`bind_host` call. Runtime stop clears `active_host` but has no scripts API
unbind call. The lifecycle host tests exercise `lua::Host` and scratch API
surface, not this missing runtime bridge.
verdict: FAIL for production registration; Host lifecycle core remains
separately CONFIRMED by the Round 3 report.
confidence: high.

## Final bounded host receipts

claim: The linked host test set is isolated from implicit Linux ELF startup and
passes after the opt-out correction.
referent: `/home/brunner56/kp-live-20260922/integration-root-ctest.log` and
the final `src/api/*` CTest properties.
checked: The receipt reports 10/10 passing tests, including
`kp_routinetest`, `kp_namespacetest.k1`, `kp_namespacetest.k2`,
`kp_vectortest`, `kp_enginegatetest`, harness, lifecycle, scripts API, and
console protocol. The four tests that link the runtime ELF carry
`KOTORPHASOR_NO_AUTOSTART=1`; the prior missing routine property is now
covered.
verdict: CONFIRMED for this bounded host CTest slice.
confidence: high.

claim: Exact owner identity and reset behavior pass without startup-worker
interference.
referent: `/home/brunner56/kp-live-20260922/latch-isolation-debug-summary.json`
and the private exact-latch probe receipt.
checked: The isolated debug summary records `reset_calls: 300`, all reset calls
on thread `1`, `probe_passed: true`, and `normal_exit: true`. The environment
opt-out removes the hidden ELF worker from this proof. The source now uses
exact `std::atomic<std::thread::id>` identity; this is host-side latch proof,
not a live selected game hook proof.
verdict: CONFIRMED for isolated owner latch/reset behavior.
confidence: high.

claim: Failed-start cleanup preserves unload callback lifetime and clears the
Host binding.
referent: `/home/brunner56/kp-live-20260922/resume-runtime-boot-probe.cpp`
with the failed-start argument and
`/home/brunner56/kp-live-20260922/resume-runtime-failed-start.log`.
checked: The probe seeds a Host through the real `Runtime::boot_scripts` seam,
then calls `Runtime::start` against the unsupported native host configuration.
The receipt reports the expected failed-start cleanup pass, including the
unload callback and cleared binding. The probe also checks failed phase, one
callback, null `bound_host`, null Runtime Host, and false live state.
verdict: CONFIRMED for bounded failed-start cleanup.
confidence: high.

These receipts close the host-side integration checks for API registration,
Host lifetime, owner reset, and failed-start cleanup. They do not establish
Windows ABI behavior, GOG/H0 target resolution, hook installation on a real
game image, native motion execution, or live game behavior. The overall gate
therefore remains PARTIAL outside this bounded host slice.

## Latch probe RCA and autostart isolation

claim: The simultaneous owner failure was caused by the probe racing runtime
startup, not by two successful owner CAS operations.
referent: `/home/brunner56/kp-live-20260922/latch-reset-debug.log`,
`src/runtime/dllmain.cpp`, and the linked host probe.
checked: The Linux ELF constructor starts a hidden worker unless the exact
environment value `KOTORPHASOR_NO_AUTOSTART=1` is present. That worker calls
`Runtime::start`, including `reset_engine_thread`, while linked host tests run.
The retained GDB trace shows the extra startup thread and reset stack
interleaved with the probe's two-thread race. The source has since restored
exact `std::atomic<std::thread::id>` ownership; the lossy hash/TLS workaround
was rejected.
verdict: CONFIRMED RCA; the original owner-probe failure was invalidated by
uncontrolled ELF autostart.
confidence: high.

claim: CTest host tests are isolated from ELF autostart.
referent: `src/runtime/dllmain.cpp:104-115`, `src/api/vector.cmake:32-35`,
`src/api/support.cmake:88-91`, and `src/api/routines.cmake`.
checked: The constructor opt-out is Linux-only, exact-match (`strcmp(value,
"1")`), and leaves production startup unchanged for all other values. Vector
and namespace tests set the opt-out in CTest. `kp_routinetest` directly links
`kphasor` but currently lacks the same CTest environment property and remains
a race risk until covered.
verdict: PARTIAL pending the routine-test environment fix and rerun.
confidence: high.

The later writer revision supersedes the earlier token allocator discussion:
the production latch is now restored to exact `std::atomic<std::thread::id>`
identity. The monotonic-token observations above describe the failed
intermediate build only and are retained solely to explain the probe RCA.

claim: `kp.vec` is available from every fresh Lua state created by Runtime.
referent: `src/api/vector.cpp:311` defines `api::register_vector`; the fresh
state callback is `runtime.cpp:718-746`.
checked: The callback has no `register_vector(L)` call. `src/runtime/runtime.cmake`
`KP_API_SOURCES` also omits `api/vector.cpp`; only the standalone vector CMake
fragment names it. The namespace/vector tests therefore cannot prove that a
runtime-created state exposes `kp.vec`.
verdict: FAIL for production registration; standalone vector contract remains
unverified as runtime behavior.
confidence: high.

## Owner identity re-review

claim: Engine-thread ownership uses an exact stable identity rather than a
lossy thread hash.
referent: `src/runtime/runtime.cpp:191-224` and
`src/runtime/hook_bodies.cpp:761-774`.
checked: The revised source uses an atomic monotonic `uint64_t` allocator,
one `thread_local` token per thread, and an atomic latched owner token. The
server MainLoop calls `latch_engine_thread()` before overlay, console, harness,
or Lua work. `on_engine_thread()` compares the exact token; the startup worker
and client/render callbacks do not latch ownership. Reset is called only from
the worker/quiescent start, failed-start, and stop paths.
verdict: CONFIRMED for exact identity and required source ordering; the prior
`std::hash<thread::id>` concern is resolved.
confidence: high.

The allocator's theoretical `uint64_t` wraparound is not reachable in normal
process operation, but a strict permanent nonzero/unique contract should use a
skip-zero/saturating allocator. A focused host test should also prove stable
per-thread tokens, distinct tokens across two threads, first-latch ownership,
rejection from a second thread, reset, relatch, and concurrent first-latch
winner behavior. The frozen library still needs its bounded rebuild and owner
test rerun after this source revision; no live or Windows proof is implied.

claim: `kp.motion` is registered, native-bound, and gated on engine thread and
phase in Runtime lifecycle.
referent: `src/api/motion_lua.cpp:244` defines `register_all`; motion core
uses `api::engine::on_engine_thread()` before argument reads; `src/api/motion.hpp`
defines `bind_native`, `bind_owner_probe`, and `bind_tick`.
checked: `runtime.cpp` has no `api::motion::register_all`, `bind_native`,
`bind_owner_probe`, `bind_tick`, or `api::engine::bind_gate` call. Runtime
source list has no motion files or `engine_gate.cpp`; `src/api/motion.cmake`
is a standalone/test fragment. Runtime stop unbinds model, camera,
animation, and projectiles, but has no motion unbind or engine-gate unbind
operation. Thus the engine-thread gate exists in the implementation but no
production lifecycle establishes its probe/context or native profile.
verdict: FAIL for production wiring; standalone motion core/test evidence does
not establish runtime registration or failure cleanup.
confidence: high.

claim: Runtime failure paths leave the new APIs safely unbound.
referent: `runtime.cpp:798-818` failed-start cleanup and `runtime.cpp:865-889`
stop cleanup, plus API bind/unbind functions.
checked: Failed start sets `set_live(false)`, clears active host and transport,
resets hooks/table/host, then unbinds animation, projectiles, model, and
camera. It does not call missing scripts host unbind, motion unbind, engine
gate unbind, or vector teardown. Since those bindings are not initialized in
the current source, this is first a registration gap; once wiring lands, each
must be part of the same failure cleanup and stop order. No loader-lock wait
was found in `Runtime::start` itself; actual bind placement still needs source
review after the writer lands it.
verdict: PARTIAL; existing host/animation/projectile cleanup is visible, new
surface cleanup is unproven.
confidence: high.

claim: `kp.vec` introduces no duplicate NWScript function names.
referent: `src/api/vector.cpp` and `tools/kp_namespacetest.cpp` plus the
historical namespace receipts.
checked: The vector implementation uses `kp.vec`/`kp.vec.meta` and does not
add entries to the NWScript routine catalogue. Existing namespace receipts
report zero failures for K1/K2, but they predate production vector
registration and are static/host evidence only.
verdict: CONFIRMED for the isolated namespace contract; runtime exposure still
requires the final integrated namespace test.
confidence: medium.

## Runtime boundary findings

The current initializer's intended fresh-state callback is the correct place
to call all Lua registrations, because `HostConfig::on_state_created` runs for
the boot state and fresh reload states. The final integration must add scripts,
vector, and motion registration there and prove that `scripts::bind_host`
tracks the newly created active Host before script callbacks can invoke
`kp.scripts.*`. Reset/reload must not leave `g_host` pointing at the destroyed
Host; stop/failure cleanup must clear it before `host_.reset()`.

Motion requires a separate lifecycle bind outside `DllMain` and loader-lock
detach. The engine gate bind must occur only after verified image/profile and
native operations are ready, and must be unbound before the backend/profile is
destroyed. The existing `Runtime::start` worker path is the candidate, but
there is no landed call site to inspect or test yet.

The concrete engine-thread callback seam remains `src/harness/commands.cpp`
`after_frame()` and the native frame bodies at `src/runtime/hook_bodies.cpp`
lines 1280 and 1304. That seam is relevant to motion owner probes and must not
be confused with the startup worker thread that installs hooks.

## Tests and gate implications

Checked read-only:

- `timeout 60s sh /home/brunner56/kp-live-20260922/pl6-scratch/run_pl6.sh ...`
  returned 0 for the real pause publication snippet and passthrough test.
- A private gate-removal mutant removed the direct-caller guard and returned
  134 at the unchanged prepublish assertion. This is standalone snippet
  evidence, not production integration evidence.
- Existing namespace receipts report zero K1/K2 failures, but are not a fresh
  post-integration runtime registration test.
- Existing Lua lifecycle and scripts API receipts prove Host and API behavior
  independently, not the current Runtime initializer bridge.

The final acceptance gate needs a source-frozen runtime diff, a bounded host
build of the actual runtime target, and tests that create/reset/reload states,
observe `kp.scripts` bound to the current Host, expose `kp.vec`, bind and
unbind motion/engine gate on success and failure, and verify no bind waits run
inside loader-lock callbacks. Until those exist, this review remains PARTIAL.

## Grill me

1. Does `api::scripts::register_all` existing prove `kp.scripts` works in the
   game? No; current Runtime never calls it and never binds the active Host.
2. Does `vector.cmake` prove the shipping runtime contains `kp.vec`? No; the
   shipping `runtime.cmake` API list omits `vector.cpp`.
3. Does an engine-thread check in `motion_lua.cpp` prove motion is safe? No;
   the gate has no production probe/bind or native operation lifecycle call.
4. Do historical namespace and lifecycle receipts settle integration? No;
   they settle their isolated contracts only. A final integrated target and
   fresh registration checks are still required.

## Freeze status

This review records the current worktree snapshot and its exact source gaps.
The writer's final saved copies should be diffed against these referents before
accepting any later integration claim; no writer files were edited here.

## Post-integration writer snapshot

The writer subsequently added the expected runtime bindings in the current
worktree. This section supersedes the baseline gap findings above for the
source snapshot, while retaining the requirement for a frozen target build and
runtime test.

claim: The fresh Lua state callback now registers scripts, vector, and motion.
referent: `src/runtime/runtime.cpp:762-775` calls
`api::register_vector(L)`, `api::motion::register_all(L)`, and
`api::scripts::register_all(L)`; `src/runtime/runtime.cmake:54-86` now includes
vector, motion, engine_gate, and scripts_lua sources.
checked: Read-only diff and source inspection confirm these calls are in the
same `HostConfig::on_state_created` callback used for boot and fresh Host
states. No build was run concurrently with the writer.
verdict: CONFIRMED at source registration level; runtime executable binding
remains unverified until the writer freezes and a target build/test receipt is
available.
confidence: high for source presence; low for linked runtime reachability.

claim: The active scripts Host is connected and cleared on lifecycle failure
and stop.
referent: `runtime.cpp:799-805` binds `api::scripts::bind_host(host_.get())`
after Host construction; failed-start cleanup around `:858-875` and stop
around `:925-940` call `api::scripts::bind_host(nullptr)`.
checked: Source inspection confirms boot binding, failed-start clearing before
`host_.reset()`, and stop clearing after `host_.reset()`. The stop order keeps
the pointer valid during Host destruction callbacks, but leaves the raw
scripts API pointer non-null while `host_.reset()` runs; a concurrent direct
caller would be an untested race. `set_active_host(nullptr)` is done before
stop teardown, and no linked lifecycle test currently proves a fresh state
sees the new Host pointer after reset/reload.
verdict: PARTIAL; intended callback lifetime is plausible, but concurrent
pointer safety and actual create/reset/reload registration remain unproven.
confidence: medium.

claim: Motion native binding and owner/tick probes are wired outside loader
lock, and are removed on failure/stop.
referent: `runtime.cpp:432-439` calls `motion::bind_native`; `:799-805`
binds owner/tick probes; `:825-831` resets the engine thread and binds the
engine gate; failure cleanup `:858-875` and stop `:925-940` clear motion
probes, unbind native operations, clear the engine gate, and reset the latch.
checked: Source inspection confirms all call sites are in `Runtime::start`
and `Runtime::stop`, not `DllMain`; `engine_gate_probe` requires both `live()`
and the latched engine thread. `motion_owner` maps `Script::owner(L)` to
Loaded/Staged/None. No target build or runtime test was available in this
review because the writer was being frozen.
verdict: CONFIRMED for source placement and failure/stop cleanup; PARTIAL for
linked/runtime behavior.
confidence: high for the inspected source; medium overall.

claim: The engine-thread latch is captured at the required server MainLoop
boundary before console pump and harness/Lua work.
referent: `src/runtime/hook_bodies.cpp:759-770` calls
`kp::runtime::latch_engine_thread()` immediately after loading the original
function pointer and before `overlay_tick`, console pump, harness drain, or
Lua dispatch.
checked: Read-only source inspection confirms the server MainLoop path, while
the client/render callbacks remain later fallback drains. The latch uses
compare-exchange so the first server MainLoop thread wins; `Runtime::start`
resets it before installation and `stop`/failed start reset it after teardown.
No linked execution receipt proves the selected hook is installed for the
current target.
verdict: CONFIRMED for source ordering; PARTIAL for actual hook installation.
confidence: high for source ordering; medium for runtime reachability.

claim: The final integrated runtime has passed the API boundary tests and
namespace test after these changes.
referent: target build and fresh tests for lifecycle/scripts API, vector,
motion/engine gate, and namespace registration.
checked: No fresh post-integration target receipt was available in this
read-only review. Historical standalone receipts are not substituted for it.
verdict: UNVERIFIED; this is the remaining acceptance gate.
confidence: high.

The final gate is therefore **PARTIAL pending frozen-target build and tests**.
The source diff now contains the intended registrations, MainLoop-before-pump
owner latch, and cleanup calls, but linked registration and failure behavior
must still be proven from the writer's frozen copies.

## Frozen source and private boot-probe review

claim: The active Host binding is established before initial top-level script
execution and is withdrawn only after unload callbacks finish.
referent: `src/runtime/runtime.cpp` binds `api::scripts::bind_host(host_.get())`
before `host_->load_all(errors)`. Both failed-start cleanup and `Runtime::stop`
call `host_->unload_all()` while the binding remains active, then clear the
binding and reset the Host.
checked: Read-only source review after writer freeze. `Host::stage()` in
`src/lua/host.cpp` invokes `on_state_created` and executes the top-level chunk
inside `load_all`; `Host::~Host()` calls `unload_all`, whose `raise_unload`
callbacks run before script destruction. The explicit unload-before-unbind
ordering now matches that contract.
verdict: CONFIRMED at source level.
confidence: high.

claim: The real Runtime boot seam exposes the registered APIs to a top-level
script and preserves scripts access during `OnScriptUnload`.
referent: `/home/brunner56/kp-live-20260922/resume-runtime-boot-probe.cpp`.
checked: Root compiled and ran the probe against the frozen runtime library;
the recorded run returned rc 0. The probe invokes the real private
`Runtime::boot_scripts` member through an explicit-access fixture, writes a
top-level script that calls `kp.scripts.list`, constructs and reads `kp.vec`,
calls `kp.motion.capabilities`, and registers an `OnScriptUnload` callback.
After registering the native `record_unload` function, it calls the real
`Runtime::stop`; the callback asserts a live bound Host, the test requires one
callback, and then requires a null binding, null Runtime Host, and false live
state.
verdict: CONFIRMED for the actual boot initializer, initial scripts binding,
registered vec/motion/scripts surfaces, unload callback lifetime, and stop
cleanup.
confidence: high for this bounded seam.

The probe deliberately bypasses `Runtime::start`, image identification,
address-table resolution, hook installation, and native engine binding. It
therefore does not prove full game startup, selected target hook reachability,
native motion execution, or loader-lock behavior. It also does not cover a
failed `Runtime::start` after a partially initialized Host. Those remain
separate gates.

claim: Integrated runtime acceptance is complete.
referent: Frozen source, private boot probe, and existing standalone
lifecycle/namespace receipts.
checked: The private boot probe is an actual linked Runtime call-path receipt,
but the full `Runtime::start`/game or Windows proof was not run; no Wine or
live launch was authorized.
verdict: PARTIAL for the overall integration gate; CONFIRMED for the bounded
boot/Host lifecycle seam above.
confidence: high.

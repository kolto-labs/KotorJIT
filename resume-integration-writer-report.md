# Host-only integration writer report

Date: 2026-09-28
Worktree: `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`
Build cache: `/tmp/lifecycle-cfg`

## Result

**Source integration completed and host gate passed.** The requested API
registrations and source lists are wired in the assigned worktree. The engine
gate is bound and reset only from `Runtime::start`/failure cleanup/`Runtime::stop`
(worker or quiescent lifecycle code). Engine ownership is latched at the top of
the server `MainLoop` detour, before console pumping, harness draining, or Lua
execution. The startup worker and `DllMain` contain no gate bind or engine
latch. Client/render callbacks only compare against the server latch and emit a
bounded mismatch diagnostic; they never relatch ownership.

Pause production hooks were not added. The R6 pause contract remains a
separate future direct-caller wiring slice.

## Files changed by this integration

- `CMakeLists.txt`: includes `src/api/vector.cmake` and `src/api/motion.cmake`.
- `src/runtime/runtime.cmake`: adds vector, motion, engine-gate, and
  `scripts_lua.cpp` production sources.
- `src/runtime/runtime.cpp`: registers `kp.vec`, `kp.motion`, and `kp.scripts`
  for every fresh Lua state; binds the scripts host and motion owner/tick
  services before initial `Host::load_all`; binds native motion; binds/resets
  the engine gate at worker/quiescent lifecycle boundaries; logs VM layout
  resolution explicitly; unbinds services before destroying `Host`.
- `src/runtime/internal.hpp`: declares the portable server-thread latch and
  engine-gate probe.
- `src/runtime/hook_bodies.cpp`: latches the server `MainLoop` thread before
  first engine-facing work and logs one client-thread mismatch without
  relatching.
- `tools/kp_namespacetest.cpp`: includes and registers vector, motion, and
  scripts surfaces in the namespace contract target and exercises the exact
  server latch/unlatch/worker refusal helper.
- `tools/kp_scriptsapitest.cpp`: keeps the host bound through unload callbacks
  and explicitly verifies `kp.scripts.list()` remains available during
  `OnScriptUnload` before unbinding and destruction.

The existing dirty changes in camera, lifecycle, H0, dead-event, and address
artifacts were preserved. The Steam K1 address tables were not rewritten in
this integration; their current hashes are recorded below and the independent
layout/regen tests passed.

## Build provenance

The cache was freshly configured and its authoritative source is:

```text
CMAKE_HOME_DIRECTORY:INTERNAL=/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation
```

Commands:

```text
cmake -S /run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation \
  -B /tmp/lifecycle-cfg -DCMAKE_BUILD_TYPE=Debug -DKP_MAX_JOBS=1
cmake --build /tmp/lifecycle-cfg --target kphasor kp_namespacetest kp_motiontest \
  kp_enginegatetest kp_vectortest kp_lifecycletest kp_scriptsapitest kp_harnesstest -j1
```

The build returned `0`. No clean-first operation was used. The final
post-correction incremental rebuild of `kphasor`, `kp_namespacetest`,
`kp_motiontest`, and `kp_enginegatetest` also returned `0`.

## Current-source host evidence

Receipt `/home/brunner56/kp-live-20260922/integration-targeted-20260928.log`,
SHA-256 `845a862e4696ee42b1e249095eea9564b4ceb7232d37270e1d080179ebd62420`,
contains these current-source runs, all exit `0`:

- `kp_namespacetest`: `namespace contract: 0 failure(s)`
- `kp_namespacetest k2`: `namespace contract: 0 failure(s)`
- `kp_vectortest`: `15 check(s), 0 failure(s)`
- `kp_motiontest`: `58/58 tests passed, 4158 checks`
- `kp_enginegatetest`: `6/6 tests passed, 19 checks`
- `kp_lifecycletest`: `31 case(s), 0 failed`
- `kp_scriptsapitest`: `10 case(s), 0 failed`
- `kp_harnesstest`: `0 failure(s)`

After the final runtime/latch corrections, the targeted rebuild and rerun
receipt is `/home/brunner56/kp-live-20260922/integration-postfix-20260928.log`,
SHA-256 `a31a14dc496ecd5a5b7f83fe11def62a469cc6b1432402acbf8ef95795952745`.
It independently reruns the namespace K1/K2, motion, and engine-gate targets;
all returned `0` with the same counts.

Static receipts:

- `/home/brunner56/kp-live-20260922/integration-static-20260928.log`, SHA-256
  `1565018848333397d04104ca8528c63d7376aa17149783e0957906896cbfa4ab`
- `address_table_layout_test.py`: 26 tests, OK
- `camera_profile_consistency_test.py`: 5 tests, OK
- `platform_profile_consistency_test.py`: 23 tests, OK

No Wine, game, Gamescope, mpv, x11grab, live lock, or live process was used.

## Source hashes at freeze

```text
029baaeb7dc32862c9842c5674a9b270a4ca1ba55a97e2ca126bb9277eab1338  CMakeLists.txt
88331564b40ea0ea506afd155ff621845d2564b9689ba34f63a7600ef6d38587  src/runtime/runtime.cmake
70a360b1a9996f62ce23a855a1ed5af92f8c2d044b0ca2a1ea17014e3d0f78fd  src/runtime/runtime.cpp
571816e0ab130fff9ae329eb430bd52426493a1136e2b0b3838104b2c10762e1  src/runtime/internal.hpp
5b561f0b24799e738a695ac0d7229c90173d0191851b9d5f8034a0f089d3e080  src/runtime/hook_bodies.cpp
2374b6e616dd9566f1c29f402966148bf26b3ff9bab372f470fca4b98df00fc9  tools/kp_namespacetest.cpp
65e7c2dd5c4c83cf02296a69f3c5d082b9e75d1c2bee5a1eeb497474c3f7fd66  data/addresses/k1_gog_103.json
c52447bd10a2811a2a40530ecf3696803adad0ddcebcb62ebf7a415ce7f62048  data/addresses/k1_steam_103.json
5cc67517140e3559b939b39aecb4d741c7f2fffb83075e3445726f897c2bc155  data/addresses/k1_steam_103_unpacked.json
```

## Claim blocks

claim: the missing Lua surfaces are production-registered on every fresh state.

referent: `src/runtime/runtime.cpp` state initializer calls
`register_vector`, `motion::register_all`, and `scripts::register_all`; the
same state initializer is installed into the console path.

checked: current-source `kp_namespacetest` K1/K2 and lifecycle/scripts targets,
all exit `0`; `runtime.cmake` contains the production source list.

verdict: CONFIRMED for the host/source gate.

confidence: high for source and host behavior; no live-game claim.

claim: motion engine access is fail-closed until the actual server MainLoop
thread is latched, and ownership is never taken from the startup worker or a
client callback.

referent: `runtime.cpp` reset/bind calls are in `Runtime::start` and cleanup;
`hook_bodies.cpp` calls `latch_engine_thread()` at the first server MainLoop
line. Client loop paths call only the mismatch logger.

checked: `kp_enginegatetest` current-source result; source inspection of
`dllmain.cpp` shows no bind/latch path; current source hashes above.

verdict: CONFIRMED for the host/source integration contract.

confidence: high for the source gate and host latch helper; the root-owned
private boot probe additionally exercised the real initializer and stop-time
OnScriptUnload binding. Live execution remains outside this gate.

claim: the Steam VM layout failure is visible in installation diagnostics.

referent: `runtime.cpp` VM resolution log now reports both stack-site count and
`layout=resolved|unresolved`; current Steam tables carry the reviewed layout.

checked: 26-case address-table layout test and 23-case platform consistency
test, both OK; current table hashes above.

verdict: CONFIRMED for the source/static gate.

confidence: high for the logged predicate and table contract; no Steam live
route was launched.

## Remaining integration boundary

The integrated host/source gate is complete. A separate future slice must wire
the R6 pause `Machine` wrappers to production direct callers and prove every
caller is covered. This report does not promote that wiring, and does not
promote any host/static result to live game or external-client acceptance.

Root-owned private boot probe: `/home/brunner56/kp-live-20260922/resume-runtime-boot-{probe.cpp,build.log,run.log}` returned rc 0 against the same worktree cache; it exercised the real Runtime initializer, top-level `kp.scripts.list`, unload callback visibility, and null host binding after stop.

## Post-freeze latch probe correction (2026-09-28)

Root's linked native probe `/tmp/kp-resume-runtime-latch-probe` exposed a
remaining blocker after the original report was written. The probe performs
100 simultaneous two-thread latch races and requires exactly one owner per
round. Its retained run `/home/brunner56/kp-live-20260922/resume-runtime-latch-run.log`
failed with `Assertion winners.load() == 1` (and a subsequent retained run
failed the `engine_thread_latched()` assertion). Repeated executions against
the same current library were intermittent: one passed, one failed, one
passed. Therefore the previous latch `CONFIRMED` claim is withdrawn and the
overall integration verdict is **BLOCKED pending root's latch repair and a
fresh linked probe**.

The current library and test hashes at the time of this correction are:

```text
15219a97bb6a29494a1984f0e3c80415701fe055489de515ab36d43840f0f1d3  /tmp/lifecycle-cfg/libkphasor.so
d78169b117644cf29df74f1671e497cd1fc2ef248a9ab09399a82f9d0854a7cd  /tmp/lifecycle-cfg/kp_namespacetest
0ac753eadb8e09e89b857c95575c72ca60ef30c3985bcb54d1fa92299e93a853  /tmp/kp-resume-runtime-latch-probe
```

No product or build changes were made during this investigation. Root owns the
repair. The other host receipts remain historical evidence only until the
latch probe is green against a rebuilt current-source library.

## Read-only post-freeze audit: GOG regeneration and H0 target

The original integration brief contains two prerequisites that this writer did
not promote:

1. **K1 GOG address regeneration remains required.** The camera review records
   the authoritative regeneration shape as a K1-only run of
   `python3 tools/gen_address_tables.py --build k1_gog_103` after the camera and
   motion adjudication overlays are present. The camera review's independent
   scratch regeneration produced 283/283 resolved and added exactly seven
   motion sites while leaving camera rows byte-identical. The seven accepted
   motion rows are the first seven `kp_motiontest` pending rows:
   `server_object.area_id`, `server_object.position`,
   `server_object.orientation`, `server_object.client_push_gate_unverified`,
   `server_object.dirty_bits`, `placeable.aabb_registered`, and
   `placeable.quaternion_raw_order_unverified`.
   `server.get_placeable_by_object_id` and `placeable.vtable` are explicitly
   marked proposed in `kp_motiontest` and remain intentionally unaccepted;
   they must not be generated or treated as integration proof. The current
   `data/addresses/k1_gog_103.json` still reports those nine pending rows in
   the rebuilt motion test, so a fresh K1-only regeneration plus a diff proving
   only the seven accepted rows and binding-count changes is still outstanding.
   The K2 GOG table has unrelated dirty edits and must not be regenerated with
   `--all`.

2. **H0 real-commands CMake coverage remains incomplete.** The existing
   `kp_harnesstest` target is current-source and green, but it links the
   channel/json/ring/platform fixture and does not link `commands.cpp`.
   `h0-followup-review.md:130-145` explicitly leaves the checked-in
   real-`drain()`/`stream_events()` regression open; the real path was covered
   only by the scratch `sub_probe_r2.cpp` plus a checked-in stand-in. The
   requested follow-up is a dedicated harness CMake target linking
   `commands.cpp` with the review stubs and running the subscribed-condemned
   client case. No such target was added by this integration writer, so H0
   source integration is not complete at that narrower regression boundary.

These are source/release prerequisites, not live-game claims. No regeneration
or additional build was performed during this audit, per root's read-only
instruction.

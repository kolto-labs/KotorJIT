# Resume integration readiness

Date: 2026-09-28. This is a read-only inventory for the shared dirty worktree
`/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`.
No regeneration, build, game/Wine launch, display launch, or live-game lock
access was performed for this inventory.

## Readiness verdict

**Preparation is incomplete; integration must wait for the pause snippets to be
CONFIRMED and for root's integration ruling.** The accepted host proofs below
are usable as inputs to an ordered integration pass. The current source still
shows several APIs as test-only or not yet wired into the runtime initializer,
so the integration gate must begin with source wiring and end with one bounded
host matrix. The runtime bind gate must be placed on worker/quiescent Runtime
lifecycle paths and remain outside `DllMain`/loader-lock callbacks.

## Inventory

| Area | Authoritative files and evidence | Current state | Integration consequence |
|---|---|---|---|
| Camera Stage 1 | `src/api/camera.{hpp,cpp}`, `src/api/camera_backend.cpp`, `src/api/camera_lua.cpp`, `src/runtime/runtime.cmake:65-68`, `src/runtime/runtime.cpp:729`; `/home/brunner56/kp-live-20260922/camera-stage1-fix-confirm.md` | **Accepted host proof.** The fixed `tools/kp_cameratest.cpp:104` matrix reports 1818 checks across standard, SSE and GNU C++20 modes; mutation without the casts is red. | Preserve the camera registration and run the final source/build matrix after all integration edits. Do not treat 1818 checks as live camera proof. |
| Lua lifecycle L1/L2 | `src/lua/host.{cpp,hpp}`, `src/api/scripts_lua.{cpp,hpp}`, `tools/kp_lifecycletest.cpp`, `tools/kp_scriptsapitest.cpp`, `src/lua/lifecycle.cmake`; `/home/brunner56/kp-live-20260922/lua-lifecycle-r2-review.md` Round 3 section and `lc3-round3/logs/` | **Host fix accepted in Round 3.** Current report records 31 lifecycle cases and 10 scripts API cases passing; Windows/Wine evidence is reused, not regenerated in this wave. | Confirm the runtime initializer actually installs `scripts_lua`; current `rg` finds the definition but no `scripts::register_all` call in `src/runtime`/`src/api`. This is a concrete integration prerequisite, not a test-count issue. |
| `kp.vec` U1/U2 | `src/api/vector.{hpp,cpp}`, `src/api/vector.cmake`, `src/api/timers.{hpp,cpp}`, `/home/brunner56/kp-live-20260922/lua-utilities-u1u2-review.md` | **Core/test proof accepted conditionally.** The review explicitly says the `kp.vec` registration snippet was tested in scratch and is not yet reachable from the runtime until the snippet lands. | Add the production source and call `register_vector(L)` in the shared state initializer, then rerun namespace, vector, timer and support tests. Current `rg` finds only the definition and no production call. |
| Motion M1/M2 + engine gate | `src/api/motion.{hpp,cpp}`, `motion_backend.cpp`, `motion_lua.cpp`, `motion_profiles.cpp`, `src/api/engine_gate.{hpp,cpp}`, `src/runtime/runtime.cpp:783-890`; `/home/brunner56/kp-live-20260922/motion-m2-r2-review.md` | **Host proof PASS with an explicit integration gate.** Current-source motion and engine-gate receipts are retained. The review requires bind/unbind placement outside `DllMain` and loader-lock detach, including failed-start cleanup. | Wire motion sources and registration deliberately; add `bind_gate` only in worker/quiescent `Runtime::start`/`stop` paths. Current `rg` finds no production `api::motion::register_all` or `bind_gate` call. Recheck every resulting call site before acceptance. |
| H0 channel | `src/harness/channel.cpp`, `src/harness/channel.hpp`, `src/harness/commands.cpp`; `/home/brunner56/kp-live-20260922/h0-followup-review.md` and `review-probes-h0-r2/` | **H0 fix CONFIRMED.** The condemned-client generation filter is reviewed; red/green drain probes and 20/20 real-drain repetitions are recorded. The remaining open item is the exact real-commands regression breadth. | Preserve the one-line channel fix and run the final harness target after all source wiring. Do not rewrite the channel while integrating APIs. |
| Steam K1 VM layout | `data/addresses/k1_steam_103.json`, `data/addresses/k1_steam_103_unpacked.json`, `data/adjudication/*`; `/home/brunner56/kp-live-20260922/steam-k1-vm-layout-fix-review.md` and `/home/brunner56/kp-live-20260922/steam-k1-vm-binding-rca.md` | **Review PASS for the table fix.** Missing `vm.wrapper_internal` and `vm.internal_command_implementer` were added and red/green table tests plus fresh regeneration evidence are retained. GOG table changes from camera work are explicitly separate. | Keep table provenance separate from runtime integration. Verify source/table hashes and run the address-layout test before any installed-target proof. |
| H0 target / native harness | `/home/brunner56/kp-live-20260922/h0-followup-review.md`, `review-probes-h0-r2/`, and existing native harness receipts | **Host-only accepted evidence.** No live route or external client is implied. | Run after source wiring with bounded `kp_harnesstest`/protocol targets; retain red controls where available. |
| M8 namespace/dead events | `src/api/compat.cpp`, `src/events/table.{hpp,cpp}`, `tools/kp_namespacetest.cpp`; `/home/brunner56/kp-live-20260922/dead-event-register-review.md`, `dead-event-namespacetest-current.log`, `dead-event-namespacetest-build-current.log` | **Current namespace contract PASS.** K1 and K2 report zero failures; direct dispatch names are checked. The current receipt is host/static contract evidence only. | Restore/retain the current target artifact after shared build cleanup, then run it once after final integration. No live event-dispatch claim follows from this test. |
| K1 GOG / Steam source ledger | `docs/example-behavior-ledger.md`, `tools/tests/examples/manifest.json`, `data/addresses/k1_gog_103.json`, `data/addresses/k1_steam_103*.json`; `/home/brunner56/kp-live-20260922/example-host-receipt-20260927f.json` and `steam-k1-vm-layout-fix-review.md` | **Ledger is recommendation/provenance, not promotion.** Current host receipt binds 41 example bytes and reports 0 live receipts; no featured video is accepted. | Do not promote examples during integration. Reconcile manifest/table/source hashes and keep live/game/capture proof as separate later gates. |

## Concrete source findings

The current runtime state initializer in `src/runtime/runtime.cpp:715-734`
registers camera, entity, animation, projectiles, model and support APIs. It
does not call `register_vector`, `api::motion::register_all`, or
`scripts::register_all`; `rg -n` over `src/runtime src/api` finds only those
definitions for vector/motion and no production call. This is the principal
unresolved integration prerequisite.

The existing engine-gate contract explicitly permits concurrent binders but
does not make bind calls loader-lock safe (`src/api/engine_gate.hpp:15-25`).
`Runtime::start` and `Runtime::stop` are the intended worker/quiescent lifecycle
locations (`src/runtime/runtime.cpp:783-890`), while `src/runtime/dllmain.cpp`
keeps process-detach handling deliberately empty. The final integration review
must confirm that all new bind/unbind operations remain in those lifecycle
paths, including failed-start cleanup, and that no call can wait under
`DllMain`/loader lock.

## Ordered integration plan

1. Freeze the source set only after the pause snippets are marked CONFIRMED and
   root records the integration ruling. Record source hashes for the dirty
   files assigned to each slice; do not reset, stash, or stage unrelated work.
2. Wire the missing production registrations and source lists: lifecycle
   scripts, `kp.vec`, and `kp.motion`. Preserve camera's existing registration.
   Add engine-gate bind/unbind at worker/quiescent Runtime start/stop points,
   including explicit failed-start cleanup. Review the resulting diff for any
   `DllMain` or loader-lock path.
3. Run the smallest host checks in dependency order: camera Stage 1; lifecycle
   and scripts API; vector/timers/support; motion and engine gate; H0 channel;
   namespace/dead-event K1 and K2; address-table layout and Steam regeneration
   parity. Use disjoint scratch/build outputs or serialize shared targets.
4. Recompute a final source/hash receipt for the integrated worktree and retain
   each target's exit code and test count. A reused artifact can remain a
   historical receipt only; a final source-gate PASS needs a current-source
   build or an explicit hash match.
5. Stop before Wine/game/Gamescope/live capture. Only after the host source
   gate, pause linkage, root ruling, and the separate capture/browser gates are
   accepted may a live route be considered.

## Unresolved prerequisite

The single blocker that must be settled before integration is accepted is the
production registration/bind wiring described above. The settling evidence is
one source inspection showing the exact new calls, followed by the bounded
host target matrix with current-source hashes. The overall live acceptance also
remains blocked on the pause snippets being CONFIRMED and root's ruling.

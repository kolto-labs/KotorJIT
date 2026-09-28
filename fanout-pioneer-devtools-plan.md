# Pioneer playback / devtools — fan-out unit D plan (read-only; saved by orchestrator from planner output, 2026-09-27)
Worktree WT=/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation. Evidence: live / host / static.

## 1. Exists
- Pioneer init/step/commit/discard/status (pioneer.py:96-472, cli.py:185-260,345-375, committed ca329e5): host (author 21+57 tests; reviewer did not rerun, pioneer-policy-review.md:15). discard only deletes metadata (pioneer-authoring.md:51-54).
- Attached speed policy compare-and-restore scenario.py:530-590; native set_speed engine_k1.cpp:1686; managed 16x live (stage-k1/runs/20260922-094527 game_speed_effective 16.0); attached restore path no live receipt.
- playback.py:1-391 untracked draft (loopback server, one Channel, play/fastforward/stop/status, job ids, journal): static only, no tests, not wired in cli.py; task-pioneer-owner-report.md absent.
- Cancel hooks scenario.py:496,528,690,1996 + waits.py (uncommitted, belong to draft).
- Checkpoints checkpoints.py:61-108 (store/restore delete old copy first); CreativeCheckpoints creative_checkpoints.py:16; "load issued" not restoration proof.
- LoadStep fields.hpp:734; engine_k1.cpp:956-1075: static, not exposed per-request.
- timers_paused readback engine_k1.cpp:426-441: 3 clocks only.
- Recovery unpause helpers engine_k1.cpp:1644/2098/2620 (contract cites stale 1622/2076/2598).
- Per-clip animation pause LIVE (probe 115034, progress.md:72). World pause: research contract only.
- Dialog observe/reply commands.cpp:842,850; no history/rollback.
- Console service + kp.console.v1 LIVE (K1 runs 20260927-003752, -014019).
- Lua timers keep pumping during pause (hook_bodies.cpp:785).

## 2. Native pause status
Proven: speed scaling live (readback = configured multiplier); clip pause live. Static ABIs (pioneer-native-pause-contract.md:9-16): PauseWorldTimer 0x4adff0 / Unpause 0x4ae030 thiscall no-arg, boolean flag; SetPauseState server 0x4b8110 / client 0x5f7fa0. Proposal only: engine-thread pause lease hooking both timer entry points. Unverified: required clock set, interaction with Set/TogglePauseState, external-load invalidation, Lua timer freeze, saving while held, K2 hooks, deterministic replay.

## 3. Staged plan
Parallel rules: capture writer owns recording.py, display_backends.py, creative*.py, capture_diagnostic.py; scenario.py/waits.py/checkpoints.py edits additive + rerun kpharness_creative_test.py; native files engine_k1.cpp/fields.hpp/commands.cpp/runtime.cpp/kp_harnesstest.cpp carry uncommitted K2 load-completion work → native stages after that lands; live runs serialized behind lock and capture diagnostic.
- Stage 0 (now, host): new tools/kpharness_playback_test.py (real subprocess+socket, synthetic engine): one connection; ordered steps; status during wait; stop during wait; speed restored after failure; stale descriptor rejected; second owner other route refused; invalid args rejected pre-mutation; no retry; CLI e2e. Red-first fixes: (1) cancelled wait/expect wrongly sets world_uncertain (playback.py:226); (2) validation errors mark uncertain (:247); (3) effective_speed published before readback (:217); (4) pioneer step/commit open own Channel without engine_guard (cli.py:209); (5) owner holds route_lock for life (playback.py:282, pioneer.py:191) → route step/commit through owner; (6) engine lock under /tmp (playback.py:63) → user-private state dir. Files: playback.py, cli.py, pioneer.py, new test, docs/pioneer-authoring.md. Live proof later: attached K1 play --until 3, status, stop; speed readback restored; PID alive; state execution_stopped.
- Stage 1 (after native load-completion lands): new src/harness/pause_lease.{hpp,cpp} state machine + tools/kp_pause_lease_test.cpp (cases per contract :63), thiscall trampoline tests, hook via registry.cpp using timer.pause_world_timer/unpause sites, engine_k1/fields/commands pause_lease command, Lua kp.pause.acquire/release/status (kp.time is a function), oracle.py watchdog. Live: hold 150 frames unchanged clocks+pose, F12 1+1 → number:2, game pause persists after tool release, no catch-up jump.
- Stage 2: Pioneer pause/play wiring (playback.py, cli.py, oracle.py, waits.py additive).
- Stage 3: checkpoints publish_ready/restore_verified (additive), per-request load sequence from LoadStep (native, after load-completion), rewind = release lease → load → new sequence Done → predicates → cursor; branches as forked route files + sidecar; mod state reported not restored.
- Stage 4: dialog rollback bound to pre-conversation ready checkpoint; candidate scenarios/k1_fresh_trask_quest.toml.
- Stage 5 (now, host): fast-forward speed (0,16], restore on finish/pause/stop/failure, explicit speed step preserved, readback before effective_speed; label "configured multiplier".
- Stage 6 (after Stage 1): devtools on kp.console.v1 unchanged; Console::reset releases session leases; overlay status strip; docs.
Order: Stage 0 + 5 now; 1 and 6 after load-completion commit; then 2, 3 native, 4.

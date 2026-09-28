# Pioneer playback architecture audit

Read-only scoped source audit, 2026-09-22, worktree `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`. No builds/tests/live game calls/source changes. Prior `/tmp/kp-runtime-playback-research.md` read as design context; its ae1695f source snapshot is older, and current conclusions below were checked against present files. This is an implementation proposal, not an implemented API or live acceptance.

## Main recommendation

Evolve Pioneer into the frontend of ONE attached-session playback service using the existing ScenarioRunner dispatch and native save/load adapter. Keep route TOML in the harness driver. Do not add a second Lua/TOML interpreter, and do not equate authoring cursor movement with restored game state. The user's full RenPy-like objective remains game-state restoration across choices, quest/inventory/party/object/effect changes and declared mod state, with alternate branches after rewind—not merely video scrubbing or route navigation.

The immediate useful slice is checkpoint-backed `rewind`, resumable `play`, verified world `pause`, bounded `fastforward`, and honest pending-edit rollback, built on one persistent session owner. Native symmetric pause is a prerequisite for claiming the world is paused; speed0 is invalid. Until that primitive passes live gates, stopping route dispatch must be labeled `execution_stopped`, not `game_paused`.

## Current concrete foundation and gaps

| Surface | Current implementation | Consequence |
|---|---|---|
| Pioneer command group | cli.py185–286,356–386: init/step/commit/discard/status | No play/pause/rewind/fastforward operation or persistent cursor/branch/job owner |
| Actual step execution | pioneer.py201+: constructs ScenarioRunner and directly calls run_step | Correct common interpreter; reuse it |
| Pending authoring | pioneer.py95–125 stores target,step,result,time in ROUTE.pending.json | No session epoch, route hash, pre-step checkpoint, execution cursor, branch, atomic transaction or concurrent-writer lock |
| Commit/discard | cli.py228–264 append pending step then unlink, or simply unlink | Commit never executes twice, which is good. Discard does NOT undo live side effects. A second step can overwrite pending metadata without undoing the first mutation |
| Execution policy | ScenarioRunner.run invokes _configure_execution; pioneer.run_one_step does not | Pioneer inherits settings for waits but does not actually apply full-run speed setup. _configure_execution also skips setting1x based on fresh-process assumption, unsuitable for attached playback after fastforward |
| Route runner | scenario.py1930–2010 common run_step/run | Synchronous blocking waits and long do operations; no cooperative pause/cancel token across waits. Need lifecycle control in the shared service, not duplicated command cases |
| Creative runner | creative_steps.py extends ScenarioRunner for mark_log/await_log/advance_ticks and event watermark | Reuse/move these helpers into shared runner extensions so Pioneer and automated routes have the same capabilities. advance_ticks observes a threshold and can overshoot; it is not an exact one-frame scheduler |
| Session attachment | session.py379 SessionInfo; Pioneer _SessionProbe | Target/port/run/stage/process metadata exists, but Pioneer has no persistent attached-session identity ownership contract. It must not terminate the separately owned game on stop |
| Channel | client.py request IDs and event cursor | Late responses are distinguished; timeout is not proof a mutation did not execute. Service must journal issued vs completed and avoid automatic retry of non-idempotent actions |
| Recording | recording.py X11Recorder and creative.py | Existing continuous capture with owned-process cleanup. Encoded frames explicitly not proof of game cadence or determinism; playback changes should add markers, not rewrite video history |

## Native primitives and honest limits

- `GameAdapter::set_speed` engine_k1.cpp1664+: positive finite-compatible range(0,16], native SetGameSpeed, after_frame maintains multiplier. Existing `kp.game_speed` in runtime.cpp61–82 and harness speed bridge. This is real world-time scaling, not frame skipping. Restore the captured prior scale when leaving fastforward/stop; do not assume1x. Audio/dialog waits can remain wallclock-bound. Readback is configured multiplier, not proof every subsystem accelerated.
- `set_fixed_step` engine_k1.cpp2590s–2638 configures native fixed snapshot rates across client world/pause/animation and server world/pause timers, preserving existing pause flags around rate changes. This is NOT rollback or global deterministic replay: RNG, external inputs, wallclock Lua timers, render/audio and scripts still need control. A snapshot rate is not a single-step gate.
- PauseWorldTimer is mapped and used during loading/fixed-rate setup. There is no public symmetric pause/resume ownership API in inspected current sources. `clear_auto_pause`/`unpause_timers` are recovery primitives, can clear game-owned pauses, and must not become normal Play. Add narrowly profiled native pause ownership with prior-state capture and verified timer readback; preserve game/modal/combat pause and handle nested tool owners.
- Native save at engine_k1.cpp1283+ reports request dispatch. scenario.py575–628 waits for fresh SAVEGAME.sav with stable positive size and age, then copies a checkpoint. Useful existing mechanism, but a stalled partial file can also stop growing: strengthen readiness with required artifacts/archive parse/content hashes and captured state predicates before marking reusable checkpoint READY.
- `load_checkpoint` scenario.py556–562 restores disk files and issues load, returning “issued”; it does not wait for restored gameplay. Checkpoints.load only waits phase gameplay. Playback restoration must observe a NEW load epoch/transition followed by complete stable world, correct module/PC and checkpoint-specific state predicates before moving executed cursor. Preexisting gameplay must not satisfy completion immediately.
- checkpoints.py store/restore deletes prior destination before copying; new playback branches need immutable named checkpoint artifacts and atomic staging/publish so cancellation/partial copies cannot destroy the last ready checkpoint. Reuse CreativeCheckpoints containment checks and improve common implementation, not a separate weaker checkpoint store.
- Saves currently require stable idle noncombat/no-dialog world for copied checkpoints. Do not promise arbitrary midfight/midline checkpoints. Rewind to a prior valid checkpoint and replay only verified steps where needed.
- Native saves do not imply Lua VM restoration. Runtime OnSave/OnLoad still uses shared lua_situation.dat behavior described in the previous research; closures, console globals, native handles and timers need an explicit per-checkpoint mod-state contract. Until then report these domains unrestored and invalidate ephemeral native handles after load. Whole-process or complete engine/Lua/RNG snapshots remain a separate requirement for finer-grained rollback.

## Proposed idiomatic CLI semantics

Keep current commands compatible but route them through the shared owner. Every command has JSON status/job output, and long operations return a job ID; optional --wait awaits a terminal state.

| Command | Meaning |
|---|---|
| `pioneer play --out R [--until STEP]` | Resume committed branch from last VERIFIED executed boundary; execute common run_step; stop on failed predicate or requested boundary. Release only playback-owned pause token. Never append route source. |
| `pioneer pause --out R` | Stop scheduling new steps immediately; cooperatively pause active waits and acquire native world-pause ownership when legal. Return pausing/paused or explicit deferred/unsupported; never claim world stopped from merely pausing Python. |
| `pioneer fastforward --out R [--until STEP] [--speed 4]` | Same play path with bounded speed ownership; execute every action/assertion, no skipped waits or invented completion. Restore prior scale on finish/pause/cancel/failure. |
| `pioneer rewind --out R [--to CHECKPOINT_OR_BOUNDARY]` | Default nearest earlier READY checkpoint; perform native load and verified state restoration. If requested boundary requires replay, restore ancestor then use SAME runner through that boundary, validating observations. No checkpoint/replay path means unavailable, never decrement-only rewind. |
| `pioneer step --out R JSON` | At paused verified boundary, establish ready pre-step checkpoint when legal, execute one proposed edit, save pending provenance and actual result. Refuse a second pending mutation unless explicitly resolved. |
| `pioneer commit --out R` | Accept already-executed pending edit into branch atomically after route/session/hash validation. Do not execute again. |
| `pioneer discard --out R` | Roll back pending live mutation through recorded pre-step checkpoint and verified replay if needed, then remove pending edit. If rollback unavailable, fail explicitly; preserve legacy metadata-only action under an explicit `--edit-only` mode with world_dirty=true. |
| `pioneer stop --out R` | Cancel further route work, release only owned speed/pause/input resources, retain game/session and journal. Stop is not game shutdown or rewind. A load/save already issued may require waiting to terminal state before safe control returns. |
| `pioneer status --out R` | Session epoch/build/route hash/branch, authoring and executed cursor separately, active job, pause ownership, effective speed, pending edit, checkpoint readiness, state divergences and last failure. |

Pause scope during a blocking native call: record requested pause, do not perform unsafe reentrant engine calls. Once original save/load returns, poll completion or classify interrupted; preserve issued operation identity. Cancellation cannot undo already-applied mutations. Wait deadlines should exclude tool-paused time while preserving explicit wallclock ceilings for hung/failed native operations. Watchdog must distinguish owned pause from stagnation.

## One shared service design

A small persistent attached-session owner holds one Channel, session epoch, runner, checkpoint manager, run journal and ordered command queue. A second CLI connection sends control requests to this owner rather than competing for the game's single client channel. UI/CLI/tests call the same service methods; engine primitives remain behind the existing native adapter/engine-thread queue. Do not implement route semantics again in the service: it schedules ScenarioRunner steps and owns lifecycle transitions only. GameSession continues owning the game process; playback owns attachment and its own resources.

Represent route revision/hash, active branch, committed authoring cursor, verified executed cursor, pending dirty mutation, checkpoint references and operation state separately. Suggested operation states: idle/running/pause_requested/paused/saving/restoring/replaying/stopping/failed. Save/load are exclusive jobs with terminal ready/failed/cancelled-or-invalidated outcomes. Journal request-issued before waiting, completion only after predicates. Atomic file replacement and route lock protect pending/commit state. Reject stale session/route modifications instead of attaching an old pending receipt to new bytes.

After rewind, selecting a different reply or committing a changed step FORKS a new branch at the restored boundary. Preserve original branch and old footage/receipts; do not silently truncate. Merely replaying original unchanged choices follows the same branch. If external play/F12 mutation occurs, mark execution state diverged until a fresh checkpoint/reconciliation; route cursors alone cannot describe the world. Bind checkpoint to native image/runtime/script/config hashes, module/PC and declared mod-state version.

## Smallest meaningful implementation sequence and acceptance

1. Extract shared attached playback owner and lifecycle/cancellation hooks around existing runner; attach/status/play/stop and positive bounded speed ownership. Fix attached1x policy rather than relying on fresh-process assumption. Host tests prove one dispatch path, no duplicate commands after timeout, concurrent-command serialization, speed cleanup and no game teardown.
2. Add native symmetric pause/resume with capability/readback and ownership, then wire `pause`/`play`; no fake world-pause label before this works. Verify world/animation timers stop while control channel/console stay usable and releasing tool token preserves preexisting game pause.
3. Add asynchronous transactional checkpoint jobs and genuine rewind to READY checkpoint; record pre/post independent module, PC position/HP, globals/journal, inventory and owned-object predicates. Single source of truth for tests, Pioneer and UI. Job dispatch is not completion. Crash/cancel during copy/load preserves old ready checkpoint and reports terminal uncertainty/failure honestly.
4. Add pending-step checkpoint rollback and branches; prove choiceA side effect, rewind to matching pre-choice state, chooseB, retain original branch. A committed cursor and a restored game cursor must never diverge silently. Explicitly demonstrate unrestored console-local state/timers until per-checkpoint mod serializer exists.

The first meaningful end-to-end delivery should support play/pause/fastforward plus one checkpoint rewind and branch on an owned existing WinK1 session. If native pause or save lifecycle blocks, ship the completed host service as partial infrastructure and keep these requested controls pending; do not label the full playback objective complete. Full RenPy-like game-state control still requires coverage of game/mod domains and reliable replay from supported boundaries. No current source evidence proves exact-frame TAS or deterministic whole-game rollback.

Relevant current files: scripts/harness/kpharness/{pioneer.py,cli.py,scenario.py,creative_steps.py,creative.py,client.py,waits.py,oracle.py,checkpoints.py,creative_checkpoints.py,session.py,recording.py}; src/harness/{engine_k1.cpp,commands.cpp}; src/runtime/{runtime.cpp,hook_bodies.cpp}; src/api/compat.cpp. All relative paths resolve under the absolute worktree root above.

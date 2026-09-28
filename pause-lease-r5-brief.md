# Pause-lease round 5 repair brief

Date: 2026-09-27

Scope: repair planning only. This brief does not modify the worktree, the
pause-lease snippets, or the integration harness. It follows the Round 4
independent review in `pause-lease-r4-review.md` and keeps its evidence
boundary: no Wine/game/live launch was used.

## Gate

Round 4 remains **PARTIAL**. Q2 publish-last ordering holds for the two hook
bodies, and the preserved TSAN result is useful, but integration must remain
gated until the Armed timeout, real engine linkage, and direct-caller
publication boundary are repaired or explicitly accepted by the owner.

## Repair 1: bound `Armed` before it can hold `loading_` forever

The current `GameAdapter::step_load_completion()` enters the `Armed` state in
`src/harness/engine_k1.cpp:876-884`. At `:1048-1057`, normal completion is
checked, then `area_loaded_due(...)` can return false and the function returns
without changing `load_step_`. `Sent` has a 20-second timeout at `:992-998`
and `Placed` has a 300-second timeout at `:1034-1040`; `Armed` has no clock.
`finish_load()` is the path that releases the load lease, so a stalled native
load can leave `pause_machine_.loading()` true indefinitely.

Required repair:

1. Capture an `load_armed_at_` timestamp when `load_step_ = LoadStep::Armed`
   is assigned after `SendLoadGameRequest`.
2. Add an explicit bounded Armed timeout in `step_load_completion()`, before
   the `area_loaded_due` early return. On expiry, log the observed state and
   transition through the existing terminal cleanup path so `end_load()` is
   called exactly once and the result is `GaveUp`/failure rather than a
   claimed success.
3. Reset the timestamp on every new load and clear it on every terminal state.
4. Add a host-only test or pure helper test that holds `Armed` while
   `server_mode`, `module_ready`, `area_not_ready`, and `player_creature_id`
   never satisfy either completion predicate, advances time beyond the bound,
   and proves: one terminal result, one `end_load`, `loading()==false`, and no
   second cleanup on later frames.

The timeout value should be chosen from the existing load budget and named as a
constant. The test must cover the exact state that currently has no clock; a
test of `Sent` or `Placed` does not settle this finding.

## Repair 2: make the terminal harness exercise the real engine path

`tools/kp_load_terminal_harness.cpp` includes only the pause-lease model and
does not include or link `src/harness/engine_k1.cpp`. The Round 4 mutation
check confirms this: removing `pause_machine_.end_load()` from a copy of the
real `engine_k1.cpp` leaves the harness at `15 checks, 0 failures`.

Required repair:

1. Keep the pure `Machine` tests, but label their result as model coverage.
2. Add a separate compile/link target or fixture that links the relevant
   `GameAdapter` implementation (or a narrow extracted terminal helper) from
   the worktree. Do not copy the `on_fail` logic into a second test model.
3. Mutate the real linked terminal call site (`on_fail` and the normal
   terminal path independently) and require the corresponding test to fail.
4. Record the exact source hash and link command beside the result. A green
   15/15 model run alone cannot gate the engine integration.

If full `engine_k1.cpp` linkage is too costly or requires unavailable native
symbols, extract only the terminal transition function into a production-owned
small unit and have `engine_k1.cpp` call it. The extracted function must own
the single-call `end_load` rule and be tested through the same production
entry point.

## Repair 3: publish one ownership gate for all direct callers

`Machine::ownership_available()` in `src/harness/pause_lease.hpp:121-126`
reads plain `pause_hook_` and `unpause_hook_`. The two detour hook bodies are
protected by the `g_pause` acquire gate and the publish-last ordering, but a
direct engine-thread caller of `pause_machine_.acquire()` or
`register_timer()` can read `ownership_available()` independently. If it runs
between hook installation and the final `g_pause.store`, it can acquire a
lease while the hook bodies still pass through to the game.

Required repair:

1. Define the ownership publication boundary once, in production code, and
   make every direct caller use it. Options include an acquire-loaded atomic
   publication bit inside `Machine`, or requiring all direct callers to load
   the published `g_pause` owner before calling `acquire/register_timer`.
2. Preserve the ordering: install both detours, publish owner/thread state,
   then release-store the machine pointer last. Unpublish the machine before
   removing either detour.
3. Add a test that races a direct `acquire/register_timer` caller against
   installation and asserts it cannot return `Ok` until the hook bodies are
   also in ownership mode. The existing three-mode publish race only calls
   `on_pause_entry`/`on_unpause_entry`; it does not exercise a direct Machine
   caller.

This is currently a scope/integration gap rather than a demonstrated live
caller: `grep` found no wired `pause_machine_` direct caller in the current
tree. It must still be resolved before publication because the runtime has
already had an analogous `g_sites` publication race (`src/runtime/runtime.cpp`
comment near the hook installation path).

## Repair 4: test and initialize the owner-thread guard

The `tool_depth_` owner-thread guard has safe passthrough behavior when a
violation occurs, but the current race test never calls the installation helper
and no production caller currently supplies a real owner-thread identity.

Required repair:

1. Add a deterministic unit test that installs the hook bridge, records the
   owner thread, calls a hook from that thread, and calls it from a worker
   thread. Assert owner-thread calls enter the Machine and off-thread calls
   forward without touching Machine state.
2. Add an assertion or diagnostic for an unset owner thread before production
   publication; do not silently treat the default thread id as authoritative.
3. Keep the guard behavior nonfatal: an off-thread call must forward, and the
   test must verify no lease or `tool_depth_` mutation occurs.

## Required evidence packet for the next review

- Armed timeout test: command, raw output, exact timeout and one-call cleanup
  count.
- Real terminal linkage: compile/link command, source hashes, green result,
  and two mutation results proving each real terminal path is covered.
- Direct-caller publication race: fixed and intentionally reordered modes,
  with the direct `acquire/register_timer` path included.
- Owner-thread test: owner and worker thread outputs plus the passthrough
  decision.
- No integration PASS claim until all four receipts exist. The unresolved
  dedicated-server live `UnloadModule` question remains a separate live gate.

## Grill me

1. Why not merely add a timeout to `Placed`? Because the unbounded return is
   at `engine_k1.cpp:1057`, before `Placed`; a `Placed` timeout cannot fire when
   the state never reaches `Placed`.
2. Why is the 15/15 harness result insufficient? Because deleting the real
   `engine_k1.cpp` `end_load()` leaves the same 15/15 result; the harness does
   not link that file.
3. Why test direct callers if none are wired? Because publication ordering is
   a contract for every future caller, and the current `Machine` API exposes
   `ownership_available()` directly; the existing race test does not cover it.

Open question: which production-owned seam is cheapest for real
`GameAdapter` terminal linkage without requiring a game launch? Settle it by
building the narrowest extracted terminal helper and proving the real source
mutation turns its test red.

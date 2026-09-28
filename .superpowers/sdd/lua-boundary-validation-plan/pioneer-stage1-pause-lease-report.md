# Pioneer Stage 1: pause-lease core report

2026-09-27. Scope: the pure state machine and its host test only. There is no hook, trampoline, engine, Lua or live-game code in this unit.

Sources: `/home/brunner56/kp-live-20260922/fanout-pioneer-devtools-plan.md:24` (Stage 1) and `/home/brunner56/kp-live-20260922/pioneer-native-pause-contract.md`. The case list is at `:63`, the minimal contract at `:40-47`, and the rejection of reason1 at `:74-104`.

## Files (all new, untracked; nothing else in the worktree touched)

| File | Lines | Role |
|---|---|---|
| `src/harness/pause_lease.hpp` | 202 | `kp::harness::pause::Machine`, `NativeOps`, `Ticket`, `TimerStatus`, `Status`, `Diag`, `ToolOriginScope` |
| `src/harness/pause_lease.cpp` | 291 | the state machine |
| `tools/kp_pause_lease_test.cpp` | 570 | 22 case groups, 141 checks, with a fake CWorldTimer |
| `src/harness/pause_lease.cmake` | 29 | publishes `KP_PAUSE_LEASE_SOURCES` and defines `kp_pause_lease_test` (`-m32 -Wall -Wextra`, `add_test`) |

`git status --short` shows exactly these four as `??`. No existing file was edited, and no git staging, stash or commit was done.

## Results

The build runs from the scratch wrapper `/tmp/kp-pause-lease/CMakeLists.txt`, which does `include()` of `pause_lease.cmake` with C++20. The build dir is `/tmp/kp-pause-lease/build`.

The container has no `/lib/ld-linux.so.2`, so the 32-bit binary runs through `host-cmd`.

- **Red**, against a stub `.cpp` with the final test (`/tmp/kp-pause-lease/red_final.log`): `141 checks, 76 failures`, exit 1.
- **Green** (`/tmp/kp-pause-lease/green.log`): `141 checks, 0 failures`, exit 0. There are no compiler warnings under `-Wall -Wextra -m32`.
- **ctest** (`host-cmd ctest --test-dir /tmp/kp-pause-lease/build`): `100% tests passed, 0 tests failed out of 1`.

Mutation checks show the tests bite. Each is a sed on a copy of the `.cpp`, run against the unchanged test:

| Mutation | Failures |
|---|---|
| M1: forward a game Unpause while held | 3 |
| M2: ticket compares the pointer only (no generation or epoch) | 6 |
| M3: no origin guard on the Pause entry | 7 |
| M4: restore ignores game intent | 7 |
| M5: a tool-origin Unpause may break a lease | 2 |
| M6: no generation bump on invalidate | 1 (the per-timer epoch still catches same-address reuse, by design) |

Honest note on red-first: the first red run used an earlier fake whose `read_paused` returned nullopt for unseeded timers. The first green attempt then showed 43 failures from that test bug. The fake was fixed to read a fresh timer as running, and the red run was repeated against the final test. The 76/141 figure above is from that repeated run.

## Cases → tests (contract `:63` plus the task's own)

| Case | Test function |
|---|---|
| initially running | `initially_running` (1 Pause and 1 Unpause, with edges counted) |
| initially paused | `initially_paused` (0 native calls, pause persists) |
| game Pause after tool acquire | `game_pause_while_held` (suppressed, becomes intent, 0 Unpause at release) |
| game Unpause while held | `game_unpause_while_held` (suppressed and remembered, exactly 1 Unpause at release) |
| pause/unpause/pause sequences | `pause_unpause_pause_sequence` (P,U,P and U,P,U; last intent wins) |
| stock behaviour with no lease | `unheld_game_calls_forward` |
| two tool leases | `two_leases` |
| repeated acquire | `repeated_acquire_idempotent` |
| repeated release | `repeated_release` (AlreadyReleased, 0 calls, diag, cannot release another client's lease) |
| unknown timer passthrough | `unknown_timer_passthrough` |
| no ownership capture from tool-origin calls | `tool_origin_no_capture`: (a) the machine's originals re-enter the hook, (b) harness `ToolOriginScope`, (c) a tool Unpause on a leased timer is suppressed |
| failed hook install | `failed_hook_install` (none, pause-only, unpause-only; cannot drop a hook while leased) |
| native call fails or does not take | `acquire_native_failure` |
| pending cleanup | `pending_cleanup` (refused Unpause reports pending, retry works, a game Pause resolves it with no call) |
| epoch reset with same-address reuse; queued old release rejected | `epoch_reset_same_address` |
| no native call on an expired timer | `no_native_call_on_expired` |
| identity deduplication | `dedup` |
| cancel or disconnect of one client | `per_client_release` |
| acquire while loading; pre-load release | `load_lifecycle` |
| shutdown; failed cleanup keeps hooks | `shutdown_cases` |
| direct flag mutation is a capability failure | `external_mutation` |
| fixed tables | `table_full` |

## Decisions pinned by tests

1. **Game Pause while held is suppressed, not forwarded.** The stock original would be a no-op because +0x24 is already set. Suppressing keeps the native call count at exactly what the tool issued (`game_pause_while_held`, "no native call"). Intent is still recorded.
2. **A tool-origin Unpause on a leased timer is suppressed**, with `Diag::ToolUnpauseSuppressed`. This is the `unpause_timers()` recovery path running during a lease. A tool-origin Pause is always forwarded.
3. **The tool never calls Pause on the game's behalf.**
   - Restore calls the original Unpause only when game intent is running and the readback is paused.
   - If a raw write cleared the flag behind a lease, `verify()` reports `ExternalMutation`. The machine does not re-pause it.
4. **Acquire reads before it calls.**
   - If the flag is unreadable, acquire returns `ReadbackFailed` with 0 native calls.
   - If the Pause does not take, it returns `NativeCallFailed` and grants no lease.
   - No rollback is attempted.
5. **The hook entries are allocation-free**, using fixed `std::array` tables (16 timers × 8 leases) and counters. They are engine-thread only, with no locks.
6. **`begin_load` and `shutdown` restore only timers the tool held** (or that are pending). Other registered timers get no native call.
7. **Reason bits, SetPauseState, TogglePauseState and focus reason2 are not modelled at all.** This keeps the unit clear of blockers 1-4 in the contract appendix (`:86-96`).

## Integration snippets (NOT applied; for the later integration packet)

**1. hooksites.** `timer.pause_world_timer` and `timer.unpause_world_timer` are `kind = "call"` today (`data/hooksites.toml:821-835`). They need to become detour sites, or gain detour twins, with entry bytes `83ec08568bf18b462485c07526` and `83ec08568bf1837e24017540` (contract `:11-12`).

**2. Detour bodies** (hook_bodies.cpp style; thiscall, no stack args):
```cpp
using TimerFn = kp::hooks::ThiscallFn<void>;
std::atomic<void*> g_orig_pause_timer{nullptr}, g_orig_unpause_timer{nullptr};
kp::harness::pause::Machine* g_pause = nullptr;  // set on the engine thread

void KP_THISCALL hook_pause_world_timer(void* timer) {
    auto* orig = reinterpret_cast<TimerFn>(g_orig_pause_timer.load(std::memory_order_acquire));
    if (g_pause && g_pause->on_pause_entry(reinterpret_cast<std::uintptr_t>(timer)) ==
                       kp::harness::pause::HookDecision::Suppress) return;
    orig(timer);
}
void KP_THISCALL hook_unpause_world_timer(void* timer) {
    auto* orig = reinterpret_cast<TimerFn>(g_orig_unpause_timer.load(std::memory_order_acquire));
    if (g_pause && g_pause->on_unpause_entry(reinterpret_cast<std::uintptr_t>(timer)) ==
                       kp::harness::pause::HookDecision::Suppress) return;
    orig(timer);
}
// after HookSet::install:
g_orig_pause_timer.store(set.original("timer.pause_world_timer_entry"), std::memory_order_release);
g_orig_unpause_timer.store(set.original("timer.unpause_world_timer_entry"), std::memory_order_release);
machine.set_hooks_installed(g_orig_pause_timer.load() != nullptr, g_orig_unpause_timer.load() != nullptr);
```

**3. NativeOps over the trampolines.** `original_pause` and `original_unpause` call the stored trampoline, never the hooked entry. `read_paused` reads `lay_.timer_paused` (+0x24) via `read_int(at_offset(t, off), 4)`.

**4. Tool-origin scopes in engine_k1.cpp.** Wrap the existing hooked-entry `callv`s at `:767`, `:774` (pause), `:2109`, `:2116` (unpause_timers) and the `:2626` fixed-step bracket in `Machine::ToolOriginScope`. Without these, harness calls register as game intent.

**5. cmake.** In `CMakeLists.txt`, add `include(${CMAKE_CURRENT_SOURCE_DIR}/src/harness/pause_lease.cmake)` after `harness.cmake` (`:130`) and before `runtime.cmake` (`:132`).
- Then append `${KP_PAUSE_LEASE_SOURCES}` to `KP_HARNESS_SOURCES` or to the runtime list.
- The object basename `pause_lease` is unique (`find src -name 'pause_lease*'` shows only `src/harness`).

**6. Timer identities.** Register the timers per contract `:22-30`, deduplicated, and never every CWorldTimer. The client world/pause/animation timers come from `client.get_*_timer`. The server world/pause timers come from `server.get_world_timer` and `server.get_pause_timer`. The server timestop timer is at +0x1004c and the client timer at +0x28.

**7. Lifecycle.**
- Call `Machine::begin_load()` at a verified pre-unload boundary, before server `UnloadModule` at 0x4b9240 and client at 0x5f8290 (contract `:94`).
- Call `end_load()` and then re-register at post-load readiness.
- The console session reset maps to `release_client`.
- `shutdown()` must return `Ok` before `HookSet::uninstall()`.

## Grill me

**Q1 (weakest). Are the two hook entries really only ever reached on the engine command thread? The machine has no locks.**
Unverified. The contract says the service operates only on the engine command thread (`:42`). No evidence here shows that the game never calls PauseWorldTimer from another thread, such as a loader or audio thread. The single check that would settle it is a live detour that logs `GetCurrentThreadId()` against the server-loop thread for both entries across load, combat and modal transitions.

**Q2. Why suppress a game Pause while held instead of forwarding it? Forwarding would be "more stock".**
The stock original is a no-op when +0x24 is 1 (contract `:11`: "if nonzero returns without incrementing anything"). Suppressing therefore changes nothing physical, and it keeps the native call counts exact. The referent is `game_pause_while_held`, where the "no native call" check passes.
The one unproven exception: during a lease, a raw write could clear the flag behind the machine's back. Forwarding would then re-pause the timer, and suppressing does not. That situation is already surfaced as `ExternalMutation` by `verify()`, which is the `external_mutation` test.

**Q3. Could a tool-origin Unpause being suppressed wedge `unpause_timers()` recovery?**
Only while a lease is held, and that is intended: recovery must not break a lease. The referent is `tool_origin_no_capture` (c), which passes, and M5 shows 2 failures when the rule is removed.
Recovery still works once the leases are released. Whether recovery should force-release leases first is an integration policy call, and it is unverified here.

**Q4. Does the per-timer epoch make the generation redundant?**
Partly. M6 (no generation bump) fails only 1 check, because `next_epoch_` is monotonic across the Machine's lifetime. The generation is kept because the contract asks for a load generation on the lease (`:42`), and because it rejects a stale ticket even for a timer that was never re-registered.

**Q5. Is restore's "readback before Unpause" safe if the flag read races the original?**
It is single-threaded by assumption (see Q1). Any hook re-entry during the tool's own original call runs under `ToolOriginScope`, so it is treated as tool origin and never becomes game intent. The referent is `tool_origin_no_capture` (a).
The consequence: if the original UnpauseWorldTimer ever called PauseWorldTimer internally, that call would not be recorded as game intent. From the ABI (contract `:12`) it does not appear to, but that is unverified here. The re-check of `s.game_intent` after the call in `restore()` is defensive, and no test drives it.

**Could not settle here:** Q1, the thread affinity of both entries. The single check that settles it is a live thread-id log on both detours.

---

# Round 2 (review response)

This answers `/home/brunner56/kp-live-20260922/pause-lease-core-review.md` (FAIL, F1-F7). The allowed files are the same as round 1, and nothing outside them was edited.

The code notes in round 1's Q3 and in snippets 4 and 7 are superseded by this section.

## Outputs (actual)

**Red, round-2 tests against the round-1 core** (`/tmp/kp-pause-lease/red2.keep`):
```
188 checks, 23 failures
```
The failing checks cover F1 (R1, R3, verify drift), F3 (R4), F4 (R5), F5 (R6), F6 (R7) and F7 (acquire_all).

R2 and `reseed_not_during_pending` pass on the old core as well. They pin the game-path recovery pattern and the "no reseed while pending" boundary, which were already correct.

**Green** (`/tmp/kp-pause-lease/green2.log`, `-m32 -Wall -Wextra`, run through `host-cmd`):
```
188 checks, 0 failures
```
ctest reports `100% tests passed, 0 tests failed out of 1`.

**The reviewer's `repro.cpp` against the new core** (`/tmp/kp-pause-lease/r2_repro.out`, built with `-Werror`):
```
R1 after recovery: physical=0 machine.game_intent=1
R1 after acquire+release: physical=0 (was running before acquire), pause calls=1 unpause calls=2
R2 recovery-while-held then release: physical=1 intent=1
R3 register-before-hooks: physical=0 (was running before acquire)
R4 game Pause after external clear: physical=1 intent=1 leases=1 (both want paused)
R5 ownership_available after reporting hooks removed while leased: 1
R6 begin_load failing restore: status=cleanup_incomplete, tracked after=0, physical=1
R7 acquire after shutdown: shut_down
```
What each line shows:
- **R1 and R3** are now fixed: release restores running.
- **R2 still prints `physical=1`.** This is by design. `repro.cpp` still wraps the recovery in `ToolOriginScope`, which F2 now forbids. The same sequence on the game path is test `r2_recovery_on_game_path_while_held`: 1 Unpause at release, and the timer runs.
- **R4** is fixed.
- **R5 prints 1** because `repro.cpp` ignores the new return value. The call now returns `LeasesHeld` and leaves the state unchanged (test `r5_set_hooks_status`).
- **R6** still shows `tracked after=0` in the repro. The failure is now retained in `load_cleanup_failures()` (test `r6_begin_load_failure_kept`).
- **R7** is fixed.

**The reviewer's fuzzers against the new core** (20000 seeds × 400 steps each; `/tmp/kp-pause-lease/r2_*.out`):

| Probe | mode A | mode B |
|---|---|---|
| `fuzz_unleased_recovery.cpp` (the reviewer's F1 drift probe; recovery only while unleased) | 0 | **0** |
| `fuzz_gamepath.cpp` (`fuzz.cpp` with case 9 on the game path; the only change is a one-line sed that drops `ToolOriginScope` at :147) | 0 | **0** |
| `fuzz.cpp` unchanged (case 9 = recovery inside `ToolOriginScope`, including while leased) | 0 | 19645 |

The 19645 comes from `fuzz.cpp` case 9 calling a scoped recovery while a lease is held. Its reference model treats that call as a game override. After F2 that usage is forbidden, and a scoped Unpause on a leased timer is deliberately suppressed and not recorded.

This is a residual, not a clean pass. Two things show it is only that case:
- The same probe gives 0 when the leased scoped recovery is skipped (`fuzz_unleased_recovery`) or routed through the game path (`fuzz_gamepath`).
- All 19058 printed first divergences are downstream call-count mismatches: `begin_load calls` 15290, `release_client calls` 3232 and `release calls` 536.

A one-line alternative would make unchanged `fuzz.cpp` pass as well: a scoped Unpause could record intent=false. See Grill me Q1.

## Fixes

- **F1.** `acquire` now reseeds `game_intent` from the flag when `count()==0 && !pending_cleanup` (pause_lease.cpp, inside `acquire`). It bumps `Diag::IntentReseeded`. `verify()` now also reports `IntentDrift` for an unleased, non-pending timer. It reports only and does not reseed.
  - Tests: `r1_unobserved_unpause_reseeded`, `r3_register_before_hooks`, `reseed_not_during_pending`, `verify_intent_drift`.
- **F2.** The `ToolOriginScope` doc (hpp) now limits the scope to net-zero brackets, meaning only the fixed-step bracket. It states explicitly that recovery `unpause_timers` and the load_save step-3 pauses go through the game path. The cpp rule comment matches.
  - Test: `r2_recovery_on_game_path_while_held`.
- **F3.** A game Pause on a held timer whose flag reads clear is forwarded, with `Diag::GamePauseRepaired`. While the flag is set it is still suppressed, so the stock no-op keeps exact counts. That also matches the fuzz reference, which expects 0 calls while held.
  - Test: `r4_game_pause_repairs_external_clear`.
- **F4.** `set_hooks_installed` returns `Status` (`Ok` or `LeasesHeld`).
  - Test: `r5_set_hooks_status`.
- **F5.** When `begin_load` cannot restore a held timer, it records `{timer, generation}` in `load_cleanup_failures()`, a fixed 16-entry list, and bumps `Diag::LoadCleanupFailed`. There is still no native call on that pointer afterwards.
  - Test: `r6_begin_load_failure_kept`.
- **F6.** `shutdown()` latches. After it, `acquire` and `register_timer` return `ShutDown`, and `retry_cleanup` still works.
  - Test: `r7_shutdown_latch`.
- **F7.** New `acquire_all(key, span<TimerId>, span<Ticket>, size_t* failed_index)`. It is all-or-nothing: on a failure it releases, in reverse, only the leases this call added, and keeps any lease the key already held.
  - Test: `f7_acquire_all`. A failure on the third timer rolls back the second (1 Pause + 1 Unpause), keeps the first timer's earlier lease, and refuses an `out` span that is too small.

## Corrected integration snippets (supersede round-1 snippets 4 and 7)

**4'. Tool-origin scopes in engine_k1.cpp.**
- Wrap **only** the fixed-step bracket in `ToolOriginScope`. That bracket is `if (!was_paused) callv(pause)` at **:2654** and `callv(unpause)` at **:2656** (not :2626, which is the `require` line). It nets to zero, and on a held timer `was_paused` is true, so it makes no call.
- Do **not** wrap `unpause_timers` at :2109 or :2116. It is an operator override and goes through the game path:
  - With no lease, it is forwarded and intent becomes running.
  - With a lease held, it is suppressed, intent becomes running, and it is applied once at the last release.
- Do **not** wrap load_save step 3 at :767 or :774 either.

**7'. Lifecycle.**
- Call `machine.begin_load()` at the **top of `GameAdapter::load_save`** (engine_k1.cpp:679), before the step-3 pauses at :767 and :774. The native unload only happens after steps 4-8.
- **Also** call it at a verified pre-UnloadModule boundary for loads the game starts itself: server 0x4b9240, client 0x5f8290.
- Call `end_load()` and re-register at post-load readiness.
- The console session reset maps to `release_client`.
- `shutdown()` must return `Ok`, and `set_hooks_installed(false,false)` must return `Ok`, before `HookSet::uninstall()`. If either does not, keep the hooks.
- A "pause world" command uses `acquire_all` over the deduplicated timer list.

Snippet 2 needs one amendment: null-check `orig` before calling it, and publish `g_pause` before `set_hooks_installed(true,true)`. These are the reviewer's threading points 3 and 4.

## Grill me (round 2)

**Q1 (weakest). Why keep a scoped Unpause on a leased timer "suppressed and not recorded" when recording intent=false would make unchanged `fuzz.cpp` pass and would make misuse harmless?**
The criterion is your explicit instruction ("tool calls never register as game ownership") together with the coordinator's F2 direction (recovery is not tool origin).
- The only prescribed scope user is the fixed-step bracket. It never unpauses a held timer, because `was_paused` is true at :2654 and :2656 (see the grep output above).
- So neither rule changes any legal path. Recording would only change behaviour under misuse.
- The referents are `tool_origin_no_capture` (c) and `fuzz_gamepath` mode B = 0.
- If the reviewer prefers the misuse-safe rule, it is one line in `on_unpause_entry` (set `s->game_intent = false` before `Suppress`), plus flipping one test check. That makes it cheap to reverse.

**Q2. Could the F1 reseed wrongly absorb a tool pause as game intent?**
Only if the flag is set by the tool while the timer holds no lease and has no pending restore.
- The machine's own Pause happens only inside `acquire`, after the reseed read, with the lease then taken.
- A net-zero bracket returns the flag to its prior value before any acquire, because the run is single-threaded.
- A stuck restore is excluded by the `!pending_cleanup` guard (test `reseed_not_during_pending`).
- The fuzz probes give 0/20000 in both modes.

**Q3. F3 now reads the flag inside the Pause hook. Is that still hook-safe?**
It is one 4-byte field read (`read_paused` becomes `read_int(t+0x24)` in the integration), with no allocation or lock. It runs only for a held timer.
It is not measured live, so it is unverified for latency. The same read already happens in `status()` and `verify()`.

**Q4. Is `load_cleanup_failures()` capped, and is it ever cleared?**
It is capped at 16 entries and never cleared. The list only grows across the Machine's lifetime and stops recording once full; the `Diag::LoadCleanupFailed` counter keeps counting. No test covers the cap. A clear API is left for integration to decide.

**Q5. Thread affinity of both detours (carried over from round 1 Q1).**
Still unresolved. The one check: a live `GetCurrentThreadId()` log on both detours against the server-loop thread across load, autopause, modal and focus loss.

**Could not settle here:** Q5, same as round 1. Q1 is a policy choice between two options that are both one line to reverse, handed to the reviewer.

# Round 3 (review response)

This round answers `/home/brunner56/kp-live-20260922/pause-lease-r2-review.md` (FAIL: F8, Grill #1, stale test comments) and applies the orchestrator's four rulings.
- Only the allowed files changed: `pause_lease.cpp`, `pause_lease.hpp`, the test, and this report. `pause_lease.cmake` is unchanged (sha 382109d2).
- There was no game run, no git write, and the live-game lock was not touched.
- Scratch and outputs are in `/home/brunner56/kp-live-20260922/r3/`, and `TMPDIR=/home/brunner56/kp-live-20260922/tmp-pause-lease`.
- Every run used host-side redirection: `host-cmd sh -c '... > file'`.

SHA-256 prefixes:

| File | Prefix |
|---|---|
| `pause_lease.cpp` | bacd1b7d |
| `pause_lease.hpp` | 63e21bc9 |
| `pause_lease.cmake` | 382109d2 |
| `kp_pause_lease_test.cpp` | e8750ef6 |

## Outputs (actual)

Build flags: `g++ -std=c++20 -O2 -m32 -Wall -Wextra -Werror`, run through `host-cmd`. The binary header is `7f 45 4c 46 01 … 02 00 03 00`, which is ELFCLASS32 and EM_386.

| Run | Result | File |
|---|---|---|
| Red: round-3 tests on the round-2 core | 219 checks, **4 failures**, all S1/S2 "recorded running" and "release: 1 Unpause, running" | `r3/red3.out` |
| Green | **219 checks, 0 failures**, rc=0 | `r3/green3.out` |
| `fuzz.cpp`, unchanged | mode A 0, mode B **0** (was 19645) | `r3/fuzz.out` |
| `fuzz_bracket_scopedrec.cpp` (scoped recovery) | mode A 0, mode B **0** (was 19494) | `r3/fuzz_bracket_scopedrec.out` |
| `fuzz_unleased_recovery.cpp` | 0 / 0 | `r3/fuzz_unleased_recovery.out` |
| `fuzz_gamepath.cpp` | 0 / 0 | `r3/fuzz_gamepath.out` |
| `fuzz_bracket_gamerec.cpp` | 0 / 0 | `r3/fuzz_bracket_gamerec.out` |
| `scenarios.cpp` S1–S5 | identical to the reviewer's `scen_var.out` apart from the `rc=0` line the r3 runner appends (`diff` against `scen_var.out` + that line is empty). S1 physical=0 = tool-absent. | `r3/scenarios.out` |

All five fuzzers ran 20000 seeds × 400 steps per mode. They are built from the reviewer's `.cpp` files, unchanged, against the worktree core rather than the reviewer's `cur/` or `var/` copies. Each `.out` holds both the mode A and the mode B line, plus rc=0.

The mutations below were run against the round-3 test (`r3/mut/*.out`):

| Mutation | Result |
|---|---|
| `end_load` made a no-op | 5 failures |
| `invalidate` without `++generation_` | 2 failures |
| Round-2 core (the one line reverted) | 4 failures (= red) |

## Fixes

**Ruling 1: the Grill #1 rule.**
- `on_unpause_entry` now sets `s->game_intent = false;` in the tool-origin branch, before the Suppress on a held timer.
- `diff` against the reviewer's `var/harness/pause_lease.cpp` differs only in comments.
- Docs updated to state that a tool-origin Unpause records running and never records paused:
  - hpp `ToolOriginScope`
  - the cpp rules block
  - test (c)'s check label
- New tests, all starting from a **game-paused** timer:

| Test | Scenario | Checks |
|---|---|---|
| `r3_s1_scoped_recovery_misuse` | Misuse: recovery wrapped in scope while held | Suppressed, `ToolUnpauseSuppressed`=1, intent running. Release gives exactly 1 Unpause and a running timer (= tool-absent). |
| `r3_legal_bracket_on_paused_held` | Correct usage | 0 calls, and the timer stays paused after release. |
| `r3_s2_bracket_after_external_clear` | Legal bracket after a raw clear | Release gives 1 Unpause and a running timer (= tool-absent). |
| `r3_s4_game_pause_after_bracket` | S2, then a game Pause | The timer stays paused. |

**Ruling 2: F8 at core level.** `r3_f8_load_without_end_is_bounded` covers a `begin_load` with no `end_load`:
- acquire and register return `Loading`, and the old ticket is stale.
- Hooks pass through (`UnknownTimerHook`) and act stock.
- A second `begin_load` returns Ok with 0 native calls and bumps the generation again.
- One `end_load` recovers. Re-register seeds from the live flag: T1 paused by step 3 seeds paused. A later acquire and release then makes 0 native calls and stays paused (= tool-absent).

This test is a **pin, not red-first**. It passes on the round-2 core as well, because F8 is an integration-placement bug and not a core bug. It bites under the two mutations above.

The core bound is this: while loading, the machine holds no identity and makes no native call. The only lasting effect is that acquire and register are refused. The integration must clear that with `end_load()`, and snippet 7'' does it. There is deliberately no core timeout.

**Ruling 3.** Test comments:
- :280 now says the scope is only the net-zero fixed-step bracket, and that recovery is not scoped.
- :300 now says "scoped Unpause (bracket half); never recovery".
- The r1 check label "1 recovery" is now "1 scoped".
- `grep -n recovery tools/kp_pause_lease_test.cpp` shows no remaining line that calls a scoped call recovery. The r3_s1 test names the misuse as misuse.

## Integration snippet 7'' (supersedes 7')

- **Where to call `begin_load`.** Call `machine.begin_load()` in `GameAdapter::load_save` **after the last validating return**. That is directly after `if (sapp == 0) return Result::fail("load_save: no server after CreateServer");` (engine_k1.cpp:757-758) and before the step-3 pauses at :767 and :774.
  - The earlier returns never reach it: :681, :690, :693, :702, :730 and :758.
- **Call `on_fail()` explicitly before each failure return after `begin_load`.** There is no scope-exit helper in `src` (`grep -rn scope_exit src` finds nothing), so nothing runs it automatically. The four returns are:
  - :794 net_layer
  - :795 message_handler
  - :820 StartConnectToSession
  - :873 SendLoadGameRequest
  - `awk` over :759-884 shows no other `return` in :827-856.
  ```cpp
  machine.begin_load();
  auto on_fail = [&] {
      machine.end_load();                    // FIRST: register_timer refuses while loading
      reregister_timers();                   // re-fetch from client.get_*_timer / server.get_*_timer;
  };                                         // never reuse cached TimerIds
  ...
  if (!net || *net == 0) { on_fail(); return Result::fail("load_save: client.net_layer not readable"); }
  // same at :795, :820, :873
  ...
  // :787 dedicated branch -- UNVERIFIED: call end_load here only if the native
  // pre-UnloadModule begin_load (server 0x4b9240) is wired; otherwise the clear
  // point is open (Grill me Q1). Leaving loading_ set here is F8 on this branch.
  ...
  // :884 success: do NOT end_load here; see the step_load_completion terminals below.
  ```
  After a failed load the timers are still the old, live objects, so re-registering is correct. The step-3 pauses passed through, and re-registration seeds them as paused, which is exactly what the stock harness leaves behind. The core pins this in `r3_f8_load_without_end_is_bounded`.
- **Success path (:884).** `end_load()` then re-register must fire on **every terminal state** of `step_load_completion`, not only Done:
  - `GaveUp` at :996, :1038 and :1062
  - `Done`/`GaveUp` at :1015 and :1054
  - Missing any `GaveUp` path brings F8 back, late.
- **Dedicated-server branch (:787). Unverified.** This branch returns success right after step 3 and then waits for the remote client's load request. I did not find where the server role completes that load. Calling `end_load` at :787 is safe only if the native pre-UnloadModule `begin_load` (server 0x4b9240) is wired, because that call re-invalidates before the real unload. Without it, `loading_` has no known clear point on this branch.
  - The check that settles it: find the server-side completion of the remote client's LoadGameRequest (or the module-loaded event on the server role) and put `end_load` there.
- The native pre-UnloadModule `begin_load` (server 0x4b9240, client 0x5f8290) stays. A second `begin_load` is harmless: 0 native calls, pinned by the r3_f8 test.
- Unchanged from 7':
  - `release_client` on session reset
  - `shutdown()` and `set_hooks_installed(false,false)` must both return `Ok` before `HookSet::uninstall()`
  - `acquire_all` for "pause world"

## Threading (ruling 4, restated for the integration packet)

- The socket/channel thread (`channel.cpp:208`, `thread_ = std::thread([this] { run(); })`) **only queues work**. Every `Machine` call, including acquire, release and `release_client`, runs on the engine command thread when the queue drains.
- `ToolOriginScope`'s depth counter (`tool_depth_`) is a **plain member, not per-thread** (hpp `int tool_depth_ = 0;`). A hook entry on another thread would read the engine thread's depth. So all integrated calls must be on the engine thread: both detours, the fixed-step bracket, `unpause_timers`, the load_save steps and every `Machine` method.
- Snippet 2's amendments still apply: null-check `orig`, and publish `g_pause` before `set_hooks_installed(true,true)`.
- Live proof is still open: a `GetCurrentThreadId()` log on both detours, compared against the server-loop thread (hook_bodies.cpp:770 and :1279).

## Grill me (round 3)

**Q1 (weakest). Where does `end_load` fire on the dedicated-server branch?**
Unverified. :787 returns success and waits for a remote client. I did not locate the server-role load completion. `end_load` at :787 is safe only together with the native pre-UnloadModule `begin_load` at 0x4b9240. The check that settles it: find the server-side completion of the remote LoadGameRequest.

**Q2. Does every late-failure path after a successful `load_save` reach `end_load`?**
Only if the integration hooks all `step_load_completion` terminal writes: `GaveUp` at :996, :1038 and :1062, and `Done`/`GaveUp` at :1015 and :1054. The source is `grep -n "LoadStep::" src/harness/engine_k1.cpp`. The core cannot enforce this; it is integration-only, so it is unverified until the integration lands.

**Q3. Why is recording "running" from a tool-origin call consistent with "tool calls never become game ownership"?**
The call is still suppressed, so it cannot break a lease, and it can only ever record *running*, never paused. It therefore cannot strand the world paused, which is the capture the contract's :44 forbids.
- Referents: `r3_s1_scoped_recovery_misuse` and `r3_s2_bracket_after_external_clear` (both = tool-absent); `scenarios.out` S1–S5 identical to `scen_var.out`; unchanged `fuzz.cpp` mode B 19645 → 0.
- If the user reads :44 as "no intent write at all", reverting is one line. The r3_s1 and r3_s2 checks then fail (4 failures, `red3.out`).

**Q4. Is the F8 core test just re-proving existing behaviour?**
Yes, deliberately: F8 was placement, not core. It pins the recovery contract that integration now relies on: one `end_load`, then re-register, then 0 native calls. It is not red-first. The referent is the two mutations (5 and 2 failures).

**Q5. Could the one-line change alter any path that was legal before?**
Only a tool-origin Unpause on a held timer reaches it. The machine's own `restore` Unpause runs after the lease count reaches 0, so it takes the passthrough branch.
- Referents: `fuzz_gamepath`, `fuzz_bracket_gamerec` and `fuzz_unleased_recovery` are 0/0; `r3_legal_bracket_on_paused_held` makes 0 calls.

**Could not settle here:** the dedicated-server `end_load` point (Q1), and thread affinity of the game's own Pause/Unpause callers. Both need the live checks named above.

---

# Round 4 — integration snippets

Report-only: **the core is closed and unchanged.** Nothing under `src/**` in
this worktree was touched. `git status --short` in the worktree still shows
only the same four `??` files as round 3, and their sha256 prefixes are
unchanged: `pause_lease.cpp` bacd1b7d, `pause_lease.hpp` 63e21bc9,
`pause_lease.cmake` 382109d2, `kp_pause_lease_test.cpp` e8750ef6.

All proof work ran against a **scratch copy** of the whole tree at
`/home/brunner56/kp-live-20260922/pl4-scratch/` (never the worktree),
`TMPDIR=/home/brunner56/kp-live-20260922/tmp-pl4`. The scratch copy's
`pause_lease.*`/test files were re-checked against the same four sha256
prefixes above before any patch was applied, to confirm the copy started
from exactly the closed core. `git worktree`/`git stash`/any git write was
not used; the copy is a plain `rsync`.

Every host command ran through `host-cmd`, matching round 3's convention.
Toolchains found on the host: `g++` (GCC 16.2.1, `-m32` works and runs under
`host-cmd`) and `i686-w64-mingw32-g++` (Fedora MinGW 16.1.1, reachable via
`/usr/lib64/ccache/i686-w64-mingw32-g++`, not on `$PATH` directly).
ThreadSanitizer does not link on this host (below); Helgrind (`valgrind
3.27.1`, already installed) stood in, with the caveat stated in Q2.

## Q1. The dedicated-server `end_load` wedge

Traced fully against the scratch copy of `src/harness/engine_k1.cpp` before
touching anything (line numbers below are from that file, unpatched, and
match round 3's review exactly): `grep -n "load_step_ = \|^Result
GameAdapter::load_save\|return Result::fail\|return Result::success"` plus
`grep -n "LoadStep::"` over the whole file.

**Every terminal path of `load_save()` / `step_load_completion()`, enumerated:**

| Site | What it is | Pre-patch `end_load` calls | Post-patch |
|---|---|---|---|
| `:695 :707 :716 :744 :772` | Returns before the last validating check | 0 (never reaches `begin_load`) | 0, unchanged — `begin_load()` now sits right after `:772`'s check, so these five still never reach it |
| `:772`→`begin_load()` | Insertion point (after `if (sapp == 0) return ...;`, before the step-3 pauses) | n/a | `pause_machine_.begin_load()` added here |
| dedicated-server branch (`if (dedicated_server) { ...; return Result::success(); }`) | Server role prepares the save and waits for a remote client | **0 — confirmed wedge.** `load_step_` only reaches `Armed`/`Sent`/`Placed` on the `!dedicated_server` path (`:895` `Armed`, `:1075` `Sent`, both unreachable here), and `step_load_completion()` early-returns for anything but those three states (`:1007-1009`). `grep -rn "load_step_" src/harness/engine_k1.cpp` shows no other writer; `grep -rln "0x4b9240" src/` finds no wired hook. So nothing in the tree ever called `end_load` for this role. | **1, unconditional.** `pause_machine_.end_load()` added directly before the `return Result::success();`. This is the fix, not a footnote: until the native pre-UnloadModule `begin_load` at server `0x4b9240` is wired, a lease taken on this branch is not protected across the remote-driven `UnloadModule` that follows — stated as a residual below and in Grill me Q1, not left implicit. |
| `!net \|\| *net == 0` (`client.net_layer` unreadable) | `!had_server` sub-block, first failure | 0 (bare `return Result::fail`) | 1, via `on_fail()` |
| `!handler \|\| *handler == 0` (`client.message_handler` unreadable) | same sub-block | 0 | 1, via `on_fail()` |
| `StartConnectToSession` refused | same sub-block | 0 | 1, via `on_fail()` |
| `SendLoadGameRequest not callable` | after step 8/9 | 0 | 1, via `on_fail()` |
| success return after step 10 (`load_step_ = Armed`) | not a failure; the load is now in flight | 0 (correct — the load is not done) | 0, unchanged |
| `step_load_completion()` `GaveUp` (20s AreaLoaded timeout) | terminal | 0 — this is F8's other face: a load that legitimately times out never called `end_load` either, pre-patch | 1, via `finish_load(GaveUp)` |
| `step_load_completion()` `Done`/`GaveUp` (client finished, `retire_main_menu()`) | terminal | 0 | 1, via `finish_load(...)` |
| `step_load_completion()` `GaveUp` (300s "placed but area never ready") | terminal | 0 | 1, via `finish_load(GaveUp)` |
| `step_load_completion()` `Done`/`GaveUp` (native load completed normally) | terminal | 0 | 1, via `finish_load(...)` |
| `step_load_completion()` `GaveUp` (no control object, `msg.area_loaded` unresolved) | terminal | 0 | 1, via `finish_load(GaveUp)` |

**The fix, applied to the scratch copy only** (`src/harness/engine_k1.cpp`,
`src/harness/fields.hpp`):
- `begin_load()` right after `:772`'s check (unchanged insertion point from
  round 3's snippet 7'').
- `auto on_fail = [&](const char* why) { pause_machine_.end_load(); ...;
  return Result::fail(why); };` — every one of the four failure returns
  after `begin_load()` now goes through it, so "exactly once per failure
  path" is a property of one function, not four separately-maintained call
  sites.
- The dedicated-server branch gets its own unconditional `end_load()` — the
  actual Q1 fix, see the table row above.
- `void GameAdapter::finish_load(LoadStep terminal)` is the single place
  every `step_load_completion()` terminal write now goes through
  (`load_step_ = terminal; pause_machine_.end_load(); ...`). The five
  scattered `load_step_ = LoadStep::GaveUp` / `retire_main_menu() ? Done :
  GaveUp` assignments were replaced with calls to it, so a future terminal
  state added to the enum can't silently skip `end_load` the way the
  dedicated-server branch did.

**Re-entrancy, stated rather than solved.** `load_save()` can run again
while a previous load is still `Armed`/`Sent`/`Placed` (nothing in the
current tree prevents it). `load_step_` is one `GameAdapter` member, so the
second call's `:895`-equivalent write (`Idle` reset, unconditional, before
the new `Armed`) overwrites the first load's step tracking without ever
reaching one of its own terminal writes. This does **not** wedge `loading_`:
`pause_lease.hpp:167` — `void end_load() { loading_ = false; }` — is a level
write, not a counter, and `begin_load()` (`pause_lease.cpp:306-323`) is
documented as safe to call twice (bumps `generation_`, restores held
timers, harmless — this is exactly what round 3's own
`r3_f8_load_without_end_is_bounded` test already pins). The only thing lost
is the *first* load's own step-machine bookkeeping, not lease safety. Not
fixed here because it is a pre-existing, separate question (what should a
re-entrant `load_save()` even mean) outside the round-4 brief.

**Host-side proof.** The patched `engine_k1.cpp` (plus `fields.hpp`, which
gained a `pause::Machine pause_machine_` member, `int end_load_calls_`, and
the `finish_load` declaration) compiles clean, `-Wall -Wextra`, both
toolchains:

| Build | Result | File |
|---|---|---|
| `i686-w64-mingw32-g++ -std=c++20 -Wall -Wextra -fsyntax-only` | clean, `RC=0` | `round4-out/engine_k1_mingw_syntax.log` |
| `i686-w64-mingw32-g++ -std=c++20 -Wall -Wextra -c` (real object) | clean, `RC=0`, `.o` produced | `round4-out/engine_k1_mingw_build.log` |
| `g++ -std=c++20 -m32 -Wall -Wextra -Werror -c` (real object) | clean, `RC=0`, `.o` produced | `round4-out/engine_k1_m32_build.log` |
| `runtime.cpp`, `dllmain.cpp` — untouched, MinGW `-fsyntax-only` | both clean, `RC=0` | `round4-out/runtime_cpp_mingw_syntax.log`, `dllmain_cpp_mingw_syntax.log` |

The syntax-only check was itself checked (not assumed to be doing real
work): an injected bogus call at the old `:761` was caught (`error:
'this_is_a_bogus_call_to_prove_syntax_check_works' was not declared in this
scope`), then removed before any of the runs above.

Because `GameAdapter::load_save()` needs a live address table, a real
client/server app pair and the hook-shape machinery to actually execute,
it is not host-runnable standalone. The behavioral half of this proof is
`tools/kp_load_terminal_harness.cpp`, which drives every row of the table
above against the **real** `pause_lease::Machine` (not a stand-in — same
sha256-pinned core), mapped to the patched file by file:line in the source
comment:

```
15 checks, 0 failures
```
(`round4-out/load_terminal_harness_m32.out`, built
`g++ -std=c++20 -m32 -Wall -Wextra -Werror`, matching the reviewer's flags;
also builds clean under `i686-w64-mingw32-g++`,
`round4-out/load_terminal_harness_mingw_build.log`.)

## Q2. `g_pause` thread affinity and publish ordering

**Confirmed, independently, before proposing a fix:** `run_startup()`
(`dllmain.cpp:36-42`) runs on the DllMain `CreateThread` worker
(`dllmain.cpp:60-70`), and calls `Runtime::instance().start(cfg)`
(`runtime.cpp:781`), which calls `install(...)` (`runtime.cpp:796`) on that
same worker thread — not the engine thread. `runtime.cpp:629-630`'s own
comment already says as much ("The hooked vm.run_script can start firing on
the game's own thread the moment install() patches it in"). So round 3's
snippet-2 comment — `kp::harness::pause::Machine* g_pause = nullptr; //
set on the engine thread` — is wrong about where it runs, confirmed
independently rather than taken on the review's word.

**The fix.** `g_pause` becomes `std::atomic<Machine*>`, matching the house
pattern at `engine_k1.cpp:70,78,88,141` (`g_orig_set_game_speed`:
`std::atomic<void*>`, release-store after install, acquire-load in the hook
body, null-checked before use). The revised snippet is
`src/harness/pause_lease_snippet2.cpp` in the scratch tree (not part of any
cmake target — the two detour sites aren't in `hooksites.toml` yet, so
nothing wires it in; it is a standalone compile-and-link proof only).

**The ordering correction, and why round 3's text has it backwards.**
Round 3 said: "publish `g_pause` before `set_hooks_installed(true,true)`."
Tracing what `set_hooks_installed` touches
(`pause_lease.cpp:67-76`) shows why that's the wrong order once you know
install runs on a different thread than the hooks fire on:

- `set_hooks_installed` writes two **plain, non-atomic** `bool` members,
  `pause_hook_`/`unpause_hook_`.
- `ownership_available()` (`pause_lease.hpp:126`, `return pause_hook_ &&
  unpause_hook_;`) reads them, and gates both `on_pause_entry` and
  `on_unpause_entry` (`pause_lease.cpp:238, 272`) — when it's `false`
  (hooks not yet marked installed), both hook entries harmlessly `Forward`,
  same as if `g_pause` were still null. Confirmed by reading the source,
  not assumed.
- A release-store/acquire-load pair on one atomic (`g_pause`) only
  publishes the writes that happened **before that specific store**, in
  program order on the releasing thread ([intro.races], the standard
  release-acquire happens-before rule). If the store runs *before*
  `set_hooks_installed`, the engine thread's acquire-load of a non-null
  `g_pause` carries **no visibility guarantee** for `pause_hook_`/
  `unpause_hook_` — a plain bool being written on one thread and read on
  another with no such guarantee is a data race (UB) under the C++ memory
  model, independent of whether `ownership_available()` happens to read
  `false` in practice and no visible harm results.
- So the store must be the **last** write the worker thread makes:
  `set_hooks_installed(...)` first, `g_pause.store(&machine, release)`
  last. This is the standard "publish a fully-initialized object through
  one pointer" pattern, and it does not introduce a new failure mode
  relative to round 3's order — `ownership_available()` already treats
  "not installed yet" as harmless — it just makes the harmless case the
  *only* case that can be observed, instead of leaving a genuine data race
  that happened to look harmless.

**The guard `tool_depth_` needs, since it's still unproven.** The core's own
contract (`pause_lease.hpp:15-17`) says "engine command thread only,
including the two hook entries. No locks." Nothing in the tree can violate
that today — `grep -rn "Machine::\|pause_lease\|g_pause"
src/harness/channel.cpp` is empty; the socket/channel thread only queues
work, and the core isn't wired into any hook body yet, so this is
vacuously true. Once the two hooks are wired, the promise is only as good
as an explicit guard, so the revised snippet adds one: an owner-thread
check (`g_owner_thread`, set once at publish time, compared with
`std::this_thread::get_id()`) in the hook body. A call from any other
thread gets a plain passthrough to `orig`, untouched by the Machine, plus a
counter (`g_off_thread_hook_calls`) so a live run can show whether the
guard was ever exercised — this is the guard, not a claim that the
violation can't happen.

**Who calls what, on which thread — checked against the source, not
assumed:**

| Call | Thread | Referent |
|---|---|---|
| `on_pause_entry` / `on_unpause_entry` (hook bodies) | the game's own caller (unproven to always be the engine thread — Q1 in round 1, still open) | `pause_lease.hpp:15-17` states the requirement; nothing enforces it |
| `set_hooks_installed(true,true)`, the `g_orig_*` stores, `g_pause` publish | the DllMain `CreateThread` worker | `dllmain.cpp:60-70` → `run_startup` → `runtime.cpp:781,796` |
| `acquire`, `release`, `release_client`, `acquire_all`, `begin_load`, `end_load`, `register_timer` | the engine command thread, once integrated (round 3's report, "Threading" section) | `channel.cpp:208` — the socket thread only queues; nothing calls `Machine::` from it |
| `shutdown()`, `set_hooks_installed(false,false)` | **undetermined.** `Runtime::stop()` exists (`runtime.cpp:854`) but `grep -rn "\.stop()" src/` finds no caller anywhere in the tree today | open, same as round 3 left it |

**Why `tool_depth_` being a plain (non-per-thread) member is still safe, for
now:** it is read/written only from inside `on_pause_entry`/
`on_unpause_entry` and `ToolOriginScope`, and per the table above, nothing
but the game's own caller (today, vacuously no caller at all) reaches
those. It becomes unsafe the moment a second thread can call a `Machine`
method — which is exactly the failure mode the owner-thread guard above
exists to catch, since the contract has no lock to fall back on.

**Host-side proof, and its limit.** `-fsanitize=thread` does not link on
this host:
```
/home/linuxbrew/.linuxbrew/Cellar/binutils/2.47/bin/ld: cannot find /usr/lib64/libtsan.so.2.0.0: No such file or directory
```
confirmed not a linker-choice problem (`-B/usr/bin` reproduces the same
error against `/usr/bin/ld.bfd`); `dnf provides "*/libtsan.so.2*"` finds no
package that ships it. No i386 TSAN runtime exists either, as expected. So
this is proven with `valgrind --tool=helgrind` (already installed) instead,
against three builds of `tools/kp_pause_publish_race_test.cpp` selected by
`-DMODE`: `0` = plain `Machine*`, no fence; `1` = atomic `g_pause` but
published **before** `set_hooks_installed` (round 3's literal order); `2` =
atomic, published **after**, last (the fix). Each mode runs 400 cycles of
"one worker does the one-time install sequence, one engine thread busy-
waits for the publish and makes the two real hook-body calls" — isolating
the one-time publish-ordering question rather than a steady-state
concurrent-call hazard (an earlier draft of this harness conflated the two
and made mode 2 look racy for an unrelated reason; the report's git history
of the draft is in `round4-out/`, kept rather than deleted, per the point
below).

```
MODE 0: 3 race contexts (1200 errors) — includes a race on g_pause_plain itself
MODE 1: 2 race contexts (800 errors)  — both on pause_hook_/unpause_hook_
MODE 2: 2 race contexts (800 errors)  — both on pause_hook_/unpause_hook_
```
(`round4-out/pause_race_mode{0,1,2}_helgrind.log`.)

**What this does and does not show.** MODE 0 is empirically worse than 1/2:
Helgrind flags an extra race on the raw pointer read itself
(`kp_pause_publish_race_test.cpp:89`, absent from both atomic modes) —
that much is a clean, tool-confirmed result. But MODE 1 and MODE 2 report
the *same* two race contexts, both on `pause_hook_`/`unpause_hook_`, and
that is **not** evidence the ordering fix does nothing: Valgrind's
Helgrind is documented not to model C++11/C++20 atomic acquire/release as a
happens-before edge the way ThreadSanitizer does — it treats atomics as
race-free with respect to each other but does not propagate their fences
to surrounding plain memory. So it cannot see the distinction this fix
actually makes, and it would flag MODE 2 even if the ordering were
perfectly correct. The claim that MODE 2 is correct rests on the C++
memory-model argument above (cited to `pause_lease.cpp:67-76` and
`pause_lease.hpp:126`), not on this tool run — stated plainly as the limit
of what could be checked here, not glossed over. A real TSAN run, if the
package gap is fixed, is the one check that would settle it.

## Threading (restated, round 4)

- Snippet 2's amendments from round 2 still apply: null-check `orig` before
  calling it.
- Publish order is now the opposite of round 3's literal text:
  `set_hooks_installed` first, `g_pause.store(..., release)` last — see Q2.
- The owner-thread guard is new this round; round 3 had no guard at all,
  only the unproven assumption.
- Live proof is still open, same as every prior round: a
  `GetCurrentThreadId()` log on both detours, compared against the
  server-loop thread (`hook_bodies.cpp:770` and `:1279`), once the hooks
  are actually wired into `hooksites.toml`.

## Grill me (round 4)

**Q1 (weakest). Does the dedicated-server `end_load()` fix actually make
that branch safe, or just quiet?**
Partially unverified, and said so above rather than buried: the fix stops
`loading_` from latching forever (table row above, host-proven:
`load_terminal_harness`'s `path_dedicated_server_success` check). It does
**not** protect a lease held on this branch across the remote-driven
`UnloadModule` that follows, because the native pre-UnloadModule
`begin_load` at server `0x4b9240` still isn't wired (`grep -rln "0x4b9240"
src/` — unchanged from round 3, still finds nothing). So this round closes
the *wedge* (F8 recurring), not the *lease-across-remote-unload* question,
which stays open. The check that would settle it: find where the server
role's `UnloadModule` actually fires relative to this `end_load()`, once
`0x4b9240` is wired, and confirm no lease can be held across that gap.

**Q2. Is the re-entrancy residual (a second `load_save()` overwriting the
first's `load_step_`) actually harmless, or just "not this round's
problem"?**
Argued from the core's own semantics (`end_load()` is a level write, not a
counter — `pause_lease.hpp:167`), and pinned by
`path_reentrant_load_is_bounded` in the harness (2 checks, both pass). What
is *not* claimed: that the first load's own step-machine bookkeeping
(`Sent`/`Placed` polling) being silently dropped is good behavior — only
that it doesn't wedge the pause-lease core. Unverified: whether a
re-entrant `load_save()` can happen in practice (nothing in the corpus
audit was checked for this round) — if it can't, the residual is moot.

**Q3. Is the Helgrind proof for Q2 actually evidence, given the tool's
documented atomics blind spot?**
Only for MODE 0 vs MODE 1/2 (the extra race context on the raw pointer,
which Helgrind can see). For MODE 1 vs MODE 2 specifically — the ordering
question the fix is actually about — Helgrind is the wrong tool and this
report says so rather than reporting a green (or in this case, an
uninformative red) result as if it settled anything. The check that would
settle it is a real ThreadSanitizer run, blocked here on a missing host
package (`libtsan.so.2`, confirmed absent via `dnf provides`).

**Q4. Does the owner-thread guard added to snippet 2 solve the round-1 Q1
thread-affinity question ("are the two hook entries really only ever
reached on the engine command thread")?**
No — it makes a *violation survivable* (off-thread calls get a counted
passthrough instead of touching `tool_depth_`/the slot table unsynchronized)
rather than proving no violation occurs. Q1 from round 1 is still open,
same referent as always: a live `GetCurrentThreadId()` log across load,
autopause, modal and focus-loss transitions, once the hooks are wired.

**Q5. Why trust the "15 checks, 0 failures" harness result when it doesn't
call the real `GameAdapter::load_save()`?**
Because the part that's modeled (the terminal-path shape and call counts)
is checked against the patched file by file:line in the harness's own
header comment and cross-referenced against the table above, and the part
that's *not* modeled (the real engine calls, `require()`/`have()`, the
address table) is exactly the part proven separately, by compiling the
real, patched `engine_k1.cpp` itself under both toolchains
(`-Wall -Wextra -Werror`, `-c`, real `.o` files produced). Neither half
alone would be enough; the report keeps them as two separate checks rather
than one blended claim.

**Could not settle here:** the dedicated-server lease-across-remote-unload
question (Q1, second half), whether a real TSAN run would agree with the
memory-model argument for Q2's ordering fix, and the round-1 thread-
affinity question that every round has carried forward unresolved. All
three need a live check this scratch-only, no-Wine round could not run.

## Round 5 snippet repairs

2026-09-28. Scratch only. No product integration/core file was edited. The selected scratch inputs and outputs are under `/home/brunner56/kp-live-20260922/pl5-scratch/`; the previous `pl4-scratch` was preserved.

### Armed timeout

The scratch `fields.hpp` adds `kLoadArmedTimeout{60}` and `load_armed_at_`. The scratch `engine_k1.cpp` timestamps the `Armed` transition, clears timestamps in `finish_load()` and on a new load, and checks the timeout after reading `module_ready` and before the `area_loaded_due()` early return. Expiry logs `server_mode`, `module_ready`, `area_not_ready`, and `player_creature_id`, then calls `finish_load(GaveUp)`.

The logic is extracted into `/home/brunner56/kp-live-20260922/pl5-scratch/armed_timeout.hpp`, which the scratch engine copy includes and calls. The bounded unit output was:

```text
armed timeout: 60s; terminal end_load calls=1; loading=false; later frame calls=0
```

Command: `g++ -std=c++20 -Wall -Wextra -Werror -I/home/brunner56/kp-live-20260922/pl5-scratch armed_timeout_test.cpp -o /tmp/kp-r5-snippet/armed_timeout_test && /tmp/kp-r5-snippet/armed_timeout_test`. The `>=` to `>` mutation aborted at the exact 60-second assertion (`rc=134`). Helper SHA-256: `a1fb0543ef590179b3b3a88aeb1973909e6d07ba07d575f677493896494e01fd`.

### Terminal linkage evidence

The scratch engine passes: `timeout 20s clang++ -m32 -std=c++20 -fsyntax-only -I/home/brunner56/kp-live-20260922/pl5-scratch/src -I<worktree>/src /home/brunner56/kp-live-20260922/pl5-scratch/src/harness/engine_k1.cpp` → `rc=0`. Source SHA-256: `f5c4cc8b67b110c6d11faa703f82892b04438deb89b0e898453c7fb57954cd72`.

`engine_linkage_probe.py` reads the actual scratch `on_fail` and `finish_load` call sites, then independently removes each real `pause_machine_.end_load()` call. Outputs: `on_fail mutation: detected missing cleanup (red)` and `finish_load mutation: detected missing cleanup (red)`. The full native link was not available; the recorded command is `clang++ -m32 -std=c++20 -I pl5-scratch/src engine_k1.cpp <native adapter closure>`. This is linkage evidence, not an integration PASS claim.

### Direct caller publication gate

The scratch Machine adds an acquire-loaded `hooks_published_` bit. The scratch bridge's `direct_caller_can_touch()` requires the published Machine pointer, the acquire-loaded hook-ready bit, and the owner thread. The 32-bit test output was:

```text
direct caller before publish=refused; after publish=allowed; reordered publish=refused
```

Command: `clang++ -m32 -std=c++20 -Wall -Wextra -Werror -Ipl5-scratch/src -I<worktree>/src direct_caller_gate_test.cpp pause_lease_snippet2.cpp pause_lease.cpp -o /tmp/kp-r5-snippet/direct_caller_gate_test && /tmp/kp-r5-snippet/direct_caller_gate_test`. This is a scratch candidate until wired into runtime.

### Owner-thread guard

The scratch owner-thread test installs the bridge, acquires a real Machine lease, calls the hook on the owner thread, then calls from a worker. Output:

```text
owner hook suppressed=1; worker passthrough=1; off_thread_calls=1; tool_state_unchanged=1
```

Command: `clang++ -m32 -std=c++20 -Wall -Wextra -Werror -Ipl5-scratch/src -I<worktree>/src owner_thread_test.cpp pause_lease_snippet2.cpp pause_lease.cpp -o /tmp/kp-r5-snippet/owner_thread_test && /tmp/kp-r5-snippet/owner_thread_test`. Hashes: `pause_lease_snippet2.cpp` `8863618608f9b7a02b33cae61b3e4f2ad510cdedb3857453c07c48c556e281e7`; `owner_thread_test.cpp` `d2d095f52d0ba283c1bf3b501e5b0cae1312efc1c048ab6c1a0dcb68ec257797`; `direct_caller_gate_test.cpp` `63adc5c22efac0f258dd819f456d325e75e3c2ce16874feb173410a593a79504`.

### Claims and evidence

claim: Armed cannot retain `loading_` indefinitely in the repaired snippet.
referent: `armed_timeout_test` shows exact 60-second expiry, one terminal cleanup, `loading=false`, and zero later cleanup calls; the strict-boundary mutation aborts.
checked: `/tmp/kp-r5-snippet/armed_timeout_test`; helper SHA-256 above.
verdict: holds
confidence: high for the extracted helper and scratch call site; a product integration build would be required to promote it.

claim: The real engine terminal call sites are covered by mutation checks.
referent: `engine_linkage_probe.py` independently detects missing cleanup at `on_fail` and `finish_load` after each mutation.
checked: `python3 /home/brunner56/kp-live-20260922/pl5-scratch/engine_linkage_probe.py`; syntax check `rc=0`.
verdict: holds
confidence: medium; full native link was unavailable.

claim: Direct callers cannot enter through the publication gap.
referent: fixed mode reports `before publish=refused; after publish=allowed`; reordered mode reports `reordered publish=refused`.
checked: `/tmp/kp-r5-snippet/direct_caller_gate_test`.
verdict: holds
confidence: medium; scratch bridge only, no current product caller is wired.

claim: The owner-thread guard forwards worker calls without Machine mutation.
referent: owner-thread test reports `owner hook suppressed=1; worker passthrough=1; off_thread_calls=1; tool_state_unchanged=1`.
checked: `/tmp/kp-r5-snippet/owner_thread_test`.
verdict: holds
confidence: medium; bridge is a selected scratch copy and remains unwired.

## Round 5 Grill me

1. Is this a product integration PASS? No. The full `GameAdapter` native adapter closure was not linked; the exact missing step is the recorded `<native adapter closure>` link command.
2. Does the timeout test exercise the exact Armed state? The scratch engine assigns `load_armed_at_` at the `LoadStep::Armed` assignment and checks it before `area_loaded_due`; the helper test covers the exact 60-second boundary and one-call cleanup.
3. What proves the direct caller gate is not just a comment? The fixed/reordered executable output differs on publication state, and the helper uses an acquire-loaded published pointer plus `hooks_published_`.
4. What remains unverified? Wiring these scratch seams into `engine_k1.cpp`/runtime and linking the native adapter closure without a game launch. The next settling check is a bounded compile/link target including the same helper and real adapter object.

Open question I could not settle: the exact minimal native object closure needed to link `GameAdapter`. The single check that settles it is the recorded `clang++ -m32` link command with the first unresolved symbol set, run against the selected scratch files only.

# Pause-lease core review, round 2 (Pioneer Stage 1)

2026-09-27. This is an independent re-review of the writer's "Round 2" in
`.superpowers/sdd/lua-boundary-validation-plan/pioneer-stage1-pause-lease-report.md`.
It checks that round against my round-1 review, `pause-lease-core-review.md` (FAIL).

Ground rules:
- The worktree `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation` was read-only.
- Scratch lives in `/home/brunner56/kp-live-20260922/review-probes-pause-lease-r2/`.
- No game ran, the live-game lock was not touched, and there were no git writes.

## Artifacts under review

All four files show `??` (untracked) in `git status`. SHA-256 prefixes:
- `pause_lease.cpp` a8f80468
- `pause_lease.hpp` af545294
- `pause_lease.cmake` 382109d2
- `tools/kp_pause_lease_test.cpp` 2d356964

## Verdict up front

The core logic is correct. My own reference-model fuzzers show 0 divergences on every legal usage pattern. F1 and F3–F7 are closed by my own runs, and so is the core part of F2.

The verdict is still FAIL. Three narrow items remain:

1. **F8 (new, deterministic, integration snippet 7').** Calling `begin_load` at the top of `load_save` (:679) wedges the lease service after any failed `load_save`.
2. **Grill #1 (recommendation).** Take the one-line misuse-safe rule, and add a test that pins it. Today no test pins either rule.
3. **Stale test comments** at `kp_pause_lease_test.cpp:280` and `:300`. They still describe the forbidden scoped-recovery pattern as "the recovery path".

Items 2 and 3 alone would not fail the review. Item 1 would, because round 1 set the bar: a deterministic failure in the integration guidance is a FAIL.

## Build and run (independent, 32-bit)

**Build.** Every binary was built through `host-cmd g++` (GCC 16.2.1) with `-std=c++20 -O2 -m32 -Wall -Wextra -Werror`.
- The ELF header of `kp_pause_lease_test_cur` is `7f 45 4c 46 01 …  02 00 03 00`, which means ELFCLASS32 and EM_386.
- I built two cores:
  - `cur/` is a verbatim copy of the worktree `.cpp`/`.hpp`.
  - `var/` is identical except for one line in `on_unpause_entry`: `s->game_intent = false;` before the tool-origin Suppress.

**Transport caveat.** When run from the container, `host-cmd ./x > file` can drop the tail of a program's stdout. `fuzz_bracket_gamerec_cur` came back with no mode B line even though rc=0. Under `strace`, and with the redirection done on the host (`host-cmd sh -c "./x > file"`), the line is always there. Every figure below comes from host-side redirection.

The `/tmp` tmpfs is also at its per-user quota (12767M of 12769M). Some later compiles needed `TMPDIR` pointed at the scratch dir. Neither problem is a code defect.

### Results (20000 seeds × 400 steps per mode)

| Probe | cur mode A | cur mode B | var mode A | var mode B |
|---|---|---|---|---|
| `kp_pause_lease_test` (writer's) | 188 checks, 0 failures | | 188 checks, 0 failures | |
| `fuzz.cpp` unchanged (case 9 = recovery in `ToolOriginScope`, also while leased) | 0 | **19645** | 0 | **0** |
| `fuzz_unleased_recovery.cpp` (round-1 F1 probe) | 0 | 0 | 0 | 0 |
| `fuzz_gamepath.cpp` (writer's; case 9 unwrapped) | 0 | 0 | 0 | 0 |
| `fuzz_bracket_gamerec.cpp` (new: game-path recovery plus a scoped fixed-step bracket op, modelled on :2652-2656) | 0 | 0 | 0 | 0 |
| `fuzz_bracket_scopedrec.cpp` (new: scoped recovery plus the scoped bracket) | 0 | **19494** | 0 | **0** |

The output files are `*_cur.out`, `*_var.out`, `test_cur.out` and `test_var.out` in the scratch dir.

The writer's figures reproduce exactly: 188/0, 19645, 0 and 0.

### Mutations of the round-2 fixes

Each mutation is a sed on a copy of `cur` (see `mut/`), run against the unchanged test:

| Mutation | Failures |
|---|---|
| no reseed (F1) | 6 |
| no F3 forward | 3 |
| no shutdown latch (F6) | 2 |
| no `acquire_all` rollback (F7) | 3 |
| no `load_cleanup_failures` record (F5) | 1 |

Every mutation is caught, so the new tests bite.

## F1–F7 closure (my runs, not the writer's)

claim: F1 closed. `acquire` reseeds intent when count==0 && !pending.
referent: cpp `acquire`, the reseed runs after the readback and before the Pause; `repro_cur.out` R1 `physical=0 … unpause calls=2` and R3 `physical=0`; `fuzz_unleased_recovery` 0/0; mutation `noreseed` gives 6 failures
checked: all four, run myself
verdict: holds
confidence: high

claim: F2 closed. Recovery is not tool origin, and the scope is limited to the net-zero bracket.
referent: hpp:190-198 ToolOriginScope doc; cpp rule comment; test `r2_recovery_on_game_path_while_held`; `fuzz_gamepath` and `fuzz_bracket_gamerec` 0/0
checked: code read and runs
verdict: holds for the core and its doc. It does **not** hold for the test comments at `kp_pause_lease_test.cpp:280` ("e.g. the fixed-step bracket or recovery unpause") and `:300` ("unpause_timers() recovery path"). Both still describe the forbidden pattern as recovery (item 3).
confidence: high

claim: F2b closed by snippet 7' (begin_load at the top of load_save, before step 3).
referent: after `begin_load` → `invalidate()` no slot is tracked, so step 3's hooked Pause calls at :767/:774 hit unknown timers and pass through (`on_pause_entry`: find()==nullptr → Forward). No restore can undo them.
checked: code read
verdict: holds for the step-3 undo. The same placement introduces F8, below.
confidence: high

claim: F3 closed. A game Pause on a held timer whose flag reads clear is forwarded.
referent: `repro_cur.out` R4 `physical=1`; test `r4_game_pause_repairs_external_clear`; mutation `nof3` gives 3 failures
checked: run
verdict: holds
confidence: high

claim: F4 closed. `set_hooks_installed` returns `Status::LeasesHeld`.
referent: hpp `Status set_hooks_installed`; test `r5_set_hooks_status`. Repro R5 still prints 1 only because `repro.cpp` ignores the return value.
checked: code read and test pass
verdict: holds
confidence: high

claim: F5 closed. A failed `begin_load` restore is kept in `load_cleanup_failures()`.
referent: cpp `begin_load`; test `r6_begin_load_failure_kept`; mutation `noloadfail` gives 1 failure
checked: run
verdict: holds. The cap of 16 and the fact that the list is never cleared are untested, as the writer's Q4 says.
confidence: high

claim: F6 closed. `shutdown` latches.
referent: `repro_cur.out` R7 `shut_down`; mutation `nolatch` gives 2 failures
checked: run
verdict: holds
confidence: high

claim: F7 closed. `acquire_all` is all-or-nothing and keeps prior leases.
referent: cpp `acquire_all`. `added[i] = !held` is computed before the acquire, and rollback runs in reverse over `added[j]`. A duplicate timer in the list gives `held=true` on its second occurrence, so it is released once. Test `f7_acquire_all`; mutation `norollback` gives 3 failures.
checked: code read and run
verdict: holds
confidence: high

## Integration snippets against the engine_k1.cpp call sites

The line numbers were checked with `sed -n` and `grep -n` in the worktree.

| Snippet claim | Site | Verdict |
|---|---|---|
| load_save top | :679 `Result GameAdapter::load_save` | line correct; placement defective (F8) |
| step-3 pauses unwrapped | :767 and :774 `callv("timer.pause_world_timer", …)` | holds (unknown timers after begin_load, passthrough either way) |
| recovery unwrapped | :2109 and :2116 `callv("timer.unpause_world_timer", …)` inside `unpause_timers` (:2098) | holds |
| fixed-step bracket wrapped | :2654 `if (!was_paused) callv(pause)` and :2656 `if (!was_paused) callv(unpause)` | holds. On a held timer `was_paused` is true, so there are no calls. Unheld, it nets to zero (`fuzz_bracket_gamerec` 0/0). |

The repo has exactly three hooked-Unpause `callv` sites (`grep -n unpause_world_timer src`): :2109, :2116 and :2656. Two of the three must stay unwrapped. All three use the same string.

### F8 (new, major for integration). `begin_load` at :679 wedges acquire after a failed load_save

The chain, from the code:
1. `begin_load` sets `loading_ = true`.
2. `acquire` returns `Status::Loading` while `loading_` is set (cpp `acquire`, third guard).
3. Only `end_load()` clears it.
4. Snippet 7' calls `end_load` only "at post-load readiness".

`load_save` has these early failure returns after :679:
- dir validation :681
- `require` :690
- `read_last_module` :693
- mgr/capp :702
- export :730
- "no server after CreateServer" :758
- after step 3: net_layer/handler :794-795, StartConnectToSession :820, SendLoadGameRequest :873

The list comes from `awk` over :679-880 for `return Result::fail|return req`.

A failed load_save never reaches post-load readiness. The result:
- One mistyped save name drops every live lease.
- Every later pause acquire is refused with `Loading` until some later load succeeds.

Required fix:
- Call `begin_load` after the last validating return before step 3, meaning after the :758 check.
- Every failure return after that point must call `end_load()` and re-register the timers, ideally through one scope-exit cleanup path.

A second `begin_load` at the native pre-unload boundary is safe. With every slot unused, the loop does nothing and `invalidate()` only bumps the generation.

Unverified: where `end_load` fires for the dedicated-server branch. That branch returns success at :787 right after step 3 and waits for a remote client.

## Grill #1: scoped Unpause on a held timer, suppress-only or also record running

Independent view first. I built both cores and the scenario probe (`scenarios.cpp`, outputs `scen_cur.out` and `scen_var.out`) before reading the writer's answer in detail.

**Criterion.** After the last release, the timer should hold the flag it would hold if the tool never existed ("tool-absent"). That should be true under any usage the integration can realistically produce. A secondary question is whether the contract can be enforced at hook time.

**Measurement.**

| Scenario | tool-absent | cur | var |
|---|---|---|---|
| S1 misuse: autopaused, lease, recovery wrapped in scope, release | 0 | **1** (intent=1, stuck paused) | 0 |
| S2 external raw clear behind the lease, scoped bracket, release; game's last hooked intent = paused | 0 | 1 | 0 |
| S3 = S2 with intent running | 0 | 0 | 0 |
| S4 = S2 then a game Pause while held | 1 | 1 | 1 |
| S5 legal: autopaused, lease, game-path recovery, bracket, release | 0 | 0 (1 Unpause) | 0 (1 Unpause) |
| `fuzz.cpp` and `fuzz_bracket_scopedrec` mode B | reference | 19645 / 19494 | 0 / 0 |
| every legal-usage fuzz | reference | 0 | 0 |

`ToolUnpauseSuppressed` = 1 in S1, S2 and S3 on both cores.

**Can integration wrap recovery by mistake?** Yes, and it already has twice:
- Round 1's snippet 4 wrapped :2109 and :2116, and round 1's hpp doc prescribed it.
- The round-2 test still says so at :280 and :300.
- All three Unpause sites are the same `callv` string, and two of the three must stay unwrapped.

**What happens to the world.**
- Under the current rule, a misused recovery during a lease leaves the timer **stuck paused** after release (S1). Meanwhile `unpause_timers` clears paused-by-combat and auto-paused (:2117-2120, verified), so the client flags and the timer disagree. On a softlock-recovery branch, that is the softlock the command exists to clear, and it happens silently.
- Under the variant, the worst case is S2. The timer ends **running** where the game's last *hooked* intent was paused. That needs a raw clear behind the lease first, which `verify()` already reports as `ExternalMutation`. In the tool-absent world the same raw clear would also have left the timer running. A later game Pause re-asserts paused (S4, via F3).

**Is the current contract enforceable?** Not at hook time. `ToolUnpauseSuppressed` fires identically in S1 (misuse) and S2/S3 (legal bracket after an external clear). An assert on it would also fire in the degraded-but-legal path. Telling the two apart would need new state: either key on `external_mutation`, which is only set when `verify()` was polled, or track "tool Pause forwarded on this held slot within the scope". Today the rule is a doc comment plus a counter.

**Writer's principle.** The writer rests on "tool calls never register as game ownership". The contract text is at `pioneer-native-pause-contract.md:44`: "Tool-origin native calls must use the original/trampoline or explicit origin guard so they do not become game ownership."
- That sentence is about *capture*: a tool Pause turning into game-held paused and stranding the world.
- The variant only ever records *running*. It cannot strand the world paused, and it never lets a tool call break a lease, because the call is still suppressed.
- The variant is therefore consistent with :44. If the user reads the rule as "no intent write of any kind from a tool-origin call", the user can overrule this recommendation. In that case, keep `cur` and add the tracking needed for a real misuse assert.

**Recommendation.** Take the variant. It wins S1, ties S3–S5 and every legal fuzz, and on S2 it matches the tool-absent reference. It costs one line.

Pin it with a test in the S1 shape, starting from game intent **paused**, then acquire, a scoped Unpause, and release, and expect running. Update the hpp:197-198 sentence "A tool-origin Unpause on a leased timer is suppressed and NOT recorded".

The writer's "flip one test check" does not hold. `var` passes 188/188 unchanged, because test (c) starts with intent already false. Today no test pins either rule.

## Threading requirement for integration

The hpp states it at :15-17: engine command thread only, including both hook entries, with no locks. The round-2 report adds two amendments to snippet 2: null-check `orig`, and publish `g_pause` before `set_hooks_installed(true,true)`. Those are my round-1 points 3 and 4.

Round-1 points 1 and 2 are not restated in the report:
- The channel thread (channel.cpp:208) only enqueues.
- `tool_depth_` is a plain member, not thread-local.

Both are implied by the hpp sentence. Carry them into the integration packet verbatim.

The live proof is still open: a `GetCurrentThreadId()` log on both detours, compared against the server-loop thread (hook_bodies.cpp:770 and :1279).

## Grill answers (writer's round-2 questions, weakest first)

claim: Q1 "neither rule changes any legal path; recording would only change behaviour under misuse"
referent: `fuzz_gamepath` and `fuzz_bracket_gamerec` give 0/0 on both cores; S3–S5 identical
checked: run
verdict: holds as stated, but with one exception. S2 (legal bracket after an external clear) differs, and there `var` matches the tool-absent reference. The conclusion to keep `cur` does not follow: misuse is realistic (test :280/:300, round-1 snippet 4), and its cost is a silent stuck pause.
confidence: high on the measurements; the policy call is the user's if they read :44 as stricter

claim: Q2 "F1 reseed cannot absorb a tool pause"
referent: reseed happens before the Pause inside `acquire`; `reseed_not_during_pending`; fuzz 0
checked: code read and run
verdict: holds
confidence: high

claim: Q3 "F3's flag read in the Pause hook is hook-safe"
referent: one `read_paused` on the held path only
checked: code read; latency not checkable here
verdict: holds for allocation and locks; latency unverified
confidence: medium

claim: Q4 "load_cleanup_failures capped at 16, never cleared"
referent: hpp `load_failures_` is a `std::array<…, kMaxTimers>`
checked: code read
verdict: holds; the cap is untested
confidence: high

claim: Q5 thread affinity
referent: none
checked: not checkable here
verdict: unresolved
confidence: medium that K1 simulation is single-threaded

Questions the writer missed:
- What happens to `loading_` when `load_save` fails after `begin_load`? That is F8.
- Does any test distinguish the two Grill #1 rules? None does, since `var` passes 188/188.
- Do the test comments still prescribe the forbidden pattern? Yes, at :280 and :300.

## Required before PASS

1. Snippet 7': move `begin_load` to after :758, and route every later failure return through `end_load()` plus re-register. State where `end_load` fires for the dedicated-server branch.
2. Recommended: one-line `game_intent = false` before the tool-origin Suppress in `on_unpause_entry`, plus an S1-shaped test starting from intent paused, plus the hpp:197-198 doc update. If the user rejects this, keep `cur` and add a pinning test for it instead, so the rule is at least tested.
3. Fix the test comments at :280 and :300 so they no longer call the scoped pattern recovery.

## Could not settle here

The thread affinity of the game's own PauseWorldTimer and UnpauseWorldTimer callers. The one check that settles it is a live `GetCurrentThreadId()` log on both detours across load, combat autopause, modal and focus loss.

Pause lease round 2 verdict: FAIL

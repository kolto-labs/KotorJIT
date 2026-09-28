# Pause-lease core review, round 3 (Pioneer Stage 1)

2026-09-27. Independent re-review of the writer's "Round 3" in
`.superpowers/sdd/lua-boundary-validation-plan/pioneer-stage1-pause-lease-report.md`,
answering `/home/brunner56/kp-live-20260922/pause-lease-r2-review.md` (FAIL: F8,
Grill #1, stale test comments).

Ground rules followed: worktree
`/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`
was read-only. Scratch is `/home/brunner56/kp-live-20260922/review-probes-pause-lease-r3/`
(own build under `myown/`, `TMPDIR` pointed there). No game ran, no git write, the
live-game lock was not touched. All host binaries ran through
`host-cmd sh -c '... > file'`.

## Verdict up front

**Pause lease round 3: PARTIAL.**

The core (`pause_lease.cpp`/`.hpp` and its test) fully confirms: every number
in the report reproduces from a from-scratch, independent build, and the
round-2 FAIL items (F8's core pin, Grill #1's misuse-safe rule, the stale
comments) are genuinely fixed. But the two things I was told to attack first
land differently than the report implies:

- **Q1 (dedicated-server `end_load`)** is not just "unverified" — I traced it
  and it is a confirmed, currently-real wedge (see below). The report is
  honest that it's open, but the report's own snippet 7'' does not close it,
  and nothing in the tree closes it either.
- **Q2 (thread affinity)** — the *steady-state* claim ("every `Machine` call
  runs on the engine command thread") holds; I found no other thread in the
  tree that can reach a `Machine` method today, because the core isn't wired
  into any hook yet. But the *install-time* half of snippet 2 has a concrete,
  previously-unflagged defect: `g_pause` is published from the DllMain
  worker thread, not the engine thread, as its own comment claims — see below.

## Artifacts

`git status --short` shows the same four files `??`:
```
?? src/harness/pause_lease.cmake
?? src/harness/pause_lease.cpp
?? src/harness/pause_lease.hpp
?? tools/kp_pause_lease_test.cpp
```
SHA-256 prefixes match the report's table: `pause_lease.cpp` bacd1b7d,
`pause_lease.hpp` 63e21bc9, `pause_lease.cmake` 382109d2 (unchanged since
round 1), `kp_pause_lease_test.cpp` e8750ef6.

## Independent build and run (32-bit, from scratch)

claim: `219 checks, 0 failures`, rc=0, 32-bit ELF.
referent: my own `g++ -std=c++20 -O2 -m32 -Wall -Wextra -Werror` build of the
worktree `.cpp`/`.hpp`/test, run through `host-cmd`.
checked: `review-probes-pause-lease-r3/myown/green_myown.out` — `219 checks,
0 failures / rc=0`; ELF header `7f 45 4c 46 01 01 ... 02 00 03 00` (ELFCLASS32, EM_386).
verdict: holds — confidence: high

claim: all five fuzzers, unchanged since round 2, give 0/20000 both modes
against the round-3 core.
referent: the five `.cpp` probes diffed byte-identical against my round-2
review copies; rebuilt and rerun myself against my own core.
checked: `review-probes-pause-lease-r3/myown/{fuzz,fuzz_bracket_gamerec,
fuzz_bracket_scopedrec,fuzz_gamepath,fuzz_unleased_recovery}_myown.out` —
all five `0 diverging seeds` both modes, rc=0.
verdict: holds — confidence: high

claim: the actual round-2 core (sha a8f80468, not a hand-sed approximation)
fails exactly the 4 S1/S2 checks against the round-3 test.
referent: `review-probes-pause-lease-r3/r2core/harness/pause_lease.cpp`,
sha256 confirmed `a8f80468...`, already built as `test_r2core`.
checked: `review-probes-pause-lease-r3/test_r2core.out` — `219 checks,
4 failures`; the 4 `[FAIL]` lines are the same two S1/S2 pairs the round-3
report names. (I separately reverted just the Ruling-1 line in my own build
as a second check — also 4 failures, same lines — but the r2core artifact
above is the one that actually matches "the round-2 core," not an approximation.)
verdict: holds — confidence: high

claim: mutation `end_load` no-op → 5 failures; mutation `invalidate` without
`++generation_` → 2 failures.
referent: independently hand-mutated copies, rebuilt and run (not the writer's `mut/`).
checked: `mut_endload/out.log` → 5 failures; `mut_gen/out.log` → 2 failures. Both match.
verdict: holds — confidence: high

claim: test comments no longer call a scoped Unpause "recovery" (Ruling 3).
referent: `grep -n recovery tools/kp_pause_lease_test.cpp`.
checked: `:280-282` now reads "Recovery unpause is NOT scoped; it goes through
the game path (R2)"; `:301` reads "scoped Unpause (bracket half); never
recovery". The word only otherwise appears attached to
`r2_recovery_on_game_path_while_held` and the r3 misuse-test's own name,
both correctly labelled.
verdict: holds — confidence: high

## Integration snippet 7'' line numbers against engine_k1.cpp

claim: `begin_load` after `:757-758`; failure returns needing `on_fail()` at
`:787, :794, :795, :820, :873`; success terminals needing `end_load` at
`:884` plus `LoadStep::` writes at `:996, :1015, :1038, :1054, :1062`.
referent: `grep -n`/`sed -n`/`awk` over `engine_k1.cpp`.
checked: every line lands exactly on the claimed statement, no extra `return`
in `:759-884` beyond what's listed.
verdict: holds — confidence: high

## Attacking Q1 (dedicated-server `end_load`) — does not hold as a closed item

The report calls this "unverified" and stops there. I traced it further:

- `load_step_ = LoadStep::Armed` is written only at `:881`, which is inside
  the `!dedicated_server` branch — unreachable after the `dedicated_server`
  branch's `return Result::success();` at `:787`.
- `step_load_completion()` (`:956-959`) is a no-op unless `load_step_` is
  `Armed`/`Sent`/`Placed`. On the dedicated-server role it is permanently
  `Idle`, so `step_load_completion` never fires for that role.
- `grep -rn "load_step_" src/` shows the only other write to `load_step_` is
  `:856 LoadStep::Idle`, set unconditionally at the top of every `load_save`
  call (a fresh-load reset, not a mid-flight abort). There is no separate
  disconnect/cancel path that resets it, and no other file writes
  `server.server_mode` completion or handles "the remote client's
  LoadGameRequest" (`grep -rn "LoadGameRequest\|ModuleLoaded\|RunModule"
  src/harness/engine_k1.cpp` finds only comments and the client-side poll).
- So on the dedicated-server role, if snippet 7'' is applied as written,
  `begin_load()` runs (moved past `:758`) but nothing in the current tree
  ever calls `end_load()` for that role. `loading_` latches permanently after
  the first server-hosted load, and every later `acquire`/`register_timer`
  on that role returns `Loading` forever — this is F8 recurring on a branch
  snippet 7'' does not cover.
- The report's own text says end_load at `:787` is "safe only if the native
  pre-UnloadModule `begin_load` (server `0x4b9240`) is wired." That native
  hook is not wired (`grep -rln "0x4b9240" src/` finds nothing outside the
  report text), so today's honest state is: dedicated-server role has no
  clear point, period. This should be a **does-not-hold** on snippet 7'' for
  that branch, not a footnote in the middle of a "holds" table.
checked: `sed -n '840,886p'`, `sed -n '955,1020p'`, `grep -rn "load_step_"`,
`grep -rn "0x4b9240"` in `src/`.
verdict: does not hold (for the dedicated-server branch of snippet 7'')
confidence: high

## Attacking Q2 (thread affinity) — partially holds, one concrete new defect

**What holds:** no thread in the tree today can reach a `Machine` method.
`grep -rn "Machine::\|pause_lease\|g_pause" src/harness/channel.cpp` returns
nothing; the socket thread only queues work. `grep -rln "pause_lease\|g_pause"
src/` shows the lease core is not wired into any hook body yet — this is
still a standalone unit, so "every Machine call runs on the engine thread"
is vacuously true right now, and the writer is right that a live
`GetCurrentThreadId()` proof can't be run until integration lands.

**What does not hold — a defect in snippet 2, not the core:**
- `run_startup()` → `Runtime::instance().start(cfg)` runs entirely on the
  **DllMain `CreateThread` worker** (`dllmain.cpp:70` → `run_startup` →
  `Runtime::start` `runtime.cpp:781`), which calls `install(...)` at
  `runtime.cpp:796`.
- `runtime.cpp:629-630`'s own comment confirms detours go live *while the
  game's own thread is already running*: "The hooked vm.run_script can start
  firing on the game's own thread the moment install() patches it in."
- Snippet 2 does `g_orig_pause_timer.store(...)` and
  `machine.set_hooks_installed(...)` **"after `HookSet::install`"** — i.e.
  on that same DllMain worker thread, not the engine thread.
- The existing house pattern for this exact situation
  (`engine_k1.cpp:70,78,88,141`, `g_orig_set_game_speed`) uses
  `std::atomic<void*>` with acquire/release and a null-check in the hook
  body — snippet 2 copies that part correctly for `g_orig_pause_timer` /
  `g_orig_unpause_timer`. That part is not a new problem; it's the same
  accepted publish-after-install window every other hook in this codebase
  already has.
- **But `g_pause` itself, per the report's own snippet text, is a plain
  pointer** (`kp::harness::pause::Machine* g_pause = nullptr; // set on the
  engine thread`) — not atomic, and the comment's claimed location
  ("engine thread") contradicts the actual call chain, which sets it on the
  worker thread inside `Runtime::start`. This is a genuine, previously
  unflagged inconsistency: either the comment is wrong about where it runs,
  or the field should be atomic like its two neighbours, or both.
checked: `dllmain.cpp:33-40, 55-70`, `runtime.cpp:625-630, 781-796`,
`engine_k1.cpp:70,78,88,141` (house pattern), the report's snippet-2 text.
verdict: does not hold as stated (the "set on the engine thread" comment and
the non-atomic `g_pause` are both wrong once the actual call chain is
traced); the underlying risk itself is bounded by the same window every
other hook already lives with, not a new hazard invented here.
confidence: high on the trace, medium on real-world impact (the window is a
few instructions on one thread; it would need the engine thread to call
PauseWorldTimer in that exact window to matter)

## Residual items (not blocking)

- `load_cleanup_failures()` cap (16) and lack of a clear API remain untested,
  as both round-2 and round-3 already say. Not new.
- The g_pause/thread-location issue and the dedicated-server gap are both
  integration-packet items, not core defects — the core itself (`pause_lease.cpp/.hpp`)
  is unaffected by either.

## Comparison against round-2 review's three FAIL items

| Item | Status |
|---|---|
| F8 (begin_load placement, client/normal role) | Fixed by snippet 7'' + `on_fail()`/terminal-state discipline; core pin `r3_f8_load_without_end_is_bounded` passes on both the real round-2 core (`r2core`, confirmed above) and the round-3 core, because it is a placement fix, not a core fix. |
| F8 (dedicated-server role) | **Not closed.** See Q1 above — snippet 7'' has no clear point for this branch given the current tree. |
| Grill #1 (misuse-safe rule) | Taken and verified: reverting the one line reproduces the round-2 core's exact 4-failure red. |
| Stale test comments | Fixed, verified. |
| Thread affinity (carried since round 1) | Still open for live proof, correctly so; new finding: snippet 2's `g_pause` publish location/atomicity is wrong as written, independent of live proof. |

Pause lease round 3: **PARTIAL**.

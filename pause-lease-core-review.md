# Pause-lease core review (Pioneer Stage 1)

2026-09-27. Independent spec review, then an adversarial one. Read-only on the worktree
`/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`.
Scratch lives in `/home/brunner56/kp-live-20260922/review-probes-pause-lease/`. No game ran,
the live-game lock was not touched, and there were no git writes.

Under review: `src/harness/pause_lease.{hpp,cpp,cmake}` and `tools/kp_pause_lease_test.cpp`.
Spec: `fanout-pioneer-devtools-plan.md:24` and `pioneer-native-pause-contract.md` (:40-48, :63, :74-104).

## Verdict up front

The core does what the contract's offline list at :63 asks. It matches an independent
reference model exactly, provided every change to a timer flag goes through a hook the
machine can see. It does **not** hold once one timer change goes unobserved between
`register_timer` and `acquire`. The report's own integration plan creates that case.
Examples are snippet 4's tool-origin `unpause_timers` recovery, or registering timers before
the hooks are installed. Snippet 4 is not the only source of the recovery case. The core's own
API docs prescribe it: the `ToolOriginScope` comment at `pause_lease.hpp:155-157` tells
integrators to wrap "the existing fixed-step bracket and recovery unpause". In that case a tool release can leave the world paused when it was
running before the acquire. Contract :44 says "seed game intent from a validated paused value
before acquiring". The core seeds only at register. The fix is one line. It was checked in
scratch and is described below.

## Build and run (independent)

- 32-bit build from the worktree sources with `-std=c++20 -m32 -Wall -Wextra -Werror`, through
  `host-cmd g++`. There were no warnings. The binary is `ELF 32-bit LSB executable, Intel i386`.
- `host-cmd review-probes-pause-lease/kp_pause_lease_test` printed `141 checks, 0 failures`,
  rc=0 (`test.out`).
- A UBSan build did not link because the host has no 32-bit libubsan. Not pursued.

## Contract :63 case coverage

Each case was checked against the test source, with exact call counts asserted:

| Contract case | Test | Exact native counts asserted |
|---|---|---|
| initially running / paused | `initially_running`, `initially_paused` | yes (1P+1U, then 0) |
| game Pause after acquire | `game_pause_while_held` | yes |
| game Unpause while held | `game_unpause_while_held` | yes (1U at release) |
| P/U/P sequences | `pause_unpause_pause_sequence` | yes |
| two leases | `two_leases` | yes |
| repeated release | `repeated_release` | yes (0 calls) |
| unknown timer passthrough | `unknown_timer_passthrough` | yes |
| tool-origin no capture | `tool_origin_no_capture` a/b/c | yes |
| failed hook install | `failed_hook_install` | yes |
| pending cleanup | `pending_cleanup` | yes (1U per retry) |
| epoch reset with same-address reuse; queued old release rejected | `epoch_reset_same_address` | yes |
| no native call on an expired timer | `no_native_call_on_expired` | yes (`total_calls` unchanged) |

All are covered. Two things are missing from the tests. Nothing checks that game intent matches
the physical flag at acquire (F1). The re-check of `game_intent` after the call in `restore()`
is never driven, which the writer already admits in Q5.

## Model check (my own, not the writer's)

The probe is `review-probes-pause-lease/fuzz.cpp`. It has an independent reference in which
`shadow` is the flag the timer would hold if no tool existed. The expected physical flag is
`shadow || leases`. The expected calls are:

- 1 Pause on acquire only when there are no leases and `!shadow`.
- 1 Unpause on the last release only when `!shadow`.
- Game calls are forwarded with no lease and make 0 calls while a lease is held.
- `begin_load` unpauses only a held timer whose `!shadow`.

The probe runs random acquire, release, stale-ticket release, `release_client`, game
Pause/Unpause, and load with same-address reuse and a random new flag. It uses 3 clients × 4
requests, which is more than 8 keys, so it hits TableFull. On every step it compares the
returned Status, the per-timer Pause/Unpause call deltas, the physical flag and the lease count.

| Run | Result |
|---|---|
| Mode A: hooks installed first, game ops only | **20000 seeds × 400 steps, 0 diverging seeds** (`fuzz.out`) |
| Mode B: adds hooks installed after register and a tool-origin recovery Unpause (report snippet 4) | 19934 / 20000 seeds diverge |
| Mode B, recovery only while unleased, original core | 15535 / 20000 diverge (`f2o.out`) |
| Same, core patched with the reseed fix below | **0 / 20000** diverge |
| Writer's test against the patched core | `141 checks, 0 failures` |

So composition, stale tickets, epochs, same-address reuse, capacity and load release are all
correct against the reference, as long as intent never drifts.

## Findings

Reproducers are in `review-probes-pause-lease/repro.cpp`, with output in `repro.out`.

**F1 (major, core). Game intent is seeded only at register and drifts on any unobserved change.**
- R1: the timer is autopaused, so intent=1. Recovery `unpause_timers` runs inside
  `ToolOriginScope`, as snippet 4 says. On an unleased timer it forwards and does not touch
  intent. The output was `physical=0 machine.game_intent=1`. Acquire and release then gave
  `physical=1 (was running before acquire)`, which means the tool left the world frozen.
- R3: the timer was registered before `set_hooks_installed`. A game Unpause in that window is
  forwarded and never recorded. Acquire and release then leave the timer paused.
- Fix, checked in scratch as `fix/pause_lease_reseed.cpp`. In `acquire`, after the readback at
  pause_lease.cpp:102-103, add
  `if (s->count() == 0 && !s->pending_cleanup) s->game_intent = *paused;`.
  With no lease and no pending restore, the physical flag is the game's state by definition.
  After the fix R1 and R3 restore running, the writer's 141 checks still pass and the mode B
  fuzz (unleased recovery) drops to 0.
- A cheap addition: `verify()` could also flag `count()==0 && !pending && game_intent != physical`
  as drift. Today it only checks a timer that is held and found unpaused (pause_lease.cpp:234).

**F2 (major, integration snippet 4). A recovery unpause during a lease is silently dropped.**
- R2: autopaused, then acquire, then recovery (tool origin), then release. The output was
  `physical=1 intent=1`. The operator cleared autopause, yet the world stays paused after the
  release. Meanwhile `unpause_timers` still clears paused-by-combat and auto-paused
  (engine_k1.cpp:2117-2121). The client flags and the timer then disagree.
- The core prescribes this pattern too: `pause_lease.hpp:155-157` names "recovery unpause" as
  a `ToolOriginScope` user. That comment has to change along with the snippet.
- Recovery is an intentional override of the game's pause. Do not wrap engine_k1.cpp:2109 and
  :2116 in `ToolOriginScope`. On the game path the hook suppresses the call while a lease is
  held, sets intent=false and applies it once at release. That is the right composition. The
  other options are to refuse recovery while leased, or to give the machine an explicit
  `set_game_intent(t, false)`.
- The fixed-step wrap in snippet 4 is fine. Its line reference is off. :2626 is the
  `require(...)` line, and the bracket calls are at engine_k1.cpp:2654 and :2656 (grep). With a
  lease held they make no calls, because `was_paused` is true. When unleased they net to zero.

**F2b (major, integration snippets 4 and 7 together). The load ordering undoes load_save step 3.**
- load_save (engine_k1.cpp:679) has an in-game branch where the server already exists. In that
  branch it pauses both world timers at step 3 (:767, :774), right after CreateServer. The
  native load, and therefore UnloadModule, only happens later, after steps 4-8 (:797-861).
- Snippet 7 puts `begin_load` at the pre-UnloadModule boundary. So step 3 runs while leases are
  still live. Wrapped as tool origin (snippet 4), the Pause is a forwarded no-op and game intent
  stays false. `begin_load` then calls restore, which fires `original_unpause` and undoes step 3.
  The clocks then run during the load.
- Unwrapped, step 3 would be recorded as intent=true, and `begin_load` would leave the timers
  paused, which is correct. This is by code reading. The machine rules it rests on are covered
  by the fuzz.
- Required: call `begin_load` at the top of `load_save`, before step 3, as well as at the native
  pre-unload boundary for game-initiated loads. Otherwise do not wrap :767 and :774.

**F3 (minor). A game Pause while held is suppressed instead of forwarded.**
- R4: an external clear happens during a lease, then the game calls Pause. The output was
  `physical=0 intent=1 leases=1`. Both parties want the timer paused, and it runs.
- Forwarding is always safe. Pause never breaks a lease. The original returns early when +0x24
  is set (contract :11), with no other effect. So forwarding costs only the "exact tool-issued
  call count" aesthetic.
- The writer's Q2 answer ("already surfaced as ExternalMutation") holds for detection only. It
  does not repair anything, and `verify()` must be polled to see it. Recommend Forward.

**F4 (minor, API). `set_hooks_installed` refuses silently.**
- It returns `void` (hpp:116). R5: the integration reports the hooks gone while a lease is
  held, and `ownership_available()` stays 1.
- If the integration really did uninstall, the machine now misstates reality. Return a
  bool/Status. Snippet 2 calls it after install, and snippet 7 must also check the result
  before `HookSet::uninstall()`.

**F5 (minor). `begin_load` with a failed restore drops the pending state.**
- R6: `status=cleanup_incomplete, tracked after=0, physical=1`. Contract :48 says to "expose
  pending cleanup instead of silently reporting resumed".
- The return value does expose it once. After that `status()` shows nothing.
- Native UnloadModule clears reasons 1/2 anyway (contract :94), so the risk is low. Keep a
  counter or the timer ids that failed.

**F6 (minor). There is no latch after shutdown.**
- R7: acquire after `shutdown()` still returns `ok`. Add a latch, or document that the
  integration stops issuing commands before shutdown.

**F7 (observation).** Acquire works per timer. A "pause world" command acquires about 5-7
timers, so the integration must roll back a partial acquire. The core leaves no lease on
TableFull, ReadbackFailed or NativeCallFailed, which the tests and the fuzz confirm.

## Specific checks requested

- **Blocked game Pause, side effects of the original.** Contract :11: beyond the flag, Pause
  stores GetWorldTime day/ms at +0x28/+0x2c, but only when the flag is 0. While held the flag is
  1, so the stock call is a pure early return, and suppressing it loses nothing (except F3).
- **Blocked game Unpause.** It skips clearing the flag and rebasing +0x30/+0x34 until release.
  At release the original Unpause rebases from the saved time of the tool's own pause, so no
  catch-up jump is expected. That is not proven; contract :65 requires a live timestamp test.
- The game callers are SetPauseState, and they also run CopyWorldTime and snapshot sync (contract
  :46, :90). The hooks do not see those raw copies. That stays outside this core and needs live
  evidence.
- **`verify()` semantics.** It reports only a timer that is held and found unpaused. It does not
  re-pause, and it clears the flag on the next acquire. It cannot see the unleased drift behind
  F1. Pending cleanup is reported after the mutation check.
- **Shutdown and pending cleanup.** It holds (test `shutdown_cases`). It returns
  CleanupIncomplete and keeps the pending state visible. F4 and F6 are the caveats.
- **Capacity.** It holds. 16 timers × 8 leases. TableFull is checked before any native call
  (hpp:109-110, cpp:98-100), and the fuzz compared it against the reference with 0 divergences.
  A hook on a timer that failed to register is passed through.
- **Epoch and address reuse.** It holds. `next_epoch_` is monotonic, and the generation bumps
  on `invalidate`. The fuzz reloads with the same address and a random new flag, compares stale
  statuses, and found 0 divergences. The writer's Q4 holds: M6 is caught by the epoch.

## Threading: what integration must guarantee

`kp::harness::drain()` and the console pump run on the game's main thread inside the server
loop hook (src/runtime/hook_bodies.cpp:770-771) and the client loop hook (:1279-1280). The
socket listener is a separate `std::thread` (src/harness/channel.cpp:208). Required:

1. Every `Machine` method, and every Ticket or LeaseKey use, runs only from drain or the console
   pump on the main thread. The channel thread only enqueues.
2. Both detours are reached only on that same thread. `tool_depth_` is a plain member, not
   thread-local. A game Pause arriving from another thread during a tool scope would be
   mis-attributed, and the tables would race.
3. `g_pause` is published before `set_hooks_installed(true,true)`. It is not cleared while a
   detour can run.
4. The trampoline pointers are non-null before a detour can fire. Snippet 2 calls `orig(timer)`
   with no null check.

Point 2 is the writer's Q1, and it is still unverified. The check that settles it is a live
detour logging `GetCurrentThreadId()` on both entries against the server-loop thread, across
load, combat autopause, modal and focus loss.

## Grill answers (weakest first)

claim: Q1 "hook entries only on the engine command thread"
referent: none from the writer. I found that the command path runs on the main thread (hook_bodies.cpp:770, :1280), but I have no evidence for the game's own callers.
checked: source read only; live thread-id not checkable here
verdict: unresolved
confidence: medium that K1 simulation is single-threaded; a live TID log would change it

claim: Q5 "restore's readback before Unpause is safe; re-check is defensive"
referent: cpp:137-141; contract :12 (Unpause takes no args and has no Pause call described)
checked: code read; the fuzz never drives re-entry because the trampoline does not re-enter
verdict: holds (the code is correct; the branch is untested, as stated)
confidence: high

claim: Q3 "suppressing tool-origin Unpause during a lease is intended; recovery works after release"
referent: `tool_origin_no_capture` (c)
checked: repro R2
verdict: does not hold. Recovery does **not** work after release. The world stays paused because the recovery never updates intent (F2).
confidence: high; R2 output is deterministic

claim: Q2 "suppressing game Pause changes nothing physical"
referent: contract :11; `game_pause_while_held`
checked: repro R4
verdict: holds while the flag is set; does not hold after an external clear (F3, minor)
confidence: high

claim: Q4 "per-timer epoch makes generation partly redundant"
referent: M6 fails 1 check
checked: fuzz load op with same-address reuse, 0 divergences
verdict: holds
confidence: high

Questions the writer missed:

- Why is intent not reseeded at acquire, as contract :44 says? This is F1.
- Should recovery count as game intent or as tool origin? This is F2.
- Does `begin_load` run before or after load_save pauses the timers at step 3? This is F2b.
- Does `set_hooks_installed` tell the caller when it refused? This is F4.

## Could not settle here

Thread affinity of the game's own PauseWorldTimer/UnpauseWorldTimer callers (Q1). The one
check: a live TID log on both detours.

## Required before integration

1. Reseed intent in `acquire` when there is no lease and no pending restore, and add a test in
   the shape of R1 and R3.
2. Change snippet 4 and the `ToolOriginScope` comment at hpp:155-157. Do not wrap
   `unpause_timers` in `ToolOriginScope`, or add explicit intent handling for recovery. Add a
   test in the shape of R2. Correct the fixed-step reference to :2654 and :2656.
2b. Load order (F2b): call `begin_load` at the top of `load_save`, before step 3 at :767 and
   :774, or leave step 3 unwrapped.
3. Recommended: forward a game Pause while held (F3), make `set_hooks_installed` return a
   status (F4), add a shutdown latch (F6).

Pause lease core verdict: FAIL

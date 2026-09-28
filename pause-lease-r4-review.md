# Pause-lease integration snippets round 4 (review)

2026-09-27. Independent re-review of "Round 4 — integration snippets" in
`.superpowers/sdd/lua-boundary-validation-plan/pioneer-stage1-pause-lease-report.md`
(worktree `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`),
answering `/home/brunner56/kp-live-20260922/pause-lease-r3-review.md` (PARTIAL).

Ground rules followed: worktree and `/home/brunner56/kp-live-20260922/pl4-scratch/`
read-only. Own scratch at `/home/brunner56/kp-live-20260922/review-probes-pause-lease-r4/`,
`TMPDIR` pointed there. No game/Wine run, no git write. Confirmed
`git status --short -- src tools` in the worktree: `engine_k1.cpp`/`fields.hpp`
show `M`, but `git diff` on both is pre-existing lua-boundary-validation work
(phase classification, `normal_load_completed`/`main_menu_pointer_absent`) —
no `pause_machine_`/`begin_load`/`end_load` anywhere in the diff. The four
pause-lease files are still the only pause-lease-related entries, `??`, sha256
unchanged: `pause_lease.cpp` bacd1b7d, `pause_lease.hpp` 63e21bc9,
`pause_lease.cmake` 382109d2, `kp_pause_lease_test.cpp` e8750ef6 (matches
`pl4-scratch`'s copies exactly).

## Verdict up front

**Pause lease round 4: PARTIAL.**

The publish-ordering fix (Q2) is correct and is now backed by a real TSAN
run, better evidence than the report itself produced. But two of the
report's claims about its own rigor don't survive re-checking, and one is a
live safety gap the report's "complete" table doesn't cover:

- The dedicated-server `end_load` wedge (F8's original site) is genuinely
  closed. But the same round's own fix introduces or exposes a **second,
  unbounded wedge**: the `Armed` state in `step_load_completion()` has no
  timeout at all, unlike `Sent` (20s) and `Placed` (300s). If the native load
  never reaches the point where `area_loaded_due()`/`normal_load_completed()`
  goes true, `load_step_` stays `Armed` forever, `finish_load()` is never
  called, and `loading_` latches permanently — the exact class of bug Q1's
  fix was supposed to close, in a spot the "complete" table doesn't mention.
- The terminal-path table also drops a sixth early-return path that round
  3's own text already enumerated, and claims its line numbers are
  "unpatched" and "match round 3's review exactly" — both false (they are
  post-patch numbers, offset +14 by round 4's own inserted comment block).
- The report says ThreadSanitizer "does not link on this host." That's true
  for the host via `g++`/`ld.bfd` (confirmed by the report's own error), but
  false for this container via `clang++ -fsanitize=thread`, which links and
  runs cleanly and gives a decisive three-way result the report didn't have.

## Claim 1: the terminal-path table is complete

referent asked for: independent enumeration of every return/terminal path of
`load_save()`/`step_load_completion()` (and anything setting `load_step_`),
diffed against the writer's table; every path calls `end_load` exactly once,
including exceptions/early returns before `begin_load` (must NOT call it).

referent received: the writer's table (5 pre-`begin_load` returns:
`:695 :707 :716 :744 :772`; dedicated-server branch; 4 `on_fail()` returns;
5 `finish_load()` terminal writes).

checked (part A — missing row): `grep -n "^Result GameAdapter::load_save\|
return Result::fail\|return Result::success"` over the worktree's
`src/harness/engine_k1.cpp` (unpatched, matches round 3) misses one return
because it isn't textually `return Result::fail`/`return Result::success`;
`sed -n '688,692p'` shows it: `if (!req.ok) return req;` at worktree `:690`.
Round 3's own text lists six early returns (`:681 :690 :693 :702 :730 :758`);
round 4's table and its harness header comment both list only five and both
omit the equivalent of `:690`/scratch `:704` (confirmed present in
`pl4-scratch/src/harness/engine_k1.cpp` by `sed -n '704p'`). Diffing the
scratch copy against the worktree shows a 14-line `NullPauseOps` block
inserted near the top (round 4's own addition) that shifts every later line
by exactly +14 (`681+14=695` … `758+14=772`, all confirmed) — so the table's
numbers are **post-patch**, not "unpatched" as claimed, and they are not
"round 3's review exactly." Behaviorally this missing path is still correct
(it returns before `begin_load()`, 0 `end_load` calls, read directly in the
patched source) — a documentation defect, not a safety bug on its own.

checked (part B — Armed has no timeout, this one is a safety bug): read
`pl4-scratch/src/harness/engine_k1.cpp:1020-1138` (the whole of
`step_load_completion()`, past where I'd stopped on the first pass) and
`fields.hpp:391-395` (`area_loaded_due`). `Sent` has a 20s bound (`:1055`,
`> std::chrono::seconds(20)` → `finish_load(GaveUp)`); `Placed` has a 300s
bound (`:1097`). `Armed` (the state set right after `begin_load()`, `:931`)
falls straight through to the `normal_load_completed(...)` check and then
`if (!area_loaded_due(...)) return;` (`:1119`) with **no clock check
anywhere in that path**. If the server never reaches `server_mode==2` with a
loaded module (`area_loaded_due` requires `server_mode==2 && area_not_ready==1
&& have_module`) and `normal_load_completed` never goes true either,
`step_load_completion()` returns every frame with `load_step_` still
`Armed`, forever. `grep -n "load_step_\|seconds(" src/harness/engine_k1.cpp`
confirms `Armed` is the only one of the three watched states with no
`seconds(...)` guard anywhere near it. `finish_load()` — the only thing that
calls `pause_machine_.end_load()` for this branch — is never reached. This is
the same class of wedge Q1's own fix targets (`loading_` latches forever,
`acquire`/`register_timer` refused permanently), in a spot round 4's
"complete" table never names.

verdict: **does not hold**. Table is missing a row (cosmetic — the missing
path is behaviorally correct), and separately, and more importantly, `Armed`
is an unbounded, un-timed-out terminal-adjacent state that the round-4 fix
does not close.
confidence: high — both findings are direct reads of the patched source, not
inference; the Armed gap follows from the same file the report itself
quotes line numbers from.
one line: the dedicated-server wedge is closed, fair, but Armed's wide open
with no clock on it — same bug, new spot, table doesn't say so

## Claim 2: the harness exercises the patched code, not a re-implementation

referent asked for: how it links; run it (15/15 claimed); mutate one
`on_fail` call away and confirm red.

referent received: "15 checks, 0 failures," claimed against the real
`pause_lease::Machine`, cross-referenced to the patched `engine_k1.cpp` by
file:line comment.

checked: `grep -n '#include'` on `tools/kp_load_terminal_harness.cpp` shows
only `<cassert> <cstdio> <optional> "harness/pause_lease.hpp"` — it never
includes or links `engine_k1.cpp`. Rebuilt it myself, 64-bit, no `host-cmd`
needed: `g++ -std=c++20 -Wall -Wextra -Werror -I src
tools/kp_load_terminal_harness.cpp src/harness/pause_lease.cpp` →
`15 checks, 0 failures`, reproducing the writer's number.

Then the actual mutation the brief asks for: in a copy of the **patched
`engine_k1.cpp`** (not the harness), deleted `pause_machine_.end_load();`
inside the real `on_fail` lambda, rebuilt the harness with the identical
command. Result: **still `15 checks, 0 failures`, unchanged**, because
`engine_k1.cpp` was never part of that build to begin with. This is a
stronger, more direct demonstration than mutating the harness's own model
(which I also did earlier and got 4 failures — that only proves the model
is internally consistent, not that it tracks the patched file).

Separately, read the real patched `on_fail`/`finish_load` in
`pl4-scratch/src/harness/engine_k1.cpp` directly and confirmed both do call
`pause_machine_.end_load()` — so the substantive claim (the patch itself is
correct) holds; it's the "15/15 proves it" framing that doesn't.

verdict: **does not hold** as a description of what the harness result
means, confirmed by the exact experiment the brief specifies. This mirrors
the report's own Q5 disclosure ("the part that's not modeled ... is proven
separately, by compiling the real, patched engine_k1.cpp"), so it isn't a
hidden gap — but the number needs that caveat every time it's quoted, and
this review found no caveat attached to it in the summary table at the top
of the round-4 section.
confidence: high — measured, not inferred; command and result reproduced.
one line: mutated the real file, rebuilt, still 15/0 — the harness genuinely
never sees engine_k1.cpp, exactly as your own Q5 admits

## Claim 3: publish-last ordering is sufficient; any misbehaving reader?

referent asked for: reasoning from `pause_lease.cpp:67-76` /
`pause_lease.hpp:126` plus the engine thread's reads; any reader that can
observe hooks-installed-but-`g_pause`-null and misbehave.

referent received: `set_hooks_installed` writes plain bools;
`ownership_available()` reads them; hook bodies gated by
`g_pause.load(acquire)`; store must be last.

checked: read `pause_lease.cpp:66-76` and `pause_lease.hpp:110-135` directly
— matches the report's citations exactly. Read `pause_lease_snippet2.cpp` in
full: `bind_pause_hooks_after_install` does `set_hooks_installed(...)` then
`g_owner_thread.store` then `g_pause.store(..., release)` last, matching the
claimed order.

The reader the report doesn't name: `pause_machine_` is a **direct
`GameAdapter` member** (`fields.hpp:752`), not reached only through
`g_pause`. Any engine-thread caller of `pause_machine_.acquire()`/
`register_timer()` reads `ownership_available()` (the same plain bools) with
**no atomic gate at all** — it doesn't go through `g_pause` the way the two
hook bodies do. `runtime.cpp:629-630`'s own comment shows this class of race
is real in this codebase: "the hooked `vm.run_script` can start firing on
the game's own thread the moment `install()` patches it in," and the
surrounding comment there describes a **previous, actual bug** from
publishing `g_sites` too late relative to when it started being read. If the
engine's command queue ever calls `pause_machine_.acquire()` directly
(bypassing `g_pause`) in the window between `set_hooks_installed(true,true)`
and the worker finishing its later, unrelated work, it would read
`ownership_available()==true` unsynchronized and could take a lease while
both hook bodies still see `g_pause==nullptr` and forward the game's own
calls untouched — silently breaking the lease. Confirmed this path is
**not wired today**: `grep -rn "Machine::\|pause_lease\|g_pause"
src/harness/channel.cpp` is empty, so nothing currently calls
`pause_machine_` from off the object's own construction — vacuously safe,
same as the report's own framing, but the report's Q2 only reasons about the
two hook bodies, not about `pause_machine_`'s other engine-thread callers
needing the same publish discipline once wired.

verdict: **holds** for what it explicitly covers (the two hook bodies), with
a real, disclosed-by-implication-but-not-explicitly-named scope gap: nothing
protects `pause_machine_`'s direct callers the same way, and this codebase
has already been bitten by exactly this shape of bug once (`g_sites`).
confidence: medium — the ordering argument for the two hook bodies is solid
and TSAN-backed (see claim 5); the `pause_machine_` direct-caller gap is
correctly currently unreachable, so it's a scope note, not a live bug, but
it's the kind of thing that should be named before the integration lands.
one line: the hook-body fix is solid, but nothing gates pause_machine_'s
other callers the same way yet — same shape as the g_sites bug you already
had once

## Claim 4: `tool_depth_` owner-thread guard — behavior on violation

referent asked for: what happens on violation (abort/log/refuse) and is that
safe in a game process.

referent received: off-thread call gets a plain passthrough to `orig`,
untouched by the Machine, plus a relaxed counter.

checked: read `pause_lease_snippet2.cpp` hook bodies directly — off-thread
calls get `orig` unconditionally, on-thread calls touch the Machine; no
abort, no log by default, no lock. Matches the report's Q4 answer exactly.

Additionally checked whether the guard is exercised by anything: `grep -n
"bind_pause_hooks_after_install\|owner_thread"
tools/kp_pause_publish_race_test.cpp` — **empty**. The TSAN/Helgrind race
test that stands in for Q2's proof never calls
`bind_pause_hooks_after_install` at all; it busy-waits and calls
`on_pause_entry`/`on_unpause_entry` directly post-publish, so the
owner-thread guard added this round is untested by the very proof offered
for this section. `grep -rn "GetCurrentThreadId\|this_thread::get_id"
src/` shows no caller anywhere sets a real owner-thread id into that guard
yet (the only `get_id()` call is the guard's own comparison; the only
`GetCurrentThreadId()` calls in the tree are in `devtools/overlay.cpp`,
unrelated).

verdict: **holds** for the behavior-on-violation question (crash-safe,
no lock, matches Q4's answer). New finding: the guard itself is currently
inert and untested — nothing supplies a real owner thread id, and the race
test doesn't exercise it — so "safe in a game process" is verified for the
snippet in isolation, not for anything connected to a real caller yet.
confidence: high on the behavior; high on "untested by the race harness"
(grep is definitive); medium on "inert" (I did not exhaustively search every
future caller, only what exists in the tree today).
one line: the guard itself checks out, but nobody's even tried to trip it
yet — the race test that's supposed to stand in for Q2 doesn't touch it

## Claim 5: a real TSAN run

referent asked for: try clang with `-fsanitize=thread` in this container, or
say so with command output.

referent received: "ThreadSanitizer does not link on this host ...
`/usr/lib64/libtsan.so.2.0.0: No such file or directory`", stood in with
Helgrind instead.

checked: ran the exact thing the report said was blocked —
`/home/brunner56/.local/bin/clang++ -std=c++20 -fsanitize=thread -O1 -g -I src
-DMODE={0,1,2} pl4-scratch/tools/kp_pause_publish_race_test.cpp
src/harness/pause_lease.cpp -o race_mode{0,1,2}`. **All three link cleanly,
no missing-library error, unlike the writer's `g++`/`ld.bfd` attempt.** Ran
all three (`TSAN_OPTIONS=halt_on_error=0`):
```
MODE 0: ThreadSanitizer: SEGV, READ at 0x000000000e40 (rc=66)
MODE 1: 1 data race reported, T1 write vs T2 read on the stack of main
        thread (rc=66, "MODE=1 cycles=400 saw_machine=400")
MODE 2: 0 races (rc=0), "MODE=2 cycles=400 saw_machine=400 / done, rc=0"
```
Outputs at `/home/brunner56/kp-live-20260922/review-probes-pause-lease-r4/tsan/out_mode{0,1,2}.log`.
This is exactly the discriminating result the memory-model argument
predicts: MODE 2 (fixed order) clean, MODE 1 (round 3's original order)
flagged, MODE 0 (no atomic at all) is worse still. Tried to symbolize the
MODE 1 frames (`race_mode1+0x4be25c` etc.) with `addr2line` — **not
installed in this container** (`bash: addr2line: command not found`), and no
`llvm-symbolizer` next to `clang` either, so the race is confirmed by
location ("stack of main thread," matching where the test's local `Machine`
and hook flags live) but not by symbol name. The MODE 0 SEGV (read at a
small offset, `0xe40`) is consistent with a torn/garbage-pointer dereference
through the unsynchronized plain `Machine*`, but is not confirmed by symbol
name either — logged as unexplained, not asserted.
verdict: the writer's claim as stated, "ThreadSanitizer does not link on
this host," **holds for the host** (the writer's own error output, `ld.bfd`
against `/usr/lib64/libtsan.so.2.0.0`, is real and I have no reason to doubt
it) but the practical upshot ("so the check is blocked here") **does not
hold** — it isn't blocked in this container via `clang++`, and the report
should have tried that before falling back to Helgrind, especially since the
brief for this very round says to try it.
confidence: high on "clang links and the three-mode result is real" (ran it
myself, logs saved); low on the specific mechanism behind the MODE 0 SEGV
(no symbolizer available to confirm).
one line: not blocked here — clang links it, and MODE 2 comes back clean
while MODE 1 gets flagged, which is the result you wanted, you just didn't
have the tool to get it

## Claim 6: core sha256s unchanged

referent asked for: `bacd1b7d/63e21bc9/382109d2/e8750ef6` still current.
checked: `sha256sum` on both the worktree's four `??` files and
`pl4-scratch`'s copies — all four match, both places. `git status --short --
src tools` in the worktree shows `engine_k1.cpp`/`fields.hpp` as `M`, but
`git diff` on both is pre-existing lua-boundary-validation work (phase
classification helpers), with no `pause_machine_`/`begin_load`/`end_load`
anywhere in it.
verdict: **holds**.
confidence: high — sha256 and git diff both checked directly.

## Grill me (writer's round 4) — spot check

Q1 (dedicated-server lease-across-remote-unload) and the round-1 thread-
affinity question: both still correctly reported as open, both still
correctly say what single check would settle them. No referent needed here
— these are honest "unresolved" markers, not claims.

## Could not settle here

Whether the dedicated-server branch's lease is actually safe across a live
`UnloadModule` once `0x4b9240` is wired (needs the live hook, per the
report's own Q1) — same open item as every prior round. Whether the
`Armed`-state wedge found here (claim 1, part B) is reachable in practice —
it needs a live run where the native load stalls before `server_mode`
reaches 2, which this report-only round could not run either.

---

Pause lease round 4: PARTIAL.

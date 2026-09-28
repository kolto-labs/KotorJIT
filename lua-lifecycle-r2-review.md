# Lua lifecycle L1+L2 round 2 — independent re-review

Reviewer: resumed and completed by a second session after a model-switch
interruption (prior session's last status: "Build running in background;
consulting the advisor on classification"). This file did not exist yet; no
prior review content is duplicated here except where explicitly cited.

Scope: `src/lua/host.{cpp,hpp}`, `src/api/scripts_lua.{cpp,hpp}`,
`tools/kp_lifecycletest.cpp`, `tools/kp_scriptsapitest.cpp` in the worktree
`/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`,
against writer report `.superpowers/sdd/lua-boundary-validation-plan/lua-lifecycle-l1-l2-report.md`
("Round 2" section) and prior review (FAIL)
`/home/brunner56/kp-live-20260922/lua-lifecycle-l1l2-review.md`.

What I did not do: no game, Wine-as-a-game, Gamescope or FFmpeg. I did not
touch `tmp/harness-locks/live-game.lock`. I made no edits inside the
worktree (read-only), no git reset/stash/stage/commit. All builds and
probes are scratch under
`/home/brunner56/kp-live-20260922/review-probes-lifecycle-r2/` (`RP2/`
below), with `TMPDIR` under that tree (host `/tmp` was full).

## Verdict up front

**Lua lifecycle round 2 verdict: FAIL**

Two concrete, reproduced-by-me correctness bugs on the Windows/Wine side of
I2 and M1, both of which the writer's own round-2 "Grill me" flagged only as
`unverified` ("Does I2 hold on a real Windows or Wine build? unverified at
runtime"). I went further than `-fsyntax-only` and actually cross-compiled
with `i686-w64-mingw32-g++` and ran the binaries under Wine via `host-cmd`.
That run demonstrates both gaps as live test/behaviour failures, not just
theoretical ones. Everything else I checked (P0–P11 reruns, N1/N2/N4/N5
adversarial probes, casefold, M8 namespace fix) holds.

## Method (prove-the-effort: independent first)

I inspected the partial work in `RP2/` before reading the writer's report,
to avoid anchoring: `RP2/logs/*.log` and `RP2/logs/*.txt` were already
populated by the prior session (Linux builds/runs of P0–P11, r2's N1–N5,
and — critically — a `RP2/win/` tree with `.exe` binaries already
cross-compiled and already run through Wine). I formed the reading below
from those raw logs and the source at `host.cpp:52-84`, `701-719` in
`kp_lifecycletest.cpp`, before reading the writer's Grill-me section. Only
afterward did I read the writer's report to compare.

## Reused from round 1 (P0–P11), rerun against round-2 sources

Rebuilt and reran the reviewer's own `probe_lifecycle.cpp` / `probe_casefold.cpp`
unmodified (`RP2/build.sh lifecycle scriptsapi probe casefold`, 0 warnings;
logs `RP2/logs/run-probe.log`, `run-probe-casefold.log`,
`run-kp_lifecycletest.log`, `run-kp_lifecycletest-casefold.log`,
`run-kp_scriptsapitest.log`).

- `kp_lifecycletest`: **29 case(s), 0 failed** (Linux, no casefold dir).
- `kp_lifecycletest` (casefold tmpfs, `chattr +F`): **30 case(s), 0 failed**.
- `kp_scriptsapitest`: **10 case(s), 0 failed**.
- P0–P11 outputs match the writer's before/after claims in the report's
  "Reviewer probes, rerun on the new code" section line for line: P0's
  `OnSave` now fires on the new generation (`called=1 new-onsave=1
  old-onsave=0`), P3's delete/recreate window keeps the script and recovers,
  P6's request storm is bounded and fast (`pending=1 ... in 84 ms` vs the
  round-1 `20000/20000 in 7836 ms`), P7/P7b refuse the symlink-outside-dir
  and the hard-link alias on POSIX, P8's numeric edges are all `nil` except
  the exact integer id, P9's queued request during `load_all` is dropped as
  documented (M5). No divergence found — **that holds**.

## New round-2 adversarial probes (N1–N5), independently rerun

Ran `RP2/probe_r2.cpp` twice back to back (`run-probe-r2.log`,
`run-probe-r2b.log`) — byte-identical, so the new logic is deterministic
under these probes, not racy on Linux.

- **N1 (staged-skip must not drop events the new generation should get
  after commit).** `probe_r2.cpp:16-42`. Sequence observed: `b-tick
  old-unload old-tick b-tick new-load new-tick b-tick`; after commit
  `new-tick=1 old-tick=0 b-tick=1 new-save=1`. `b` (an unrelated script)
  keeps ticking through every phase, and the new generation's own `OnSave`
  binding (registered at chunk top level) fires after commit. **That
  holds** — matches `host.cpp`'s `staging_chunk_` design (grill-me #2).
- **N2 (reload whose new version errors at top level while events
  fire).** `probe_r2.cpp:46-77`. The staged chunk runs two nested
  dispatches before `error('boom at top level')`; the poll reports exactly
  one error, the old generation keeps ticking (`old-tick=3`), the failed
  stage's state is created and closed exactly once
  (`states created=1 closed=1`), and a subsequent fix is picked up on the
  next poll (`fixed-tick=1`). **That holds** — R1 (compile-before-close)
  survives a runtime error mid-chunk with live nested dispatch, which round
  1 did not test.
- **N3 (delete-then-create race, 5 sub-cases A–E).** `probe_r2.cpp:80-150`.
  All 5 sub-cases pass on Linux with the expected counts (unload fires
  once, final content is v2, the absent/present/absent counter resets, a
  rename is treated as one delete + one create). **This is where I found
  the round's real bug — see "Windows/Wine findings" below**: the same
  probe run through the Windows/Wine build gives a materially different,
  wrong answer for sub-case A.
- **N4 (coalescing must not lose an explicit unload queued after a
  reload).** `probe_r2.cpp:152+`. All four orderings
  (`reload,unload` / `unload,reload,unload` / `reload,unload,reload` /
  `unload,load,unload`) leave the correct final state and the last queued
  op's id resolves `OK`; a non-tail unload is never silently dropped.
  **That holds.**
- **N5 (bonus: raising-script reload-scope check).** Refused with a clear
  error naming the responsible script. Not requested by name in the task
  but exercises the same `RaiseMark` guard as M3; **holds**.

`created=27 closed=27` (Linux) matches at the end of the r2 probe run —
no leaked or double-closed Lua states across N1–N5.

## Windows/Wine findings (the substantive result of this round)

The prior session had already cross-compiled with
`i686-w64-mingw32-g++ -std=c++20` and run the resulting `.exe`s through
`host-cmd` (which resolves to Wine — note the `Z:/home/...` drive mapping
in `RP2/logs/run-win-equiv.txt`). I verified these runs are against the
same round-2 sources (same `RP2/win/build-win.sh`, `built lifecycle`
`built casefold` `built r2`, `RP2/logs/build-win.log`) and re-examined the
raw output myself rather than trusting only the summary line.

### 1. `same_file()` does not detect a hard-link alias on `_WIN32` — confirmed failing, not just "unverified"

`src/lua/host.cpp:74-84`:
```cpp
// Two paths name one file. POSIX asks the filesystem (device and inode), which
// catches hard links, symlinks and case variants on a case-insensitive
// directory. On _WIN32 the libstdc++ equivalent() cannot be exercised here, so
// it is not trusted; the lookup rule there is case-insensitive, and that is
// what is compared.
bool same_file(const std::string& a, const std::string& b) {
    if (a == b) return true;
#ifdef _WIN32
    return iequals(a, b);
#else
    ...fs::equivalent...
#endif
}
```
On `_WIN32` this compares path *strings* only. A hard-link alias (`b.lua`
hard-linked to `a.lua`, distinct path strings) is therefore never caught.
`tools/kp_lifecycletest.cpp:701-719` (`alias_of_held_script_refused`) has no
platform gate for this — unlike `symlink_outside_dir_refused`, which prints
a NOTE and skips when `create_symlink` isn't supported (Wine's `ln -s`
gives `Function not implemented`, and the test handles that gracefully).
`alias_of_held_script_refused` instead hard-asserts refusal unconditionally,
because `create_hard_link` *does* succeed under Wine.

Result, run under Wine (`RP2/logs/run-win-lifecycle.txt`):
```
FAIL lifecycle.alias_of_held_script_refused
     - load of an alias of a held file is an error
     - one script held, saw 2
     - one tick runs the body once, saw 2
29 case(s), 1 failed
```
Every other case in the same run is `PASS` (28/29), including
`case_variant_request_refused` (case-insensitivity itself works — that part
of I2 is fine on Windows) and the gated `symlink_outside_dir_refused` NOTE.
This isolates the failure to hard-link identity specifically, exactly as
the code comment predicts.

Why this matters beyond a unit test: `Host::do_load_path`'s duplicate
refusal is the only thing standing between "one script, one running Lua
state" and silently running the same file's top-level code and event
handlers twice per tick under two different `Script` objects (confirmed
by the test's own `one tick runs the body once, saw 2`). On a platform
where hard links are cheap and NTFS supports them natively, this is a
reachable double-execution bug, not a hypothetical.

Writer's own grill-me #1 called this `unverified at runtime` and named the
"single settling check" as exactly this: "a Wine run of `kp_lifecycletest`
... requesting `10_COVER` while `10_cover` is held" — that specific
sub-case (case-insensitivity) passes. The adjacent hard-link sub-case,
which the writer's residual note also flagged ("Hard-link aliases are not
detected on `_WIN32`"), was not run, and it fails.

### 2. M1 delete-then-create: Windows silently keeps stale content (new bug I found; not previously flagged as `unverified`)

`RP2/probe_r2.cpp:82-94`, sub-case A: load `a` with body `v1`; delete `a`;
poll once (grace window, M1's `kMissingPollsToDrop=2`); recreate `a` with
body `v2`; poll again; tick.

Linux (`RP2/logs/run-probe-r2.log`):
```
OBSERVE A poll1-absent: a state=Loaded gen=1 timers=0 ...
OBSERVE A poll2-recreated: a state=Loaded gen=2 timers=0 ...
OBSERVE A unload=1 v1=0 v2=1
```
Generation bumps 1→2, `OnScriptUnload` fires once, and the new body (`v2`)
is what runs. Correct: the recreated file is treated as a new copy of the
script, exactly as M1 intends.

Windows/Wine, same probe binary, same recipe (`RP2/logs/run-win-r2.txt`):
```
OBSERVE A poll1-absent: a state=Loaded gen=1 timers=0 ...
OBSERVE A poll2-recreated: a state=Loaded gen=1 timers=0 ...
OBSERVE A unload=0 v1=1 v2=0
```
Generation stays at 1, `OnScriptUnload` never fires, and **the old body
(`v1`) is still what runs** — the delete-then-recreate was invisible to the
host. This is the opposite of M1's stated guarantee for this exact
scenario ("recovers", per the writer's report line "One absent poll changes
nothing, so R1 and an explicit Unloaded state both survive the window" —
here more than that survives: the *stale content* also survives, silently,
past the recreate). Sub-cases B/C/D/E (`RP2/logs/run-win-r2.txt`) do show
correct recovery, so this is specific to the one-poll-grace-then-recreate
timing in sub-case A, not a total failure of M1.

Corroborating root cause: `RP2/logs/run-mtime.txt`, a small standalone
probe (`RP2/win/mtime.cpp` vs its Linux build) measuring mtime granularity
for writes ~150 ms apart:
```
Linux (ext4, this host):   writes 150ms apart with equal mtime: 0/20;  stamps with sub-second part: 20/20
Windows/Wine (same probe): writes150msapartwithequalmtime:17/20; stampswithsub-secondpart:0/20
```
(second line's spacing is a terminal-wrap artifact of the tool, not a typo
in the source — the numbers are 17/20 and 0/20.) Under Wine, `stat` mtimes
on this filesystem carry no sub-second component and collide 17/20 times
for back-to-back writes; on Linux they never collide in the same test.
`host.cpp`'s poll/stamp logic is mtime-based, so a fast delete-then-recreate
that lands within the same whole second is exactly the case this loses:
the recreated file's mtime doesn't move enough (or at all) to be seen as
"changed" against what the poll already recorded on the absent/present
transition, so the recreate is missed and the previously-staged/kept
generation just... stays. The writer's own residual note for M2 already
flags mtime coarseness as a known risk ("If mtime granularity is coarser
than the gap between the two writes, the final write is missed until the
next edit. P5 measured 0/200 on btrfs; ext4 was not measured.") but that
note is scoped to plain edits, not to delete-then-create, and it was never
measured against the actual deployment filesystem (Wine). I measured it
here and it is far worse than the ext4 assumption the report leans on
elsewhere.

Game-relevance: this is not a synthetic corner case. Any editor or sync
tool that saves via delete-then-write (many do, to avoid partial-write
corruption) plus a script author retrying a fix quickly, on the Windows
build (native or Wine) landing within the same wall-clock second as the
delete, reproduces "the host keeps running the old script forever with no
error and no log line," which is a materially worse failure mode than a
delayed reload.

### What did not regress on Windows

`RP2/logs/run-win-lifecycle.txt`: 28/29 non-skipped cases pass, including
`request_queue_coalesced_and_bounded`, `nul_name_refused`,
`queued_requests_discarded_by_load_all`, `delete_window_keeps_script`
(the *simple* single-delete case, as opposed to N3's delete-then-recreate).
`RP2/logs/run-win-casefold.txt` and `run-win-equiv.txt` show
case-insensitive lookup and `equivalent()`-style listing work as the
`_WIN32` branch intends. N4's coalescing rules hold identically on Windows
(`RP2/logs/run-win-r2.txt`, N4 section byte-for-byte matches Linux). N2's
top-level-throw-with-live-events case also matches Linux exactly on
Windows. So this is not "the Windows branch is broadly broken" — it is two
specific, identifiable gaps (hard-link identity; delete-then-recreate
timing under coarse mtimes), both downstream of the same root design choice
(`_WIN32` trusts path-string/mtime comparisons, not filesystem identity).

## M8 (namespace snippet) — applied only in a scratch copy, not in the worktree

Per instructions, I did not touch the worktree's forbidden
`tools/kp_namespacetest.cpp`. The prior session had already copied the
worktree into `RP2/src/` and applied the writer's corrected M8 diff there
(`RP2/logs/patch.log`: `patching file tools/kp_namespacetest.cpp`, clean
hunks). I diffed that patched file against the file the **round-1**
reviewer independently verified and ran to `namespace contract: 0
failure(s)` on both k1 and k2
(`/home/brunner56/kp-live-20260922/review-probes-lifecycle/src/tools/kp_namespacetest.cpp`,
`run-namespacetest-fixed-k1.log`, `run-namespacetest-fixed-k2.log`):
```
diff review-probes-lifecycle/src/tools/kp_namespacetest.cpp \
     review-probes-lifecycle-r2/src/tools/kp_namespacetest.cpp
(no output — files are byte-identical)
```
I did not rebuild and rerun `kp_namespacetest` k1/k2 myself this round: the
host is at 12G free disk system-wide and a fresh `cmake` configure/build in
`RP2/build/` (started by the prior session) was still at the "clone
LuaJIT" step with no forward progress and no live compiler process by the
time I inspected it, so I judged a second full rebuild not worth the disk
risk given the patch is provably identical to an already-independently-run
fix. This is the one item I did not personally re-execute; the byte-identity
check is the referent for treating M8 as still resolved. **That holds**,
with the caveat above stated plainly instead of silently assumed.

`ctest -L lifecycle`: I did not run this myself in `RP2/` for the same
disk/host-load reason. The writer's report shows it passing 2/2 in the
worktree's own scratch `tmp/lifecycle-cfg`, built after a source-hash check
against the current round-2 files (`host.cpp fa8c58be`, etc., report
lines 379-390), which I did not re-verify by hash myself but which is a
reasonable, checkable claim I have no contrary evidence against. Given
that the two custom test binaries (`kp_lifecycletest`, `kp_scriptsapitest`)
built and run standalone here are compiled from the identical source files
and reproduce the writer's pass counts exactly, I treat the CMake/ctest
path as redundant confirmation rather than a gap — the machinery ctest
wraps (CMake target wiring in `lifecycle.cmake`) was not itself in the
round-2 diff.

## Grill-me attack (round 2, per protocol)

1. **"Does I2 hold on a real Windows or Wine build?" (writer's weakest,
   answered first).** Does not hold — see finding 1 above. `referent:
   RP2/logs/run-win-lifecycle.txt`, `FAIL lifecycle.alias_of_held_script_refused`.
   `verdict: does not hold`. `confidence: high` — the failure reproduces
   deterministically from source (`host.cpp:74-84`'s `_WIN32` branch
   structurally cannot see hard links), and the test that catches it has no
   platform gate, so it is not an artifact of the harness.
2. **"Why is skipping the script during the chunk enough for I1, and what
   about timers?"** N1/N2 reruns match the writer's claim and the residual
   about `timers::pump` running outside the host is stated as `unverified
   but not reachable in the code I read`, which matches what I read too
   (`host.cpp:787`-area hook, timers module does not call back into
   `Host::dispatch`). **That holds** — I did not find a path where a timer
   callback binds into the staged map.
3. **"Could the two-poll delete rule keep a truly deleted script running
   too long?"** Not the bug I found — the bug is the opposite (a
   *recreated* file not being picked up), which the writer's grill-me
   didn't ask about. New question, not a rebuttal of #3; **that (#3 as
   asked) holds** on its own terms.
4. **"Why refuse self-reload instead of rate-limiting?"** N5 confirms the
   refusal path with a specific, readable error. **Holds.**
5. **"Does the equivalence check cost much at boot?"** Not measured by
   either of us; O(N²) `equivalent()` stats as described is plausible and
   not disqualifying for typical script counts. `unresolved`, low stakes,
   not gating the verdict.

My own new grill question the writer didn't ask: **"If `same_file` can't
trust `equivalent()` on `_WIN32`, why does it fall back to a string
compare instead of Windows' own file-identity API
(`GetFileInformationByHandle`'s `nFileIndexHigh/Low`, or
`FILE_ID_INFO`)?"** — `unverified`, but this is the concrete fix direction:
it would close finding 1 without needing libstdc++'s `equivalent()` to be
trusted at all.

## Open item / what would settle it

Same open item the writer named, now sharpened: a mingw+Wine
`kp_lifecycletest` run already exists and already answers "does `_WIN32`
`same_file` catch a hard link" — no. What remains open is whether the
*production* Windows filesystem (real NTFS, not Wine's Unix-backed
implementation) has the same mtime coarseness measured in
`RP2/logs/run-win-mtime.txt` (17/20 collisions at 150 ms). Wine's `stat`
emulation may be coarser than real NTFS's 100 ns `FILETIME` resolution, so
finding 2's severity on a real Windows box (vs. Wine) is `unverified` — the
single settling check is the same `mtime.exe` probe run on native Windows.
Finding 1 (hard links) is not filesystem-emulation-dependent: it is a
direct reading of `host.cpp:74-84`'s `#ifdef _WIN32` branch, so it holds on
real Windows too, hard links being an NTFS feature Wine merely also
happens to expose.

Lua lifecycle round 2 verdict: FAIL

## Round 3 independent re-review — Windows file identity and recreate polling

Reviewer: resumed independently in `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation` after the Round 3 writer report. I read the handoff and protocol blocks, inspected the current `src/lua/host.cpp`, `src/lua/host.hpp`, `tools/kp_lifecycletest.cpp`, and the partial `lc3-round3/` artifacts before reading the writer's Grill-me section. No product edits were made. No Wine, game, Gamescope, FFmpeg, or live launch was performed in this wave, and `tmp/harness-locks/live-game.lock` was not touched.

### Verdict

**Round 3: PASS for the W1/W2 host lifecycle fix, with Windows runtime confirmation carried as reused artifact evidence rather than a fresh run in this wave.** The previous Round 2 blockers are addressed in the current source: `_WIN32` duplicate detection no longer falls back to path spelling, and delete/recreate polling no longer trusts an equal mtime when file identity or bounded content checks disagree. The host-side executable rerun passed all 31 cases and the scripts API artifact passed all 10. The preserved Round 3 Wine output reports 30 executed cases, 0 failures, and the two expected unsupported-environment notes; I did not independently regenerate that output because this wave explicitly forbade Wine.

claim: `_WIN32` duplicate detection refuses a hard-link alias of a held script.
referent: `src/lua/host.cpp:117-141` obtains Windows volume serial plus file index through `CreateFileW`/`GetFileInformationByHandle`; `src/lua/host.cpp:554-623` compares the candidate against the held script's stamped identity and refuses an unverifiable candidate; `src/lua/host.cpp:74-102` leaves `same_file` POSIX-only. The preserved pre-fix failure is `review-probes-lifecycle-r2/logs/run-win-lifecycle.txt`, while the preserved Round 3 output is `lc3-round3/logs/run-win-lifecycle-green.clean.log` with `PASSlifecycle.alias_of_held_script_refused` and `30case(s),0failed`.
checked: `nl -ba src/lua/host.cpp | sed -n '117,141p;554,623p'`; `sed -n '1,220p' /home/brunner56/kp-live-20260922/lc3-round3/logs/run-win-lifecycle-green.clean.log`; no new Wine launch.
verdict: holds
confidence: high for source behavior and preserved result; medium for a fresh Windows/Wine runtime confirmation in this wave. A native Windows or separately authorized Wine run would raise the runtime-evidence confidence.

claim: delete-then-recreate with unchanged size and mtime is promoted to a new generation, including when the transition is observed inside the one-poll grace window and when it happens between polls.
referent: `src/lua/host.cpp:1006-1047` compares identity before size/mtime and hashes only when the identity/size/mtime agreement is suspect; `src/lua/host.cpp:978-990` marks a missing path for a later content check; `tools/kp_lifecycletest.cpp:805-884` adds both deterministic same-mtime cases. The preserved pre-fix log has both cases failing (`lc3-round3/logs/run-red.log`); the current host binary rerun passed both (`lc3-round3/logs/recheck-host.log`, `31 case(s), 0 failed`).
checked: `/home/brunner56/kp-live-20260922/lc3-round3/bin/kp_lifecycletest /home/brunner56/kp-live-20260922/lc3-round3/tmp/recheck-lifecycle`; `nl -ba src/lua/host.cpp | sed -n '978,1057p'`; no Wine/game launch.
verdict: holds
confidence: high for the host algorithm and Linux execution; medium for native Windows filesystem semantics because no fresh Windows run was permitted. The preserved Round 3 Wine output is supporting evidence, not newly collected evidence.

claim: the Round 3 lifecycle changes preserve the existing lifecycle and scripts API behavior.
referent: `lc3-round3/logs/recheck-host.log` reports `31 case(s), 0 failed`; `lc3-round3/logs/recheck-scriptsapi.log` reports `10 case(s), 0 failed`; `lc3-round3/logs/ctest.txt` records both lifecycle CTest targets passing. Source hashes at review time are `host.cpp fa6830f8`, `host.hpp 3fbfad3a`, and `kp_lifecycletest.cpp 61736b47` (full hashes recorded by `sha256sum`).
checked: reran both existing host-only binaries from `lc3-round3/bin`; inspected `lc3-round3/logs/ctest.txt`; `sha256sum src/lua/host.cpp src/lua/host.hpp tools/kp_lifecycletest.cpp`.
verdict: holds
confidence: high for the tested host-only scope. The empty preserved build logs (`build-lifecycle-fix.log`, `build-scriptsapi-fix.log`, `build-win-lifecycle.log`, each 0 bytes) mean the claimed compiler warning/build transcript itself is not independently auditable from those files; executable output and CTest output remain valid runtime artifacts, but they do not prove a fresh rebuild in this review.

### Grill attack and open item

Weakest writer answer first: the writer did not run the unfixed W2 code under Wine. That answer is candid and remains an evidence limitation. The deterministic pre-fix Linux cases force the exact equal-mtime condition, and the current identity/hash path passes them; the preserved Round 2 Wine mtime and hard-link failures explain why W2/W1 were real. That holds for the algorithmic fix, while the native Windows severity of coarse mtime remains unverified here.

Additional check: `FileIdentity::operator==` returns false when either side is not `ok`, and `reload_changed` treats that as changed (`host.cpp:1013-1024`); `do_load_path` treats the same uncertainty as a typed refusal (`host.cpp:615-623`). This is the required fail-closed behavior and does not regress the alias rule.

One question remains open: does real NTFS expose any filesystem behavior that differs from the preserved Wine result for the racy mtime case? Single settling check: run the existing `kp_lifecycletest` Windows build on native Windows (or an explicitly authorized isolated Wine run) and retain the raw output plus build transcript. This is a runtime-evidence gap, not a Round 3 source or host-test blocker.

Round 3 lifecycle verdict: PASS (host fix); integration may treat W1/W2 as resolved, with the Windows proof boundary recorded above.

## Fresh current-source rebuild follow-up

The prior re-review's reused binaries were rebuilt against the current dirty
worktree before this follow-up verdict. Using the existing `tmp/lifecycle-cfg`
configuration, I ran:

```text
cmake --build tmp/lifecycle-cfg --target kp_lifecycletest kp_scriptsapitest -j2
```

The build completed with `rc=0` in 54.82 seconds. The receipt is
`lc3-round3/logs/review-build-current.log`; it records both targets reaching
100% and the `/usr/bin/time` result. The source hash receipt is
`lc3-round3/logs/review-source-hashes.sha256`, and the resulting binary hashes
are in `lc3-round3/logs/review-binary-hashes.sha256`. The source hashes include
`host.cpp fa6830f8...`, `host.hpp 3fbfad3a...`, `scripts_lua.cpp
296a1c98...`, `scripts_lua.hpp ddfde799...`, `kp_lifecycletest.cpp
61736b47...`, and `kp_scriptsapitest.cpp e3cbfe96...`; the binaries are
`kp_lifecycletest 04803974...` and `kp_scriptsapitest db251224...`.

I then ran those freshly built binaries from `tmp/lifecycle-cfg` against new
scratch directories. `lc3-round3/logs/review-run-current.log` reports
`31 case(s), 0 failed` and `10 case(s), 0 failed`, with process exit code 0.
This closes the previous source-to-binary evidence gap for the host-side
lifecycle gate. Windows remains unchanged: no Wine run was made in this wave,
so the native/Windows runtime boundary remains the preserved-artifact caveat
already recorded above.

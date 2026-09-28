# Lua lifecycle L1+L2 review (spec compliance, then adversarial)

Reviewer: independent, 2026-09-27. I read the source without editing it. Worktree: `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`.

What I did not do: no git reset, stash, staging or commit in the worktree. I ran no Wine or game and did not touch the live-game lock. All builds and probes live under `/home/brunner56/kp-live-20260922/review-probes-lifecycle/`, called `RP/` below.

I formed my findings list from the plan, the source and my own probes before I read the writer's report. The Grill-me reply is at the end.

## Verdict summary

- **Critical:** none.
- **Important, introduced by this change:**
  - **I1.** A nested dispatch while a new generation is staging sends the old generation's bind/unbind into the new generation's map. Result: the new handler is silently dropped, or a stale ref index is stored.
  - **I2.** Duplicate refusal compares paths as text only. On a case-insensitive directory (the Windows/Wine lookup rule), a case variant of a held or new script name loads the same file a second time. A casefolded tmpfs run shows 2 files on disk becoming 4 running scripts.
- **Minor:** M1 to M9 below. One is in the integration hand-off: the `kp_namespacetest` snippet fails when applied verbatim and passes after a 3-line fix.
- The host tests pass (21/21 and 9/9). With the snippet applied, the tree links.

Lua lifecycle L1+L2 verdict: **FAIL**.
- I1 is in the core R1 staging path and has a passing control, so FAIL stands on I1 alone.
- I2 is the plan's own "refuses a duplicate path" line. It rests on case-insensitive lookup, shown on a Linux casefolded directory. Wine itself was not run.
- Each fix is small and can stay inside the writer's files; see the fix lines.

## Pinned sources

`RP/sha256-at-build.txt` holds the source hashes at build time. I rechecked them after all runs and every file still matched:

| File | sha256 (prefix) |
|---|---|
| `src/lua/host.cpp` | 227714fb |
| `src/lua/host.hpp` | b1d6b1d1 |
| `src/api/scripts_lua.cpp` | 6d0850b5 |
| `src/api/scripts_lua.hpp` | d7bc6d94 |
| `src/api/timers.cpp` | 4d1792bf |
| `src/api/timers.hpp` | 54a7b4e1 |
| `tools/kp_lifecycletest.cpp` | 12bff8f3 |
| `tools/kp_scriptsapitest.cpp` | 8b40582d |

## Commands and outputs

The build uses the writer's recipe and reads worktree sources in place. Outputs go to `RP/bin`, and LuaJIT32 is the scratch copy at `review-probes-u1u2/build/luajit32/src`:

```
g++ -std=c++20 -m32 -Wall -Wextra -Isrc -I$LJ tools/kp_lifecycletest.cpp  <BASE> libluajit.a -lm -ldl   lifecycle-rc=0
g++ ... -DKP_REPO=... tools/kp_scriptsapitest.cpp src/api/scripts_lua.cpp <BASE> ...                   scriptsapi-rc=0
g++ ... RP/probe_lifecycle.cpp src/api/scripts_lua.cpp <BASE> ...                                      probe-rc=0
(0 warnings; RP/build-direct.log)
host-cmd RP/bin/kp_lifecycletest RP/tmp/l   -> "21 case(s), 0 failed" rc=0   (RP/run-kp_lifecycletest.log)
host-cmd RP/bin/kp_scriptsapitest RP/tmp/s  -> "9 case(s), 0 failed"  rc=0   (RP/run-kp_scriptsapitest.log)
host-cmd RP/bin/probe_lifecycle RP/tmp/p    -> rc=0, "created=20143 closed=20143" (RP/run-probe.log)
host-cmd unshare -Urm sh -c 'mount -t tmpfs -o casefold tmpfs RP/cf && mkdir RP/cf/d && chattr +F RP/cf/d && RP/bin/probe_casefold RP/cf/d'
                                            -> rc=0 (RP/run-probe-casefold.log)
```

The fragment itself (`src/lua/lifecycle.cmake`), built in the scratch tree:
```
cmake --build RP/build --target kp_lifecycletest kp_scriptsapitest -j8   build-rc=0  (RP/build-lifecycle-cmake.log)
ctest -L lifecycle --output-on-failure  -> 100% tests passed, 0 tests failed out of 2; labels lifecycle, offline  ctest-rc=0
```

Integration check, in the scratch copy `RP/src` (a git baseline plus the snippet; `RP/integration-snippet-applied.diff`):

```
cmake -S RP/src -B RP/build -DCMAKE_BUILD_TYPE=Release          configure-rc=0
cmake --build . --target kp_namespacetest -j8                    build-rc=0  (kphasor links with scripts_lua.cpp + hook_bodies snippet)
VERBATIM snippet ("add the paths to the bound-name list"):
  kp_namespacetest      -> FAIL: missing kp.scripts (x2)  rc=1
  kp_namespacetest k2   -> FAIL: missing kp.scripts (x2)  rc=1
FIXED (register_all in install_native + drop the table 'scripts' from the function list):
  kp_namespacetest      -> namespace contract: 0 failure(s) rc=0
  kp_namespacetest k2   -> namespace contract: 0 failure(s) rc=0
```

## Stage 1: spec compliance (plan L1, L2, §4; rulings R1-R4)

claim: unload_one/reload_one/load_path, generation, stamp-at-load, deleted-file unload, on_state_closing, request queue, R1.
referent: `host.cpp:360-430,432-503,348-352,621-672,81-85,110-193`; tests `lifecycle.*` 21/21.
checked: RP/run-kp_lifecycletest.log
verdict: holds, except the duplicate-path line (I2) and the R1 staging edge (I1).
confidence: high.

claim: R1: a failed hot reload keeps the running script, with its timers and handlers intact.
referent: probe P1 (string and function timers, with syntax and runtime-throw variants): `state=Loaded gen=1 timers=2 L=<same>`, global pending `before=2 after=2` (the staged chunk's own timers do not leak), then after pump `str=1 fn=1 staged-fn=0`.
checked: RP/run-probe.log P1
verdict: holds. The shipped test covers handlers only; P1 covers timers.
confidence: high.

claim: R2: all Lua lifecycle requests are deferred.
referent: `scripts_lua.cpp:78-91` only queues; `lifecycle.request_from_own_callback_deferred`, `request_from_timer_deferred`, `scripts_api.self_unload_from_callback_safe`; probe P10 (a's OnTick unloads b, and b still runs that tick; b's own OnScriptUnload re-queues its load, which takes effect on the next service).
checked: RP logs
verdict: holds
confidence: high

claim: R3: `kp.random` is not bound. R4: unload does not restore native changes.
referent: `grep random src/api/scripts_lua.cpp` finds nothing; no ownership module.
verdict: holds

claim: the L2 surface shape, console `scriptname()` returning nil, and lowercase names that are not NWScript names.
referent: `scripts_api.*` 9/9. I grepped the eight names myself against `data/routines/k1.json`, `k2.json` and both corpus `nwscript.nss` files, case-insensitively, including constants: no hits.
verdict: holds (a null move on the NWScript-name attack).

claim (report): "Integration snippet ... `tools/kp_namespacetest.cpp`: add the paths ... to the bound-name list."
referent: verbatim application gives `FAIL: missing kp.scripts` rc=1 on k1 and k2.
verdict: does not hold as written. See M8 for the fix.
confidence: high

## Stage 2: adversarial findings

### I1. Important, new. Nested dispatch during staging lets the old generation corrupt the new generation's bindings.

`Script::bind_callback` (`host.cpp:195-208`) chooses its target map from the flag `staging_chunk_`. It does not check which `lua_State` made the ref. While the new chunk runs, the old generation is still `Loaded` and still dispatchable. `Host::dispatch` (`host.cpp:532`) has no busy refusal, and `do_reload` does not hide the script.

So any synchronous re-entry into dispatch from the staged chunk's top level runs the old generation's handlers with `staging_chunk_ == true`. When one of those handlers calls `kp.events.register` or `unregister`, the call lands in `staged_bound_`:
- `luaL_unref(N, …, new_ref)` releases the new generation's own handler.
- An index from the OLD state's registry is then stored as the new binding.

This did not happen before this change. The old `Script::load` called `unload()` first, so the script was `Unloaded` while its chunk ran (`git show HEAD:src/lua/host.cpp:63-64`).

Probe P0 uses a C function that calls `host->dispatch(OnTick)` from the staged chunk (`RP/run-probe.log`):
```
bind-variant:    old OnTick binds OnSave   -> reload ok=1 bound(OnSave)=1 -> OnSave after commit: called=0 new-onsave=0 old-onsave=0
unbind-variant:  old OnTick unbinds OnSave -> reload ok=1 bound(OnSave)=0 -> OnSave after commit: called=0 new-onsave=0
control:         old OnTick is a no-op      -> old-tick-noop=1 (nested dispatch reached the old generation)
                                              reload ok=1 bound(OnSave)=1 -> OnSave after commit: called=1 new-onsave=1
```
The control shows that the nested dispatch alone does not drop the binding. The old handler's bind or unbind is the cause. In both variants the new generation's top-level `OnSave` handler is gone. In the bind variant the map holds a stale index, and it is only luck which value that index names in the new registry. It could be a timer's callback function.

Reachability in game is `unverified`. The likely path: a chunk top-level `nwscript.call('ExecuteScript', …)` runs the engine's RunScript, which fires `vm.run_script` and then `OnRunScript` dispatch (`hook_bodies.cpp:700-725`; OnRunScript is "Live" per `docs/user/api-status.md:100`). `scripts/examples/harness/90_run_script.lua:30` does exactly this at top level. Whether ExecuteScript is synchronous in K1 was not run here.

Fix, inside the writer's files: in `Host::dispatch` and `dispatch_one`, skip a script while `s.staged()` is true. The old generation then gets no events while its successor's chunk runs, which matches the pre-change behaviour. The alternative (pass `L` into `bind_callback` and route by the calling state) is more exact, but it touches `src/api/compat.cpp`, which another writer owns.

### I2. Important, partial requirement. Duplicate refusal is lexical, so a case variant runs a file twice.

`do_load_path` refuses on `sp->path() == path || sp->name() == name` (`host.cpp:372-373`), after `lexically_normal` (`:38-40`). `find` compares names case-sensitively (`:356`). A request builds `<dir>/<name>.lua` and accepts it if `is_regular_file` is true (`:464-469`).

Run here, on a case-insensitive directory: a casefolded tmpfs inside a user namespace, the Linux stand-in for Windows/Wine lookup (`RP/run-probe-casefold.log`):
```
casefold lookup: exists(10_COVER.lua)=1
after load_all:        [10_cover 10_cover.lua]
request 10_COVER -> OK ; request NEWFILE -> OK      (newfile.lua created on disk first)
after service:         [10_COVER] [10_cover] [NEWFILE]
after hot-reload poll: [10_COVER] [10_cover] [NEWFILE] [newfile]
one OnTick ran 4 handler bodies from 2 files on disk
```
- `load('10_COVER')` while `10_cover` is held passes every check and runs a second copy.
- `load('NEWFILE')` loads `newfile.lua` under the requested spelling. The next poll lists the on-disk spelling, finds it missing from `held` (`:626-629`), and loads it again.
- Wine's own lookup was not run; the rating depends on it matching casefold behaviour.
- For comparison only: probe P7b hard-links `b.lua` to `a.lua` and loads it, which also runs twice. That is two directory entries, which `load_all` would load anyway, so it only shows the comparison is lexical. It is not part of the defect.

Fix: before loading, compare with `fs::equivalent` against held paths. Or resolve a request name against the actual `list_script_paths()` entries, case-insensitively on `_WIN32`, and store the on-disk spelling.

### Minor

- **M1. A non-atomic save bypasses R1 and explicit unload** (P3). Some editors rename the original away and then write a new file. If a poll lands in that window:
  - The script is erased and gets OnScriptUnload. It comes back later as a new entry with generation 1.
  - If the rewritten file is broken, the result is `FailedToLoad gen=0`. The running generation is already gone, so R1 is lost.
  - An explicitly `Unloaded` script comes back `Loaded` after the window.
  - An atomic rename-over behaves correctly: gen 2, entry kept.
  - Fix: treat a script as deleted only when it has been absent for two polls.
- **M2. A truncated file mid-write is a valid empty chunk** (P4: `gen=2`, and the handler fired 0 times). The next poll recovers. Same mitigation as M1.
- **M3. The queue has no bound and no coalescing** (P6):
  - 20,000 `kp.scripts.reload('b')` calls ran in one `service_requests`: `ran=20000 in 15328 ms`, `gen=20001`.
  - A script that reloads itself from OnScriptLoad reloads once per service, forever (gen 6 after 5 services).
  - This is not a new capability, since `while true do end` already freezes. The accidental case is cheap to prevent: coalesce identical pending (op, name) pairs, and cap the queue or the per-tick work.
- **M4. The NUL byte passes `bare_name`** (`host.cpp:43-46`). In P7, `kp.scripts.load('notlua\0x')` returned OK and ran a file named `notlua` with no `.lua` extension, held as name `notlua\0x`. It is limited to the scripts directory, because slashes and `..` are still rejected. Fix: reject `'\0'`, or look names up in `list_script_paths()`.
- **M5. Queued requests survive `load_all`** (P9). An unload queued before the console `lua reload` unloaded the freshly loaded script on the next service. Fix: `load_all` or `unload_all` should fail the pending queue with "host reloaded".
- **M6. `result(id)` casts the double without a range check** (`scripts_lua.cpp:97-99`). `math.huge` or `2^64` is undefined behaviour in the `uint64_t` cast; x86 returned nil (P8). `ID + 0.5` aliases `ID`. `removetimer` already has the guard to copy (`timers.cpp:351`).
- **M7. Reload order change.** The new chunk's top level now runs before the old generation's OnScriptUnload. In P2, the new top level called `setflag(2)`, the old unload called `setflag(0)`, and the final value was `0`. No shipped example does native work at top level that its OnScriptUnload undoes (grep of `scripts/**/*.lua`). The integrator should document it: do native setup in OnScriptLoad, not at top level. It is disclosed as behaviour change 1, but not as a hazard.
- **M8. The integration hand-off for `kp_namespacetest` is incomplete.** `install_native` has its own registration list, and the path loop asserts `type(v)=='function'`, which fails for the table `kp.scripts`. The minimal fix is 3 lines (`RP/integration-snippet-applied.diff`):
  - `#include "api/scripts_lua.hpp"`
  - `kp::api::scripts::register_all(L);` in `install_native`
  - list only `scripts.list` through `scriptdir`

  With it, k1 and k2 both report 0 failures. Also, `register_all` makes a fresh `kp.scripts` table on each call (`scripts_lua.cpp:147`). That breaks the test's "re-registration preserves shared tables" rule if someone asserts it for `scripts`; it is harmless in the runtime.
- **M9. A symlink in the scripts dir can point outside it** (P7: `link.lua` loaded `outside/evil.lua`). This is informational. Scripts already get `io`, `os`, `dofile` and `kp.mem` (`runtime.cpp:692-711`; `luaL_openlibs` at `host.cpp:126`), so path containment is not a security boundary. The `bare_name` check stops `../` in request names, which is what matters.

### Null moves (attacked, held)

- **mtime granularity.** On btrfs (scratch), 0 of 200 back-to-back rewrites left mtime unchanged. 0 of 50 immediate edits after load were missed (P5). The game dir's ext4 was not measured. The shipped test sidesteps this by bumping mtime by 2 s (`kp_lifecycletest.cpp:163-169`).
- **Generation counters.** Monotonic across unload/load and reload within one Host (`explicit_unload_survives_poll`; P10 gen 1→2). They reset only when the entry is recreated (`load_all`, or delete then recreate; see M1).
- **Function-timer refs and the closing guard.** The staged chunk's function timers die with the discarded state, with no leak (P1). The create and close counts match over 20,141 states (P6 included). The sentinel's `closing` flag is untouched by this change.
- **Unload during its own callback, a timer pump or event dispatch.** The sync methods refuse while busy (`sync_refused_while_dispatching`). Lua can only queue.
- **Teardown.** After `bind_host(nullptr)`, OnScriptUnload's `kp.scripts.list` raises "no script host is running" rather than crashing (P11).
- **`kp.scriptname` / `kp.scriptdir` leakage.** `scriptdir` returns the path `kp.gamedir()` and `io` already expose. `list()` shows other scripts' paths and errors. Scripts share the process and `kp.mem`, so there is no new exposure.
- **Disclosed residuals, which hold as disclosed:** the timer pump does not count toward `depth_`, and `load_all`/`unload_all` have no busy guard (report "Residual proof boundary").

## Grill-me reply (read after the above)

Weakest first: **#2** ("How do top-level bindings in a replacement chunk avoid landing on the old state?").

- claim: `staging_chunk_` routing keeps bindings on the right state, and the old OnScriptUnload binds against the old state.
- referent: `lifecycle.old_unload_cannot_touch_new_bindings` covers OnScriptUnload only. P0 covers the other direction: an old handler reached through nested dispatch while `staging_chunk_==true` lands on the staged map. The P0 control (a no-op old handler) keeps `new-onsave=1`, so the probe is not the cause.
- checked: RP/run-probe.log P0
- verdict: does not hold in general (I1)
- confidence: high on the host; in-game reachability is `unverified`.

The rest:
- **#1** (failed reload keeps the old script): holds, and P1 adds timers.
- **#3** (self-unload safe): holds. Tests plus P10.
- **#4** (live registration): not yet. The snippet builds, but its namespacetest part fails verbatim (M8).
- **#5** (R4): holds.

Questions the writer missed:
- Is duplicate refusal proof against case variants? No (I2, casefold run).
- Does a non-atomic save bypass R1? Yes (M1).
- Is the queue bounded? No (M3).
- Does a queued request survive `lua reload`? Yes (M5).

## Hand-off: the one question I could not settle

Does `nwscript.call('ExecuteScript', …)` at chunk top level run `vm.run_script` synchronously inside the Lua call in K1 GOG? That decides whether I1 can happen in game today.

The one check: a private live fixture whose top level calls ExecuteScript. It should log from its old generation's `OnRunScript` during a hot reload, then report `kp.scripts.list()` and whether its new OnRunScript binding still fires.

Lua lifecycle L1+L2 verdict: FAIL

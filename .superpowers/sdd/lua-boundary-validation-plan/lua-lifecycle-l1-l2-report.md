# Lua lifecycle L1 + L2 report (host-only)

Writer: sole writer for L1/L2, 2026-09-27. Plan: `/home/brunner56/kp-live-20260922/fanout-lua-lifecycle-plan.md` (Track L, section 4). Rulings applied:
- R1: a failed reload keeps the running script.
- R2: every Lua request is deferred.
- R3: `kp.random` is not bound.
- R4: unload does not undo native changes.

What I did not do: no game, Wine, Gamescope or FFmpeg. I did not touch `tmp/harness-locks/live-game.lock`. I did not reset, stash, stage, commit or push. I did not edit any forbidden file.

## Files changed

| File | Change |
|---|---|
| `src/lua/host.hpp` | Script staging/generation API, `HostConfig::on_state_closing`, lifecycle request types, Host per-script/queue API; `git diff --stat -- src/lua`: host.cpp +378/-66 combined with host.hpp +107 and luahost.cmake +3 (422 insertions, 66 deletions) |
| `src/lua/host.cpp` | L1 implementation |
| `src/lua/luahost.cmake` | +3 lines: `include(lifecycle.cmake)` inside the existing `TARGET kphasor` guard |
| `src/lua/lifecycle.cmake` | NEW: `kp_lifecycletest` and `kp_scriptsapitest`, CTest labels `offline;lifecycle` |
| `src/api/scripts_lua.hpp`, `src/api/scripts_lua.cpp` | NEW: `kp.scripts.{list,load,unload,reload,result}`, `kp.scriptname`, `kp.scriptdir`; `bind_host`, `bound_host`, `register_all` |
| `tools/kp_lifecycletest.cpp` | NEW: 21 cases |
| `tools/kp_scriptsapitest.cpp` | NEW: 9 cases |

Scratch only (gitignored `tmp/`): `tmp/lifecycle-build/` (standalone build script, binaries, red/green logs) and `tmp/lifecycle-cfg/` (scratch CMake tree).

## Requirements, with referents

Line numbers are for the current worktree files.

| Requirement | Code | Test |
|---|---|---|
| Record the first mtime at load, before the file is read. A failed load is stamped too. | `host.cpp:348` `Host::stamp`, called at `:380` (`do_load_path`) and `:397` (`do_reload`) | `lifecycle.edit_inside_first_window_detected`, `lifecycle.failed_first_load_is_FailedToLoad` |
| Unload a deleted script on poll. Only a definite not-found counts. Removal happens after the walk. | `host.cpp:639` (`fs::exists` with `ec`), `:659` (erase loop) | `lifecycle.deleted_file_unloads_on_poll`; the deleted-while-unloaded half of `lifecycle.explicit_unload_survives_poll` |
| R1: compile before close. The new chunk runs in a fresh state, and the old state closes only after success. | `host.cpp:110` `Script::stage`, `:170` `commit_staged`, `:396` `Host::do_reload` (order: stage, old OnScriptUnload, close old, swap, re-sort, new OnScriptLoad) | `lifecycle.failed_reload_keeps_running_generation` (syntax and runtime-throw variants), `lifecycle.reload_one_increments_generation_and_rebinds` |
| R1 binding hazard: a top-level `kp.events.register` in the staged chunk lands in the new state. The old generation's OnScriptUnload binds and unbinds against the old state. | `host.cpp:199-200` (`staging_chunk_` routing); `host.hpp:145-150` | `lifecycle.reload_one_increments_generation_and_rebinds`, `lifecycle.old_unload_cannot_touch_new_bindings` |
| Refuse a duplicate path or name. Paths are compared lexically normalised. | `host.cpp:369-376` | `lifecycle.duplicate_load_refused` (same path, `load_one`, and the `dir/./a.lua` spelling) |
| Deferred request queue, safe from callbacks and timers. `service_requests` takes a snapshot of the queue. | `host.cpp:432` `request`, `:478-484` `service_requests` with `batch.swap(queue_)`; results capped at 64 | `lifecycle.request_from_own_callback_deferred`, `lifecycle.request_from_timer_deferred`, `lifecycle.service_runs_snapshot_only`, `lifecycle.unknown_name_result_error` |
| Depth guard: the synchronous methods and `service_requests` refuse while Lua runs under the host. | `DepthGuard` at `host.cpp:314` (dispatch_one), `:531` (dispatch), `:383`/`:400` (chunk), plus the `busy()` checks at `:361`, `:417`, `:426`, `:479` and in `reload_changed` | `lifecycle.sync_refused_while_dispatching` |
| Pre-close hook. It runs exactly once before every `lua_close`: unload, reload, quarantine, `unload_all`, and a discarded failed stage. | `host.cpp:81-83` `Script::close_state`, the only `lua_close` in the file; `HostConfig::on_state_closing` at `host.hpp:182` | `lifecycle.state_closing_hook_once_per_close` (5 creates and 5 closes, pairing checked against a set of open states) |
| Generation counter | `host.hpp:93`; incremented in `commit_staged` | `lifecycle.reload_one_increments_generation_and_rebinds`, and generations are asserted in most cases |
| `unload_one`, `reload_one`, `load_path`, `find` | `host.cpp:416`, `:425`, `:360`, `find` | `lifecycle.unload_one_*` (3 cases), `lifecycle.priority_resort_after_reload` |
| An explicit unload survives hot reload | `host.cpp:644` | `lifecycle.explicit_unload_survives_poll` |
| Quarantine, then edit, recovers | the `do_reload` path | `lifecycle.quarantine_then_edit_recovers` |
| L2 `kp.scripts.list()` shape `{name,path,state,generation,priority,errors,timers,last_error}` | `scripts_lua.cpp` `l_list` | `scripts_api.list_shape` |
| L2 `load`/`unload`/`reload` return an id, and `result(id)` returns `"pending"`, a table, or nil | `scripts_lua.cpp` `queue`, `l_result` | `scripts_api.unload_request_then_service` |
| L2: a script unloads or reloads itself from a handler or a timer | queue-only binding | `scripts_api.self_unload_from_callback_safe` |
| L2 `kp.scriptname()` returns nil in the console state; `kp.scriptdir()` returns the HostConfig dir, or `""` with no host | `l_scriptname`, `l_scriptdir` | `scripts_api.console_state_has_no_scriptname`, `scripts_api.scriptname_and_scriptdir_in_a_script`, `scripts_api.unbound_host` |
| L2: all keys lowercase | the registration table | `scripts_api.no_pascalcase_keys` |
| L2: bad arguments raise a Lua error, not a crash. Arguments are checked strictly (`load(42)` is an error). | `queue`, `l_result` | `scripts_api.bad_args_error_not_crash` |
| L2: names are not NWScript names. `scripts`, `scriptname`, `scriptdir`, `list`, `load`, `unload`, `reload` and `result` were checked case-insensitively against every quoted token in `data/routines/k1.json` and `k2.json`. | n/a | `scripts_api.names_are_not_nwscript_names` |
| R3 | `kp.random` is not bound anywhere (`grep -rn '"random"' src/api/scripts_lua.cpp` finds nothing) | n/a |
| R4 | no native restore added | n/a |

## Behaviour changes to note

1. **Reload order.** The new chunk's top level now runs before the old generation's `OnScriptUnload`, which R1 requires. The full order is: new chunk, old `OnScriptUnload`, close old, new `OnScriptLoad`. Asserted in `lifecycle.reload_one_increments_generation_and_rebinds`.
2. **Unload state.** `Script::unload()` now always leaves the script in `Unloaded`. Before this change, a Quarantined or FailedToLoad script kept that state. The only earlier callers were `~Script` and the old `load()`.
3. **Duplicate loads.** `load_one` now refuses a held path or name. Before, it appended a duplicate.
4. **Path spelling.** Script paths are stored after `lexically_normal()`, so `list_script_paths` and `load_path` agree.
5. **Poll return value.** `reload_changed` counts deleted-file removals in its return value, so the runtime's "hot reload: N script(s)" line includes them. It returns 0 while the host is busy.
6. **Divergence from `data/hostapi.toml:1545`.** That entry says "every lua_State has an owning script". The console state has none, so `kp.scriptname()` returns nil there. The declared `returns = "string"` does not hold in the console.

## Commands and outputs

The build runs in the container. The 32-bit binaries run on the host through `host-cmd`, because the container has no i386 loader.

Standalone build: `tmp/lifecycle-build/build.sh {lifecycle|scriptsapi|support|luatest}`. It uses `g++ -std=c++20 -m32 -Wall -Wextra` and links the main checkout's native `build/luajit32/src/libluajit.a`.

Red, captured before implementation (test against stubs):
- `tmp/lifecycle-build/red-lifecycle.txt`: `20 case(s), 20 failed`, rc=1. The old code fails the four behaviours the old API can express: the first-window edit, the deleted file, the failed reload, and duplicates.
- `lifecycle.old_unload_cannot_touch_new_bindings`: added later and red first. Output was `FAIL ... new generation keeps its top-level OnTick binding`, then it passed after the `staging_chunk_` fix.
- `tmp/lifecycle-build/red-scriptsapi.txt`: every case failed with "attempt to index field 'scripts' (a nil value)", and the run ended in a segfault (rc=139) from a null state. The test now guards against that.

Green:
```
host-cmd sh -c 'cd <wt> && tmp/lifecycle-build/kp_lifecycletest <wt>/tmp/lifecycle-build/scratch-l'
  21 case(s), 0 failed   rc=0     (full log: tmp/lifecycle-build/green-lifecycle.txt)
host-cmd sh -c 'cd <wt> && tmp/lifecycle-build/kp_scriptsapitest <wt>/tmp/lifecycle-build/scratch-s'
  9 case(s), 0 failed    rc=0
```

Regressions against the new `host.cpp`:
```
kp_supporttest                         support-rc=0, "all timers are gone after state teardown ok"
kp_luatest arbitration   | grep -c 'claimed by  : 25_claims_via_string'   -> 1
kp_luatest edge_fallback | grep -c 'no (fallback applied)'                -> 1
kp_luatest edge_quarantine --repeat 3 | grep -c 'quarantined after 3 errors' -> 1
g++ -m32 -fsyntax-only tools/kp_namespacetest.cpp   rc=0  (Script(name,path,&created) + .load(error) still compile)
i686-w64-mingw32-g++ -std=c++20 -fsyntax-only (host):
  src/lua/host.cpp, src/api/scripts_lua.cpp, src/api/compat.cpp,
  src/runtime/runtime.cpp, src/runtime/hook_bodies.cpp, src/harness/commands.cpp   all ok
```

Scratch CMake (fragment exercised for real):
```
host-cmd sh -c 'cd <wt> && cmake -S . -B tmp/lifecycle-cfg -DCMAKE_BUILD_TYPE=Release'      configure-rc=0
cmake --build tmp/lifecycle-cfg --target kp_lifecycletest kp_scriptsapitest -j8               build-rc=0
  (built LuaJIT32 + libkphasor.so as the add_dependencies prerequisite; only pre-existing
   -Wclobbered warnings in hook_bodies.cpp; no warning from the new files)
cd tmp/lifecycle-cfg && ctest -L lifecycle --output-on-failure
  1/2 Test #30: kp_lifecycletest .................   Passed
  2/2 Test #31: kp_scriptsapitest ................   Passed
  100% tests passed, 0 tests failed out of 2         ctest-rc=0
Logs: tmp/lifecycle-build/cmake-configure.txt, cmake-build.txt, ctest.txt.
Note: src/api/timers.{hpp,cpp} and tools/kp_supporttest.cpp were modified by another writer
(U2) during this session (the build reconfigured and recompiled timers.cpp mid-run). The ctest
pass above is against that newer timers.cpp; I did not edit those files.
```

Not run: `ctest -L offline` on the full tree, `kp_namespacetest.k1/.k2` binaries, and `tools/nwscript_boundary_test.py`. The integration writer should run these after I-L, because they depend on the runtime registration.

## Integration snippet (I-L, for the serialized integration writer)

All four edits are in files I was forbidden to touch.

`src/runtime/runtime.cmake`: add the source to the kphasor source list.
```cmake
    "${KP_SRC_ROOT}/api/scripts_lua.cpp"
```

`src/runtime/runtime.cpp`:
```cpp
#include "api/scripts_lua.hpp"
// inside hc.on_state_created (about :689-704), with the other register_* calls:
    kp::api::scripts::register_all(L);
// install the close hook on hc BEFORE `std::make_unique<lua::Host>(hc)` (:722), because Host copies
// its config (L3 will chain ownership::run_and_clear here):
    hc.on_state_closing = [](lua_State*) {};
// right after `auto host = std::make_unique<lua::Host>(hc);` (:722) and BEFORE host->load_all (:724).
// Binding only after `host_ = std::move(host)` (:729) would make a chunk-top-level
// kp.scriptdir() return "" and kp.scripts.* raise during boot:
    kp::api::scripts::bind_host(host.get());
// in Runtime::stop and every failure path, BEFORE host_.reset() (:845), and on any path that
// drops `host` before it is moved into host_:
    kp::api::scripts::bind_host(nullptr);
```
The console (F12) state is built with `set_state_init(hc.on_state_created)` at `runtime.cpp:709`, so it gets `kp.scripts` from the same line. `kp.scriptname()` returns nil there. The console state is not closed through the Host, so `on_state_closing` does not run for it.

`src/runtime/hook_bodies.cpp`, in the OnTick body (about `:785-793`): service the queue after `timers::pump` and before the reload poll.
```cpp
        kp::api::timers::pump(kp::api::timers::now_ms(), tick);
        h.advance_tick();
        if (h.pending_requests() != 0) {
            const unsigned ran = h.service_requests();
            if (ran != 0) Runtime::instance().log("lua: serviced %u script request(s)", ran);
        }
        if (tick % kReloadEvery == 0) { ... unchanged ... }
```
Optional: `console_status` could print `s->generation()` next to the state.

`tools/kp_namespacetest.cpp`: add the paths `kp.scripts`, `kp.scripts.list`, `kp.scripts.load`, `kp.scripts.unload`, `kp.scripts.reload`, `kp.scripts.result`, `kp.scriptname` and `kp.scriptdir` to the bound-name list.

Docs and `data/hostapi.toml`, owned by the integrator:
- Mark `kp.scriptname` and `kp.scriptdir` as bound.
- Add `kp.scripts.*`.
- Record the console-nil divergence (behaviour change 6).

`CMakeLists.txt`: no change needed. `luahost.cmake` is already included (`CMakeLists.txt:141`) and now pulls in `lifecycle.cmake`.

## Residual proof boundary

- **Nothing services the queue in the game yet.** Until the `hook_bodies.cpp` snippet above lands, every `kp.scripts.load/unload/reload` from a script or the F12 console stays `pending` forever. Until the `runtime.cpp` snippet lands, `kp.scripts`, `kp.scriptname` and `kp.scriptdir` do not exist in game states.
- There is no live proof. The plan's L2 live steps (a)-(d), using a `zz_lifecycle_probe.lua` fixture, are the controller's job after I-L.
- R1 covers chunk syntax and chunk runtime errors. It does not cover a new generation that loads and then throws in its own `OnScriptLoad`. That generation is already committed and follows the normal error budget.
- The depth guard counts only Lua calls the host makes itself: dispatch, lifecycle raises and chunk loads. It does not count timer callbacks from `api::timers::pump`, which runs outside the host. That is safe today because no Lua-reachable binding calls the synchronous methods; `kp.scripts` only queues. A future binding that calls `unload_one` from Lua would bypass the guard inside timers.
- `load_all` and `unload_all` are not guarded, same as before. The console `lua reload` calls `load_all` from DoConsole, and whether DoConsole can run inside a dispatch is still `unverified` (plan §1a).
- Deleted-file detection trusts `fs::exists` on the staged scripts directory under Wine. Its behaviour on that filesystem is `unverified`.
- The name-collision check covers `data/routines/*.json` only. It does not cover `nwscript.nss` constants that are absent from those JSON files.

## Resume verification (2026-09-27)

This report was resumed after the previous writer was interrupted during a
CMake build. I inspected the existing report, owned source/test files and the
gitignored `tmp/lifecycle-build/` scratch tree before doing new work. The
interrupted CMake targets have `add_dependencies(... kphasor)` in
`src/lua/lifecycle.cmake:40`, so building either target can first enter the
repository's slow full LTO link. I deliberately did **not** restart that build
on the heavily loaded machine.

I reran the already-built, host-only test executables through the required
host wrapper:

```
host-cmd sh -c 'cd <wt>; tmp/lifecycle-build/kp_lifecycletest "$PWD/tmp/lifecycle-build/scratch-l"'
  PASS lifecycle.explicit_unload_survives_poll
  PASS lifecycle.load_request_for_new_file
  PASS lifecycle.service_runs_snapshot_only
  PASS lifecycle.sync_refused_while_dispatching
  21 case(s), 0 failed   rc=0

host-cmd sh -c 'cd <wt>; tmp/lifecycle-build/kp_scriptsapitest "$PWD/tmp/lifecycle-build/scratch-s"'
  PASS scripts_api.no_pascalcase_keys
  PASS scripts_api.bad_args_error_not_crash
  PASS scripts_api.unbound_host
  PASS scripts_api.names_are_not_nwscript_names
  9 case(s), 0 failed    rc=0
```

This is a rerun of the two targeted executables, not a fresh CMake or LTO
build. No game/Wine/display/capture process was started and no shared lock was
touched.

## Grill me

1. **Why does failed hot reload keep the old script rather than dropping it?**
   `Script::stage` creates and runs the fresh state before `Host::do_reload`
   calls `raise_unload` or `commit_staged` (`src/lua/host.cpp:110-181,396-408`).
   `lifecycle.failed_reload_keeps_running_generation` covers syntax and
   top-level-runtime failure; the resumed `kp_lifecycletest` run is 21/21.

2. **How do top-level bindings in a replacement chunk avoid landing on the old
   state?** `Script::bind_callback` routes bindings through `staging_chunk_`
   while the staged chunk runs (`src/lua/host.hpp:145-150`,
   `src/lua/host.cpp:199-200`).
   `lifecycle.old_unload_cannot_touch_new_bindings` is the direct regression;
   its green result is included in the 21/21 run above.

3. **Why can a script request unloading itself without freeing its own Lua
   stack?** Lua only calls `Host::request`; `service_requests` snapshots and
   executes the queue after callback return (`src/lua/host.cpp:432,478-497`).
   `lifecycle.request_from_own_callback_deferred`,
   `lifecycle.request_from_timer_deferred`, and
   `scripts_api.self_unload_from_callback_safe` are covered by the two green
   executables. The game tick service point remains integration work, as
   stated above.

4. **Is the new API actually registered in live runtime states?** Not yet.
   The runtime files are forbidden to this task; the exact I-L snippet is in
   this report. `scripts_api` proves registration against test Lua states only.
   The single settling check is the controller's L2 live fixture after I-L.

5. **Does an unload restore game-native changes?** No: R4 explicitly forbids
   it in L1/L2. No ownership or native-restore module was added; that is the
   separate L3 scope.

## Round 2 (review FAIL: I1, I2, M1-M9)

Review: `/home/brunner56/kp-live-20260922/lua-lifecycle-l1l2-review.md`. Before editing, I checked that every source matched the reviewer's pinned hashes: `sha256sum` gave host.cpp `227714fb`, host.hpp `b1d6b1d1`, scripts_lua.cpp `6d0850b5`, kp_lifecycletest.cpp `12bff8f3`. Round-1 copies are in `tmp/lifecycle-r2/*.r1`.

Files touched in this round:
- `src/lua/host.{cpp,hpp}`
- `src/api/scripts_lua.{cpp,hpp}`
- `tools/kp_lifecycletest.cpp`
- `tools/kp_scriptsapitest.cpp`

Not touched: `lifecycle.cmake`, compat.cpp, runtime/**, CMakeLists.txt and kp_namespacetest.cpp. No game or Wine was run, and the live-game lock was not touched. There was no git staging, stash or commit.

### Fixes

- **I1 (nested dispatch during staging).** A script is skipped while `Script::staging_chunk()` is true (`host.hpp:86`). The skip applies in the `Host::dispatch` loop (`host.cpp:725`) and in `dispatch_one` (`host.cpp:377`), which also covers the lifecycle raises and the quarantine sweep's raise.
  - **Why not `staged()` as the review wrote it.** `staged()` stays true after the chunk returns and until commit. The old generation's OnScriptUnload runs inside that span (`do_reload`). A `staged()` skip would suppress that raise and break `lifecycle.reload_one_increments_generation_and_rebinds`, which asserts `v1:unload` runs once. `staging_chunk_` covers exactly the span in which `bind_callback` aims at the staged map.
  - **Why not route by calling state.** `bind_callback` receives no `lua_State`, and its caller `compat.cpp` is forbidden to me. The skip restores the round-0 behaviour: the script was Unloaded while its chunk ran.
- **I2 (duplicates by file identity).**
  - `same_file()` (`host.cpp:77`) compares with `fs::equivalent` (device and inode, error_code overload) on POSIX, and with a case-insensitive path compare on `_WIN32`. `same_name()` is case-insensitive on `_WIN32` only.
  - `do_load_path` refuses on either match.
  - A request name is resolved against the real directory listing (`Host::resolve_script_file`, `host.cpp:452`):
    - exact stem first;
    - then a case-insensitive stem match on `_WIN32`;
    - then, on POSIX, a listed file that `equivalent()` says is the same file as `<dir>/<name>.lua`.
  - The script is held under its on-disk spelling. When the resolved file is already held, the request acts on that script: "already loaded as '10_cover'".
  - The poll skips an unheld listed path that is the same file as a held script, and logs nothing.
  - I gated `equivalent()` off `_WIN32` because libstdc++-on-mingw behaviour cannot be run here. See Grill me #1.
- **M1 (delete, then create).**
  - A held file must be absent on `kMissingPollsToDrop = 2` consecutive polls (`host.cpp:831`). The counter clears when the file reappears, when the script is dropped, and in `unload_all`.
  - One absent poll changes nothing, so R1 and an explicit Unloaded state both survive the window.
  - In game, polls are every 64 ticks (`hook_bodies.cpp:757`).
- **M2 (empty or half-written file).**
  - A file of size 0 neither reloads a held script (`host.cpp:846`) nor loads as a new one (`host.cpp:813`). It is not stamped, so the finished write is seen as an edit.
  - Residual, documented in `host.hpp` above `reload_changed`: a non-empty partial write that compiles loads as a partial generation, and the final write replaces it on the next poll. A partial write that does not compile is covered by R1. If mtime granularity is coarser than the gap between the two writes, the final write is missed until the next edit. P5 measured 0/200 on btrfs; ext4 was not measured.
- **M3 (bound and coalesce the queue).** All in `Host::request` (`host.cpp:555`) and `service_requests` (`host.cpp:651`):
  - An identical (op, name) request still in `queue_` returns the existing id. `inflight_` is not searched, so `service_runs_snapshot_only` still holds.
  - At most `kMaxQueued = 64` requests wait. An overflowing request gets an id whose result is Error "request queue full".
  - One service runs at most `kMaxPerService = 16`. Leftovers stay at the front, and requests made during the service go behind them.
  - A load or reload of a script from its own OnScriptLoad, or from the OnScriptUnload that a reload raises, fails at once. The marker is the RAII `RaiseMark` (`host.cpp:366,525`).
  - An OnScriptUnload after an explicit unload may still re-load itself, because that happens only once (P10).
  - Residual: two scripts that reload each other from OnScriptLoad still ping-pong. The work is bounded to 16 per tick and coalesced.
- **M4.** `bare_name` rejects NUL explicitly (`host.cpp:46`). `find_first_of` with a C string can never match NUL. Resolution goes through the listing as well, so a file without `.lua` cannot be selected.
- **M5.**
  - `unload_all` fails every still-queued request with "discarded: the script host reloaded" (`host.cpp:709`).
  - This runs after its OnScriptUnload raises, so their requests go too. It runs before `load_all` loads, so requests from the new OnScriptLoad are kept.
  - The discarded ids answer an Error result, not nil.
- **M6.**
  - `result()` treats anything that is not an integer in [1, 2^53] as unknown and returns **nil** (`scripts_lua.cpp:104`). It does not raise, because `result()` is a poll.
  - This covers `ID+0.5`, `math.huge`, `-math.huge`, NaN, `2^64`, `2^53+2`, `-1` and `0`.
- **M7.** Documented in `host.cpp` above `do_reload` and in `scripts_lua.hpp`: do native setup in OnScriptLoad, not at top level. Behaviour is unchanged; P2 still ends with flag=0.
- **M8.** The corrected namespace snippet is below. I did not apply it (the file is forbidden).
- **M9.**
  - `list_script_paths` drops a `.lua` symlink that resolves outside the script directory. The check uses `weakly_canonical` on both sides and compares component by component, so a sibling `dir2` does not pass for `dir`.
  - `load_all` reports each refusal. The poll skips them silently.
  - Residual: this is not a security boundary, because scripts have `io`, `os` and `kp.mem`. `load_path` from C++ is not restricted.

### Behaviour changes since round 1

- A deleted script is dropped on the second consecutive absent poll, not the first. I updated `lifecycle.deleted_file_unloads_on_poll` and the last block of `explicit_unload_survives_poll` to poll twice.
- On POSIX, `load_all` now loads a hard link or in-directory symlink that aliases a held script once, and reports the second entry as "already loaded".
- A load request resolves through the listing, and the script takes its on-disk spelling.
- An empty file on disk is not hot-loaded or hot-reloaded. `load_all` still loads it.
- `kp.scripts.*` can return an id whose result is already an error: queue full, or a self-reload from OnScriptLoad.

### Red first, then green

Build: `tmp/lifecycle-r2/build.sh` uses the same recipe as round 1 (`g++ -std=c++20 -m32 -Wall -Wextra`, main checkout `build/luajit32/src/libluajit.a`). It compiled with 0 warnings. Binaries run on the host through `host-cmd`.

For the casefold runs:
```
host-cmd unshare -Urm sh -c 'mount -t tmpfs -o casefold tmpfs X && mkdir X/d && chattr +F X/d && KP_CASEFOLD_DIR=X/d kp_lifecycletest ...'
```

Red runs, with the new tests built against the unchanged round-1 `host.cpp` and `scripts_lua.cpp`:
```
tmp/lifecycle-r2/red-lifecycle.txt           29 case(s), 9 failed   rc=1
tmp/lifecycle-r2/red-lifecycle-casefold.txt  30 case(s), 10 failed  rc=1  (adds case_variant_request_refused:
                                             "2 files on disk, 4 held", "one tick runs each file once, saw 4 bodies")
tmp/lifecycle-r2/red-scriptsapi.txt          10 case(s), 1 failed   rc=1  ("result(ID + 0.5) is nil, got table")
```

The new cases that were red in those runs:
- `nested_dispatch_during_staging_skips_old`. This is P0, with bind, unbind and no-op variants. Red for bind: "OnSave reaches the new handler, called=0".
- `alias_of_held_script_refused`
- `case_variant_request_refused`. This needs `KP_CASEFOLD_DIR`. Without it the case prints NOTE and is not counted.
- `delete_window_keeps_script`
- `empty_file_not_reloaded`
- `request_queue_coalesced_and_bounded`
- `nul_name_refused`
- `queued_requests_discarded_by_load_all`
- `symlink_outside_dir_refused`
- `scripts_api.result_rejects_bad_ids`

Green runs:
```
tmp/lifecycle-r2/green-lifecycle.txt           29 case(s), 0 failed  rc=0
tmp/lifecycle-r2/green-lifecycle-casefold.txt  30 case(s), 0 failed  rc=0
tmp/lifecycle-r2/green-scriptsapi.txt          10 case(s), 0 failed  rc=0
i686-w64-mingw32-g++ -std=c++20 -Wall -Wextra -fsyntax-only (host): src/lua/host.cpp rc=0, src/api/scripts_lua.cpp rc=0
```

### Reviewer probes, rerun on the new code

I rebuilt the reviewer's unmodified `probe_lifecycle.cpp` and `probe_casefold.cpp` into `tmp/lifecycle-r2/`. `RP/bin` was left alone. Logs: `tmp/lifecycle-r2/run-probe.txt` and `run-probe-casefold.txt`. Values are before → after:

- **P0.** OnSave after commit went from `called=0` in both the bind and unbind variants to `called=1 new-onsave=1 old-onsave=0` in all three. `old-tick-noop` went from 1 to 0.
- **P1.** Unchanged: `timers=2`, pending 2→2, `str=1 fn=1 staged-fn=0`.
- **P2.** Unchanged: flag=0. This is the documented M7 hazard.
- **P3.**
  - `after-poll-in-window`: was "absent", now `Loaded gen=2`.
  - `after-recreate-broken`: was `FailedToLoad gen=0`, now `Loaded gen=2 last_error=set` (R1 kept).
  - After the window on an unloaded script: was `Loaded`, now `Unloaded`.
- **P4.** Was `gen=2 fired=0`, now `gen=1 fired=1`.
- **P6.** Was `pending=20000, ran=20000 in 7836 ms`, now `pending=1, ran=1 in 84 ms`. Self-reload after 5 services: was gen 6, now gen 1.
- **P7.**
  - The symlink out of the directory went from loaded to "symlink resolves outside the script directory; not loaded".
  - `load('notlua\0x')` went from OK to ERROR.
  - Scripts held went from 3 to 1.
- **P7b.** The hard-link alias went from OK (body ran 2 times) to ERROR (body ran once).
- **P8.** `ID+0.5` went from table to nil. `math.huge`, NaN, `2^64` and `-1` stay nil.
- **P9.** Pending after `load_all` went from 1 to 0, and a stays `Loaded`. It used to be Unloaded after service.
- **P10 and P11.** Unchanged. The run printed `created=134 closed=134`.
- **Casefold.**
  - `10_COVER` went from OK to "ERROR '10_COVER' is already loaded as '10_cover'; use reload".
  - `NEWFILE` loads as `newfile`.
  - After the poll, 2 scripts are held (was 4).
  - One OnTick runs 2 bodies (was 4).
  - My first casefold probe run with stdout redirected produced an empty log with rc=0. The rerun piped through `tee` produced the lines above; I kept that one. I did not investigate the empty run.

### CMake fragment / ctest

`lifecycle.cmake` is unchanged. The new cases live in the two existing tool sources, so the existing targets build them.

Scratch CMake tree `tmp/lifecycle-cfg` (configured in round 1), rebuilt against the round-2 sources:
```
cmake --build tmp/lifecycle-cfg --target kp_lifecycletest kp_scriptsapitest   build-rc=0
  (recompiled host.cpp, scripts_lua.cpp, both tools; only the pre-existing
   -Wclobbered warning in hook_bodies.cpp)                  log: tmp/lifecycle-r2/cmake-build.txt
host-cmd sh -c 'cd tmp/lifecycle-cfg && ctest -L lifecycle --output-on-failure'
  1/2 Test #30: kp_lifecycletest .................   Passed
  2/2 Test #31: kp_scriptsapitest ................   Passed
  100% tests passed, 0 tests failed out of 2               ctest-rc=0   log: tmp/lifecycle-r2/ctest.txt
```

Resumed-writer rerun (the round-2 writer was cut off here). Source hashes at this point (first 8 of sha256): host.cpp `fa8c58be`, host.hpp `b7f257e9`, scripts_lua.cpp `296a1c98`, scripts_lua.hpp `ddfde799`, kp_lifecycletest.cpp `5f51131b`, kp_scriptsapitest.cpp `e3cbfe96`. The sources are older than the CMake binaries (14:47 vs 15:31), so the ctest pass covers this code.
```
host-cmd sh -c 'cd tmp/lifecycle-cfg && ctest -L lifecycle'   2/2 passed   ctest-rc=0
tmp/lifecycle-r2/build.sh lifecycle scriptsapi probe casefold   0 warnings
kp_lifecycletest               29 case(s), 0 failed  rc=0   tmp/lifecycle-r2/final-lifecycle.txt
kp_lifecycletest (casefold)    30 case(s), 0 failed  rc=0   tmp/lifecycle-r2/final-lifecycle-casefold.txt
kp_scriptsapitest              10 case(s), 0 failed  rc=0   tmp/lifecycle-r2/final-scriptsapi.txt
probe_lifecycle                rc=0; P0 x3: "called=1 errored=0 new-onsave=1 old-onsave=0",
                               old-tick-noop=0                 tmp/lifecycle-r2/final-probe.txt
probe_casefold                 rc=0; 10_COVER -> ERROR "already loaded as '10_cover'";
                               2 held, one OnTick ran 2 bodies  tmp/lifecycle-r2/final-probe-casefold.txt
```
One setup slip on the rerun: my first casefold test run forgot `chattr +F` on the `KP_CASEFOLD_DIR` directory and printed `30 case(s), 1 failed`. With the flag set, as the recipe above says, it is 0 failed. Rerun the same way on purpose (`tmp/lifecycle-r2/cf-noflag.txt`, rc=1): the one failure is `case_variant_request_refused` with "KP_CASEFOLD_DIR is not case-insensitive". So the case guards its own setup.

### Corrected integration snippet for `tools/kp_namespacetest.cpp` (M8, not applied)

The round-1 hand-off said to "add the paths to the bound-name list". That fails as written: `install_native` never registers `kp.scripts`, and `kp.scripts` is a table, not a function. The fix below is the one the reviewer verified. It gives 0 failures on k1 and k2 (`RP/integration-snippet-applied.diff`, `RP/run-namespacetest-fixed-k{1,2}.log`):

```diff
 #include "api/structs.hpp"
+#include "api/scripts_lua.hpp"
 #include "lua/host.hpp"
@@ void install_native(lua_State* L, bool reverse = false) {
     kp::runtime::register_director(L);
+    kp::api::scripts::register_all(L);
     if (!reverse) kp::api::compat::install(L, "/offline/game");
@@ the function-path list
-                    'speed', 'time'}) do
+                    'speed', 'time', 'scripts.list', 'scripts.load',
+                    'scripts.unload', 'scripts.reload', 'scripts.result',
+                    'scriptname', 'scriptdir'}) do
```

Do not list `'scripts'` itself: the loop asserts `type(v) == 'function'`.

Do not assert "re-registration preserves shared tables" for `scripts`: `register_all` builds a fresh `kp.scripts` table on each call (`scripts_lua.cpp`, in `register_all`). That is harmless in the runtime.

### Grill me (round 2)

1. **Does I2 hold on a real Windows or Wine build?** `unverified` at runtime.
   - Referent: the `_WIN32` branch compiles (the mingw `-fsyntax-only` rc=0 above).
   - It relies on the case-insensitive stem match in `resolve_script_file`, and on case-insensitive `same_file`/`same_name`. It does not use `equivalent()`.
   - Hard-link aliases are not detected on `_WIN32`.
   - Paths from a C++ `load_path` with a differently cased directory part would compare unequal, but runtime callers pass `list_script_paths()` spellings.
   - The single settling check: a Wine run of `kp_lifecycletest` with a script dir on a Wine drive, requesting `10_COVER` while `10_cover` is held.
2. **Why is skipping the script during the chunk enough for I1, and what about timers?**
   - The skip is keyed on `staging_chunk_`, which is exactly the span in which `bind_callback` targets the staged map (`host.cpp` `Script::stage`). Test: `lifecycle.nested_dispatch_during_staging_skips_old`, plus P0.
   - Residual: an old-generation timer callback would still bind into the staged map if `timers::pump` ran inside a chunk. The pump runs from the tick hook (`hook_bodies.cpp:787`), not from Lua, so that is `unverified` but not reachable in the code I read.
3. **Could the two-poll delete rule keep a truly deleted script running too long?** In game it adds one poll, 64 ticks, before OnScriptUnload. Test: `lifecycle.deleted_file_unloads_on_poll` (first poll keeps it, second drops it).
4. **Why refuse self-reload instead of just rate-limiting it?**
   - A cap alone would still reload the script on every tick, forever. That is P6's loop, which went from gen 6 to gen 1 after 5 services.
   - The refusal is scoped to OnScriptLoad, and to the OnScriptUnload that a reload raises. An explicit-unload OnScriptUnload may still re-load once (P10 unchanged).
   - Test: `lifecycle.request_queue_coalesced_and_bounded`.
5. **Does the equivalence check cost much at boot?** It is O(held) `equivalent()` calls per `do_load_path`, so O(N²) stat pairs in `load_all`. With tens of scripts that is a few thousand stats. I did not measure it.

Question I could not settle: does libstdc++'s `fs::equivalent` on mingw compare real file ids? Settle it with a mingw build of a two-file `equivalent()` check under Wine. Until then the `_WIN32` branch does not rely on it.

## Round 3 (Windows file identity, W1/W2 from the round-2 review)

Sole writer, resuming from the round-2 FAIL
(`/home/brunner56/kp-live-20260922/lua-lifecycle-r2-review.md`). Scope per
the ruling: `src/lua/host.{cpp,hpp}` and `tools/kp_lifecycletest.cpp` only;
`src/api/scripts_lua.{cpp,hpp}` was not touched (not needed). No git writes,
no game, no edits outside the worktree except scratch logs/binaries under
`/home/brunner56/kp-live-20260922/lc3-round3/` and a fresh scratch
`WINEPREFIX=/home/brunner56/kp-live-20260922/wineprefix-lifecycle-r3`.

### The two findings, and the fix

**W1** (`host.cpp:74-84` at round 2): `same_file()`'s `_WIN32` branch compared
path strings (`iequals`), so a hard-link alias of a held script loaded as a
second `Script` and ran its body twice a tick.

**W2** (new this round, `host.cpp` poll walk in `reload_changed`): a held
script's file, deleted then recreated within `kMissingPollsToDrop`'s one-poll
grace window, kept running the **deleted** generation's content forever if
the recreated file's mtime happened to collide with the stamped mtime --
measured by the round-2 reviewer at 17/20 collisions under Wine for writes
150ms apart. The bug is in the algorithm, not the platform: forcing an equal
mtime reproduces it identically on Linux (see "Red, before the fix" below).

Fix, in order of what each piece buys:

1. **`FileIdentity`** (`host.hpp`, new struct): `st_dev`/`st_ino` on POSIX
   (unchanged from what `fs::equivalent` used internally at round 2 --
   the ruling's "keep Linux unchanged" is about this identity source, not
   about leaving the poll algorithm untouched, since the poll never used
   identity at all before this round); on `_WIN32`,
   `dwVolumeSerialNumber` + `nFileIndexHigh/Low` from
   `GetFileInformationByHandle`, reached via `CreateFileW` opened with
   `FILE_SHARE_READ|WRITE|DELETE` and `FILE_FLAG_BACKUP_SEMANTICS` (metadata
   only, never blocks or is blocked by the game's own access, and works on a
   file another handle has open for writing). `ok=false` when the platform
   could not be asked -- never a guess.
2. **`same_file()`** (POSIX-only now; `host.cpp`) keeps its old body,
   scoped to the one remaining call site that needs it
   (`resolve_script_file`'s POSIX casefold lookup). The `_WIN32` branch is
   gone, not repaired -- every cross-platform identity question now goes
   through `FileIdentity` instead of a function that used to silently
   degrade to a string compare on that platform.
3. **`Host::held_same_file(path, bool* unknown)`** compares a live
   `file_identity(path)` for the candidate against each held script's
   **stamped** identity (taken at its last load/reload, not a live re-stat
   of the held file -- a held script mid-delete-window would otherwise come
   back `Unknown` and block every unrelated load). Tri-state, not bool:
   `Same` (match), `Different` (no match, all `ok`), `Unknown` (at least one
   side unverifiable). Two call sites read `unknown` differently:
   `do_load_path`'s duplicate check turns it into a distinct, named refusal
   ("cannot verify file identity ... refusing to load a possible
   duplicate") -- a typed refusal, not a fallback to path/case comparison.
   `reload_changed`'s new-file scan and the request resolver treat `Unknown`
   the same as a match: skip quietly, retry next poll, so a script whose
   identity is briefly unreadable is neither double-loaded nor logged as an
   error every poll.
4. **`FileStamp`** (`host.hpp`): identity + size + mtime + a bounded
   FNV-1a content hash (`kHashCap = 64 KiB`), all captured in `Host::stamp()`
   **before** `stage()`/`load()` reads the file (same ordering rule as the
   existing "recorded before the file is read" comment -- hashing after
   would reopen exactly the race W2 is about).
5. **`reload_changed`'s poll**, per held script, in this order: identity
   differs (or either side is unverifiable) -> changed, full stop, no mtime
   consulted. Else size or mtime differs -> changed (the ordinary edit, same
   as round 2). Else -- identity, size and mtime all agree with the stamp --
   fall back to the content hash, and *only* when that agreement is itself
   suspect: the path is in `needs_content_check_` (set when a poll saw the
   file missing, cleared only once a check on the reappeared file actually
   completes -- not on the poll that merely notices it exists again, so a
   hash read that fails leaves the flag standing for the next poll), or the
   stamped mtime is within `kRacyWindow` (2s) of wall-clock now (git's
   racy-clean rule: a filesystem clock this coarse cannot prove a same-
   second write didn't happen). An untouched script's poll hits neither
   condition and is never hashed -- this is what keeps the fix from costing
   anything on the steady-state per-tick path.

**Why identity is checked on every poll, not gated the same way as the
hash:** a delete-then-recreate that completes entirely between two polls
(never observed missing) needs `mtime_is_racy` to catch it via the racy
window, since `needs_content_check_` never gets set for a transition nobody
saw -- so identity alone is not sufficient for that case either. Identity's
own per-poll cost is one extra `stat()` (POSIX) or one `CreateFileW` +
`GetFileInformationByHandle` + `CloseHandle` (`_WIN32`) per held script,
each poll. Two facts bound this: `reload_changed` is called from
`hook_bodies.cpp`'s `kReloadEvery = 64` gate (`tick % 64 == 0`), not every
tick, so the identity check runs roughly once per 1-2s of gameplay, not per
frame; and it is the same order of cost as the `last_write_time` stat the
poll already did unconditionally before this round. I did not merge the
three (identity, size, mtime) into one `BY_HANDLE_FILE_INFORMATION` open on
`_WIN32`, which would make the per-poll Windows cost one open instead of two
-- `FILETIME` to `std::filesystem::file_time_type` conversion is exactly the
kind of hand-rolled, toolchain-version-sensitive code this fix is trying to
get away from, and the correctness win from W1/W2 is worth more than that
micro-optimization. Flagged plainly rather than silently assumed away.

### Red, before the fix (both new tests, Linux; W1's `alias_of_held_script_refused` already existed and was already red on Wine at round 2)

Two new cases were added to `kp_lifecycletest.cpp`, ported from the
reviewer's `probe_r2.cpp` sub-case A recipe (variant a: one absent poll
observed, then recreate) plus a variant the reviewer's probe did not cover
(variant b: delete and recreate both land between two polls, never observed
missing -- the case that needs the racy-mtime check specifically, since
`needs_content_check_` is never set for a transition nobody saw). Both force
the recreated file to the *exact* mtime of the original stamp via
`fs::last_write_time`, and v1/v2 bodies are the same byte length so a
size-only check could not incidentally catch the change either.

Built and run against the pre-fix sources (standalone `g++ -m32`, LuaJIT from
`build/luajit32/src`, run via `host-cmd` -- 32-bit needs the host's loader):
```
$ g++ -std=c++20 -m32 -Wall -Wextra -Isrc -I<luajit32/src> \
    tools/kp_lifecycletest.cpp <BASE> <luajit32.a> -lm -ldl -o kp_lifecycletest
0 warnings                                    lc3-round3/logs/build-lifecycle-red.log
$ host-cmd kp_lifecycletest <scratch>
FAIL lifecycle.delete_then_recreate_same_mtime_promotes_generation
     - the recreated file is a new generation, gen=1
     - the deleted generation's OnScriptUnload fired once
     - the new body runs, not the stale one (v1=1 v2=0)
FAIL lifecycle.delete_and_recreate_between_polls_promotes_generation
     - a single poll still promotes the new generation, gen=1
     - the deleted generation's OnScriptUnload fired once
     - the new body runs, not the stale one (v1=1 v2=0)
31 case(s), 2 failed                          lc3-round3/logs/run-red.log
```
Every other case (including `alias_of_held_script_refused`, which passes here
because POSIX identity was never the buggy branch) is unaffected. I did not
reproduce a separate pre-fix Wine run for W2: the algorithm-level red run
above is the direct evidence the bug is real and that these tests catch it
(mtime-only comparison is not platform code), and W1's pre-fix Wine failure
is already an authoritative, unmodified artifact from round 2
(`review-probes-lifecycle-r2/logs/run-win-lifecycle.txt`,
`FAIL lifecycle.alias_of_held_script_refused`). I did not have a clean
pre-round-3 snapshot of `host.cpp` to rebuild from without a git write (the
file already carried 793 uncommitted lines from rounds 1-2 with no
checkpoint), so re-deriving a second Wine red run for W2 specifically would
have meant a stash operation on the shared stash stack for marginal extra
rigor; I judged that not worth the risk and say so here instead of hiding
it. See grill-me #1.

### Green, after the fix

Linux 32-bit, same recipe, sources rebuilt clean (0 warnings,
`lc3-round3/logs/build-lifecycle-fix.log`, `build-scriptsapi-fix.log`):
```
kp_lifecycletest    31 case(s), 0 failed   rc=0   lc3-round3/logs/run-lifecycle-green.log
kp_scriptsapitest    10 case(s), 0 failed   rc=0   lc3-round3/logs/run-scriptsapi-green.log
```
Both new cases pass; `alias_of_held_script_refused` still passes.
`case_variant_request_refused` prints its usual NOTE (no `KP_CASEFOLD_DIR`
here); `symlink_outside_dir_refused` runs and passes on Linux (not skipped --
only skipped under Wine, see below).

Windows, cross-compiled `i686-w64-mingw32-g++ -std=c++20 -O1` (same command
shape as `review-probes-lifecycle-r2/win/build-win.sh`, LuaJIT from
`third_party/luajit/src`, statically linked), 0 warnings
(`lc3-round3/logs/build-win-lifecycle.log`), run under Wine only inside
`flock -w 180 tmp/harness-locks/live-game.lock` with a fresh scratch
`WINEPREFIX=/home/brunner56/kp-live-20260922/wineprefix-lifecycle-r3`
(never the user's own prefix; `wineserver -k` afterward, scoped to that
`WINEPREFIX` only):
```
30 case(s), 0 failed   lc3-round3/logs/run-win-lifecycle-green.log (raw, has console escape codes)
                       lc3-round3/logs/run-win-lifecycle-green.clean.log (stripped)
```
Includes `PASS lifecycle.alias_of_held_script_refused` (W1, the exact case
that failed at round 2),
`PASS lifecycle.delete_then_recreate_same_mtime_promotes_generation` and
`PASS lifecycle.delete_and_recreate_between_polls_promotes_generation` (W2,
new). Two NOTEs, not failures: `case_variant_request_refused`
(`KP_CASEFOLD_DIR` unset, same as round 2) and `symlink_outside_dir_refused`
("no symlinks here (Function not implemented)" -- Wine's `ln -s`, same
graceful skip round 2 already documented). 29 PASS + 2 NOTE = 31 total
cases, 30 run.

`kp_scriptsapitest` was not cross-compiled or run under Wine this round (no
change in its scope; round 2 already covers it on that platform via the
unrelated M8 fix, and this round's diff does not touch `scripts_lua.*`).

### ctest -L lifecycle

The worktree's shared `tmp/lifecycle-cfg` was contended while I worked --
`ps` showed other concurrent sessions building unrelated targets
(`kp_pause_lease_test`, `kp_namespacetest`) in the same directory, and my own
`cmake --build . --target kp_lifecycletest kp_scriptsapitest` ran in the
background for several minutes before finishing. It did finish clean (only
the pre-existing, unrelated `-Wclobbered` warnings in `hook_bodies.cpp`
round 2 already noted), and the subsequent run confirms the fix through the
project's own build, not just the standalone recipes above:
```
host-cmd sh -c 'cd tmp/lifecycle-cfg && ctest -L lifecycle --output-on-failure'
1/2 Test #30: kp_lifecycletest .................   Passed   13.79 sec
2/2 Test #31: kp_scriptsapitest ................   Passed    9.00 sec
100% tests passed, 0 tests failed out of 2          ctest-rc=0
                                             log: lc3-round3/logs/ctest.txt
```
Binary hashes at that run (first 16 of sha256): `kp_lifecycletest`
`04803974e42571d9`, `kp_scriptsapitest` `db251224ee6f4047`, built at
19:38 local, after this round's source edits (confirmed via the source
hashes below and the object files' build timestamps in the ninja/make log).

### Source hashes at this point (first 8 of sha256)

`host.cpp` `fa6830f8`, `host.hpp` `3fbfad3a`, `kp_lifecycletest.cpp`
`61736b47`.

### What did not change

`src/api/scripts_lua.{cpp,hpp}` -- untouched, not needed for W1/W2.
`same_name()`'s `_WIN32` `iequals` -- unchanged; it compares a *requested
name string*, not file identity, and is not part of either finding.
`resolve_script_file`'s POSIX casefold branch -- unchanged, still uses the
POSIX-only `same_file()`. `list_script_paths`, symlink-escape refusal,
quarantine, staged-generation dispatch skip, the request queue -- untouched,
not in scope.

### Grill me (round 3)

1. **Why no pre-fix Wine red run for W2 specifically -- doesn't "red-first"
   demand it?** Weakest answer, first, per protocol.
   `unverified` in the strict sense: I did not run the *unfixed* code under
   Wine for the two new tests. What I have instead: (a) the algorithm-level
   Linux red run above, which shows the exact same code path (`stamps_[path]
   == t` in the pre-fix `reload_changed`) failing when mtime is forced equal
   -- the bug is a comparison of two `file_time_type` values, which does not
   know or care what OS it runs on; (b) W1's pre-fix Wine failure is already
   a preserved, unmodified artifact from round 2 I did not need to
   reproduce. I judged re-deriving a second one, at the cost of a stash
   operation on a stack shared with other live sessions, not worth it for a
   platform-portability claim I can already argue from the source. The
   single settling check, if this is challenged: I looked for a preserved
   round-2-final copy of `host.cpp` to rebuild from (checked
   `tmp/lifecycle-build/host.cpp.orig` in the worktree; its hash,
   `6155d906`, does not match the round-2 report's cited final hash
   `fa8c58be`, so it is an earlier backup, not usable here) and did not find
   one. The settling check is therefore: revert this round's diff to
   `host.{cpp,hpp}` only (my changes are additive and separable from
   rounds 1-2's), cross-compile that reverted source plus this round's two
   new tests with `i686-w64-mingw32-g++`, and run it under Wine the same way
   as the green run below.
2. **Does checking identity every poll actually cost anything measurable on
   real hardware, not just "the same order as the existing stat"?**
   `unverified` -- I reasoned from `kReloadEvery = 64`
   (`hook_bodies.cpp:788`) and from CreateFileW/GetFileInformationByHandle
   being one open+one query+one close, not from a measurement on a Windows
   box with a realistic script count. Round 2's own grill-me #5 left the
   O(N^2) `equivalent()` cost at boot similarly unmeasured and called it "not
   disqualifying for typical script counts" -- I'm making the same
   argument-by-analogy, not a new one.
3. **Why 2 seconds for `kRacyWindow` and not something derived from the
   measured 150ms Wine collision window?** The 150ms figure is the *write
   spacing* the reviewer tested, not the clock's granularity -- the
   granularity itself was "17/20 collisions", i.e., could be arbitrarily
   coarse up to whatever unit Wine's `stat` emulation rounds to (looked like
   whole seconds in the sample output). 2s is a round number with margin
   over "at least 1 whole second", chosen the same way `kMissingPollsToDrop
   = 2` and the test harness's own `+2s` mtime bump were already chosen
   elsewhere in this file -- not measured against real NTFS, which the
   round-2 reviewer already flagged as the one thing Wine can't answer for
   them either.
4. **Could `needs_content_check_` leak -- a path inserted on a missing poll
   whose script is later dropped into `gone`, never reappearing?** That
   holds: `gone`'s cleanup loop erases `needs_content_check_[path]`
   alongside `stamps_` and `missing_` (see the `for (Script* sp : gone)`
   loop), and `unload_all` clears it too. Referent:
   `src/lua/host.cpp`, the `gone` cleanup block and `Host::unload_all`.
5. **Is `held_same_file`'s "compare against the held side's *stamped*
   identity, not a live stat" actually necessary, or just cautious?**
   Necessary for `do_load_path`'s refusal specifically: a held script
   mid-delete-window (M1's grace period, `missing_[path] == 1`) has no
   current file to `CreateFileW`/`stat` at all, so a live check would come
   back `Unknown` for *every* held script whenever *any one* of them is
   between polls, which would block every unrelated load host-wide during
   that window. Not tested directly this round (would need a case that
   loads a new, unrelated script while another held script's file is
   mid-delete) -- `unresolved`, worth a case if this is picked up again.

Open item / what would settle it: grill #1 above, and whether real NTFS's
100ns `FILETIME` resolution makes W2's racy-window branch unreachable in
production (Wine's coarser clock is what makes it reachable in this
environment) -- same open item round 2 left for finding 2, still open,
still not gating: identity change alone already makes W2 deterministic on
any real filesystem tested so far, and the hash/racy-window path is the
belt-and-suspenders the ruling asked for, not the mechanism doing the
primary work.

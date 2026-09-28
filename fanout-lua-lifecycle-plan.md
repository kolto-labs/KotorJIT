# Fan-out unit C: Lua lifecycle, runtime utilities, placeable movement (read-only plan)

Prepared 2026-09-27 by a read-only planner. Worktree read: `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation` (HEAD `ca329e5`, with a dirty tree; see §0). I edited no repository file and ran no build, test, game, Wine, Gamescope or FFmpeg. I did not touch `tmp/harness-locks/live-game.lock`. `WT/` below means the worktree root. Every file:line was read in this session. Anything I did not read or run is marked `unverified`.

Directive being planned (from `WT/docs/user-directive-audit.md:15`): "Real-time placeable movement, familiar Lua utilities, proper script loading/reloading/unloading". Rules applied: native Lua APIs live under `kp.*`. NWScript is reachable only through `nwscript.call`. No Lua name duplicates an NWScript routine or variable name. Harness TOML is a separate test-driver layer.

---

## 0. Shared-file hazard (read first)

`git status --short` (this session) shows these files already modified or untracked by other writers: `CMakeLists.txt`, `src/runtime/runtime.cpp`, `src/runtime/runtime.cmake`, `src/harness/commands.cpp`, `src/api/routines.cpp`, `tools/kp_routinetest.cpp`, `tools/kp_harnesstest.cpp`, many `scripts/harness/kpharness/*.py`, and all `src/api/projectiles*`.

- The camera plan (`/home/brunner56/kp-live-20260922/kp-camera-api-plan.md` §2d) edits `runtime.cpp` (bind block at about `:370-375`, registration at about `:698`, unbind at about `:785`/`:848`), `runtime.cmake:61-64`, `CMakeLists.txt:136`, `data/hooksites.toml`, `data/addresses/k1_gog_103.json`, `docs/lua-api.md`, `docs/user/api-status.md`, `data/hostapi.toml` and `tools/kp_namespacetest.cpp`.
- Consequence: this plan does not put new tests into `kp_routinetest.cpp` or `kp_harnesstest.cpp`, even though the brief names them as examples. Both are dirty, and neither exercises `lua::Host` lifecycle. Each stage below adds a **new** test file and registers it in a `.cmake` fragment that is currently clean (`src/lua/luahost.cmake`, `src/api/support.cmake`, or a new `src/api/motion.cmake`).
- All edits to `runtime.cpp`, `runtime.cmake`, `CMakeLists.txt`, `hook_bodies.cpp`, `kp_namespacetest.cpp` and the public docs are collected into **integration steps (I-x)** owned by one serialized integration writer. That writer is also the camera integrator, or runs strictly after them.

---

## 1. Current state (with referents)

### 1a. Script load / reload / unload

| Fact | Referent |
|---|---|
| One `lua_State` per script, and no shared globals | `src/lua/host.hpp:3-5` |
| States: `Loaded`, `FailedToLoad`, `Quarantined`, `Unloaded` | `src/lua/host.hpp:36-41` |
| Host API: `load_all`, `load_one`, `unload_all`, `reload_changed`. There is **no** `unload_one(name)`, `reload_one(name)` or list/result API | `src/lua/host.hpp:146-152` |
| Hot reload exists. It polls mtimes every `kReloadEvery = 64` server ticks from the MainLoop body. Default is `hot_reload = true` | `src/runtime/hook_bodies.cpp:757,788-793`; `src/lua/host.hpp:126`; `src/runtime/runtime.hpp:49`; ini key `runtime.cpp:257` |
| `reload_changed` loads new files and reloads changed ones. It raises `OnScriptUnload` then `OnScriptLoad` on the single script | `src/lua/host.cpp:384-420` |
| **A deleted file is never unloaded.** `last_write_time` fails, then `if (ec) continue;` | `src/lua/host.cpp:401` |
| **The first stamp is recorded lazily.** `load_all` clears `stamps_`, and a script's mtime is first recorded on the next poll with no reload (`:403`). An edit made inside the first ≤64-tick window after load is therefore missed until the next edit | `src/lua/host.cpp:293,403` |
| **A failed reload destroys the running generation.** `Script::load` calls `unload()` first (`:64`), so a syntax error during hot reload leaves the script `FailedToLoad`, with its previous working state already closed | `src/lua/host.cpp:63-103` |
| `load_one` does not deduplicate. It always appends a new `Script` | `src/lua/host.cpp:258-267` |
| Full reload paths: console `lua reload` → `load_all` (`hook_bodies.cpp:906-915,947`). Harness `reload` → `load_all` (`src/harness/commands.cpp:757-771`). `kp.harness.reload()` sets a flag that the harness drain services later (`src/api/compat.cpp:622-624`; `commands.cpp:1387,1424-1433`) | as cited |
| Lifecycle events `OnScriptLoad(game, build)` and `OnScriptUnload()` exist. Boot dispatches OnScriptLoad once, then enables per-script raises | `data/events.toml:33-53`; `src/runtime/runtime.cpp:738-749`; `src/lua/host.cpp:216-228` |
| **Event-handler teardown on unload works.** Runtime-bound handlers are registry refs in the script's own state. `release_state` drops the map and closes the state | `src/lua/host.cpp:118-126,149-155`; `kp.events.register` binds through `Script::owner` (`src/api/compat.cpp:80-133`) |
| `kp.events.register` fails with "no owning script" in any state that has no `Script` (the F12 console state) | `src/api/compat.cpp:92-94`; confirmed as a product gap in `docs/user-directive-audit.md:50` |
| **Timer teardown on unload works.** A per-state finalised sentinel calls `forget_state` from `lua_close`. `pump` skips non-`Loaded` scripts | `src/api/timers.hpp:31-48`; `src/api/timers.cpp:65-80,145-146`; host proof `tools/kp_supporttest.cpp:446-454` ("all timers are gone after state teardown") |
| **Native side effects are NOT torn down on unload.** `kp.model.resize`, `kp.animation` cues, `kp.speed`, `kp.game_speed` and projectile config have no per-state ownership or restore. `model_lua.cpp` registers no `__gc` and no close hook. A grep for `__gc`/`sentinel`/`forget_state` under `src/` outside timers finds only `enginestruct.cpp:250` (engine struct handles) | `src/api/model_lua.cpp:94-105`; `grep` this session |
| **Per-script state across reload:** none. Each generation is a fresh state, and timers are dropped by design (`timers.hpp:36-44`). The only persistence is the save sidecar `lua_situation.dat` (OnSave/OnLoad) | `src/events/situation.hpp:1-12`; `runtime.cpp:683` |
| Reentrancy: harness/Lua reload requests are deferred. Console `lua reload` runs from the DoConsole hook, outside `Host::dispatch` | `hook_bodies.cpp:937-963`. Whether a nested dispatch can reach DoConsole is `unverified` |
| Shutdown order: `Runtime::stop` uninstalls hooks (`:843`) **before** `host_.reset()` (`:845`), which runs `unload_all` → `OnScriptUnload`. A script calling `nwscript.call` from OnScriptUnload at shutdown is therefore `unverified`-safe | `src/runtime/runtime.cpp:835-846` |
| Existing lifecycle host tests: only quarantine (`kp_luatest.quarantine`, `src/lua/luahost.cmake:58-62`) and the timers-teardown check above. **No test covers** `reload_changed`, OnScriptUnload ordering, deleted files or handler rebinding | `grep reload/unload tools/kp_luatest.cpp tools/kp_supporttest.cpp` |

### 1b. Placeable movement

| Fact | Referent |
|---|---|
| Read-only position: `kp.obj.position(id)` and handle `:position()`, via the routine `GetPosition` (a C++ bridge, not a Lua export) | `src/api/entity.cpp:31,213,375,419,443,456` |
| **No** Lua set-position, orientation, facing or smooth-move API. There is no `src/api/motion*` | `ls src/api/motion*` → absent |
| `data/hostapi.toml` declares an **unbound** `kp.obj.move` through the routine CutsceneMove (k1 id 507). api-status lists it as unbound. Whether CutsceneMove moves placeables is `unverified` | `data/hostapi.toml:1064-1079`; `docs/user/api-status.md:230` |
| Engine setter already called natively: `CSWSObject::SetPosition` via site `server_object.set_position`, flags `(1,1,0)`, used for creatures in multiplayer replay | `data/hooksites.toml:393-400`; `data/addresses/k1_gog_103.json:539-540` (`0x004CD1A0`, expected bytes `538b5c2408…`); `src/runtime/hook_bodies.cpp:267-307,332-352` |
| Struct evidence: `CSWSObject.position` +0x90, `.orientation` +0x9C (set by `SetOrientation 0x4CD170`), dirty word +0x1FC bit 2; `CSWCObject.position` +0x24, `.orientation` +0x30; `CSWSPlaceable.orientation` quaternion at +1064 is **Low** confidence | `src/generated/structs_k1.inc:855-856,925,949-950,1288` |
| Typed placeable lookup: `GetPlaceableByGameObjectID 0x4AE7A0` → internal `0x4B18D0`, type byte ==9 | `structs_k1.inc:1695`; `data/research/phasor_structs.json:6000` |
| Bounded brief with Win K1 GOG and Mac K2 x64 ABI facts (setter args, flags, client wrapper 0x5ED5F0 +0x24, "do NOT reject valid 0xffffffff", no Lua GetPosition/SetPosition aliases, `kp.motion` with distinct capture/relocate/restore names) | `.superpowers/sdd/lua-boundary-validation-plan/task-9-motion-brief.md`. The underlying byte audit `/tmp/kp-native-motion-audit.md` **no longer exists** (`ls` fails), so the brief's addresses other than 0x4CD1A0 are `unverified` until re-derived |
| Mac transform sites (K1 i386 / K2 i386 / K2 x64) | `docs/research/mac-model-memory.md:46-52` (research only, not live) |
| Status in the directive audit: "Native site/ABI/profile research and a bounded implementation brief exist". Movement is not implemented | `docs/user-directive-audit.md:45` |
| Template to copy: `kp.model` is a profile, Backend, checked `Operations`, and a protected userdata capture/restore | `src/api/model.hpp:9-83`, `model_lua.cpp`, `model_profiles.cpp:3-27`, `model.cmake`, `tools/kp_modeltest.cpp`, `tools/tests/model_backend_fixture.hpp`, `tools/model_scene_test.lua` |

### 1c. Lua utility library (bound today)

`kp.print`, `kp.diagnostic`, `kp.console`, `kp.feedback`, `kp.registertimer`/`kp.removetimer` (callbacks by **string name only**), `kp.tokenizestring`, `kp.tokenizecmdstring`, `kp.speed`, `kp.game_speed`, `kp.time`, `kp.gamedir`, `kp.version`, `kp.obj.*`, `kp.struct.*`, `kp.mem.*`, `kp.events.*`, `kp.harness.*`, `kp.model.*`, `kp.animation.*`, `kp.projectiles.*`.

Referents: `docs/user/api-status.md:213-221`; `tools/kp_namespacetest.cpp:98-104`; `src/runtime/runtime.cpp:689-704`; `src/api/support.cmake:18-22`.

Declared but not bound: `kp.vec`, `kp.timer.*`, `kp.scriptname`, `kp.scriptdir`, `kp.random` (`data/hostapi.toml:1290,1463,1533,1545,1722`; `api-status.md:230-238`).

Task 11 ("kp.vec + function-overload `registertimer`") is briefed at `.superpowers/.../task-11-utilities-brief.md` but **not implemented**: `src/api/vector*` is absent and there is no task-11 report. Its research input `/tmp/kp-lua-power-api-research.md` **no longer exists**. The namespace contract test already asserts that no routine name appears as a global or under `kp`/`nwscript` (`tools/kp_namespacetest.cpp:121-131`).

---

## 2. Gaps

G1. There is no per-script unload/reload/load/list. Only whole-host `load_all`. The directive audit asks for this backed by real Host ownership (`user-directive-audit.md:50`).
G2. A deleted script stays loaded (`host.cpp:401`).
G3. The first mtime stamp is lazy, so an early edit is missed (`host.cpp:293,403`).
G4. A failed hot reload kills the working generation (`host.cpp:64`). The desired behavior needs a ruling (see §4 R1).
G5. Duplicate `load_one` is allowed (`host.cpp:258`).
G6. No safe deferred path exists for a script or console to request a lifecycle operation on a specific script. Synchronously closing a state from inside its own callback or timer would be use-after-free. `unverified` whether any current path can do that; the Host has no dispatch-depth guard.
G7. No per-state native ownership exists. Model scale, animation cues and speed survive the script that set them.
G8. There is no generation or evidence counter, so a live test cannot tell "reloaded" from "never unloaded".
G9. Lifecycle has no host tests (§1a last row).
G10. Utilities: `kp.vec` and function-valued timers are missing (Task 11). `kp.scriptname`/`kp.scriptdir` are declared and unbound.
G11. Movement: no `kp.motion` capture/relocate/restore/observe. Orientation is unimplemented. There is no smooth-move helper and no demo.
G12. The Task-9 ABI facts beyond `0x4CD1A0`, which has expected bytes, lost their audit file and must be re-derived before code (`unverified`).

---

## 3. Staged, test-first plan

Convention for every stage: write the failing host test first, register it in CTest, make it pass, then run the regression suites `ctest -L offline`, `kp_namespacetest.k1/.k2`, `tools/nwscript_boundary_test.py` (the camera plan uses the same set), and `i686-w64-mingw32` compile of the touched sources. Live proofs go under the canonical lock, run by the controller. Route TOMLs stay **private** under `/home/brunner56/kp-live-20260922/…` (the established precedent is `release-console-strings.toml`), so no stage touches `scripts/harness/**`.

Proposed Lua names, all lowercase and none equal to an NWScript routine: `kp.scripts.{list,status,load,unload,reload,result}`, `kp.scriptname`, `kp.scriptdir`, `kp.vec`, `kp.motion.{capabilities,capture,relocate,restore,observe}`. Each is added to the namespace contract test at integration time.

### Track L: lifecycle

**L1: Host lifecycle core (pure `src/lua`, no runtime).**
Files: `src/lua/host.hpp`, `src/lua/host.cpp`, new `tools/kp_lifecycletest.cpp`, `src/lua/luahost.cmake` (add `kp_lifecycletest`, labels `offline;lifecycle`, linking like `kp_supporttest` does in `support.cmake:61-80`; it also compiles `api/timers.cpp` and `api/output.cpp` for the timer assertions).
Changes:
- `Host::unload_one(name)`, `Host::reload_one(name)` and `Host::load_path(path)`, which refuses a duplicate path.
- `Script::generation()`, incremented on each successful load.
- Stamp the mtime at load.
- In `reload_changed`, unload and remove scripts whose file vanished.
- `HostConfig::on_state_closing` (a `std::function<void(lua_State*)>`), called exactly once immediately before every `lua_close`: unload, reload, quarantine release and `unload_all`. It is symmetric with `on_state_created` (`host.hpp:131-136`).
- A request queue, `Host::request(op, name) -> id`, plus `Host::service_requests()` and a `results` ring. Nothing ever closes a state synchronously from Lua.
- The G4 behavior, per ruling R1.

Tests (each prints a PASS/FAIL line; the exit code is authoritative):
`lifecycle.unload_one_raises_OnScriptUnload_once`, `lifecycle.unload_one_drops_timers` (`api::timers::pending(L)==0`), `lifecycle.unload_one_drops_bound_handlers`, `lifecycle.reload_one_increments_generation_and_rebinds`, `lifecycle.deleted_file_unloads_on_poll`, `lifecycle.new_file_loads_on_poll`, `lifecycle.edit_inside_first_window_detected`, `lifecycle.duplicate_load_refused`, `lifecycle.failed_reload_<per R1>`, `lifecycle.quarantine_then_edit_recovers`, `lifecycle.state_closing_hook_once_per_close` (covering unload, reload, quarantine and unload_all), `lifecycle.request_from_own_callback_deferred` (the state stays valid until `service_requests`), `lifecycle.request_from_timer_deferred`, `lifecycle.unknown_name_result_error`, `lifecycle.priority_resort_after_reload`.
Minimal live proof: none on its own. L1 is host-only, and its live proof is L2's.

**L2: `kp.scripts` / `kp.scriptname` / `kp.scriptdir` Lua surface.**
Files: new `src/api/scripts_lua.hpp/.cpp` with `bind_host(lua::Host*)`, `register_all(L)`; new `tools/kp_scriptsapitest.cpp`; register it in `src/lua/luahost.cmake`. That file is shared with L1, so L2 runs after L1 or with the same writer.
Semantics: `list()` returns `{name, path, state, generation, priority, errors, timers}`. `load`, `unload` and `reload` return a request id. `result(id)` returns `pending | {ok, error, generation}`. `scriptname()` returns nil in the console state; `scriptdir()` returns the HostConfig dir.
Tests: `scripts_api.list_shape`, `scripts_api.unload_request_then_service`, `scripts_api.self_unload_from_callback_safe`, `scripts_api.console_state_has_no_scriptname`, `scripts_api.no_pascalcase_keys`, `scripts_api.bad_args_error_not_crash`.
Integration **I-L** (serialized):
- `runtime.cpp`: `api::scripts::register_all(L)` inside `on_state_created` (about `:689-704`), `bind_host(host_.get())` after `host_ = std::move(host)` (about `:729`), `bind_host(nullptr)` in stop/fail, and install `on_state_closing`.
- `runtime.cmake`: add `api/scripts_lua.cpp`.
- `hook_bodies.cpp` (clean in git today): call `h.service_requests()` right after `timers::pump` (`:785-786`) and before the reload poll.
- `kp_namespacetest.cpp`: add the new paths.
Minimal live proof (K1 GOG Wine, physical F12 or harness `lua`), using a private fixture script `zz_lifecycle_probe.lua` that counts OnTick, holds one repeating timer and logs `OnScriptLoad`/`OnScriptUnload` with its generation:
- (a) `kp.scripts.list()` shows `generation=1` and `timers=1`.
- (b) `kp.scripts.unload('zz_lifecycle_probe')`, then `result` is `ok`. The runtime log shows exactly one OnScriptUnload line, the tick counter stops advancing across ≥64 ticks, and `list()` shows the state `unloaded`, `timers=0`.
- (c) `load` gives `generation=2` and one OnScriptLoad line.
- (d) A private route overwrites the staged fixture (controller only; staged dir, never the source tree) and generation reaches 3 within ≤64 ticks + 1.
Source-preservation receipt as in prior runs.

**L3: native ownership restore on close.**
Depends on L1's `on_state_closing`.
Files: new `src/api/ownership.hpp/.cpp` (per-`lua_State` list of `{module, restore_fn}`, plus `run_and_clear(L)`); new `tools/kp_ownershiptest.cpp` registered in `support.cmake`.
Modules opt in: motion in M3, and optionally model as a separate stage because it touches `model_lua.cpp`.
Rule: restore runs only while `live()` and before hook uninstall. At `Runtime::stop` it is skipped and logged (§1a shutdown row).
Tests: `ownership.restore_runs_once_on_unload`, `ownership.skipped_when_not_live`, `ownership.restore_failure_logged_not_thrown`, `ownership.cleared_on_explicit_restore`.
Integration I-L3: `runtime.cpp` wires `on_state_closing` to `ownership::run_and_clear` and `runtime.cmake`.
Live proof: combined with M3.

### Track U: utilities (Task 11 scope, unchanged)

**U1: `kp.vec`.**
Files: new `src/api/vector.hpp/.cpp`, new `tools/kp_vectortest.cpp`, `src/api/support.cmake` (add the source and the test), `src/api/output.cpp` (`register_support` calls `register_vector`, `output.cpp:231`).
Semantics per the Task-11 brief: fresh mutable `{x,y,z}` tables with a protected shared metatable; finite numbers only; plain tables still marshal to NWScript vectors unchanged. Method names must not equal routine names; for example, use `length` and `distance`, not `VectorMagnitude` or `GetDistanceBetween`.
Tests: `vec.construct_finite_only`, `vec.arith_ops`, `vec.length_normalize_zero`, `vec.dot_cross`, `vec.lerp_endpoints`, `vec.distance`, `vec.metatable_protected`, `vec.plain_table_still_marshals` (fake VM).
Integration I-U1: `runtime.cmake` source list. `vector.cpp` must also be added there because runtime.cmake enumerates `api/output.cpp`/`timers.cpp` explicitly (`runtime.cmake:55-70`).
Live proof: F12 `return kp.vec(3,4,0):length()` returns `number:5`, plus `nwscript.call('GetPosition', kp.obj.pc():id())` round-trips through `kp.vec`.

**U2: function-valued `kp.registertimer`.**
Files: `src/api/timers.hpp/.cpp`, `tools/kp_supporttest.cpp` (clean today).
Semantics: the existing string path is unchanged. The function ref is released exactly once on complete, cancel, error or state close. There is no second scheduler.
Tests: `timers.function_callback_fires`, `timers.function_ref_released_on_cancel`, `timers.function_ref_released_on_error`, `timers.function_ref_released_on_state_close`, `timers.string_callback_unchanged`.
Live proof: F12 closure timer increments an upvalue 3 times and then stops; `pending` returns to baseline.

Excluded pending ruling R3: `kp.random`, which wraps the routine `Random`. See §4.

### Track M: placeable movement

**M0: evidence re-derivation (read-only, no code).**
Re-derive the Win K1 GOG facts listed in `task-9-motion-brief.md`: typed placeable wrapper and internal, conversion slot, `SetPosition 0x4CD1A0` signature, flags and `ret 16`, the same-position early return, client wrapper `0x5ED5F0` +0x24, and `SetOrientation 0x4CD170`. Use the raw image with SHA `9c10e045…` (the same image as `model_profiles.cpp:17`), in the camera plan's replay style.
Output: a receipt file under `/home/brunner56/kp-live-20260922/`.
Gate: none of M1+ proceeds on a fact without a receipt. Profile data lives in C++ only (model precedent). It is cross-checked by a test against the existing row `data/addresses/k1_gog_103.json:539-540`, **read-only**, so there are no `data/` edits and no conflict with camera.

**M1: read-only `kp.motion.capabilities` / `capture`.**
Files (all new): `src/api/motion.hpp`, `motion.cpp`, `motion_profiles.cpp`, `motion_backend.cpp`, `motion_lua.cpp`, `motion.cmake`, `tools/kp_motiontest.cpp`, `tools/tests/motion_backend_fixture.hpp`.
The capture is protected userdata (as in `model_lua.cpp:11-35`) with fields id, type-checked placeable pointer, server XYZ, orientation vector, area and epoch.
Tests: `motion.unsupported_profile_capabilities_false`, `motion.guard_flip_refuses_before_call`, `motion.non_placeable_type_refuses`, `motion.capture_reads_server_xyz_and_orientation`, `motion.forged_userdata_argerror`, `motion.accepts_client_id_0xffffffff`, `motion.profile_matches_address_table_row` (reads `k1_gog_103.json`).
Integration I-M:
- `runtime.cpp`: `bind_native` after model (about `:370-375`), `register_all` (about `:698`), unbind (about `:784`/`:847`).
- `runtime.cmake`: sources.
- `CMakeLists.txt`: `include(motion.cmake)` next to `model.cmake`/`animation.cmake` (`:136-137`).
- `kp_namespacetest.cpp`.
These are the **same hunks as camera**, so the edits are serialized.
Live proof: spawn one disposable footlocker via `nwscript.call('CreateObject', …)`. `kp.motion.capture(id).position` equals `nwscript.call('GetPosition', id)` within 1e-3. There is no mutation, and the source receipt is unchanged.

**M2: `relocate` / `restore` / `observe`.**
Files: the same M1 files (single writer).
Refusal order: bounds (finite, |step| ≤ configured max, same area) → identity (id, object, area, epoch) → guards → one setter call with flags `(1,1,0)` (precedent at `hook_bodies.cpp:307`) → server readback. `observe(capture)` reads the client XYZ only and never calls the client setter. Restore verifies an exact return to the original.
Tests: `motion.nonfinite_refused_zero_calls`, `motion.step_bound_refused`, `motion.stale_identity_refused`, `motion.area_change_refused`, `motion.relocate_single_setter_call_flags_110`, `motion.readback_mismatch_reports_possible_mutation`, `motion.same_position_reported_noop`, `motion.restore_exact_readback`, `motion.restore_refused_after_identity_change`, `motion.observe_reports_client_lag_without_client_setter`.
Live proof: relocate the footlocker +1.0 m in x. The `GetPosition` oracle agrees (server), `observe` agrees within a bounded N ticks (client), and a screenshot shows it moved. Then restore, and the oracle equals the original. Collision and use-at-destination are **not** claimed (brief: separate acceptance).

**M3: ownership auto-restore.** Depends on L3 and M2.
Files: `motion.cpp`/`motion_lua.cpp`, registering with `ownership`.
Tests: `motion.unload_restores_owned_placeable`, `motion.explicit_restore_clears_ownership`, `motion.unload_after_identity_change_logs_not_writes`.
Live proof: script relocates the crate, then `kp.scripts.unload(...)`. The oracle shows the original position and the log shows one restore line.

**M4: smooth choreography demo.**
Files (new): `scripts/demos/placeable-motion/{motion_scene.lua,README.md}`, `tools/motion_scene_test.lua` (fake `kp`, following the `tools/model_scene_test.lua` pattern), and registration in `motion.cmake`.
Motion: an L-path of per-tick `relocate` calls driven by one function-valued timer (U2) and `kp.vec` lerp (U1), with a corner pause, a return and a restore. NWScript is used only for spawn and oracle.
Tests: `motion_scene.l_path_monotonic`, `motion_scene.pause_at_corner`, `motion_scene.restore_on_failure`, `motion_scene.no_teleport_steps_over_bound`.
Live proof (controller): a continuous 60 fps recording of the fixed first-person camera, the crate visibly sliding, the per-step oracle log, and final restoration. Presentation acceptance is separate from behavior.

**M5 (optional): orientation.** Only if M0 yields a receipt for `SetOrientation 0x4CD170` and the dirty-bit semantics. Otherwise report unsupported. Everything about it is `unverified` today.

### Dependency order

L1 → L2 → L3. U1 and U2 are independent of everything. M0 → M1 → M2 → M3 (also needs L3) → M4 (also needs U1 and U2). Integration I-L, I-U1 and I-M are serialized with the camera integration.

### Parallel-writer disjointness

| Stage | Owned files | Disjoint from |
|---|---|---|
| L1 (+L2, same writer) | `src/lua/host.{hpp,cpp}`, `src/lua/luahost.cmake`, `tools/kp_lifecycletest.cpp`, `src/api/scripts_lua.*`, `tools/kp_scriptsapitest.cpp` | U1, U2, M0-M2, camera, `scripts/harness/**` |
| L3 | `src/api/ownership.*`, `tools/kp_ownershiptest.cpp`, `src/api/support.cmake` | L1/L2, M, camera, harness. **Conflicts with U1** on `support.cmake`, so give it its own cmake line in the same serialized step or the same writer as U1 |
| U1 | `src/api/vector.*`, `tools/kp_vectortest.cpp`, `src/api/support.cmake`, `src/api/output.cpp` | L, U2, M, camera, harness |
| U2 | `src/api/timers.{hpp,cpp}`, `tools/kp_supporttest.cpp` | L, U1, M, camera, harness |
| M0 | none (a receipt outside the repo) | everything |
| M1-M4 | `src/api/motion*`, `src/api/motion.cmake`, `tools/kp_motiontest.cpp`, `tools/tests/motion_backend_fixture.hpp`, `tools/motion_scene_test.lua`, `scripts/demos/placeable-motion/*` | L, U, camera (`src/api/camera*`), harness |
| I-* (one integrator) | `src/runtime/runtime.cpp`, `src/runtime/runtime.cmake`, `src/runtime/hook_bodies.cpp`, `CMakeLists.txt`, `tools/kp_namespacetest.cpp`, `docs/lua-api.md`, `docs/lua-api-complete.md`, `docs/user/scripts.md`, `docs/user/api-status.md`, `data/hostapi.toml` | conflicts with camera integration and with the current uncommitted edits to `runtime.cpp`/`runtime.cmake`/`CMakeLists.txt` |

Result: three writers can run at once (L1+L2, U1, U2), with M0 as a read-only fourth. M1 can start once M0 lands, and none of these touch camera or harness Python. Everything that touches the runtime goes through one integrator.

---

## 4. Rulings needed (open decisions)

- **R1 (G4).** On a failed hot reload, either (a) keep the running generation and report the error, which needs a syntax probe (`luaL_loadfile` in a throwaway state) before `unload`, or (b) keep today's behavior (the script dies to `FailedToLoad`). Criterion: what the user asked for, "proper reloading". A typo killing a live scene reads as improper. The cheaper-to-reverse option is (a), because it only reorders operations. Chunk *runtime* errors still cannot keep the old generation without running two generations side by side; `unverified` whether that is wanted.
- **R2 (G6).** Lifecycle requests are always deferred (proposed), or they run synchronously when the Host is idle. Always-deferred is simpler to prove safe. The cost is that F12 sees `pending` for one tick.
- **R3.** Does `kp.random` (a C++ wrapper around routine `Random`) violate "Lua must not duplicate NWScript names"? The names differ in case, and the ledger's ruling permits C++ bridge conveniences. Leave it unbound until someone rules.
- **R4.** Should model scale, animation cues and `kp.speed` also be auto-restored on unload (L3 opt-in retrofit)? That behavior change touches `model_lua.cpp` and `hook_bodies.cpp`. Proposed as a separate, later stage.

## 5. Unverified items carried forward

- Whether `CutsceneMove` or any NWScript routine moves placeables.
- Every Task-9 ABI fact except `0x4CD1A0` and its expected bytes (the audit file is gone).
- Client propagation latency for placeables.
- Walkmesh and collision rebuild after `SetPosition`.
- Whether OnScriptUnload at shutdown is safe after hook uninstall.
- Whether `DoConsole` can be re-entered during a dispatch.
- Filesystem mtime granularity on the staged scripts directory.
- Mac and K2 runtime support: no Darwin loader exists, so report unsupported.
- The live behavior of every stage above. Nothing here has been run.

### Critical files for implementation
- `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/lua/host.cpp`
- `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/api/timers.cpp`
- `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/api/model_lua.cpp` (template for `motion_lua.cpp`)
- `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/runtime/runtime.cpp` (integration, shared with camera)
- `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/runtime/hook_bodies.cpp` (service point `:785-793`; SetPosition precedent `:307`)

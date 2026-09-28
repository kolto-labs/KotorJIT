# U1 (kp.vec) and U2 (function-valued kp.registertimer): report

Scope: host-only. No Wine, game, Gamescope or FFmpeg. The live-game lock was not touched. Nothing was staged, committed or pushed. Unrelated dirty files were left alone.

## Files

| File | Change |
|---|---|
| `src/api/vector.hpp` | NEW. Contract comment and `register_vector(lua_State*)` |
| `src/api/vector.cpp` | NEW. `kp.vec` constructor (`vector.cpp:91`), operators, methods, `register_vector` (`vector.cpp:288`) |
| `src/api/vector.cmake` | NEW. Self-contained fragment for `kp_vectortest` (links `kphasor`, compiles `vector.cpp` itself) |
| `tools/kp_vectortest.cpp` | NEW. Lua-half tests plus the fake-VM bridge tests |
| `src/api/timers.cpp` | Function callback overload, release-once, closing guard |
| `src/api/timers.hpp` | Header comment rewritten for the overload and the closing guard |
| `tools/kp_supporttest.cpp` | Additions only: `kFnScripts`, `eval_bool`, `find_script`, `pump_range`, `function_timer_cases` (`:488`), one call at `:746`. `git diff` shows 0 removed lines |

Forbidden files were not edited: `host.*`, `runtime.*`, `CMakeLists.txt`, `support.cmake`, namespacetest, routinetest, harness, docs, camera and projectiles.

## U2: function-valued `kp.registertimer`

- **Accepted callback types.** Arg 2 is a string or a function; anything else raises `expected string or function` (`timers.cpp:242`). The string path is unchanged: late global lookup, the same `(id, count, data)` arguments, the same renew rule and the same scheduler.
- **Holding the function.** A function is held by `luaL_ref` and pushed with `lua_rawgeti` at fire time (`timers.cpp:182`).
- **Release exactly once.** The function ref is released only in `cancel_timer`, and in the same step the entry is erased (`timers.cpp:137`). Completion, `removetimer` and a throw all go through that path. On state close, `forget_state` erases without unref, and the registry goes with the state.
- **Error label and budget.** Errors are charged to `function <short_src>:<linedefined>`. One closure definition therefore shares one error budget, the same way one global name does (`Script::record_error` counts per callback name, `host.cpp:171`).
- **Closing guard (pre-existing bug found red).** Under `lua_close`, a script `__gc` can run after the timers sentinel's finaliser. If it calls `kp.registertimer`, it creates an entry whose `L` is freed, and the next `pump` crashes in `Script::owner`. This affected string timers before this change. `Sentinel::closing` is now set by the finaliser (`timers.cpp:75`), and registration raises once it is set (`timers.cpp:246`).

## U1: `kp.vec`

- **Construction.** `kp.vec(x, y, z)` takes exactly three finite numbers, with no string coercion. `kp.vec(t)` copies finite x/y/z out of any table.
- **Result shape.** Every result is a fresh table with raw fields `x`, `y`, `z`, which is the same shape `routines.cpp:194-210` marshals and `:329-345` returns.
- **Operators.** `+ - * / unary- == tostring`. `vec*vec`, `number/vec` and division by zero are errors. `vec == plain table` is false (a Lua 5.1 `__eq` rule).
- **Methods.** `length lengthsq normalize dot cross distance distancesq lerp copy unpack`. Normalizing a zero vector returns a fresh zero vector.
- **Validation.** Fields stay writable, and every op re-validates them.
- **Shared, protected metatable.** `getmetatable(v) == "kp.vec"`, and `setmetatable` raises.
- **Name ruling.** No method name and not `vec` equals an NWScript routine name, case-insensitively. The test checks this against the compiled catalogue, and a Python pass over `data/routines/k1.json`/`k2.json` agrees: `routine hits: []`. `x/y/z` are an open ruling (see below). `kp.random` is not bound, per ruling.

## Tests (names as printed)

**`kp_vectortest`: 14 checks.**
- Lua half: `vec.construct_finite_only`, `vec.arith_ops`, `vec.length_normalize_zero`, `vec.dot_cross`, `vec.lerp_endpoints`, `vec.distance`, `vec.equality`, `vec.metatable_protected`, `vec.mutated_fields_revalidated`, `vec.tostring_unpack_copy`, `vec.names_not_routines`.
- Fake VM through the real `kp::api::call`: `vec.plain_table_still_marshals (kp.vec in)`, `(plain table in)` and `(round trip)`. The round trip goes from a vector return, to a plain table, to `kp.vec(t)`, and back into the same pushed floats.

**`kp_supporttest`: 33 new checks** (43 total with the existing ones).
- Scripts load: `function-timer scripts loaded`.
- `timers.bad_callback_rejected` ×2.
- `timers.function_callback_fires` ×3: the closure increments its upvalue 3 times, receives id/count/data, and stops.
- `timers.string_callback_unchanged` ×3.
- `timers.function_ref_released_on_complete`, `timers.function_ref_released_on_cancel` and `timers.function_ref_released_on_error` each include a control check. The weak-key token must survive `collectgarbage` while the timer is pending, then be collected after the timer ends.
- `timers.function_ref_released_once`: 32 fresh `luaL_ref` slots must all be distinct.
- `timers.function_error_isolated` ×4: one error, the script stays Loaded, the label and message are recorded, and the healthy function timer and named timer on the same pump still run.
- `timers.function_error_budget` ×2: quarantined after 3 errors, and the fourth never runs.
- `timers.function_ref_released_on_state_close` ×6. `pending(L)` goes to 0 on `Script::unload`, and a later pump runs nothing.
  - Both finaliser orders are observed through logged pcall results. From the run: `[close] late fn=true name=true`, meaning it ran before the sentinel, registered, and `forget_state` then dropped the timer. `[close] early fn=false name=false kp.registertimer: this script's state is closing`, meaning it ran after the sentinel and was refused.
  - Both orders are asserted as checks.
- `function timers: pending back to baseline`.

## Commands and outputs

Scratch build: `/home/brunner56/kp-u1u2-build`. The shared build dir was not used. Test binaries are 32-bit, so they run through host-cmd.

```
cmake -S <worktree> -B /home/brunner56/kp-u1u2-build -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_PROJECT_KotorPhasor_INCLUDE=<worktree>/src/api/vector.cmake     -> rc=0
cmake --build . --target kp_supporttest kp_vectortest kp_namespacetest kp_routinetest -j10  -> rc=0
```

**RED run: U1 stub `register_vector` installs nothing; U2 unchanged.**
- `kp_vectortest`: `14 check(s), 13 failure(s)` (rc=1). The only pass was `plain table in`, which shows the fake VM itself works.
- `kp_supporttest`: every function case FAILed with `bad argument #2 to 'registertimer' (expected string, got function)`.
- It then crashed with SIGSEGV (rc=139). gdb:
  ```
  #0 lua_pushlightuserdata  #1 kp::lua::Script::owner(lua_State*)
  #2 kp::api::timers::pump  #3 main
  ```
  This is the finaliser-registered string timer that outlived its closed state.

**Mutation check.** A second `luaL_unref` was temporarily added in `cancel_timer`, then reverted (`grep -c MUTATION` = 0). Result: `timers.function_ref_released_once: no registry slot freed twice FAIL` (rc=1).

**Closing-guard mutation.** The `s->closing` check was temporarily disabled, then reverted (`grep -c MUTATION` = 0). Result: `kp_supporttest` rc=139 (SIGSEGV). The guard is what prevents the crash.

**GREEN run.**
```
kp_vectortest   -> 14 check(s), 0 failure(s)   rc=0
kp_supporttest  -> 43 ok, 0 FAIL               rc=0
ctest -R "kp_supporttest|kp_vectortest|kp_namespacetest|kp_routinetest"
                -> 100% tests passed (kp_routinetest, kp_supporttest,
                   kp_namespacetest.k1, .k2; kp_vectortest separately 1/1)
i686-w64-mingw32-g++ -std=c++20 -Wall -Wextra -O2 -c vector.cpp / timers.cpp -> ok, ok
cmake --build . (all targets) -> rc=0
ctest -E "kpharness|gameplay_scheduler|example_validation|scene_test|macho_test"
                -> 24/25 passed. Includes kp_luatest.*, kp_eventtest,
                   kp_lifecycletest, kp_scriptsapitest, kp_consoletest,
                   kp_harnesstest, kp_entitytest, kp_structtest and others.
                   Only failure: kp_hooktool_x64.selftest
                   ("FAIL decoder: length/rel f6 15 01 02 03 04", 2/230).
                   That is the x64 instruction decoder, which shares no code
                   with Lua or timers (tools/kp_hooktool.cpp is another
                   writer's dirty file). Not caused by this change.
```
Grep for callers of the old arg-2 error text `expected string, got` in `tools/` and `scripts/examples/`: none. Every existing `kp.registertimer` caller passes a string name.
The only new warning is `-Wmissing-field-initializers` on `lua::Host host({dir, 3, false})` in the supporttest additions. It is the same pattern and warning the existing line (`:625`) already produces.

## Integration snippet (one serialized step, integrator only)

Once `register_support` calls `register_vector`, `kp_supporttest` and `kphasor` fail to link unless their source lists carry `vector.cpp`. `support_win32` only compiles, so without it the Windows half is not compile-checked. All three lists get it in the same step.

```diff
--- src/api/output.cpp
 #include "api/strings.hpp"
 #include "api/timers.hpp"
+#include "api/vector.hpp"
@@ void register_support(lua_State* L) {
     register_output(L);
     register_timers(L);
     register_strings(L);
+    register_vector(L);
 }

--- src/api/support.cmake   (KP_SUPPORT_SOURCES)
     "${KP_API_DIR}/strings.cpp"
+    "${KP_API_DIR}/vector.cpp"
 )

--- src/runtime/runtime.cmake   (after line 70)
     "${KP_SRC_ROOT}/api/timers.cpp"
+    "${KP_SRC_ROOT}/api/vector.cpp"

--- CMakeLists.txt   (beside line 125)
 include(${CMAKE_CURRENT_SOURCE_DIR}/src/api/support.cmake)
+include(${CMAKE_CURRENT_SOURCE_DIR}/src/api/vector.cmake)

--- tools/kp_namespacetest.cpp:101  (kp path list)
-                    'print', 'diagnostic', 'console', 'feedback', 'registertimer',
+                    'print', 'diagnostic', 'console', 'feedback', 'registertimer', 'vec',
```

`-DCMAKE_PROJECT_KotorPhasor_INCLUDE=.../vector.cmake` was scratch-only. Once the CMakeLists include lands, passing it as well would define `kp_vectortest` twice.

After integration, `kp_vectortest` still compiles `vector.cpp` itself. The copy in `kphasor` is interposed by the executable's copy, which is harmless. Removing `vector.cpp` from `vector.cmake`'s source list is optional. `hostapi.toml`/`api-status.md` still list `kp.vec` as declared-unbound, which is a docs item for the integrator.

## Open ruling (non-blocking)

`x`, `y` and `z` appear in `data/routines/*.json`, but only as the parameter names of routine `Vector` (id 142). They are not routine or global names. They cannot be renamed, because the brief requires plain-table marshalling to stay unchanged and `routines.cpp:199-203` reads exactly those keys. The controller should rule on whether parameter names fall under "must not duplicate NWScript names". This does not block U1.

## Residual proof boundary

- **Not live.** Nothing here ran in the game.
  - F12 reaches `kp.vec` only through `register_support`, via the shared `set_state_init` initializer (`runtime.cpp:700`, `:709`). That happens after integration and is unverified live.
  - Still owed: F12 `return kp.vec(3,4,0):length()` returning `number:5`, and a `GetPosition` round trip on real engine floats.
- **The fake VM proves the marshal path, not the engine thunk.** The `push_vector` ABI stays as `enginestruct.hpp` documents it.
- **GC probes are indirect.** "Released" is shown by weak-key collection plus the distinct-ref check, not by registry inspection. The state-close case is shown by `pending(L)==0` and a pump that does not touch the freed state. The pre-fix SIGSEGV is the red counterpart. No ASan run was done (32-bit ASan was not attempted).
- **F12 timers have no error budget.** Console-state timers have no owning Script, so a throwing F12 function timer is logged and cancelled, but no budget applies. This is the same as string timers before the change.
- **`forget_state` on a live state** still leaks refs until the state closes, as it did for string timers before. It is documented in `timers.hpp` and has no in-tree caller other than the finaliser.
- **Transient build risk.** `kphasor` and `kp_supporttest` compile other writers' in-flight files (`host.cpp`, `runtime.cpp`). They built cleanly at the time of this run.

## Follow-up round

This round fixes the independent review's I1, M1, M2, M4, M5 and M6. The review is at `/home/brunner56/kp-live-20260922/lua-utilities-u1u2-review.md`. M3 is in the bridge and was not touched.

Files touched, and no others:
- `src/api/timers.cpp`
- `src/api/timers.hpp`
- `src/api/vector.cpp`
- `src/api/vector.hpp`
- `tools/kp_supporttest.cpp`
- `tools/kp_vectortest.cpp`

The build ran in `/home/brunner56/kp-u1u2-build`. It was configured against this worktree and built with `make kp_supporttest kp_vectortest`, rc=0. The binaries ran 32-bit through `~/.local/bin/host-cmd`. There was no game, and the live-game lock was not touched.

Logs are in the build dir: `red-sup.log`, `red-vec.log`, `green-sup.log`, `green-vec.log`. Writing to a file from the container side of `host-cmd` sometimes gave an empty or cut-off file. The green logs were therefore written on the host side (`host-cmd sh -c '... > log'`), and each ends in an `exit rc=` line.

### Red: regressions written first, fixes not yet applied

`kp_supporttest`: rc=1, 45 ok, 3 FAIL.
```
PANIC: unprotected error in call to Lua API (strict: undefined global no_such_global)
    child: exited=1 status=1 signalled=0
  timers.string_lookup_protected: strict _G error isolated, reported   FAIL
  timers.delay_bounds: inf/nan/negative/huge rejected, 0 and 2^32-1 ok FAIL
  timers.delay_bounds: nothing left scheduled                          ok
    C callback label: function [C]:-1
    C callback label: function [C]:-1
  timers.c_function_labels: distinct labels per C function             FAIL
```
The strict-globals case runs in a `fork()`ed child. Exit 1 is LuaJIT's panic: the child printed `PANIC` and never reached its own report, which would exit 0 or 3. The parent survived and recorded the FAIL.

`kp_vectortest`: rc=1, `15 check(s), 1 failure(s)`.
```
    vec.scalar_results_finite: [string "..."]:4: expected an error mentioning 'not finite', got success
```
Line 4 is `big.length` with `big = kp.vec(1e155, 0, 0)`.

### Fixes

**I1: string timer lookup.** `fire_one` now looks up a name inside `lua_pcall` through a small C function (`lookup_global`), with the traceback handler.
- A raising `__index` becomes an ordinary timer error. It is logged, charged to the name's budget and the timer is cancelled.
- It is **not** counted as a firing, because the callback never ran.
- `lua_rawget` was not used, so lookup semantics are unchanged.
- `g_firing_id` is set during the lookup, so a `kp.removetimer(id)` issued from `__index` raises inside the protected call.
- After the lookup, the entry is found again by id, and `userdata_ref` is re-read from it. `__index` is arbitrary script code.
- The not-a-function branch, its message and the call path are unchanged.

**M2: delay bounds.** `kp.registertimer` now rejects a delay unless it is finite and between 0 and `timers::kMaxDelayMs`, which is 2^32 − 1 ms (about 49.7 days). The error reads `delay must be a finite number of milliseconds from 0 to 4294967295`.
- The cap keeps the `uint64_t` cast defined and `clock() + delay` far from overflow.
- A repo grep of `registertimer(` delays found 999000 as the largest literal (the tests' "never fires" value), so the cap breaks no existing caller.
- `removetimer` stays forgiving. It now also ignores ids at or above 2^64 and infinite ids, where the cast was undefined behaviour.

**M1/M6: vector finiteness.**
- `length`, `lengthsq`, `dot`, `distance` and `distancesq` go through `push_scalar`, which raises `<who>: result is not finite`.
- `normalize` raises `length is not finite` on overflow. A true zero vector still normalises to zero.
- **Beyond the brief:** `normalize` also raises `length underflows to zero` when a nonzero vector's length underflows (`1e-200`). The review listed this with M1. It is the other way to silently get zero back.

Found on the way: the first green run still passed `length()` of `1e155`. The 32-bit build uses the x87, and 1e310 fits in its 80-bit registers, so `sqrt(dot)` came back finite from a register. That made the result depend on the optimiser. `dot` and `push_scalar` now round through a `volatile` double, so the check sees exactly the value Lua receives.

The header now says that results, scalars included, are checked, and states the `normalize` overflow and underflow rule. The review's "finite numbers only" point (M6) now holds as written.

**M4: C-function labels.** A C function callback is labelled `function [C] <address>` (`lua_topointer`), so each C function gets its own budget. Lua functions keep `function <source>:<line>`.

**M5.** The comment in `l_registertimer` now says the two `luaL_ref` calls can still raise on out-of-memory. It also says that if the second raises, the first ref is held until the state closes.

### Regressions added

`kp_supporttest`, which adds scripts `72_fn_clabels.lua` and `90_fn_strict.lua` to `kFnScripts`:
- `timers.string_lookup_protected`: the reviewer's `strictg` probe, run in a forked child. The child asserts:
  - one new error, labelled `no_such_global`, with message `strict: undefined global no_such_global`
  - the script is still Loaded
  - `pending(L)==0`

  The parent checks that the child exited normally with status 0.
- `timers.delay_bounds` (×2): rejects `math.huge`, `-math.huge`, `0/0`, `-1`, `1e30` and `4294967296`. Accepts `0` and `4294967295`, then removes both. Also calls `removetimer(math.huge / 1e30 / nan)`, which must not raise. Afterwards nothing is scheduled.
- `timers.c_function_labels` (×2): uses `error` and `setmetatable` as callbacks. The two labels differ, both start with `function [C]`, and the script is still Loaded.

`kp_vectortest`, one new case:
- `vec.scalar_results_finite` uses `1e155`. It checks:
  - all six of length, lengthsq, dot, distance, distancesq and normalize raise `not finite`
  - `kp.vec(1e308,1e308,0):length()` raises
  - `1e-200` normalize raises `underflow`
- It also has a `1e150` control: lengthsq, length, normalize and distance still work, compared with a relative tolerance, since `1e150*1e150` is not exactly `1e300`.

### Green

`kp_supporttest`: `exit rc=0`, 48 ok, 0 FAIL.
```
  [log:error] timer 'no_such_global': strict: undefined global no_such_global
    [child] recorded [no_such_global] strict: undefined global no_such_global
    [child] survived the pump, mask=0
    child: exited=1 status=0 signalled=0
  timers.string_lookup_protected: strict _G error isolated, reported   ok
  timers.delay_bounds: inf/nan/negative/huge rejected, 0 and 2^32-1 ok ok
  timers.delay_bounds: nothing left scheduled                          ok
  timers.c_function_labels: registers two                              ok
    C callback label: function [C] 0xf78c70e0
    C callback label: function [C] 0xf78c6e40
  timers.c_function_labels: distinct labels per C function             ok
  ...
  all timers are gone after state teardown                             ok
exit rc=0
```
(`exited=1` is the `WIFEXITED` flag, and `status=0` is the exit code.)

Every check that already existed still passes, including `timers.string_callback_unchanged`. The count went from 43 to 48 because of the five new checks.

`kp_vectortest`: `15 check(s), 0 failure(s)`, `exit rc=0`.

Also rebuilt: `kp_namespacetest` gave `namespace contract: 0 failure(s)`, rc=0. The `support_win32` target compiled `win32/api_timers.obj` with the new `timers.cpp`.

### Second pass (after the advisor's check)

- **Vec-valued overflow was not tested.** `vec.scalar_results_finite` now also checks that these raise `not finite`, all from finite inputs:
  - `kp.vec(1e308,0,0) * 10`, `- kp.vec(-1e308,0,0)`, `+ kp.vec(1e308,0,0)` and `/ 1e-10`
  - `kp.vec(0,1e200,0):cross(kp.vec(0,0,1e200))`
  - a `lerp` with `t = 3`

  All passed with no change to `push_vec`, so this was a null move. The x87 concern did not show up for vec results in this build.
- **The I1 re-find and the `g_firing_id` guard now have a referent.** The new script `91_fn_strict_remove.lua` gives `_G` an `__index` that calls `kp.removetimer` on the timer whose name it is resolving. The new check is `timers.lookup_removes_self`, run in a forked child.
  - It expects one recorded error on `missing_fn` that contains `within its own callback`, with the script still Loaded and `pending==0`.
  - Log line: `timer 'missing_fn': .../91_fn_strict_remove.lua:9: attempt to remove timer 10 within its own callback; ...`
  - This covers behaviour that is new in this round. It has no red run.

Final counts:
- `kp_supporttest`: `exit rc=0`, **49 ok, 0 FAIL**
- `kp_vectortest`: `15 check(s), 0 failure(s)`, `exit rc=0` (the new vec checks are inside the existing `vec.scalar_results_finite` case)

### Residual

- Other writers are editing the same shared worktree, so the tree cannot show which edits are mine. The six files above are the only ones this round wrote.
- The reviewer's scratch probe (`kp_reviewprobe strictg` / `hugedelay`) was not re-run. The in-tree regressions reproduce both.
- `docs/lua-api.md` and `data/hostapi.toml` (`delay_ms`, "delay must be zero or more") do not state the new upper bound. That is docs drift for the integrator, outside this round's files.
- The C-function label holds a pointer, so it is stable within one process and state, but not across runs.

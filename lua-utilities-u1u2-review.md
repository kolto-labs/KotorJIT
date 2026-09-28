# U1 (kp.vec) + U2 (function-valued kp.registertimer): independent review

Reviewer: independent correctness and adversarial pass. The source was read-only.
Scratch area: `/home/brunner56/kp-live-20260922/review-probes-u1u2/`. It holds a copy of the worktree (`src/`), the build (`build/`), logs (`*.log`) and the probe (`probe_u1u2.cpp`).
No Wine, no game, and the live-game lock was not touched. The worktree was not written to.

Order of work: I formed my own view from the source first. Only then did I read `.superpowers/sdd/lua-boundary-validation-plan/lua-utilities-u1-u2-report.md`.

Scratch sources are byte-identical to the worktree. sha256 matches for vector.{hpp,cpp,cmake}, timers.{hpp,cpp}, kp_vectortest.cpp and kp_supporttest.cpp.

## Verdict summary

- **Critical:** none.
- **Important (pre-existing, not a U1/U2 regression):**
  - I1: string-timer panic under a raising `_G.__index`.
- **Minor:**
  - M1: numeric results are not checked for finiteness.
  - M2: `math.huge` delay fires immediately. Pre-existing.
  - M3: a finite double above FLT_MAX marshals as float inf. This is in the bridge, shared with plain tables.
  - M4: the error-budget label is coarse for C functions and console chunks.
  - M5: a stale comment.
  - M6: the header overstates "finite numbers only".
- **Scope:** the PASS covers the source, the tests, and the integration snippet applied and built in scratch. It is **not** live. Until the snippet lands, `kp.vec` cannot be reached from the runtime, because nothing in the worktree calls `register_vector` outside the tests.

## Commands and outputs

Configure: `cmake -S review-probes-u1u2/src -B review-probes-u1u2/build -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_COMPILER=~/.local/bin/c++` gave rc=0. The only warning is that the Windows `libluajit.a` was not copied, so kphasor.dll is not built. The DLL is out of scope.

Build: `cmake --build . --target kp_supporttest kp_vectortest kp_namespacetest kp_routinetest kp_reviewprobe support_win32 -j8` gave **rc=0**. `build.log` shows vector.cpp compiled into all of these:
- `kphasor.dir/src/api/vector.cpp.o`
- `kp_supporttest.dir/.../vector.cpp.o`
- `kp_vectortest.dir/...`
- `i686-w64-mingw32-g++ vector.cpp`, followed by `Built target support_win32`

There were no link errors. `kp_vectortest` both compiles vector.cpp and links kphasor, which now also carries vector.cpp, and it linked without a duplicate-symbol error.

Run, 32-bit, through `~/.local/bin/host-cmd`. Direct exec in the container gives rc=127 "required file not found", meaning there is no 32-bit loader.

| binary | rc | summary line |
|---|---|---|
| kp_vectortest | 0 | `14 check(s), 0 failure(s)` |
| kp_supporttest | 0 | 43 ` ok`, 0 `FAIL` (grep counts); last line `all timers are gone after state teardown ok` |
| kp_namespacetest | 0 | `namespace contract: 0 failure(s)` (with `'vec'` added to the path list) |
| kp_namespacetest k2 | 0 | `namespace contract: 0 failure(s)` |
| kp_routinetest | 0 | `kp_routinetest: 0 failure(s)` |
| kp_reviewprobe | 0 | `27 check(s), 0 failure(s)` |

The supporttest finaliser-order lines, verbatim:
```
[close] late fn=true name=true
[close] early fn=false name=false kp.registertimer: this script's state is closing
```

Wiring mutation: I commented out `register_vector(L)` in scratch `output.cpp`, rebuilt kp_namespacetest and ran it. The result is in the appendix below.

## Integration snippet

claim: "Once `register_support` calls `register_vector`, `kp_supporttest` and `kphasor` fail to link unless their source lists carry `vector.cpp`… All three lists get it in the same step" (implementer report, Integration snippet)
referent: snippet applied verbatim in scratch (`git diff --stat`: CMakeLists.txt +1, output.cpp +2, support.cmake +1, runtime.cmake +1, kp_namespacetest.cpp 1 line changed); build rc=0; five test runs rc=0 (table above)
checked: `review-probes-u1u2/build.log`, `run-*.log`
verdict: holds (the snippet links and the tests pass)
confidence: high. Other writers' in-flight `host.cpp`/`runtime.cpp` can still break the build at integration time. That is transient, and not a property of U1/U2.

Note: the only test that exercises `register_support → register_vector` is kp_namespacetest with `'vec'` in its list. kp_vectortest and kp_supporttest call `register_vector` directly or not at all. That one-word namespacetest edit is therefore load-bearing, and the integrator must not drop it.

## U2: function-valued kp.registertimer

claim: function ref released exactly once on complete, cancel and error; `forget_state` does not unref on close
referent: `timers.cpp` `cancel_timer`, the only `luaL_unref` sites, which erase in the same step. `forget_state` erases without unref. Probe P8 registered 60 timers across complete, error and cancel, then took 128 fresh `luaL_ref` slots, and all 128 were distinct. The implementer's double-unref mutation went red (their report).
checked: source read; `run-kp_reviewprobe.log` "P8 … distinct … ok"
verdict: holds
confidence: high

claim: no use after state close, and the closing guard holds for both finaliser orders
referent: LuaJIT `lua_close` (`third_party/luajit/src/lj_state.c:331-360`) runs `lj_gc_separateudata(g,1)` and then loops `cpfinalize`. An erroring `__gc` does not end the loop (`i` only increments on `LUA_OK`). There are up to 10 re-separation rounds, and `close_state` runs after them. `lj_gc_separateudata` (`lj_gc.c:142-169`) walks the udata list newest-first and appends in that order. A script's own proxies are newer than the sentinel, so they are finalised BEFORE it. That is the "late" order, and `forget_state` then drops what they registered. Userdata created during round 1 is finalised in round 2, after the sentinel, and the `closing` flag refuses it.
Probe P10 prints `[p10] round1 fn register ok=true` and `[p10] round2 fn register ok=false kp.registertimer: this script's state is closing`, then `pending before close=1 after=0`, and a pump after close fires 0.
checked: vendored LuaJIT source; `run-kp_reviewprobe.log`
verdict: holds
confidence: high

claim: timer callback errors are isolated and reported
referent: `fire_one` uses `lua_pcall(L,3,1,base+1)` with a traceback handler, then `report_error` and `cancel_timer`. `Script::record_error` only marks quarantine and never closes the state (`host.cpp:242-260`), so the `lua_settop(L, base)` that follows is safe.
- P2: unprotected self-remove is logged and cancelled, and the ref is released.
- P6: yield across the C boundary is isolated, and the next timer still ran.
- P7: a C-function callback (`error`) and a table-valued error are both isolated. Each logs `'function [C]:-1'` or `(non-string error)`.
- supporttest: `timers.function_error_isolated` ×4 and `timers.function_error_budget` ×2 pass.
checked: source; `run-kp_reviewprobe.log`; `run-kp_supporttest.log`
verdict: holds
confidence: high

claim: cancellation inside the callback, re-registration inside the callback, and a pump that iterates while the timer set is mutated are all safe
referent: `pump` takes a snapshot of `(due, id)` and `fire_one` looks each id up again before it runs it. Ids are monotonic and never reused.
- P1: `pcall(kp.removetimer, own_id)` raises "…within its own callback", and the timer keeps renewing when the callback returns true. An external remove then releases the ref.
- P3: a timer re-registered with delay 0 is not fired in the same pump (`f1==1`). A chain of three runs and then stops.
- P4: timer A cancels timer B, both due in the same pump. B is skipped and B's ref is released.
checked: `run-kp_reviewprobe.log`
verdict: holds
confidence: high

claim: timers registered from coroutines belong to the script
referent: `owner_state` resolves through the registry sentinel.
- P5: a closure is registered inside a coroutine and captures a coroutine local. The coroutine is dropped and `collectgarbage` runs twice. The timer then fires on the main state with the upvalue intact (`p5_seen == 42`).
checked: `run-kp_reviewprobe.log`
verdict: holds
confidence: high

claim: the string path is unchanged
referent: `git diff` of timers.cpp. The string branch still uses `lua_getglobal(L, callback.c_str())`. The only change on that path is the argument-2 type message (`expected string` became `expected string or function`). `timers.string_callback_unchanged` ×3 passes.
checked: diff; `run-kp_supporttest.log`
verdict: holds
confidence: high

## U1: kp.vec

claim: the metatable is protected
referent:
- `__metatable = "kp.vec"`, so `setmetatable(v, {})` raises.
- The host strips `debug.getmetatable`, `debug.setmetatable` and `debug.getregistry` (`host.cpp:133-138`).
- The method table is reachable only through `__index`, and the methods are C functions with no upvalues.
- V1 checks this under the same stripping: `rawget(v,'length') == nil` and `debug.getupvalue(v.length,1) == nil`.
checked: `run-kp_reviewprobe.log` V1 ok; `vec.metatable_protected`
verdict: holds
confidence: high

claim: NaN and inf are rejected at construction, and every operation revalidates
referent:
- `read_axis`/`read_scalar` check `lua_type == LUA_TNUMBER` (no string coercion) and `std::isfinite`.
- `push_vec` checks the result.
- V2 writes junk into fields (`0/0`, the string `'1'`, `math.huge`, nil) and every op raises.
- `==` with a NaN field returns false and does not raise.
- `tostring` prints `vec(1, -nan, 3)`.
checked: `run-kp_reviewprobe.log` V2
verdict: holds for vec-valued results. For scalar results, see M1.
confidence: high

claim: marshalling round trip into nwscript.call vector params is unchanged
referent:
- `routines.cpp:194-210` reads `lua_getfield` x/y/z from any table. A vec carries raw x/y/z fields, so it marshals exactly like a plain table.
- The return path (`:329-345`) still builds a plain table.
- `vec.plain_table_still_marshals` (kp.vec in, plain in, round trip) goes through the real `kp::api::call` with the fake VM.
checked: source; `run-kp_vectortest.log`
verdict: holds
confidence: high for the bridge. The engine thunk is not proven here, which needs a live run.

claim: LuaJIT vs PUC semantics
referent:
- `__eq` is consulted only when both operands are tables with the same metamethod. That rule is the same in LuaJIT 2.1 and 5.1, so `vec == plain` is false in both (`vec.equality`).
- `luaL_register(L, nullptr, …)` and `lua_getinfo(">S")` are 5.1 API calls that LuaJIT provides.
- lua_Number is a double on 32-bit LuaJIT.
- Close-time finaliser rounds: LuaJIT re-separates up to 10 rounds (`lj_state.c:347-358`). The difference from PUC 5.1, which runs one `luaC_separateudata` at close, only affects userdata created during finalisation. Neither behaviour lets a timer outlive its state, because the sentinel is in the first batch either way. I did not re-read PUC 5.1's handling of an erroring `__gc` at close, so I am not claiming anything about it. The game uses LuaJIT.
checked: vendored LuaJIT source; tests are linked against the 32-bit LuaJIT build (`build/luajit32/src/libluajit.a`)
verdict: holds
confidence: medium-high. PUC was not built or run.

claim: naming rule (no NWScript function or variable names)
referent:
- The routine catalogue walk found no hits among `vec` and the 10 method names. `data/routines/k1.json` has 1211 name identifiers and `k2.json` has 1341.
- I parsed both `nwscript.nss` files (from the `signature_source` path in the JSON), which covers every constant and every function:
  - k1: 1490 constants and 772 functions, no hits
  - k2: 1810 constants and 877 functions, no hits
  - positive control: `VectorMagnitude` was found
- Across all non-comment identifiers: no hits. With comments included, `length`, `normalize`, `distance` and `copy` appear, but only in comment prose.
- `x`, `y` and `z` are the parameter names of routine `Vector`, which the orchestrator ruled out of scope.
checked: python scan (commands in the reviewer session); `vec.names_not_routines` ok
verdict: holds
confidence: high

## Findings

**I1. Important, pre-existing, not a regression. A string timer panics the process when `_G` has a raising `__index`.**
`fire_one` calls `lua_getglobal(L, callback)` outside any pcall (HEAD `timers.cpp:156`, now in the string branch). A strict-globals script (the common strict.lua pattern) plus a string timer naming an undefined global gives:
```
kp_reviewprobe strictg -> rc=1
PANIC: unprotected error in call to Lua API (strict: undefined global no_such_global)
```
No `lua_atpanic` is installed anywhere in `src/` (grep shows none), so in the game this is LuaJIT's default panic, which exits the process.

The function path uses `lua_rawgeti` and is immune: `kp_reviewprobe strictg_fn` gives `ran=1 pending=0`, rc=0.

Fix: do the lookup inside the protected call. Either push a small C trampoline that does the `getglobal` and then calls, or use `lua_rawget` on the globals table, which would change lookup semantics. Out of U2 scope, so it does not flip the verdict.

**M1. Minor. Scalar results and `normalize` are not finiteness-checked.**
- `kp.vec(1e155,0,0)` returns `length=inf lengthsq=inf dot=inf distance0=inf`, and `normalize=vec(0, 0, 0)`.
- `kp.vec(1e308,1e308,0):length()` returns `inf`.
- The squared length can also underflow: `kp.vec(1e-200,0,0):normalize()` returns `vec(0, 0, 0)`, a zero vector from a nonzero input.

Both happen only far outside game coordinate scale. Fix: route scalar results through the same finite check, or compute with `std::hypot`.

**M2. Minor, pre-existing. An infinite or huge delay fires immediately.**
`!(delay >= 0)` rejects NaN but accepts `math.huge`. `std::uint64_t(inf)` is UB, and in practice the timer fired within 200 ms (`[E1] registertimer(math.huge) accepted=1 … fired within 200ms=1`). `removetimer(1e30 / inf / nan)` returns without raising, which is harmless. Present at HEAD `timers.cpp:238`. Fix: reject `!std::isfinite(delay)` or clamp.

**M3. Minor, in the bridge, not U1.**
`kp.vec(1e39,0,0)` is accepted (V7), and `routines.cpp:201-203` then casts it to `float`, giving +inf. A plain table does the same, so this is not a U1 issue.

**M4. Minor. The error-budget label can be coarse.**
- Every C-function callback shares the label `function [C]:-1` (P7 log).
- Console or F12 chunks with the same chunk name and line share a budget.

This follows from the documented "one budget per definition site" rule. F12 timers have no owning Script, so no budget applies anyway (implementer's report, residual section).

**M5. Minor. Stale comment.**
`l_registertimer` says "Everything that can raise has raised by now", but two `luaL_ref` calls follow and can raise on OOM. If the second raises, the first ref leaks until the state closes. Negligible.

**M6. Minor, docs.**
The `vector.hpp` header promises "finite numbers only". M1 is the exception, so either fix M1 or narrow the wording.

Also noted, not a finding: `v.length = 7` shadows the method on that instance (V4). This is ordinary table semantics under the documented "fields stay writable" rule.

## Claims I could not check

claim: "Forbidden files were not edited: `host.*`, `runtime.*`, `CMakeLists.txt`, `support.cmake`…"
referent: none that separates writers. `git status` shows `src/lua/host.cpp`, `src/lua/host.hpp`, `src/runtime/runtime.cpp` and `CMakeLists.txt` modified in the shared worktree. The plan assigns those to other writers (L1/L2 and the integrator).
checked: `git status --short`
verdict: unresolved (not attributable from the tree)
confidence: low. A per-writer diff or a timestamp log would settle it.

## Appendix: wiring mutation

claim: the snippet wires `kp.vec` in through `register_support`. It does more than link.
referent: I replaced `register_vector(L);` in scratch `output.cpp` with a `// REVIEW-MUTATION` comment and rebuilt kp_namespacetest (rc=0). The run gave rc=1:
```
FAIL: [string "..."]:35: missing kp.vec
namespace contract: 2 failure(s)
```
After restoring the call (`grep -c REVIEW-MUTATION` = 0) and rebuilding, the run gave rc=0 with `namespace contract: 0 failure(s)`.
checked: `run-mut-namespacetest.log`, `run-unmut-namespacetest.log`
verdict: holds
confidence: high

U1+U2 verdict: PASS

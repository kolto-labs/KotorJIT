# U1 + U2 Lua utilities: follow-up independent review

Reviewer scope: read-only worktree review of `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`. This report is the only file written by this review. No Wine, game, Gamescope, X server/capture tool, live-game lock, git reset/stash/stage/commit/push, or canonical checkout was touched.

I first read the current implementation and re-derived the follow-up behaviour, then read the writer's `Follow-up round` report. The inherited prior review was `/home/brunner56/kp-live-20260922/lua-utilities-u1u2-review.md`; no partial file at this report path existed.

## Inherited state and evidence

- `git diff --stat -- src/api/timers.cpp src/api/timers.hpp src/api/vector.cpp src/api/vector.hpp tools/kp_supporttest.cpp tools/kp_vectortest.cpp` showed the tracked timer/test change (600 insertions, 22 deletions); `vector.*` and `kp_vectortest.cpp` remain untracked in this intentionally shared-dirty tree. I preserved all unrelated changes.
- The writer's already-built 32-bit binaries are newer than the corresponding reviewed files: `kp_vectortest` 12:43:45 and `kp_supporttest` 12:43:59, versus the newest reviewed input `tools/kp_supporttest.cpp` at 12:43:18 (`stat -c '%y %n' ...`).
- An independent scratch configure exists at `/home/brunner56/kp-live-20260922/review-probes-u1u2-followup/build-default`, configured RelWithDebInfo. Its `compile_commands.json` proves the applicable build uses `-O2 -g -DNDEBUG -m32 -Wall -Wextra`, not `-ffast-math`. I started an isolated `cmake --build ... --target kp_supporttest kp_vectortest -j2`; it remained in its LuaJIT source-copy step under the explicitly reported heavy-I/O conditions, so it is not claimed as completed evidence.

## Re-run results

Command (the required host-only 32-bit route):

```
/home/brunner56/.local/bin/host-cmd sh -c '/home/brunner56/kp-u1u2-build/kp_supporttest /home/brunner56/kp-live-20260922/review-probes-u1u2-followup/run-support-scratch; rc=$?; echo support_rc=$rc; exit $rc'
/home/brunner56/.local/bin/host-cmd sh -c '/home/brunner56/kp-u1u2-build/kp_vectortest; rc=$?; echo vector_rc=$rc; exit $rc'
/home/brunner56/.local/bin/host-cmd sh -c '/home/brunner56/kp-u1u2-build/kp_namespacetest; rc=$?; echo namespace_rc=$rc; exit $rc'
```

Observed output:

- `kp_supporttest`: **49 `ok`, 0 `FAIL`, `support_rc=0`**. It includes `timers.lookup_removes_self ... ok`; `timers.string_lookup_protected ... ok`; both delay-bound checks; two distinct C labels; ref-release, both finalizer orders, and state-close/pump checks all `ok`.
- `kp_vectortest`: **`15 check(s), 0 failure(s)`, `vector_rc=0`**.
- `kp_namespacetest`: **`namespace contract: 0 failure(s)`**. Its final shell status line was not emitted before output collection ended, but the test's own failure count is zero.

The support run's relevant strict lookup receipts were:

```
[log:error] timer 'missing_fn': ...attempt to remove timer 10 within its own callback...
timers.lookup_removes_self: raises in lookup, reported, cancelled    ok
[log:error] timer 'no_such_global': strict: undefined global no_such_global
[child] recorded [no_such_global] strict: undefined global no_such_global
timers.string_lookup_protected: strict _G error isolated, reported   ok
timers.delay_bounds: inf/nan/negative/huge rejected, 0 and 2^32-1 ok ok
timers.c_function_labels: distinct labels per C function             ok
```

## Claim checks

claim: strict-globals lookup is now inside the protected call; a lookup exception is reported and cancels the timer rather than panicking the process
referent: `src/api/timers.cpp:127-134` defines `lookup_global`; `:195-208` invokes it with `lua_pcall`, resets firing state, reports, restores the stack and calls `cancel_timer`. The re-run logged the strict error and passed `timers.string_lookup_protected` with a normally exiting child.
checked: source lines above; host-cmd supporttest run
verdict: holds
confidence: high; a fresh binary from the isolated scratch build would be redundant confirmation only.

claim: an `_G.__index` lookup that tries to remove its own timer remains protected and cannot leave stale map state
referent: `src/api/timers.cpp:197-201` sets/reset `g_firing_id` around lookup, `:211-215` re-finds the timer after arbitrary lookup code, and `:361-363` makes self-removal raise. The re-run printed the expected error and `timers.lookup_removes_self ... ok`.
checked: source; host-cmd supporttest run
verdict: holds
confidence: high.

claim: timer delays accept only finite 0..4294967295 millisecond values and do not break existing callers
referent: `src/api/timers.cpp:271-278` applies `std::isfinite`, lower and upper bounds before `uint64_t` conversion; `src/api/timers.hpp:110-111` defines `kMaxDelayMs = 0xFFFFFFFFull`. The test passes zero and the maximum, rejects infinities/NaN/negative/over-cap, then proves nothing remains scheduled. The worktree search `rg -n 'registertimer\\s*\\(' .` found existing calls; the writer's cited maximum literal is the pre-existing `999000`, well under the cap.
checked: source; host-cmd supporttest run; caller search
verdict: holds
confidence: high.

claim: finite vec inputs cannot expose non-finite scalar results on the 32-bit x87 route, and normalize does not silently make a nonzero underflow vector zero
referent: `src/api/vector.cpp:94-101` stores/reloads scalar values through a volatile `lua_Number`; `:105-108` makes dot itself round through volatile storage; `:219-232` rejects nonfinite length and a nonzero vector whose length underflows to zero. The configured 32-bit command is `-O2 ... -m32` with no fast-math flag, and the re-run's `vec.scalar_results_finite` passed within 15/0.
checked: source; `build-default/compile_commands.json`; CMake cache; host-cmd vectortest run
verdict: holds
confidence: high for the repository's stated `-O2 -m32` route. A build with fast-math would void the normal `isfinite` contract, but this repository does not enable it.

claim: the prior U2 safety properties did not regress
referent: re-run `kp_supporttest` passed function reference release on completion/cancel/error and exactly-once ref slots; both finalizer orders (`late fn=true name=true`, `early fn=false name=false ... state is closing`); and mutation-safe pump/callback cases. `cancel_timer` remains the sole live unref path at `timers.cpp:141-149`; `forget_state` only erases during close at `:406-412`; snapshot/re-find pump is at `:388-403`.
checked: source; host-cmd supporttest run
verdict: holds
confidence: high.

claim: distinct C callbacks have independent error-budget labels
referent: `src/api/timers.cpp:293-296` labels a C closure as `function [C] %p` using `lua_topointer`; re-run registers `error` and `setmetatable`, logs two different addresses, and passes `timers.c_function_labels`.
checked: source; host-cmd supporttest run
verdict: holds for simultaneously live C closures
confidence: high.

## Finding

**M1 — Minor residual: address-based C-function labels are not durable identities across C-closure lifetimes.** `lua_topointer` at `src/api/timers.cpp:295` labels the closure object's address, while `Script::record_error` keys its accumulated budget by the resulting string. If a host extension creates a C closure, it fails enough times to leave a budget record, is released and collected, and a later distinct C closure is allocated at the same address in the same Script state, the later callback inherits that record/budget. The current Lua surface does not let a script allocate C closures: it can only pass already-reachable host/builtin functions, and a timer holds its passed callback in `callback_ref` until cancellation. Therefore I did not establish a current script-reachable reproducer, and this does not invalidate the round.

Suggested future-proof key: use the actual `lua_CFunction` pointer returned by `lua_tocfunction` (and, if desired, include closure identity/upvalue policy explicitly), rather than the GC-managed C-closure object address. This should be decided with the intended semantics for two closures around the same native function; it is not a required follow-up edit for the reviewed Lua-only API.

No Critical or Important finding was established. The bridge's float narrowing and live-game proof remain outside this follow-up and are not represented as passing here.

## Grill review

The writer did not include a `Grill me` section, so I attacked the most uncertain reported points directly:

- Why does protected lookup preserve strict-globals semantics? It still calls `lua_getglobal`, not `lua_rawget` (`timers.cpp:131-133`); the re-run records the strict `__index` message verbatim.
- Could lookup script mutation invalidate the fire path? `lookup_removes_self` exercises it and `fire_one` re-finds the id (`:211-215`); the test passes.
- Could x87 keep an overflowed intermediate finite? The 32-bit `-O2` compilation route is evidenced in `compile_commands.json`; the volatile store/reload is present in both dot and scalar push; the large-value test passes.
- Is C address identity permanent? No: it is sound for concurrently live callbacks, but M1 records the future host-extension reuse limitation.

## Verdict

**U1+U2 follow-up verdict: PASS.**

Counts: 0 Critical, 0 Important, 1 Minor residual; `kp_supporttest` 49/0; `kp_vectortest` 15/0; namespace test 0 failures. Incomplete only: the newly launched independent scratch rebuild was still copying LuaJIT under high I/O and is not counted as a completed check; no live-game or engine-thunk proof was attempted.

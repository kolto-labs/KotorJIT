# Motion M2 round 2 review

Date: 2026-09-28. Independent host-only review of the fixed
`src/api/engine_gate.{hpp,cpp}` and M2 signed-zero regression tests in
`/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`.
No product files, ledger files, game/Wine processes, or live-game lock were
changed. The only written artifact is this report.

## Independent claims

claim: `bind_gate` now serializes concurrent writers while preserving a lock-free reader path.

referent: `src/api/engine_gate.cpp:23-35` has `g_bind_mutex`, a
`std::lock_guard` around the odd-marker, probe/context stores, and final
even-marker. `on_engine_thread()` at `:38-49` only performs atomic loads and
the probe call; it never takes that mutex. The matching header contract is at
`src/api/engine_gate.hpp:15-25`.

checked: The current-source rebuild log is
`/home/brunner56/kp-live-20260922/review-probes-motion-m2-r2/build/current-enginegate-host-build.log`.
The command was `g++ -std=c++20 -m32 -Wall -Wextra -pthread -Isrc
tools/kp_enginegatetest.cpp src/api/engine_gate.cpp -pthread -o
build/current-enginegate-host`; it returned `compile_rc=0`, and the rebuilt
binary reported `6/6 tests passed, 19 checks`, including
`engine_gate.concurrent_two_writers_never_tear`. The preserved pre-fix binary
`kp_enginegatetest_myred` reported
`FAIL ... concurrent_two_writers_never_tear: ... torn=14985 of iters=3000000`
and `5/6 tests passed, 18 checks`.

verdict: holds

confidence: high; SHA-256 of the rebuilt binary is
`7ba4b2840d5d9275304934064b1bed1691da7f98e335a792ec788671db07f002`, and the
log records the source hashes used.

claim: the signed-zero distinctions required by M2 are now exercised by tests.

referent: `/home/brunner56/kp-live-20260922/review-probes-motion-m2-r2/build/kp_motiontest_myfixed`
reported passing `stale_capture_pose_refused_on_signed_zero`,
`readback_mismatch_on_signed_zero`, `restore_conflict_on_signed_zero`, and
`relocate_conflict_on_signed_zero`. The same run reported `58/58 tests passed,
4158 checks`.

checked: Rebuilt from the current worktree with the direct command recorded in
`build/current-motion-host-build.log`, using the existing LuaJIT static archive
as a link input. The command returned `compile_rc=0`; the rebuilt binary
reported each named PASS and `58/58 tests passed, 4158 checks`. SHA-256 of the
rebuilt binary is
`bd475caad742dabb3c57d55897b097d331bf04692c7626aea28b2677e9c49c51`. The
source still uses `bit_equal` for stale/readback/conflict fences and
`engine_equal` only for the intended no-op path in `src/api/motion.cpp`.

verdict: holds

confidence: high for the host contract and regression coverage; live engine
ABI/game behavior remains outside this host-only review.

claim: the mutex does not introduce a new dynamic `libwinpthread` dependency
under the production MinGW link flags.

referent: writer's direct link receipt
`/home/brunner56/kp-live-20260922/tmp-m2r2/mingw_link_test.exe` was built with
`-static -static-libgcc -static-libstdc++ -Wl,--exclude-all-symbols`; its
`i686-w64-mingw32-objdump -p` import list contains only `KERNEL32.dll` and
`msvcrt.dll`.

checked: the receipt is present and the source's mutex is the same fixed gate
implementation under review. No DLL/game launch was performed here.

verdict: holds

confidence: medium-high; a full runtime DLL link remains an integration check,
but the direct link uses the stated production flags and checks the relevant
import boundary.

claim: the current DllMain path does not block on `bind_gate` or execute the
runtime startup under the loader lock.

referent: `src/runtime/dllmain.cpp:3-14` documents the loader-lock boundary;
`:58-84` shows `DllMain` only disables thread callbacks, calls `CreateThread`,
closes the handle, and returns. `run_startup()` at `:36-43` calls
`Runtime::start` only from the worker (`:51-54`).

checked: `rg -n "bind_gate\\(" src tools` finds only the gate tests and API
implementation in this worktree; there is no DllMain call. `src/runtime/runtime.cpp:783-851`
contains start, and `:854-890` contains stop. The planned integration snippets
in `motion-m2-report.md` place `bind_gate` in Runtime lifecycle code, not in
`DllMain`.

verdict: holds for the current entry-point design; integration-gated

confidence: high for the loader-lock claim in the checked source. It would
change to FAIL if integration places `bind_gate` (or any operation that may
wait for it) directly in `DllMain`, or if stop is invoked from a loader-lock
callback.

claim: the fixed mutex is acceptable for the intended Runtime lifecycle calls,
but the integration must preserve the loader-lock and quiescence boundary.

referent: `Runtime::stop()` explicitly says at `src/runtime/runtime.cpp:872-875`
that it belongs at a quiescent point and is unsafe while a patched prologue is
executing. `DllMain` `DLL_PROCESS_DETACH` at `src/runtime/dllmain.cpp:74-79`
is deliberately empty. Therefore a blocking `bind_gate(nullptr, nullptr)` is
appropriate only from the existing worker/quiescent stop path, never from
DllMain detach. The mutex serializes binders; it does not make stop safe against
concurrent engine teardown.

checked: source read plus the fixed two-writer test. No runtime integration
edit was made in this review, and the current tree has no production
`bind_gate` call site to validate end-to-end.

verdict: holds conditionally; integration gate required

confidence: high. The missing proof is a post-integration source check that
there are exactly the intended start/stop binds, both outside DllMain, and that
the failed-start cleanup also unbinds or otherwise leaves the gate fail-closed.

## Grill-me

1. Is the two-writer fix actually tested rather than inferred from a mutex?
   That holds: fixed is 6/6 with the two-writer case; the pre-fix mutant is
   5/6 with 14,985 torn observations.
2. Are signed-zero tests merely named, or do they run? That holds: the fixed
   motion receipt is 58/58 and prints all four signed-zero cases as PASS.
3. Could DllMain still wait indirectly? The checked DllMain body has no gate
   call and returns after CreateThread/CloseHandle. The remaining check is
   integration placement of future Runtime binds.
4. Does the mutex prove Runtime::stop is safe during teardown? No. The source
   explicitly requires a quiescent stop point; the mutex only fixes concurrent
   binder serialization.

## Final verdict

Motion M2 round 2: **PASS with a precise integration gate**. The concurrent
writer defect is fixed and killed by the preserved race test; signed-zero
regressions are covered and all 58 motion tests pass. Before integration is
accepted, inspect the resulting runtime diff to confirm `bind_gate` is called
only from worker/quiescent Runtime lifecycle code, never from `DllMain` or
loader-lock detach, and that failed-start/stop paths leave the gate fail-closed.
No live game, Wine, or engine ABI proof is claimed.

Unsettled question: after the integration writer lands the Runtime binds, do
all bind/unbind call sites remain outside loader-lock callbacks and does the
failed-start path unbind explicitly? Single settling check: `rg -n
'bind_gate\\(' src/runtime src/proxy src/api` plus a focused source review of
the failure branches in `Runtime::start` and `Runtime::stop`.

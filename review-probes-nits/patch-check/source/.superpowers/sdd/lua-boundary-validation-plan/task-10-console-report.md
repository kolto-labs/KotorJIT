# Task 10: F12 console implementation

## Integration

Extracted the old blind `lua exec` interpreter into `src/devtools/console.*`, a bounded portable service. Product submissions are drained at the existing engine-loop boundaries. Native API registration reuses `init_lua_state`. Legacy console execution queues into this state; harness devtools requests forward to it without the overlay depending on harness TCP.

Added pinned Dear ImGui v1.91.9b (`f5befd2d29e66809cd1110a152e375a7f1981f06`) core and Win32/OpenGL2 backends with MIT license. Windows integration uses EXE IAT SwapBuffers/SetCursorPos and window subclassing. Shared DirectInput device vtable hooks suppress state and buffered input. Probes cover existing device implementations, but actual game call counters and live movement/camera isolation are required evidence. GL2 backend fixed-function preservation is supplemented with shader-program and VBO binding preservation.

## Implemented behavior

F12/Escape visibility, typed multiline editing, Enter execution/Ctrl+Enter newline, Ctrl+Up/Down bounded history, Tab raw-table completion, labelled stdout/stderr/errors and typed returns, scrollback/copy, persistent globals, command IDs/status, bounded queues/output, and LuaJIT-disabled instruction budgeting. See docs/devtools-console.md for exact contracts and limitations.

## Validation

Native32 and MinGW shipping targets built during implementation. `kp_consoletest` executes actual native32 LuaJIT and checks expression/statement returns, persistence, print/io standard handles, traceback/parse recovery, accidental infinite-loop termination, raw completion without getters, overwritten global recovery, queue rejection, and output bounds. Final command receipts and controller live acceptance will be added separately; no live game was launched by the implementation agent.

## Remaining proof / risks

Controller owns real keyboard/video acceptance, runtime native scale/readback/restore demonstration and independent review. No runtime proof claimed here. DirectInput shared-vtable discovery must be observed on the actual target. Context recreation, alternate game windows and additional render backends remain platform hardening work. Budget protection is cooperative for Lua instructions and does not preempt native calls or intentionally bypassed hooks. Output capture is scoped and does not redirect process C streams or arbitrary background callbacks. Full editor panels, entity tree, property editing/gizmos, debugger stepping and other platforms remain the separate roadmap.

## Frozen implementation candidate

`/home/brunner56/kp-validation-20260922-build/kphasor-console-smoke3.dll`

SHA256: `62c223ba14e8a823470fe7a617e420342dd713eb8c9192d67a4901aaf5718a62`.

Native32 `kphasor`, MinGW `kphasor_dll` and actual LuaJIT `kp_consoletest` passed after the last behavioral change. Test assertions are request-scoped and success commands explicitly reject error rows. Added preservation checks for real standard-file handles and `io.output` redirection to an ordinary file. Build receipt: `/tmp/kp-console-smoke3-build.log`.

The controller's first live test of smoke1 found a movement baseline contaminated by residual movement from a preceding closed-console input check. A settled repeat passed its 35 live checks, including actual F12 typing, native queries and model scale/readback/restore. Those are controller-reported observations, not an implementation-agent launch. Smoke2 exposed a real fast-Ctrl+A regression: deferring Win32 event handling sampled modifier state after Ctrl was released. Smoke3 dispatches immediately when WndProc and renderer have the same owner thread, queues only cross-thread events with modifier snapshots, and clears held ImGui input at the toggle boundary. Controller owns final smoke3 acceptance and independent review.

## Independent-review fix round 1

Review `/tmp/kp-task10-review.md` passed the scoped MVP specification and requested two bounded usability changes. Both are implemented:

- P2: after first window attachment, a closed console skips the entire presentation adapter body and calls original SwapBuffers exactly once. No ImGui frame, OpenGL extension lookup, texture iteration, GL query or state preservation work runs in steady closed frames. A cross-thread reset transition may enter once to clear owner-thread input state, then follows the same fast path. Toggle boundaries clear stale queued events so close/reopen does not replay them.
- P3: extracted `History` into `src/devtools/history.hpp`. It captures the current draft on first older navigation and restores it after returning beyond the newest entry. Rejected submissions preserve the original draft and navigation; successful submissions reset the draft deliberately. The existing actual-LuaJIT test now also checks empty history, multiline draft/older/newer/draft round trips, rejection by an actually full console queue and successful-submission reset.

No restart lifecycle, platform support or additional editor surface was added. Controller-reported held-key live acceptance is 24/24 passing for run 122456 before this fix round. Fresh physical-input acceptance and matched-scene closed-console timing comparisons remain controller-owned; removing source-level work is not itself a measured FPS improvement.

Fix-round build: native32 `kphasor`, MinGW `kphasor_dll` and focused `kp_consoletest` all passed; CTest elapsed 0.02 seconds. Build receipt `/tmp/kp-console-fixround1-build.log`. Frozen DLL `/home/brunner56/kp-validation-20260922-build/kphasor-console-fixround1.dll`, SHA256 `db3f0734ef9d18207f39432bf93d984f514e60dee71e7ba170a333fb60af044d`.

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

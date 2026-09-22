# In-game Lua console

The initial renderer targets the Windows K1 OpenGL game, including Wine. Press **F12** to show the console over the game. **Escape** or F12 closes it. Type Lua and press **Enter** to queue execution on the engine loop. **Ctrl+Enter** inserts a newline. **Ctrl+Up/Down** recalls history. The unfinished edit buffer, including multiline text, is saved when entering history and restored when moving past the newest entry. Rejected submissions retain that draft; a successful submission clears it. **Tab** completes a single match or prints bounded candidates. Scroll through output and use **Copy output** to copy the retained transcript.

Expressions need no `return`: `1+1`, `false`, or `nil, 42` display typed results. Statements also work, and globals persist across submissions:

```lua
counter = (counter or 0) + 1
```

The native API uses `kp.*`; engine script routines remain explicit, for example `nwscript.call("GetFirstPC")`. No NWScript globals or aliases are installed. `dofile("path/to/script.lua")` uses this same persistent interpreter. Loaded host scripts remain separate states; loading a script here does not automatically register its host event lifecycle.

During a console command, standard `print`, `io.write`, `io.stdout:write`, and `io.stderr:write` route to labelled output rows. File writes continue using Lua's original file implementation. The `kp.print` compatibility helper retains its existing diagnostic-log route. Previous print/write functions are restored afterward; these are scoped output-routing changes, not process-wide stdout/stderr redirection. Native C writes, subprocess output, and asynchronous callbacks outside console execution are not captured by this mechanism. `kp.console` uses the runtime output sink. Lua parse/runtime errors are labelled and runtime errors include a traceback. Results format scalar values faithfully, including false/nil/multiple returns; tables/functions/userdata show their type/address without invoking arbitrary display metamethods.

Commands run only at the existing engine pump. The window/render callbacks enqueue text and read snapshots; they never execute Lua or call engine APIs. At most one command is dequeued per pump. Limits are 16 queued commands, 16 KiB per command, 100 history entries, 512 output rows and 256 KiB total output. Individual rows are truncated around 8 KiB. Rejection is visible and leaves the edit buffer available for retry. Each submission receives an increasing request ID.

The console disables/flushed LuaJIT traces before execution and installs a one-million-instruction budget hook. An ordinary accidental `while true do end` ends with an error and the next command remains usable. This is not a sandbox: intentionally replacing debug hooks, enabling JIT, catching hook errors repeatedly, blocking native functions, and callbacks outside the command cannot be forcibly preempted. The cancellation flag is cooperative; a UI on the same blocked game thread cannot deliver a click until execution yields or the budget fires. Do not treat this as a hard native-code deadline.

Completion snapshots are built on the engine thread with raw table traversal, a visited-table set, depth two, 256 visited entries per table, 16384 visited entries total and a 4096-name cap. Completion never evaluates a text expression or invokes `__index`/getters. Up to 64 matches are shown. Very large/deep tables are intentionally not exhaustive.

After initial window attachment, closed-console presentation calls the original SwapBuffers directly, without ImGui frames or OpenGL state work. An input-reset transition may perform one owner-thread input cleanup before returning to that fast path.

The Windows adapter hooks the main executable's imported SwapBuffers, subclasses the rendering window, and intercepts shared DirectInput keyboard/mouse device state/buffer reads. While open, window keyboard/mouse messages are consumed, game DirectInput output is emptied and cursor warping is suppressed. The status exposes observed DirectInput calls so attachment can be tested against the actual game. This implementation needs live verification for every supported game image; source presence or a compiled DLL does not prove gameplay input isolation. Other renderer/platform adapters are not implemented.

For automation, the optional existing harness forwards to this same service:

```json
{"cmd":"devtools","op":"submit","code":"1+1"}
{"cmd":"devtools","op":"status"}
{"cmd":"devtools","op":"output"}
{"cmd":"devtools","op":"complete","prefix":"kp.model."}
```

A submission returns `request`. Status returns `submitted`, `completed`, `running`, `queued`, `open`, and `input_calls`. Output returns bounded `lines` with `request`, `kind`, and `text`; request zero denotes unassociated system output. Poll `completed >= request`, then inspect that request's rows for results or errors. This adapter is a test surface: the actual F12 UI never calls the harness or its listener. Existing harness `lua` remains its independent test-state contract; legacy game-console `lua exec` now queues through the product console.

# Lua harness API

This is the KotorJIT API added for headless control. The generated routine
catalog in [`lua-api-complete.md`](lua-api-complete.md) is available only
through `nwscript.call(name, ...)`; it is intentionally not repeated here.

## Script loading

At process startup the runtime loads every `*.lua` file in
`<game>/kotorjit/scripts/`, once, in lexical filename order. A file may set
`priority` (higher values run first) and define any event callback. Errors put
only that file into quarantine. `OnScriptLoad(game, build)` is called after
registration; `OnScriptUnload()` runs on unload/reload.

```lua
priority = 50
function OnScriptLoad(game, build)
  kp.print("KotorJIT " .. game .. " / " .. build)
end
```

## Runtime helpers and bridge context

| API | Result | Use |
|---|---|---|
| `nwscript.with_caller(object, fn, ...)` | returns `fn` results | Runs `fn` with `object` as the temporary engine caller (`OBJECT_SELF`), restoring the prior caller even if `fn` errors. |
| `kp.registertimer(ms, callback_name[, data])` | timer handle | Schedules the named global callback on the game thread after the delay. The callback receives `(timer_id, count, data)`; return `true` to repeat it. |
| `kp.gamedir()` | string | Absolute executable/game directory. |
| `kp.time()` | number | Monotonic milliseconds for diagnostics and bounded scripts. |
| `kp.diagnostic(text[, level])` | none | Flushes a line to the runtime log; level is `debug`, `info`, `warn`, or `error`. |
| `kp.console(text)` | none | Writes a line to the game console/log. |
| `kp.feedback(text[, x, y[, life]])` | none | Engine feedback text; one argument uses the default position/lifetime. |

## `kp.harness`

These are the same native control operations used by the external harness,
available from a Lua callback or `lua exec`. Mutating operations return `true`
when the request is dispatched and raise a Lua error when the adapter or the
build cannot honour it. Query operations return the value described in the
table and raise on an unavailable adapter or field. The `take_*_result`
operations are non-blocking: they return `nil` while a deferred transaction is
still pending and a result table once its postcondition is observed. All of
these calls run on the game thread; a successful dispatch does not claim that a
deferred action has finished. `screenshot(path)` returns `nil, error` when a
capture is already queued instead of raising.

Harness object-id arguments accept exact unsigned 32-bit Lua numbers, including
values above `0x7fffffff`; IDs returned in deferred result tables use Lua
numbers too, so they can be passed back to another harness operation on 32-bit
LuaJIT builds without signed-integer wraparound.

| API | Arguments | Operation |
|---|---|---|
| `ping()` | none | Returns `{pong, tick, build, phase, live}` for a quick runtime check. Its `phase` is the runtime lifecycle; `state().phase` is the game phase. |
| `state()` | none | Returns `{phase, module, adapter, chargen_stage, modal_count, timers_paused, phase_detail, server_tick, client_tick, live, poisoned, counts}` plus `pc`, `party`, `dialog`, `globals_hash`, and `journal_hash` when available. `dialog` is omitted when no conversation is active; hashes are omitted if that walk is unavailable. `pc_error` reports a failed protected PC/party read. `phase_detail` contains `server_mode`, `loading_module`, `area_not_ready`, `input_class`, `main_menu`, `game_over`, `pause`, `controller_pause`, `tutorial`, `modal_count`, `status_summary`, `movie`, `load_error`, `move_pending`, `chargen`, and `timers_paused`; `-1` means unreadable on this build. |
| `status()` | none | Returns runtime/build identity, optional `failure`, process id, control-channel uptime in milliseconds, hook and script counts, adapter, missing sites, poison list, and latest event sequence. Uptime is `0` when the optional socket channel is disabled. |
| `adapter_name()` | none | Returns `k1` or `k2` for the selected native adapter. |
| `new_game()` | none | Starts the engine-owned new-game flow. |
| `chargen_select_class(index)` | integer `0..5` | Selects a class through the native character-generation panel. |
| `chargen_begin_play()` | none | Completes character generation through BeginPlayGame. |
| `chargen_stage()` | none | Returns the current verified character-generation stage. |
| `load_save(dir)` | save directory string | Issues the engine load-save sequence. |
| `save(slot[, name])` | integer, string | Requests a native save; `name` defaults to `harness`. |
| `warp(module)` | module resref | Requests the native module transition. |
| `speed([scale])` | optional number `0 < scale` | Sets world-time scale, clamping values above `16` to `16`; with no argument, returns the current scale. |
| `fixed_step(hz)` | integer | Sets the fixed snapshot rate (`0` disables it; negative values normalize to `0`; the engine accepts `1..100000`). |
| `movies(enabled)` | boolean | Enables or disables movie playback. |
| `dialog_skip()` | none | Advances/skips the active dialog sound wait through the native dialog path. |
| `dialog_continue()` | none | Continues an empty authored dialog node. |
| `dialog_abort()` | none | Ends the active dialog through the native close path. |
| `dialog()` | none | Returns the current dialog table, including authored reply text and indices. |
| `reply(index)` | integer | Chooses a visible dialog reply through the native reply path. |
| `dialog_clear_sound_wait()` | none | Clears an engine sound wait. |
| `clear_auto_pause()` | none | Clears the adapter’s detected automatic pause. |
| `unpause_timers()` | none | Unpauses world timers through native timer calls. |
| `advance_tutorial()` | none | Sends the tutorial panel’s native continue event. |
| `finish_hidden_tutorial()` | none | Completes the hidden tutorial path. |
| `dismiss_status_summary()` | none | Retires the status-summary modal through its handler. |
| `dismiss_messagebox()` | none | Accepts the top message box through its native handler. |
| `equipment(enabled)` / `equipment_screen(enabled)` | boolean | Opens/closes the equipment screen lifecycle. |
| `door_use(door)` | unsigned 32-bit object id | Sends the retail door-use request. |
| `door_commit_open(door)` | unsigned 32-bit object id | Commits a pending native door animation state. |
| `door_security(door)` | unsigned 32-bit object id | Starts the retail lock-pick/security action; never writes lock state. |
| `take_door_security_result()` | none | Returns the completed security result table, or `nil` while pending. |
| `attack(target)` | unsigned 32-bit object id | Sends a normal retail attack request. |
| `dismiss_container()` | none | Closes the top native container panel. |
| `take_all_container()` | none | Uses the native Take All event and closes the panel. |
| `accept_party_selection()` | none | Commits the native party-selection modal. |
| `set_party_leader(index)` | integer | Arms a native party leader change; slot `0` is already the leader. |
| `take_party_leader_result()` | none | Returns the completed leader result table, or `nil` while pending. |
| `use_item(item[, target])` | unsigned 32-bit ids | Sends the native party-menu item-use request; omitted target means the PC. |
| `take_use_item_result()` | none | Returns the completed item-use result table, or `nil` while pending. |
| `equip_item(item, slot[, instant])` | unsigned 32-bit id, slot `0..31`, boolean | Runs the native equipment path; `instant` defaults to `true`. |
| `take_equip_item_result()` | none | Returns the completed equipment result table, or `nil` while pending. |
| `auto_levelup()` | none | Arms the GUI-independent native PC auto-level path. |
| `take_auto_levelup_result()` | none | Returns the completed level result table, or `nil` while pending. |
| `movies_enabled()` | none | Reads the native movie-playback setting. |
| `missing_sites()` | none | Returns unresolved logical hook-site names for this binary. |
| `globals()` | none | Returns `{bools, numbers, strings}` from the adapter’s engine-global walk. |
| `journal()` | none | Returns the native journal entries as `{tag, state}` records. |
| `events([since[, limit]])` | non-negative cursor and limit | Reads the event ring after `since`; defaults to cursor `0`, limit `256`, capped at `4096`. A limit of `0` also means `256`. Returns `{seq, oldest, items}`; each item has `event`, `tick`, `seq`, and event-specific fields. |
| `screenshot(path)` | output path | Schedules a front-buffer PPM capture after the next rendered frame; returns `true`, or `nil, error` if another capture is pending. |
| `take_screenshot_result()` | none | Returns `nil` while pending, then `{ok, path, width, height, client_tick, format}` or `{ok=false, path, error}`. |
| `reload()` | none | Requests a script reload after the current game callback stack unwinds; returns `true` when queued. Reload details go to the runtime log. |
| `quit()` | none | Requests an orderly game exit after the current frame; returns `true` when queued. |

`state().counts` contains the number of globals and journal entries traversed;
each hash is populated only when its complete adapter walk succeeds. In Lua,
omitted fields represent the socket protocol's JSON `null` values.

The `take_*_result` calls are intentionally non-blocking. Start the operation,
then poll from a short `kp.registertimer` callback until a table is returned.
For adapter transactions, an engine failure raises a Lua error; `nil` means the
native transaction has not reached its postcondition yet. Screenshot completion
uses an `ok` field because capture failures include filesystem or GL errors.
Pending transactions are process-wide, so a Lua script and a socket client
should not arm the same transaction family at the same time. Consume a
screenshot result before queuing another capture; a newer request replaces an
unconsumed screenshot result.

## Callback arbitration

`OnRunScript`, `OnDialogConditional`, and the creature/area/item callbacks
are cancellable. Return `false` to stop the game handler. Return nothing to
abstain. Every registered script still runs; later scripts receive
`relevant=false` after an earlier script has claimed the result. `OnTick(tick)`
runs once per server frame and should remain short.

## Existing game API

This page documents the KotorJIT additions used by the harness. The
NWScript-compatible routine catalog used by `nwscript.call(name, ...)` and the
existing memory, struct, and entity APIs are listed in
[`lua-api-complete.md`](lua-api-complete.md).

## Headless driving pattern

Every game-facing harness operation is available in this Lua namespace,
including event-ring reads and deferred screenshot capture. Lua uses
`events()` with a cursor to poll the same ring that the socket controller can
stream with `subscribe`; socket subscription and remote `lua` evaluation are
transport features. A Lua script can drive the game without a socket client
and verify each dispatch through a later callback or timer. For example:

```lua
local d = kp.harness.dialog()
if d.active and d.waiting_for_player then
  kp.harness.reply(d.replies[1].index)
end
function poll_harness_state(id, count, data)
  local state = kp.harness.state()
  kp.print("phase=" .. state.phase .. " module=" .. state.module)
  return count < data.max_polls
end
kp.registertimer(250, "poll_harness_state", {max_polls = 10})
```

Lua calls still go through the engine’s native handlers and postcondition
checks. They must not synthesize GUI state, journal state, party membership, or
door flags with memory writes. The screenshot functions use the same
render-thread capture path. Checkpoint storage and scenario orchestration
remain driver facilities; `reload()` and `quit()` are queued until the active
game callback has unwound.

## Optional channel

Add this to `kotorjit.ini` to enable the external controller:

```ini
harness_port = 27015
harness_bind = 127.0.0.1
```

`KOTORJIT_HARNESS_PORT` overrides the port. Commands execute on the game
thread; state reads are independent postconditions, not acknowledgements that
an action completed.

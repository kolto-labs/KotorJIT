# Write a script

Put a `.lua` file in `<game>/kotorphasor/scripts/`. Each file is its own Lua state. Scripts do not share globals.

Define only the callbacks you need. A missing callback costs a lookup, not a Lua call.

```lua
priority = 10

function OnScriptLoad(game, build)
    kp.print("loaded on " .. tostring(game) .. " " .. tostring(build))
end

function OnRunScript(script_name, object_id, has_object, relevant)
    if script_name == "k_ambush_spawn" then
        return false
    end
end
```

`kp.print` writes to `kotorphasor.log`.

Native facilities are owned by `kp`; direct engine routines are available only
through `nwscript.call(name, ...)`. Lua's standard `print` keeps its normal stdout
behavior. API version 2 removes the former host root and bare compatibility names.
The dispatcher still discovers global `On*` callbacks for legacy compatibility;
new explicit bindings use `kp.events.register(kp.events.OnTick, function(...) ... end)`.
The script's own `priority` global remains loader metadata.

## Priority

Higher `priority` runs first. Ties break on filename. A script that omits `priority` is ordered by filename only.

Every script that defines a callback is called. The first return that converts to the expected type decides the outcome. Later scripts still run, with `relevant = false`. Returning nothing abstains.

For a boolean result, the value is compared against `1`. Returning `2` is `false`.

`return false` from `OnRunScript` stops the game's own script for that call.

## Events that fire today

| Callback | When |
|---|---|
| `OnScriptLoad` | After the file loads |
| `OnScriptUnload` | Before unload, reload, or quarantine |
| `OnTick` | Once per server frame |
| `OnRunScript` | Every NWScript the engine runs |
| `OnRunScriptDone` | After that script finishes |
| `OnConsoleCommand` | Every cheat-console line, on Enter |
| `OnSave` / `OnLoad` | Script-situation save and restore |
| `OnModuleLoad`, `OnModulePlayerEnter`, `OnAreaEnter`, `OnCreatureAttacked` | Proven on 0.1.0 |
| Other `OnModule*`, `OnArea*`, `OnDoor*`, `OnPlaceable*`, `OnTrigger*`, `OnEncounter*`, `OnAoe*`, `OnStoreOpen`, `OnWaypointDestroy`, and creature EventHandler names | Installed; they fire when the engine raises that id |

Do **not** write `function OnCreatureHeartbeat` or `function OnDialogConditional`. Those names never run. Heartbeats, spawn, damage, death, end-of-round, and dialog conditionals arrive as `OnRunScript` with a script resref (`k_def_heartbt01`, `k_hen_spawn01`, …).

The full table is in [api-status.md](api-status.md). Argument lists are in [../lua-api.md](../lua-api.md).

## Call the game

Call any of the 769 supported engine routines through `nwscript.call(name, ...)`.
Arguments after the name follow `nwscript.nss` order. You may omit trailing defaults.
Routine names are not installed as Lua globals or table members.

```lua
local pc = nwscript.call("GetFirstPC")
nwscript.call("SendMessageToPC", pc, "hello")
nwscript.call("AdjustAlignment", pc, 0, 5)
```

These three names are missing on purpose. They need an NWScript closure Lua cannot build:

- `AssignCommand`: use `kp.as(object_id, function() ... end)`
- `DelayCommand`: use `kp.registertimer(ms, "callback_name", data)`
- `ActionDoCommand`: same timer, or `kp.as`

```lua
local id = kp.registertimer(1500, "on_bang", { n = 3 })

function on_bang(timer_id, count, data)
    kp.feedback("bang " .. count)
    return count < data.n
end
```

The timer callback is a **string** naming a global, not a function value. Return true to run again.

A vector is `{ x =, y =, z = }`. An effect, event, location, or talent is an opaque handle. Hold it and pass it back. Do not index it.

`Action*` calls often do nothing while the cheat console has focus. Close the console if a queued action seems ignored.

## Harness controls from Lua

The headless harness controls are also available in the loaded game state under
`kp.harness`. This is the same native adapter and event ring used by the
socket driver, so Lua can inspect dialog replies and choose them, start loads
and warps, control timing, read globals or journal entries, query runtime
status, inspect events, and request a post-render screenshot without
synthesizing memory state. Deferred actions return immediately; poll their
matching `take_*_result()` function from a timer. See
[the complete harness API](../lua-harness-api.md) for every operation and
result shape, including safe queued reload and quit requests.

```lua
local dialog = kp.harness.dialog()
if dialog.active and dialog.waiting_for_player then
    kp.harness.reply(dialog.replies[1].index)
end
```

## Host names that exist

| Name | What it does |
|---|---|
| `nwscript.call(name, ...)` | Direct engine routines; names are listed in [the generated catalog](../nwscript-api.md) |
| `kp.as` | Run a Lua function as `OBJECT_SELF` |
| `kp.speed([n])` | Read or set MainLoop tick scale |
| `kp.version` | `"0.1.0"` |
| `kp.obj` | Object handles, party, `find` |
| `kp.struct` | Named field views |
| `kp.mem` | Raw reads and writes |
| `kp.log`, `kp.console`, `kp.feedback` | Log, console text, on-screen message |
| `kp.registertimer`, `kp.removetimer` | Delayed work |
| `kp.print` | Log line |
| `kp.events.register` / `kp.events.On*` | Bind a handler after load |

`kp.timer.after`, `kp.obj.create`, and most other `kp.*` rows in `data/hostapi.toml` are **not** bound. Calling them is `nil`. See [api-status.md](api-status.md).

Bare host names and underscored compatibility aliases have been removed. See the [API version 2 migration](../api-dialects.md).

## Cheat console

| Command | What it does |
|---|---|
| `lua exec <code>` | Run one expression, then one statement if that fails |
| `lua status` | Write runtime facts to the log |
| `lua reload` | Reload every script; also re-arms after a fault |

The input line is 512 bytes. `OnConsoleCommand` sees every line, including ones the game does not know. Return `false` to consume the line.

`heal` and similar stock cheats close the console. Open it again before the next `lua exec`.

## Errors

A script that keeps raising is quarantined after `error_budget` failures (default 8). `lua reload` loads a fresh state. A hook that faults in C++ can turn scripting off; `lua reload` turns it back on if the process is still sound.

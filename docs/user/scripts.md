# Write a script

Put a `.lua` file in `<game>/kotorphasor/scripts/`. Each file is its own Lua state. Scripts do not share globals.

Define only the callbacks you need. A missing callback costs a lookup, not a Lua call.

```lua
priority = 10

function OnScriptLoad(game, build)
    print("loaded on " .. tostring(game) .. " " .. tostring(build))
end

function OnRunScript(script_name, object_id, has_object, relevant)
    if script_name == "k_ambush_spawn" then
        return false
    end
end
```

`print` writes to `kotorphasor.log`.

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

769 engine routines are `kotor.<Name>`. Arguments follow `nwscript.nss` order. You may omit trailing defaults.

```lua
local pc = kotor.GetFirstPC()
kotor.SendMessageToPC(pc, "hello")
kotor.AdjustAlignment(pc, 0, 5)
```

These three names are missing on purpose. They need an NWScript closure Lua cannot build:

- `kotor.AssignCommand`: use `kp.as(object_id, function() ... end)`
- `kotor.DelayCommand`: use `kotor.registertimer(ms, "callback_name", data)`
- `kotor.ActionDoCommand`: same timer, or `kp.as`

```lua
local id = kotor.registertimer(1500, "on_bang", { n = 3 })

function on_bang(timer_id, count, data)
    kotor.feedback("bang " .. count)
    return count < data.n
end
```

The timer callback is a **string** naming a global, not a function value. Return true to run again.

A vector is `{ x =, y =, z = }`. An effect, event, location, or talent is an opaque handle. Hold it and pass it back. Do not index it.

`Action*` calls often do nothing while the cheat console has focus. Close the console if a queued action seems ignored.

## Host names that exist

| Name | What it does |
|---|---|
| `kotor.GetFirstPC` and the other 768 routines | Engine work |
| `kp.as` | Run a Lua function as `OBJECT_SELF` |
| `kp.speed([n])` | Read or set MainLoop tick scale |
| `kp.version` / `_KP_VERSION` | `"0.1.0"` |
| `kotor.obj` / `kp.obj` | Object handles, party, `find` |
| `kotor.struct` / `kp.struct` | Named field views |
| `kotor.mem` | Raw reads and writes (not `kp.mem`) |
| `kotor.log`, `kotor.console`, `kotor.feedback` | Log, console text, on-screen message |
| `kotor.registertimer`, `kotor.removetimer` | Delayed work |
| `print` | Log line |
| `register_callback` / `cb.On*` | Bind a handler after load |

`kp.timer.after`, `kp.print`, `kp.obj.create`, and most other `kp.*` rows in `data/hostapi.toml` are **not** bound. Calling them is `nil`. See [api-status.md](api-status.md).

Underscored aliases also work: `read_byte`, `register_timer`, and the rest listed in [../api-dialects.md](../api-dialects.md).

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

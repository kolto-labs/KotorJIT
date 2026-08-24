# Lua API reference

Generated from `data/events.toml`. Do not edit by hand.

## How to write a script

Define only the callbacks you want. Anything you leave out costs nothing.

```lua
priority = 10   -- optional; higher runs first, ties break on filename

function OnScriptEvent(script, object, relevant)
    if script == "k_def_heartbeat01" then return false end
end
```

## When several scripts answer the same event

Every script that defines the callback is called, in priority order. The first
one to return a usable value decides the outcome. Later scripts still run, and
receive `relevant = false` to say their answer will not be used.

Returning nothing means you are abstaining, not voting. So does returning a
value that will not convert -- a non-numeric string where a number is wanted,
for instance. Returning `"5"` where a number is wanted does convert.

For a boolean result the value is compared against 1. Returning `2` gives
`false`, not `true`.

If your event returns several values and any one of them will not convert, the
whole answer is discarded and you have abstained.

## Events

#### `OnScriptLoad(game, build, relevant)`

Called once after the script loads. `build` is the identified game build, e.g. k1_steam_103.

| argument | type |
|---|---|
| `game` | string |
| `build` | string |

Returns: nothing. 

#### `OnScriptUnload(relevant)`

Called before the script is unloaded, including on reload and on quarantine.

Returns: nothing. 

#### `OnTick(tick, relevant)`

Called once per server frame. This is the highest-frequency callback -- a script that does not define it pays nothing, but one that does should keep the body short.

| argument | type |
|---|---|
| `tick` | int |

Returns: nothing. 

#### `OnScriptEvent(script, object, relevant)`

Called before the engine runs any NWScript. `script` is the resref, e.g. "k_def_heartbeat01". Return false to stop it running. The engine is told the script ran, so blocking stays invisible to whatever asked for it.

| argument | type |
|---|---|
| `script` | string |
| `object` | object |

Returns: bool. If no script answers, the result is `true`. Returning false stops the game's own handler.

#### `OnScriptEventDone(script, object, ran, relevant)`

Called after an NWScript finishes. `ran` is the engine's own return value.

| argument | type |
|---|---|
| `script` | string |
| `object` | object |
| `ran` | bool |

Returns: nothing. 

#### `OnConsoleCommand(line, relevant)`

Called for every line typed into the cheat console, including lines the game does not recognise. Return false to consume the line so the game never sees it -- which is how a script adds its own commands.

| argument | type |
|---|---|
| `line` | string |

Returns: bool. If no script answers, the result is `true`. Returning false stops the game's own handler.

### Medium confidence

Argument mapping is partly verified. Check before relying on it.

#### `OnModuleLoad(module, relevant)`

Called when a module begins loading. The argument mapping is not yet verified.

| argument | type |
|---|---|
| `module` | string |

Returns: nothing. 

#### `OnSave(relevant)`

Return a string to persist alongside the save. It comes back to OnLoad when that save is loaded.

Returns: string. 

#### `OnLoad(state, relevant)`

Receives whatever OnSave returned when this save was written.

| argument | type |
|---|---|
| `state` | string |

Returns: nothing. 

### Low confidence

Argument mapping is **not yet verified against the game's own code**. Names and types may change.

#### `OnCreatureEvent(creature, event_type, caller, relevant)`

Called for engine-level creature events. `event_type` is the raw engine constant; named per-type events replace this once the constants are verified.

| argument | type |
|---|---|
| `creature` | object |
| `event_type` | int |
| `caller` | object |

Returns: bool. If no script answers, the result is `true`. Returning false stops the game's own handler.

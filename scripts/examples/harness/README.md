# Harness Lua examples

Lua chunks you run against a booted headless game over the control channel.
They read and drive the live world the same way the scenario runner and the
`pioneer` CLI do. Historical K1 Endar Spire runs covered many snippets, but those receipts
were not bound to current source hashes. The exact `end_m01ab/from_01a`
transition remains unvalidated. See [example validation](../../../docs/example-validation.md).

## Run one

```sh
cd /path/to/KotorJIT
PYTHONPATH=scripts/harness python3 -m kpharness.cli boot --target k1
PYTHONPATH=scripts/harness python3 -m kpharness.cli exec --target k1 "$(cat scripts/examples/harness/10_world_probe.lua)"
```

Or from a route file / `pioneer step`:

```json
{"do": "lua", "code": "<one-line chunk>", "timeout": 20}
```

A chunk returns a value; tables come back as JSON under `values[0]`.
The loot snippet's `taken` field counts queued `ActionTakeItem` requests; poll
inventory to verify acquisition. The PC status snippet inspects wearable slots
0 through 11, not every engine slot. `GetIsInConversation` is the registered
conversation query; `IsInConversation` is not a routine.

## How the API is shaped

- `nwscript.call(name, ...)` reaches NWScript routines with the same argument order as
  `nwscript.nss` (K1). Object ids are plain integers. Strings from the engine
  carry a trailing `\0`; strip it with `s:gsub("%z","")` before comparing.
- `nwscript.with_caller(obj, function() ... end)` is `AssignCommand`: the closure runs with
  `obj` as `OBJECT_SELF`, so `Action*` calls inside it queue on `obj`. Outside
  `nwscript.with_caller`, `OBJECT_SELF` is not the PC, and `Action*` calls go nowhere.
- Nothing here writes engine memory. State changes go through the action
  queue or NWScript setters (`SetLocked`, `SetCommandable`, ...).

## Pitfalls seen live

| Call | What happens | Use instead |
|---|---|---|
| `nwscript.call('AssignCommand', ...)` | action-closure error | `nwscript.with_caller(obj, fn)` |
| `nwscript.call('Location', area, vec, f)` | "takes at most 2 arguments" | `nwscript.call('Location', vec, facing)` |
| `nwscript.call('GetUserActionsPending', pc)` | "takes at most 0 arguments" | `nwscript.call('GetCurrentAction', pc)` |
| `nwscript.call('GetLockKeyTag', d)` | string return unsupported | `nwscript.call('GetLockKeyRequired', d)` |
| `GetUseableFlag`, `GetPartyLeader`, `IsInConversation`, `SetPauseState` | unknown routine | see the snippets |
| `GetIsDoorActionPossible(d, 0) == 0` on a plot door | PC cannot open it | `nwscript.with_caller(d, function() nwscript.call('ActionOpenDoor', d) end)` |

## Action codes (`GetCurrentAction`)

`65534` idle, `0` move to point, `3` attack object, `7` dialog object,
`38` follow leader (companion AI re-asserts this every heartbeat),
`39` in a combat round.

## Cutscenes and scripts

- A Skippable cinematic ends entirely on `dialog_skip` (that is the Escape
  key), dropping every later node's script. Clear the VO wait first
  (`dialog_clear_sound_wait`), skip second, abort last -- the order the
  scenario runner's dialog ladder uses.
- After a talk or a fight the engine may raise the XP status summary
  (`phase_detail.status_summary == 1`, world paused); `dismiss_status_summary`
  clears it.
- Cutscenes that pause and resume their conversation on DelayCommands
  (Trask's sacrifice, k_pend_traskdie1 -> resume2 -> cut14 ...) die at 16x
  game speed and complete at 1x. Wrap such a beat in `speed 1` / `speed 16`
  route steps rather than diagnosing a missing node.
- When a cutscene's later nodes did not run, fire the authored script itself
  (`nwscript.call('ExecuteScript', ...)`, see `90_run_script.lua`) or its authored event
  (`nwscript.call('SignalEvent', ...)`, see `80_signal_event.lua`) instead of emulating the
  effect. Make such steps idempotent: check for the effect before creating
  objects.

## Reading a stalled world

If ticks advance but nothing moves, fights, or converses, the world timers are
paused. The engine's autopause (enemy sighted, combat start) pauses them; the
raw commands `clear_auto_pause` and `unpause_timers` restore them, and the
staged ini disables autopause so it stops happening. `50_doors.lua` and
`40_attack_nearest.lua` show the state-gated polling that catches this.

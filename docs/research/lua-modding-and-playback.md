# Lua modding ergonomics and playback research

22 September 2026. These are implementation decisions and planned interfaces; only features with implementation and live receipts should be presented as available.

## Familiar utilities without a compatibility fork

Garry's Mod demonstrates useful vector arithmetic, closure-based timers, removable hooks and entity queries. Factorio demonstrates explicit filter-table queries. KotorPhasor will borrow those conventions within its current ownership model. GMod's sphere query uses bounding boxes; a KotOR center-distance query must say so. Its hook return rules also differ from our existing event arbitration. [GMod vectors](https://wiki.facepunch.com/gmod/Vector), [timers](https://wiki.facepunch.com/gmod/timer.Create), [hooks](https://wiki.facepunch.com/gmod/hook.Add), [sphere queries](https://wiki.facepunch.com/gmod/ents.FindInSphere), [Factorio filtered queries](https://lua-api.factorio.com/latest/classes/LuaSurface.html#find_entities_filtered).

Immediate utility slice:

- `kp.vec`: table-backed vector arithmetic and geometry, compatible with existing raw `x/y/z` bridge values. Fresh results, explicit finite-value checks, explicit degree units, no global `Vector` alias.
- Function callbacks on existing `kp.registertimer`, preserving its millisecond clock, owner state, cancellation, error policy and renewal semantics. No second scheduler and no synthetic global callback names.

Existing `kp.events.register` already accepts functions, and `kp.obj` already provides PC, party and object access. Do not add parallel `hook`, `ents` or `player` globals. Later utilities should extend these existing modules: bounded value inspection, generated API help, filtered queries and owner-aware subscription tokens. Current generic object handles do not prove generation identity for same-type ID reuse; future query records must not imply stronger safety.

Example intended style after the utility slice lands:

```lua
local start = kp.vec.from(kp.obj.pc():position())
local destination = start + kp.vec.forward_degrees(90) * 6
local timer = kp.registertimer(1000, function(id, count, data)
    kp.console("tick " .. count)
    return count < 3
end)
```

Vector construction computes a value; it does not move an object or promise a camera heading. Native mutation still requires its typed, verified backend and appropriate ownership checks.

## Ren'Py-style controls with a KotOR state contract

Ren'Py can roll back interactions because it owns the interpreter, checkpoints and revertable store. Its save/load state and rollback participation are explicitly defined. Its `pause` is an interaction wait, which differs from freezing KotOR world time. Borrow the explicit checkpoint and choice-boundary concepts; do not imply the same mechanism exists in KotOR. [Saving, loading and rollback](https://www.renpy.org/doc/html/save_load_rollback.html), [pause semantics](https://www.renpy.org/doc/html/statement_equivalents.html#pause).

Proposed product interface, not yet implemented:

```lua
local token = kp.runtime.pause({reason = "inspect scene"})
kp.runtime.resume(token)
local job = kp.runtime.checkpoint("before_choice", {slot = 901})
kp.runtime.job(job.id) -- pending / ready / failed
local restore = kp.runtime.restore("before_choice")
kp.dialog.history()
kp.dialog.rewind(choice_id) -- only with a verified restorable checkpoint
```

The current harness supplies native save requests, native load sequences, dialog observation/reply selection and recovery-oriented unpause. A successful save request is not completion. The Python driver currently supplies file-set stabilization and private checkpoint copying. Those lifecycle rules must move into a product-owned service before the Lua API can offer them independently; harness transport and TOML become clients.

First playback slice needs symmetric, token-owned pause/resume; asynchronous save/restore jobs; explicit save slot and overwrite policy; artifact completion checks; checkpoint/build/module metadata; and a new session epoch after load. Preserve a pause already owned by the game. Never equate positive slow-motion scaling with pause or skip server ticks to simulate complete frozen state.

Dialog history can record replies and associate choices with ready checkpoints. A transcript entry without a checkpoint remains history. Initially restore may return to a safe pre-conversation gameplay save, requiring the conversation to restart. Saving during active dialog is unverified. Replaying prior choices must verify each node/reply and stop on divergence. Writing an old dialog index is not rollback.

Round-trip acceptance must cover the effects the user expects to undo: quest/global state, inventory, party/HP/position, spawned objects and dialog choices. Lua timers, closures, random state and FFI resources need an explicit separate state policy. The existing one-file `lua_situation.dat` is not per-checkpoint Lua VM serialization. Fine-grained engine-memory snapshots remain a separate research phase, not an advertised save-state feature.

## Delivery order

1. Complete real F12 input/output/native command acceptance and reviewed video.
2. Add the scoped vector/timer utility pack and console-driven demonstrations.
3. Extract and verify product playback controls and coarse native checkpoints.
4. Add dialog-choice associations and tested checkpoint rewind.
5. Add per-checkpoint declared script data, then investigate finer rollback coverage.

The live editor roadmap is in [devtools-design.md](../devtools-design.md). Harness configuration remains documented independently.

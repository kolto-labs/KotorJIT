# Nonvisual TAS capability audit

Audited 2026-09-10 against the current generated routine tables, harness
adapter, scenario runner, and the recovered route notes. This is a capability
audit, not live proof. No game was launched for this audit.

## Practical control model

The driver can remain entirely state driven. A route step should select an
object by its module-local tag, issue an NWScript action through `kp.as`, and
wait for a state predicate or event. The model does not need to see the game
or synthesize keyboard input:

```lua
local pc = kotor.GetFirstPC()
local door = kotor.GetObjectByTag("end_door01", 0)
kp.as(pc, function()
  kotor.ActionMoveToObject(door, 1, 1.0)
  kotor.ActionOpenDoor(door)
end)
```

`kp.as` temporarily supplies the engine command implementer's caller object,
then restores it even when the Lua call fails. The action is therefore queued
for the PC by the engine; it is not a memory write or a simulated keypress.
The driver must follow it with `state`, `lua`, or event polling and must not
declare success from the return value of a void action.

## Capability matrix

The routine names and parameter shapes below are generated in both
`src/generated/routines_k1.inc` and `src/generated/routines_k2.inc`. “Bound”
means the routine is in the per-game generated API; whether a particular
binary has a resolved address is a separate address-table question and must be
checked through the runtime's `missing_sites`/call error.

| Need | Existing engine routine(s) | Evidence available now | What a TAS step can prove |
| --- | --- | --- | --- |
| Locate a named object | `GetObjectByTag(tag, nth)`, `GetNearestObject(type, origin, nth)`, `GetIsObjectValid` | Generated in K1 and K2; Endar tag `end_door01` was returned by a prior live softlock run | Non-invalid object ID, then `GetTag` and `GetPosition` readback |
| Read movement state | `GetPosition`, `GetDistanceToObject`, `GetDistanceToObject2D` | Generated in K1 and K2; position is already part of the state fingerprint | Position changes and distance reaches a route-specific threshold |
| Walk to an object/location | `ActionMoveToObject`, `ActionMoveToLocation`, `ActionForceMoveToObject`, `ActionForceMoveToLocation` | Generated in K1 and K2; parameter shapes are object/location plus run/range | Position/distance predicate and subsequent action/event; no generic action-complete flag is currently exposed |
| Operate a door | `ActionOpenDoor`, `ActionCloseDoor`, `GetIsDoorActionPossible`, `DoDoorAction`, `GetLocked`, `SetLocked` | Generated in K1 and K2; locked-door behavior and `GetLocked == 0` were observed in the live softlock investigation | Door state/action result or module transition; avoid treating `Action*` return as proof |
| Operate a console/container | `ActionInteractObject`, `GetIsPlaceableObjectActionPossible`, `DoPlaceableObjectAction` | `ActionInteractObject` resolves a placeable through `GetPlaceableByGameObjectID`; it is not a generic NPC or door interaction | Placeable action result, inventory change, dialog, or event. Object-specific tags and action constants still need corpus measurement |
| Start conversation | `ActionStartConversation(npc, dlg, ...)` | Generated in K1/K2; `end_trask` is used by the existing dialog scenario; exact K1/K2 arity differs | `phase == dialog`, nonempty `dialog.replies`, then reply transition |
| Select dialogue | Harness `dialog` and `reply`; Lua `ActionStartConversation` | Harness adapter reads active node/replies and calls the engine reply path; reply path is documented and K1-tested at the call level | Entry/reply changes or dialog ends, with event and journal/global checks |
| Skip or end dialogue | Harness `dialog_skip`, `dialog_abort`; Lua `ActionPauseConversation`/`ActionResumeConversation` | Engine adapter and recovered conversation audit; `dialog_skip` handles VO wait | Dialog phase exits or node advances; never use a fixed VO delay |
| Fight | `ActionAttack`, `ActionUseFeat`, `ActionUseSkill`, `ActionCastSpellAtObject`, `GetIsInCombat`, `GetAttackTarget`, `GetIsDead`, HP reads | Generated in K1/K2; K1 route notes say console focus made `ActionAttack` unreliable, while scripted Endar combat is known to occur | Target death, combat exit, HP/party state and relevant script event. `ActionAttack` needs a dedicated live control-path proof |
| Loot/equip/give | `CreateItemOnObject`, `ActionPickUpItem`, `ActionEquipItem`, `GetFirstItemInInventory`, `GetNextItemInInventory`, `GetItemPossessedBy`, `ActionGiveItem`, `GiveItem` | Generated in K1/K2; no complete Endar loot route has been live-proven through the harness | Item/template or inventory enumeration change, then equip/readback |
| Plot progression | `ExecuteScript`, `SetGlobalBoolean/Number/String`, `AddJournalQuestEntry`, `GetJournalEntry`, `GetGlobal*` | Several state routines are live-proven; plot writes are command-path evidence unless journal/global readback changes | Journal/global change plus the corresponding module/dialog/event transition |
| Area/module transition | Harness `warp`; Lua `StartNewModule`, `JumpToObject`, `JumpToLocation` | Harness warp has been live-proven; route-specific door transition has not | `module` changes, load detail settles, `phase == gameplay`, valid PC |
| Save/rollback | Harness `save`, `load_save`, checkpoints | Existing load/save path and checkpoint mechanism are implemented; K1 load gameplay is live-proven | Save artifact exists; restored module/PC/state matches expected checkpoint |

## What is missing for a real Endar Spire route

The current primitives are enough to build a closed-loop route, but they do
not yet constitute one. The smallest missing slice is a **route probe**, not a
new hook:

1. Enumerate the known Endar module objects from the game-side Lua API using
   tags discovered by the corpus, and return `{id, tag, position, type}` for
   each candidate. The existing API can read an individual object, but there
   is no harness command that enumerates all module objects or exposes a
   generic object type/tag index.
2. For each route interaction, measure the object-specific action and its
   completion predicate in a throwaway checkpoint: move to the object, use
   the door/console/container, then require an object state, dialog, event,
   inventory change, or module change. Record the successful tag and action
   constants in declarative route data.
3. Add encounter branches based on `GetIsDead`, HP and combat state. The
   speedrun notes explicitly describe a probabilistic grenade outcome, so a
   deterministic route cannot assume that all three Sith die.
4. Add a route-level checkpoint after each stable room/encounter. A failed
   precondition restores the preceding checkpoint and retries only an
   idempotent action. Do not retry a conversation start or transition blindly.

The existing scenario runner already supplies the required control loop:
`do = "lua"`, `wait = "phase"|"module"|"dialog"|"global"|"journal"`,
event-order assertions, checkpoints, screenshots, and the softlock watchdog.
Its current `walk_dialog` helper demonstrates rollback and reply iteration.
No new Python scheduler is needed until route probes show that a generic
object enumeration primitive is insufficient.

## Route strategy and evidence boundary

The speedrun route research in `kotor-speedrun-routes.md` supplies the order of
the Endar Spire tasks and the K2 prologue, but it does not supply universal
object tags, coordinates, action constants, or completion signals. Those are
installation/save dependent and must be measured from each corpus. The
ordinary no-glitch route is the right first TAS profile: movement, loot,
doors, combat, dialogue, and pod transition can each be proven through engine
state. Frame buffers and unrestricted glitches belong in a separate profile
after the ordinary route works.

For a useful live proof, the recording must contain at least two minutes of
actual Endar Spire gameplay while these state-driven actions execute. Menus,
loading, camera movement, and screenshots are sanity checks only. The proof
report should additionally show the room/encounter checkpoints, final module,
valid PC, and quit result. A journal or global mutation alone is not evidence
that the physical route was played.

## Explicit ceilings

- Routine presence in both generated files is not binary resolution. Every
  target build must report unresolved routines and skip unsupported steps.
- `ActionMoveTo*` is asynchronous and has no generic action-queue completion
  read in the harness state. Use position/distance plus an event or object
  predicate until a measured action-state reader is added.
- `ActionAttack` has a documented console-focus failure mode. The TAS must
  issue it from the main-thread harness Lua path and prove target/combat state
  changed before relying on it.
- Object enumeration, object type classification, and route tags are not yet
  universal. Adding absolute addresses for them would violate the
  signature-first requirement; a routine/corpus-backed probe is required.
- The current dialog readback uses strref text labels where TLK resolution is
  unavailable. Reply indices are engine-derived and are the stable control
  input.

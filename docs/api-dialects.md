# Native namespace and callback migration

Generated from `data/api_aliases.toml` and `data/events.toml`.

API version 2 has two public roots: `nwscript.call(name, ...)` for direct engine routines and `kp` for every native host facility.

The former kotor root, bare host functions, underscored aliases, cb/events globals, host identity globals and host bit32 alias are removed. Use `kp.mem.readbyte`, `kp.registertimer` and `kp.diagnostic`. The engine logarithm is `nwscript.call('log', value)`.

Bridge context is `nwscript.with_caller(object_id, fn, ...)`; `nwscript.last_trace()` returns a limited GetFacing diagnostic table, or nil before a trace exists. Only GetFacing (routine 28) initializes a trace, after live VM/context and argument-count checks pass; other routines and those early failures do not initialize a new trace. It is not a receipt for the latest arbitrary dispatch. The old native log, as and last_routine_trace members have no compatibility aliases.

Native object conveniences such as `kp.obj.position` retain distinct names. Their C++ implementation explicitly consumes `api::find` and `api::call`; they require the VM backend for engine operations without exporting engine routine names or creating the nwscript root.

Lua's standard `print` remains unchanged. `kp.print(...)` writes host diagnostics; console and harness states capture that native output.

Host metadata is `kp.host`, `kp.serverapp`, `kp.game`, `kp.api_version` (2), `kp.version`, `kp.gamedir()` and `kp.time()`.

## Explicit event registration

```lua
kp.events.register(kp.events.OnTick, function(tick, relevant)
    -- ...
end)
kp.events.unregister(kp.events.OnTick)
```

Registration accepts a function or a script-owned global function name. The dispatcher still discovers global On* callbacks for legacy compatibility. Explicit registration wins; unregister restores a discovered global handler. Script-owned `priority` remains loader metadata. Neither behavior exports a bare host facility.

The 113 event constants below come from the event catalog.

| constant | dispatched event |
|---|---|
| `kp.events.OnScriptLoad` | `OnScriptLoad` |
| `kp.events.OnScriptUnload` | `OnScriptUnload` |
| `kp.events.OnConsoleCommand` | `OnConsoleCommand` |
| `kp.events.OnRunScriptDone` | `OnRunScriptDone` |
| `kp.events.OnSave` | `OnSave` |
| `kp.events.OnLoad` | `OnLoad` |
| `kp.events.OnTick` | `OnTick` |
| `kp.events.OnRunScript` | `OnRunScript` |
| `kp.events.OnDialogConditional` | `OnDialogConditional` |
| `kp.events.OnCreaturePerception` | `OnCreaturePerception` |
| `kp.events.OnCreatureSpellCastAt` | `OnCreatureSpellCastAt` |
| `kp.events.OnCreatureDialogue` | `OnCreatureDialogue` |
| `kp.events.OnCreatureUserDefined` | `OnCreatureUserDefined` |
| `kp.events.OnCreatureInventoryDisturbed` | `OnCreatureInventoryDisturbed` |
| `kp.events.OnCreaturePathBlocked` | `OnCreaturePathBlocked` |
| `kp.events.OnCreatureAttacked` | `OnCreatureAttacked` |
| `kp.events.OnCreatureHeartbeat` | `OnCreatureHeartbeat` |
| `kp.events.OnCreatureSpawn` | `OnCreatureSpawn` |
| `kp.events.OnCreatureDamaged` | `OnCreatureDamaged` |
| `kp.events.OnCreatureDeath` | `OnCreatureDeath` |
| `kp.events.OnCreatureEndCombatRound` | `OnCreatureEndCombatRound` |
| `kp.events.OnCreatureEndDialogue` | `OnCreatureEndDialogue` |
| `kp.events.OnCreatureTimedEvent` | `OnCreatureTimedEvent` |
| `kp.events.OnCreatureApplyEffect` | `OnCreatureApplyEffect` |
| `kp.events.OnCreatureRemoveEffect` | `OnCreatureRemoveEffect` |
| `kp.events.OnCreatureRemoveFromArea` | `OnCreatureRemoveFromArea` |
| `kp.events.OnCreaturePlayAnimation` | `OnCreaturePlayAnimation` |
| `kp.events.OnCreatureDestroy` | `OnCreatureDestroy` |
| `kp.events.OnCreatureSpellImpact` | `OnCreatureSpellImpact` |
| `kp.events.OnCreatureItemOnHitSpellImpact` | `OnCreatureItemOnHitSpellImpact` |
| `kp.events.OnCreatureForcedAction` | `OnCreatureForcedAction` |
| `kp.events.OnCreatureBroadcastAOO` | `OnCreatureBroadcastAOO` |
| `kp.events.OnCreatureBroadcastSafeProjectile` | `OnCreatureBroadcastSafeProjectile` |
| `kp.events.OnCreatureFeedbackMessage` | `OnCreatureFeedbackMessage` |
| `kp.events.OnCreatureControllerRumble` | `OnCreatureControllerRumble` |
| `kp.events.OnModuleHeartbeat` | `OnModuleHeartbeat` |
| `kp.events.OnModuleUserDefined` | `OnModuleUserDefined` |
| `kp.events.OnModuleLoad` | `OnModuleLoad` |
| `kp.events.OnModuleStart` | `OnModuleStart` |
| `kp.events.OnModulePlayerEnter` | `OnModulePlayerEnter` |
| `kp.events.OnModulePlayerExit` | `OnModulePlayerExit` |
| `kp.events.OnModuleActivateItem` | `OnModuleActivateItem` |
| `kp.events.OnModuleAcquireItem` | `OnModuleAcquireItem` |
| `kp.events.OnModuleLoseItem` | `OnModuleLoseItem` |
| `kp.events.OnModulePlayerDeath` | `OnModulePlayerDeath` |
| `kp.events.OnModulePlayerDying` | `OnModulePlayerDying` |
| `kp.events.OnModuleRespawnButtonPressed` | `OnModuleRespawnButtonPressed` |
| `kp.events.OnModulePlayerRest` | `OnModulePlayerRest` |
| `kp.events.OnModulePlayerLevelUp` | `OnModulePlayerLevelUp` |
| `kp.events.OnModuleEquipItem` | `OnModuleEquipItem` |
| `kp.events.OnModuleDestroyPlayerCreature` | `OnModuleDestroyPlayerCreature` |
| `kp.events.OnModuleTimedEvent` | `OnModuleTimedEvent` |
| `kp.events.OnAreaHeartbeat` | `OnAreaHeartbeat` |
| `kp.events.OnAreaUserDefined` | `OnAreaUserDefined` |
| `kp.events.OnAreaEnter` | `OnAreaEnter` |
| `kp.events.OnAreaExit` | `OnAreaExit` |
| `kp.events.OnAreaSpawnBodyBag` | `OnAreaSpawnBodyBag` |
| `kp.events.OnDoorHeartbeat` | `OnDoorHeartbeat` |
| `kp.events.OnDoorSpellCastAt` | `OnDoorSpellCastAt` |
| `kp.events.OnDoorDamaged` | `OnDoorDamaged` |
| `kp.events.OnDoorDialogue` | `OnDoorDialogue` |
| `kp.events.OnDoorDeath` | `OnDoorDeath` |
| `kp.events.OnDoorUserDefined` | `OnDoorUserDefined` |
| `kp.events.OnDoorDisarm` | `OnDoorDisarm` |
| `kp.events.OnDoorTrapTriggered` | `OnDoorTrapTriggered` |
| `kp.events.OnDoorLocked` | `OnDoorLocked` |
| `kp.events.OnDoorUnlocked` | `OnDoorUnlocked` |
| `kp.events.OnDoorClicked` | `OnDoorClicked` |
| `kp.events.OnDoorFailToOpen` | `OnDoorFailToOpen` |
| `kp.events.OnDoorOpen` | `OnDoorOpen` |
| `kp.events.OnDoorClose` | `OnDoorClose` |
| `kp.events.OnDoorAttacked` | `OnDoorAttacked` |
| `kp.events.OnDoorDestroy` | `OnDoorDestroy` |
| `kp.events.OnPlaceableHeartbeat` | `OnPlaceableHeartbeat` |
| `kp.events.OnPlaceableSpellCastAt` | `OnPlaceableSpellCastAt` |
| `kp.events.OnPlaceableDamaged` | `OnPlaceableDamaged` |
| `kp.events.OnPlaceableDialogue` | `OnPlaceableDialogue` |
| `kp.events.OnPlaceableDeath` | `OnPlaceableDeath` |
| `kp.events.OnPlaceableUserDefined` | `OnPlaceableUserDefined` |
| `kp.events.OnPlaceableOpen` | `OnPlaceableOpen` |
| `kp.events.OnPlaceableClose` | `OnPlaceableClose` |
| `kp.events.OnPlaceableDisarm` | `OnPlaceableDisarm` |
| `kp.events.OnPlaceableUsed` | `OnPlaceableUsed` |
| `kp.events.OnPlaceableTrapTriggered` | `OnPlaceableTrapTriggered` |
| `kp.events.OnPlaceableInventoryDisturbed` | `OnPlaceableInventoryDisturbed` |
| `kp.events.OnPlaceableLocked` | `OnPlaceableLocked` |
| `kp.events.OnPlaceableUnlocked` | `OnPlaceableUnlocked` |
| `kp.events.OnPlaceableAttacked` | `OnPlaceableAttacked` |
| `kp.events.OnPlaceableEndDialogue` | `OnPlaceableEndDialogue` |
| `kp.events.OnPlaceableAcquireItem` | `OnPlaceableAcquireItem` |
| `kp.events.OnTriggerEnter` | `OnTriggerEnter` |
| `kp.events.OnTriggerExit` | `OnTriggerExit` |
| `kp.events.OnTriggerUserDefined` | `OnTriggerUserDefined` |
| `kp.events.OnTriggerDisarm` | `OnTriggerDisarm` |
| `kp.events.OnTriggerClicked` | `OnTriggerClicked` |
| `kp.events.OnTriggerTrapTriggered` | `OnTriggerTrapTriggered` |
| `kp.events.OnTriggerHeartbeat` | `OnTriggerHeartbeat` |
| `kp.events.OnTriggerDestroy` | `OnTriggerDestroy` |
| `kp.events.OnEncounterHeartbeat` | `OnEncounterHeartbeat` |
| `kp.events.OnEncounterEnter` | `OnEncounterEnter` |
| `kp.events.OnEncounterExit` | `OnEncounterExit` |
| `kp.events.OnEncounterExhausted` | `OnEncounterExhausted` |
| `kp.events.OnEncounterUserDefined` | `OnEncounterUserDefined` |
| `kp.events.OnAoeEnter` | `OnAoeEnter` |
| `kp.events.OnAoeExit` | `OnAoeExit` |
| `kp.events.OnStoreOpen` | `OnStoreOpen` |
| `kp.events.OnWaypointDestroy` | `OnWaypointDestroy` |
| `kp.events.OnCreatureStateScript` | `OnCreatureStateScript` |
| `kp.events.OnAreaTransitionFail` | `OnAreaTransitionFail` |
| `kp.events.OnItemUse` | `OnItemUse` |
| `kp.events.OnClientRequestedScript` | `OnClientRequestedScript` |
| `kp.events.OnScriptSituation` | `OnScriptSituation` |
| `kp.events.OnPlayerSpawn` | `OnPlayerSpawn` |

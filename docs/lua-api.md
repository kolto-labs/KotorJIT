# Lua API reference

Generated from `data/events.toml`. Do not edit by hand.

## How to write a script

Define only the callbacks you want. Anything you leave out costs nothing.

```lua
priority = 10   -- optional; higher runs first, ties break on filename

function OnRunScript(script_name, object_id, has_object, relevant)
    if script_name == "k_def_heartbeat01" then return false end
end
```

The trailing `relevant` argument always comes last, after every argument
the event declares. It is false when another script has already decided
the outcome.

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

#### `OnConsoleCommand(line, relevant)`

Called for every line typed into the cheat console, including lines the game does not recognise. Return false to consume the line so the game never sees it, which is how a script adds its own commands. The console hook receives one keystroke at a time and buffers to a line, so this fires on Enter.

| argument | type |
|---|---|
| `line` | string |

Returns: bool. If no script answers, the result is `true`. Returning false stops the game's own handler.

#### `OnRunScriptDone(script_name, object_id, ran, relevant)`

Called after an NWScript finishes. `ran` is the engine's own return value: true when the script loaded and ran with a balanced stack.

| argument | type |
|---|---|
| `script_name` | string |
| `object_id` | object |
| `ran` | bool |

Returns: nothing. 

#### `OnTick(tick, relevant)`

Called once per server frame. The highest-frequency callback: a script that does not define it pays nothing, one that does should keep the body short.

| argument | type |
|---|---|
| `tick` | int |

Returns: nothing. 

#### `OnRunScript(script_name, object_id, has_object, relevant)`

Return false to stop the game's own script running.

| argument | type |
|---|---|
| `script_name` | string |
| `object_id` | object |
| `has_object` | int |

Returns: bool. If no script answers, the result is `true`. Returning false stops the game's own handler.

#### `OnDialogConditional(script_name, speaker, relevant)`

Script slot: dialog node Active/StartingConditional resref. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `script_name` | string |
| `speaker` | object |

Returns: bool. If no script answers, the result is `true`. Returning false stops the game's own handler.

#### `OnCreaturePerception(creature, perceived, how, relevant)`

Object type: creature. Script slot: ScriptOnNotice. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `creature` | object |
| `perceived` | object |
| `how` | int |

Returns: bool. Returning false stops the game's own handler.

#### `OnCreatureSpellCastAt(creature, caster, spell_id, harmful, relevant)`

Object type: creature. Script slot: ScriptSpellAt. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `creature` | object |
| `caster` | object |
| `spell_id` | int |
| `harmful` | int |

Returns: bool. Returning false stops the game's own handler.

#### `OnCreatureDialogue(creature, speaker, listen_pattern, conversation, action_conv_flag, ignore_range, match_count, relevant)`

Object type: creature. Script slot: ScriptDialogue. Default script: k_hen_dialogue01.

| argument | type |
|---|---|
| `creature` | object |
| `speaker` | object |
| `listen_pattern` | int |
| `conversation` | string |
| `action_conv_flag` | int |
| `ignore_range` | int |
| `match_count` | int |

Returns: nothing. 

#### `OnCreatureUserDefined(creature, event_number, relevant)`

Object type: creature. Script slot: ScriptUserDefine. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `creature` | object |
| `event_number` | int |

Returns: bool. Returning false stops the game's own handler.

#### `OnCreatureInventoryDisturbed(creature, disturber, disturb_type, item, relevant)`

Object type: creature. Script slot: ScriptDisturbed. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `creature` | object |
| `disturber` | object |
| `disturb_type` | int |
| `item` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnCreaturePathBlocked(creature, blocker, relevant)`

Object type: creature. Script slot: ScriptOnBlocked. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `creature` | object |
| `blocker` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnCreatureAttacked(creature, attacker, relevant)`

Object type: creature. Script slot: ScriptAttacked. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `creature` | object |
| `attacker` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnCreatureHeartbeat(creature, relevant)`

Object type: creature. Script slot: ScriptHeartbeat. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `creature` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnCreatureSpawn(creature, relevant)`

Object type: creature. Script slot: ScriptSpawn. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `creature` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnCreatureDeath(creature, relevant)`

Object type: creature. Script slot: ScriptDeath. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `creature` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnCreatureEndCombatRound(creature, relevant)`

Object type: creature. Script slot: ScriptEndRound. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `creature` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnCreatureEndDialogue(creature, relevant)`

Object type: creature. Script slot: ScriptEndDialogue. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `creature` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnCreatureTimedEvent(creature, relevant)`

Object type: creature.

| argument | type |
|---|---|
| `creature` | object |

Returns: nothing. 

#### `OnCreatureApplyEffect(creature, relevant)`

Object type: creature.

| argument | type |
|---|---|
| `creature` | object |

Returns: nothing. 

#### `OnCreatureDestroy(creature, relevant)`

Object type: creature.

| argument | type |
|---|---|
| `creature` | object |

Returns: nothing. 

#### `OnCreatureBroadcastAOO(relevant)`

Object type: creature. Return false to stop the game's own script running.

Returns: bool. Returning false stops the game's own handler.

#### `OnCreatureControllerRumble(pattern, relevant)`

Object type: creature. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `pattern` | int |

Returns: bool. Returning false stops the game's own handler.

#### `OnModuleHeartbeat(calendar_day, time_of_day, relevant)`

Object type: module. Script slot: Mod_OnHeartbeat. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `calendar_day` | int |
| `time_of_day` | int |

Returns: bool. Returning false stops the game's own handler.

#### `OnModuleUserDefined(event_number, relevant)`

Object type: module. Script slot: Mod_OnUsrDefined. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `event_number` | int |

Returns: bool. Returning false stops the game's own handler.

#### `OnModuleLoad(relevant)`

Object type: module. Script slot: Mod_OnModLoad. Return false to stop the game's own script running.

Returns: bool. Returning false stops the game's own handler.

#### `OnModuleStart(relevant)`

Object type: module. Script slot: Mod_OnModStart. Return false to stop the game's own script running.

Returns: bool. Returning false stops the game's own handler.

#### `OnModulePlayerEnter(player, relevant)`

Object type: module. Script slot: Mod_OnClientEntr. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `player` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnModulePlayerExit(player, relevant)`

Object type: module. Script slot: Mod_OnClientLeav. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `player` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnModuleAcquireItem(item, previous_possessor, relevant)`

Object type: module. Script slot: Mod_OnAcquirItem. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `item` | object |
| `previous_possessor` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnModuleLoseItem(item, loser, relevant)`

Object type: module. Script slot: Mod_OnUnAqreItem. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `item` | object |
| `loser` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnModulePlayerDeath(player, relevant)`

Object type: module. Script slot: Mod_OnPlrDeath. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `player` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnModulePlayerDying(player, relevant)`

Object type: module. Script slot: Mod_OnPlrDying. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `player` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnModuleRespawnButtonPressed(player, relevant)`

Object type: module. Script slot: Mod_OnSpawnBtnDn. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `player` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnModulePlayerRest(player, rest_phase, relevant)`

Object type: module. Script slot: Mod_OnPlrRest. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `player` | object |
| `rest_phase` | int |

Returns: bool. Returning false stops the game's own handler.

#### `OnModulePlayerLevelUp(player, relevant)`

Object type: module. Script slot: Mod_OnPlrLvlUp. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `player` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnModuleEquipItem(item, relevant)`

Object type: module. Script slot: Mod_OnEquipItem. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `item` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnModuleDestroyPlayerCreature(creature, relevant)`

Object type: module.

| argument | type |
|---|---|
| `creature` | object |

Returns: nothing. 

#### `OnModuleTimedEvent(relevant)`

Object type: module.

Returns: nothing. 

#### `OnAreaHeartbeat(area, calendar_day, time_of_day, relevant)`

Object type: area. Script slot: OnHeartbeat. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `area` | object |
| `calendar_day` | int |
| `time_of_day` | int |

Returns: bool. Returning false stops the game's own handler.

#### `OnAreaUserDefined(area, event_number, relevant)`

Object type: area. Script slot: OnUserDefined. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `area` | object |
| `event_number` | int |

Returns: bool. Returning false stops the game's own handler.

#### `OnAreaEnter(area, entering, from_save_game, relevant)`

Object type: area. Script slot: OnEnter.

| argument | type |
|---|---|
| `area` | object |
| `entering` | object |
| `from_save_game` | int |

Returns: nothing. 

#### `OnAreaExit(area, leaving, relevant)`

Object type: area. Script slot: OnExit. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `area` | object |
| `leaving` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnDoorHeartbeat(door, calendar_day, time_of_day, relevant)`

Object type: door. Script slot: OnHeartbeat. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `door` | object |
| `calendar_day` | int |
| `time_of_day` | int |

Returns: bool. Returning false stops the game's own handler.

#### `OnDoorSpellCastAt(door, caster, spell_id, harmful, relevant)`

Object type: door. Script slot: OnSpellCastAt. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `door` | object |
| `caster` | object |
| `spell_id` | int |
| `harmful` | int |

Returns: bool. Returning false stops the game's own handler.

#### `OnDoorDialogue(door, speaker, listen_pattern, conversation, match_count, relevant)`

Object type: door. Script slot: OnDialog. Default script: k_hen_dialogue01.

| argument | type |
|---|---|
| `door` | object |
| `speaker` | object |
| `listen_pattern` | int |
| `conversation` | string |
| `match_count` | int |

Returns: nothing. 

#### `OnDoorDeath(door, killer, relevant)`

Object type: door. Script slot: OnDeath. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `door` | object |
| `killer` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnDoorUserDefined(door, event_number, relevant)`

Object type: door. Script slot: OnUserDefined. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `door` | object |
| `event_number` | int |

Returns: bool. Returning false stops the game's own handler.

#### `OnDoorDisarm(door, disarmer, relevant)`

Object type: door. Script slot: OnDisarm. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `door` | object |
| `disarmer` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnDoorTrapTriggered(door, triggerer, force, relevant)`

Object type: door. Script slot: OnTrapTriggered. Default script: traps.2da column MineScript for this door's TrapType. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `door` | object |
| `triggerer` | object |
| `force` | int |

Returns: bool. Returning false stops the game's own handler.

#### `OnDoorLocked(door, locker, relevant)`

Object type: door. Script slot: OnLock. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `door` | object |
| `locker` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnDoorUnlocked(door, unlocker, relevant)`

Object type: door. Script slot: OnUnlock. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `door` | object |
| `unlocker` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnDoorClicked(door, clicker, pending_id, relevant)`

Object type: door. Script slot: OnClick. Default script: NW_G0_Transition.

| argument | type |
|---|---|
| `door` | object |
| `clicker` | object |
| `pending_id` | int |

Returns: nothing. 

#### `OnDoorFailToOpen(door, opener, relevant)`

Object type: door. Script slot: OnFailToOpen. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `door` | object |
| `opener` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnDoorClose(door, closer, relevant)`

Object type: door. Script slot: OnClosed. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `door` | object |
| `closer` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnDoorAttacked(door, attacker, relevant)`

Object type: door. Script slot: OnMeleeAttacked. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `door` | object |
| `attacker` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnDoorDestroy(door, relevant)`

Object type: door.

| argument | type |
|---|---|
| `door` | object |

Returns: nothing. 

#### `OnPlaceableHeartbeat(placeable, calendar_day, time_of_day, relevant)`

Object type: placeable. Script slot: OnHeartbeat. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `placeable` | object |
| `calendar_day` | int |
| `time_of_day` | int |

Returns: bool. Returning false stops the game's own handler.

#### `OnPlaceableSpellCastAt(placeable, caster, spell_id, harmful, relevant)`

Object type: placeable. Script slot: OnSpellCastAt. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `placeable` | object |
| `caster` | object |
| `spell_id` | int |
| `harmful` | int |

Returns: bool. Returning false stops the game's own handler.

#### `OnPlaceableDialogue(placeable, speaker, listen_pattern, conversation, match_count, relevant)`

Object type: placeable. Script slot: OnDialog. Default script: k_hen_dialogue01.

| argument | type |
|---|---|
| `placeable` | object |
| `speaker` | object |
| `listen_pattern` | int |
| `conversation` | string |
| `match_count` | int |

Returns: nothing. 

#### `OnPlaceableDeath(placeable, killer, relevant)`

Object type: placeable. Script slot: OnDeath. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `placeable` | object |
| `killer` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnPlaceableUserDefined(placeable, event_number, relevant)`

Object type: placeable. Script slot: OnUserDefined. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `placeable` | object |
| `event_number` | int |

Returns: bool. Returning false stops the game's own handler.

#### `OnPlaceableOpen(placeable, opener, relevant)`

Object type: placeable. Script slot: OnOpen. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `placeable` | object |
| `opener` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnPlaceableClose(placeable, closer, relevant)`

Object type: placeable. Script slot: OnClosed. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `placeable` | object |
| `closer` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnPlaceableDisarm(placeable, disarmer, relevant)`

Object type: placeable. Script slot: OnDisarm. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `placeable` | object |
| `disarmer` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnPlaceableUsed(placeable, user, relevant)`

Object type: placeable. Script slot: OnUsed. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `placeable` | object |
| `user` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnPlaceableTrapTriggered(placeable, triggerer, force, relevant)`

Object type: placeable. Script slot: OnTrapTriggered. Default script: traps.2da column MineScript for this placeable's TrapType. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `placeable` | object |
| `triggerer` | object |
| `force` | int |

Returns: bool. Returning false stops the game's own handler.

#### `OnPlaceableInventoryDisturbed(placeable, disturber, disturb_type, item, relevant)`

Object type: placeable. Script slot: OnInvDisturbed. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `placeable` | object |
| `disturber` | object |
| `disturb_type` | int |
| `item` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnPlaceableLocked(placeable, locker, relevant)`

Object type: placeable. Script slot: OnLock. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `placeable` | object |
| `locker` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnPlaceableUnlocked(placeable, unlocker, relevant)`

Object type: placeable. Script slot: OnUnlock. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `placeable` | object |
| `unlocker` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnPlaceableAttacked(placeable, attacker, relevant)`

Object type: placeable. Script slot: OnMeleeAttacked. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `placeable` | object |
| `attacker` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnPlaceableAcquireItem(placeable, item, relevant)`

Object type: placeable.

| argument | type |
|---|---|
| `placeable` | object |
| `item` | object |

Returns: nothing. 

#### `OnTriggerEnter(trigger, entering, int0, relevant)`

Object type: trigger. Script slot: ScriptOnEnter.

| argument | type |
|---|---|
| `trigger` | object |
| `entering` | object |
| `int0` | int |

Returns: nothing. 

#### `OnTriggerExit(trigger, leaving, relevant)`

Object type: trigger. Script slot: ScriptOnExit. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `trigger` | object |
| `leaving` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnTriggerUserDefined(trigger, event_number, relevant)`

Object type: trigger. Script slot: ScriptUserDefine. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `trigger` | object |
| `event_number` | int |

Returns: bool. Returning false stops the game's own handler.

#### `OnTriggerDisarm(trigger, disarmer, relevant)`

Object type: trigger. Script slot: OnDisarm. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `trigger` | object |
| `disarmer` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnTriggerClicked(trigger, clicker, relevant)`

Object type: trigger. Script slot: OnClick. Default script: NW_G0_Transition. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `trigger` | object |
| `clicker` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnTriggerDestroy(trigger, relevant)`

Object type: trigger.

| argument | type |
|---|---|
| `trigger` | object |

Returns: nothing. 

#### `OnEncounterHeartbeat(encounter, relevant)`

Object type: encounter. Script slot: OnHeartbeat. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `encounter` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnEncounterEnter(encounter, entering, relevant)`

Object type: encounter. Script slot: OnEntered.

| argument | type |
|---|---|
| `encounter` | object |
| `entering` | object |

Returns: nothing. 

#### `OnEncounterExit(encounter, leaving, relevant)`

Object type: encounter. Script slot: OnExit.

| argument | type |
|---|---|
| `encounter` | object |
| `leaving` | object |

Returns: nothing. 

#### `OnEncounterExhausted(encounter, relevant)`

Object type: encounter. Script slot: OnExhausted. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `encounter` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnEncounterUserDefined(encounter, event_number, relevant)`

Object type: encounter. Script slot: OnUserDefined. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `encounter` | object |
| `event_number` | int |

Returns: bool. Returning false stops the game's own handler.

#### `OnAoeEnter(aoe, entering, relevant)`

Object type: aoe. Script slot: OnEnter (named member script_on_enter). Return false to stop the game's own script running.

| argument | type |
|---|---|
| `aoe` | object |
| `entering` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnAoeExit(aoe, leaving, relevant)`

Object type: aoe. Script slot: OnExit (named member script_on_exit). Return false to stop the game's own script running.

| argument | type |
|---|---|
| `aoe` | object |
| `leaving` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnStoreOpen(store, opener, relevant)`

Object type: store. Script slot: OnOpenStore. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `store` | object |
| `opener` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnWaypointDestroy(waypoint, relevant)`

Object type: waypoint.

| argument | type |
|---|---|
| `waypoint` | object |

Returns: nothing. 

#### `OnAreaTransitionFail(creature, relevant)`

Script slot: hardcoded. Default script: k_trg_transfail. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `creature` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnItemUse(object, relevant)`

Script slot: hardcoded. Default script: itemuse. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `object` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnClientRequestedScript(script_name, creature, relevant)`

Object type: creature. Script slot: arbitrary, supplied by the client message. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `script_name` | string |
| `creature` | object |

Returns: bool. Returning false stops the game's own handler.

### Medium confidence

Argument mapping is partly verified. Check before relying on it.

#### `OnSave(relevant)`

Return a string to persist alongside the save. It comes back to OnLoad when that save is loaded.

Returns: string. 

#### `OnLoad(state, relevant)`

Receives whatever OnSave returned when this save was written.

| argument | type |
|---|---|
| `state` | string |

Returns: nothing. 

#### `OnCreatureDamaged(creature, relevant)`

Object type: creature. Script slot: ScriptDamaged. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `creature` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnCreatureRemoveEffect(creature, effect_id, relevant)`

Object type: creature.

| argument | type |
|---|---|
| `creature` | object |
| `effect_id` | int |

Returns: nothing. 

#### `OnCreatureRemoveFromArea(creature, flag, relevant)`

Object type: creature.

| argument | type |
|---|---|
| `creature` | object |
| `flag` | int |

Returns: nothing. 

#### `OnCreaturePlayAnimation(creature, animation, relevant)`

Object type: creature.

| argument | type |
|---|---|
| `creature` | object |
| `animation` | int |

Returns: nothing. 

#### `OnCreatureSpellImpact(creature, caster, relevant)`

Object type: creature. Script slot: spell impact script, carried in the event payload. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `creature` | object |
| `caster` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnCreatureItemOnHitSpellImpact(creature, caster, relevant)`

Object type: creature. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `creature` | object |
| `caster` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnCreatureForcedAction(creature, relevant)`

Object type: creature.

| argument | type |
|---|---|
| `creature` | object |

Returns: nothing. 

#### `OnCreatureBroadcastSafeProjectile(creature, attacker, relevant)`

Object type: creature.

| argument | type |
|---|---|
| `creature` | object |
| `attacker` | object |

Returns: nothing. 

#### `OnCreatureFeedbackMessage(creature, other, message_kind, message_id, relevant)`

Object type: creature.

| argument | type |
|---|---|
| `creature` | object |
| `other` | object |
| `message_kind` | int |
| `message_id` | int |

Returns: nothing. 

#### `OnModuleActivateItem(item, activator, target, obj_param_3, target_x, target_y, target_z, relevant)`

Object type: module. Script slot: Mod_OnActvtItem. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `item` | object |
| `activator` | object |
| `target` | object |
| `obj_param_3` | object |
| `target_x` | float |
| `target_y` | float |
| `target_z` | float |

Returns: bool. Returning false stops the game's own handler.

#### `OnAreaSpawnBodyBag(area, bag_id, relevant)`

Object type: area.

| argument | type |
|---|---|
| `area` | object |
| `bag_id` | object |

Returns: nothing. 

#### `OnDoorDamaged(door, damager, amount, relevant)`

Object type: door. Script slot: OnDamaged. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `door` | object |
| `damager` | object |
| `amount` | int |

Returns: bool. Returning false stops the game's own handler.

#### `OnDoorOpen(door, opener, relevant)`

Object type: door. Script slot: OnOpen. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `door` | object |
| `opener` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnPlaceableDamaged(placeable, damager, amount, relevant)`

Object type: placeable. Script slot: OnDamaged. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `placeable` | object |
| `damager` | object |
| `amount` | int |

Returns: bool. Returning false stops the game's own handler.

#### `OnPlaceableEndDialogue(placeable, relevant)`

Object type: placeable. Script slot: OnEndDialogue. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `placeable` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnTriggerTrapTriggered(trigger, relevant)`

Object type: trigger. Script slot: OnTrapTriggered. Default script: traps.2da column MineScript. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `trigger` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnTriggerHeartbeat(trigger, relevant)`

Object type: trigger. Script slot: ScriptHeartbeat. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `trigger` | object |

Returns: bool. Returning false stops the game's own handler.

#### `OnCreatureStateScript(creature, state, relevant)`

Object type: creature. Script slot: statescripts.2da column SCRIPTNAME. Return false to stop the game's own script running.

| argument | type |
|---|---|
| `creature` | object |
| `state` | int |

Returns: bool. Returning false stops the game's own handler.

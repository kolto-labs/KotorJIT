# Lua API reference

Generated from `data/events.toml`. Do not edit by hand.

## How to write a script

Native registration uses `kp.events.register(kp.events.OnTick, handler)`. The global On* definitions below remain supported as legacy dispatcher discovery. Explicit bindings take precedence; `kp.events.unregister` restores a discovered global handler. See [the namespace migration](api-dialects.md).

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

| argument | type | source |
|---|---|---|
| `game` | string |  |
| `build` | string |  |

Returns: nothing. 

#### `OnScriptUnload(relevant)`

Called before the script is unloaded, including on reload and on quarantine.

Returns: nothing. 

#### `OnConsoleCommand(line, relevant)`

Called for every line typed into the cheat console, including lines the game does not recognise. Return false to consume the line so the game never sees it, which is how a script adds its own commands. The console hook receives one keystroke at a time and buffers to a line, so this fires on Enter.

| argument | type | source |
|---|---|---|
| `line` | string |  |

Returns: bool. If no script answers, the result is `true`. Returning false stops the game's own handler.

#### `OnRunScriptDone(script_name, object_id, ran, relevant)`

Called after an NWScript finishes. `ran` is the engine's own return value: true when the script loaded and ran with a balanced stack.

| argument | type | source |
|---|---|---|
| `script_name` | string |  |
| `object_id` | object |  |
| `ran` | bool |  |

Returns: nothing. 

#### `OnTick(tick, relevant)`

Called once per server frame. The highest-frequency callback: a script that does not define it pays nothing, one that does should keep the body short.

| argument | type | source |
|---|---|---|
| `tick` | int |  |

Returns: nothing. 

#### `OnRunScript(script_name, object_id, has_object, relevant)`

Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `script_name` | string | arg1 CExoString* |
| `object_id` | object | arg2 ulong |
| `has_object` | int | arg3 int |

Returns: bool. If no script answers, the result is `true`. Returning false stops the game's own handler.

#### `OnDialogConditional(script_name, speaker, relevant)`

Script slot: dialog node Active/StartingConditional resref. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `script_name` | string | CResRef* arg2 |
| `speaker` | object | CWSObject* arg1 |

Returns: bool. If no script answers, the result is `true`. Returning false stops the game's own handler.

#### `OnCreaturePerception(creature, perceived, how, relevant)`

Object type: creature. Script slot: ScriptOnNotice. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `creature` | object | this |
| `perceived` | object | object_params[0] |
| `how` | int | int_params[0] |

Returns: bool. Returning false stops the game's own handler.

#### `OnCreatureSpellCastAt(creature, caster, spell_id, harmful, relevant)`

Object type: creature. Script slot: ScriptSpellAt. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `creature` | object | this |
| `caster` | object | object_params[0] |
| `spell_id` | int | int_params[0] |
| `harmful` | int | int_params[1] |

Returns: bool. Returning false stops the game's own handler.

#### `OnCreatureDialogue(creature, speaker, listen_pattern, conversation, action_conv_flag, ignore_range, match_count, relevant)`

Object type: creature. Script slot: ScriptDialogue. Default script: k_hen_dialogue01.

| argument | type | source |
|---|---|---|
| `creature` | object | this |
| `speaker` | object | caller |
| `listen_pattern` | int | int_params[1] |
| `conversation` | string | string_params[0] |
| `action_conv_flag` | int | int_params[2] |
| `ignore_range` | int | int_params[3] |
| `match_count` | int | int_params[0] |

Returns: nothing. 

#### `OnCreatureUserDefined(creature, event_number, relevant)`

Object type: creature. Script slot: ScriptUserDefine. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `creature` | object | this |
| `event_number` | int | int_params[0] |

Returns: bool. Returning false stops the game's own handler.

#### `OnCreatureInventoryDisturbed(creature, disturber, disturb_type, item, relevant)`

Object type: creature. Script slot: ScriptDisturbed. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `creature` | object | this |
| `disturber` | object | caller |
| `disturb_type` | int | int_params[0] |
| `item` | object | object_params[0] |

Returns: bool. Returning false stops the game's own handler.

#### `OnCreaturePathBlocked(creature, blocker, relevant)`

Object type: creature. Script slot: ScriptOnBlocked. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `creature` | object | this |
| `blocker` | object | caller |

Returns: bool. Returning false stops the game's own handler.

#### `OnCreatureAttacked(creature, attacker, relevant)`

Object type: creature. Script slot: ScriptAttacked. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `creature` | object | this |
| `attacker` | object | caller |

Returns: bool. Returning false stops the game's own handler.

#### `OnCreatureHeartbeat(creature, relevant)`

Object type: creature. Script slot: ScriptHeartbeat. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `creature` | object | this |

Returns: bool. Returning false stops the game's own handler.

#### `OnCreatureSpawn(creature, relevant)`

Object type: creature. Script slot: ScriptSpawn. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `creature` | object | this |

Returns: bool. Returning false stops the game's own handler.

#### `OnCreatureDeath(creature, relevant)`

Object type: creature. Script slot: ScriptDeath. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `creature` | object | this |

Returns: bool. Returning false stops the game's own handler.

#### `OnCreatureEndCombatRound(creature, relevant)`

Object type: creature. Script slot: ScriptEndRound. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `creature` | object | this |

Returns: bool. Returning false stops the game's own handler.

#### `OnCreatureEndDialogue(creature, relevant)`

Object type: creature. Script slot: ScriptEndDialogue. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `creature` | object | this |

Returns: bool. Returning false stops the game's own handler.

#### `OnCreatureTimedEvent(creature, relevant)`

Object type: creature.

| argument | type | source |
|---|---|---|
| `creature` | object | this |

Returns: nothing. 

#### `OnCreatureApplyEffect(creature, relevant)`

Object type: creature.

| argument | type | source |
|---|---|---|
| `creature` | object | this |

Returns: nothing. 

#### `OnCreatureDestroy(creature, relevant)`

Object type: creature.

| argument | type | source |
|---|---|---|
| `creature` | object | this |

Returns: nothing. 

#### `OnCreatureBroadcastAOO(relevant)`

Object type: creature. Return false to stop the game's own script running.

Returns: bool. Returning false stops the game's own handler.

#### `OnCreatureControllerRumble(pattern, relevant)`

Object type: creature. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `pattern` | int | arg3 (immediate) |

Returns: bool. Returning false stops the game's own handler.

#### `OnModuleHeartbeat(calendar_day, time_of_day, relevant)`

Object type: module. Script slot: Mod_OnHeartbeat. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `calendar_day` | int | calendar_day |
| `time_of_day` | int | time_of_day |

Returns: bool. Returning false stops the game's own handler.

#### `OnModuleUserDefined(event_number, relevant)`

Object type: module. Script slot: Mod_OnUsrDefined. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `event_number` | int | int_params[0] |

Returns: bool. Returning false stops the game's own handler.

#### `OnModuleLoad(relevant)`

Object type: module. Script slot: Mod_OnModLoad. Return false to stop the game's own script running.

Returns: bool. Returning false stops the game's own handler.

#### `OnModuleStart(relevant)`

Object type: module. Script slot: Mod_OnModStart. Return false to stop the game's own script running.

Returns: bool. Returning false stops the game's own handler.

#### `OnModulePlayerEnter(player, relevant)`

Object type: module. Script slot: Mod_OnClientEntr. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `player` | object | object_params[0] |

Returns: bool. Returning false stops the game's own handler.

#### `OnModulePlayerExit(player, relevant)`

Object type: module. Script slot: Mod_OnClientLeav. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `player` | object | object_params[0] |

Returns: bool. Returning false stops the game's own handler.

#### `OnModuleAcquireItem(item, previous_possessor, relevant)`

Object type: module. Script slot: Mod_OnAcquirItem. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `item` | object | object_params[0] |
| `previous_possessor` | object | object_params[1] |

Returns: bool. Returning false stops the game's own handler.

#### `OnModuleLoseItem(item, loser, relevant)`

Object type: module. Script slot: Mod_OnUnAqreItem. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `item` | object | object_params[0] |
| `loser` | object | caller |

Returns: bool. Returning false stops the game's own handler.

#### `OnModulePlayerDeath(player, relevant)`

Object type: module. Script slot: Mod_OnPlrDeath. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `player` | object | caller |

Returns: bool. Returning false stops the game's own handler.

#### `OnModulePlayerDying(player, relevant)`

Object type: module. Script slot: Mod_OnPlrDying. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `player` | object | caller |

Returns: bool. Returning false stops the game's own handler.

#### `OnModuleRespawnButtonPressed(player, relevant)`

Object type: module. Script slot: Mod_OnSpawnBtnDn. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `player` | object | caller |

Returns: bool. Returning false stops the game's own handler.

#### `OnModulePlayerRest(player, rest_phase, relevant)`

Object type: module. Script slot: Mod_OnPlrRest. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `player` | object | caller |
| `rest_phase` | int | int_params[0] |

Returns: bool. Returning false stops the game's own handler.

#### `OnModulePlayerLevelUp(player, relevant)`

Object type: module. Script slot: Mod_OnPlrLvlUp. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `player` | object | caller |

Returns: bool. Returning false stops the game's own handler.

#### `OnModuleEquipItem(item, relevant)`

Object type: module. Script slot: Mod_OnEquipItem. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `item` | object | object_params[0] |

Returns: bool. Returning false stops the game's own handler.

#### `OnModuleDestroyPlayerCreature(creature, relevant)`

Object type: module.

| argument | type | source |
|---|---|---|
| `creature` | object | caller |

Returns: nothing. 

#### `OnModuleTimedEvent(relevant)`

Object type: module.

Returns: nothing. 

#### `OnAreaHeartbeat(area, calendar_day, time_of_day, relevant)`

Object type: area. Script slot: OnHeartbeat. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `area` | object | this |
| `calendar_day` | int | calendar_day |
| `time_of_day` | int | time_of_day |

Returns: bool. Returning false stops the game's own handler.

#### `OnAreaUserDefined(area, event_number, relevant)`

Object type: area. Script slot: OnUserDefined. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `area` | object | this |
| `event_number` | int | int_params[0] |

Returns: bool. Returning false stops the game's own handler.

#### `OnAreaEnter(area, entering, from_save_game, relevant)`

Object type: area. Script slot: OnEnter.

| argument | type | source |
|---|---|---|
| `area` | object | this |
| `entering` | object | caller |
| `from_save_game` | int | int_params[0] |

Returns: nothing. 

#### `OnAreaExit(area, leaving, relevant)`

Object type: area. Script slot: OnExit. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `area` | object | this |
| `leaving` | object | caller |

Returns: bool. Returning false stops the game's own handler.

#### `OnDoorHeartbeat(door, calendar_day, time_of_day, relevant)`

Object type: door. Script slot: OnHeartbeat. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `door` | object | this |
| `calendar_day` | int | calendar_day |
| `time_of_day` | int | time_of_day |

Returns: bool. Returning false stops the game's own handler.

#### `OnDoorSpellCastAt(door, caster, spell_id, harmful, relevant)`

Object type: door. Script slot: OnSpellCastAt. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `door` | object | this |
| `caster` | object | object_params[0] |
| `spell_id` | int | int_params[0] |
| `harmful` | int | int_params[1] |

Returns: bool. Returning false stops the game's own handler.

#### `OnDoorDialogue(door, speaker, listen_pattern, conversation, match_count, relevant)`

Object type: door. Script slot: OnDialog. Default script: k_hen_dialogue01.

| argument | type | source |
|---|---|---|
| `door` | object | this |
| `speaker` | object | caller |
| `listen_pattern` | int | int_params[1] |
| `conversation` | string | string_params[0] |
| `match_count` | int | int_params[0] |

Returns: nothing. 

#### `OnDoorDeath(door, killer, relevant)`

Object type: door. Script slot: OnDeath. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `door` | object | this |
| `killer` | object | caller |

Returns: bool. Returning false stops the game's own handler.

#### `OnDoorUserDefined(door, event_number, relevant)`

Object type: door. Script slot: OnUserDefined. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `door` | object | this |
| `event_number` | int | int_params[0] |

Returns: bool. Returning false stops the game's own handler.

#### `OnDoorDisarm(door, disarmer, relevant)`

Object type: door. Script slot: OnDisarm. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `door` | object | this |
| `disarmer` | object | caller |

Returns: bool. Returning false stops the game's own handler.

#### `OnDoorTrapTriggered(door, triggerer, force, relevant)`

Object type: door. Script slot: OnTrapTriggered. Default script: traps.2da column MineScript for this door's TrapType. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `door` | object | this |
| `triggerer` | object | caller |
| `force` | int | int_params[0] |

Returns: bool. Returning false stops the game's own handler.

#### `OnDoorLocked(door, locker, relevant)`

Object type: door. Script slot: OnLock. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `door` | object | this |
| `locker` | object | caller |

Returns: bool. Returning false stops the game's own handler.

#### `OnDoorUnlocked(door, unlocker, relevant)`

Object type: door. Script slot: OnUnlock. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `door` | object | this |
| `unlocker` | object | caller |

Returns: bool. Returning false stops the game's own handler.

#### `OnDoorClicked(door, clicker, pending_id, relevant)`

Object type: door. Script slot: OnClick. Default script: NW_G0_Transition.

| argument | type | source |
|---|---|---|
| `door` | object | this |
| `clicker` | object | object_params[0] |
| `pending_id` | int | int_params[0] |

Returns: nothing. 

#### `OnDoorFailToOpen(door, opener, relevant)`

Object type: door. Script slot: OnFailToOpen. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `door` | object | this |
| `opener` | object | caller |

Returns: bool. Returning false stops the game's own handler.

#### `OnDoorClose(door, closer, relevant)`

Object type: door. Script slot: OnClosed. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `door` | object | this |
| `closer` | object | caller |

Returns: bool. Returning false stops the game's own handler.

#### `OnDoorAttacked(door, attacker, relevant)`

Object type: door. Script slot: OnMeleeAttacked. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `door` | object | this |
| `attacker` | object | caller |

Returns: bool. Returning false stops the game's own handler.

#### `OnDoorDestroy(door, relevant)`

Object type: door.

| argument | type | source |
|---|---|---|
| `door` | object | this |

Returns: nothing. 

#### `OnPlaceableHeartbeat(placeable, calendar_day, time_of_day, relevant)`

Object type: placeable. Script slot: OnHeartbeat. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `placeable` | object | this |
| `calendar_day` | int | calendar_day |
| `time_of_day` | int | time_of_day |

Returns: bool. Returning false stops the game's own handler.

#### `OnPlaceableSpellCastAt(placeable, caster, spell_id, harmful, relevant)`

Object type: placeable. Script slot: OnSpellCastAt. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `placeable` | object | this |
| `caster` | object | object_params[0] |
| `spell_id` | int | int_params[0] |
| `harmful` | int | int_params[1] |

Returns: bool. Returning false stops the game's own handler.

#### `OnPlaceableDialogue(placeable, speaker, listen_pattern, conversation, match_count, relevant)`

Object type: placeable. Script slot: OnDialog. Default script: k_hen_dialogue01.

| argument | type | source |
|---|---|---|
| `placeable` | object | this |
| `speaker` | object | caller |
| `listen_pattern` | int | int_params[1] |
| `conversation` | string | string_params[0] |
| `match_count` | int | int_params[0] |

Returns: nothing. 

#### `OnPlaceableDeath(placeable, killer, relevant)`

Object type: placeable. Script slot: OnDeath. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `placeable` | object | this |
| `killer` | object | caller |

Returns: bool. Returning false stops the game's own handler.

#### `OnPlaceableUserDefined(placeable, event_number, relevant)`

Object type: placeable. Script slot: OnUserDefined. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `placeable` | object | this |
| `event_number` | int | int_params[0] |

Returns: bool. Returning false stops the game's own handler.

#### `OnPlaceableOpen(placeable, opener, relevant)`

Object type: placeable. Script slot: OnOpen. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `placeable` | object | this |
| `opener` | object | caller |

Returns: bool. Returning false stops the game's own handler.

#### `OnPlaceableClose(placeable, closer, relevant)`

Object type: placeable. Script slot: OnClosed. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `placeable` | object | this |
| `closer` | object | caller |

Returns: bool. Returning false stops the game's own handler.

#### `OnPlaceableDisarm(placeable, disarmer, relevant)`

Object type: placeable. Script slot: OnDisarm. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `placeable` | object | this |
| `disarmer` | object | caller |

Returns: bool. Returning false stops the game's own handler.

#### `OnPlaceableUsed(placeable, user, relevant)`

Object type: placeable. Script slot: OnUsed. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `placeable` | object | this |
| `user` | object | caller |

Returns: bool. Returning false stops the game's own handler.

#### `OnPlaceableTrapTriggered(placeable, triggerer, force, relevant)`

Object type: placeable. Script slot: OnTrapTriggered. Default script: traps.2da column MineScript for this placeable's TrapType. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `placeable` | object | this |
| `triggerer` | object | caller |
| `force` | int | int_params[0] |

Returns: bool. Returning false stops the game's own handler.

#### `OnPlaceableInventoryDisturbed(placeable, disturber, disturb_type, item, relevant)`

Object type: placeable. Script slot: OnInvDisturbed. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `placeable` | object | this |
| `disturber` | object | caller |
| `disturb_type` | int | int_params[0] |
| `item` | object | object_params[0] |

Returns: bool. Returning false stops the game's own handler.

#### `OnPlaceableLocked(placeable, locker, relevant)`

Object type: placeable. Script slot: OnLock. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `placeable` | object | this |
| `locker` | object | caller |

Returns: bool. Returning false stops the game's own handler.

#### `OnPlaceableUnlocked(placeable, unlocker, relevant)`

Object type: placeable. Script slot: OnUnlock. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `placeable` | object | this |
| `unlocker` | object | caller |

Returns: bool. Returning false stops the game's own handler.

#### `OnPlaceableAttacked(placeable, attacker, relevant)`

Object type: placeable. Script slot: OnMeleeAttacked. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `placeable` | object | this |
| `attacker` | object | caller |

Returns: bool. Returning false stops the game's own handler.

#### `OnPlaceableAcquireItem(placeable, item, relevant)`

Object type: placeable.

| argument | type | source |
|---|---|---|
| `placeable` | object | this |
| `item` | object | caller |

Returns: nothing. 

#### `OnTriggerEnter(trigger, entering, int0, relevant)`

Object type: trigger. Script slot: ScriptOnEnter.

| argument | type | source |
|---|---|---|
| `trigger` | object | this |
| `entering` | object | object_params[0] |
| `int0` | int | int_params[0] |

Returns: nothing. 

#### `OnTriggerExit(trigger, leaving, relevant)`

Object type: trigger. Script slot: ScriptOnExit. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `trigger` | object | this |
| `leaving` | object | object_params[0] |

Returns: bool. Returning false stops the game's own handler.

#### `OnTriggerUserDefined(trigger, event_number, relevant)`

Object type: trigger. Script slot: ScriptUserDefine. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `trigger` | object | this |
| `event_number` | int | int_params[0] |

Returns: bool. Returning false stops the game's own handler.

#### `OnTriggerDisarm(trigger, disarmer, relevant)`

Object type: trigger. Script slot: OnDisarm. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `trigger` | object | this |
| `disarmer` | object | caller |

Returns: bool. Returning false stops the game's own handler.

#### `OnTriggerClicked(trigger, clicker, relevant)`

Object type: trigger. Script slot: OnClick. Default script: NW_G0_Transition. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `trigger` | object | this |
| `clicker` | object | object_params[0] |

Returns: bool. Returning false stops the game's own handler.

#### `OnTriggerDestroy(trigger, relevant)`

Object type: trigger.

| argument | type | source |
|---|---|---|
| `trigger` | object | this |

Returns: nothing. 

#### `OnEncounterHeartbeat(encounter, relevant)`

Object type: encounter. Script slot: OnHeartbeat. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `encounter` | object | this |

Returns: bool. Returning false stops the game's own handler.

#### `OnEncounterEnter(encounter, entering, relevant)`

Object type: encounter. Script slot: OnEntered.

| argument | type | source |
|---|---|---|
| `encounter` | object | this |
| `entering` | object | object_params[0] |

Returns: nothing. 

#### `OnEncounterExit(encounter, leaving, relevant)`

Object type: encounter. Script slot: OnExit.

| argument | type | source |
|---|---|---|
| `encounter` | object | this |
| `leaving` | object | object_params[0] |

Returns: nothing. 

#### `OnEncounterExhausted(encounter, relevant)`

Object type: encounter. Script slot: OnExhausted. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `encounter` | object | this |

Returns: bool. Returning false stops the game's own handler.

#### `OnEncounterUserDefined(encounter, event_number, relevant)`

Object type: encounter. Script slot: OnUserDefined. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `encounter` | object | this |
| `event_number` | int | int_params[0] |

Returns: bool. Returning false stops the game's own handler.

#### `OnAoeEnter(aoe, entering, relevant)`

Object type: aoe. Script slot: OnEnter (named member script_on_enter). Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `aoe` | object | this |
| `entering` | object | object_params[0] |

Returns: bool. Returning false stops the game's own handler.

#### `OnAoeExit(aoe, leaving, relevant)`

Object type: aoe. Script slot: OnExit (named member script_on_exit). Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `aoe` | object | this |
| `leaving` | object | object_params[0] |

Returns: bool. Returning false stops the game's own handler.

#### `OnStoreOpen(store, opener, relevant)`

Object type: store. Script slot: OnOpenStore. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `store` | object | this |
| `opener` | object | caller |

Returns: bool. Returning false stops the game's own handler.

#### `OnWaypointDestroy(waypoint, relevant)`

Object type: waypoint.

| argument | type | source |
|---|---|---|
| `waypoint` | object | this |

Returns: nothing. 

#### `OnAreaTransitionFail(creature, relevant)`

Script slot: hardcoded. Default script: k_trg_transfail. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `creature` | object | the creature that tried to transition |

Returns: bool. Returning false stops the game's own handler.

#### `OnItemUse(object, relevant)`

Script slot: hardcoded. Default script: itemuse. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `object` | object | object id read from the client message |

Returns: bool. Returning false stops the game's own handler.

#### `OnClientRequestedScript(script_name, creature, relevant)`

Object type: creature. Script slot: arbitrary, supplied by the client message. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `script_name` | string | CExoString read from the message, max 0x20 |
| `creature` | object | the sending player's creature |

Returns: bool. Returning false stops the game's own handler.

#### `OnScriptSituation(object, has_object, relevant)`

Delayed/assigned script closure (DelayCommand/AssignCommand) is about to resume. Return false to cancel execution.

| argument | type | source |
|---|---|---|
| `object` | object | arg2 ulong |
| `has_object` | int | arg3 int |

Returns: bool. If no script answers, the result is `true`. Returning false stops the game's own handler.

#### `OnPlayerSpawn(player, relevant)`

Player creature spawned or entered module control.

| argument | type | source |
|---|---|---|
| `player` | object | player creature object id |

Returns: nothing. 

### Medium confidence

Argument mapping is partly verified. Check before relying on it.

#### `OnSave(relevant)`

Return a string to persist alongside the save. It comes back to OnLoad when that save is loaded.

Returns: string. 

#### `OnLoad(state, relevant)`

Receives whatever OnSave returned when this save was written.

| argument | type | source |
|---|---|---|
| `state` | string |  |

Returns: nothing. 

#### `OnCreatureDamaged(creature, relevant)`

Object type: creature. Script slot: ScriptDamaged. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `creature` | object | this |

Returns: bool. Returning false stops the game's own handler.

#### `OnCreatureRemoveEffect(creature, effect_id, relevant)`

Object type: creature.

| argument | type | source |
|---|---|---|
| `creature` | object | this |
| `effect_id` | int | arg3, reinterpreted as the effect's 64-bit id |

Returns: nothing. 

#### `OnCreatureRemoveFromArea(creature, flag, relevant)`

Object type: creature.

| argument | type | source |
|---|---|---|
| `creature` | object | this |
| `flag` | int | arg3 (used as an int, not a pointer) |

Returns: nothing. 

#### `OnCreaturePlayAnimation(creature, animation, relevant)`

Object type: creature.

| argument | type | source |
|---|---|---|
| `creature` | object | this |
| `animation` | int | arg3 (used as an immediate) |

Returns: nothing. 

#### `OnCreatureSpellImpact(creature, caster, relevant)`

Object type: creature. Script slot: spell impact script, carried in the event payload. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `creature` | object | this |
| `caster` | object | caller |

Returns: bool. Returning false stops the game's own handler.

#### `OnCreatureItemOnHitSpellImpact(creature, caster, relevant)`

Object type: creature. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `creature` | object | this |
| `caster` | object | caller |

Returns: bool. Returning false stops the game's own handler.

#### `OnCreatureForcedAction(creature, relevant)`

Object type: creature.

| argument | type | source |
|---|---|---|
| `creature` | object | this |

Returns: nothing. 

#### `OnCreatureBroadcastSafeProjectile(creature, attacker, relevant)`

Object type: creature.

| argument | type | source |
|---|---|---|
| `creature` | object | this |
| `attacker` | object | caller |

Returns: nothing. 

#### `OnCreatureFeedbackMessage(creature, other, message_kind, message_id, relevant)`

Object type: creature.

| argument | type | source |
|---|---|---|
| `creature` | object | this |
| `other` | object | caller |
| `message_kind` | int | first byte of arg3 |
| `message_id` | int | message_data int_params[0] |

Returns: nothing. 

#### `OnModuleActivateItem(item, activator, target, obj_param_3, target_x, target_y, target_z, relevant)`

Object type: module. Script slot: Mod_OnActvtItem. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `item` | object | object_params[0] |
| `activator` | object | object_params[1] |
| `target` | object | object_params[2] |
| `obj_param_3` | object | object_params[3] |
| `target_x` | float | float_params[0] |
| `target_y` | float | float_params[1] |
| `target_z` | float | float_params[2] |

Returns: bool. Returning false stops the game's own handler.

#### `OnAreaSpawnBodyBag(area, bag_id, relevant)`

Object type: area.

| argument | type | source |
|---|---|---|
| `area` | object | this |
| `bag_id` | object | arg3 first dword |

Returns: nothing. 

#### `OnDoorDamaged(door, damager, amount, relevant)`

Object type: door. Script slot: OnDamaged. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `door` | object | this |
| `damager` | object | caller |
| `amount` | int | int_params[0] |

Returns: bool. Returning false stops the game's own handler.

#### `OnDoorOpen(door, opener, relevant)`

Object type: door. Script slot: OnOpen. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `door` | object | this |
| `opener` | object | caller |

Returns: bool. Returning false stops the game's own handler.

#### `OnPlaceableDamaged(placeable, damager, amount, relevant)`

Object type: placeable. Script slot: OnDamaged. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `placeable` | object | this |
| `damager` | object | caller |
| `amount` | int | int_params[0] |

Returns: bool. Returning false stops the game's own handler.

#### `OnPlaceableEndDialogue(placeable, relevant)`

Object type: placeable. Script slot: OnEndDialogue. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `placeable` | object | this |

Returns: bool. Returning false stops the game's own handler.

#### `OnTriggerTrapTriggered(trigger, relevant)`

Object type: trigger. Script slot: OnTrapTriggered. Default script: traps.2da column MineScript. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `trigger` | object | this |

Returns: bool. Returning false stops the game's own handler.

#### `OnTriggerHeartbeat(trigger, relevant)`

Object type: trigger. Script slot: ScriptHeartbeat. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `trigger` | object | this |

Returns: bool. Returning false stops the game's own handler.

#### `OnCreatureStateScript(creature, state, relevant)`

Object type: creature. Script slot: statescripts.2da column SCRIPTNAME. Return false to stop the game's own script running.

| argument | type | source |
|---|---|---|
| `creature` | object | this |
| `state` | int | creature field_0x8ed |

Returns: bool. Returning false stops the game's own handler.

## Native camera (`kp.camera`)

Status: host-tested, K1 GOG only, no live proof yet. Read-only; nothing here writes game memory.

Tests ran against synthetic memory (`kp_cameratest`, `camera_profile_consistency_test`). No snapshot has been taken in a running game. Every other build reports `available = false`.

#### `kp.camera.capabilities()`

Returns a table: `available` (bool), `profile` (`"windows-k1-gog"` or `"unsupported"`), `abi`, `writes` (always false) and `limits` (text).

#### `kp.camera.snapshot()`

Returns a protected, read-only capture, or `nil, message, code` on failure. `code` is one of `unsupported`, `guard`, `chain` or `value`. A failed code guard, a wrong vtable, a null or unreadable pointer, or a non-finite float gives a failure. You never get a partial capture.

| field | type | meaning |
|---|---|---|
| `behavior` | string | `"chase"` for the chase camera, `"other"` for any other behaviour |
| `mode` | int | camera mode byte (client options +0x6d) |
| `pending_style` | int | pending camera-style global, `-1` when none |
| `module`, `camera`, `behavior_ptr`, `behavior_vtable` | string | hex pointers, for diagnostics |
| `distance` | number | `m_fDist` (+0x110), the target distance |
| `speed` | number | `m_fSpeed` (+0x114) |
| `pitch` | number | `m_fPresetPitch` (+0x11c), units unverified |
| `height` | number | `m_fHeight` (+0x120), units unverified |
| `dolly` | int | raw dword at +0x84; nonzero makes the engine recompute `distance` every tick |
| `base_distance`, `base_view_angle` | number | +0x88 and +0x8c |
| `style_row` | int | cached camera-style row at +0x5c, `-1` for defaults |
| `raw_28_unverified` | {4 numbers} | floats at +0x28, meaning unverified |
| `raw_38_unverified`, `raw_50_unverified` | {3 numbers} | floats at +0x38 and +0x50, meaning unverified |

Fields from `distance` down are nil unless `behavior` is `"chase"`. For any other behaviour the runtime reads only its vtable.

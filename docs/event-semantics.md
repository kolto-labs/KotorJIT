# KOTOR 1 event semantics

How the engine turns things that happen into scripts that run, and what a Lua
runtime can honestly do about it.

Everything here comes from recovered C for the K1 GOG build
(`swkotor.exe`, md5 `9a44891011437deb6536d992bccdfe4b`), under:

```
/home/brunner56/biodecompwarehouse/kotorxid/output/kotor_readable/
  K1__k1_win_gog_swkotor.exe/src/AspyrBuild/depot/KOTOR/PC_Source/Dev/
```

Every `file.cpp:NNN` below is relative to that directory. The recovered source
is Ghidra output. Each function carries `authority: advisory-ghidra -- readable,
NOT byte-verified`. Line numbers are stable for this corpus snapshot only.

The machine-readable table is `data/events.draft.toml`.

## Two corrections to the working assumptions

Read these first. Both were stated as settled in the brief. Both are wrong, and
both would produce silent bugs.

### 1. `CScriptEvent` parameters are variable-length arrays

The brief describes the 52-byte layout as an event type plus three ints, three
floats, three strings and three object ids. The size is right. The reading is
not.

Each of the four parameter blocks is a `CExoArrayList`, which the corpus type
table defines with a size assertion:

```c
typedef struct CExoArrayList { void *data; int size; int capacity; } CExoArrayList;
// sizeof == 0xC   -- SQLite ghidra_type, binary_id 8
```

`CScriptEvent::CScriptEvent` zeroes all twelve words
(`nwsscriptevent.cpp:83-99`). `CScriptEvent::LoadEvent` grows each list from 0
to 0x10 and then doubles (`nwsscriptevent.cpp:155-163`). So the layout is:

| offset | field |
|---|---|
| 0x00 | `unsigned short event_type` |
| 0x02 | `unsigned short` -- never written by any code I read |
| 0x04 | `CExoArrayList<int>` int params |
| 0x10 | `CExoArrayList<float>` float params |
| 0x1C | `CExoArrayList<CExoString>` string params |
| 0x28 | `CExoArrayList<ulong>` object id params |

The 0x10 / 0x14 offsets are confirmed directly by `GetFloat` at `0x004d64a0`,
which dereferences `*(this+0x10)` as the array base and compares the index
against `*(this+0x14)`.

There is no fixed count of three. A module activate-item event writes four
object ids and three floats (`nwsmodule.cpp:1195-1213`). A damage event writes
fifteen ints in a loop (`nwseffectlist.cpp:6410-6419 (the loop body is :6416)`).

**What this means for a Lua binding.** Do not index a fixed array. Read
`.size` first, or go through the engine's own accessors, which are bounds-safe:

| accessor | address | out-of-range result |
|---|---|---|
| `GetInteger(n)` | `0x004d6480` | `0` |
| `GetFloat(n)` | `0x004d64a0` | `0.0` |
| `GetObjectID(n)` | `0x004d64c0` | `0x7f000000` (OBJECT_INVALID) |
| `GetString(n)` | `0x004d7360` | `""` |

The setters grow the list instead of failing: `SetInteger` at `0x004d76b0`,
`SetFloat` at `0x004d7720`, `SetObjectID` at `0x004d7780`, `SetString` at
`0x004d6ae0` (`nwmessage.cpp:610-617`).

A Lua binding that reads slot 2 of an event that only filled slot 0 gets a
zero, not garbage. That is a safe failure. A binding that reads
`((int*)ev)[offset]` directly gets a pointer value interpreted as an integer.
That is not.

### 2. The creature handler's branch set

The brief says `CSWSCreature::EventHandler` dispatches on 0, 1, 2, 4, 5, 8, 9,
with gaps at 3, 6 and 7. It does not. The actual top-level branches, in source
order from `nwscreature.cpp:11456-12137`, are:

`5, 0xE, 4, 9, 1, 0x14, 0x15, 0x16, 0xF, 8, 0x13, 0xB, 0x12, 0xA, 0x1B`

There is no branch on 0, 2, 3, 6 or 7. And 3, 6 and 7 are not gaps in the
numbering at all -- they are `EVENT_LEFT_TRIGGER`, `EVENT_CLOSE_OBJECT` and
`EVENT_OPEN_OBJECT`. Creatures simply do not implement them. Doors do
(`nwsdoor.cpp:1672` and `:1678`).

## The two dispatch layers

There are two numbering spaces. They are unrelated. Conflating them is the
single easiest way to build a wrong event table.

```
  something happens
        |
        v
  CServerAIMaster::AddEventDeltaTime(days, ms, callerId, objectId, eventId, data)
        |                                                          ^^^^^^^
        |                                            LAYER 1: engine event id
        v
  event queue (CExoLinkedList of CServerAIEventNode)
        |
        v
  CServerAIMaster::UpdateState  ->  vtable+0x78  ->  CSWS<Type>::EventHandler
        |
        +-- eventId != 10 : the engine does something directly
        |                   (apply an effect, destroy the object, open a door)
        |
        +-- eventId == 10 (EVENT_SIGNAL_EVENT): data is a CScriptEvent*
                |
                v
          switch (ev->event_type)     LAYER 2: script event type
                |
                v
          CVirtualMachine::RunScript(<a resref from the object>, objectId, 1)
```

### Layer 1 -- engine event ids

`CServerAIMaster::AddEventAbsoluteTime` logs every queued event, and the log
strings are a complete, authoritative name table
(`serveraimaster.cpp:299-380`):

| id | name | id | name |
|---|---|---|---|
| 1 | `EVENT_TIMED_EVENT` | 0xF | `EVENT_ON_MELEE_ATTACKED` |
| 2 | `EVENT_ENTERED_TRIGGER` | 0x10 | `EVENT_DECREMENT_STACKSIZE` |
| 3 | `EVENT_LEFT_TRIGGER` | 0x11 | `EVENT_SPAWN_BODY_BAG` |
| 4 | `EVENT_REMOVE_FROM_AREA` | 0x12 | `EVENT_FORCED_ACTION` |
| 5 | `EVENT_APPLY_EFFECT` | 0x13 | `EVENT_ITEM_ON_HIT_SPELL_IMPACT` |
| 6 | `EVENT_CLOSE_OBJECT` | 0x14 | `EVENT_BROADCAST_AOO` |
| 7 | `EVENT_OPEN_OBJECT` | 0x15 | `EVENT_BROADCAST_SAFE_PROJECTILE` |
| 8 | `EVENT_SPELL_IMPACT` | 0x16 | `EVENT_FEEDBACK_MESSAGE` |
| 9 | `EVENT_PLAY_ANIMATION` | 0x17 | `EVENT_ABILITY_EFFECT_APPLIED` |
| 0xA | `EVENT_SIGNAL_EVENT` | 0x18 | `EVENT_SUMMON_CREATURE` |
| 0xB | `EVENT_DESTROY_OBJECT` | 0x19 | `EVENT_ACQUIRE_ITEM` |
| 0xC | `EVENT_UNLOCK_OBJECT` | 0x1A | `EVENT_AREA_TRANSITION` |
| 0xD | `EVENT_LOCK_OBJECT` | 0x1B | `EVENT_CONTROLLER_RUMBLE` |
| 0xE | `EVENT_REMOVE_EFFECT` | | |

Anything outside 1..0x1B falls to `CExoString::Format("Event(%d)")`, so the
range is complete.

**The numbering is shared across object types.** `CServerAIMaster::UpdateState`
looks the target object up by id and calls `vtable + 0x78` on it with the same
event id regardless of type (`serveraimaster.cpp:1004`); areas and modules get
static calls to the same slot (`:1010`, `:1016`). Each type implements the
subset it cares about and returns from the rest. Waypoints implement exactly
one: 0xB, destroy (`nwswaypoint.cpp:49-57`).

One trap in that function: `if (!bVar4)` at `serveraimaster.cpp:998-1002` gates on
`GetGameObject` -- dispatch happens on the *inverted* return, i.e. on success.

### Layer 2 -- script event types

When the engine event id is 10, the payload is a `CScriptEvent` and its
`event_type` selects the script. The same log function names all of these
(`serveraimaster.cpp:386-498`), prefixed `CSWSSCRIPTEVENT_EVENTTYPE_`:

| type | name | type | name |
|---|---|---|---|
| 0 | `ON_HEARTBEAT` | 0x16 | `ON_OPEN` |
| 1 | `ON_PERCEPTION` | 0x17 | `ON_CLOSE` |
| 2 | `ON_SPELLCASTAT` | 0x18 | `ON_DISARM` |
| 4 | `ON_DAMAGED` | 0x19 | `ON_USED` |
| 5 | `ON_DISTURBED` | 0x1A | `ON_MINE_TRIGGERED` |
| 7 | `ON_DIALOGUE` | 0x1B | `ON_INVENTORY_DISTURBED` |
| 8 | `ON_SPAWN_IN` | 0x1C | `ON_LOCKED` |
| 9 | `ON_RESTED` | 0x1D | `ON_UNLOCKED` |
| 0xA | `ON_DEATH` | 0x1E | `ON_CLICKED` |
| 0xB | `ON_USER_DEFINED_EVENT` | 0x1F | `ON_PATH_BLOCKED` |
| 0xC | `ON_OBJECT_ENTER` | 0x20 | `ON_PLAYER_DYING` |
| 0xD | `ON_OBJECT_EXIT` | 0x21 | `ON_RESPAWN_BUTTON_PRESSED` |
| 0xE | `ON_PLAYER_ENTER` | 0x22 | `ON_FAIL_TO_OPEN` |
| 0xF | `ON_PLAYER_EXIT` | 0x23 | `ON_PLAYER_REST` |
| 0x10 | `ON_MODULE_START` | 0x24 | `ON_DESTROYPLAYERCREATURE` |
| 0x11 | `ON_MODULE_LOAD` | 0x25 | `ON_PLAYER_LEVEL_UP` |
| 0x12 | `ON_ACTIVATE_ITEM` | 0x26 | `ON_EQUIP_ITEM` |
| 0x13 | `ON_ACQUIRE_ITEM` | | |
| 0x14 | `ON_LOSE_ITEM` | | |
| 0x15 | `ON_ENCOUNTER_EXHAUSTED` | | |

Types **3** and **6** have no case in that switch and fall to the
`EventType(%d)` default. They are real holes in the enum, unlike the layer-1
"gaps".

Three more constants are named but **no handler consumes them**. I enumerated
every layer-2 case in all ten `EventHandler` implementations. The union is:

`0, 1, 2, 4, 7, 0xA, 0xB, 0xC, 0xD, 0xE, 0xF, 0x10, 0x11, 0x12, 0x13, 0x14,
0x15, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E, 0x1F, 0x20, 0x21,
0x23, 0x24, 0x25, 0x26`

Missing from that union, though the log table names them:

| type | name | why it is dead |
|---|---|---|
| 5 | `ON_DISTURBED` | superseded by 0x1B, `ON_INVENTORY_DISTURBED` |
| 8 | `ON_SPAWN_IN` | creature spawn runs directly at `nwscreature.cpp:443` |
| 9 | `ON_RESTED` | rest reaches scripts as module type 0x23 instead |

Do not expose 5, 8 or 9 as Lua events. Queueing one would deliver an event that
every handler silently drops.

**The two layers collide on three values.** Always say which layer you mean:

| value | layer 1 (engine event id) | layer 2 (script event type) |
|---|---|---|
| 0xB | `EVENT_DESTROY_OBJECT` | `ON_USER_DEFINED_EVENT` |
| 0x1A | `EVENT_AREA_TRANSITION` | `ON_MINE_TRIGGERED` |
| 0x1B | `EVENT_CONTROLLER_RUMBLE` | `ON_INVENTORY_DISTURBED` |

0x1A is the nastiest of the three, because `DeleteEventData` treats layer-1 id
0x1A as carrying a `CScriptEvent` payload just like id 0xA does
(`serveraimaster.cpp:851-855`). A door's trap event is layer-2 0x1A queued under
layer-1 id 0xA (`nwsdoor.cpp:1651-1658`). The two 0x1A's are unrelated.

## The `EventHandler` signature

Ghidra recovered `CSWSCreature::EventHandler` with three parameters and the
other nine handlers with five. The five-parameter form is correct for all of
them:

```c
void __thiscall EventHandler(this,
                             ulong nEventId,        // layer 1 id
                             ulong nCallerObjectId, // who caused it
                             void *pEventData,      // type depends on nEventId
                             ulong nCalendarDay,
                             ulong nTimeOfDay);
```

Evidence, in order of strength:

1. `CSWSModule::EventHandler` reads arguments 4 and 5 in its heartbeat case and
   stores them (`nwsmodule.cpp:1156-1161`). So does the area
   (`nwsarea.cpp:5626-5632`) and the door (`nwsdoor.cpp:1741-1748`). Ghidra
   only recovers parameters that are used, which is why the creature handler
   looks shorter -- it has no heartbeat case.
2. `CServerAIMaster::UpdateState` unpacks a queue node and passes
   `(node[4], node[2], node[5], node[0], node[1])` (`serveraimaster.cpp:989-1017`).
3. `AddEventDeltaTime(this, lenDays, lenMS, callerId, objectId, eventId, data)`
   -- the door posts a mine event with the attacker as caller and itself as
   target (`nwsdoor.cpp:1651-1658`).

Argument 2 is the **caller**, not the target. `this` is the target. The creature
handler feeds argument 2 straight to `GetCreatureByGameObjectID` and treats the
result as the attacker, damager or disturber
(`nwscreature.cpp:11594`, `:11673`, `:12105`).

One thing does not line up: `CServerAIEventNode::SaveNode` writes fields in the
order day, time, objectId, callerId, eventId (`serveraimaster.cpp:545-549`),
but `UpdateState` reads word [3] as the recipient and passes word [2] as
argument 2. Either the struct field order differs from the write order, or
Ghidra's field names on that node are guesses. The behavioural evidence above
settles the *semantics*; the node's byte layout stays an open question.

### The payload is polymorphic

`pEventData` is not always a `CScriptEvent`.
`CServerAIMaster::DeleteEventData` is the authority, because it must destroy
each payload correctly (`serveraimaster.cpp:841-871`):

| event id | payload type |
|---|---|
| 1 | `CVirtualMachineScript` (freed via `DeleteScriptSituation`) |
| 8, 0x13 | `CSWSSpellScriptData` |
| 0xA, 0x18, 0x1A | `CScriptEvent` |
| 0x15 | `CSWSCombatAttackData` |
| 0x16 | `CSWCCMessageData` |
| everything else | not freed -- either an immediate or nothing |

Event id 4 stores a single byte and is serialised as `WriteFieldBYTE(..., "Value")` at `serveraimaster.cpp:559`,
which is why it is passed as an immediate rather than a pointer.

### `CSWCCMessageData` is not `CScriptEvent`

The decompiled listings constantly call `CSWCCMessageData::GetInteger` on
objects that are then destroyed as `CScriptEvent`. That looks like one class
with two names. It is not:

| symbol | address | size |
|---|---|---|
| `CSWCCMessageData::CSWCCMessageData` | `0x004d69f0` | 78 |
| `CSWCCMessageData::~CSWCCMessageData` | `0x004d6a40` | 47 |
| `CScriptEvent::CScriptEvent` | `0x004d7540` | 76 |
| `CScriptEvent::~CScriptEvent` | `0x004d7590` | 139 |

(SQLite `func`, `binary_id = 8`.) Two distinct constructors, two distinct
destructors, and two different source files -- `clientcore/nwmessage.cpp`
versus `servercore/nwsscriptevent.cpp`. Both are 52 bytes and both are
`operator_new(0x34)`.

Most likely the layouts are identical and the compiler folded the accessors, so
Ghidra attached one name to shared code. Treat that as probable, not proven.
Concretely: event id 0x16's payload really is `CSWCCMessageData` and its
parameter layout should be marked unverified until the two structs are compared
byte for byte.

## Script slots are per-type index tables

Each object type keeps its script resrefs in a `CExoString` array. The index
into that array is what the code uses; the GFF field name is what a modder
sees. The mapping comes from the save/load functions, which pair
`CResRef::CResRef(&tmp, scripts + N)` with `WriteFieldCResRef(..., "Name")`.

There is no shared ordering. The creature's slot 5 is `ScriptDisturbed`; the
door's slot 5 is `OnHeartbeat`.

**Creature**, 14 slots (`nwscreature.cpp:12564-12591`, array size `0xe` from the
constructor at `:7137`):

`0 ScriptHeartbeat, 1 ScriptOnNotice, 2 ScriptSpellAt, 3 ScriptAttacked,
4 ScriptDamaged, 5 ScriptDisturbed, 6 ScriptEndRound, 7 ScriptDialogue,
8 ScriptSpawn, 9 ScriptRested, 10 ScriptDeath, 11 ScriptUserDefine,
12 ScriptOnBlocked, 13 ScriptEndDialogue`

**Door**, 15 slots (`nwsdoor.cpp:1140-1287`):

`0 OnOpen, 1 OnClosed, 2 OnDamaged, 3 OnDeath, 4 OnDisarm, 5 OnHeartbeat,
6 OnLock, 7 OnMeleeAttacked, 8 OnSpellCastAt, 9 OnTrapTriggered, 10 OnUnlock,
11 OnUserDefined, 12 OnClick, 13 OnDialog, 14 OnFailToOpen`

**Placeable**, 16 slots (`nwsplaceable.cpp:797-919` and `:1284-1315`):

`0 OnClosed, 1 OnDamaged, 2 OnDeath, 3 OnDisarm, 4 OnHeartbeat,
5 OnInvDisturbed, 6 OnLock, 7 OnMeleeAttacked, 8 OnOpen, 9 OnSpellCastAt,
10 OnTrapTriggered, 11 OnUnlock, 12 OnUsed, 13 OnUserDefined, 14 OnDialog,
15 OnEndDialogue`

**Trigger**, 7 slots (`nwstrigger.cpp:1281-1293`):

`0 ScriptHeartbeat, 1 ScriptOnEnter, 2 ScriptOnExit, 3 ScriptUserDefine,
4 OnTrapTriggered, 5 OnDisarm, 6 OnClick`

**Module**, 15 slots (`nwsmodule.cpp:2830-2856`, plus `:4470` for slot 14):

`0 Mod_OnHeartbeat, 1 Mod_OnUsrDefined, 2 Mod_OnModLoad, 3 Mod_OnModStart,
4 Mod_OnClientEntr, 5 Mod_OnClientLeav, 6 Mod_OnActvtItem, 7 Mod_OnAcquirItem,
8 Mod_OnUnAqreItem, 9 Mod_OnPlrDeath, 10 Mod_OnPlrDying, 11 Mod_OnSpawnBtnDn,
12 Mod_OnPlrRest, 13 Mod_OnPlrLvlUp, 14 Mod_OnEquipItem`

**Area**, **encounter**, **store** and **AOE** use named members instead of an
array: area has `OnHeartbeat / OnUserDefined / OnEnter / OnExit`
(`nwsarea.cpp:3233-3257`); encounter has
`OnEntered / OnExit / OnHeartbeat / OnExhausted / OnUserDefined`
(`nwsencounter.cpp:853-863`); store has `OnOpenStore` (`nwsstore.cpp:112`).

## Not everything goes through `EventHandler`

This is the finding that most changes how a Lua runtime should be wired.

Six creature scripts are **never** reachable through `event.creature`:

| script slot | where it actually runs |
|---|---|
| `ScriptHeartbeat` (0) | `nwscreature.cpp:462` -- the AI update |
| `ScriptSpawn` (8) | `nwscreature.cpp:443`, `nwseffectlist.cpp:579` |
| `ScriptDamaged` (4) | `nwseffectlist.cpp:6634` -- `OnApplyDamage` |
| `ScriptEndRound` (6) | `nwscombatround.cpp:2061`, `nwseffectlist.cpp:2110` |
| `ScriptDeath` (10) | `nwseffectlist.cpp:7167` -- `OnApplyDeath` |
| `ScriptEndDialogue` (13) | `nwscreature.cpp:3122-3124` -- `OnEndDialog` |

The layer-2 enum has `ON_HEARTBEAT`, `ON_SPAWN_IN`, `ON_DAMAGED`, `ON_DEATH`
and `ON_RESTED` constants, and other object types *do* use them. The creature
handler just has no cases for them. For `ON_DAMAGED` this is visibly wasteful:
`nwseffectlist.cpp:6386-6402` builds a type-4 event carrying the damage amount
and queues it at the damaged object; if that object is a creature, the event is
delivered, matched against nothing, and destroyed.

Two more creature quirks worth knowing:

- `ScriptDamaged` does not run for the party leader. The guard is
  `CSWPartyTable::GetIsLeader(...) == 0` at `nwseffectlist.cpp:6632`.
- `ScriptRested` (slot 9) is **dead**. An exhaustive grep for `script_resrefs`
  across the whole tree finds it only in save and load. Player rest reaches
  scripts through the module's `Mod_OnPlrRest` instead (layer-2 type 0x23,
  `nwsmodule.cpp:1239-1245`).

Trigger heartbeat is the same story: `nwstrigger.cpp:773` runs slot 0 directly
and `CSWSTrigger::EventHandler` has no case 0.

So `hook_site` in `events.draft.toml` is not a style choice. It records where
the event is observable at all.

**This is a hook-site decision, not a documentation detail.** `data/hooksites.toml`
marks `event.creature` as `required = true` and `vm.run_script` as `required = true`,
but treats the pairing as if `event.creature` were the richer of the two for
creature events. It is not. Six of the creature's fourteen script slots --
heartbeat, spawn, damaged, end-of-round, death and end-dialogue -- are invisible
from `event.creature` and reachable only from `vm.run_script`. Any creature
event surface that intends to cover those must be built on `vm.run_script`,
with `event.creature` supplying the caller id and the typed payload for the
events that do route through it.

## Return values

`CVirtualMachineInternal::RunScript` (`0x005d45d0`) returns an `int`:

- `0` -- empty script name, `ReadScriptFile` failed, or the stack was
  unbalanced on return.
- `1` -- the script ran and the stack was clean.

Separately, if the script left exactly one `INTEGER` on the stack, `RunScript`
stashes it: type tag `3` into `field1_0x1c`, value into `field2_0x20`.
`GetRunScriptReturnValue` reads that pair.

**One caller in the entire recovered tree reads it.** A single grep for
`GetRunScriptReturnValue` across the whole corpus returns exactly one hit:
`nwsdialog.cpp:238`, inside `CSWSDialog::CheckScript`:

```c
if (CResRef::operator==(param_2, "")) return 1;           // empty  -> allow
uVar2 = RunScript(&name, object, 1);
if (uVar2 == 1) {
    if (GetRunScriptReturnValue(&type, &value) && type == 3) return value != 0;
    return 0;
}
```

That is the dialogue node conditional. Nothing else in the engine looks at what
a script returned.

The practical consequence: **`OnDialogConditional` is the only event where a
Lua handler can meaningfully "override" the result by changing a return value.**
Everywhere else the engine ignores the result, so the only lever is suppressing
the call.

Every `EventHandler` returns `void`.

## What is blockable

Two very different questions:

**Can you suppress the script?** Almost always yes. Detour `vm.run_script`,
return 0 without running anything, and the caller carries on. The handlers do
their bookkeeping around the call, not because of it.

**Can you suppress the whole event?** Usually no. Detouring `event.*` and
returning early skips work the rest of the engine has already committed to, and
in most branches also leaks the payload -- the handler owns it and frees it at
the end.

The clearest cases:

- **Event id 0xB, destroy object.** The last statement is the destructor. Before
  it, the creature branch removes itself from every trigger, door and placeable
  occupant list in the area and decrements its encounter's active count
  (`nwscreature.cpp:11808-11915`). Skipping this leaves dangling object ids in
  live containers.
- **Event id 5, apply effect.** No script at all
  (`nwscreature.cpp:11513-11530`). Suppressing it silently discards an effect
  the caller believes was applied.
- **Layer-2 type 0x1E on a linked door or trigger.** This is the K1 area
  transition state machine. The first pass starts a global fade, sets
  `SetPauseState(2)` and re-posts itself with a 500 ms delay
  (`nwsdoor.cpp:1946-1964`); the second pass matches the pending id and calls
  `SetMoveToModulePending` (`:1985`). Block either pass and the player is
  stranded behind a fade, paused.
- **Layer-2 type 2, spell-cast-at, on a creature.** The script runs at
  `nwscreature.cpp:12024`; combat-state broadcast and `SetExcitedState` run
  *after* it (`:12030-12044`). Safe to block the script, not the event.
- **Layer-2 type 0xC on an area.** The handler saves the global
  load-from-savegame flag, overwrites it with `int_params[0]`, runs the script,
  and restores it (`nwsarea.cpp:5640-5649`). The restore is unconditional, so
  blocking the script alone is fine.

The genuinely advisory ones -- where `RunScript` is the last statement in its
branch and everything before it already happened -- include creature
perception, user-defined, inventory-disturbed, path-blocked and attacked, and
the equivalents on doors, placeables, triggers, encounters and the module. Those
are the events a Lua API can honestly offer as blockable. They are marked
`blocking = true` in the TOML.

`EVENT_BROADCAST_AOO` (0x14) is a special case: on creatures the entire branch
is a `return` (`nwscreature.cpp:11590-11593`). It is a leftover from NWN's
attack-of-opportunity system. There is nothing to block and nothing to observe
beyond the fact that it fired.

## Two engine bugs found on the way

Both are in the TOML as notes. Neither is a recovery artefact.

**Module slot 14 is read but never written.** `LoadModule` reads
`Mod_OnEquipItem` into slot 14 (`nwsmodule.cpp:4470`), the handler runs it
(`:1262-1267`), but `SaveModule` stops at slot 13 (`:2830-2856`). Save and
reload a module and its equip-item script is gone.

**The trigger's user-defined script runs on the wrong object.** Every other
handler passes its own object id to `RunScript`. The trigger passes the caller:

```c
else if (sVar1 == 0xb) {                       // nwstrigger.cpp:1603
    iVar4 = GetInteger(param_3, 0);
    this->field39_0x2f8 = iVar4;
    this_08 = this->scripts + 3;               // :1607
    uVar5  = param_2;                          // :1608  <-- the caller
}
...
RunScript(VirtualMachine, this_08, uVar5, 1);  // :1640
```

Compare `nwscreature.cpp:12095-12102`, which uses
`(this->object).game_object.id`. Inside a trigger's `ScriptUserDefine`,
`OBJECT_SELF` is whoever signalled the event, not the trigger. A Lua binding
that helpfully "fixes" this will disagree with every stock K1 script.

## Confidence and how to raise it

105 entries: **87 high**, **18 medium**, **0 low**.

An entry is `high` when the dispatch constant, the script slot index, the slot's
GFF name and every argument were each read from a named line. It is `medium`
when one of those is inferred.

The medium entries and what would settle them:

| entry | gap | fix |
|---|---|---|
| `OnModuleActivateItem` | four object slots and three floats are read but never named | read `ExecuteCommandGetItemActivated` / `...Activator` / `...TargetLocation` in `nwvmachinecommands.cpp` and see which module field each returns |
| `OnCreatureDamaged`, `OnDoorDamaged`, `OnPlaceableDamaged` | the handler never reads `int_params[0]`; the amount is only known from the producer | read `CSWSEffectListHandler::OnApplyDamage` in full (`nwseffectlist.cpp:6232-6767`) and the `GetTotalDamageDealt` routine |
| `OnCreatureSpellImpact`, `OnCreatureItemOnHitSpellImpact` | the script resref's offset inside `CSWSSpellScriptData` is mislabelled by Ghidra | recover the `CSWSSpellScriptData` struct from the corpus `ghidra_type` table |
| `OnCreatureRemoveEffect` | the effect id's byte packing is unreadable | read `CSWSObject::RemoveEffectById` |
| `OnCreatureRemoveFromArea`, `OnCreaturePlayAnimation` | the immediate argument's meaning | read `CServerAIEventNode::SaveNode`'s case 4 and case 9 serialisation in full |
| `OnCreatureForcedAction` | the `CancelAction` argument offset | recover `CSWSForcedAction` |
| `OnCreatureFeedbackMessage` | payload is `CSWCCMessageData`, layout unproven | diff the two 52-byte structs field by field |
| `OnAreaSpawnBodyBag` | ad-hoc payload with no `DeleteEventData` case | read the producer of event id 0x11 |
| `OnDoorOpen` | `OnOpen` runs inside `OpenDoor`, unread | read `nwsdoor.cpp` around `:711` |
| `OnPlaceableEndDialogue`, `OnTriggerHeartbeat`, `OnTriggerTrapTriggered` | enclosing function not identified | map `nwsplaceable.cpp:537`, `nwstrigger.cpp:773` and `nwstrigger.cpp:666` to their functions |
| `OnCreatureStateScript` | meaning of `field_0x8ed` | read the writers of that field |
| `OnCreatureBroadcastSafeProjectile` | payload offsets | recover `CSWSCombatAttackData` |

## What `default_script` does and does not mean

Names like `k_def_heartbeat01` live in `.utc` blueprints, not in the executable.
They are template data. This document does not guess them.

The only defaults that exist **in the binary** are:

| script | where |
|---|---|
| `k_hen_dialogue01` | creature slot 7 (`nwscreature.cpp:12084-12090`), door slot 13 (`nwsdoor.cpp:1815-1818`), placeable slot 14 (`nwsplaceable.cpp:2228-2234`) -- substituted when the slot is empty or literally `"default"` |
| `NW_G0_Transition` | door slot 12 (`nwsdoor.cpp:2000-2005`), trigger slot 6 (`nwstrigger.cpp:1626`) -- only when the object is module-linked |
| `k_trg_transfail` | hardcoded, run when the party is not together at a transition (`nwsdoor.cpp:1935-1938`, `nwstrigger.cpp:1680-1684`) |
| `itemuse` | hardcoded, client message 0xC (`nwshandleplayermessage.cpp:2506-2515`) |
| `traps.2da` column `MineScript` | door slot 9 (`nwsdoor.cpp:1293-1310`), placeable slot 10 (`nwsplaceable.cpp:907-919`) |
| `statescripts.2da` column `SCRIPTNAME` | run right after the creature heartbeat (`nwscreature.cpp:466-486`) |

Everywhere else the TOML omits `default_script`.

## One security note

`nwshandleplayermessage.cpp:595-615` handles player message subtype 8 by
reading a script name off the wire (up to 0x20 characters) and running it on the
sending player's creature. Any Lua sandbox that reasons about where a script
came from should know this path exists.

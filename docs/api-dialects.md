# Two ways to write the same script

Generated from `data/api_aliases.toml`. Do not edit by hand.

Scripts for this kind of runtime came from one of two Halo server mods, and
the two never agreed on names. One writes `readbyte`, `getplayer`, `say`; the
other writes `read_byte`, `get_player`, `say_all`. Both work here, natively.
Mixing them in one file is fine.

You do not need a compatibility module. There isn't one to require.

**57 aliases** over **48 functions**.

## Names

| this runtime calls it | also accepts |
|---|---|
| `assignweapon` | `assign_weapon` |
| `console` | `cprint`, `sendconsoletext` |
| `createobject` | `spawn_object` |
| `destroyobject` | `destroy_object` |
| `entervehicle` | `enter_vehicle` |
| `exitvehicle` | `exit_vehicle` |
| `feedback` | `say`, `say_all`, `privatesay`, `rprint`, `respond` |
| `findsig` | `sig_scan` |
| `getobject` | `get_object_memory` |
| `getplayer` | `get_player` |
| `getplayerobject` | `get_dynamic_player` |
| `getrandomnumber` | `rand` |
| `gettagaddress` | `get_tag` |
| `gettagid` | `lookup_tag`, `lookuptag` |
| `halointersect` | `intersect` |
| `log` | `hprintf`, `log_msg` |
| `movobjectcoords` | `moveobjectcoords` |
| `playerpresent` | `player_present` |
| `readbit` | `read_bit` |
| `readbyte` | `read_byte`, `safe_read` |
| `readchar` | `read_char` |
| `readdouble` | `read_double` |
| `readdword` | `read_dword` |
| `readfloat` | `read_float` |
| `readint` | `read_int` |
| `readshort` | `read_short` |
| `readstring` | `read_string` |
| `readvector` | `read_vector3d` |
| `readwidestring` | `read_wide_string` |
| `readword` | `read_word` |
| `registertimer` | `timer` |
| `removetimer` | `stop_timer` |
| `resolveplayer` | `to_real_index` |
| `rresolveplayer` | `to_player_index` |
| `svcmd` | `execute_command` |
| `updateammo` | `sync_ammo` |
| `writebit` | `write_bit` |
| `writebyte` | `write_byte`, `safe_write` |
| `writechar` | `write_char` |
| `writedouble` | `write_double` |
| `writedword` | `write_dword` |
| `writefloat` | `write_float` |
| `writeint` | `write_int` |
| `writeshort` | `write_short` |
| `writestring` | `write_string` |
| `writevector` | `write_vector3d` |
| `writewidestring` | `write_wide_string` |
| `writeword` | `write_word` |

## Events, two ways

Define a global and it is found at load:

```lua
function OnTick(tick, relevant)
    -- ...
end
```

Or register a handler by name at runtime:

```lua
function OnScriptLoad(game, build)
    register_callback(cb.EVENT_TICK, "my_tick")
end

function my_tick(tick, relevant)
    -- ...
end
```

A runtime registration wins over a same-named global, since asking for one
is explicit. `unregister_callback(cb.EVENT_TICK)` removes it.

### The 10 events that map

| constant | raises |
|---|---|
| `cb.EVENT_TICK` | `OnTick` |
| `cb.EVENT_COMMAND` | `OnConsoleCommand` |
| `cb.EVENT_GAME_START` | `OnModuleLoad` |
| `cb.EVENT_SPAWN` | `OnCreatureSpawn` |
| `cb.EVENT_DIE` | `OnCreatureDeath` |
| `cb.EVENT_DAMAGE_APPLICATION` | `OnCreatureDamaged` |
| `cb.EVENT_AREA_ENTER` | `OnAreaEnter` |
| `cb.EVENT_AREA_EXIT` | `OnAreaExit` |
| `cb.EVENT_OBJECT_SPAWN` | `OnObjectSpawn` |
| `cb.EVENT_CHAT` | `OnDialogue` |

### The 21 that do not

These are Halo concepts. A single-player RPG has no teams, no vehicles and no
network players, so there is nothing honest to bind them to. The constants
exist so a script referencing one still loads, and registering for one logs
once saying it will never fire rather than failing silently.

| constant | why |
|---|---|
| `cb.EVENT_JOIN` | no network players |
| `cb.EVENT_PREJOIN` | no network players |
| `cb.EVENT_LEAVE` | no network players |
| `cb.EVENT_LOGIN` | no network players |
| `cb.EVENT_TEAM_SWITCH` | no teams |
| `cb.EVENT_BETRAY` | no teams |
| `cb.EVENT_SCORE` | no scoring |
| `cb.EVENT_GAME_END` | no match end |
| `cb.EVENT_MAP_RESET` | no map cycle |
| `cb.EVENT_VEHICLE_ENTER` | no vehicles |
| `cb.EVENT_VEHICLE_EXIT` | no vehicles |
| `cb.EVENT_WEAPON_DROP` | not yet mapped |
| `cb.EVENT_WEAPON_PICKUP` | not yet mapped |
| `cb.EVENT_KILL` | not yet mapped |
| `cb.EVENT_SUICIDE` | not yet mapped |
| `cb.EVENT_ALIVE` | not yet mapped |
| `cb.EVENT_WARP` | not yet mapped |
| `cb.EVENT_CAMP` | not yet mapped |
| `cb.EVENT_SNAP` | not yet mapped |
| `cb.EVENT_ECHO` | not yet mapped |
| `cb.EVENT_PRESPAWN` | not yet mapped |

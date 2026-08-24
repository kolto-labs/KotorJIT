# Host API design

What a Lua script can call. The event pipeline decides *when* a script runs. This file decides what it can *do* once it is running.

Grounded in the KOTOR engine routine tables, the recovered struct layouts, and the event catalog in `data/events.toml`.

KOTOR is a dedicated server in-process (`CServerExoApp`) with one hardcoded client. That creature is `CServerExoApp::GetFirstPCObject` / `GetPlayerCreatureId` / `GetFirstPC`. Client attach and leave are `OnModulePlayerEnter` (`Mod_OnClientEntr`) and `OnModulePlayerExit`
(`Mod_OnClientLeav`). Objects are `CServerExoApp::GetGameObject` / `CGameObject`, not a Halo player-memory slot.

## The shape of the problem

KOTOR already has a scripting language. 769 of 772 engine routines become
`kotor.GetFirstPC()`, `kotor.CreateObject(...)`, `kotor.SpeakString(...)`. The local
server's player list is that one client plus party slots. Areas, dialogue, journal,
alignment, and force powers are engine questions. Engine routines answer them.

The rest of the surface exists because those routines are not enough:

- A field that is not in the generated layouts still needs a read.
- `DelayCommand` takes an NWScript closure Lua cannot push.
- The cheat console hands a script a whole input line that has to be split.

**Typed access first, raw memory as the escape hatch.**

## Modules

Each is file-disjoint so they can be built in parallel.

### `routines`: the NWScript bridge
`src/api/routines.cpp`, `src/api/enginestruct.{hpp,cpp}`

The highest-value module. 769 of KOTOR 1's 772 engine routines become
`kotor.GetModule()`, `kotor.CreateObject(...)` and so on.

Marshalling has three kinds. Scalars are plain Lua values. Vectors are `{x=,y=,z=}` tables
and use the VM's own vector push/pop, not three scalar pushes. Effects, events, locations
and talents are opaque handles a script holds and passes back. There are exactly four,
because KOTOR has no `itemproperty`, and pushing that type id would be rejected.

Argument order is the trap: the VM pops the first declared parameter first, so the last
declared parameter is pushed first. Reversed, it appears to work for symmetric signatures
and silently corrupts everything else.

`AssignCommand`, `DelayCommand` and `ActionDoCommand` cannot be called. They take a
closure the compiler emits as `STORE_STATE` bytecode. The `timers` module replaces them.

### `structs`: generated typed views
`src/api/structs.{hpp,cpp}`, `tools/gen_structs.py`, `src/generated/structs_*.inc`

Named field access with the offset and width baked in at build time. A field that does
not exist is an error at the call, not a wrong number.

**The trap, already hit once on this project:** several fields Ghidra emits as
`unsigned char[0xC]` are `CExoArrayList {void* data; int size; int capacity}`. Reading slot
0 as an int returns the data pointer. The generator must recognise these and emit a list
accessor, never an integer read.

### `memory`: the escape hatch
`src/api/memory.{hpp,cpp}`

`readbyte`/`readfloat`/`writeword` and the rest, 23 functions. The typed layer will always
lag what someone needs today.

Reads are probe-guarded: a bad address returns nil rather than faulting. Writes are the
sharp edge and stay sharp. A scripting runtime that cannot write memory cannot do what
people install it for. The line is drawn at *reporting*, not prevention.

### `entity`: objects and party
`src/api/entity.{hpp,cpp}`

Resolving an object id to a typed handle, the local client (`GetFirstPC` /
`CServerExoApp::GetPlayerCreatureId`), party members via `GetPartyMemberByIndex`
/ `CSWPartyTable`, and area contents. Almost everything here calls an engine
routine. The handle is what the routine bridge does not have.

### `output`: saying things
`src/api/output.{hpp,cpp}`

Log, cheat-console text, and on-screen feedback (`SendMessageToPC`, `AurPostString`,
`SpeakString`) to the `GetFirstPC` creature.

### `timers`: deferred work
`src/api/timers.{hpp,cpp}`

`registertimer`/`removetimer` over the `OnTick` hook, and the replacement for
`DelayCommand`. A timer that throws is quarantined like any other callback.

### `strings`: tokenising
`src/api/strings.{hpp,cpp}`

`tokenizestring`/`tokenizecmdstring`. Small, but every console-command script needs it.

## What we are not doing

- **HTTP.** A local-server RPG mod that phones home is a bad default.
- **A second network client.** The engine is already a server; a second
  attachable client is not wired yet. The player/chat/join surface stays.
- **`itemproperty`.** Not a KOTOR type.

## What only KOTOR has

Dialogue, journal and quest state, alignment, force powers and talents, party management,
inventory, module transitions, and the 2DA rules database. That last one has no NWScript routine
at all and is currently invisible to scripts.

`OBJECT_SELF` being writable is the single largest one. A script can run engine routines as
any object.

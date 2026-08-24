# Host API design

What a Lua script can call. The event pipeline decides *when* a script runs; this decides
what it can *do* once it is running.

Grounded in three research artifacts under `data/research/`, produced by reading Phasor's
registration table and its 13 real scripts, the KOTOR engine routine tables, and the
recovered struct layouts:

- `phasor_inventory.json` — 93 host functions Phasor provides, with signatures and call-site
  counts. The registration table is authoritative for what exists; the scripts are
  authoritative for how it is used.
- `phasor_mapping.json` — 51 capability mappings onto KOTOR mechanisms, 37 high confidence,
  plus 11 that genuinely do not map and 18 things KOTOR can do that Halo cannot.
- `phasor_structs.json` — 25 engine struct layouts with field offsets.

## The shape of the problem

Phasor's API is Halo-shaped: players, teams, weapons, vehicles, tags. Most of it maps, but
not by copying names. `kill(player)` becomes an engine routine call; `getteamsize` becomes
party size; `gettagid` becomes a resref lookup.

Three quarters of the surface is not really API at all — it is **1,071 call sites** of
`readfloat(base + 0x1C)` and friends. Phasor scripts build typed views of engine state out
of raw reads, and `z4eqrjVN.txt` is 150 KB of exactly that, annotated `-- Confirmed.` A
wrong offset there is a silent wrong answer.

We can do better, because we have size-asserted struct layouts. So the design is:

**Typed access first, raw memory as the escape hatch.**

## Modules

Each is file-disjoint so they can be built in parallel.

### `routines` — the NWScript bridge
`src/api/routines.cpp`, `src/api/enginestruct.{hpp,cpp}`

The highest-value module. 769 of KOTOR 1's 772 engine routines become
`kotor.GetModule()`, `kotor.CreateObject(...)` and so on. The generated tables already
exist and are included by nothing.

Marshalling has three kinds. Scalars are plain Lua values. Vectors are `{x=,y=,z=}` tables
and use the VM's own vector push/pop, not three scalar pushes. Effects, events, locations
and talents are opaque handles a script holds and passes back — there are exactly four,
because KOTOR has no `itemproperty`, and pushing that type id would be rejected.

Argument order is the trap: the VM pops the first declared parameter first, so the last
declared parameter is pushed first. Reversed, it appears to work for symmetric signatures
and silently corrupts everything else.

`AssignCommand`, `DelayCommand` and `ActionDoCommand` cannot be called — they take a
closure the compiler emits as `STORE_STATE` bytecode. The `timers` module replaces them.

### `structs` — generated typed views
`src/api/structs.{hpp,cpp}`, `tools/gen_structs.py`, `src/generated/structs_*.inc`

Turns `phasor_structs.json` into named field access with the offset and width baked in at
build time. A field that does not exist is an error at the call, not a wrong number.

**The trap, already hit once on this project:** several fields Ghidra emits as
`unsigned char[0xC]` are `CExoArrayList {void* data; int size; int capacity}`. Reading slot
0 as an int returns the data pointer. The generator must recognise these and emit a list
accessor, never an integer read.

### `memory` — the escape hatch
`src/api/memory.{hpp,cpp}`

`readbyte`/`readfloat`/`writeword` and the rest, 23 functions. Kept because every Phasor
script uses them and because the typed layer will always lag what someone needs today.

Reads are probe-guarded: a bad address returns nil rather than faulting. Writes are the
sharp edge and stay sharp — a scripting runtime that cannot write memory cannot do what
people install it for. The line is drawn at *reporting*, not prevention.

### `entity` — objects and party
`src/api/entity.{hpp,cpp}`

Resolving an object id to a typed handle, the player, party members, area contents. This is
where Phasor's `resolveplayer`/`getplayer`/`getplayerobject` land, reshaped: KOTOR has a
party of up to three, not sixteen network players.

### `output` — saying things
`src/api/output.{hpp,cpp}`

Log, console, and on-screen feedback. Phasor's six output functions assume a server talking
to clients; KOTOR is one machine, so `say`/`privatesay` collapse to feedback and dialogue.

### `timers` — deferred work
`src/api/timers.{hpp,cpp}`

`registertimer`/`removetimer` over the `OnTick` hook, and the replacement for
`DelayCommand`. A timer that throws is quarantined like any other callback.

### `strings` — tokenising
`src/api/strings.{hpp,cpp}`

`tokenizestring`/`tokenizecmdstring`. Small, but every console-command script needs it.

## What we are not doing

- **HTTP.** Phasor has it for ban lists on a game server. A single-player RPG mod that
  phones home is a bad default, and it can be added later if someone wants it.
- **Multiplayer.** Deferred deliberately.
- **`itemproperty`.** Not a KOTOR type.

## KOTOR-only surface

18 capabilities Halo has no analogue for, so Phasor never needed them, all reachable through
the routine bridge once it exists: dialogue, journal and quest state, alignment, force
powers and talents, party management, inventory, module transitions, and the 2DA rules
database — which has no NWScript routine at all and is currently invisible to scripts.

`OBJECT_SELF` being writable is the single largest one. A script can run engine routines as
any object, which Halo's model simply has no equivalent for.

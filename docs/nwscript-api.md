# NWScript routines from Lua

Generated from `data/routines/`. Do not edit by hand.

`nwscript.call(name, ...)` is the only direct engine-routine entry point.
Routine names are catalog data, not Lua globals or table members:

```lua
local m = nwscript.call("GetModule")
local pc = nwscript.call("GetFirstPC")
nwscript.call("SendMessageToPC", pc, "hello")
```

Arguments follow the declaration order in the game's own `nwscript.nss`.
Defaulted parameters may be omitted from the right.

## K1

- callable: **769** of 772
  - plain values only: 607
  - take or return a vector: 22
  - take or return an engine structure: 140
- unsupported: 3
- declared by the binary but undocumented in the header: 0
- total ids: 772

A vector is a Lua table with `x`, `y`, and `z`. An `effect`,
`event`, `location`, or `talent` is an opaque handle: hold it in a
variable and pass it back to another routine, but do not expect to
read fields off it.

Not callable:

- `AssignCommand` -- takes a script closure (action)
- `DelayCommand` -- takes a script closure (action)
- `ActionDoCommand` -- takes a script closure (action)

`AssignCommand`, `DelayCommand`, and `ActionDoCommand` take a script
closure, which the NWScript compiler builds as bytecode. Lua cannot
hand one over. Use the runtime's own scheduler in `OnTick` for delayed
work instead.

## K2

- callable: **874** of 877
  - plain values only: 693
  - take or return a vector: 27
  - take or return an engine structure: 154
- unsupported: 3
- declared by the binary but undocumented in the header: 0
- total ids: 877

A vector is a Lua table with `x`, `y`, and `z`. An `effect`,
`event`, `location`, or `talent` is an opaque handle: hold it in a
variable and pass it back to another routine, but do not expect to
read fields off it.

Not callable:

- `AssignCommand` -- takes a script closure (action)
- `DelayCommand` -- takes a script closure (action)
- `ActionDoCommand` -- takes a script closure (action)

`AssignCommand`, `DelayCommand`, and `ActionDoCommand` take a script
closure, which the NWScript compiler builds as bytecode. Lua cannot
hand one over. Use the runtime's own scheduler in `OnTick` for delayed
work instead.

# NWScript, Lua, and harness configuration boundary plan

## Contract

- `nwscript.call(name, ...)` is the only public entry point for a direct
  NWScript routine.  It owns no Lua-host facilities and exports no routine
  names as Lua variables.
- `kp.*` is the only public root for Hyperstim-native Lua facilities:
  output, timers, memory, objects, structures, harness controls, events, and
  host metadata.
- There are no normal bare Hyperstim globals.  A script's own globals remain
  Lua's responsibility.
- The runtime INI, operator/workspace TOML, and route TOML each have one
  documented owner.  Generated API metadata and hook data remain outside the
  harness configuration contract.
- Preserve K1/K2 bridge behavior, routine argument handling, action-closure
  exclusions, and the shared script/console state initializer.

## Evidence and decision

`kotor.log` currently overwrites NWScript routine 74 (`log(float)`) after the
generated routine registration.  A one-function exception would leave every
future routine exposed to the same shared-table registration-order defect.

The implementation therefore uses one string-dispatched bridge, reusing the
existing `api::find` and `api::call` machinery, rather than generating a
second 769/803-name Lua namespace.  Lua 5.1 resolves globals through ordinary
environment tables, so distinct `nwscript` and `kp` roots are the enforceable
public ownership boundary.  TOML tables and arrays of tables represent the
three configuration scopes directly; `tomllib` plus explicit validation is
adequate.

## Tasks

### Task 1: Replace the generated Lua routine namespace with the NWScript bridge

Owner: routine bridge only (`src/api/routines.*`, direct bridge consumers,
routine/support tests, generated routine documentation).

1. Register only `nwscript.call(name, ...)` from the routine catalog.
2. Delegate to the existing lookup, argument validation, marshalling, VM call,
   default-argument, trace, and result logic.
3. Change output's dynamic engine calls to the bridge, so output does not depend
   on generated routine members.
4. Prove `nwscript.call("log", value)` reaches routine 74 and a bad or excluded
   name reports an actionable error.
5. Prove no generated routine is exported as a `kotor.*` member and that both
   script and console initialization use the same bridge.

### Task 2: Put every Hyperstim-native Lua facility under `kp.*`

Owner: native Lua registrations and compatibility only (`src/api/{memory,entity,
structs,output,timers,strings,compat}.*`, related host API data/docs/tests).

1. Reuse each existing single-table registration; relocate its public root from
   `kotor` to `kp` without wrapper duplication.
2. Remove native `kotor.*` aliases and bare compatibility promotions, including
   the `log`/`log_msg` collision path.
3. Keep callbacks/events under explicit `kp.events.*`; treat legacy global
   callbacks only as documented compatibility if they cannot be removed without
   breaking the existing event dispatcher.
4. Add a namespace contract test: public native names occur only below `kp`,
   direct engine names only through `nwscript.call`.
5. Update user-facing Lua/API docs to describe provenance and the breaking API
   migration precisely.

### Task 3: Separate harness TOML ownership and document the driver contracts

Owner: Python harness config/scenario parsing, scenario tests, and harness docs.

1. Specify three scopes: runtime `<game>/hyperstim.ini`, optional operator
   `kotorphasor.toml`, and immutable route `scenarios/**/*.toml`.
2. Use one reader and precedence policy for optional workspace TOML; do not move
   supported-build facts into mutable configuration.
3. Normalize legacy scenario `[settings]` and resource-backed steps into an
   explicit validated execution/resource/step model, preserving checked-in
   route behavior and direct nested scenario paths.
4. Make scenario discovery and offline parsing recursive; test every shipped
   route including `cursed/` before any live game session.
5. Publish separate driver and scenario TOML references, correct ineffective INI
   examples, and register the existing Python offline gates alongside CTest/CI.

## Verification order

1. Focused routine/support namespace tests.
2. Full configured CMake build at `-j3` and CTest.
3. Python harness offline and world tests, including recursive scenario parsing.
4. One serialized, opt-in K1 live harness smoke only after the offline gates;
   retain a continuous recording only when the run establishes a functional
   behavior not already evidenced.

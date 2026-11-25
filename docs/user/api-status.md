# API status

Status of every KotorJIT Lua host API, event callback, codecave hook, engine routine bridge, and native-call surface. Verified both offline (`ctest`, Python self-tests) and live in-game via the procedural state-matrix suite (`tools/kotor_statematrix/`) on:

- **KOTOR 1 GOG Windows** (`k1_gog_103`, Wine + Xvfb): **392 passed, 0 failed, 0 crashed, 0 VM stack-balance failures** (`818` total probes: `426` destructiveness/context-skipped).
- **KOTOR 2 GOG Aspyr Windows** (`k2_gog_aspyr`, Wine + Xvfb): **429 passed, 0 failed, 0 crashed, 0 VM stack-balance failures** (`923` total probes: `494` destructiveness/context-skipped).
- **KOTOR 2 Steam Linux** (`k2_steam_linux`, native i386 ELF): `libkotorjit.so` verified to load, classify `k2_steam_linux`, resolve `36/286` sites and `13/13` VM stack sites (`layout=resolved`), and install its 3 core detours (`vm.run_script`, `app.server_main_loop`, `app.client_main_loop`); full headless gameplay under Xvfb requires an active Steam client IPC session (`SteamAPI_Init()`).

The catalogs in [../lua-api.md](../lua-api.md), [../nwscript-api.md](../nwscript-api.md), `data/hostapi.toml`, and `data/signatures/native_manifest.json` define the full contract.

---

## Status key

| Tag | Meaning |
|---|---|
| **Live** | Executed and verified in a running K1/K2 process |
| **Live (A/B)** | Return value / blocking effect verified live with paired override vs allow runs |
| **Bound** | Registered and resolved; offline-tested or build-dependent |
| **Guard-refused** | Intentionally rejected at runtime with an explicit error on unsupported builds |

---

## Console commands

| Command | Status |
|---|---|
| `lua exec <code>` | **Live** |
| `lua status` | **Live** |
| `lua reload` | **Live** (triggers `sync_demand_hooks()`) |

---

## Script metadata and hook introspection

| Name | Status |
|---|---|
| `priority` | **Live** |
| `kp.print(...)` | **Live** |
| `kp.host`, `kp.serverapp` | **Bound** |
| `kp.game`, `kp.build` | **Live** (`"k1"` / `"k2"`, `"k1_gog_103"` / `"k2_gog_aspyr"` / etc.) |
| `kp.api_version` | **Live** (`2`) |
| `kp.version` | **Live** (`"0.1.0"`) |
| `kp.vm_ready()` | **Live** (true once VM objects and command table are captured) |
| `kp.hooks.active()` | **Live** (array of currently attached detour site names) |
| `kp.events` (113 `On*` integers) | **Live** |
| `kp.events.register`, `kp.events.unregister` | **Live** (`register` activates demand hooks dynamically on load/reload) |
| LuaJIT standard libraries | **Live** |
| `kp.camera.capabilities()`, `kp.camera.snapshot()` | **Bound** (profile-gated read-only snapshot; reports unavailable on builds without a camera profile) |

---

## Demand-driven codecaves & call sites

To minimize runtime overhead and isolate unrelated engine paths, KotorJIT uses **demand-driven lazy default hooking** (`hook_all_events` / `KP_HOOK_ALL_EVENTS` opts back into eager hooking of all resolved detours):

- **Core default detours active at boot (7 on K1/K2 GOG)**: `vm.run_script`, `app.server_main_loop`, `console.do_console`, `app.client_main_loop` (plus K2 Linux `client.frame_wrapper`), `vm.save_script_situation`, `vm.load_script_situation`, and `creature.ai_action_move_to_point`.
- **On-demand event detours attached automatically when a loaded script subscribes** (and detached when unsubscribed on `lua reload`): `event.creature`, `event.door`, `event.placeable`, `event.trigger`, `event.module`, `event.area`, `event.encounter`, `event.aoe`, `event.store`, `event.waypoint`, `dialog.check_script` (`OnDialogConditional`), and `vm.run_script_situation` (`OnScriptSituation`).
- **Call sites (13 VM stack/dispatch sites + engine destructors)**: `vm.execute_command`, `vm.stack_{push,pop}_{integer,float,string,object,vector,engine_structure}`, `vmcmd.destroy_game_defined_structure`, `exo.string_dtor` — all 13 VM sites resolved on `k1_gog_103`, `k2_gog_aspyr`, and `k2_steam_linux`.

---

## Events (113 constants)

All **113** event constants in `data/events.toml` are wired and subscribable on builds that resolve their dispatch paths (no dead-name stubs remain):

- **Lifecycle & runtime**: `OnScriptLoad` (**Live**), `OnScriptUnload` (**Live**), `OnTick` (**Live**), `OnRunScript` (**Live A/B** — returning `false` blocks engine `RunScript` and yields `ran=false` in `OnRunScriptDone`, whereas returning `true` executes the engine script and yields `ran=true`), `OnRunScriptDone` (**Live A/B**), `OnConsoleCommand` (**Live**), `OnSave` (**Live**), `OnLoad` (**Live**).
- **Resumed script situations & dialog conditionals**: `OnScriptSituation` (**Live** on K1 via `vm.run_script_situation`), `OnDialogConditional` (**Bound** / demand-hooked via `dialog.check_script`).
- **Player spawn**: `OnPlayerSpawn` (**Live** on both K1 and K2, synthesized when `OnCreatureSpawn` fires for the player creature).
- **Previously `vm.run_script`-routed events (14 wired)**: `OnCreatureHeartbeat` (**Live** K1 & K2), `OnCreatureSpawn` (**Live** K1 & K2), `OnCreatureStateScript` (**Live** K2), `OnTriggerHeartbeat` (**Live** K2), `OnClientRequestedScript` (**Live** K1), plus `OnCreatureDamaged`, `OnCreatureDeath`, `OnCreatureEndCombatRound`, `OnCreatureEndDialogue`, `OnPlaceableEndDialogue`, `OnTriggerTrapTriggered`, `OnAreaTransitionFail`, `OnItemUse` (**Bound** via vtable/resref matching).
- **Native `EventHandler` events (Creature, Module, Area, Door, Placeable, Trigger, Encounter, AoE, Store, Waypoint)**: all demand-hooked and subscribable; `OnModuleLoad` (**Live** K1 & K2), `OnAreaEnter` (**Live** K1 & K2) verified live in-game, remaining entity callbacks **Bound**.

---

## Host functions (`kp.*` & `nwscript.*`)

| Group | Functions | Status |
|---|---|---|
| `kp.mem` | `readbit`, `readbyte`, `readchar`, `readword`, `readshort`, `readdword`, `readint`, `readfloat`, `readdouble`, `readstring`, `readwidestring`, `write*`, `findsig`, `readbytes`, `writebytes`, `readable`, `writable`, `base` | **Live** (`allow_code_writes` spec-only) |
| `kp.native` | `list()`, `resolve(site_or_sig)`, `bind(target, abi)`, `call(target, conv, ...)` | **Live** (signature/site backed + fault-guarded via `kp::runtime::guard_call`; `133` code sites in `data/signatures/native_manifest.json`) |
| `kp.struct` | `at`, `view`, `types`, `fields`, `typeof`, `address`, `valid`, `size`, `how_to_obtain`, `allow_unverified_writes`, `totable`, `writes_performed` | **Live** on K1; **Guard-refused** on K2 (`K1 32-bit layouts only` runtime guard) |
| `kp.obj` | `ready`, `valid`, `get`, `pc`, `self`, `module`, `party`, `party_size`, `party_member`, `party_slot`, `is_party_member`, `is_pc`, `name`, `tag`, `position`, `type`, `area`, `faction`, `find`, `in_area`, `near`, `create`, `destroy`, `INVALID` (plus handle methods) | **Live** (`address`, `typed_address`, `typename`, `move` spec-only) |
| `kp.timer` | `after`, `every`, `after_ticks`, `cancel`, `list`, `tick`, `clock`, `registertimer`, `removetimer` | **Live** |
| `kp.str` | `split`, `cmdsplit`, `tokenizestring`, `tokenizecmdstring` | **Live** (`cexo`, `strref` spec-only) |
| `kp.*` misc | `build`, `vm_ready`, `routine`, `routines`, `engine_type`, `gametime`, `gamestate`/`game_speed`, `speed`, `vec`, `version`, `gamedir`, `time`, `diagnostic`, `console`, `feedback` | **Live** |
| `nwscript` | `call(name, ...)`, `with_caller(id, fn)`, `last_stack_balance()` | **Live** |

---

## Engine routines (`nwscript.call`) & stack-balance checking

- **K1 (`data/routines/k1.json`)**: `769 / 772` engine routines bound and callable (`AssignCommand`, `DelayCommand`, `ActionDoCommand` omitted in favor of `nwscript.with_caller` and `kp.timer.*`). **358/358** safe procedural probes passed live on `k1_gog_103` with `nwscript.last_stack_balance().balanced == true`.
- **K2 (`data/routines/k2.json`)**: `874 / 877` engine routines bound (`0` undocumented routines, `234` default parameters recovered from TSL `nwscript.nss`). Live i386 `ExecuteCommand` bound decoding supports K1 (`cmp edx, imm32`), K2 Windows (`cmp [ebp+8], imm32` = `0x36D` / `877`), and K2 Linux (`cmp eax, imm32; jg` = `0x36D` / `877`), and Linux i386 builds use SysV `cdecl` (`this` on stack) for engine C++ method calls (`KP_ENGINE_METHOD_CALL`). **395/395** safe procedural probes passed live on `k2_gog_aspyr` with `nwscript.last_stack_balance().balanced == true`.
- **VM stack-pointer tracking**: `nwscript.call` records `sp_before` and `sp_after` from `CVirtualMachineInternal.stack_pointer` (`+0x1AC` on i386, resolved via `vm.stack_pointer` field site) and raises a Lua error if a handler leaves the VM argument stack unbalanced.

### Observed game-binary bugs / context requirements (disassembly-verified)

- **K1 `RandomName` (`0x00541a30` -> `0x007113e5`)**: BioWare K1 loads an unloaded `"names"` LTR resource (`0x74872c`) and NULL-dereferences `[eax+0x4c] -> 0x8`.
- **K1 `GetFactionWorstAC` (`0x005bf350`) / `GetFactionBestAC` (`0x005bf490`)**: BioWare K1 passes `0` as attacker into `CSWSCreatureStats::GetArmorClassVersus` (`0x005ad0e0`), which unconditionally dereferences `[ebp+0x9c8]`.
- **K1 `GetLastAssociateCommand` (routine `321` @ `0x00409eb0`)**: 3-byte BioWare stub `xor eax, eax; ret 8` returning `0` without touching the VM stack.
- **K2 `GetRandomDestination` (`0x007AFCD0` -> `0x007AFE15`)**: Obsidian/BioWare K2 computes `rand() % (2 * rangeLimit)` using `idiv ecx`; passing `rangeLimit == 0` causes an integer divide-by-zero exception (`0xC0000094`). Supply a positive `rangeLimit` (e.g. `GetRandomDestination(creature, 5)`).
- **K2 `GetItemComponent`, `GetItemComponentPieceValue`, `GetChemicals`, `GetChemicalPieceValue`**: Workbench UI context queries; the engine handler at `0x00793430` (`GetItemComponent`) explicitly returns `-2001` (`0xFFFFF82F`) unless an item is open in the upgrade UI.
- All hard faults raised inside game calls via `nwscript.call` or `kp.native.call` are contained by the vectored exception / signal fault guard (`src/runtime/fault_guard.cpp`) without crashing the host process.

---

## Standalone reusable tooling

- **`tools/sigforge/`**: Project-agnostic PE/ELF/Mach-O signature extraction, masked matching, `xref_thunk` resolution, and cross-build transfer engine (`5/5` unit tests passing).
- **`tools/statematrix/`**: Project-agnostic procedural multi-universe state-matrix test framework supporting safety-tier classification, paired A/B event verification, trace-driven synthesis, crash recovery, and JSON/Markdown reporting (`4/4` unit tests passing).
- **`tools/kotor_statematrix/`**: KOTOR adapter driving `statematrix` live against `kpharness`.

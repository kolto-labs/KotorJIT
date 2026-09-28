# KotorPhasor Lua side audit

This is a read-only static classification of the Lua registrations in the isolated worktree [lua-boundary-validation](/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation). The machine-readable inventory is [lua-api.json](/home/brunner56/kp-live-20260922/side-audit/lua-api.json). Source links below point to the exact callback implementation site.

The audit covers 136 distinct exposed names in 116 inventory records. It includes the native `src/api` registrations, NWScript bridge entry points, userdata metamethod callbacks, and runtime `kp.speed`/`kp.game_speed`. It deliberately leaves compatibility event registration and dispatch, `kp.scripts`, and `kp.harness` to the other delegated audits.

The classification is about the logical engine side reached by the implementation. KOTOR normally embeds client and server objects in the same process. A Lua state, callback thread, or namespace name does not establish a side. `shared_vm_process_local` means the callback acts on the injected process/VM or a caller-supplied address without enough information to identify a client/server owner. `unresolved_per_native` is used where a generic bridge dispatches native routines whose implementations are outside this repository.

## Coverage and counts

| Classification | Inventory records | Exposed names |
|---|---:|---:|
| `server_side` | 33 | 33 |
| `client_side` | 9 | 9 |
| `both_client_server` | 4 | 4 |
| `shared_vm_process_local` | 47 | 67 |
| `no_engine_io` | 20 | 20 |
| `unresolved_per_native` | 3 | 3 |
| **Total** | **116** | **136** |

The 20-name difference between records and names comes from registrations that use one callback mechanism for exact same-implementation aliases: the generated memory scalar readers/writers and the four engine-structure handle metatables. The JSON keeps every exposed name in the `names` array and identifies the callback that owns it.

The generated routine catalog contains 772 K1 entries and 877 K2 entries. The generic bridge reports 769 callable K1 routines and 803 callable K2 routines in the repository's own documentation/comments. The three K1 and 74 K2 catalog entries that are not callable are outside the Lua bridge's callable set; `AssignCommand`, `DelayCommand`, and `ActionDoCommand` are explicitly rejected because their action-closure argument cannot be represented by this bridge.

## Findings by API surface

The client-primary surfaces are the read-only chase camera snapshot, client model scale operations, and client model animation query/cue. Their implementation follows client chains or calls client model setters directly. A model capture carrying an ownership token can perform a conditional server identity check before the client operation; the ordinary snapshot path does not read a server object. See [camera_lua.cpp](/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/api/camera_lua.cpp:51), [model.cpp](/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/api/model.cpp:52), and [animation.cpp](/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/api/animation.cpp:60). `kp.model.identify` and `kp.model.matches` are `both_client_server` because the `windows-k1-gog` profile has an optional server identity site, while the macOS profiles fall back to the client actor chain. `kp.model.snapshot`, `resize`, `restore`, and animation refresh remain client-primary with that conditional validation detail recorded in JSON.

The server-only surfaces are the object/party wrappers under `kp.obj`, server placeable motion (`kp.motion.capture`, `relocate`, `restore`, `observe`), the server-loop timer scheduler, and `kp.speed`. The object wrappers call named engine routines such as `GetIsObjectValid`, `GetObjectByTag`, `GetPosition`, and `GetPartyMemberByIndex` through [entity.cpp](/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/api/entity.cpp:22). Motion is explicit in [motion.hpp](/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/api/motion.hpp:8): lookup is `CServerExoApp::GetPlaceableByGameObjectID` and the only setter is `CSWSObject::SetPosition`. The timer callback is pumped from the server main-loop path, and `kp.speed` changes the server tick multiplier in [hook_bodies.cpp](/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/runtime/hook_bodies.cpp:1342).

`kp.game_speed` is client-side in this audit. Its callback calls `EngineAdapter::set_speed`; the K1 adapter applies the scale through `client.set_game_speed`/`CClientExoAppInternal` in [engine_k1.cpp](/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/harness/engine_k1.cpp:1669). This is distinct from `kp.speed`, which scales server-loop ticks.

`kp.projectiles` is mixed. The service counters and record access are process-local, while native configuration/interception traverses both the server PC identity and client creature/resource/model state. The native path is visible in [projectiles_native.cpp](/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/api/projectiles_native.cpp:61), [projectiles_native.cpp](/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/api/projectiles_native.cpp:109), and [projectiles_native.cpp](/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/api/projectiles_native.cpp:155).

`kp.mem.*` and `kp.struct.*` are intentionally process-local/side-agnostic. They read or write an address supplied by Lua, or a view produced by an externally installed resolver. No address value alone proves whether the bytes belong to the client or server object graph. In this worktree no call to `structs::set_address_resolver` was found, so `kp.struct.view` is additionally marked `unresolved_per_native`; `kp.struct.at` remains explicitly address-backed. The direct memory funnel is [memory.cpp](/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/api/memory.cpp:120), and typed field reads/writes are [structs.cpp](/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/api/structs.cpp:572) and [structs.cpp](/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/api/structs.cpp:670).

Pure value APIs (`kp.vec`, `kp.tokenizestring`, `kp.tokenizecmdstring`) have no engine I/O. `kp.diagnostic` only logs. `kp.console` writes the process-local devtools console/output buffer when bound: the runtime binds `devtools_output` at [hook_bodies.cpp](/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/runtime/hook_bodies.cpp:781), and that writer appends to `devtools::console().output` at [hook_bodies.cpp](/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/runtime/hook_bodies.cpp:841). A later overlay may render that buffer in the client, while the unbound path logs to the process. `kp.feedback` is `unresolved_per_native`: its VM calls and intended client-visible feedback effect are source-proven, but the native handlers are outside this repository, so exact side ownership and routing remain unresolved.

## NWScript bridge boundary

The only direct engine-routine entry point is `nwscript.call(name, ...)` in [routines.cpp](/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/api/routines.cpp:373). It reverses arguments onto the VM stack, calls `CSWVirtualMachineCommands::ExecuteCommand`, and pops typed results. That implementation proves VM dispatch and marshalling, not the logical side of each native routine. The audit therefore does not label the bridge blanket server-side.

The JSON contains a small explicit native-routine evidence section for routines relevant to the side question:

- `CreateObject` (ID 243 in both catalogs) is `server_side` with `semantic_only` confidence because the generated signature and use mean server-world object creation, while the native handler is not in this repository.
- `SetGlobalFadeIn` (719) and `SetGlobalFadeOut` (720) are `unresolved_per_native` with `unverified` confidence. Their names suggest a client-visible fade, but there is no native handler body or client call chain here. They must not be reported as verified client-facing dispatch based on the name alone.
- `GetPosition` is recorded as a semantic server-side example because `kp.obj` uses it for server object queries, while the generic bridge itself remains routine-specific.

A script that combines `CreateObject` with a `kp.animation` call is mixed by composition: object creation is server-side and the animation callback operates on client model state. That script-level combination does not make the `kp.animation` registration itself server-only or client-only.

`nwscript.with_caller` writes and restores `CSWVirtualMachineCommands.has_caller/caller_id` around a Lua closure in [routines.cpp](/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/api/routines.cpp:524), so it is `shared_vm_process_local`; the call made inside the closure retains the native routine's own side semantics. `nwscript.last_trace` is a thread-local bridge diagnostic and performs no engine I/O.

## Limits and unresolved points

This is source classification, not live proof. It does not establish that a profile is bound, that a hook installed, or that an engine call succeeded on a particular build. The JSON keeps the exact source path, callback, underlying object/hook, and reason for every included registration so a later native/profile audit can replace semantic-only or unresolved labels with evidence.

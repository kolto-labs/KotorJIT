# Auxiliary Lua API side audit

## Scope and conclusion

This report covers the callable registrations intentionally excluded from `lua-api.json`: five `kp.scripts` namespace functions plus `kp.scriptname` and `kp.scriptdir`, two `kp.events` functions, all 53 `kp.harness` functions (including the `equipment_screen` alias), and three direct compat callables (`kp.print`, `kp.gamedir`, `kp.time`). It also checks direct callable registrations in `src/api` and `src/runtime` against the union. The Lua/native registration seam is process-local. `engine_side` follows the concrete root harness command and adapter classification or the local result store; it is not inferred from callback thread or process role.

| Surface | Callable count | Registration | Native callback/call path | API seam |
|---|---:|---|---|---|
| `kp.scripts` | 7 | `src/api/scripts_lua.cpp:150-171` | `lua::Host` lifecycle/query | processlocal |
| `kp.events` | 2 | `src/api/compat.cpp:942-945` | `lua::Script::bind_callback` | processlocal; callback later event-dependent |
| `kp.harness` | 53 | `src/api/compat.cpp:965-984` | `kp::harness::EngineAdapter` and stored-result accessors | processlocal |
| compat helpers | 3 | `src/api/compat.cpp:948-961` | log, captured path, monotonic clock | processlocal |

`kp.events` also installs 111 numeric event constants at `src/api/compat.cpp:938-940` from `src/generated/compat_events.inc`. Those constants are metadata, not callable rows. `kp.events.register` rejects dead/non-dispatchable contracts with `false`; a constant name alone does not establish a side.

## Callable registrations

| Name | Callback | Implementation source | Registration source | Side at API seam | Concrete engine side / local path | Confidence |
|---|---|---|---|---|---|---|
| `kp.scripts.list` | `l_list` | `src/api/scripts_lua.cpp:57` | `src/api/scripts_lua.cpp:155` | `processlocal` | processlocal | high |
| `kp.scripts.load` | `l_load` | `src/api/scripts_lua.cpp:90` | `src/api/scripts_lua.cpp:156` | `processlocal` | processlocal | high |
| `kp.scripts.unload` | `l_unload` | `src/api/scripts_lua.cpp:91` | `src/api/scripts_lua.cpp:157` | `processlocal` | processlocal | high |
| `kp.scripts.reload` | `l_reload` | `src/api/scripts_lua.cpp:92` | `src/api/scripts_lua.cpp:158` | `processlocal` | processlocal | high |
| `kp.scripts.result` | `l_result` | `src/api/scripts_lua.cpp:94` | `src/api/scripts_lua.cpp:159` | `processlocal` | processlocal | high |
| `kp.scriptname` | `l_scriptname` | `src/api/scripts_lua.cpp:120` | `src/api/scripts_lua.cpp:168` | `processlocal` | processlocal | high |
| `kp.scriptdir` | `l_scriptdir` | `src/api/scripts_lua.cpp:129` | `src/api/scripts_lua.cpp:170` | `processlocal` | processlocal | high |
| `kp.events.register` | `l_register_callback` | `src/api/compat.cpp:101` | `src/api/compat.cpp:943` | `processlocal` | event_dependent | high |
| `kp.events.unregister` | `l_unregister_callback` | `src/api/compat.cpp:149` | `src/api/compat.cpp:945` | `processlocal` | event_dependent | high |
| `kp.harness.dialog_skip` | `l_h_dialog_skip` | `src/api/compat.cpp:250` | `src/api/compat.cpp:966` | `processlocal` | server mutation selected through client UI | high |
| `kp.harness.dialog_abort` | `l_h_dialog_abort` | `src/api/compat.cpp:251` | `src/api/compat.cpp:966` | `processlocal` | client primary, server fallback | high |
| `kp.harness.dialog_continue` | `l_h_dialog_continue` | `src/api/compat.cpp:252` | `src/api/compat.cpp:966` | `processlocal` | client dialog selection with server validation | high |
| `kp.harness.unpause_timers` | `l_h_unpause_timers` | `src/api/compat.cpp:253` | `src/api/compat.cpp:967` | `processlocal` | both | high |
| `kp.harness.advance_tutorial` | `l_h_advance_tutorial` | `src/api/compat.cpp:254` | `src/api/compat.cpp:967` | `processlocal` | client GUI | high |
| `kp.harness.finish_hidden_tutorial` | `l_h_finish_hidden_tutorial` | `src/api/compat.cpp:255` | `src/api/compat.cpp:967` | `processlocal` | client GUI | high |
| `kp.harness.dismiss_status_summary` | `l_h_dismiss_status_summary` | `src/api/compat.cpp:256` | `src/api/compat.cpp:968` | `processlocal` | client GUI | high |
| `kp.harness.dismiss_messagebox` | `l_h_dismiss_messagebox` | `src/api/compat.cpp:257` | `src/api/compat.cpp:968` | `processlocal` | client GUI | high |
| `kp.harness.dismiss_container` | `l_h_dismiss_container` | `src/api/compat.cpp:258` | `src/api/compat.cpp:969` | `processlocal` | client GUI | high |
| `kp.harness.take_all_container` | `l_h_take_all_container` | `src/api/compat.cpp:259` | `src/api/compat.cpp:969` | `processlocal` | client GUI | high |
| `kp.harness.accept_party_selection` | `l_h_accept_party_selection` | `src/api/compat.cpp:260` | `src/api/compat.cpp:970` | `processlocal` | both | high |
| `kp.harness.speed` | `l_h_speed` | `src/api/compat.cpp:266` | `src/api/compat.cpp:970` | `processlocal` | client timers | high |
| `kp.harness.fixed_step` | `l_h_fixed_step` | `src/api/compat.cpp:280` | `src/api/compat.cpp:970` | `processlocal` | both | high |
| `kp.harness.new_game` | `l_h_new_game` | `src/api/compat.cpp:261` | `src/api/compat.cpp:971` | `processlocal` | client GUI | high |
| `kp.harness.chargen_select_class` | `l_h_chargen_select_class` | `src/api/compat.cpp:501` | `src/api/compat.cpp:971` | `processlocal` | client GUI | high |
| `kp.harness.chargen_begin_play` | `l_h_chargen_begin_play` | `src/api/compat.cpp:262` | `src/api/compat.cpp:971` | `processlocal` | client GUI | high |
| `kp.harness.chargen_stage` | `l_h_chargen_stage` | `src/api/compat.cpp:507` | `src/api/compat.cpp:972` | `processlocal` | client GUI | high |
| `kp.harness.adapter_name` | `l_h_adapter_name` | `src/api/compat.cpp:515` | `src/api/compat.cpp:972` | `processlocal` | process-local | high |
| `kp.harness.dialog` | `l_h_dialog` | `src/api/compat.cpp:529` | `src/api/compat.cpp:972` | `processlocal` | both, read-only | high |
| `kp.harness.reply` | `l_h_reply` | `src/api/compat.cpp:523` | `src/api/compat.cpp:972` | `processlocal` | client dialog selection with server validation | high |
| `kp.harness.dialog_clear_sound_wait` | `l_h_dialog_clear_sound_wait` | `src/api/compat.cpp:263` | `src/api/compat.cpp:973` | `processlocal` | server mutation selected through client UI | high |
| `kp.harness.clear_auto_pause` | `l_h_clear_auto_pause` | `src/api/compat.cpp:264` | `src/api/compat.cpp:973` | `processlocal` | server | high |
| `kp.harness.warp` | `l_h_warp` | `src/api/compat.cpp:874` | `src/api/compat.cpp:974` | `processlocal` | server | high |
| `kp.harness.load_save` | `l_h_load_save` | `src/api/compat.cpp:880` | `src/api/compat.cpp:974` | `processlocal` | both plus local filesystem | high |
| `kp.harness.save` | `l_h_save` | `src/api/compat.cpp:886` | `src/api/compat.cpp:974` | `processlocal` | client-to-server request | high |
| `kp.harness.door_use` | `l_h_door_use` | `src/api/compat.cpp:893` | `src/api/compat.cpp:975` | `processlocal` | client-to-server request plus server validation | high |
| `kp.harness.door_commit_open` | `l_h_door_commit_open` | `src/api/compat.cpp:897` | `src/api/compat.cpp:975` | `processlocal` | server | high |
| `kp.harness.door_security` | `l_h_door_security` | `src/api/compat.cpp:901` | `src/api/compat.cpp:975` | `processlocal` | client-to-server request plus server readback | high |
| `kp.harness.attack` | `l_h_attack` | `src/api/compat.cpp:905` | `src/api/compat.cpp:975` | `processlocal` | client-to-server request plus server validation | high |
| `kp.harness.take_door_security_result` | `l_h_take_door_security_result` | `src/api/compat.cpp:805` | `src/api/compat.cpp:976` | `processlocal` | process-local stored result | high |
| `kp.harness.set_party_leader` | `l_h_set_party_leader` | `src/api/compat.cpp:758` | `src/api/compat.cpp:976` | `processlocal` | client party | high |
| `kp.harness.take_party_leader_result` | `l_h_take_party_leader_result` | `src/api/compat.cpp:820` | `src/api/compat.cpp:977` | `processlocal` | process-local stored result | high |
| `kp.harness.use_item` | `l_h_use_item` | `src/api/compat.cpp:764` | `src/api/compat.cpp:977` | `processlocal` | client action request | high |
| `kp.harness.take_use_item_result` | `l_h_take_use_item_result` | `src/api/compat.cpp:832` | `src/api/compat.cpp:977` | `processlocal` | process-local stored result | high |
| `kp.harness.equip_item` | `l_h_equip_item` | `src/api/compat.cpp:772` | `src/api/compat.cpp:978` | `processlocal` | server mutation through client player selection | high |
| `kp.harness.take_equip_item_result` | `l_h_take_equip_item_result` | `src/api/compat.cpp:844` | `src/api/compat.cpp:978` | `processlocal` | process-local stored result | high |
| `kp.harness.auto_levelup` | `l_h_auto_levelup` | `src/api/compat.cpp:784` | `src/api/compat.cpp:978` | `processlocal` | server mutation through client player selection | high |
| `kp.harness.take_auto_levelup_result` | `l_h_take_auto_levelup_result` | `src/api/compat.cpp:857` | `src/api/compat.cpp:979` | `processlocal` | process-local stored result | high |
| `kp.harness.equipment` | `l_h_equipment` | `src/api/compat.cpp:909` | `src/api/compat.cpp:979` | `processlocal` | client GUI | high |
| `kp.harness.movies` | `l_h_movies` | `src/api/compat.cpp:285` | `src/api/compat.cpp:979` | `processlocal` | client playback policy | high |
| `kp.harness.movies_enabled` | `l_h_movies_enabled` | `src/api/compat.cpp:554` | `src/api/compat.cpp:980` | `processlocal` | process-local stored flag | high |
| `kp.harness.state` | `l_h_state` | `src/api/compat.cpp:448` | `src/api/compat.cpp:980` | `processlocal` | both, read-only aggregate | high |
| `kp.harness.missing_sites` | `l_h_missing_sites` | `src/api/compat.cpp:559` | `src/api/compat.cpp:980` | `processlocal` | process-local | high |
| `kp.harness.globals` | `l_h_globals` | `src/api/compat.cpp:710` | `src/api/compat.cpp:981` | `processlocal` | server read-only | high |
| `kp.harness.journal` | `l_h_journal` | `src/api/compat.cpp:736` | `src/api/compat.cpp:981` | `processlocal` | server read-only | high |
| `kp.harness.ping` | `l_h_ping` | `src/api/compat.cpp:699` | `src/api/compat.cpp:982` | `processlocal` | process-local | high |
| `kp.harness.status` | `l_h_status` | `src/api/compat.cpp:649` | `src/api/compat.cpp:982` | `processlocal` | process-local runtime metadata | high |
| `kp.harness.events` | `l_h_events` | `src/api/compat.cpp:565` | `src/api/compat.cpp:982` | `processlocal` | process-local event transport | high |
| `kp.harness.screenshot` | `l_h_screenshot` | `src/api/compat.cpp:610` | `src/api/compat.cpp:982` | `processlocal` | client renderer plus filesystem | high |
| `kp.harness.take_screenshot_result` | `l_h_take_screenshot_result` | `src/api/compat.cpp:621` | `src/api/compat.cpp:982` | `processlocal` | process-local stored result | high |
| `kp.harness.reload` | `l_h_reload` | `src/api/compat.cpp:643` | `src/api/compat.cpp:983` | `processlocal` | process-local script host | high |
| `kp.harness.quit` | `l_h_quit` | `src/api/compat.cpp:637` | `src/api/compat.cpp:983` | `processlocal` | process lifecycle | high |
| `kp.harness.equipment_screen` | `l_h_equipment` | `src/api/compat.cpp:909` | `src/api/compat.cpp:984` | `processlocal` | client GUI | high |
| `kp.print` | `lua_print_to_log` | `src/api/compat.cpp:46` | `src/api/compat.cpp:948` | `processlocal` | processlocal | high |
| `kp.gamedir` | `l_kp_gamedir` | `src/api/compat.cpp:166` | `src/api/compat.cpp:958` | `processlocal` | processlocal | high |
| `kp.time` | `l_kp_time` | `src/api/compat.cpp:176` | `src/api/compat.cpp:960` | `processlocal` | processlocal | high |

## Reconciled semantics and architecture

- `kp.scripts.list` and `result` read process-wide host state. `load`, `unload`, and `reload` call `Host::request` (`src/lua/host.cpp:698-735`) and return request ids; `Host::service_requests` (`src/lua/host.cpp:794-815`) performs the operation later at a host lifecycle service boundary. `kp.scriptname` reads `lua::Script::owner` and returns `nil` for the console state; `kp.scriptdir` reads host configuration.
- `kp.events.register` resolves the event constant and handler immediately, then stores the Lua registry reference with `lua::Script::bind_callback`. `kp.events.unregister` clears that reference. The later callback’s logical side is the event dispatch site, which is why these API calls are `processlocal` with an event-dependent callback path.
- Harness classifications follow `/home/brunner56/kp-live-20260922/side-audit/harness.json` and the traced `src/harness/engine_k1.cpp` implementations. Client GUI rows include new-game/chargen/tutorial/dialog-panel/equipment/container paths; server rows include globals/journal/warp and server mutations; request rows preserve client-to-server or server-validation boundaries; both rows preserve combined client/server reads or timer operations; local rows cover status/ping/adapter metadata/event transport/movie flags/stored results.
- `kp.harness.equipment` and `kp.harness.equipment_screen` invoke the same `l_h_equipment` callback and `GameAdapter::equipment_screen` implementation. `take_*_result` accessors report stored/deferred transaction results and are process-local at the API surface.
- The source distinguishes process role, logical embedded engine object, and caller thread. A split client can have client/render state and an in-process support server while authoritative server state is remote. Engine-side labels therefore follow concrete implementation paths and do not claim that a Lua callback thread proves a network role.

## Public callable registrations absent from lua-api.json

`lua-api.json` delegates `kp.events`, `kp.scripts`, and `kp.harness`. The direct compat scan also found three callable fields installed by `compat::install` that were absent from that manifest. They are included as ordinary rows above and remain listed here as manifest omissions:

| Name | Callback | Implementation | Registration | Side |
|---|---|---|---|---|
| `kp.print` | `lua_print_to_log` | `src/api/compat.cpp:46` | `src/api/compat.cpp:948` | `processlocal` |
| `kp.gamedir` | `l_kp_gamedir` | `src/api/compat.cpp:166` | `src/api/compat.cpp:958` | `processlocal` |
| `kp.time` | `l_kp_time` | `src/api/compat.cpp:176` | `src/api/compat.cpp:960` | `processlocal` |

The other fields installed by `compat::install` (`host`, `serverapp`, `game`, `api_version`, `version`) are metadata values rather than callable APIs. The 111 event constants and generated NWScript routine catalog are separate metadata/catalog surfaces. This report does not duplicate TCP/socket commands.

## Audit limits

This is static source and manifest evidence only. It establishes registration, callback wiring, and documented execution boundaries; it does not prove that a particular binary resolved the binding, that a live game reached the hook, or that an external client observed the operation.

## Execution-thread correction after independent quality review

All Lua/native API calls execute on the current Lua caller thread. Registration does not marshal them to a server/engine thread. This includes script listing, lifecycle request submission, event registration, and harness convenience callbacks. Initial script loading can occur during startup. `Host::request` queues lifecycle work for a later host service boundary; a registered event handler runs on that event's dispatch thread; deferred harness operations and screenshots are serviced on their game-loop/post-frame paths. `HookBodyScope` marks a native fault-guard boundary, not a thread dispatcher. Logical client/server object ownership remains a separate classification.

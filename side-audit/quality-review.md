# Side audit accuracy and quality review

Date: 2026-09-27. This review follows the approved static completeness gate in `spec-review.md`. It is read-only: no builds, engine/Wine/display/harness/lock actions, or product edits.

## Result

The corrected inventories pass the source-side accuracy review. The auxiliary rows now describe the actual current Lua caller thread, while lifecycle servicing and event callback dispatch are recorded as separate deferred paths. The side labels are traced to the corrected root harness paths. The review also records conditional and wording limits for model identity, status/state, native speed, generic NWScript, script presentation effects, and generated native routine routing.

No product fix is indicated. The remaining qualifications are scope limits on static source evidence.

## Finding 1 — corrected execution-thread and deferred-path metadata

**Claim:** The auxiliary callable rows identify the Lua call thread separately from deferred lifecycle servicing and later event dispatch.

**Referents:** corrected [auxiliary-api.json](/home/brunner56/kp-live-20260922/side-audit/auxiliary-api.json), `execution_thread` values; [src/api/scripts_lua.cpp:35-96](/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/api/scripts_lua.cpp:35); [src/api/compat.cpp:101-176](/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/api/compat.cpp:101); [src/lua/host.cpp:698-815](/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/lua/host.cpp:698).

**Checked:** All 65 auxiliary rows carry `execution_thread: current Lua caller thread; the registration does not marshal to another thread`. `Host::request` queues lifecycle work and returns a request id; `Host::service_requests` later drains that queue. `kp.events.register/unregister` bind or clear a Lua registry callback in the current state, and the callback later runs at its event dispatch site. `kp.scripts.list` and `result` read the current host; load/unload/reload enqueue. No `HookBodyScope` or adapter call marshals the original API invocation to another thread. `HookBodyScope` is a fault-guard scope, not a thread scheduler.

**Verdict:** corrected and accurate. The separate deferred fields preserve the lifecycle service boundary and event dispatch boundary without inventing an automatic thread guarantee. The union metadata also reports `missing_names_from_main_manifest_only` as `kp.print`, `kp.gamedir`, and `kp.time`, with `missing_names_from_complete_union: []`.

**Confidence:** high.

## Finding 2 — generated native routine metadata is complete as a catalog, unresolved as handler-side proof

**Claim:** The generated native routine metadata records the callable signature surface without claiming exact native handler ownership.

**Referents:** [native-routines.json](/home/brunner56/kp-live-20260922/side-audit/native-routines.json), `callable_counts`, `distinct_names`, and each routine's `classification` and `reason` fields.

**Checked:** The metadata contains 769 K1 callable signatures, 803 K2 callable signatures, and 806 distinct names across 806 routine rows. Every row is marked `classification: native_handler_unresolved`, with the explicit reason that generated bridge signatures do not prove the native handler's side or routing. Closure/action routines remain explicitly excluded.

**Verdict:** holds. The catalog closes the inventory gap without upgrading generated signatures into client/server or live-handler proof.

**Confidence:** high.

## Finding 3 — status and state are distinct surfaces and must stay named

The TCP `status` command is a read-only aggregate that calls the adapter and combines client GUI/input/timer data with server/runtime data, while Lua `kp.harness.status` returns process/runtime metadata (`phase`, `live`, `pid`, ticks, adapter, missing sites, poison state) from [src/api/compat.cpp:649-695](/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/api/compat.cpp:649). Lua `kp.harness.state` is the combined client/server snapshot path at [src/api/compat.cpp:448-607](/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/api/compat.cpp:448).

The artifacts now distinguish the namespaced surfaces. Quality requirement: do not collapse `kp.harness.status` and TCP `status` into one side label. `kp.harness.status` is process-local metadata; TCP `status` is both/aggregate; `state` is both/aggregate.

Verdict: accurate after preserving the namespace distinction. Confidence: high.

## Finding 4 — client speed and server tick speed are separate controls

`kp.harness.speed` and `kp.game_speed` reach the client game-speed path (`client.set_game_speed`) through [src/harness/engine_k1.cpp:1669-1691](/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/harness/engine_k1.cpp:1669) and [src/runtime/runtime.cpp:31-42](/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/runtime/runtime.cpp:31). `kp.speed` changes the server main-loop repeat scale at [src/runtime/hook_bodies.cpp:1342-1357](/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/runtime/hook_bodies.cpp:1342).

Verdict: corrected artifacts are accurate. A script using `kp.speed` should not be described as changing client timers, and a harness `speed` command should not be described as server tick pacing. Confidence: high.

## Finding 5 — model identity is conditional on the profile

The model artifact correctly describes model operations as client model work and `kp.model.snapshot` as crossing server id to client model state. `kp.model.identify` and `matches` need a conditional qualifier: in [src/api/model.cpp:72-99](/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/api/model.cpp:72), profiles with `sites[4].va` validate a server object identity, while profiles without that optional server site fall back to `actor()` and return client-side identity (`client`, `creature`). The profile is selected and guarded by executable SHA/ABI/width in `Operations::bind`.

Verdict: “server-side” is too absolute for `identify`/`matches`; the accurate wording is “server identity when optional server lookup is present; otherwise client actor identity, with profile-dependent ownership fencing.” This is a documentation precision correction. Confidence: high.

## Finding 6 — generic NWScript routing remains unresolved per native routine

The API artifact correctly refuses a blanket client/server label for `nwscript.call`. [src/api/routines.cpp:373-407](/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/api/routines.cpp:373) dispatches a named command through the VM and marshals values; the native handler bodies are outside this repository. The generated catalogs contain more signatures than the callable bridge exposes, and closure/action routines are intentionally rejected.

Verdict: keep `unresolved_per_native` for the generic bridge. Individual script classifications may describe a known routine’s semantic target, but must not upgrade that to proof of the generic bridge’s side or live native success. Confidence: high.

## Finding 7 — scripts that request presentation effects need downstream wording

The script inventory correctly identifies gameplay calls and mixed demos. For scripts containing `SetGlobalFadeIn/Out`, `MusicBattlePlay`, `SpeakString`, or similar routines, the source proves that a native VM request is made and that the intended semantic effect is presentation. It does not prove a client memory path for the native handler. The inventory already states that exact native routing remains outside bridge metadata in the relevant rows; retain that qualification in summaries and do not call such routines verified client-side implementations.

Verdict: accurate with the existing downstream/unknown qualification. Confidence: medium-high, because native handlers are not in this repository.

## Finding 8 — direct requests, mutations, and stored results are separated

The corrected harness inventory distinguishes request paths (`save`, `door_use`, `door_security`, `attack`), direct server mutations (`warp`, `door_commit_open`, `clear_auto_pause`, `equip_item`, `auto_levelup`), client GUI actions, mixed state reads, and `take_*_result` process-local polling. This matches the adapter traces in [harness.md](/home/brunner56/kp-live-20260922/side-audit/harness.md) and the implementation in [src/api/compat.cpp:758-909](/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/api/compat.cpp:758).

Verdict: holds. The result accessors must remain process-local observations and must not be presented as a second engine mutation. Confidence: high.

## Finding 9 — dead event names are explicit and not implementation proof

The event catalog contains 111 names, with 97 implemented rows (94 server, one client, two process-local lifecycle) and 14 unimplemented/dead rows. The dead names remain constants but registration returns false when no dispatch contract exists, as documented by [src/events/table.cpp:53](/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/events/table.cpp:53) and [src/api/compat.cpp:122](/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/api/compat.cpp:122).

Verdict: holds. No quality defect found. Confidence: high.

## Final quality verdict

The side specification passes the completeness gate and the source-accuracy gate. The corrected auxiliary execution-thread fields and deferred lifecycle/event metadata match the source. The complete callable union has no remaining missing names, and the native routine catalog records K1 769, K2 803, and 806 distinct names while retaining `native_handler_unresolved` limits. Preserve the corrected client/server side labels, the status/state namespace distinction, conditional model identity wording, unresolved generic NWScript routing, downstream presentation caveats, and the 97/14 event count split.

These findings do not require product changes. The quality review is ready for root's consolidated review.

## Grill me, weakest first

1. The corrected execution-thread fields are direct source evidence: queueing a lifecycle request is not a thread hop, and callback registration has no owner-thread marshal; deferred service and dispatch are represented separately.
2. The generated native catalog is complete for its declared signature inputs, but `native_handler_unresolved` is the honest boundary because the repository does not contain every native handler body.
3. Model identity is profile-dependent; its optional server lookup site is visible in the profile array and the branch in `Operations::identify`.
4. All other conclusions are static classification. They do not assert resolved signatures, installed hooks, live game behavior, or external-client acceptance.

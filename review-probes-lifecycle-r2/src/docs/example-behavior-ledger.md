# Example behavior ledger

One row per original example script: 33 retained sources and 8 retired ones.
Each row gives the path, intended behavior, API boundary, the outcome to check,
evidence level and a curation verdict. This ledger recommends. It promotes
nothing. `scripts/demos/catalog.json` still lists no featured entries, and no
manifest live status changes because of this file.

Written 2026-09-27 against these inputs:

- Manifest `tools/tests/examples/manifest.json`, SHA-256 `1ec55bdb…5c30363a`
  (updated 2026-09-27 by the chain-reaction round 4 fix; before that
  `c0dc1cec…28125bac` from the first round 4 bytes,
  `8e787165…bcb9a9ec` from round 3,
  `67b08f4b…d5ef68e3` from the I1 fix, and `f530e825…b420a218`,
  and before the first example fixes `82dab5ef…dd796c22`).
  The `sha` column holds the first 12 hex digits of each entry's `sha256`.
  All 41 current source files hash to their manifest value. If a source hash
  or the manifest hash changes, the affected rows are stale.
- Host receipt `/home/brunner56/kp-live-20260922/example-host-receipt-20260927e.json`
  (SHA-256 `b28ca4bf…1cafd43d`), generated 2026-09-27T23:09:26Z at `ca329e5`
  (dirty diff `162fd55b…`), host `kp_luatest` SHA-256 `9309dd6a…`. It
  overwrote the first 20260927e receipt (`8d684683…28b5a0fb`, 19:57:51Z,
  chain `047e37906bbd`), which superseded `example-host-receipt-20260927d.json` (`2a98839a…60dba021`,
  19:12:42Z, dirty diff `850863e9…`), which superseded
  `example-host-receipt-20260927c.json` (17:47:18Z), which superseded
  `example-host-receipt-20260927.json` (16:15:51Z), which superseded the
  07:02:04Z receipt at `/home/brunner56/kp-validation-20260922-build/example-validation.json`.
- Live runs under `/home/brunner56/kp-live-20260922/stage-k1/runs/`.
- `docs/original41-live-evidence-audit.md` and
  `/home/brunner56/kp-live-20260922/original41-next-three-proof.md`.

## Evidence levels

| Level | Meaning | What it does not prove |
|---|---|---|
| none | No test or run bound to the example | anything |
| static-host | Named cases in `tools/tests/examples/*.lua` or the real-host dispatch suite, run by `tools/example_validation.py` | engine behavior, effects or rendering |
| live receipt (partial) | A K1 GOG/Wine run whose deployed Lua SHA equals the current source SHA, with `report.json` (and `continuous.mp4`, except 105626, which has screenshots and logs only) | the full manifest predicate set; none of these runs is an importable schema-1 live receipt |
| video accepted | A reviewed recording accepted as a clear demonstration of the behavior | — |

Each row gets the highest level it actually holds.

The 23:09:26Z host receipt matches current bytes for all 41 examples,
including `cursed/70_doppelganger.lua` at `5d9864b22241` (5 host cases) and
`cursed/40_chain_reaction.lua` at `e7b65781ca5b` (22 host cases). It
also hashes the current manifest and test files. The validator printed:
"41 original syntax/host regression sources, 105 per-file cases; 8 retired
from public catalog; 0 live receipts attached". This is host evidence only.

All live receipts below come from the 2026-09-22 batch. They ran on earlier
runtime DLLs, not the current console/native build. The audit says the same:
they bind Lua bytes, not the current runtime. Two runs do not count as
example evidence. Run 094527 is an environment preflight, even though it
deployed the two probes. Run 104936 (bullet time) was interrupted and has no
`report.json`.

**Video accepted: none.** `media/automatic-review.json` says none of the
automatic excerpts is deliverable-quality: they are 12 fps captures and the
defining effect is not staged. The user also rejected the low-FPS combat
clips and the GPU rave clip (`progress.md` line 59). The accepted giant-bow
and size-swap media come from native scene and diagnostic scripts, not
`scripts/examples/`, so they do not count here.

## Boundary rule

A boundary violation means a name that duplicates an NWScript routine and is
reachable from script scope. That covers Lua globals, `kp.*` fields, and bare
calls to routine names that skip `nwscript.call`.

The scan checked every example against the 878 routine names in
`data/routines/k1.json` and `k2.json`. It looked for function definitions,
assignments, `kp.<Routine>` and bare identifiers outside strings and comments.
Two things are excluded:

- Local constants copied from `nwscript.nss`, such as `OBJECT_TYPE_CREATURE`,
  `DAMAGE_TYPE_FIRE` and `DURATION_PERMANENT`. There are 28 such
  declarations. They are values, not routines.
- Local `q(name, ...)` wrappers that forward a string name to
  `pcall(nwscript.call, ...)`. They add no new name.

Results:

- **No violation in any shipped or retired example.** Every routine call goes
  through `nwscript.call` or a local `q` wrapper. Every caller switch uses
  `nwscript.with_caller`. The `kp.*` names in use are `print`,
  `registertimer`, `game_speed`, `speed`, `gamedir` and `time`. None of them
  is a routine name.
- **Test mock, classified as not a violation. The parent may overrule this.**
  `scripts/examples/multiplayer/10_avatar_sync_test.lua:64-89` defines Lua
  functions named `GetFirstPC`, `GetIsObjectValid`, `GetArea`, `GetTag`,
  `GetPosition`, `GetFacing`, `Location`, `CreateObject`, `DestroyObject`,
  `CutsceneMove` and `SetFacing`. They are keys of the local table
  `engine_routines`. They are reachable only through the mocked
  `nwscript.call` at lines 91-97, which asserts on unknown names. They are
  not globals and not `kp.*`.
- **Stale alias in the same mock: fixed 2026-09-27.** The test no longer
  defines `kp.as`. It mocks `nwscript.with_caller` (line 100), and its
  `SetFacing` mock logs the caller (line 90). The test now asserts that the
  `SetFacing` branch in `10_avatar_sync.lua:560-561` runs as the ghost on
  first spawn and on a facing change, and does not run when facing is
  unchanged.

## Ledger

APIs: `nw` is the number of distinct NWScript routines named in `nwscript.call`
or `q(...)`. `wc` means the example uses `nwscript.with_caller`. The outcome
column paraphrases the manifest's `live.predicate_obligations`, keyed by
predicate suffix. Every engine-dependent entry also carries `clean_recording`:
a clean serialized session with current bytes, independent state artifacts,
and continuous video where the behavior is visible.

### Arbitration and edge fixtures (real host, live not applicable)

| Path | sha | Intended behavior | APIs | Outcome to check | Evidence | Verdict |
|---|---|---|---|---|---|---|
| `scripts/examples/arbitration/10_abstain_nil.lua` | 91308fbe2548 | Priority 100 handler returns nothing, so it does not decide the event | Lua `print` only | Real-host dispatch: the event is claimed by `25_claims_via_string`, not this script | static-host: "real Lua host dispatch assertions: arbitration" | keep-curated as a regression and teaching fixture. It is the clearest demo of abstention. Not showcase. |
| `scripts/examples/arbitration/20_abstain_badstring.lua` | e38c5adb9dce | Returns a non-numeric string, which counts as abstaining | `print` | Same dispatch assertion: no vote from this script | static-host (same suite) | keep-curated as a fixture |
| `scripts/examples/arbitration/25_claims_via_string.lua` | 2fb4eb30a9e5 | Returns `"1"`, which converts to true and claims the event | `print` | The event is claimed here at priority 80 | static-host (same suite) | keep-curated as a fixture |
| `scripts/examples/arbitration/30_claims_false.lua` | 41757499f42a | Would block the NWScript by returning false | `print` | Loses to 25 on priority. It wins only if its priority is raised. | static-host (same suite) | keep-curated as a fixture |
| `scripts/examples/arbitration/40_too_late.lua` | 7e18f0bfae1e | Runs after the claim, sees `relevant=false`, and its return is discarded | `print` | Prints the too-late line. Its return has no effect. | static-host (same suite) | keep-curated as a fixture |
| `scripts/examples/arbitration/50_number_two_is_false.lua` | 938a7b525dc7 | Returns 2, which converts to FALSE | `print` | Returns after the claim, so the result is ignored in this set | static-host (same suite); receipt 20260927 | **retire (recommended; blocked).** It is byte-identical to `edge_number_two/50_number_two_is_false.lua` (same SHA-256 `938a7b52…`), and its own header says to run the edge copy. The `ab387d6` retire convention needs edits outside the allowed scope: the hardcoded `RETIRED` set in `tools/example_inventory.py:11-16`, and the arbitration expectations in `tools/example_validation.py:147-149` (`called: 6`, `abstained: 2`, `ignored: 3` and the `[50_number_two_is_false]` line). The "8 retired" print at lines 205-206 is hardcoded too. Moving the file alone breaks the validator, so it stays in place. |
| `scripts/examples/edge_fallback/all_abstain.lua` | 71ce5320521c | No claimant, so the event falls back to its declared default | `print` | Default is allowed, so the NWScript runs | static-host: "real Lua host dispatch assertions: edge_fallback" | keep-curated as a fixture |
| `scripts/examples/edge_number_two/50_number_two_is_false.lua` | 938a7b525dc7 | Shows that a return of 2 is FALSE | `print` | A lone script returning 2 yields false | static-host: "…: edge_number_two" | keep-curated as a fixture. Keep this copy. |
| `scripts/examples/edge_quarantine/always_errors.lua` | 314dc45cda17 | Errors on every tick until quarantined | none | After the error budget is spent, the script is suppressed | static-host: "…: edge_quarantine" | keep-curated as a fixture |

### Cursed pack (retained)

| Path | sha | Intended behavior | APIs | Outcome to check | Evidence | Verdict |
|---|---|---|---|---|---|---|
| `scripts/examples/cursed/10_rancor_roulette.lua` | 1bca2de3ca5f | A hostile that notices the PC is redrawn 50 ms later as Malak or a party human, then barks | `kp.print`, `kp.registertimer`; nw 12; wc | `arming_hooks`: armed after 200 ticks; unarmed and conversation events do nothing. `appearance_readback`: at least 3 non-party creatures read back rows in {21,4,5,6,7,8}. `guards_once`: PC, party, invalid, beyond 30 m and dead-at-timer creatures are excluded, with no double apply. `animation_safety`: no freeze. | live receipt (partial): `stage-k1/runs/20260922-095936/report.json` (11/11). Appearance query gate passed. Arming, guards and animation safety are not proven. | keep-curated. Strongest visual joke with a real appearance readback. Before featuring, remove the duplicated comment block at lines 29-44 (two paragraphs say the same thing). |
| `scripts/examples/cursed/20_fus_ro_dah.lua` | e84102b15810 | Each PC hit Force-pushes the victim with a flash, and every 5th hit sweeps non-party creatures within 10 m. | `kp.print`; nw 18; wc | `attacked_hook`: only PC attacks count. `push_observed`: independent push observation, not the counter. `fifth_sweep`: other creatures within 10 m are thrown; party, dead and far ones are not. `dedup`: one per victim per game-second. | live receipt (partial): `20260922-100404`. Only the five-shout counter; no displacement or sweep readback. | keep-curated. Needs a measured displacement before featuring. |
| `scripts/examples/cursed/30_necromancer.lua` | af24b0172f83 | 800 ms after an enemy's death script, a hostile Malak-disguised creature replaces the corpse, once per corpse | `kp.print`, `kp.registertimer`; nw 22; wc | `death_timer`: one rise per corpse. `replacement`: a valid hostile at the corpse position, with the corpse destroyed. `malak_readback`: independent `GetAppearanceType` is 21. `once_and_cleanup`: risen ones die for good. `failed_spawn`: a failure is not counted. | live receipt (partial): `20260922-100830`. Corpse counter and "no hostile left" only. Timed spawn, Malak readback and the failed-spawn branch are unproven. | keep-curated |
| `scripts/examples/cursed/40_chain_reaction.lua` | e7b65781ca5b | Every death detonates: 40 fire damage within 7 m, a third of that to party members, with blast deaths chaining. Party members keep at least 1 HP until their prior min-one-HP flag is restored | `kp.print`, `kp.registertimer`; nw 22 (adds `GetMinOneHP`, `GetTag`, `GetPartyMemberCount`, `GetPartyMemberByIndex`, `GetObjectByTag`) | `death_once`, plus `damage_readback`: measured full damage to non-party and floor(40/3) to party. `party_survival`: min-one-HP is observed, not the local-6 request total, and each member's prior flag reads back restored after settle, transition and unload. `cascade_cleanup`: bounded. | live receipt (partial): `20260922-101511` ran older bytes (`a346b5a8`), so it does not bind the current source. static-host, receipt 20260927e: 22 cases, including "party min-one-HP guard restores each prior flag after settle, transition and unload", the re-resolution cases for review probes A1 and P3, the identity cases for round-2 probe `pc_swap_probe.lua`, the round-3 probes R3-1 to R3-5 as host regressions, the epoch, collision and untagged-prior cases added in round 4, and the two frag VFX cases. | **keep-curated (fixed 2026-09-27; I1, round 3 and round 4 fixes the same day).** (1) `guard` reads `GetMinOneHP` before it sets the flag. `restore_guards` puts back the value it read. It runs from the `chain_settle` timer 3 s after the latest blast, from `disarm` on module load or area enter, and from `OnScriptUnload`. A party member whose flag cannot be read (an error, or a boolean `false` answer) is left out of the blast. (2) Identity epochs (round 4, replacing round 3's session-wide `owned` ID set, which left a creature that came back under a recycled ID stuck at 1). A numeric object ID counts only in the module epoch it was read in; `OnModuleLoad` and `OnAreaEnter` start a new epoch before the restore. `find` tries the stored ID (same epoch only), then `GetFirstPC` for a PC entry, then the roster by tag, then `GetObjectByTag`. Every candidate must be a valid party member with the stored tag. A creature that cannot be found is logged as "restore pending" and kept for the next settle or transition. Everyone found is restored in the same pass. While an entry exists, `guard` never reads that creature's flag as a prior. A pending entry that resolves to the member carries its prior over, and so does a read of 1 when an unresolved entry has the same tag. If two entries land on one creature, its prior is unknown: it is set to 0 (the NWScript default) and logged. `OnScriptUnload` restores what it can find. It names each creature left over ("NOT restored at unload") with the F12 console line that clears it. Not covered: a creature missing at unload keeps the flag, an untagged non-PC member cannot be found again after a transition, and a save written inside the 3 s window is loaded in a new session. (3) The comments now say local 6 is requested damage, not a measurement. (4) `VFX_FRAG` in `detonate` is reached only if a victim's death script runs inside the damage call. The host cannot decide this. `Host::dispatch` in `src/lua/host.cpp` wraps each dispatch in a `DepthGuard` that counts depth and never refuses re-entry, and the header records deaths arriving a frame later. Both cases are tested. Only a live chained kill decides which one the engine does. Live damage and restore readback are still open. |
| `scripts/examples/cursed/70_doppelganger.lua` | 5d9864b22241 | On the PC's first attack on a living non-party creature, the PC becomes Malak and each creature it attacks takes the PC's original look, with the exact disguise tokens removed after 40 quiet ticks or on a transition. | `kp.print`; nw 15 (includes `RemoveEffect`); wc | `pc_malak`: PC row 21. `hostile_copy`: record row P before arming; at least 3 living hostiles read P while the PC reads 21. `guards_once`: after settle, all touched actors are back to their pre-copy rows and only script-owned handles are gone. `failed_request_retry`. `animation_safety`. | static-host: receipt 20260927 binds the current bytes `5d9864b22241` and passes 5 cases (`tools/tests/examples/cursed.lua` lines 63, 108, 124, 139 and 149). Before that receipt, the main receipt and all three `/tmp/kp-doppel-*.json` receipts are stale for this file. The Task 13 round-3 review (`kp-live-20260922/task13-doppel-rereview-round3.md`) is a static route check. Run 104259 deployed older bytes and failed `hostile_copy`: the PC and copies went to row 21. That run is history only. | **keep-curated (README fixed 2026-09-27; script bytes unchanged).** The source captures P first; that is the fix from the live failure. README line 14 now gives the trigger as your first attack on a living non-party creature. It also states that `OnCreatureAttacked` was not seen firing with the PC as victim (the `OnCreatureAttacked` row in `docs/user/api-status.md`, verified 2026-09-16), so the `creature == pc` branch at line 205 is not expected to run. README line 14 also describes the restore: after combat, 40 quiet ticks (lines 179-186) or an area enter or module load (lines 163-164). Since the I1 round it also says that a creature dead or gone at cleanup keeps its disguise (logged; the transition path at `cursed.lua:134-136` gives up on it), and that a failed removal is retried on later ticks with no new copies until cleanup ends. Still open: a fresh serialized K1 gameplay run with video. |
| `scripts/examples/cursed/80_loot_pinata.lua` | a72857b81e3b | Each enemy death rings the corpse with 5 credit piles, and every 2nd burst also spawns a hostile gizka that attacks. | `kp.print`; nw 13; wc | `death_once`. `credit_objects`: 5 independently listed unowned credit items, with failures not counted. `gizka`: valid, hostile, and actually attacking. `retry_position`. | live receipt (partial): `20260922-104621`. At least 5 unowned items and row 69 were seen; credit identity, causality and the retry branch are unproven. | keep-curated |
| `scripts/examples/cursed/90_bullet_time.lua` | 57d1cfbc9f91 | When PC HP drops to at most 70%, game speed goes to 0.25 for 2.5 s with a blue tint and aura, then the previous speed returns | `kp.game_speed`, `kp.registertimer`, `kp.print`; nw 9 | `hp_trigger`: a real drop at or below 70%; no trigger otherwise. `speed_readback`: engine speed read independently in 0.20-0.30. `speed_restored`: returns to the previous speed, including a non-default one. `suppression_visual`: no timer stacking and no stuck slowdown. | static-host: "HP threshold, active suppression and previous speed restore". Run 104936 was interrupted (exit -2, no report), so it is not evidence. | keep-curated. Ranked third in `original41-next-three-proof.md`. First confirm that engine speed can be read independently. Note: it has no arming delay and no conversation guard. |
| `scripts/examples/cursed/100_item_airstrike.lua` | ce2e1504f9b4 | Each new item the PC or party acquires strikes a space laser and 60 damage on hostile (`GetIsEnemy` against the PC) living non-party creatures within 20 m, and a level-up gives a 15 s Revan look and aura. | `kp.print`; nw 18 (adds `GetIsEnemy`) | `acquire_arming`: load-time inventory replay before 200 ticks does not strike. `targets_damage`: measured damage on hostile living non-party creatures within 20 m; neutrals excluded. `owner_dedup`. `levelup`: a real level-up gives row 22 and the aura. | static-host, receipt 20260927: "owner filtering, strike radius and level-up requests"; "unrelated owner does not consume later legitimate pickup"; "strikes only hostile non-party creatures by GetIsEnemy against the PC". **No live run exists.** | **keep-curated (fixed 2026-09-27).** Line 67 now also requires `GetIsEnemy(creature, pc) == 1`, so neutrals are spared and README line 17 is accurate. Live risk: on 2026-09-16, `GetIsEnemy(x, pc)` answered 0 for a hostile trooper inside `OnRunScript`. The same comment appears in scripts 10, 20 and 30. Nobody has checked it from `OnModuleAcquireItem`. If it also answers 0 there, a strike hits nothing. The README and header now call level-up unproven, because `OnModulePlayerLevelUp` is only "Bound" (its row in the event table of `docs/user/api-status.md`). There is still no `GetIsInConversation` guard, and bullet time has none either. |

### Harness snippets (control-channel tools, not showcase)

All are one-shot chunks that return a table. No `kp.*`; only `nwscript.call` and
`nwscript.with_caller`. Evidence for all 11 is static-host only. The audit
found no live receipt bound to current bytes. README notes that earlier
Endar runs were not hash-bound.

| Path | sha | Intended behavior | APIs | Outcome to check | Evidence | Verdict |
|---|---|---|---|---|---|---|
| `scripts/examples/harness/10_world_probe.lua` | 9d043fdb12bc | PC facts, hostiles within 60 m sorted nearest first, party, and Endar globals | nw 17 | `pc_facts`, `hostile_filter`, `globals` match independent engine state | static-host: "world shape, sorted living hostiles and party" | keep-curated as a tool |
| `scripts/examples/harness/20_dialog_state.lua` | d0edc3dc6399 | Engine-side conversation state and partner fields | nw 10 | `dialog_facts` agree with engine and GUI state. `partner_guard`: an absent partner omits its fields. | static-host: "engine dialog shape and absent partner" | keep-curated as a tool |
| `scripts/examples/harness/30_move_to.lua` | f986d44610e6 | Queue a PC run to a tagged object or an offset | nw 10; wc | `reviewed_destination`. `arrival_distance`: the PC actually arrives; the action code is not enough. `missing_tag` errors with no move. | static-host: "missing target errors, move request under PC" | keep-curated as a tool |
| `scripts/examples/harness/40_attack_nearest.lua` | ee74e4739f35 | Attack the nearest live hostile within 40 m unless already engaged | nw 13; wc | `nearest_radius` includes the boundary. `combat_progress`: combat actually progresses. `engaged_noop`. | static-host: "nearest target, engagement and no enemies"; "inclusive radius and just-outside rejection" | keep-curated as a tool |
| `scripts/examples/harness/50_doors.lua` | c1793deb1426 | Inspect a door. With OPEN=true, the door commands itself open. | nw 10; wc | `door_facts`. `self_open`: the walkmesh becomes passable; record any `door_commit_open` used. `invalid_or_open`. | static-host: "inspect, self-open configuration and invalid door" | keep-curated as a tool |
| `scripts/examples/harness/60_area_dump.lua` | 41dc5b3191fd | List objects of one type with position and distance, nearest first, capped at MAX | nw 15 | `typed_rows` match independent enumeration. `sort_limit`. | static-host: "typed sorted rows and empty area" | keep-curated as a tool |
| `scripts/examples/harness/70_pc_status.lua` | c8154f8045f2 | PC HP, effects, slots 0-11 and inventory | nw 16 | `status_facts`, `effect_inventory`, and `wearable_slots` (0-11 only) | static-host: "status and populated equipment inventory effects" | keep-curated as a tool |
| `scripts/examples/harness/80_signal_event.lua` | 8728b4cd6e10 | Send UserDefined event 20 to the area or a tag | nw 6 | `target_event`. `authored_outcome`: the Endar dialog, faction flip and despawn are observed. `missing_target` errors. | static-host: "area and tag requests with missing target rejection" | keep-curated as a tool |
| `scripts/examples/harness/90_run_script.lua` | 560dbdc1ea4c | `ExecuteScript` of an authored NCS on a chosen object | nw 4 | `script_self`. `authored_postcondition` read from the world. `refusal_missing`. | static-host: "authored script and selected self; invalid target rejected" | keep-curated as a tool |
| `scripts/examples/harness/100_module_transition.lua` | 5e9eedb00450 | Inspect the transition door. With INSPECT=false, call `StartNewModule(end_m01ab, from_01a)`. | nw 7 | `inspect_facts`. `target_module`: the destination module is reached in a valid phase. `waypoint_arrival`. | static-host: "inspect default and explicit configured request only". The documented transition did not reach its target historically (`example-validation.md`). | keep-curated as a tool |
| `scripts/examples/harness/110_loot_container.lua` | d97d16a1c8d9 | Take all items from the nearest stocked `metalbox` via PC `ActionTakeItem` | nw 11; wc | `stocked_nearest`. `inventory_acquired`: every item moves; `taken` counts queued requests only. `empty_noop` gives taken=0. | static-host: "nearest stocked selection and PC-scoped takes" | keep-curated as a tool. Ranked first in `original41-next-three-proof.md` for the next live proof. |

### Coverage, probes and multiplayer

| Path | sha | Intended behavior | APIs | Outcome to check | Evidence | Verdict |
|---|---|---|---|---|---|---|
| `scripts/examples/coverage/10_cover.lua` | c13f64247ba8 | `cover …` console commands for globals, talk, jump, fade, module, autosave, convo, haste and pick | `kp.print`, `kp.speed`; nw 13; wc | `console_delivery`, `globals` read back, `talk_jump`, `fade_module_save`, `convo_haste_pick`. Pick only records the index; no ChooseReply call is claimed. | static-host: 10 command cases, plus "prefix rejection, help, pick, haste and missing target" | **keep-curated as a harness driver (fixed 2026-09-27).** The help text at line 47 now says pick "prints the index only; no reply is chosen". That matches lines 118-124, and the case "help describes pick as print-only with no reply chosen" asserts it. No proven API queues a reply. `tools/coverage_walk.py:6` still mentions a digit fallback; that file was out of scope. This is a harness driver used by `tools/coverage_walk.py`, not showcase material. The F12 console now runs `nwscript.call` directly, so its public value is low. |
| `scripts/examples/probe/00_probe.lua` | cafcf88daf06 | Passive observer: logs the first and every 100th event of each kind, never claims, and persists `cave-witness` through `OnSave` | `kp.print` | `event_arrival` for live hooks only; dead names such as `OnCreatureDeath` are not claimed. `throttle_abstain`. `sidecar` save/load. | static-host: "every observer abstains; throttle and sidecar". Run 094527 deployed it, but that run is an environment preflight, not probe evidence. | keep-curated as a diagnostic |
| `scripts/examples/probe/10_position_trace.lua` | 1dd76b8b044e | Every 10 ticks, logs PC position and facing when they change by more than 0.02 or 0.3 | `kp.print`; nw 4 | `real_movement`, `thresholds`, and `invalid_pc` gives no trace | static-host: "poll and strict movement thresholds". Same preflight caveat. | keep-curated as a diagnostic |
| `scripts/examples/multiplayer/10_avatar_sync.lua` | 954b9cdee1f1 | UDP avatar sync over LuaJIT ffi/ws2_32 in which a remote player's position, facing and name drive a placeholder actor from a generated UTC | `kp.print`, `kp.gamedir`, `kp.time`; nw 11; wc | `two_game_clients` (two real clients), `winsock_transport`, `generated_utc` loads in game, `avatar_state` with same-area gating, `lifecycle` | static-host: "existing multiplayer mocked socket/engine regression" | keep-curated as experimental, not featured. It needs two real game clients before any claim. |
| `scripts/examples/multiplayer/10_avatar_sync_test.lua` | 784e2e98d56e | Standalone LuaJIT test that drives the real script with mocked `nwscript`, `kp` and sockets | mock only | Test assertions pass (live not applicable) | static-host: same case, receipt 20260927 | **keep-curated (fixed 2026-09-27).** `kp.as` is removed. The mock has `nwscript.with_caller` (line 100). The test asserts `SetFacing` as the ghost on first spawn (90) and on a facing change (100), and asserts no call when facing is unchanged. |

### Retired on 2026-09-22 (commit `ab387d6`)

Sources are in `tools/tests/examples/fixtures/legacy/`. The manifest reason
for all eight: "text/buff commentary or unfocused random effects". Their
regression cases and open live obligations remain. Retirement is not a pass.

| Original path | sha | Intended behavior | APIs | Outcome still owed | Evidence | Verdict |
|---|---|---|---|---|---|---|
| `cursed/50_chaos_roulette.lua` | 5d796ae8cca1 | Each combat-end rolls one of ten effects on that creature | `kp.print`; nw 22; wc | `combend_hook`, `effect_branches`, `teleport_branch`, `request_text` | live receipt (partial): `20260922-102211`. Effect-type changes were seen, but not every branch or the teleport distance. Run 095353 used older bytes. | retire (done). Unfocused random effects. |
| `cursed/60_rave.lua` | 56e47290dd37 | A beat timer strobes, plays battle music, makes idle creatures dance, and fires plasma every 4th beat | `kp.print`, `kp.registertimer`; nw 19; wc | `timer_start`, `dance`, `fourth_plasma`, `music_strobe`, `inactive_poll` | live receipt (partial): `20260922-104031`; supplementary peaceful run `110018`. The user rejected the GPU rave clip. | retire (done). Disorienting; rejected by the user. |
| `showcase/10_ahto_city_law.lua` | 7f263c2f5784 | Manaan strike commentary bark, with the count persisted | `kp.print`; nw 4 | `module_attacker`, `text_delivery`, `persistent_count` | static-host: "module attacker guards and persisted strikes". Deployed in 105626, but no gate covered it. | retire (done). Text only. |
| `showcase/20_sith_patrol_alarm.lua` | c06f339b5b74 | A hostile sentry that perceives the PC barks once per module | `kp.print`; nw 6 | `perception`, `text_delivery`, `sentry_reset` | static-host: "hostility and once per sentry per module". Same caveat. | retire (done). Text only. |
| `showcase/30_battle_meditation.lua` | 6aaf0ad7a0c9 | While Bastila is conscious in the party, a party member being attacked gives the party a 6 s attack buff once per round | `kp.print`; nw 9 | `bastila_guard`, `effects_observed`, `round_gate` | live receipt (partial): `20260922-105626`, a combined six-script run. Effect deltas, expiry and suppression were seen; the negative Bastila guards and next round are missing. | retire (done). Buff with little to see. |
| `showcase/40_alignment_drift.lua` | 5d151bc4be02 | Bark when light/dark alignment crosses a decade, polled every 180 ticks | `kp.print`; nw 3 | `alignment_readback`, `poll_threshold`, `text_delivery` | live receipt (partial): `105626`. 20→35 crossing and same-decade suppression were seen; the downward crossing was not. | retire (done). Text only. |
| `showcase/50_enclave_arrival.lua` | 35d87eb81d43 | One line on the first entry to each planet prefix, persisted | `kp.print`; nw 2 | `prefix_once`, `sidecar_reload`, `text_delivery` | live receipt (partial) **with a failed gate**: `105626` step 37 no-repeat failed after danm13. The cause is a combined OnSave collision, not a proven script fault. The isolated script is untested. | retire (done). Text only. |
| `showcase/60_party_wounded.lua` | d6e7c59d7d2e | Warning at or below 35% HP, once per object per Lua state | `kp.print`; nw 5 | `threshold`, `text_delivery`, `once_per_state` | live receipt (partial): `105626` steps 26-29, after tag fix `1bb1714`. Above-threshold, non-party and heal cases are missing. | retire (done). Text only. |

## Counts

| Evidence level | Count | Rows |
|---|---|---|
| none | 0 | — |
| static-host | 31 | 10 host-only fixtures, 11 harness, coverage, 2 probes, avatar sync, bullet time, airstrike, doppelganger (current-byte receipt 20260927), chain reaction (its live run used older bytes), showcase 10 and 20 |
| live receipt (partial) | 10 | rancor, fus ro dah, necromancer, loot pinata; chaos, rave; showcase 30, 40, 50 (failed gate) and 60 |
| video accepted | 0 | — |

| Verdict | Count |
|---|---|
| keep-curated | 32: 8 arbitration/edge fixtures, 11 harness, 2 probes, avatar sync, rancor, fus ro dah, necromancer, loot pinata, bullet time, plus the five fixed on 2026-09-27: chain reaction, doppelganger, item airstrike, coverage, avatar sync test |
| needs-fix | 0 |
| retire | 9: `arbitration/50` (duplicate; recommended, blocked on validator files outside the allowed scope), plus the 8 already retired in `ab387d6` |

## Curation set

These are the examples worth featuring once their gaps close. Harness
snippets, probes, arbitration fixtures and multiplayer are tools,
diagnostics or experiments. They stay out of the showcase.

One gap is shared by every entry. A featured example needs an accepted
recording: 60 fps, with the effect staged in view. The Gamescope capture path
that would produce it is still blocked. Round 9 failed review. Rootless
Xwayland root capture records black frames. Child-window cadence is
unresolved (`progress.md` lines 181-191). No example below can be featured
until that path produces a reviewed clip.

1. **`cursed/10_rancor_roulette.lua`.** Closest to ready: it has a
   current-byte appearance readback (095936). It needs:
   - A hash-bound receipt for `guards_once` (party, PC, beyond 30 m and
     dead-at-timer exclusions) and `animation_safety`.
   - Removal of the duplicated comment block at lines 29-44.
2. **`cursed/70_doppelganger.lua`.** A strong visual gag, and the source fix
   is reviewed. The current-byte host receipt (20260927) and the README
   correction for the trigger and the restore are done. It needs:
   - A fresh serialized K1 gameplay run: PC reads 21, at least 3 hostiles
     read the pre-arming row P, and all rows are restored after settle.
   - A reviewed video.
   Live gameplay and video are **still open**.
3. **`cursed/30_necromancer.lua`.** It needs:
   - An independent `GetAppearanceType == 21` readback on each risen object,
     taken separately from the script's own verify line.
   - A timed-rise check at about 800 ms.
   - A failed-spawn negative case (audit gap for 100830).
4. **`cursed/20_fus_ro_dah.lua`.** It needs:
   - A measured victim displacement for `push_observed`.
   - A 5th-hit sweep that shows other creatures thrown, with party, dead and
     far ones excluded. Today only the counter is proven (100404).
5. **`cursed/90_bullet_time.lua`.** It needs:
   - A first complete run. 104936 was interrupted.
   - An independent game-speed readback in 0.20-0.30 and restoration of a
     non-default previous speed.
   The next-three audit says to first confirm that such a readback exists.

Not in the set yet. The 2026-09-27 source fixes are host-tested only:

- **Chain reaction:** the min-one-HP restore is fixed and host-tested,
  including PC and party objects that come back under new IDs after a module
  load (review probes A1 and P3 are now host regressions), and a `GetFirstPC`
  change while the guarded PC object stays valid (round-2 `pc_swap_probe`,
  now a host regression). Round 4 scopes object IDs to one module epoch and
  finds creatures again by role and tag after a transition (round-3 probes
  R3-1 to R3-5 are host regressions). A creature missing at unload is
  logged with its console fix, not restored. Still open: whether K1's `GetFirstPC` can change
  that way at all (a live before/after identity readback settles it), live
  damage and restore readback, a live chained kill to show whether frag VFX
  ever fires, and whether K1 actually re-IDs party objects on
  `StartNewModule` (unverified; the fix does not depend on it). A save
  written inside the 3 s window and loaded in a new session is not covered.
- **Item airstrike:** targeting now matches the README, and level-up is
  marked unproven. Still open: whether `GetIsEnemy` answers 1 inside
  `OnModuleAcquireItem`, the missing conversation guard, and a level-up
  event that is only "Bound".
- **Loot pinata:** kept, but its gaps are credit identity and gizka attack
  behavior. It is lower priority than the five above.

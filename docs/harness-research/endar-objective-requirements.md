# Endar Spire physical objective requirements

Audited 2026-09-10 against `kq` decodes from the staged K1 install at
`tmp/k1_harness`. Most findings use retained decoded resources and their
recorded source containers. Independent review later completed two focused,
container-pinned `kq` decodes for the opening door and Starboard terminal;
those rows label the fresh evidence explicitly. These are authored-resource
facts, not claims about a running save.

## Evidence boundary

The primary module evidence is:

- `kq cat m01aa -t git -f json --from end_m01aa.rim`, retained as
  `tmp/tas-research/m01aa.git.json`; metadata records
  `modules/end_m01aa.rim/m01aa.git`.
- `kq cat m01ab -t git -f json --from end_m01ab.rim`, retained as
  `tmp/tas-research/m01ab.git.json`; metadata records
  `modules/end_m01ab.rim/m01ab.git`.
- Selected UTD/UTP/NCS decodes under `tmp/tas-research/resources/`. Each JSON
  file records its exact `path` and `container`; those addresses are cited
  below.

The GITs contain placements and module links. UTD/UTP files contain initial
lock/use/conversation hooks. NCS instruction listings establish referenced
objects, globals, engine actions, and branches, but do not recover source-level
variable names. No route-guide ordering is used.

## Physical graph

`m01aa.git` contains 15 doors, 60 placeables, and 14 triggers. Tags are not
unique: four instances use `end_door06`, and two use `end_door10`. Every
executor lookup therefore requires tag plus template and authored position.

The corridor graph that is directly supported by placements is:

| Module / target | Authored position | Resource facts | Normal action and observable postcondition |
| --- | ---: | --- | --- |
| `end_m01aa`: `end_door01`, template `sw_door_test001` | `(21.1225, 20.7130, -1.3158)` | Opening-room door in `modules/end_m01aa.rim/m01aa.git`. Fresh container-pinned review query `kq --json cat sw_door_test001 -t utd --from end_m01aa_s.rim` resolved `modules/end_m01aa_s.rim/sw_door_test001.utd`: `Tag=end_door01`, `Locked=0`, `Conversation=end_door01`, `OnOpen=k_pend_door1xp`, and `OnFailToOpen=k_pend_door01`. | Interact after the opening conversation permits control; require the same resolved instance to become open/passable and wait for its authored hook to settle. Its initial state is unlocked. Effects of `k_pend_door1xp` and `k_pend_door01` remain unresolved until their NCS resources are decoded. |
| `end_door05` | `(46.5749, 50.8134, -1.3158)` | `modules/end_m01aa_s.rim/end_door05.utd`: `Locked=1`, no conversation, `OnOpen`, or `OnFailToOpen`. | Do not repeatedly force-use it. Wait for authored module/dialogue logic to change the live lock state, then interact and require open/passable. The retained resources do not identify the unlocking script. |
| `end_door06`, template `end_door06` | `(29.1850,67.0221)`, `(14.5120,101.2710)`, `(18.5973,115.2390)`, `(42.2760,99.0562)` | Four separate instances in `modules/end_m01aa.rim/m01aa.git`; `modules/end_m01aa_s.rim/end_door06.utd` is initially locked and has no conversation or open/fail hook. | Resolve by position, wait for each required corridor instance to unlock through authored progression, interact, and verify that exact instance is open/passable. Which of the four are mandatory cannot be proved from the GIT alone. |
| `end_door10_cut2`, template `end_door012_2` | `(43.8580,66.9634,-1.3158)` | `modules/end_m01aa_s.rim/end_door012_2.utd`: unlocked, conversation `end_door01`, `OnOpen=k_pend_room5_02`. | Interact; require the door open and the authored `k_pend_room5_02` sequence to settle before continuing. |
| `end_door16` | `(29.1850,106.0310,-0.0408)` | `modules/end_m01aa_s.rim/end_door16.utd`: locked, conversation `end_door01`, `OnOpen=k_pend_door16`. | Satisfy the preceding authored encounter/dialogue state, interact, and require unlock/open plus completion of the open-script side effects. The retained NCS for the gate is absent, so its exact global prerequisite is unresolved. |
| `end_door07` | `(42.2760,109.2290,-0.0408)` | `modules/end_m01aa_s.rim/end_door07.utd`: unlocked, conversation `end_door03`, `OnFailToOpen=k_pend_door22`, user-defined hook `k_pend_cut25`. | Interact and require open/passable after any conversation or user-defined sequence settles. |
| `end_door19` | `(39.5591,125.3790,-0.0408)` | `modules/end_m01aa_s.rim/end_door19.utd`: unlocked, conversation `end_door01`, `OnOpen=k_pend_traskdie1`. | Interact; require open/passable and the Trask authored sequence to settle. This is a stronger route milestone than merely reaching its coordinates. |
| `end_door15` | `(39.5591,135.6210,-0.0408)` | `modules/end_m01aa_s.rim/end_door15.utd`: locked, conversation `end_door01`, `OnFailToOpen=k_pend_door15`. The retained NCS reads `END_ROOM7_DEAD`; when it is at least 2, the script unlocks and opens the door. If the value is lower it can start `end_levelup`; it also reads `END_TRASK_DLG`. | Defeat/resolve the room-7 encounter until `END_ROOM7_DEAD >= 2`, then interact. Require this exact door to become unlocked and open. Treat the level-up conversation as a blocking branch to complete, not as proof that the gate passed. |
| `end_door08` | `(29.1850,135.6220,-0.0408)` | `modules/end_m01aa_s.rim/end_door08.utd`: locked, `OnFailToOpen=k_pend_door20`. Retained `tmp/tas-research/resources/k_pend_door20.ncs.json`, decoded from `modules/end_m01aa_s.rim/k_pend_door20.ncs`, proves the normal predicate `GetGlobalNumber("END_ROOM8_DEAD") >= 2` through `CONSTI 2`, `GEQII`, and a failing `JZ`. It separately reads `END_BRIDGE_SEALED` and `END_TRASK_DLG`, references bridge combatants and `end_bridgeseal`, and can call `SetLocked`, `ActionOpenDoor`, and `ActionStartConversation`. | Resolve room-8 combat until `END_ROOM8_DEAD >= 2`, then interact and require the exact door unlocked/open with the bridge sequence settled. Preserve `END_BRIDGE_SEALED` as a separate sealed-door/dialogue branch; its downstream behavior and the `END_TRASK_DLG` branches still require reconciliation. |
| bridge approach | `wp_end_bridgedoor=(28.9740,136.1659,0)` | `modules/end_m01aa.rim/m01aa.git` places `end_bridgesith1/2` at `(33.1356,155.8231)` and `(35.7716,159.2234)`, with bridge explosion/seal triggers spanning the intervening region. | Cross by normal movement; resolve valid hostile objects until combat is over, then require pathability beyond the bridge. Trigger entry alone is not success. |
| `end_door10`, template `end_door011` | `(47.4172,120.1260,-0.0425)` | The only explicit module link in `m01aa.git`: `LinkedToModule=end_m01ab`, `LinkedTo=from_01a`. `modules/end_m01aa_s.rim/end_door011.utd` is unlocked and has conversation `end_door01`. A second same-tag instance at `(49.4322,120.1260)` uses locked template `end_door013` and has no link. | Select the `end_door011` instance by template/position, interact, and require module `end_m01ab` plus a settled PC near `from_01a=(49.8766,120.2613,0)` from `modules/end_m01ab.rim/m01ab.git`. Never choose by tag alone. |

The exact topological ordering among unlinked internal doors is not encoded as
an adjacency list in the retained resources. Coordinates, trigger polygons,
and scripted gate names constrain the graph, but a walkmesh parse or a live
pathability probe is still required before declaring every internal door
mandatory.

## Trigger objectives

Triggers in `modules/end_m01aa.rim/m01aa.git` are placed along the physical
route and must be treated as authored event boundaries:

- `end_trig02` starts at `(24.5195,23.6921,-0.9835)` immediately beyond the
  opening room.
- Five `end_trig_expld01` polygons start near `(43.7035,16.2031)`,
  `(33.8585,78.4464)`, `(26.1165,113.4881)`, `(25.4928,140.4223)`, and
  `(28.8366,148.8316)`.
- `end_reinfrc` starts at `(38.5159,85.6304,-0.2749)` and spans back toward
  the corridor; reinforcement waypoints occur on both sides of the adjacent
  rooms.
- `end_trig_expl001` occurs near `(43.1119,31.7940)` and `(10.7762,89.4628)`.
- `bridgeexplosion1`, `bridgeexplosi001`, and two `end_sealbridge` instances
  cover the bridge approach beginning around y=136-146.

The retained GIT proves placement and template resrefs, not each UTT's
`OnEnter` script. A normal executor should cross these polygons through
movement, then wait for newly spawned enemies, door-state changes,
conversation/cutscene completion, or combat settlement. It must not execute a
suspected trigger script directly. Fresh `kq cat <template> -t utt` validation
is required to bind each trigger to an exact script.

## `end_m01ab`: terminal, containers, and pod

Entry is physically anchored by `from_01a=(49.8766,120.2613,0)` in
`modules/end_m01ab.rim/m01ab.git`. That GIT contains five doors, sixteen
placeables, and six triggers. None of its five door instances carries an
explicit `LinkedToModule`; the retained data therefore proves the forward
`m01aa -> m01ab` link only.

| Target | Authored position | Resource facts | Normal action and observable postcondition |
| --- | ---: | --- | --- |
| `end_trig_carth02` | `(49.2852,122.4013,0)` | Trigger template in `modules/end_m01ab.rim/m01ab.git`, directly beside `from_01a`. | Enter by movement and wait for its authored sequence to settle. Exact script and gate need a fresh UTT decode. |
| `end_trig10` | `(65.7129,109.1905,0.6998)` | Trigger placement in the same GIT. | Cross normally and wait for resulting encounter/state changes; exact script unresolved. |
| `g_zoncata001` / `g_zoncata002` | `(62.6810,95.0349,0)` / `(77.1109,56.9201,0)` | Trigger placements adjacent to `g_zoncont001` / `g_zoncont002`. | Let the zone trigger populate/control its paired container before reading or looting it; require inventory delta if looted. Exact zone script needs fresh UTT/UTP resolution. |
| `g_zoncont001` / `g_zoncont002` | `(62.0341,92.4972,0)` / `(79.2008,52.3423,0)` | Container template refs in `modules/end_m01ab.rim/m01ab.git`. Existing retained generic UTP decodes resolve from `danm14aa_s.rim`, so they are not valid evidence for Endar contents or hooks. | Optional loot unless another task proves an item gate. Resolve the Endar template copy, open normally, and verify inventory transfer; do not require either container for completion yet. |
| `footlker003` | `(74.5179,72.8904,0)` | Placeable template ref in `m01ab.git`; retained UTP resolves from `danm13_s.rim`, so Endar inventory is unresolved. | Optional loot pending module-specific UTP/inventory evidence. |
| `end_killsith` | `(75.9846,63.6179,0.17)` | Trigger placement beside two `wp_end_killsith` waypoints and the assault-droid area. | Enter through movement, resolve spawned/nearby hostiles, and require combat settled. Exact kill counter/global write needs fresh UTT/NCS binding. |
| `end_comp02` | `(82.9170,66.4592,0.1851)` | This sole placement is in `tmp/tas-research/m01ab.git.json`; `tmp/tas-research/m01aa.git.json` contains none. Fresh container-pinned review query `kq --json cat end_comp02 -t utp --from end_m01ab_s.rim` resolved `modules/end_m01ab_s.rim/end_comp02.utp`: `Conversation=end_securitycomp`, `OnUsed=k_pend_comp07`. The `end_m01aa_s.rim` copy binding `temp_comp01` is shadowed and does not describe this placement. | Interact normally; complete the `end_securitycomp` branch required by current state and require its selected physical effect (door/droid/container/global) before proceeding. Which branch is mandatory remains unresolved pending DLG/action-script recovery. |
| `end_door01`, template `end_door002` | `(76.8854,81.2643,-0.0408)` | `modules/end_m01ab_s.rim/end_door002.utd`: unlocked, `OnOpen=k_pend_explode04`. Retained NCS references `end_explode04` and applies delayed visual effects. | Interact, require open/passable, then wait for `k_pend_explode04` effects to settle. |
| `end_pod` | `(85.2928,41.1341,-0.2029)` | `modules/end_m01ab_s.rim/end_pod.utp`: conversation `end_pod`, `OnUsed=k_pend_pod02`. Retained `modules/end_m01ab_s.rim/k_pend_pod02.ncs` resolves `end_pod`, requires a valid first PC, clears party actions/cancels combat, starts conversation when the user is party member 0, otherwise fades and changes party leader before staging the sequence. | Interact only when combat is settled and the intended PC/party leader is valid. Require the pod conversation/script sequence, then an authored campaign transition or other independently proven quest postcondition. The NCS snapshot contains no destination module string, so `module != end_m01ab` alone is observable but does not identify the correct destination. |

## Minimum executor requirements

For each physical step, resolve the live object by tag, occurrence, template,
and approximate authored position; move using normal pathfinding; interact or
cross the trigger normally; and wait on an engine state change. A successful
step needs one of: exact door unlocked/open plus pathability, inventory delta,
enemy death/combat exit, completed conversation/cutscene with control restored,
or expected module transition with settled gameplay.

Never use direct script execution, teleportation, plot-variable writes, or a
mere coordinate arrival as the success oracle. Authored placements can be
absent, destroyed, already consumed, or changed in a save.

## Unresolved requirements

1. Fresh `kq` UTT decodes are needed for every named trigger to bind its
   `OnEnter`/`OnExit` scripts.
2. Fresh module-specific resolution is needed for `g_zoncont001/002` and
   `footlker003`; retained generic UTP copies come from other modules.
3. NCS/source-level reconciliation is needed for `k_pend_door16`,
   `k_pend_comp07`, terminal dialogue actions, `end_killsith`, and the final
   pod destination/postcondition.
4. A walkmesh parse or read-only live pathability probe is needed to prove
   which repeated `end_door06` instances and internal branches are mandatory.

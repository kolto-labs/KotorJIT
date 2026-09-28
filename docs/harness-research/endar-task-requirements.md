# Endar Spire executor requirements

Audited 2026-09-10. This contract combines the reviewed dialogue, journal,
global, and physical-object investigations. It describes what an ordinary,
non-visual Endar Spire executor must do. It is not a claim that a fresh game
has completed the route live.

## Evidence classes

- **Fresh `kq`:** the journal/global investigation and review-time,
  container-pinned decodes for `sw_door_test001.utd` and the placed
  `end_comp02.utp`.
- **Retained `kq`:** earlier decoded GIT, UTD/UTP/NCS, and coverage JSON under
  `tmp/tas-research/` and `tmp/coverage/`, with source-container metadata.
- **Unresolved:** any behavior supported only by a resref, script name,
  coordinate, story expectation, or untested harness routine.

The independent review found and corrected one cross-module template error:
the placed Starboard `end_comp02` uses
`modules/end_m01ab_s.rim/end_comp02.utp` and dialogue
`end_securitycomp`; `temp_comp01` belongs to an unplaced shadow copy. See
`tasks-1-3-review.md` and `tasks-1-3-corrections-report.md`.

## Normal progression facts

| Requirement | Object or authored state | Normal action | Required postcondition | Evidence |
| --- | --- | --- | --- | --- |
| Leave the opening room | `end_door01`, template `sw_door_test001`, `(21.1225,20.7130,-1.3158)`; initially unlocked; `OnOpen=k_pend_door1xp` | Move to the exact door and open it through the door action | The same instance is open/passable and its hook has settled | Fresh, container-pinned `kq`; Tasks 1 and 3 correction |
| Traverse authored corridor events | Internal doors and placed trigger polygons in `end_m01aa` | Move through the walkmesh; interact with exact door instances; let triggers fire naturally | Door/passability, spawned-enemy, dialogue/cutscene, or combat state changes settle before the next step | Retained `kq`; Task 3 |
| Pass room 7 | `end_door15` at `(39.5591,135.6210,-0.0408)` | Resolve both authored room-7 deaths, then operate the door | `END_ROOM7_DEAD >= 2`, exact door unlocked/open, any `end_levelup`/Trask branch settled | Fresh `kq` gate proof plus retained object decode; Tasks 2 and 3 |
| Pass room 8 / bridge gate | `end_door08` at `(29.1850,135.6220,-0.0408)` | Resolve both authored room-8 reinforcement deaths, then operate the door | `END_ROOM8_DEAD >= 2`, exact door unlocked/open, bridge flow settled | Fresh `kq` plus retained NCS/object decode; Tasks 2 and 3 correction |
| Handle sealed-bridge diversion | `END_BRIDGE_SEALED` branch in `k_pend_door20` | If true, finish the authored `end_bridgeseal` conversation branch | Control returns and the subsequent live door/path state determines whether progress is possible | Fresh/retained `kq`; Tasks 1–3. Downstream branch behavior remains unresolved |
| Cross into Starboard | Linked `end_door10`, template `end_door011`, `(47.4172,120.1260,-0.0425)` | Select by tag, template, and position; open normally | `module=end_m01ab`, gameplay settles, valid PC is near `from_01a=(49.8766,120.2613,0)` | Retained `kq`; Task 3 |
| Use the Starboard terminal only if live state requires it | Placed `end_comp02` at `(82.9170,66.4592,0.1851)`, `Conversation=end_securitycomp`, `OnUsed=k_pend_comp07` | Interact as a placeable and choose only an engine-visible reply | The selected physical/global effect is observed before continuing | Fresh, container-pinned `kq`; Tasks 1 and 3 correction. Mandatory branch is unresolved |
| Reach the escape pod | `end_pod` at `(85.2928,41.1341,-0.2029)`, `Conversation=end_pod`, `OnUsed=k_pend_pod02` | Interact as a placeable with combat settled and a valid first PC/leader | Pod dialogue becomes active and exposes its engine-filtered replies | Retained `kq`; Tasks 1 and 3 |
| Complete Endar Spire | Resource reply `end_pod.dlg/ReplyList[1]`, text `[Use the escape pod.]`, `Quest=end_attack`, `QuestEntry=99`, `Script=k_pend_pod01` | Select the currently visible link that resolves to this authored reply; do not assume visible index 1 | Journal `end_attack=99` **and** the pod script's authored campaign transition settle in gameplay with a valid PC | Fresh `kq`; Task 2 |

The terminal completion action is therefore exact: traverse the use-pod
reply in `modules/end_m01ab_s.rim/end_pod.dlg`, resource `ReplyList[1]`.
Opening the pod dialogue, selecting the step-away reply, forcing journal 99,
or observing only `module != end_m01ab` does not satisfy completion. The
destination module is not present in the retained `k_pend_pod02` decode and
must be identified before a destination-specific oracle is written.

## Candidate authored boundaries

The placed Trask creature has `Conversation=end_trask01`, but current evidence
does not identify the initiating trigger or action. Treat Trask conversation
start as a candidate boundary: when the recovered DLG/UTT graph or a live
fresh-state probe proves how normal play enters it, wait for the active
dialogue and expose only the engine-filtered replies. It is not yet a required
executor step.

Starboard contains the placed trigger/object candidates `end_trig_carth02`,
`end_trig10`, and `end_killsith`. Placement alone proves neither their order
nor that the completion path intersects all of them. When normal movement
crosses one, wait for its observed combat/dialogue/world-state result to
settle. Promote a candidate to the route only after its UTT/script behavior
and DLG or walkmesh topology establish that it lies on the selected normal
path.

## Journal and global contract

`data/_newbif.bif/global.jrl` defines `end_attack` entries 1, 10, 11, 20, 30,
40, and terminal 99. Fresh `kq` ties entries 1, 11, 20, and 30 to specific
`end_trask01.dlg` replies: `ReplyList[92] -> 1`, `ReplyList[49] -> 11`,
`ReplyList[45] -> 20`, and `ReplyList[1] -> 30`. These are possible progress
observations, not route requirements: observe one only after the engine selects
its exact authored reply, and require it only if the recovered graph proves
that reply belongs to the selected normal branch. The separate
`end_pod.dlg/ReplyList[1] -> 99` effect remains the proven terminal reply
effect. The executor must not write any of these entries directly.

No Endar DLG writer was found for entries 10 or 40, and the module-scoped NCS
query found no `AddJournalQuestEntry`. Neither is a prerequisite. A writer
outside the two Endar module roots has not been ruled out.

`END_ROOM7_DEAD >= 2` and `END_ROOM8_DEAD >= 2` are the two proven physical
open-path predicates. `END_TRASK_DLG` and `END_CARTH_DLG` are dialogue state
machines, so the executor observes rather than guesses or forces their
values. `END_BRIDGE_SEALED` selects a distinct sealed-door conversation path.

## Closed-loop control contract

Every step resolves a live target by module, tag, occurrence, template when
available, and approximate authored position. This is required because tags
such as `end_door06` and `end_door10` are duplicated. A step then queues the
object-appropriate engine action and waits for an independent state change:

- creatures: `ActionStartConversation` for dialogue;
- doors: movement plus `ActionOpenDoor`;
- placeables such as `end_comp02` and `end_pod`: `ActionInteractObject`;
- hostiles: a combat action followed by death/combat/global readback;
- trigger objectives: normal movement across the trigger polygon.

`ActionInteractObject` is placeable-only. An action call returning is never a
success oracle. The executor records module, PC/party validity, position,
dialogue entry and visible replies, relevant globals/journal, inventory,
combat/HP, and exact object state before and after each action. It checkpoints
only after a stable, independently observed postcondition. On failure it may
retry an idempotent movement or door action; it must not blindly repeat a
conversation choice or transition.

The harness already provides the scenario loop, checkpoints, softlock
watchdog, module/phase/PC state, globals and journal walking, dialogue
readback/reply/VO skip, and Lua access to the generated movement, door,
placeable, conversation, combat, inventory, and state routines. K1 movement
to and opening of a door has live evidence elsewhere in the project. These
facts establish available control surfaces, not Endar-route completion.

## Missing capability or proof

1. A genuine fresh-game fixture is missing. The available advanced Endar save
   cannot prove the normal opening, inventory, party, or dialogue state. The
   signed new-game GUI/event bridge described in
   `new-game-control-path.md` is still required.
2. Creature conversation start is not live-proven for Trask. The generated
   routine and dialogue reader exist, but a prior Trask start attempt did not
   enter dialogue. This must be resolved before implementing reply policy.
3. Combat action control is not live-proven reliably. The executor cannot
   promise the room-7/room-8 counters until attack, target death, and combat
   exit are measured through the main-thread action path.
4. The full `end_trask01`, `end_securitycomp`, `end_pod`, and other
   `end_m01ab` node/link graphs are not retained. Exact visible-choice policy,
   auto-start behavior, and terminal/dialogue branch handling remain unknown.
5. Trigger UTT bindings, `k_pend_door16`, `k_pend_comp07`, terminal action
   scripts, `end_killsith`, and the final pod destination need narrow,
   container-pinned `kq` recovery.
6. Internal topology is not proven. GIT coordinates are not a walkmesh graph;
   a walkmesh parse or read-only live pathability probe must determine which
   repeated doors and branches are mandatory.
7. Object enumeration/type classification and generic action-queue completion
   are not first-class harness commands. Existing tag lookup and state probes
   may be enough; add a new primitive only if the narrow route probe proves
   they are insufficient.

## Implementation sequence

1. Recover only the unresolved route resources listed above with serial,
   container-pinned `kq` queries and retain their complete JSON. Produce the
   exact active-condition/action mapping for Trask, Starboard terminal, pod,
   and named triggers.
2. Finish the signed fresh-new-game bridge and establish a reproducible
   checkpoint at `end_m01aa` with a newly created PC and normal authored state.
3. From disposable checkpoints, live-prove one primitive at a time:
   Trask conversation start and engine-visible reply selection; placeable
   interaction; combat target/death/counter behavior; linked-door transition;
   pod transition and destination.
4. Measure walkmesh/pathability and exact object identity along the authored
   corridor. Encode only proven targets, actions, branch predicates, and
   postconditions as route data; reuse the existing scenario loop.
5. Implement the ordinary route as stable-room transactions: observe
   preconditions, act, wait for the independent postcondition, checkpoint,
   and record evidence. Do not execute scripts, teleport, or write plot state.
6. Run the complete fresh route headlessly. Only after it succeeds, record the
   required proof video with at least two minutes of actual driven gameplay
   and retain the corresponding state/event/checkpoint report.

Until items 1–4 are resolved, the repository has a resource-grounded route
skeleton and proven hard gates, but it cannot honestly claim an end-to-end
normal Endar Spire run.

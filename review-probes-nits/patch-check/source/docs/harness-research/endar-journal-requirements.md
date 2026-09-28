# Endar Spire journal and global requirements

Audited 2026-09-10 against the staged K1 install with
`KQ_INSTALL=$PWD/tmp/k1_harness`. This document describes authored resource
state. It does not claim that a save or live session has reached any state.

## Journal category

`kq cat global -t jrl` resolves the only Endar category to
`data/_newbif.bif/global.jrl` (Chitin resource, offset 36, size 77,301):

| Tag | Title strref | Entry | End | Text strref | Meaning from staged `dialog.tlk` |
| --- | ---: | ---: | ---: | ---: | --- |
| `end_attack` | 32564 | 1 | 0 | 32565 | Trask reports the attack and the search for Bastila. |
| `end_attack` | 32564 | 10 | 0 | 32567 | Map/journal tutorial text. |
| `end_attack` | 32564 | 11 | 0 | 32567 | Same map/journal tutorial text. |
| `end_attack` | 32564 | 20 | 0 | 32568 | Carth orders all hands to the bridge. |
| `end_attack` | 32564 | 30 | 0 | 32569 | Bastila is absent from the bridge; head to the starboard pods. |
| `end_attack` | 32564 | 40 | 0 | 36893 | The ship is lost; use an escape pod. |
| `end_attack` | 32564 | 99 | 1 | 32566 | Carth and the player escaped in the final pod. |

The category is a progress record, not by itself a route lock. The Endar NCS
query for `AddJournalQuestEntry` returned no matches. Instead, the DLG
resources attach `Quest="end_attack"` and `QuestEntry` directly to replies;
the dialogue engine applies the update when that reply is traversed.

## Proven journal writers

The focused query

```sh
KQ_INSTALL=$PWD/tmp/k1_harness kq --text grep -F 'end_attack' \
  -t dlg -m end_m01aa -m end_m01ab --winners
```

finds five writers:

| Resource-addressed reply | Journal entry | Authored context | Other effect |
| --- | ---: | --- | --- |
| `modules/end_m01aa_s.rim/end_trask01.dlg`, `ReplyList[92]` | 1 | Unconditional `Okay.` reply after Trask says to grab gear. | `Script=k_pend_time01` |
| same DLG, `ReplyList[49]` | 11 | Unconditional `Okay.` reply in the menu tutorial. | `Script=k_pend_time01` |
| same DLG, `ReplyList[45]` | 20 | Unconditional reply after Trask relays Carth's bridge order. | `Script=k_pend_carth11` |
| same DLG, `ReplyList[1]` | 30 | Unconditional reply after Trask says Bastila is absent and to head for the pods. | no reply action script |
| `modules/end_m01ab_s.rim/end_pod.dlg`, `ReplyList[1]` | 99, terminal | Explicit `[Use the escape pod.]` choice. | `Script=k_pend_pod01`, `PlotIndex=48`, `PlotXPPercentage=1.4` |

The pod's alternative `[Step away from the escape pod.]` has no quest update
or action script. Therefore entry 99 is a real authored completion action:
the harness must choose the use-pod reply, then separately observe the normal
scripted transition. Merely seeing `end_pod`, opening its dialogue, or already
having an earlier journal entry is insufficient.

No Endar DLG writer was found for entry 10 or 40. Entry 10 duplicates entry
11's text and may be an unused/alternate tutorial state. Entry 40 has useful
route wording, but its presence in `global.jrl` is only an observed journal
definition until a writer is located. A harness must not synthesize either
entry as a prerequisite.

## Proven global gates

These globals are distinct from the `end_attack` journal entry number.

### Room 7 combat door

`modules/end_m01aa_s.rim/k_pend_room7_01.ncs` handles user-defined event
`1007` by reading `END_ROOM7_DEAD`, adding one, and writing the result with
`SetGlobalNumber`. The same script sets `END_BRIDGE_SEALED=1` only when both
`END_PC_ON_BRIDGE` and `END_TRASK_ON_BRIDGE` are true.

`modules/end_m01aa_s.rim/k_pend_door15.ncs` reads
`END_ROOM7_DEAD`, compares it with `2` using `GEQII`, and returns without its
open path when the comparison fails. This is a real gate: normal progression
through that door requires the two authored room-7 death events (or the
equivalent resulting global value), not a journal entry.

### Room 8 / bridge door

`modules/end_m01aa_s.rim/k_pend_reinfrc08.ncs` handles user-defined event
`1007` by incrementing `END_ROOM8_DEAD`. The symbol query also locates the
same read/write pair in `k_pend_reinfrc09.ncs`, identifying the two authored
reinforcement death sources.

`modules/end_m01aa_s.rim/k_pend_door20.ncs` first reads
`END_BRIDGE_SEALED`. When true it starts conversation `end_bridgeseal` and
does not enter the normal open branch. Otherwise it requires
`END_ROOM8_DEAD >= 2` before continuing. Thus the room-8 count is the normal
combat gate; `END_BRIDGE_SEALED` is a diversion/closed-state condition, not a
prerequisite to open the route.

### Dialogue progress numbers

`END_TRASK_DLG` and `END_CARTH_DLG` are dialogue state machines used by many
Endar condition/action scripts. Their mere appearance in an NCS is not a
route requirement. Two concrete effects are established:

- `data/scripts.bif/k_pend_door03.ncs` writes `END_CARTH_DLG=5` and starts a
  conversation with `Carth`.
- `k_pend_door15.ncs` and `k_pend_door20.ncs` read/write `END_TRASK_DLG`
  inside their post-combat dialogue flow. Those operations coordinate the
  Trask conversation state; the actual door predicates remain the death
  counters described above.

Do not force a guessed `END_TRASK_DLG` value. Follow the authored dialogue
and object scripts, then observe the global if a live oracle exposes it.

## Harness requirements

1. Treat `end_attack` as an observable progress record. Do not use entries
   10 or 40 as mandatory gates without a located writer.
2. To reproduce normal early progress, traverse the authored
   `end_trask01.dlg` replies that write entries 1/11/20/30; do not inject the
   journal entry directly.
3. Require `END_ROOM7_DEAD >= 2` before expecting the room-7 door script to
   open, and `END_ROOM8_DEAD >= 2` before expecting the normal room-8/bridge
   door branch.
4. Treat `END_BRIDGE_SEALED=true` as a sealed/conversation branch.
5. Complete the quest only through `end_pod.dlg` reply 1, then require both
   journal entry 99 and the independently observed pod/module transition.
6. Resolve every DLG/NCS through its winning resource and retain its container
   path in proof output; a resref alone does not establish which copy ran.

## Evidence boundary

All JRL, DLG, and NCS facts above were decoded from installed resources with
`kq`. Staged `dialog.tlk` was read only to render the referenced strings. No
game was launched and no save was inspected for current journal/global
values, so live readback remains required before claiming route completion.

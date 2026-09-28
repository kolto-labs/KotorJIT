# Endar Spire dialogue requirements

Audited 2026-09-10 against the staged K1 install at `tmp/k1_harness`. This is
an authored-resource specification, not evidence that any dialogue ran in a
live session.

## Evidence boundary

The primary retained evidence is output previously decoded from this exact
install by `kq`:

```sh
KQ_INSTALL=$PWD/tmp/k1_harness kq cat end_trask -t utc
KQ_INSTALL=$PWD/tmp/k1_harness kq cat end_comp02 -t utp
KQ_INSTALL=$PWD/tmp/k1_harness kq cat end_pod -t utp
KQ_INSTALL=$PWD/tmp/k1_harness kq cat k_pend_pod02 -t ncs
```

Those outputs are retained as `tmp/tas-research/trask.utc.json`,
`tmp/tas-research/resources/end_comp02.utp.json`,
`tmp/tas-research/resources/end_pod.utp.json`, and
`tmp/tas-research/resources/k_pend_pod02.ncs.json`. The earlier coverage run
retained `tmp/coverage/end_m01aa.json`, a graph summary of every DLG in the
first module. During this pass, concurrent reads of the external game volume
blocked in uninterruptible I/O, so fresh `kq cat` validation of each DLG could
not complete. Counts, links, and script names below that come only from the
coverage summary are therefore marked **retained lead**. Exact player-facing
text is unresolved rather than reconstructed from a route guide.

The cached `kq` index identifies these exact dialogue containers:

- `modules/end_m01aa_s.rim`: `end_bridgeseal`, `end_comp01`, `end_cut01`,
  `end_cut04`, `end_door01`, `end_door02`, `end_door03`, `end_levelup`,
  `end_pop01`, `end_pop02`, `end_pop03`, `end_room3`, `end_room5`,
  `end_trask01`, and `m01aa_c01`.
- `modules/end_m01ab_s.rim`: `end_carth001`, `end_damagedroid`, `end_pod`,
  and `end_securitycomp`.
- The retained coverage graph additionally names `cp_end_traskbrdg` as an
  Endar dialogue. Its summary labels the logical container `end_m01aa.mod`;
  fresh `kq which` is required to settle the physical winner.

## Required opening conversation

`end_trask.utc` is authoritative decoded resource evidence. The creature has
tag/template `end_trask`, authored position `(22.8837, 20.6108, -1.2750)` in
`end_m01aa`, and `Conversation=end_trask01`. Its standard dialogue event is
`ScriptDialogue=k_hen_dialogue01`; it also has Endar-specific spawn, death,
and user-defined scripts `k_pdan_trask_9`, `k_pend_trask_7`, and
`k_pend_trask_d`.

The `end_trask01` DLG graph is a **retained lead** with 74 entries, 93 replies,
and 19 starting links. Start-link conditions, in stored order, are:

```text
k_pend_trask00, _false, k_pend_traskdlg2, _false,
k_pend_traskdlg4, k_pend_traskdlg7, _false, _false,
k_pend_traskdl14, _false, _false, _false, k_pman_false,
_false, _false, _false, _false, k_pend_traskdl35
```

This proves that starting the same DLG is state-dependent. A harness must not
assume start index 0. It must let the engine evaluate the starting links and
then read the active entry and visible replies.

Conditional scripts present in the graph are `_false`, `k_con_isscout`,
`k_con_issoldier`, `k_pend_trask00`, `k_pend_traskdl14`,
`k_pend_traskdl35`, `k_pend_traskdlg2`, `k_pend_traskdlg4`,
`k_pend_traskdlg7`, and `k_pman_false`. Action scripts are
`cp_end01_pcjump`, `k_pend_cadlg_inc`, `k_pend_carth11`, `k_pend_map`,
`k_pend_time01`, `k_pend_traskdl29`, `k_pend_traskdl32`,
`k_pend_traskdl40`, `k_pend_traskdl41`, `k_pend_traskdl43`,
`k_pend_traskdl45`, `k_pend_traskdl47`, `k_pend_traskdl48`,
`k_pend_traskdl49`, `k_pend_traskdl50`, and `k_pend_traskinc`.

The script names establish control points, not their effects. Fresh NCS
decodes are required to bind each condition to literal globals, class checks,
inventory, journal state, party changes, or movement. The harness-visible
postcondition for each choice is the engine-selected next entry or dialogue
end plus a before/after snapshot of globals, journal, inventory, party,
position, module, and object state.

## Other first-module dialogue graphs

All rows in this table are **retained leads** from
`tmp/coverage/end_m01aa.json`.

| DLG | Entries / replies / starts | Active conditions | Action scripts | Harness role |
| --- | ---: | --- | --- | --- |
| `m01aa_c01` | 18 / 18 / 4 | starts: `k_pend_bedtal`, `k_pend_bedmed`, `k_pend_bedsml`, `k_pend_bedtny`; also `k_pend_female`, `k_pend_male` | `k_pend_rumble01`; end and abort: `k_pend_cut09` | Opening body/gender branch and cutscene completion. No player choice may be assumed merely because reply nodes exist. |
| `end_cut01` | 6 / 6 / 1 | none | `k_pend_cut01`, `02`, `14`, `24`, `26`, `27`, `32` | Scripted Trask/scene-object sequence. |
| `end_cut04` | 5 / 5 / 1 | none | `k_pend_cut18`, `19`, `20`, `31`, `k_pend_reinfrc03`, `k_pend_room5_03` | Scripted room-five sequence. |
| `end_room3` | 6 / 6 / 1 | none | `k_pend_camera`, `k_pend_cut1_1`, `_2`, `_3`, `k_pend_cut1_end`, `k_pend_traskdl49` | Scripted room-three sequence. |
| `end_room5` | 6 / 6 / 1 | none | `k_end_plot`, `k_pend_cut2_1`, `_2`, `_3`, `k_pend_explosion`, `k_pend_jump`, `k_pend_room5_03` | Scripted room-five plot sequence; `k_end_plot` is a named action, not proof of a particular plot write until NCS is decoded. |
| `cp_end_traskbrdg` | 3 / 3 / 1 | start/link: `k_pend_traskdl35` | `cp_end_bridgecs` | Bridge transition gated by a Trask condition. |
| `end_levelup` | 2 / 3 / 1 | none | `k_pend_xpboost` | Level-up prompt. Its three reply nodes require fresh text/link recovery before automated selection. |
| `end_pop01` | 9 / 11 / 1 | none | none | Trask informational pop-up tree. |
| `end_pop02` | 4 / 5 / 1 | `k_pend_traskdlg3` on a link | none | Conditional Trask pop-up tree. |
| `end_pop03` | 12 / 16 / 1 | none | none | Trask informational pop-up tree. |
| `end_bridgeseal` | 1 / 1 / 1 | none | none | One-entry/one-reply bridge notice. |
| `end_door01` | 1 / 1 / 1 | none | none | One visible acknowledgement is expected, but its text is unresolved. |
| `end_door02` | 1 / 0 / 1 | none | none | Terminal one-entry door message. |
| `end_door03` | 1 / 0 / 1 | none | none | Terminal one-entry door message. |
| `end_comp01` | 8 / 8 / 2 | start: `k_pend_comp10`; link: `k_con_comhack` | `k_act_comp01`, `k_pend_comp09`, `k_pend_comp13`, `k_pend_repair07` | Computer interaction. `k_con_comhack` reads literal string `K_REPAIR_PART` in retained NCS analysis. `k_pend_comp13` and `k_pend_repair07` were missing from the scanned resolved script set, so those branches are not yet safe to automate. |

There are no orphan entries or replies in any of these retained first-module
graphs. That is graph-connectivity evidence only; it does not show that every
branch can become active in the installed game state.

## Object-bound conversations and second module

Decoded UTP evidence gives two exact use paths. The Starboard terminal binding
was refreshed during independent review with the container-pinned query
`kq --json cat end_comp02 -t utp --from end_m01ab_s.rim`; this is fresh `kq`
evidence rather than part of the retained snapshot set above.

- The placed `end_comp02` in `tmp/tas-research/m01ab.git.json` has no matching
  placement in `tmp/tas-research/m01aa.git.json`. Its module-local template is
  `modules/end_m01ab_s.rim/end_comp02.utp`, which binds
  `Conversation=end_securitycomp` with `OnUsed=k_pend_comp07`. This is the
  authoritative dialogue binding for the Starboard terminal.
- `modules/end_m01aa_s.rim/end_comp02.utp` binds
  `Conversation=temp_comp01` with the same `OnUsed=k_pend_comp07`, but it is a
  shadowed cross-module copy with no `end_comp02` placement in `m01aa.git`.
  It must not be used to model the placed Starboard terminal.
- `end_pod.utp` in `end_m01ab_s.rim` is usable and unlocked, binds
  `Conversation=end_pod`, and runs `OnUsed=k_pend_pod02`.

Literal retained NCS for `k_pend_pod02` resolves `end_pod` and the first PC,
checks object validity, clears party-member actions, cancels combat, changes
the party leader, performs global fade-out/fade-in and delayed commands, and
calls `ActionStartConversation` on two branches. These are real bytecode
operations from the installed resource. The dynamic branch taken, dialogue
speaker/listener, selected DLG argument, and eventual module transition still
require fresh structured disassembly or a live trace.

The second-module DLG resources `end_carth001`, `end_damagedroid`, `end_pod`,
and `end_securitycomp` are container-proven by the cached `kq` index. The fresh
module-local UTP decode now proves that `end_securitycomp` is the DLG selected
by the placed Starboard terminal, but no retained graph output contains its
links, visible replies, or action scripts. Those graphs remain required
recovery work before claiming a complete Endar dialogue route.

## Selection and observable acceptance contract

For every conversation, the harness must:

1. Start through the authored object action or conversation event, preserving
   its condition scripts; do not jump directly to a guessed DLG node.
2. Wait for active dialogue state and read the current entry plus the
   engine-filtered visible reply list. The visible list, not the raw DLG reply
   array, is authoritative because link `Active` scripts filter it.
3. Record display index, resolved link index, and text/StrRef. Exact visible
   choice text is not available in the retained exports from this pass.
4. Choose only a currently visible link. Empty single replies may auto-advance
   and zero-reply entries may terminate without input.
5. Prove acceptance by an entry/reply transition or dialogue end, then record
   externally visible deltas: globals, journal, inventory, XP/level, party and
   leader, door/placeable state, position, combat, fade/cutscene state, and
   module.

## Unresolved checks

- Re-run `kq which` and `kq cat` for every named DLG after external-volume I/O
  recovers; retain full node/link JSON including text/StrRefs.
- Decode every listed conditional/action NCS and record literal constants,
  comparisons, reads, and writes. Script names alone are insufficient.
- Recover `temp_comp01` only to characterize the shadowed `end_m01aa_s.rim`
  copy; recover `end_securitycomp` to model the placed Starboard terminal.
- Recover all four `end_m01ab_s.rim` dialogue graphs.
- Determine which scripted graphs auto-start from module/trigger scripts and
  which require explicit interaction.
- Live-check only after the resource graph is complete: actual visible reply
  ordering, auto-advance behavior, side effects, and the final escape-pod
  transition.

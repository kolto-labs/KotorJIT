# Endar Spire resource and fixture audit

Audited 2026-09-10 with `kq` against the staged install at
`tmp/k1_harness` (`KQ_INSTALL=$PWD/tmp/k1_harness`). This is read-only
resource research; no save or game files were modified and no game was
launched.

Decoded resource snapshots are in
`tmp/tas-research/resources/endar-route.json`. The raw decoded GIT snapshots
are `tmp/tas-research/m01aa.git.json` and `m01ab.git.json`; selected UTD/UTP
and NCS snapshots sit beside them. They can be regenerated with `kq cat`, for
example:

```sh
KQ_INSTALL=$PWD/tmp/k1_harness kq cat m01aa -t git --from end_m01aa.rim
KQ_INSTALL=$PWD/tmp/k1_harness kq cat m01ab -t git --from end_m01ab.rim
KQ_INSTALL=$PWD/tmp/k1_harness kq cat end_pod -t utp
KQ_INSTALL=$PWD/tmp/k1_harness kq cat k_pend_pod02 -t ncs
```

## Resource-grounded entities

`end_m01aa` contains 15 door instances, 26 creature instances, 60 placeable
instances, 14 triggers, and 58 waypoints. The resource does not give every
instance a unique tag: `end_door06` occurs four times, `end_door10` occurs two
times, and generic placeable tags such as `FootLker` occur in multiple rooms.
Therefore a TAS must use `GetObjectByTag(tag, nth)` and validate the returned
position/template before acting; a tag alone is insufficient.

The most useful authored locations in the first module include:

| Resource entity | Authored position (x, y, z) | Role evidence |
| --- | --- | --- |
| `end_trask` creature | `(22.8837, 20.6108, -1.2750)` | Trask fixture in the opening room |
| `end_door01` instance (`sw_door_test001`) | `(21.1225,20.7130,-1.3158)` | First room door; exact instance position is in the JSON snapshot |
| `end_door10` linked instance (`end_door011`) | `(47.4172,120.1260,-0.0425)` | `LinkedToModule=end_m01ab`, `LinkedTo=from_01a`; corresponding waypoint is in `end_m01ab` |
| `end_bridgesith1/2` creatures | `(33.1356,155.8231,0)`, `(35.7716,159.2234,0)` | Bridge encounter fixtures |
| `wp_end_bridgedoor` waypoint | `(28.9740,136.1659,0)` | Bridge-door approach location |
| `wp_pc_final` waypoint | `(38.4759,126.8600,0.0085)` | Endar room-8 player placement |

The first row and all exact entity values are authoritative in
`endar-route.json`; the abbreviated table entries above avoid duplicating the
full instance list. The `end_m01ab` resource contains 5 doors, 10 creatures,
16 placeables, 6 triggers, and 14 waypoints. Its authored `from_01a` waypoint
is `(49.8766,120.2613,0.0000)`, matching the linked `end_door10` transition
instance in `end_m01aa` at the resource level.

## Door, console, pod, and encounter script facts

The decoded templates establish useful route predicates:

- `end_door04` is locked and has conversation `end_door02`, open script
  `k_pend_door03`, and fail-open script `k_pend_door08`.
- `end_door05` and `end_door06` are locked with no authored conversation or
  open script in their templates; their usable state is controlled by module
  logic and must be observed in the live object.
- `end_door07` is unlocked, has conversation `end_door03`, and uses
  `k_pend_cut25` for user-defined handling and `k_pend_door22` on failure.
- `end_door08` is locked and invokes `k_pend_door20` on failure.
- `end_door15` is locked and invokes `k_pend_door15` on failure.
- `end_door16` is locked, has conversation `end_door01`, and invokes
  `k_pend_door16` on open.
- The non-cutscene `end_door10` instance is unlocked, linked to `from_01a`,
  while the second `end_door10` template is locked and conversational. They
  must never be conflated by tag alone.
- `end_comp02` is a placeable with conversation `temp_comp01` and
  `OnUsed=k_pend_comp07`; it is the strongest resource candidate for an
  interactive terminal/console step.
- `end_pod` is a placeable with conversation `end_pod` and
  `OnUsed=k_pend_pod02`. The decoded `k_pend_pod02.ncs` references
  `end_pod`, starts/clears party actions, and handles the Endar escape-pod
  sequence. The resource alone does not prove that the pod was reached or
  completed in a live session.
- `g_zoncont01` and `g_zoncont02` are unlocked containers using
  `k_zon_control` heartbeat logic. Their authored templates do not identify
  which loot branch is present; inventory readback is required.

The first module's creature templates include `end_trask`, the opening Sith
and bridge Sith (`n_sithappren001/002`, `n_sithsoldier003/004`,
`end_bridgerep1/2`), and several scripted reinforcements. The template list is
placement evidence, not a promise that every instance is alive in a given
save: the live oracle must check object validity, HP, death, and combat state.

## Save fixture provenance

The staged `000001 - AUTOSAVE` and `000000 - _pick` folders are byte-identical
for the principal save resources and have `savenfo.res` identifying:

```text
AREANAME:  Endar Spire - Command Module
LASTMODULE: end_m01aa
```

Their directory contents include `SAVEGAME.sav`, `PARTYTABLE.res`,
`GLOBALVARS.res`, `savenfo.res`, and `pifo.ifo`; this is a complete loadable
fixture. The NFO also carries `PCAUTOSAVE`, `AUTOSAVEPARAMS`, and portraits
`po_pbastila`/`po_pzaalbar`. `SAVEGAME.sav` is a `MOD V1.0` ERF and includes
the `end_m01aa` module save plus other stored module resources. This explains
why the fixture can load to Endar while its party/template data contains
later-game resources: it is an in-game autosave copied from an existing
campaign, not a clean new-game/level-1 provenance artifact.

The `000038 - Game37` folder is a distinct complete fixture. Its NFO identifies
`AREANAME=Dantooine - Jedi Enclave`, `LASTMODULE=danm13`, save name
`dantooine done?`, and portraits `po_pmhc1`/`po_pzaalbar`/`po_pbastila`.
Its timestamps are 2026-04-04, while the staged Endar autosave was refreshed
2026-08-30. No local metadata identifies the original player, seed, or the
route that produced either save, so neither can honestly be advertised as a
community speedrun practice save or a clean campaign start.

`000014 - Game13` is not a usable fixture: it lacks `SAVEGAME.sav` and is
excluded by the harness save picker. No shipped `.bic` login character or
verified clean new-game save was located in the staged install during this
audit. The recovered load notes also say `new_game` remains unsupported until
the login-character writer is found. Consequently, the lowest-effort
legitimate starting state currently available is the complete Endar autosave,
with its provenance explicitly marked as an existing campaign fixture.

## Route consequence

The ordinary route can now be made declarative without visual steering:

1. Load `000001 - AUTOSAVE` and assert `module=end_m01aa`, valid PC, and a
   stable gameplay phase.
2. Resolve `end_trask`, doors, containers, and `end_comp02`/`end_pod` by tag
   plus template/position validation. Use `ActionMoveToObject` followed by a
   distance/position predicate, then `ActionInteractObject` or the object
   action and wait for a dialog, event, inventory, or object/module change.
3. Branch on actual alive enemy IDs and HP after each encounter. Do not rely
   on authored creature placement as proof of a kill.
4. Complete the pod only after `end_pod` interaction and the scripted event
   sequence are observed; then require a module change and settled gameplay.

The current resources identify the targets and scripts, but they do not supply
the live object IDs, action constants, pathfinding completion signal, or
journal completion state. Those remain the next live probe boundary. The
existing `k1_state_drive`/`k1_quest_drive` proof bundles demonstrate engine
control and state mutation, not completion of this physical route.

## `end_door01` far-side walkmesh evidence

`kq --install tmp/k1_harness --json cat m01aa_01a -t wok` identifies global
`data/models.bif/m01aa_01a.wok` (26,404 bytes) and its BWM V1.0 header. The
bounded harness parser reads 114 vertices, 195 faces, and the documented
79-face walkable prefix, deriving adjacency only from shared edges in that
prefix. With the declared +Y door-plane normal, approach face 12 has centroid
`(19.915...,20.195...,-1.275)` and projection `-0.518`; its shared edge leads
to face 13 at `(20.32586733500163,21.70310910542806,-1.274999976158142)`,
whose projection is `+0.990109`. The route records source resource, face,
centroid, and path `[12,13]`. It still requires ordinary door actions and live
postconditions; this resource proof alone is not a live crossing proof.

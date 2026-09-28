# Nonvisual campaign execution plan

## Acceptance

Complete the Endar Spire through ordinary movement, encounters, interactions,
dialogue and exits, from a documented legitimate starting fixture. Confirm the
route before rerunning it for a complete session video. Require at least 120
seconds of active gameplay; exclude loading, idle padding, menus and camera-only
motion. A successful Lua return or plot mutation is not route completion.

## Constraints

- Preserve existing uncommitted work and all run evidence; no commits or cleanup.
- Build concurrency at most 3; one live game at a time.
- Engine actions execute on the existing main-thread drain. Never block it.
- Read game state for decisions; screenshots only cross-check rendering.
- Use named resolved bindings and existing routine dispatch; no speculative addresses.
- Unsupported or missing observations cannot satisfy a proof predicate.
- Distinguish semantic automation from verified deterministic frame replay.

## Tasks and ledger

1. Research community routes and analogous state-driven systems. In progress.
2. Audit current engine capability. Complete: nonvisual-capability-audit.md.
3. Implement bounded world observation and outcome waits using existing Lua API.
4. Extract installed module resources and establish a legitimate initial fixture.
5. Measure movement, interaction, combat and dialogue; assemble ordinary route.
6. Verify route, rerun with complete video, validate active gameplay and end state.
7. Add deterministic replay controls only after their clock/RNG coverage is measured.

Ruling: Continue in the existing feature checkout with narrowly owned files and
before/after review snapshots. The harness depends on substantial existing WIP;
a fresh checkout without it would test a different runtime. Cost if wrong:
additional isolation work, with snapshots preserving the original files.

Ruling: Do not stream all executed assembly. Use static resource graphs and
bounded live observations first, then targeted breakpoints/traces for a specific
missing or failing action. Cost if wrong: an extra targeted diagnostic iteration.

Research review: rejected idle padding, treating Starboard as the escape-pod
destination, and treating the K2 skip-prologue option as full prologue completion.
Route researcher is correcting those claims before integration.

## Measured diagnostic session

Run `tmp/k1_harness/runs/20260910-003602`, K1 Steam unpacked, display 105.
This is a control diagnostic, not campaign proof or a qualifying video.

- Initial save: 34,360 XP, 96 HP, Bastila and Zaalbar. Excluded as fresh-start proof.
- `kp.as(pc, ActionMoveToObject + ActionOpenDoor)` moved from 11.703 m
  to 1.408 m from `end_door01`; door readback changed 0 to 1 over 24.76 s.
  Evidence: `tmp/tas-research/live-door-before.json`, `live-door-action.json`.
- New world observation returned 221 objects and 156 inventory rows with
  no truncation/errors. Evidence: `tmp/tas-research/live-world.json`.
- Opened actual screenshot `shots/0001_diagnostic-door-open.png`; rendered
  gameplay and opened doorway agree with engine observations.
- `ActionInteractObject(Trask)` did nothing: recovered K1 implementation
  explicitly calls GetPlaceableByGameObjectID. This API is placeable-only,
  not a generic use action. NPCs need ActionStartConversation, doors ActionOpenDoor.

Task 3 review round 1: global work budget and normalized-state validation need
fixes; implementer addressing them. Independent reviewer also identified the
pre-existing guarded-Lua engine-call defect documented in harness-design.md
Known issues. This requires a separate runtime fix before the architecture's
unguarded-engine-call constraint can be marked satisfied.

Next dependency: recover the normal quick-character-generation engine path;
no known local save establishes a clean campaign start. Do not reset plot flags
or regenerate the save to disguise the existing advanced character.

Task 3: foundation complete after review round 1 (spec pass, quality pass).
Six focused tests pass, including execution of emitted Lua against bounded
iterator stubs; existing offline harness suite passes 54 tests. Reviewed live
probe: 221 objects, 156 inventory rows, 467 work units, no truncation/errors,
52.8 ms request latency. Snapshot: `tmp/tas-research/live-world-reviewed.json`.
Runtime at exit: live, 18 hooks, no poisoned sites, no missing adapter sites.
This measurement covers this one K1 build and diagnostic fixture only.

Conversation diagnostic remains unresolved: neither PC-owned nor NPC-owned
ActionStartConversation with default resource opened Trask's dialogue within
their respective bounds. Current action subsequently read 65534 (idle), and
GetIsConversationActive read 0. Do not advertise NPC dialogue as live-proven
from these calls. Next investigation must inspect the actor/dialogue gates and
save state rather than repeat the same command or insert arbitrary sleeps.

Research tasks 1 and 4 are complete as audits. Detailed artifacts:
`nonvisual-control-research.md`, `kotor-speedrun-routes.md`,
`endar-resource-route.md`, and `new-game-control-path.md`. Tasks 5–7 remain open;
no campaign completion, frame-deterministic replay, universal binary support,
or qualifying >=120-second gameplay video has been established by this work.

# Endar Spire task investigation

## Objective

Derive what normal Endar Spire progression requires from the installed K1
resources, using `kq` as the primary evidence source. The deliverable is a
source-addressable route specification: prerequisite state, target instance,
normal action, authored script/dialogue path, and observable postcondition.

## Constraints

- Read the staged K1 installation only; do not alter saves, modules, or game
  state and do not boot the game.
- `kq` output and decoded resource content are evidence; do not infer missing
  script behavior from route guides.
- Keep authored-resource facts separate from a live-state claim.
- Preserve all existing worktree changes. No commits, pushes, or cleanup.
- Do not treat an existing advanced Endar save as a fresh-start fixture.

## Task 1

**Dialogue graph.** Trace Endar DLGs, their active conditions, reply links,
action scripts, and externally visible effects. Write
`docs/harness-research/endar-dialogue-requirements.md`.

## Task 2

**Journal and global gates.** Locate Endar JRL categories and trace relevant
NCS/DLG state reads and writes to establish the actual quest/plot gates.
Write `docs/harness-research/endar-journal-requirements.md`.

## Task 3

**Physical objectives and transitions.** Map doors, placeables, containers,
triggers, module links, and authored scripts to a normal route. Write
`docs/harness-research/endar-objective-requirements.md`.

## Task 4

**Synthesis.** Combine only corroborated claims into
`docs/harness-research/endar-task-requirements.md`, marking every unresolved
condition or required live probe.

## Dependency scan

| Tasks | Shared interface | Finding |
| --- | --- | --- |
| 1 and 2 | DLG action/condition script names | Separate output files; synthesis reconciles scripts. |
| 1 and 3 | Door/placeable conversations | Separate output files; synthesis resolves target/action pairing. |
| 2 and 3 | NCS scripts and module events | Separate output files; synthesis checks causality. |
| 1–3 and 4 | Evidence artifacts | Task 4 consumes the three reports only after they are reviewed. |

Ruling: Run Tasks 1–3 as independent read-only investigations in parallel,
then synthesize sequentially. This preserves isolated evidence while avoiding
speculative route construction. Cost if wrong: the synthesis may need one
additional reconciliation pass, but no game state or source code is changed.

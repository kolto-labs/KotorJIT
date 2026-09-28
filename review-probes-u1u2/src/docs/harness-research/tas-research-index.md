# Nonvisual KOTOR control and TAS

Use a semantic controller: read placed objects and authored dialogue from the
installed resources, reconcile them with live engine state, issue a normal
engine action, and wait for its specific outcome. Keep the language model out
of the frame loop. Trace selected native functions only when their behavior
cannot be resolved from the routine implementation and observations.

## Research and implementation

- [Control architecture and prior art](nonvisual-control-research.md): Voyager,
  MineDojo, libTAS, Frida, GDB, rr, ReAgent, AgentDecompile, kq and PyKotor.
- [Speedrun route research](kotor-speedrun-routes.md): normal progression versus
  speedrun optimizations, and why skipping the K2 prologue is ineligible.
- [Current API audit](nonvisual-capability-audit.md): available routine calls,
  object-type-specific interactions, and evidence boundaries.
- [Installed Endar resources](endar-resource-route.md): authored locations,
  duplicated tags, door links, script references and save provenance.
- [Genuine new-game path](new-game-control-path.md): normal character generation
  and the missing signature-validated panel control needed to drive it.
- [World reader](world-probe-implementation.md): implemented bounded observation,
  validation, selectors, and outcome predicates.
- [Execution ledger](tas-execution-plan.md): measured results, review findings,
  decisions and remaining work.

## The important distinctions

`ActionOpenDoor` acts on a door; `ActionInteractObject` acts on a placeable.
NPC dialogue uses its own conversation path. The name of a routine and a
successful void return cannot establish that an action occurred. Ordinary
movement and door opening were measured in the diagnostic fixture; Trask
conversation initiation remains unresolved.

The existing Endar autosave contains an advanced character and later companions.
It is unsuitable for establishing a fresh campaign start. The complete route
must begin from normal character generation or a separately verified clean save.

Semantic automation and deterministic TAS replay have different acceptance
criteria. First complete the normal route with state-based checks. Then measure
clock, RNG, scheduling and save/replay behavior before claiming determinism.
Fixed-step timers alone do not establish deterministic replay.

Confirm the route before recording its complete replay. A qualifying video
must show the completed Endar Spire or full K2 prologue and at least 120 seconds
of active gameplay. Loading, pause, cutscenes, idle padding and camera-only
motion do not count toward that time. Diagnostic artifacts are kept separately
and are not campaign proof.

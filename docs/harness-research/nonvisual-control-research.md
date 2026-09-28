# Nonvisual control architecture for a KOTOR campaign harness

## Decision

Use the existing loopback JSON channel, main-loop drain, `lua` command, `kp.as`, and generated KOTOR routine bridge as the semantic environment API. Put route knowledge and recovery logic in the external Python driver. Use the already-installed `kq` command to compile static module resources into a navigation/interaction atlas, with PyKotor available only where `kq` does not expose a needed structure. Reconcile that atlas with live engine objects and state on every step.

This is the shortest credible path to completing the Endar Spire without pixels, timed key holds, warps, plot-variable writes, or script-side teleportation. Screenshots remain periodic sanity evidence. They are not observations, success criteria, or synchronization signals.

The current harness already supports the hard infrastructure: load/save, phase and module state, PC/party position and HP, dialog inspection/replies, globals, journal, events, fixed-step engine time, and main-thread command execution. The local capability audit also confirms that `kp.as(pc, fn)` supplies `OBJECT_SELF` while `ActionMoveToObject`, `ActionInteractObject`, `ActionAttack`, `GetObjectByTag`, nearest-object queries, distance checks, combat checks, death checks, and `GetCurrentAction` are generated routine-bridge calls. Ordinary action enqueueing therefore does not require new native wrappers as a prerequisite. The remaining work is route-specific live observation, verified action completion, and a driver that composes those calls safely.

## What the cited systems actually establish

### Semantic game agents

Voyager's useful result is architectural, not a drop-in controller. It uses an automatic curriculum, executable-code skill library, and iterative correction from environment feedback.^1 Its paper explicitly chooses code as the action space because programs express temporally extended and compositional behavior.^2 MineDojo supplies a task-rich simulator and large multimodal knowledge base, while its demonstrated agent learns a language-conditioned reward model and is evaluated on a bounded set of tasks.^3 Neither work shows that a vision model can reliably operate an arbitrary closed-source game through pixels, and neither provides KOTOR actions or state.

For KotorPhasor, copy the separation of concerns: a goal planner chooses a named skill; the skill invokes typed semantic actions; engine state verifies postconditions. Do not put an LLM in the frame loop. The Endar Spire route is fixed enough that a checked state machine is smaller and more reproducible than online curriculum learning. A learned planner can be added later above the same action API without changing the injected runtime.

### libTAS and determinism

libTAS records inputs at frame boundaries and hooks time, input, rendering, files, audio, and other external effects.^4 Its own documentation says native PC programs remain nondeterministic, identifies threading as the most severe source it cannot generally solve, and lists waits/spin-waits as softlock hazards.^5 Wine needs extra patching and is described as more fragile because behavior depends on Wine and rendering versions.^6 Savestates must coordinate threads, memory maps, files, pipes, TLS/registers, and X connections.^7

Therefore `fixed_step` in KotorPhasor is a repeatability aid, not TAS-grade determinism. A valid deterministic replay claim would require, at minimum: one exact game executable and data hash; fixed KotorPhasor, Wine, Xvfb, Mesa/llvmpipe, locale, CPU/runtime settings; intercepted wall/monotonic time and sleeps/waits; controlled RNG seeds and entropy; stable thread scheduling or proven absence of schedule-sensitive state; deterministic filesystem/network/audio behavior; and repeated end-to-end replays producing identical semantic traces. libTAS may help investigate this later, but its generic input movie is the wrong primary control surface for an engine-action harness.

### Targeted runtime instrumentation

Frida supports attaching to selected functions with `Interceptor`, calling known functions with `NativeFunction`, exporting RPC calls, and tracing chosen threads/blocks with Stalker.^8 Those are useful for short discovery probes: trace a harness-driven ordinary action, compare its call path and arguments, and stop when the existing routine's behavior is understood. A probe must not require a person to operate the game. Frida does not supply KOTOR object layouts, safe call phases, or semantic correctness.

GDB is suitable for breakpoints, watchpoints, call stacks, and one-off ABI validation. Its built-in process record/replay exists only on supported targets and records an instruction log rather than defining a game-control API.^9 `rr` can capture native Linux user-space process trees and replay instruction-level control flow, memory, registers, and syscall results; it also emulates a single-core machine and requires supported syscalls/CPU behavior.^10 That makes `rr` valuable for a native K2 crash or race after the controller exists. It is not the default route for K1-under-Wine control, and no source reviewed here establishes that this exact Wine/game/32-bit stack records successfully.

Full assembly or basic-block streaming should be rejected as the controller architecture. It produces high-volume implementation detail, perturbs timing, and still needs semantic reconstruction. Use targeted function probes only if an existing routine has ambiguous behavior or a missing live-state read must be recovered, then stop tracing. ReAgent and the local AgentDecompile project are static-recovery aids for that bounded work: ReAgent gathers decompilation, xrefs, structs, P-code, CFG, assembly, and nearby source, then applies checker, structural, build/test/runtime, and parity gates.^11 ReAgent explicitly calls its result conservative verification rather than proof of semantic equivalence.^12 Neither tool is a live gameplay controller.

### Static KOTOR resources

The local `kq` CLI is the practical first choice because it already indexes the installed game using engine resource precedence and prints decoded resources as JSON. A working Endar Spire query is `KQ_INSTALL=$PWD/tmp/k1_harness kq cat m01aa -t git --from end_m01aa.rim`. Its `which`, `cat`, `grep`, `graph`, and `export` commands cover source resolution, focused inspection, relationship discovery, and bulk JSON export.

PyKotor is useful when the atlas builder needs structures beyond `kq` output. Its GIT model contains placed creatures, doors, placeables, triggers, waypoints, encounters, sounds, stores, and cameras, including positions/orientations and instance properties.^13 Its BWM model exposes walkable faces and walkmesh geometry; area WOK data includes adjacency/edge structures used for pathfinding.^14 Its JRL model provides quest categories, tags, entries, completion markers, text, and plot indices.^15 DLG resources provide the authored conversation graph, links, conditions, scripts, and journal/quest effects, but runtime conditionals still have to be evaluated by the game. xoreos is an open-source Aurora-family engine reimplementation with KOTOR module, creature, script, and dialog code, useful as readable behavioral prior art rather than binary identity evidence.^16

Static extraction cannot tell whether an instance currently exists, is hostile, is dead, is unlocked, has changed faction, has a usable action, or has a runtime object ID. It also cannot decide which DLG links are active after scripts and globals run. The atlas proposes candidates and paths; the live engine oracle decides what is possible now.

## Minimal environment contract

No new native command layer is required for the first Endar Spire attempt. The driver can define a small, versioned set of Lua snippets over the existing `lua` request. Every mutating snippet uses `kp.as(actor, function() ... end)` and calls an ordinary engine action. Every wait reads engine routines or existing harness state. Commands are drained on the game main thread, but calls into original engine code must run outside an armed KotorPhasor fault guard; an engine fault must retain its native crash semantics rather than being caught as a recoverable harness fault.

| Driver skill | Existing engine surface | Required completion proof |
|---|---|---|
| `move_to_object(tag, nth, radius)` | `GetObjectByTag`, `kp.as`, `ActionMoveToObject` | distance falls below radius, module/dialog/combat changes, or `GetCurrentAction` reports failure/idle without arrival |
| `move_to_location(location)` | `kp.as`, `ActionMoveToLocation` | PC position reaches the target tolerance |
| `interact(tag, nth)` | `GetObjectByTag`, `ActionInteractObject`; door/placeable-specific queries where needed | door/open/locked state, dialog, inventory/state change, or module transition |
| `talk_to(tag)` | `ActionStartConversation`, existing `dialog` and `reply` commands | dialog becomes active and an active runtime reply is selected |
| `attack(target)` | `ActionAttack`, `GetIsInCombat`, `GetAttackTarget`, `GetIsDead`, HP reads | target death/invalidity or combat exit; a queued call alone is not proof |
| `cancel(actor)` | `ClearAllActions` through `kp.as` | `GetCurrentAction` becomes idle and movement/combat state settles |
| `observe_route(tags)` | object/tag/nearest/distance, position, locked/combat/death/current-action queries plus existing state/dialog/globals/journal/events | one compact semantic snapshot for the route objects that matter now |

The local audit distinguishes generated/bound routines from live proof. `ActionAttack` previously no-oped when the cheat console held focus; the loopback harness avoids that UI condition, but a dedicated live proof is still required. Action routines return no completion result, so a successful `lua` reply means only that the call executed without a bridge error.

Do not add a generic memory read/write command, arbitrary native-call command, streamed instruction trace, or duplicate C++ wrappers around these calls. Lua is an allowed transport for ordinary actions. Campaign acceptance should reject Lua or native calls that teleport/jump actors, warp modules, set plot/global/journal state, grant XP/items/levels, heal, spawn/remove/kill enemies, or otherwise bypass normal play.

## Static atlas

Build an offline atlas per module and game-data hash:

1. Resolve and decode resources with `kq`, recording the selected capsule/resource and game-data hash. Use `kq which` when duplicate resources exist.
2. Read GIT JSON into semantic landmarks: tag/template, type, position, bearing, linked module/door, conversation resref, and waypoint/trigger geometry.
3. If `kq` does not expose enough WOK/BWM structure, use PyKotor for walkable faces and adjacency. Join room meshes in world coordinates; door hooks and transition edges become portals.
4. Read DLG as a possible conversation graph and JRL as quest metadata. Annotate known route decisions, but never pre-label a conditional reply as active.
5. Emit compact route data. Runtime resolves known tags with `GetObjectByTag` and validates position/type/state. Use nearest-object queries for spawned or ambiguous actors; report ambiguity rather than guessing.

The driver should use hierarchical navigation: atlas A* between landmark portals, then `move_to` the next live object or waypoint and let the engine pathfinder handle local collision and avoidance. Replan after module transition, door-state change, displacement, combat, or a bounded no-progress result. This avoids rebuilding the engine's full navigation semantics outside the process.

## Endar Spire executor

Implement the run as a small goal graph with reusable skills rather than a monolithic timeline:

```text
load known pre-Endar save
  -> verify end_m01aa + live PC + advancing server tick
  -> converse with Trask using active reply text/link metadata
  -> follow atlas landmarks through ordinary move/interact actions
  -> resolve mandatory combat with target selection + normal attacks
  -> interact with doors, consoles, remains, and transitions as live state requires
  -> select ordinary dialog replies from active runtime choices
  -> verify journal/global/module milestones
  -> reach the escape-pod transition through engine actions
```

Each skill has `applicable(state)`, `start(action API)`, `progress(state/events)`, `success(state)`, and one bounded recovery. Examples: `talk_to(tag)`, `traverse_door(tag)`, `clear_hostiles(region)`, `use_placeable(tag)`, `travel_to(landmark)`, and `choose_reply(predicate)`. Store successful route fragments as data in the Python scenario layer. Voyager supports the value of compositional executable skills; it does not justify self-modifying code during an acceptance run.

Combat should remain deliberately simple: select the nearest live hostile threatening the party, enqueue an ordinary attack, and wait on combat/action/HP state. Re-target when the object dies or becomes invalid. Do not optimize feats, equipment, or leveling until a recorded run proves the base attack policy cannot finish the mandatory encounters.

Recovery order should also stay small:

1. If the action is pending and position/ticks advance, keep waiting.
2. If the engine reports path/action failure, cancel once and replan to the next atlas portal or a nearby walkable-face centroid.
3. If combat/dialog/module state changed, re-evaluate the goal rather than replaying the old command.
4. If server ticks stop, the process exits, the hook site poisons, or no semantic progress occurs after the bounded retry, fail and preserve the checkpoint/evidence. Do not teleport around the fault.

## Acceptance evidence

A qualifying run should be at least 120 seconds of **unsped, unpaused active gameplay** after the load reaches gameplay. Measure both monotonic host duration and advancing engine ticks; conservatively exclude boot, loading, movies, cutscenes, pause, and post-failure time. The route may use ordinary engine actions transported through `lua`/`kp.as`, ordinary dialog selection, save/load, and clean quit. Teleport/jump, `warp`, plot/global/journal mutation, XP/item/level grants, healing, enemy spawn/remove/kill calls, synthetic keyboard/mouse input, and pixel/OCR branching are disallowed.

Retain:

- executable/game-data/controller/atlas hashes and exact runtime versions;
- every request/reply/event with engine tick and monotonic timestamp;
- periodic full state snapshots and action postconditions;
- checkpoint saves at module/goal boundaries;
- a continuous video of the complete session, with screenshots only as supplemental sanity samples;
- a report proving required route milestones, active-gameplay duration, no forbidden commands, no poisoned sites, and clean termination.

Passing once proves that build and route instance. It does not prove deterministic replay or campaign-wide generality. Run the same trace at least three times before calling it repeatable; compare semantic milestone order and final state, and report divergence instead of hiding it behind retries.

## Implementation order

1. Prove one tagged-object `ActionMoveToObject` through loopback Lua, with distance and `GetCurrentAction` observations and no console focus.
2. Prove `ActionInteractObject` on one door and `ActionStartConversation` on Trask, using existing dialog state as the postcondition.
3. Prove `ActionAttack` on one mandatory hostile, using combat/target/death/HP state rather than script-call success.
4. Extract Endar Spire GIT/DLG/JRL with `kq`; add PyKotor BWM parsing only if route replanning needs geometry beyond tagged landmarks.
5. Add compact driver helpers around those existing calls and encode the goal graph, bounded recoveries, and route-specific observation.
6. Add the forbidden-action audit, 120-second active-time accounting, repeated semantic traces, and full-session video evidence.

Frida/GDB/ReAgent/AgentDecompile should enter only when a routine in steps 1–3 behaves ambiguously or a required state read is absent. `rr` and libTAS are follow-up tools for a reproduced native crash or a separately scoped deterministic replay effort.

## Sources

1. Wang et al., “[Voyager: An Open-Ended Embodied Agent with Large Language Models](https://arxiv.org/abs/2305.16291),” 2023.
2. Wang et al., “[Voyager](https://openreview.net/pdf?id=P8E4Br72j3),” NeurIPS 2023, §2.
3. Fan et al., “[MineDojo: Building Open-Ended Embodied Agents with Internet-Scale Knowledge](https://arxiv.org/abs/2206.08853),” 2022.
4. libTAS, “[How does it work? — Frames](https://clementgallet.github.io/libTAS/guides/how/#frames).”
5. libTAS, “[How does it work? — Determinism](https://clementgallet.github.io/libTAS/guides/how/#determinism).”
6. libTAS, “[How does it work? — Wine](https://clementgallet.github.io/libTAS/guides/how/#wine).”
7. libTAS, “[How does it work? — Savestates](https://clementgallet.github.io/libTAS/guides/how/#savestates).”
8. Frida, “[JavaScript API](https://frida.re/docs/javascript-api/)” and “[Stalker](https://frida.re/docs/stalker/).”
9. GNU GDB, “[Process Record and Replay](https://sourceware.org/gdb/current/onlinedocs/gdb.html/Process-Record-and-Replay.html).”
10. rr Project, “[rr: lightweight recording & deterministic debugging](https://rr-project.org/).”
11. Dryxio, “[ReAgent](https://github.com/Dryxio/reagent),” README and [architecture](https://github.com/Dryxio/reagent/blob/main/docs/architecture.md).
12. Dryxio, “[ReAgent — verification limits](https://github.com/Dryxio/reagent#what-it-does).”
13. OpenKotOR, “[PyKotor GIT model](https://github.com/OpenKotOR/PyKotor/blob/master/Libraries/PyKotor/src/pykotor/resource/generics/git.py).”
14. OpenKotOR, “[PyKotor BWM model](https://github.com/OpenKotOR/PyKotor/blob/master/Libraries/PyKotor/src/pykotor/resource/formats/bwm/bwm_data.py).”
15. OpenKotOR, “[PyKotor JRL model](https://github.com/OpenKotOR/PyKotor/blob/master/Libraries/PyKotor/src/pykotor/resource/generics/jrl.py).”
16. xoreos, “[xoreos](https://github.com/xoreos/xoreos)” and its [KOTOR engine sources](https://github.com/xoreos/xoreos/tree/master/src/engines/kotor).

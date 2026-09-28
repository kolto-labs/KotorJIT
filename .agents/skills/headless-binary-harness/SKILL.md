---
name: headless-binary-harness
description: Design a headless test harness that drives a closed-source executable by calling its own code, not by sending input. Use when asked to automate, test, or script a compiled application you can inject into, especially a game or GUI program with no scripting API and no accessibility tree.
---

# Drive a binary by calling it, not by typing at it

The naive harness sends keystrokes and waits a fixed time, then checks a
pixel. It fails on a slower machine, a different window manager, or a
loading screen that ran long. Every hour spent tuning the sleeps is an
hour spent encoding one machine's timing into a test.

The harness that works puts a command channel inside the process, runs
each command on the thread the application already uses, and reads the
application's own state to decide what happened. Screenshots become a
cross-check, never a wait condition.

This skill is the shape. It assumes you can load code into the target
(a proxy DLL, `LD_PRELOAD`, an existing plugin runtime) and that you have
or can build a table of addresses for its functions and fields.

## The five parts

**1. A control plane inside the process.** A listener thread owns a
loopback socket and parses newline-delimited JSON into a request queue.
It never touches application memory. Under Wine a loopback socket inside
a 32-bit DLL is a real host socket, so this works for Windows binaries
on Linux.

**2. A drain on the application's own loop.** Hook the main loop. Each
iteration, take a bounded batch off the queue and execute it there. That
thread is the only one on which calls into the application are safe.
Cap the batch so a flood cannot stall a frame.

**3. A state oracle.** One command returns everything the driver needs
to decide: the phase (menu, loading, running, blocked), the current
scene or level, a frame counter, the player or session objects, and a
hash of the mutable state. Every field is read from a named structure,
never inferred from an image. The driver waits on these values.

**4. An event stream.** Every hook the runtime already owns pushes a
record into a fixed ring with a sequence number. The driver asserts
orderings ("the level loaded, then the area was entered") by cursor
rather than by sleeping between them.

**5. An outside driver.** It stages a writable tree, starts the virtual
display and the process, connects, runs scenarios, and tears down. It
holds every timeout, every retry, and every watchdog. The in-process
side stays a thin executor.

**Fastest accurate execution is the default.** A harness that also serves as
a TAS applies the highest live-verified engine time scale before the first
route action. The scenario format exposes that scale as a typed setting and
allows an explicit retail-speed opt-out. Report requested and effective scale;
fail clearly when the target cannot provide the requested control. Accelerate
world time, movement, combat, and scripted delays through the application's own
timer controls. Replace voice waits with a native skip only when engine state
says the line is skippable. File I/O and rendering remain wall-clock work.

Optimize the route itself as well as the clock: choose the shortest proven
dialog branches and transitions, eliminate fixed sleeps in favor of state or
event predicates, and use checkpoints only where they reduce total rerun cost.
Correctness predicates remain identical at every speed. Calibrate timing
controls inline against the live process before persisting them in a scenario.

## Rules that are not preferences

**Never block the loop you are draining.** If a command waits for state
the main loop must advance, you have deadlocked the process: the loop
that would advance it is the loop you are sitting in. Commands issue and
return. The driver polls. If an operation genuinely needs several
frames, drive it as a state machine advanced one step per iteration and
reply as soon as it is armed.

**Never pass a null `this` to a method.** A decompiler that shows an
argument going unused is describing one path through the function. If
you need the behaviour and not the object, reimplement the helper
yourself. Reading an archive and copying files is a hundred lines you
control; a null pointer in someone else's code is a hang you cannot see
into.

**Every call is bracketed but not guarded.** If the runtime has a
fault-catching guard around hook bodies, engine calls must run OUTSIDE
the armed region. A guard that catches a fault inside application code
leaves that code half-finished and its state torn, and turns a crash you
could diagnose into a silent degradation. Arm the guard around your own
parsing and serialising only.

**Never hold a lock across the guard.** A guard that unwinds with
`longjmp` runs no destructors, so a held mutex is never released and the
listener blocks forever. Swap the batch into a local before the guarded
region and push replies after it.

**Assume reentrancy.** Applications call their own loops from inside
each other during transitions. Keep a thread-local flag and skip the
drain when it is already running.

**Resolve by name, degrade by name.** Address every function and field
through a logical name looked up per build. A command whose sites did
not resolve answers `unsupported` and says which name is missing. That
turns a whole class of "it silently did nothing" into a reported skip.

## What the driver watches for

| Verdict | Signal |
|---|---|
| Crash | process gone, or the loader or runtime logged a fault |
| Hang | process alive and the frame counter has not moved |
| Stuck load | the phase stays loading with no sub-state advancing |
| Softlock | the state fingerprint stops changing while a step waits for progress |

The fingerprint is the cheap part and the valuable part: hash the
mutable state, quantise positions, and compare. If nothing in the world
has changed for a while and the scenario is still waiting, that is the
bug the harness exists to find.

On a hang, take one stack dump before killing the process. A debugger
attached to the wedged process answers in one shot what a day of
guessing will not.

## Bring-up order

Prove each layer before building the next. Each of these has failed in
practice at exactly this step:

1. The process starts headless and the runtime loads. Read the log.
2. The runtime resolves its sites on this build. Count them.
3. The channel accepts a connection and answers a ping.
4. The state oracle returns something true at the first screen.
5. One command that changes state returns and the state changes.
6. A scenario runs end to end.

Do not write scenarios before step 5. Build a complete route segment
interactively, issuing one command and checking its engine-state postcondition
before choosing the next. Persist the scenario only after the full segment or
quest succeeds start to finish. A scenario failing at step 5 looks exactly like
a scenario that is wrong.

## Route frontier control loop

For an active campaign route, the unit of work is one **frontier advance**, not
a new scenario, primitive, report, or decompiler note. Before a live run, name
the current checkpoint, one engine action, and its exact engine-state/event
postcondition. Run that action inline, record the pre-state, request, post-state,
event cursor, elapsed time, and the next gate in the mission state. A stable
authored checkpoint is useful local evidence. Campaign progress requires an
explicit continuous reproduction from the route's declared starting state.

After two experiments anywhere on the route fail to advance it, review the
strategy before another boot. Switch to the smallest evidence source that distinguishes the
remaining hypotheses: a targeted corpus query, a newly justified native engine
call, or one debugger stack/trace. Do not create a third diagnostic scenario.

Do not promote a TOML route, gameplay test, or proof recording until a receipt
shows the same inline segment reached its named final checkpoint. The promoted
route must retain the receipt/run identifier and terminal predicate. Diagnostics
and partial sequences stay disposable; they are not campaign scenarios.

Review progress using only: fresh boots, frontier advances per experiment, and
promoted-route pass rate. If artifacts grow while the frontier does not, stop
adding artifacts and return to the current gate.

Keep those numbers in `.mission/route-progress.json`; prose in `state.md` is not
the scorecard. Each frontier row has a stable id, terminal predicate, status
(`unattempted`, `observed`, `reproduced`, or `contradicted`), receipt, attempts,
and elapsed experiment seconds. Only `reproduced` rows with explicit
`proof_scope = "continuous"` count as campaign progress. Unscoped legacy receipts
and disposable checkpoint runs count separately as checkpoint evidence. A new
observation that disagrees with a credited receipt changes that row to
`contradicted` immediately, removes it from the verified-progress count, and
keeps it as the current unresolved gate until the disagreement is explained and
reproduced from its checkpoint.

Before dispatching an agent or starting a live process, run
`harness_progress.py begin` for the selected `current_gate`; do not merely
mention a frontier in prose. Its admission requires an inline experiment, the
next route milestone, and the proven primitives that will be composed in that
same run. A worker that needs a new primitive must name the exact current-gate
action it unblocks. Research, tool repair, signatures, and primitives are
enabling work; record their outcome outside the route ledger unless they are
executed in that composed attempt. They never advance the route numerator.
After each
experiment print the mechanical delta: `reproduced_before`,
`reproduced_after`, `frontier_advanced`, `elapsed_seconds`, and `next_gate`.
`live_seconds` remains a compatibility alias for elapsed experiment time; it
does not measure active gameplay or exclude enabling work.
Zero-delta runs consume the route's two-attempt budget even when they
discover something useful.

The played route is a sequential, stateful critical path and has one controller.
Parallel workers may recover independent evidence or implement an already-named
primitive, but they do not own separate route strategies or live processes.
Their contract is: frontier row, executable result, independent postcondition,
and deadline. At the deadline, integrate the result or cancel the worker and
close the experiment as zero-delta; do not let background investigation extend
an open live attempt.

Use `python3 tools/harness_progress.py begin ...` immediately before the inline
current-gate attempt. Do not open a route experiment merely to bind a site,
write a scenario, or make a research note: those activities used to consume
the budget without advancing play. Finish the attempt afterward. Check `status`
at least every 15 minutes, including while an
experiment is open. Its route-wide watchdog reports open experiment age,
minutes without continuous progress, consecutive zero-delta outcomes, and
`needs_strategy_review` with reasons. Before the first continuous advance the
clock starts at the first recorded experiment, identified by `progress_clock_basis`.

After two zero-delta outcomes or 15 minutes without progress, another `begin`
requires `--strategy-review` plus the eliminated hypothesis, new evidence,
changed action/precondition, and predicted observable difference. The review
must differ from the previous one and explain the bottleneck, the changed
strategy, and one bounded next proof. Do this review during an overdue open
experiment too; stop repeating its current approach, record the outcome, then
start the changed approach. Report the mechanical evidence to the user when
this happens. Changing gate names, writing another primitive, or repeating
queries does not reset the clock. The controller must enforce the behavior;
the tool cannot decide whether different prose describes a real strategy change.

`finish ID reproduced --receipt PATH` defaults to checkpoint evidence. Use
`--proof-scope continuous` only when that receipt establishes continuous play
from the declared start. Repeat `--covers GATE` for every predicate demonstrably
covered by the same receipt; the target gate is included automatically. One
terminal run can cover many gates. Gate list order is not a dependency graph:
verify active-resource semantics and never infer missing predecessor evidence.
`acceptance_complete` is true only when every explicitly declared `required_gates`
entry has continuous proof; it is unknown when required gates are undeclared.
Continuous promotion requires a JSON receipt emitted by the run verifier with
this contract (replace the route and predicate IDs with the actual run):

```json
{
  "schema": "kpharness.route-proof.v1",
  "route": "k1_endar",
  "proof_scope": "continuous",
  "start": {"kind": "new_game", "verified": true},
  "result": "pass",
  "terminal_predicates": {"escape_pod": true}
}
```

The verifier must evaluate the new-game starting state, uninterrupted route
continuity, and every listed engine-state/event predicate before emitting pass.
Never author this wrapper manually to upgrade checkpoint evidence. The progress
tool validates these exact claims and requires literal `true` for every covered
gate, including the target. It rejects non-JSON, wrong-route, checkpoint, failed,
and incomplete receipts before changing state. Existing checkpoint receipts
remain compatible. This contract checks claims; it does not authenticate their
producer or independently replay the game. Keep underlying run evidence in the
receipt so the controller can audit the verifier's conclusion.

Run `python3 tools/harness_progress.py self-check` to verify these mechanics
without changing the ledger or starting a game.

Every `begin` names `--active-transition`, `--precondition`, `--postcondition`,
`--route-milestone`, `--uses-proven`, and `--deadline-seconds`; its gate must
equal the ledger's `current_gate`. `--execution-mode inline` is mandatory.
`static_scenario` is rejected until the route segment has succeeded inline.
Run `status --enforce` at the deadline; a nonzero result means the controller
must close the current experiment before issuing another route action.
`finish --lineage-transition-advanced` records useful progress inside a
continuous run without changing the campaign numerator.

`current_gate` is the deliberately selected investigation target; change it
with `harness_progress.py select ROUTE GATE`. `verified_frontier` is updated
only from explicitly continuous receipts and is recomputed when evidence is
contradicted. Checkpoint evidence remains available without inflating that field.

## Testing the harness offline

The channel, the codec, the ring and the state classifier are ordinary
code and belong in the unit test suite with no application present:
malformed input gets an error and keeps the connection, the ring keeps
order across wrap-around, a second client is refused, requests execute
on the draining thread, and the classifier maps a known field snapshot
to the right phase. When a live run shows a wrong phase, add that exact
field snapshot as a case; it is the cheapest regression test you will
write.

See `binary-harness-bringup` for the live traps, and
`re-corpus-site-binding` for turning a decompiled corpus into the
address table this design assumes.

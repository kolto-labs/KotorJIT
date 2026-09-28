# Harness progress and control-loop audit

## Finding

The harness has accumulated substantial low-level capability, but its delivery
rate against the requested outcome is poor. The dominant bottleneck is the
execution strategy: work has been measured by local discoveries and completed
primitives rather than by the furthest authored game state reached and proved.

## Measured progress

| Measure | Current evidence |
|---|---:|
| K1 run directories | 139 over 40.13 hours |
| Structured run reports | 44 |
| Passing reports | 12 (27.3%) |
| Failing reports | 32 |
| Persisted TOML scenarios | 19 |
| Existing proof videos | 2 |
| Complete Endar proofs | 0 |
| K2 gameplay proofs | 0 |

The tracked diff contains 14,309 additions and 287 deletions across 32 files.
The untracked `src/harness/` and Python driver contain another 10,908 lines.
The control plane dispatches 34 commands, including state/events, load/save,
fresh character generation, dialogue, speed/fixed-step timing, movement and
interaction support, GUI/modal operations, inventory transfer, party
selection, auto-level, party-leader selection, journal inspection,
screenshots, and shutdown.

Persisted live successes include K1 gameplay-state and journal access, fresh
character generation, the first ordinary door transaction, Trask approach,
and induced softlock detection. Later inline work reached the first locker,
took its contents, equipped required items, and added Trask to the party. The
first leader-switch attempt used the wrong large server-side transition and
crashed. Its replacement now uses deferred `CSWParty::SetLeader`, passes all
offline checks, and awaits live proof.

The current proof videos are short state/journal demonstrations. Neither is a
complete Endar route or satisfies the required gameplay proof. No K2 gameplay
report exists.

## Where time went

The formal report set consumed about 71.6 minutes inside scenario execution;
manual and boot/debug sessions account for much more of the 40-hour span.
Ninety-five run directories have no report. Three consecutive load-state
timeouts consumed more than 15 minutes. Four persisted locker attempts failed
around the same pause/modal gate. Several later sessions lasted 25 to 63
minutes without producing a final report.

Build throughput is not the primary constraint. The latest incremental build
completed in 0.54 seconds because nothing needed rebuilding. The full local
verification completed with 11/11 CTest targets and 112/112 offline Python
tests passing. Live iteration loses time after each newly observed gate: static
resource analysis, native reverse engineering, a new control primitive, a
restart, and another traversal from the beginning.

## Why self-evaluation failed

The project skill already required inline reactive probes, fastest accurate
execution, and scenario persistence only after a complete segment. Execution
did not follow those rules: narrow diagnostic scenarios were repeatedly saved
before Endar passed.

The global self-optimization skill also used qualitative boundaries such as
“meaningful decision boundary.” A newly decoded dialogue edge or recovered
function could be treated as progress and reset attention even when the route
frontier did not move. It had no explicit milestone unit, experiment budget,
consecutive non-advancement threshold, or controller responsibility.

The repository mission state made the problem worse. It still described the
old scanner/director prototype, listed reply selection as pending, and deferred
full-campaign live walking. That contradicted the active goal and supplied
stale direction after context handoffs.

## Research basis for the correction

Anthropic's long-running-agent work records the same broad failure classes:
agents attempt too much, later contexts lose state, features are marked done
without end-to-end proof, and structured feature/progress artifacts improve
continuity. It recommends selecting a bounded feature, keeping a durable
requirements list, and verifying the running product end to end before marking
the feature complete.[^1]

Anthropic's later planner/generator/evaluator harness adds an explicit contract
for each sprint and hard evaluator thresholds. The evaluator exercises the
running application against the agreed behavior rather than scoring the amount
of implementation activity.[^2]

Google Research reports that multi-agent systems help parallelizable work but
hurt sequential planning tasks by 39–70% in its tested configurations. Tool
coordination adds further overhead, while a centralized orchestrator reduces
error propagation.[^3] KOTOR traversal is a sequential environment interaction;
resource decoding and binary analysis can run in parallel, but the controller
must serialize their results into one live frontier.

ReAct supports interleaving reasoning with environmental actions so each new
observation updates the working state.[^4] That supports inline route probing,
but it does not by itself prevent fixation on one local gate. The missing
control is an outcome-level budget and a forced strategy change when the
frontier does not advance.

## Corrected operating contract

1. Keep one route frontier: module, relevant globals/journal, party and leader,
   coordinates, active dialogue entry, next authored gate, and its evidence.
2. Before expensive work, name the next user-visible milestone, independent
   acceptance evidence, and experiment budget.
3. Two consecutive experiments that do not advance the frontier force a
   materially different strategy. More facts about the same blocked gate do
   not reset the budget.
4. Keep one healthy process warm. Use inline commands and short read deadlines.
   Checkpoint after every real frontier advance.
5. Do not add a general engine primitive until the immediate authored gate is
   shown to require it.
6. Do not persist another narrow diagnostic scenario. Capture commands during
   discovery and write the complete scenario only after the module passes.
7. Delegate only independent evidence work. Every subagent returns the next
   executable command, expected engine-state postcondition, and evidence
   source. One controller owns integration and route progress.
8. Review hourly using frontier advances per boot, furthest plot/module state,
   and wall time since the last advance. Code volume and local findings are
   diagnostic measures, not outcome progress.

The global `self-optimizing-execution` skill and `.mission` state now encode
these controls. The immediate critical path is unchanged: live-prove deferred
party leadership at the Trask door in at most two attempts, checkpoint the
advance, and continue forward through Endar without creating another scenario.

[^1]: Anthropic, [Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents), 2025.
[^2]: Anthropic, [Harness design for long-running application development](https://www.anthropic.com/engineering/harness-design-long-running-apps), 2026.
[^3]: Google Research, [Towards a science of scaling agent systems](https://research.google/blog/towards-a-science-of-scaling-agent-systems-when-and-why-agent-systems-work/), 2026.
[^4]: Google Research, [ReAct: Synergizing Reasoning and Acting in Language Models](https://research.google/blog/react-synergizing-reasoning-and-acting-in-language-models/), 2022.

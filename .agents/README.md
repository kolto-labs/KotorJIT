# Reusable skills and agents

Tool-agnostic and checked in, because `.claude/` and `.cursor/` are not.
Point whichever assistant you use at these paths.

These were extracted from building the headless harness in
[`docs/harness-design.md`](../docs/harness-design.md). Nothing here is
specific to this game or this engine: the subject is "a compiled program
you can load code into". The harness in this repository is the worked
example.

## Skills

| Skill | Use it when |
|---|---|
| [`headless-binary-harness`](skills/headless-binary-harness/SKILL.md) | Designing a harness that drives a closed-source executable by calling its own code instead of sending input |
| [`binary-harness-bringup`](skills/binary-harness-bringup/SKILL.md) | The harness builds and its unit tests pass, but the live run will not boot, will not progress, or hangs |
| [`re-corpus-site-binding`](skills/re-corpus-site-binding/SKILL.md) | Turning decompiled or reverse-engineered material into addresses and offsets a runtime will call |

## Agents

| Agent | Owns |
|---|---|
| [`harness-control-plane-engineer`](agents/harness-control-plane-engineer.md) | The in-process channel: commands, state oracle, event ring, offline tests |
| [`binary-live-bringup-debugger`](agents/binary-live-bringup-debugger.md) | Real headless runs and evidence-backed diagnosis of what went wrong |
| [`corpus-site-binder`](agents/corpus-site-binder.md) | Read-only corpus work producing bindings with two-signal evidence |

The three agents divide by authority, not by topic. The engineer writes
channel code and never guesses an address. The binder reads the corpus
and never writes calling code. The debugger runs the application and
never loosens a test to make it pass. When work crosses a boundary, hand
off rather than widen a role.

## Research behind the design

[`docs/harness-research/`](../docs/harness-research/) holds the mapping
reports and adversarial critiques the design was built from: the runtime
and hook engine, the scripting host, the prior harness and why it failed,
the engine's boot, conversation and save paths, multi-build support,
build conventions, external prior art, and the two critic passes that
corrected the first draft. Read those before re-deriving any of it.

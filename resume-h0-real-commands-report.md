# H0 real-commands regression target resume

Date: 2026-09-27. Worktree: `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`.
No game, Wine, display, live diagnostic, reset, stash, stage, or commit was used.
The shared `/tmp/lifecycle-cfg` build was not run by this slice.

## Ownership and changed paths

Owned paths for this slice were exactly:

- `tools/kp_harnessdrain_test.cpp` (new)
- additive target/test lines in `src/harness/harness.cmake`
- this report

`src/harness/commands.cpp` and `src/harness/channel.cpp/.hpp` were read-only referents.
The pre-existing `console_protocol.cpp` source-list change visible in the worktree was preserved and not part of this slice.

`kp_harnessdrain_test` links the single native `kphasor` target. That target owns and freshly compiles production `commands.cpp`, `channel.cpp`, `ring.cpp`, and their production dependencies. The fixture intentionally does not compile a second copy of those process-wide sources: duplicate copies would make symbol interposition ambiguous and could exercise a different channel than the command implementation. CMake target creation is deferred until `runtime.cmake` has defined `kphasor`; the test has an explicit dependency on that target.

The CTest entry sets `KOTORPHASOR_NO_AUTOSTART=1` and has a 10-second timeout. The fixture uses only typed public harness headers, a loopback socket, the production process-wide EventRing, and `commands::{start,drain,stop}`.

## Checks

| claim | referent | checked | verdict | confidence |
|---|---|---|---|---|
| The fixture source is syntactically valid with the production include contract. | `tools/kp_harnessdrain_test.cpp` | `g++ -m32 -std=c++20 -Wall -Wextra -I src -fsyntax-only` returned rc 0. | holds | high |
| CMake registers the real-commands test after the production library target exists. | `src/harness/harness.cmake`, generated `/tmp/kp-h0-drain-cmake3/CTestTestfile.cmake` | Private configure returned rc 0; generated test entry names `kp_harnessdrain_test`, sets `KOTORPHASOR_NO_AUTOSTART=1`, and shows the deferred call site. | holds | high |
| The target exercises the freshly built production command path rather than a retained scratch object. | `src/harness/harness.cmake` target dependency and `src/runtime/runtime.cmake` `KP_HARNESS_SOURCES` | Target links `kphasor` exactly once and depends on `kphasor`; `commands.cpp` remains in the production source list. | holds | high; runtime execution still awaits root's build |
| A healthy subscribed client receives an event and remains connected. | `tools/kp_harnessdrain_test.cpp`, first case | Test code sends `subscribe`, pushes `h0.control`, pumps `commands::drain`, and checks one event plus no EOF. | test encoded; execution pending | medium |
| A malformed line receives one error and no post-condemn event frame follows it. | `tools/kp_harnessdrain_test.cpp`, condemned case; production `commands.cpp:1430-1490` | Test pushes an event each pump, sends `{bad`, and asserts exactly one error, error-final ordering, and EOF. | test encoded; execution pending | medium |
| A new generation is not poisoned by the condemned generation. | `tools/kp_harnessdrain_test.cpp`, reconnect case | Test reconnects after the condemned case, subscribes, pushes `h0.reconnect`, and checks delivery while open. | test encoded; execution pending | medium |
| A good request before malformed input survives while the later request is refused. | `tools/kp_harnessdrain_test.cpp`, same-batch case | Test sends good/bad/good in one write and checks id 9 once, id 10 zero times, exactly two lines, then EOF. | test encoded; execution pending | medium |

## Source integrity

- `sha256sum tools/kp_harnessdrain_test.cpp`: `c7fca257296ed4a4d80527d4e891c5f646d2bcd95d1733a1165efa9a98eb9451`
- `sha256sum src/harness/harness.cmake`: `009afc838a4976c06b57a5a484c2888dbbf86c40ec41977329f50cb4b2b41643`
- read-only `sha256sum src/harness/commands.cpp`: `1a90490c84fff73c45389eea4eb5ef20f23b25fae67c2d2e281be4f373469e29`
- `git diff --check` passed for the owned tracked edit; the new test passed the same syntax check.

## Grill me, weakest first

1. **Weakest:** the green runtime execution has not been run in this slice. A private configure and syntax check prove graph/source validity, not a linked executable or regression result. Root must build `kp_harnessdrain_test` in the owned shared build and retain stdout/exit code.
2. The red control has not been run here. Root requested a private `Channel::push_reply` old-admission mutant; it must be compiled outside the worktree and demonstrate the error-final invariant fails before accepting the green result.
3. The test's condemned assertion deliberately relies on error-final ordering plus EOF. An event label may be delivered before the malformed request is processed, so the test does not claim that every `h0.after_bad` label is absent from the entire receipt. The relevant property is that no frame follows the final error after condemnation.
4. The target relies on the native `kphasor` shared target for typed runtime/API dependencies. That is the intended single-copy linkage, but it makes a successful result dependent on the root build completing with the current source graph.

## Remaining gates

Root owns the next gates: build the deferred target, run it with `KOTORPHASOR_NO_AUTOSTART=1`, run the private old-admission mutant against the same fixture, retain exact stdout/exit lines, and append those results here or in the root ledger. No product command/channel edits are proposed by this slice.

## Private red control after freeze

Root's shared `/tmp/lifecycle-cfg/libkphasor.so` and `kp_harnessdrain_test` were available. A private executable was linked from the frozen fixture plus a one-method old-admission mutant, with `-Wl,--export-dynamic`; no duplicate channel or command object was linked.

Claim: the old admission behavior fails the condemned-client invariant while the other fixture routes remain healthy.
Referent: `/home/brunner56/kp-live-20260922/resume-h0-mutant/run.stdout`, `run.rc`, `symbols.txt`.
Checked: the executable exported `T kp::harness::Channel::push_reply(...)`; the run returned rc 1; stdout contained `[FAIL] the error is the final line; no post-condemn event follows`; healthy subscriber, reconnect, same-batch good-before-bad, post-bad refusal, and EOF checks passed. The wrapper returned 0 only after validating the expected targeted failure.
Verdict: holds for the private red control.
Confidence: high.

Detailed mutant source, wrapper, hashes, and exact receipt are preserved in `/home/brunner56/kp-live-20260922/resume-h0-mutant/receipt.md`. Root still owns the separate green production-target run and its stdout/exit receipt.

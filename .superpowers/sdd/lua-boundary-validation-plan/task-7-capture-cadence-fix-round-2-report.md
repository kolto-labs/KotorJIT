# Task 7 capture cadence fix: round 2 implementation report

Date: 2026-09-27

Worktree: `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`

This round addresses every remaining Critical and Important finding in the two appended round-1 re-reviews. All validation remained host-only. No real FFmpeg, FFprobe, Gamescope, X11 server, Wine process, or game process was launched. No files were staged or committed.

## Completed repairs

- Schema-2 readiness now requires `capture_gate.status == passed`, `route.predicates_passed is true`, a nonempty completed route step list whose every step has `status == ok`, and the existing report artifact and completion timestamps. `schema2_receipt()` includes the capture gate and uses the same route primitives when computing `ok`.
- Visual acceptance verification and accepted export both rerun authoritative completed execution readiness. A refreshed digest cannot make an explicit capture failure acceptable.
- Root-capture argv validation now requires the producer's complete ordered FFmpeg command grammar, including the contiguous x11grab input-option segment before `-i`, one inherited descriptor progress target, and exactly one inherited staging-directory `continuous.mp4` output. Missing, changed, appended, or arbitrary destinations fail closed.
- Cadence readiness validates finite and legal numeric domains, reconstructs interval gaps, histograms, percentiles, maximum gap, threshold counts, frame/span/rate/slot arithmetic, and missing/drop ratios from serialized interval PTS. Total terminal duplicates must be zero.
- Marker receipts are bound to the capture startup monotonic origin within their declared 100 ms uncertainty. Acceptance interval bounds must lie within endpoint uncertainty.
- The producer serializes the included interval PTS and both cumulative FFmpeg progress samples bounding the interval. Readiness requires those samples to surround the selected interval and recomputes duplicate/drop deltas from their cumulative counters.
- Same-poll start/end markers retain byte/sequence ordering and use adjacent poll-uncertainty bounds for a conservative nonzero cadence interval.
- FFmpeg progress uses an inherited descriptor (`/proc/self/fd/<n>`) created with exclusive, no-follow semantics. A raced caller-visible progress symlink cannot redirect FFmpeg writes.
- All diagnostic/staging acquisition after preflight is inside the guarded start lifecycle. Setup collisions create typed `capture_setup_failed` evidence and close the log, progress descriptor, staging descriptor, run-directory descriptor, and owned staging directory. `stop()` is safe before start and after partial setup.
- Background and synchronous final binding checks catch `subprocess.SubprocessError`, including `TimeoutExpired`, and record terminal `capture_binding_changed` evidence.
- Documentation now describes inherited progress transport, same-poll interval bounds, serialized PTS/progress recomputation, and the route/capture gates.

## TDD evidence

The authoritative-gate regression was run before production changes and reproduced 11 independent false-ready categories: failed capture gate; failed predicates; failed or absent steps; missing or appended output; source option drift; nonzero terminal duplicates; negative/NaN or contradictory gap evidence; marker clock drift; progress bounds that do not surround the interval; reversed progress bounds; and cumulative counter/delta contradictions.

Lifecycle regressions cover same-poll finalization, setup collision cleanup, never-started stop, watcher timeout, final binding timeout, and progress-path symlink replacement while FFmpeg writes through the inherited descriptor.

## Final validation

```text
PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_backend_test.py
69 tests passed

PYTHONPATH=scripts/harness python3 tools/kpharness_creative_test.py
30 tests passed

PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_boot_repair_test.py
41 tests passed

python3 -m py_compile [eight scoped Python files]
PASS

git diff --check [scoped implementation, test, and documentation files]
PASS
```

Total focused tests: 140 passed.

## Files changed in this task unit

- `scripts/harness/kpharness/recording.py`
- `scripts/harness/kpharness/display_backends.py`
- `scripts/harness/kpharness/creative.py`
- `scripts/harness/kpharness/creative_accept.py`
- `scripts/harness/kpharness/creative_export.py` (preserved prior round behavior; validated through the strengthened shared gate)
- `tools/kpharness_gamescope_backend_test.py`
- `tools/kpharness_creative_test.py` (prior round tests retained)
- `docs/creative-runner.md`

## Remaining proof boundary

These mocked/static checks establish deterministic lifecycle and receipt contracts only. They do not establish real FFmpeg inherited-progress compatibility, live private-root SHM capture, source cadence on the GPU path, visual framing, distinct rendered frames, or K1 behavior. The separately serialized bounded animated-pattern diagnostic remains the next live proof step after independent review authorizes it.

# Task 7 capture cadence fix: round 3 implementation report

Date: 2026-09-27

Worktree: `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`

This round closes all Critical and Important findings in the appended round-2 reviews. Work remained host-only and mock-driven. No real FFmpeg, FFprobe, Gamescope, X11/Xvfb server, Wine process, or game process was launched. No files were staged or committed.

## Repairs

- Added the hard-coded, versioned `gamescope-cadence-v1` policy. Gamescope capture is fixed at 60 FPS with a 99% minimum rate, 0.5% maximum missing/drop ratio, and 50 ms maximum gap. The producer rejects another requested rate, serializes the policy, and the authoritative verifier requires exact policy and threshold equality.
- Added reusable authoritative PTS-summary validation. Every named interval must have strictly increasing finite PTS entirely inside its serialized bounds, exact counts/span/rate/slots/histogram/percentiles/maximum/gap counts, canonical thresholds, and a status derived from the trusted policy.
- Bound every named interval to its actual start/end markers within each marker's declared uncertainty. Duplicate marker-pair interval representations are rejected. The producer no longer emits the configured acceptance pair twice when it is also an adjacent named-marker interval.
- The whole-capture PTS summary is independently recomputed, including its missing ratio. Fabricated or partial whole-capture evidence is rejected.
- Terminal diagnostics must contain the exact canonical cumulative counters. Terminal `frame`, `out_time_us`, `dup_frames`, and `drop_frames` must be nonnegative integers, must not regress below the interval's right cumulative sample, and terminal encoded time must cover the measured whole-capture PTS clock. Terminal duplicates remain exactly zero, which also rejects equal nonzero left/right interval duplicate totals.
- Added structured capture transport metadata for the inherited progress regular-file descriptor and private output-directory descriptor. The verifier parses descriptor numbers from argv, requires both to be nonstandard and distinct, and requires exact metadata/argv role agreement.
- Start now tracks whether spawn was attempted. Every generic setup exception before `_popen()` is `capture_setup_failed`; `_popen()` failure remains `capture_process_exited`.
- Acceptance verification and export regressions confirm that terminal/right-sample contradictions remain rejected even after an attacker refreshes the execution and acceptance digests.
- Operator documentation now records the fixed policy, full PTS/terminal rules, and descriptor-role contract.

## Red-first evidence

Before production changes, the new authoritative mutation test reproduced ten false-ready receipt states:

1. Fully recomputed degraded cadence admitted by loosened thresholds.
2. Lowered requested capture rate.
3. PTS displaced outside the marker interval.
4. Duplicate contradictory acceptance intervals.
5. Fabricated whole-capture summary.
6. Zero terminal encoded clock.
7. Terminal frame regression below the right cumulative sample.
8. Equal nonzero left/right cumulative duplicate totals hidden behind a zero delta.
9. Aliased progress/output descriptor roles.
10. Standard or metadata-mismatched descriptor roles.

A separate lifecycle regression reproduced generic pre-spawn `OSError` being mislabeled as `capture_process_exited`. All eleven cases are now green.

## Final validation

```text
PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_backend_test.py
72 tests passed

PYTHONPATH=scripts/harness python3 tools/kpharness_creative_test.py
30 tests passed

PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_boot_repair_test.py
41 tests passed

python3 -m py_compile [eight scoped Python files]
PASS

git diff --check [scoped implementation, tests, and documentation]
PASS
```

Total focused tests: 143 passed.

## Round-3 files edited

- `scripts/harness/kpharness/recording.py`
- `scripts/harness/kpharness/display_backends.py`
- `tools/kpharness_gamescope_backend_test.py`
- `docs/creative-runner.md`

Earlier task-unit changes in `creative.py`, `creative_accept.py`, `creative_export.py`, and `tools/kpharness_creative_test.py` were preserved and revalidated.

## Remaining proof boundary

These checks establish deterministic producer, lifecycle, schema, acceptance, and export contracts under mocks. They do not establish real FFmpeg inherited-file behavior, live Gamescope private-root capture, active MIT-SHM use, GPU cadence, distinct rendered frames, visual framing, or K1 behavior. The separately serialized bounded animated-pattern diagnostic remains the next live proof step only after both independent re-reviews authorize it.

# Task 7 capture cadence fix: round 5

Date: 2026-09-27

## Scope

This round closes R4-1 through R4-3 from both round-4 reviews. It remains a
host-only implementation: no Wine, game, Gamescope, X11 server, FFmpeg, or
FFprobe process was launched. All process behavior in the regressions is mocked.

## Changes

- Visual acceptance now opens the public master with `O_NOFOLLOW`, retains and
  checks its regular-file identity, copies and hashes that descriptor into an
  unpredictable private acceptance directory with exclusive creation, and
  probes only the stable copy. It verifies both stable-copy and public-master
  identity/digest after the probe. Public mutation during the probe is a typed
  acceptance failure.
- Export reuses the same stable-copy primitive, retaining the existing accepted
  receipt checks before and after rendering.
- Completed route evidence now opens the stated run-local `report.json` with
  `O_NOFOLLOW`, enforces a bounded regular file and exact SHA-256, validates the
  canonical `ScenarioRunner` report and successful step-result schema, and
  requires the duplicated receipt step list to equal the report list exactly.
  Missing reports, fake digests, arbitrary fields, malformed steps, and failed
  reports therefore fail readiness, acceptance, verification, and export.
- Canonical frame-PTS probing no longer uses `check_output`. FFprobe stdout is
  incrementally drained through a nonblocking pipe while the child runs. The
  child is killed and reaped on the 16 MiB limit or timeout; nonzero exit,
  malformed JSON, nonfinite timestamps, and more than 250,000 frames fail
  closed. Python reads at most 16 MiB plus one byte.
- Documentation describes the stable acceptance probe, canonical route report,
  and bounded ffprobe process behavior.

## Regression coverage

- A probe callback mutates and restores the public master while inspecting the
  private stable input. Acceptance rejects the changed public identity and the
  callback never receives the public master path.
- Route readiness rejects a missing report, a false report digest, and an
  otherwise passed step carrying an unsupported arbitrary field.
- The oversized-output test exposes a sparse mocked stream past 16 MiB without
  constructing that byte payload in Python, then proves the child was killed
  and reaped.

## Validation

Final serial run:

- `python3 tools/kpharness_creative_test.py`: 30/30 passed.
- `python3 tools/kpharness_gamescope_boot_repair_test.py`: 41/41 passed.
- `python3 tools/kpharness_gamescope_backend_test.py`: 77/77 passed.
- Total focused tests: 148/148 passed.
- `python3 -m py_compile` passed for the six owned harness modules and both
  focused test modules.
- `git diff --check` passed.

The expected mocked cleanup/capture diagnostics printed by the creative and boot
repair suites remain test fixture output, not live process failures.

## Files changed in round 5

- `scripts/harness/kpharness/recording.py`
- `scripts/harness/kpharness/display_backends.py`
- `scripts/harness/kpharness/creative_accept.py`
- `scripts/harness/kpharness/creative_export.py`
- `tools/kpharness_gamescope_backend_test.py`
- `docs/creative-runner.md`

No files were staged, reset, or committed.

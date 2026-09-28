# Task 7 capture cadence fix: round 8

Date: 2026-09-27

## Scope

This host-only round closes R7-1 and R7-2, adds the independent configured-tool
commitment requested by the parent review, and completes the bounded probe-child
recovery contract. No Wine, game, Gamescope, X11 server, FFmpeg, or FFprobe
process was launched. All process behavior used mocks or pure filesystem logic.

## Independent configured-tool commitment

- Acceptance now requires `--ffprobe-sha256` as an operator/reviewer input
  established outside mutable run evidence.
- The expected digest must equal both the producer-recorded tool digest and the
  retained native ELF descriptor digest before execution.
- The digest is signed into `visual_review` and its acceptance digest.
- Acceptance verification, accepted-receipt loading, export, and the export CLI
  all require the same explicit digest. Export sidecars record it.
- A coherent replacement of the configured tool, cadence tool identity, and PTS
  artifact remains internally self-consistent but fails the external digest.

## Authoritative append-only cleanup ledger

- Every unreaped/signaling failure is written with a random 32-hex identity to
  `ffprobe-cleanup-failure-ID.json` using exclusive creation and directory fsync.
  A later failure cannot overwrite an earlier child identity.
- Each failure records failed status, exact PID/start identity, command, verified
  tool identity, bounded waits, signal errors, and recovery requirements.
- Acceptance, `verify_acceptance`, accepted-receipt loading, and export fail while
  any failure lacks a valid resolution. Malformed, symlinked, misnamed, or orphaned
  cleanup records also fail closed.
- Resolution records are separately and exclusively appended as
  `ffprobe-cleanup-resolution-ID.json`; original failures are never removed or
  relabeled.

## Safe recovery entry point

- `creative_accept RUN_DIR --recover-cleanup FAILURE_ID` reads the selected
  failure with `O_NOFOLLOW`, a 64 KiB bound, exact schema, and filename/id binding.
- Recovery reads the live PID start identity before any signal. A different start
  value is treated as PID reuse and no signal is sent.
- A matching identity receives only SIGKILL and bounded two-second disappearance
  polling. A surviving matching identity remains unresolved.
- An already-exited PID resolves without signaling. A ProcessLookupError race
  also proceeds safely to bounded identity polling.
- Successful recovery appends a resolution with the exact original PID/start and
  outcome. Repeated recovery reads the existing resolution without mutation.

## Robust process identity and cleanup races

- `ProbeCleanupError` now reuses `session.pid_start()`, whose final-right-parenthesis
  parser handles Linux process names containing spaces and embedded right parentheses.
- Exact nonempty PID/start identity is required by the cleanup failure schema.
- Each cleanup attempt catches `ProcessLookupError` from kill and still calls
  `wait(timeout=2)`. Other signaling errors also proceed to bounded wait and then
  become `ProbeCleanupError`; no signaling path skips reap and no wait is unbounded.

## Regression coverage

- Coherent run-local FFprobe/tool/artifact substitution fails the external tool SHA.
- Wrong external tool SHA fails verification and export admission.
- A successful second PTS callback cannot bypass an unresolved first child.
- Unresolved cleanup blocks accepted verification and export.
- Two cleanup failures produce two immutable failure records.
- Malformed, symlinked, and orphaned records block readiness.
- Matching recovery signals once and appends resolution; PID reuse sends no signal;
  already-exited recovery appends a no-signal resolution.
- Kill ProcessLookupError still performs bounded wait; permission/signaling failure
  becomes typed cleanup failure after bounded wait.
- A mocked `/proc/<pid>/stat` comm containing spaces and an embedded right parenthesis
  yields the exact field-22 start identity.

## Validation

Final serial run:

- `python3 tools/kpharness_creative_test.py`: 30/30 passed.
- `python3 tools/kpharness_gamescope_boot_repair_test.py`: 41/41 passed.
- `python3 tools/kpharness_gamescope_backend_test.py`: 95/95 passed.
- Total focused tests: 166/166 passed.
- `python3 -m py_compile` passed for the six owned harness modules and both focused
  test modules.
- `git diff --check` passed.

Expected creative and boot-repair diagnostic lines are mocked failure-path output,
not live-process failures.

## Files changed in round 8

- `scripts/harness/kpharness/recording.py`
- `scripts/harness/kpharness/creative_accept.py`
- `scripts/harness/kpharness/creative_export.py`
- `tools/kpharness_gamescope_backend_test.py`
- `docs/creative-runner.md`

No files were staged, reset, or committed.

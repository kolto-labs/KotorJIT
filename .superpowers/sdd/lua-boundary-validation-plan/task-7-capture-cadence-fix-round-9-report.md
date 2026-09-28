# Task 7 capture cadence fix — round 9 implementation report

Date: 2026-09-27

## Scope

This round closes the three cleanup-lifecycle findings in the round-8 correctness and adversarial reviews. It remains host-only: no Wine, game, Gamescope, X11/Xvfb server, FFmpeg, or FFprobe process was launched.

## Implemented

- Replaced directory glob discovery of independently mutable cleanup files with one canonical `ffprobe-cleanup-ledger.json` per Gamescope run.
- The ledger has an exact top-level schema and exact failure/resolution record schemas. Every record includes schema, type, sequence, 32-hex ID, previous-record digest, UTC timestamp, payload, and recomputed record digest. The loader checks sequence, chain order, record digest, unique failure/resolution relationships, unique regular-file identity, exact field sets/types, and exact failure-to-resolution binding.
- Failure payloads bind PID/start, full command, producer tool identity, the two bounded waits, signal diagnostics, and fixed recovery requirements. Resolution payloads bind the exact failure record digest, PID/start, outcome, pidfd use, signal result, and bounded-wait result.
- Gamescope run creation exclusively creates the empty canonical ledger before execution. Missing, symlinked, hard-linked, malformed, truncated, reordered, forged, extra-field, orphan-resolution, and unresolved ledgers fail closed.
- Acceptance now requires an independently supplied `cleanup_ledger_sha256`, checks it against the exact current ledger bytes, signs it into `visual_review`, and includes it in the acceptance digest. Verification, accepted-receipt loading, every export recheck, the export CLI, and `export.json` require the same external head.
- Cleanup recovery requires the independently retained current ledger digest. Repeated recovery returns an existing resolution only after complete chain validation proves that it binds the selected failure's exact digest, PID, and start identity.
- Recovery process identity is tri-state. Only `FileNotFoundError` or `ProcessLookupError` proves absence. Permission, I/O, decoding, truncation, and stat parsing failures remain explicitly unreadable and unresolved.
- Automated signaling now requires Linux `pidfd_open` and `pidfd_send_signal`. Recovery validates start identity, opens a pidfd, revalidates start while holding the pidfd, signals only through the pidfd, and waits on pidfd readiness with a two-second bound. There is no numeric-PID signal fallback. Missing pidfd support refuses recovery.
- PID disappearance while opening a pidfd is accepted only after a second tri-state read confirms absence. PID reuse before or after pidfd acquisition refuses signaling. A signal/exit race is recorded as a resolved diagnostic only after pidfd readiness proves reap.
- FFprobe start identity is captured immediately after `Popen`, before any cleanup can signal or reap the process. Surviving-child publication requires a positive PID and nonempty captured start identity. A signaling error followed by a successful bounded reap appends a failure and an immediately bound resolution rather than creating an unrecoverable malformed record.
- Documentation now describes the cleanup-head input, pidfd-only recovery command, fail-closed states, and export commitment.

## Regression coverage

Added mocked host tests for:

- deletion, truncation, replacement, wrong external digest, and symlink substitution;
- reordered multi-record chains, altered payloads/record digests, and extra members;
- multiple append-only failures and exact failure/resolution chain preservation;
- permission-denied, malformed, absent, present, and reused process identities;
- pidfd unavailability, reuse detected while a pidfd is held, pidfd-only signal delivery, signal/exit races, bounded pidfd waits, and descriptor closure;
- repeated recovery returning only the exact validated resolution;
- signal failure followed by bounded reap producing a resolved ledger chain;
- acceptance, verification, accepted-receipt loading, export admission, and sidecar propagation of the independent cleanup-ledger digest.

## Validation

```text
PYTHONPATH=scripts/harness python3 tools/kpharness_creative_test.py
30 tests passed

PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_boot_repair_test.py
41 tests passed

PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_backend_test.py
102 tests passed

Focused total: 173 tests passed

python3 -m py_compile \
  scripts/harness/kpharness/recording.py \
  scripts/harness/kpharness/display_backends.py \
  scripts/harness/kpharness/creative_wine.py \
  scripts/harness/kpharness/creative.py \
  scripts/harness/kpharness/creative_accept.py \
  scripts/harness/kpharness/creative_export.py \
  tools/kpharness_creative_test.py \
  tools/kpharness_gamescope_backend_test.py
passed

git diff --check
passed
```

## Files changed in round 9

- `scripts/harness/kpharness/recording.py`
- `scripts/harness/kpharness/creative.py`
- `scripts/harness/kpharness/creative_accept.py`
- `scripts/harness/kpharness/creative_export.py`
- `tools/kpharness_gamescope_backend_test.py`
- `docs/creative-runner.md`
- `.superpowers/sdd/lua-boundary-validation-plan/task-7-capture-cadence-fix-round-9-report.md`

## Residual proof boundary

The tests prove deterministic schema, digest, acceptance/export, process-identity, and pidfd control behavior with mocked child and operating-system boundaries. They do not prove real FFprobe cleanup, live Gamescope capture, MIT-SHM use, GPU cadence, rendered-frame distinctness, visual framing, or K1 behavior. The requested live diagnostic remains outside this implementation round and was not started.

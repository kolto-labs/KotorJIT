# Task 7 Gamescope backend final scoped re-review

## Verdict

**FAIL — 1 Critical and 2 Important findings remain.**

The FFmpeg effective-input validation, route-wide capture checks, component cleanup receipt, and Gamescope group termination/retry fixes address the earlier C1 and I1–I3 findings. Creative execution also no longer accepts an up-front visual status. The replacement post-run acceptance boundary, however, does not validate or bind the execution receipt it approves, so it can still preauthorize a fabricated or incomplete run.

No game, Wine, Xvfb, Gamescope, or FFmpeg process was launched during this review.

## Critical finding

### C1. `creative_accept` trusts a caller-controlled readiness bit and has no execution-receipt digest binding

`scripts/harness/kpharness/creative_accept.py:12-31` checks the selected directory, schema/backend strings, `ok=false`, `visual_review.status=pending`, and `acceptance_ready=true`, then validates only the continuous-media path and digest. It does not recompute the schema-2 readiness predicates, require the run timestamps or execution evidence, invoke `schema2_receipt`, or verify a digest of a completed execution receipt. The acceptance write at lines 34-47 stores only the media digest.

The focused test at `tools/kpharness_gamescope_backend_test.py:249-261` actually codifies this defect: its synthetic receipt omits platform admission, display lease, PID/start ownership, window identity, capture command/result, route report and physical-console correlation, preservation, cleanup, and even `started_utc`/`finished_utc`; setting `acceptance_ready: true` is sufficient for acceptance.

An independent bounded proof reproduced the same result. A receipt containing only schema, backend, run directory, pending state, caller-set `acceptance_ready`, and a newly written `continuous.mp4` was accepted with `ok=true`. The accepted result had no start time, finish time, capture evidence, or receipt digest. Therefore a caller can create or alter a partial receipt and approve it before a real Gamescope run completes. It can also modify execution evidence after acceptance without any stored digest detecting that change.

Required fix: derive acceptance readiness again from the full immutable execution evidence, and bind the decision to a canonical digest of that completed pre-acceptance receipt as well as the media digest. Require completion identity such as `finished_utc` and all schema-2 evidence fields; do not trust the serialized `acceptance_ready` boolean alone. Store the execution-receipt digest in the acceptance record and test mutation of every readiness link, a partial receipt, and post-acceptance receipt tampering.

## Important findings

### I1. The acceptance test proves digest mismatch only, not completed-run provenance

The sole acceptance test constructs the skeletal receipt described above and expects it to pass. There is no test that feeds acceptance a real schema-2 pending receipt, verifies a canonical receipt digest, rejects missing completion/evidence fields, rejects a forged readiness bit, or detects execution-receipt mutation after approval. The test should be inverted for the skeletal case and expanded around the actual final `run_creative()` receipt.

### I2. Documentation claims a receipt-digest guarantee that does not exist

`docs/creative-runner.md:36-37` says the acceptance command rechecks readiness predicates and the receipt digest. The implementation checks neither. This overstates the provenance guarantee at the exact user-facing boundary that decides whether the run passed.

## Prior finding disposition

| Prior finding | Round-2 disposition |
| --- | --- |
| Critical: effective FFmpeg `-i` not validated | **Addressed** — required options occur exactly once and parsed `-i` must equal the owned display; mutation and duplicate-option tests pass. |
| Critical: visual acceptance preauthorized by run CLI | **Still open in replacement form** — the run CLI always emits pending, but the separate accept command approves an incomplete/caller-fabricated receipt and has no execution-receipt digest. |
| Important: capture checks incomplete | **Addressed** — checks wrap every step and helper polling/success paths. |
| Important: cleanup receipt detail absent | **Addressed** — order and three component results are retained and required. |
| Important: Gamescope lease cleanup not retryable/verified | **Addressed for the reviewed lease** — `_closed` is set only after verified disappearance, post-SIGKILL polling, leader reap, and resource cleanup. |
| Important: integrated lifecycle coverage incomplete | **Still open for acceptance provenance** — host coverage grew, but there is no full schema-2 `run_creative()` to acceptance test and the current acceptance fixture is deliberately incomplete. |

## Reviewer validation

* `python3 tools/kpharness_gamescope_backend_test.py`: **24/24 PASS**.
* `python3 tools/kpharness_creative_test.py`: **28/28 PASS** (the expected cleanup-failure diagnostic is emitted by one negative test).
* `python3 -m py_compile` over the changed Gamescope/creative modules: **PASS**.
* Adversarial partial-receipt proof: **accepted with `ok=true`**, despite no start/finish timestamp, capture evidence, or receipt digest.

These host-only checks validate their assertions and launch no game process. Their green result does not close the Critical acceptance-provenance defect because the focused test currently treats that defect as expected behavior.

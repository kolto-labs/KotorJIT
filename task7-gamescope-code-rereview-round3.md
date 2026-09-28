# Task 7 Gamescope acceptance boundary round-3 review

## Verdict

**FAIL — 1 Important finding remains. No Critical findings.**

The latest fixes close the prior Critical receipt-provenance defect. Acceptance now ignores the cached `acceptance_ready` value, authoritatively recomputes the complete schema-2 execution shape, rejects a skeletal receipt, validates the selected media bytes at acceptance time, and stores a canonical digest of the pre-acceptance execution receipt. Receipt-field tampering after acceptance invalidates `verify_acceptance()`.

No game, Wine, Xvfb, Gamescope, or FFmpeg process was launched.

## Important finding

### I1. `verify_acceptance()` does not detect post-acceptance media-file tampering

`scripts/harness/kpharness/creative_accept.py:24-28` verifies the canonical execution-receipt digest and compares the accepted media digest only with the digest still recorded in `receipt["media"]["continuous"]`. It never opens or hashes the media path. Consequently, replacing or modifying `continuous.mp4` after acceptance leaves `verify_acceptance(receipt)` returning `True` as long as the JSON is unchanged.

The focused test at `tools/kpharness_gamescope_backend_test.py:288-289` proves detection of a changed receipt field (`window.pid_start`) but does not modify the accepted media bytes and invoke the verifier. The later media mutation at lines 298-300 resets the receipt to pending and tests a second `accept()` call, so it does not cover post-acceptance verification.

Required fix: make the public acceptance verifier resolve the recorded media path under the recorded run directory, require it to remain a regular file within that directory, recompute its SHA-256, and compare it with both stored media-digest fields. Add a test that accepts a complete receipt, changes `continuous.mp4`, and observes verification failure. If a receipt-only verifier is intentionally retained, add a separate authoritative artifact verifier and make the documented verification path use it.

## Acceptance-boundary results

| Check | Result |
| --- | --- |
| Skeletal/caller-fabricated readiness receipt rejected | **PASS** |
| Cached `acceptance_ready` ignored and complete evidence recomputed | **PASS** |
| Complete schema-2 pending receipt accepted | **PASS** |
| Canonical pre-acceptance execution digest stored | **PASS** |
| Post-acceptance execution-receipt field mutation detected | **PASS** |
| Post-acceptance media-byte mutation detected | **FAIL** |
| Documentation matches execution-field digest behavior | **PASS** |

## Reviewer validation

* `python3 tools/kpharness_gamescope_backend_test.py`: **24/24 PASS**.
* `python3 -m py_compile scripts/harness/kpharness/creative_accept.py scripts/harness/kpharness/display_backends.py tools/kpharness_gamescope_backend_test.py`: **PASS**.
* Static adversarial check: `verify_acceptance()` has no filesystem read or media rehash and therefore cannot observe changed media bytes after acceptance.

The green focused suite establishes skeletal rejection, full-receipt acceptance, canonical execution-field binding, and receipt tamper detection. It does not cover or implement accepted-media integrity verification after the acceptance write.

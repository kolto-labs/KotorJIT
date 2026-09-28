# Task 7 accepted-media integrity final check

## Verdict

**PASS — no Critical or Important findings.**

The accepted-media verifier now resolves both the recorded run directory and media path, requires the media to remain a regular file inside the run directory, recomputes SHA-256 from the current bytes, and requires that digest to equal both the execution receipt's media digest and the review decision's media digest. Resolution before `is_relative_to()` also rejects a symlink that escapes the run directory.

The focused acceptance test now proves:

* the accepted recording initially verifies;
* replacing its bytes makes verification fail;
* restoring the original bytes restores verification;
* deleting the recording makes verification fail;
* execution-receipt tampering still makes verification fail.

Containment is enforced directly by `creative_accept.py:28-31`. Although the focused test does not have a separately named outside-path case, the fail-closed resolved-path check is unconditional and is shared by acceptance and subsequent verification; no material review finding remains in this narrow scope.

Validation:

* `python3 tools/kpharness_gamescope_backend_test.py`: **24/24 PASS**.
* Python compilation of the acceptance module and focused test: **PASS**.

No game, Wine, Xvfb, Gamescope, or FFmpeg process was launched.

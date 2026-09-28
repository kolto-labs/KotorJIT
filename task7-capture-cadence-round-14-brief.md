# Task 7 capture cadence — round 14 brief

Written by the orchestrator. In round 13, the correctness review passed and the adversarial review failed with one Critical finding. The single diagnostic stays blocked until both reviews pass round 14.

## Scope limits

- There is one writer.
- Work on the host only. Synthetic lavfi encodes with `/usr/bin/ffmpeg` and dummy process trees are allowed.
- Do not start Wine, Gamescope, Xwayland, mpv or x11grab.
- Never open the live-game lock.
- Make no git writes.
- Do not put TMPDIR on btrfs for the suites. Host `/tmp` is tmpfs and usable.

## Files

**You may edit:**
- `scripts/harness/kpharness/{display_backends,capture_diagnostic,recording,gamescope_socket}.py`
- `tools/kpharness_{gamescope_backend,capture_diagnostic,gamescope_boot_repair}_test.py`
- `docs/creative-runner.md`

**Inputs to read:**
- The Round 13 section of `/home/brunner56/kp-live-20260922/task7-capture-cadence-adversarial-review.md`, and the probes in `review-probes-r13-adversarial/` (`probe_7loop.py`, `probe_14loop.py`).
- The Round 13 section of `task7-capture-cadence-fix-review.md`: R13C-m1, and `review-probes-r13-correctness/btrfs_dev_probe.py`.
- The round 13 report: `.superpowers/sdd/lua-boundary-validation-plan/ta[REDACTED].md`.

## Required, red-first

### 1. R13-Critical: periodic loops pass

The pattern is period 7, so a frozen 7-frame or 14-frame source loop decodes as a valid +3 mod 7 sequence.

**The fix.** The pattern must carry a per-frame index that does not repeat within the clip. The checker decodes the index and requires it to strictly increase across fresh frames inside the acceptance interval. Duplicates must repeat the same index. The step between consecutive fresh frames must match the expected cadence, within a stated tolerance for real drops, and the drop tolerance must feed the existing drop/gap criteria rather than bypass them.

**Suggested design** (choose by criterion: robust to the recorder's lossy codec at 1024x768, cheap to decode with the existing ffprobe/lavfi transport, no new tools):
- a binary barcode of the frame number, drawn as large solid blocks with `drawbox` and per-bit `enable` expressions or `geq`;
- at least 12 bits, plus a parity or check bit;
- decoded by cropping each block region and reading its luma average with signalstats.

**Partial freezes.** Place independent index copies in at least two separated screen regions, for example the top and bottom bands. They must agree frame by frame. This also closes the documented half-frame and quarter-frame freeze residual (`half_frozen_bottom`, `quarter_fresh_top`), or else state precisely what remains.

**Must fail**, typed `capture_content_sequence` or a new typed `capture_content_index`:
- 7-frame and 14-frame loops;
- a 7k loop at any k that fits the clip;
- reorder;
- a stale frame that has the right brightness level;
- a half-frame freeze.

**Must still pass:**
- every clean family from round 13;
- drift, duplicate and skip families that are within policy.

**Also:**
- Measure the decode margin: the minimum separation between bit-on and bit-off luma against the observed noise, across all round 13 families.
- Record the decoded index series summary and the violations in `diagnostic-result.json`.
- Keep the +3 mod 7 level check. It stays as a second, independent signal.

### 2. R13C-m1: btrfs lock-fd mismatch (Minor, fix now)

In `gamescope_socket.py` (around :106 and :120), the `/proc/self/fdinfo` FLOCK line encodes a different device than `fstat` on btrfs (`00:23` vs `00:2d`).

Match on inode from the fdinfo lock line, with fd identity via fstat. Then confirm exclusivity without relying on the device field: for example, open the path again and require `flock(LOCK_EX|LOCK_NB)` to fail with EWOULDBLOCK. The probe fd must never keep a lock.

Tests:
- ext4 and tmpfs behaviour must be unchanged;
- btrfs behaviour must be fixed; run the suites once with TMPDIR on btrfs to prove it;
- a fake unlocked fd with the same inode must still be refused.

## Validation to paste

- The four suites in the container and on the host (via `/home/brunner56/.local/bin/host-cmd`):
  - `creative`
  - `gamescope_boot_repair`
  - `gamescope_backend`
  - `capture_diagnostic`
- The same four suites once more with TMPDIR on btrfs (`/home/brunner56/kp-live-20260922/tmp-r14-btrfs`).
- Reruns of these probes against production code:
  - `probe_7loop.py`
  - `probe_14loop.py`
  - `evaluate_r13.py`
  - `btrfs_dev_probe.py`
- The report goes to `.superpowers/sdd/lua-boundary-validation-plan/ta[REDACTED].md` and ends with a Grill me section.

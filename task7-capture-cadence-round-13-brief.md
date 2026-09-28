# Task 7 capture cadence — round 13 brief

Orchestrator-authored. Round 12 passed both independent reviews. This round only closes the reviewers' Minor findings that bear on the single authorized diagnostic, plus two publication leaks.

## Scope limits

- There is one writer.
- Work on the host only. Synthetic lavfi encodes run with `/usr/bin/ffmpeg`, and dummy process trees are allowed.
- Do not start Wine, Gamescope, Xwayland, mpv or x11grab.
- Never open the live-game lock.
- Make no git writes.

## Files

**You may edit:**
- `scripts/harness/kpharness/{display_backends,capture_diagnostic,recording}.py`
- `tools/kpharness_{gamescope_backend,capture_diagnostic}_test.py`
- `docs/creative-runner.md`

**Inputs to read:**
- The Round 12 sections of `/home/brunner56/kp-live-20260922/task7-capture-cadence-fix-review.md`: R12C-m1 to m5.
- The Round 12 sections of `task7-capture-cadence-adversarial-review.md`: R12-1 to R12-4.
- The probes in `review-probes-r12-correctness/` and `review-probes-r12-adversarial/`.

## Required, red-first

1. **Brightness level sequence (R12-2, R12C-m2, R12C-m3).**
   - Derive each frame's brightness level from `yavg`.
   - Across the acceptance interval, each fresh frame must step exactly +3 levels (mod 7) from the previous fresh frame. Duplicates repeat the level.
   - These must fail as typed `capture_content_sequence`:
     - two-frame and three-frame loops;
     - a missing step, when mpv renders without the `eq` filter;
     - a partially frozen frame, if detectable through the level sequence.
   - A capture that is actually fine must still pass.
   - Record the decoded level histogram and the sequence violations in `diagnostic-result.json`.
2. **Guard band.** Set it to `(floor/2, floor*2)`, which is (1.95, 7.8) at a floor of 3.9. Update `CALIBRATED_DUPLICATE_MAX` to 1.2414 (review-measured) and recompute the margins in the docs.
3. **Label precedence (R12-3, R12C-m5a).**
   - `calibration_ambiguous` is the verdict only when every non-content criterion passes.
   - Otherwise the verdict is FAIL, listing each failing criterion.
   - These failing criteria include: survivors, protected displays, cleanup, cadence, lock, and SHM fallback.
4. **Dynamic loader (R12-1, R12C-m4).** Detect launches through `ld-linux*.so*` and `ld.so`, in comm, exe basename or `argv[0]`, when the loaded program argument names or hashes to ffmpeg or ffprobe. Otherwise, document it as a known gap.
5. **Thread count (R12-4, R12C-m5b).** Count threads with `/proc/self/task` instead of `threading.active_count()`.
6. **Publication leaks.**
   - Remove the literal `/home/<user>/kp-live-20260922/...` path from `docs/creative-runner.md` (around line 479).
   - Replace the Homebrew-specific ffprobe default in `capture_diagnostic.py` (around line 73) with a required explicit `--ffprobe`. The value must be a real ELF, not a wrapper, recorded by path and SHA.

## Validation to paste

- Suites in both the container and on the host, via `/home/brunner56/.local/bin/host-cmd`:
  - `creative`
  - `gamescope_boot_repair`
  - `gamescope_backend`
  - `capture_diagnostic`
- Rerun the reviewers':
  - `ldso_probe.py`
  - `nostep_probe.py`
  - the `_thread` probe
  - the stale-loop encodes
- Report: `.superpowers/sdd/lua-boundary-validation-plan/ta[REDACTED].md`, ending with a Grill me section.

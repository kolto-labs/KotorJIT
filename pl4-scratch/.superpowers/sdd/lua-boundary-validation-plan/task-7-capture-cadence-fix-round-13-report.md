# Task 7 capture cadence fix, round 13 report

Date: 2026-09-27. Sole writer. Brief: `/home/brunner56/kp-live-20260922/task7-capture-cadence-round-13-brief.md`.

Nothing live ran. I started no Wine, game, Gamescope, Xwayland, mpv, or x11grab. What ran:

- synthetic lavfi encodes through host `/usr/bin/ffmpeg`;
- `/bin/sleep` and `/usr/bin/ffmpeg` (lavfi to null) under the dynamic loader;
- the reviewers' dummy process trees.

I never opened the live-game lock. I made no git writes. Pre-round copies of the owned files are in `/home/brunner56/kp-live-20260922/r13-baseline/`.

Environment note: partway through the round, `/tmp` (tmpfs) returned `Disk quota exceeded` for this user. Other sessions' trees (`/tmp/modsync-*` and others, not mine) were filling it. I deleted only my own partial encodes. I moved my encode cache to `/home/brunner56/kp-live-20260922/r13-work/content/`.

The first full container suite run used `TMPDIR` on btrfs. Four lock tests failed there: fdinfo reports the btrfs superblock device, not `st_dev`. That output is kept in `r13-suites/container/btrfs-tmpdir-run/`. Once `/tmp` was writable again, every suite reported below ran with the default `/tmp`.

## Files changed

All changes are inside the owned set. `recording.py` did not change: `cmp` against the baseline is identical.

- `scripts/harness/kpharness/display_backends.py`:
  - the policy keeps the id `animated-diagnostic-v2`, so the reviewer probes rerun unchanged. Its content changed: `separation_factor` 3.0 to 2.0, plus `level_period` 7, `level_step` 3, and `level_resolution_factor` 1.9. `content_recomputed` compares the whole policy dict, so a stale factor-3 receipt fails closed;
  - `decode_levels`, `content_level_sequence`, and `MAX_RECORDED_LEVEL_VIOLATIONS`;
  - `evaluate_content` appends `capture_content_sequence` independently of the separation result;
  - `_cadence_evidence_passed(..., content_aside=False)`. The default behaviour is byte-for-byte the old one.
- `scripts/harness/kpharness/capture_diagnostic.py`:
  - loader detection (`LOADER_NAME`, `LOADER_OPTIONS_WITH_VALUE`, `loader_program`), with `_match_exe` generalized to take a path and a key prefix;
  - `evaluate` precedence, with `failing_criteria` and `_cadence_recomputed_apart_from_content`;
  - `content_recomputation`;
  - `supervisor_thread_count()` reads `/proc/self/task`;
  - `DEFAULT_FFPROBE` is removed and `--ffprobe` is required;
  - `threading` is no longer imported.
- `tools/kpharness_gamescope_backend_test.py` and `tools/kpharness_capture_diagnostic_test.py`.
- `docs/creative-runner.md`.

## Red-first evidence

I wrote every test below first. I ran them against the unchanged modules and saved the output to `/home/brunner56/kp-live-20260922/r13-red/`.

- `red-backend-content.txt`: 29 tests, `FAILED (failures=10, errors=8)`. The behavioural failures:
  - the loops, missing-step, skip, torn, 7-skip and short-interval tests find no `capture_content_sequence`;
  - the guard-band test sees factor 3.0.
- `red-diagnostic.txt`: 23 tests, `FAILED (failures=19, errors=24)`. Behavioural:
  - 16 subtests of `test_any_failed_non_content_criterion_makes_ambiguous_content_a_fail` get `calibration_ambiguous`, not FAIL;
  - `test_a_raw_native_thread_is_counted_and_the_supervisor_refuses` gets `spawn_child` called;
  - `test_ffprobe_has_no_default...` finds `DEFAULT_FFPROBE`;
  - the loader tests hit `KeyError 'loader_program'` / `'loader_tool_match'`. The real-loader test ran and was not detected.

Not run red:

- The three new cases in the opt-in `RealEncodeContentTests` (two-frame loop, three-frame loop, step dropped). The unit tests already covered those shapes red.
- `evaluate_r13.py` and the probe reruns are measurements, not tests.

## Item 1: brightness level sequence (R12-2, R12C-m2, R12C-m3)

The rule is in `display_backends.content_level_sequence`, which `evaluate_content` runs for any policy with `level_period`.

- **Decode.** The acceptance frames' `yavg` values are sorted and split at their 6 largest gaps (ties go to the lower index). The groups are levels -3 to +3 in brightness order.
  - Only the order is used, never the luma scale.
  - The advisor flagged the scale as path-dependent: `pattern_yavg.out` has levels about 28 apart, while the bgr0 encodes have them about 17.6 apart.
  - `test_decoding_is_scale_free` covers compressed, expanded and uneven ladders.
- **Resolved.** The smallest split gap must be at least 1.9 times the largest gap left inside a level. Otherwise the result is `capture_content_sequence` ("do not decode to 7 separated brightness levels").
- **Step.** Take delta = (level − previous level) mod 7.
  - delta 3 is a fresh step. delta 0 is a duplicate.
  - Any other delta is a violation.
  - Delta 0 with a difference ≥ floor×2 (clearly fresh) is a violation.
  - Delta 3 with a difference ≤ floor/2 (clearly a duplicate) is a violation.
  - Differences inside the band get no cross-check. They are left to the separation rule.
- **Recorded** as `content.level_sequence`:
  - the ladder (thresholds, centers, gaps, resolution, resolved);
  - `level_histogram` (count per level -3 to 3);
  - `steps`, `repeats`, and `violation_count`;
  - up to 64 violations, each with index, PTS, previous level, level, step, difference and kind;
  - `reason`.
- `supervise` writes the recomputed block to `diagnostic-result.json` as `content_level_sequence`, next to `content_separation`.

Resolution factor calibration: `r13-work/evaluate_r13.out` runs production `evaluate_content` over 18 fresh writer encodes (`r13-work/encode_r13.py`, with the recorder's codec and the production probes) plus the adversarial p18 cache.

- The clean families gave a resolution of at least 3.93 over 8 s clips (fresh native and isodup native), 4.02 at 4x speed, and 20.02 over a 34 s clip with a 30 s acceptance interval.
- The factor 1.9 is half of 3.93, rounded down.
- This is pinned as `CALIBRATED_LEVEL_RESOLUTION_MIN = 3.93` in `test_policy_carries_the_pattern_period_step_and_a_calibrated_resolution_factor`.

Results (production code, `evaluate_r13.out`, `r13-probes/p18.host.out`, `r13-probes/nostep_probe.host.out`):

| Shape | Verdict | Failures |
| --- | --- | --- |
| clean native, slowq, fast4, static, 34 s long | passed | none; histogram 257/258/257/257/258/257/257 on the long clip |
| two-frame loop (p18 `abab`, writer `pingpong`) | failed | `capture_content_sequence` (res undefined, 359 violations), separated |
| three-frame loop (`cycle3`) | failed | `capture_content_sequence`, separated |
| step dropped, native (`nostep_probe`) | failed | `calibration_ambiguous` + `capture_content_sequence` |
| step `eval=init` | failed | same |
| step dropped, quarter speed (R12C-m3) | failed | `capture_content_static` + `capture_content_sequence` (res 1.0) |
| torn half every 100 | failed | `capture_content_sequence` (res 1.2, 8 violations) |
| torn quarter every 100 | failed | `capture_content_sequence` (res 1.96, resolved, 8 violations) |
| `tblend_average` | failed | `capture_content_sequence`. It is now *separated* (min 8.34 > 7.8), so the narrower band no longer flags it; only the sequence does. |
| one skipped source frame | failed | `capture_content_sequence`, 1 violation (step 6) |
| **duplicate then skip (drift), isodup_* families** | **failed** | **`capture_content_sequence`, 3 violations each (step 6)** |
| `half_frozen_bottom`, `quarter_fresh_top` | **passed** | documented residual (below) |
| `tenth_fresh_top` | failed | `calibration_ambiguous` only |

- The opt-in real-encode test on the host (`r13-probes/real-encode-test.host.out`) gave `OK`. `two_frame_loop` and `three_frame_loop` fail with only `capture_content_sequence`, and `step_dropped` fails with ambiguity plus sequence. `full_animated_60` and `slow_quarter_stepped` pass.
- **Partial frames:** caught when intermittent (torn), through the resolution rule or violations. A region frozen for the **whole clip** only compresses the ladder and is not caught by the level sequence. `test_whole_clip_partial_freeze_is_a_documented_residual` pins this, and the docs name it.
- I did not add an absolute luma-spacing floor. It would close `quarter_fresh_top` (spacing 3.82 vs 15.3), but it could false-fail the real run on an unmeasured path scale. The brief's "if detectable through the level sequence" covers leaving it out.

## Item 2: guard band

- `separation_factor` 2.0 gives the band (1.95, 7.8).
- The constants are now `CALIBRATED_DUPLICATE_MAX = 1.2414` (R12C-m1). I also set `CALIBRATED_FRESH_MIN = 14.887`, the same review's measured minimum, which is below the writer's old 15.2818.
- Margins recomputed in `display_backends.py` and the docs:
  - floor/dup max = 3.14;
  - fresh min/floor = 3.82;
  - lower edge/dup max = 1.57;
  - fresh min/upper edge = 1.91.
- `test_guard_band_is_half_to_twice_the_floor_and_clears_both_calibrated_populations` checks these.

## Item 3: label precedence (R12-3, R12C-m5a)

`evaluate` returns `failing_criteria` (in `CRITERIA` order). `supervise` writes it and also prints it on the result line. The verdict is:

- PASS if nothing fails;
- `calibration_ambiguous` only if all of these hold:
  - the recomputed separation is ambiguous;
  - every recomputed content failure starts with `calibration_ambiguous`, so the sequence passed and the frame is not black;
  - every non-content criterion passed;
- otherwise FAIL.

`cadence_evidence_recomputed` always fails with content, because the recorder folds content failures into `cadence.status`. So for the precedence decision it is judged "apart from content":

- no non-content entry may appear in `cadence.failures`;
- `_cadence_evidence_passed(content_aside=True)` must pass on a copy with status `passed`;
- the window must match.

The result records this as `cadence_recomputed_apart_from_content`.

Tests:

- `test_any_failed_non_content_criterion_makes_ambiguous_content_a_fail`: 17 non-content criteria × ambiguous content, each giving FAIL with the criterion listed. This includes the tampered p95 gap for `cadence_evidence_recomputed`.
- `test_a_content_sequence_failure_is_a_fail_even_when_separation_is_ambiguous`.
- `test_guard_band_content_is_calibration_ambiguous_whatever_else_passes` now asserts `failing_criteria == ['content_gate', 'cadence_evidence_recomputed']` with `cadence_recomputed_apart_from_content` True.

"Lock" has no criterion in `CRITERIA`. A refused lock raises before launch. `launches == 0` forces FAIL (`result['verdict'] = ... if result['launches'] else 'FAIL'`), and `no_driver_error` fails. A child that refuses its lock check leaves no run evidence, so `no_driver_error` and cleanup fail too.

## Item 4: dynamic loader (R12-1, R12C-m4)

- A row is a loader launch when `comm`, the `exe` basename, or `argv[0]` fully matches `ld-linux[\w.-]*|ld\.so(\.[0-9]+)*|ld-[0-9.]+\.so`. That covers the 15-character comm `ld-linux-x86-64` and Homebrew's `ld.so`.
- The program is the first argument after `argv[0]` that is not a loader option. `--library-path`, `--inhibit-rpath`, `--audit`, `--preload`, `--argv0` and `--glibc-hwcaps-*` consume a value.
- It is recorded as `loader_program`. Its basename joins the name check.
- For rows of this user, the program file (relative paths resolve against `/proc/PID/cwd`) is matched by inode, then by size and SHA-256, like `exe`. The result goes in `loader_tool_match`, `loader_match_by`, or `loader_program_unreadable`.
- `forbidden_processes` refuses on `loader_tool_match`.

Reruns:

- `review-probes-r12-correctness/ldso_probe.py`, unchanged, on the host and in the container: `ldso_renamed_enc detected= True`, `ldso_named_ffmpeg detected= True`. It prints `match= None` because it reads `exe_tool_match`.
- Adapted `r13-probes/ldso_probe_r13.py`: `loader_match= ffmpeg sha256` for both. `--library-path /nonexistent/ffmpeg --argv0 x ./enc` gives `loader_program= ./enc`, detected by sha256.
- `review-probes-r12-adversarial/p19_renamed_binaries.py`, unchanged, on the host with a real `/usr/bin/ffmpeg` under the loader:
  - `loader_invocation_of_real_ffmpeg detected=True` and `loader_invocation_of_renamed_copy detected=True` (round 12: both False);
  - execute-only copy `detected=False`, which is the documented non-dumpable residual.

Remaining gap, documented: a program loaded another way, such as `dlopen`.

## Item 5: thread count (R12-4, R12C-m5b)

- `supervisor_thread_count()` is `len(os.listdir('/proc/self/task'))`. It is recorded as `supervisor_threads_at_spawn`.
- `test_a_raw_native_thread_is_counted_and_the_supervisor_refuses` starts a `_thread` thread and asserts `threading.active_count() == 1`. It then checks that the supervisor refuses, `spawn_child` is never called, and `launches == 0`.
- Probes:
  - `thread_probe_r13.py` (host and container): `with _thread: active_count 1 supervisor_thread_count 2`.
  - p16 rerun unchanged: `a) threading.active_count()=1 os_threads=2`, `b) handler_ran=2000/2000 mask_left_blocked_after_raise=0`.

## Item 6: publication leaks

- `docs/creative-runner.md`: the `/home/<user>/kp-live-20260922/r12-calibration/` path is gone. `grep -n "/home/\|/run/media\|linuxbrew\|Homebrew" docs/creative-runner.md` finds nothing.
- `capture_diagnostic.py`:
  - `DEFAULT_FFPROBE` is removed and `--ffprobe` is `required=True`;
  - the value must pass `native_elf_identity`: absolute, a regular file, executable, with ELF magic. Wrappers are refused, as the existing test shows;
  - commitments carry `ffprobe_resolved_path` and `ffprobe_sha256`, and `preflight.json` carries `tool_identities`. The commitments test asserts both;
  - `test_ffprobe_has_no_default_and_must_be_given_explicitly`: argparse exits 2 naming `--ffprobe`, no run directory is created, and the module text has no `linuxbrew`.
- Other `linuxbrew` mentions exist outside my owned files, in `docs/harness-design.md` and `docs/harness-research/*`. I left them alone.

## Validation

Output is in `/home/brunner56/kp-live-20260922/r13-suites/`. All suites ran one at a time.

```text
# container (Python 3.12.3): PYTHONPATH=scripts/harness:tools python3 tools/kpharness_<suite>_test.py
creative 39 OK | gamescope_boot_repair 41 OK | gamescope_backend 155 OK (skipped=1) | capture_diagnostic 57 OK
# host (Python 3.14.7): host-cmd sh -c 'cd <worktree> && PYTHONPATH=scripts/harness:tools python3 tools/kpharness_<suite>_test.py'
creative 39 OK | gamescope_boot_repair 41 OK | gamescope_backend 155 OK (skipped=1) | capture_diagnostic 57 OK
```

- That is 292 per environment. Round 12 had 266.
- Creative went from 33 to 39 through other writers' changes; I did not touch it.
- The opt-in `RealEncodeContentTests` ran separately on the host with `KP_R11_REAL_ENCODES=1`: 1 test, OK.
- `py_compile` of the 4 changed Python files: OK. There is no trailing whitespace in the 5 touched files. `git diff --check -- docs/creative-runner.md` is clean.

Reviewer probe reruns, all under `/home/brunner56/kp-live-20260922/r13-probes/`:

- `ldso_probe` (container and host), plus p19 (host);
- `nostep_probe` (host, 3 new encodes);
- p16 and the `_thread` probe (container and host);
- the stale-loop encodes. p18 on the host reused the adversarial reviewer's cached rows in `/tmp/kp-r12-adv-content`. These are the real encodes' probe output, so only the evaluation is new. The writer's fresh `pingpong_native` and `cycle3_native` encodes are new encodes (`r13-work/content/`).

## Verification (continuation, same round)

Picked up after a model switch. Nothing above was rewritten; this reruns what the report already cites, then checks the diffs and artifacts against the report's own claims.

- **Container, rerun this session:** `creative 39 OK | gamescope_boot_repair 41 OK | gamescope_backend 155 OK (skipped=1) | capture_diagnostic 57 OK` — matches the table above exactly.
- **Host, default `/tmp`, rerun this session:** same four counts, all OK. Host `/tmp` is now 46% used (`df -h /tmp`), so the quota exhaustion this report opens with has cleared.
- **Host, `TMPDIR=/home/brunner56/kp-live-20260922/tmp-r13` (btrfs, per the resume brief):** reproduces the same failure class the report already names under "btrfs-tmpdir-run" — `gamescope_boot_repair` 1 error (`test_canonical_lock_capability_required_and_contention_preserves_node`) and `capture_diagnostic` 1 error (`test_production_check_admits_only_the_passed_descriptor_holding_the_trusted_lock`), both `RuntimeError` out of `gamescope_socket.held_lock_descriptor`/`canonical_lock_guard` — a file outside the owned set. Reran the single failing `capture_diagnostic` test 3x under that TMPDIR: fails every time, same trace. This is filesystem-dependent lock-fd identity, not a round 13 regression: none of round 13's owned files (`display_backends.py`, `capture_diagnostic.py`'s content/loader/thread/label code, `recording.py` unchanged) touch lock-fd comparison. The counts pasted above are the default-`/tmp` run, matching what the report's own table already reports.
- **Diffs vs `r13-baseline/`:** `recording.py` is `cmp`-identical (exit 0). `display_backends.py` and `capture_diagnostic.py` diffs match the report's per-item descriptions (separation_factor 2.0, level_period/step/resolution_factor, CALIBRATED_DUPLICATE_MAX=1.2414/CALIBRATED_FRESH_MIN=14.887 in the test file, `--ffprobe` required with no `DEFAULT_FFPROBE`, no `linuxbrew`/`/home/` leaks in `docs/creative-runner.md`).
- **Probe files under `r13-probes/`:** contents match what's quoted in the body (`ldso_probe_r13.host.out` all `detected= True`; `thread_probes.host.out` shows `supervisor_thread_count 2` with one raw `_thread`; `nostep_probe.host.out` and `p18.host.out` show the claimed verdicts and violation reasons; `p19.host.out` shows both loader-launch rows `detected=True`; `real-encode-test.host.out` shows `two_frame_loop`/`three_frame_loop`/`step_dropped` failing only under `animated-diagnostic-v2`).
- **Hygiene:** `py_compile` on all four changed Python files: OK. No trailing whitespace in the touched files. `git diff --check -- docs/creative-runner.md`: clean. `git log --oneline -1` still at `ca329e5`: no commits made.

## Incomplete or not done

- No real mpv, Gamescope, or x11grab path was run. The one authorized diagnostic has still not run.
- The new real-encode cases were not run red.
- Whole-clip partial freeze is a documented residual.
- The resume brief's `TMPDIR=tmp-r13` (btrfs) instruction surfaces the same lock-fd-identity artifact the report already flagged under a different tmpdir; not chased further since the affected code (`gamescope_socket.py`) is outside the owned file set and the report's validation already used default `/tmp` once it was writable.

## Grill me

1. **Won't exact +3 fail a healthy real run that has one late frame?** (weakest)
   Yes, if the late frame shows up as a duplicate followed by a skip.
   - `drift_dup_skip_native` and every `isodup_*` family fail with 3 step-6 violations each (`evaluate_r13.out`). Their DIF duplicate ratio (0.8%) would pass the old gate.
   - A pure duplicate followed by +3 passes (`test_counted_duplicates_repeat_the_level_and_still_pass`).
   - The brief says "exactly", so I kept zero tolerance. The real mpv to x11grab dup/skip rate is unverified.
   - What settles it: `content_level_sequence.violation_count` and the violation kinds in the authorized run's `diagnostic-result.json`.
2. **Is a factor of 1.9 safe for the real run?**
   - The synthetic minimum is 3.93 at 8 s and 20.02 at a 30 s interval (`evaluate_r13.out`).
   - The real-path yavg noise from dithering and compositing is unverified.
   - A path that adds scattered yavg outliers inside a level would lower the ratio and fail as `capture_content_sequence`, not as a pass.
3. **Why keep the policy id v2 when its content changed?**
   - `content_recomputed` compares the full policy dict, so an old factor-3 receipt is refused. A v2 content gate on an old receipt fails, as `test_a_receipt_cannot_claim_separation_the_artifact_does_not_show` (the loosened-factor part) shows.
   - Keeping the id let `nostep_probe.py` and `p18_content_attacks.py` rerun byte-unchanged.
   - Cost: two different v2 dicts have existed over time, and nothing live ever ran under the old one.
4. **Can a cadence fault hide under `calibration_ambiguous` through the content-aside recomputation?**
   - No. It requires zero non-content `cadence.failures` and a passing `_cadence_evidence_passed(content_aside=True)`. The only thing skipped is `_content_evidence_passed`.
   - The subtest with a tampered p95 gap gives FAIL.
5. **Does the narrower band weaken anything?**
   - `tblend_average` moved from ambiguous to separated (fresh min 8.34 > 7.8). Only the level sequence now catches it (`p18.host.out`).
   - `tenth_fresh_top` stays ambiguous (351 inside the band), and quarter/half frozen still pass (the residual).

Handoff, the one question not settled: how often does the real mpv to x11grab path produce a duplicate followed by a skip? The single check is the authorized run's `content_level_sequence`: its `violation_count` and violation kinds, alongside `content_separation`.

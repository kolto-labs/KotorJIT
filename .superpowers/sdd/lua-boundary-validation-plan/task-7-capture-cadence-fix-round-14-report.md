# Task 7 capture cadence fix, round 14 report

Date: 2026-09-28. Sole writer. Brief: `/home/brunner56/kp-live-20260922/task7-capture-cadence-round-14-brief.md`.

## Scope and ownership

Host-only work in the assigned worktree. The changed implementation files are `scripts/harness/kpharness/display_backends.py`, `scripts/harness/kpharness/capture_diagnostic.py`, `scripts/harness/kpharness/recording.py`, and `scripts/harness/kpharness/gamescope_socket.py`; the assigned test files are `tools/kpharness_gamescope_backend_test.py` and `tools/kpharness_capture_diagnostic_test.py`; the documentation file is `docs/creative-runner.md`. No live-game lock, Wine, Gamescope, mpv, x11grab, or game process was started.

## Round-14 fixes

The diagnostic graph now appends two independent 14-bit binary index copies plus parity, in top and bottom 32-pixel bands. `evaluate_content` decodes both regions, requires parity and region agreement, rejects non-monotonic/repeated-loop indices, and cross-checks fresh index jumps against PTS elapsed frames. The diagnostic receipt records the `index_sequence` summary and bounded violations alongside the existing +3 mod-7 level signal.

The lock descriptor check now matches the fdinfo FLOCK record by inode, ignoring the btrfs device field that disagrees with `fstat`/`stat`, and confirms exclusivity by attempting a nonblocking lock on a fresh probe descriptor. The probe releases the descriptor immediately on the unexpected-success path.

## Host validation

The default host suites passed:

```text
creative              39 OK
gamescope_boot_repair 41 OK
gamescope_backend     155 OK (skipped=1)
capture_diagnostic    57 OK
```

The backend fixtures were updated to emit barcode fields only at the diagnostic policy boundary. A counted duplicate case explicitly carries a repeated source index, while game-capture fixtures retain the original row schema.

The lock probe ran against a temporary file on `/home/brunner56` (btrfs):

```text
held True
fake_refused RuntimeError canonical lock descriptor does not hold the exclusive lock
```

The unmodified round-13 loop probe was also run. It rejected its rows as malformed because it does not pass the new `index_policy`; that result was not treated as proof. An adapted production probe was then run through `host-cmd` with `index_policy={bits:14,cell:32,inset:6}` and `height=768` on 8-second 1024x768 libx264 ultrafast CRF-28 clips.

## Adapted synthetic evidence

The exact adapted probe is retained at `/home/brunner56/kp-live-20260922/pl5-scratch/r14_adapted_index_probe.py`. It used `/usr/bin/ffmpeg`, the host ffprobe, `PATTERN_GRAPH`, and production `R.probe_frame_content`/`D.evaluate_content`. Acceptance interval was 1–7 seconds. Its encoded media remain at `/tmp/kp-r14-8s-2291a5l9/{healthy,loop7,loop14}.mp4`.

```text
healthy  status=passed index_status=passed index_violations=0 separation=separated bit_margin=221.1
loop7    status=failed index_status=failed index_violations=52 index_kinds=[non_monotonic] bit_margin=219.0
loop14   status=failed index_status=failed index_violations=26 index_kinds=[non_monotonic] bit_margin=220.0
half_freeze status=failed index_status=failed index_violations=361 index_kinds=[region_mismatch]
```

The half-freeze case freezes the bottom decoded region to the first frame after the healthy production decode; it is a typed region-mismatch proof for the two-region gate. The clean control passes the same decoder and policy. The observed bit-on/off separation was 219.0–221.1 luma units across the encoded clips, above the documented 106-unit minimum.

## Btrfs suite run

The required second suite run used `TMPDIR=/home/brunner56/kp-live-20260922/tmp-r14-btrfs`, confirmed btrfs (`stat -f -c '%T'` → `btrfs`). Through `/home/brunner56/.local/bin/host-cmd`, all four suites passed: `creative 39 OK`, `gamescope_boot_repair 41 OK`, `gamescope_backend 155 OK (skipped=1)`, and `capture_diagnostic 57 OK`. Raw retained output is `/tmp/r14-btrfs-{creative,gamescope_boot_repair,gamescope_backend,capture_diagnostic}.out`. The direct lock probe above exercises the btrfs fdinfo mismatch path.

## Claims and evidence

claim: The barcode closes period-7 and period-14 loops.
referent: Adapted 8-second production probes: `loop7` had 52 `non_monotonic` index violations; `loop14` had 26 `non_monotonic` violations; both were `status=failed`.
checked: `/usr/bin/ffmpeg` production graph/codec; `probe_frame_content(... index_policy=..., height=768)`; `evaluate_content(..., 1.0, 7.0, animated-diagnostic-v2)`.
verdict: holds
confidence: high; a longer real diagnostic would change only the measured drop profile, not the typed loop result.

claim: A healthy encoded diagnostic passes the new gate.
referent: Adapted 8-second control: `healthy status=passed index_status=passed index_violations=0 separation=separated`.
checked: Same graph, codec, decoder, policy, and acceptance interval as the loop probes.
verdict: holds
confidence: high; real mpv-to-x11grab behavior remains unverified.

claim: A partial bottom freeze is rejected independently of the level signal.
referent: Adapted half-freeze: `index_status=failed`, `index_kinds=[region_mismatch]`, 361 violations.
checked: Bottom index arrays replaced with the first decoded bottom region after production decode; evaluated by `content_index_sequence`.
verdict: holds
confidence: high; a live partial-frame shape remains unverified.

claim: The barcode decode margin is adequate under the recorder codec.
referent: Healthy/loop encoded clips measured bit luma ranges with minimum observed on/off separation 219.0, compared with documented 106-unit minimum.
checked: 8-second 1024x768 libx264 ultrafast CRF-28 encodes and production signalstats crop probe.
verdict: holds
confidence: high for this host/codec; another encoder or compositor could require a fresh measurement.

claim: The btrfs lock-fd fix refuses an unlocked same-inode descriptor.
referent: Temporary btrfs file probe printed `held True` and `fake_refused RuntimeError canonical lock descriptor does not hold the exclusive lock`.
checked: `held_lock_descriptor` with one flock-held fd and one independently opened same-inode fd.
verdict: holds
confidence: high; canonical production lock remains on ext4 and was intentionally not opened.

## Grill me

1. Why is the half-freeze evidence not a full media proof? It mutates decoded bottom arrays after a healthy production decode, so it proves the typed evaluator rejects region disagreement; a separate compositor-generated partial-frame encode would settle the media-shape question.
2. Why are the loop counts below the clip frame count? The acceptance interval is 360 frames and the decoder records at most 64 index violations; the typed count is the full violation count, while the list is bounded for receipt size.
3. Does the btrfs test prove production lock behavior? It proves the exact fdinfo inode/exclusivity logic on a btrfs temporary file. The live-game lock was not opened, as required.
4. What remains unresolved? Real mpv-to-x11grab duplicate/drop rates. The required round-13 drift/duplicate/skip family sweep was not rerun in round 14; the adapted control/loop/half-freeze probes above are the bounded round-14 evidence. No live diagnostic was authorized in this unit.

Open question I could not settle: whether the real mpv-to-x11grab path produces a duplicate followed by a skip often enough to exceed the exact index/PTS policy. The single settling check is the authorized diagnostic's `diagnostic-result.json` `content_level_sequence` and `index_sequence` blocks.

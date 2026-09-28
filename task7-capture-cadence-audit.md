# Task 7 K1 capture cadence audit

Date: 2026-09-27

Run audited: `/home/brunner56/kp-live-20260922/next-k1-preparations/20260927-task7-scale-102038-74cb804b/runs/20260927-102706-0523fa70`

Scope: read-only diagnosis of the preserved run. No Wine, KOTOR, Gamescope, or capture session was launched. The source media was only decoded/probed; it was not modified.

## Decision

Block another acceptance-oriented live run until capture selection and cadence validation are implemented. The gameplay route passed, but this recording does not meet a defensible 60 FPS capture contract. A diagnostic run intended specifically to test the new capture adapter is appropriate after implementation; another content run with the current recorder is likely to repeat the same defect and can still be serialized as `capture.status = passed`.

The immediate Linux fix is to capture the full root of the harness-owned, private Gamescope Xwayland display rather than passing the game child window through FFmpeg `-window_id`. The private display is already exactly 1024x768, admits one verified game window, and is not the user's desktop. Root capture should let FFmpeg's MIT-SHM path operate, avoiding the synchronous full-frame X11 round trips that failed here. This must be verified by a bounded adapter integration test; if Xwayland still refuses MIT-SHM root capture, select the Gamescope PipeWire stream instead. The host has `gst-pipewiresrc`, and Gamescope published node 208 in this run, while this FFmpeg build has no PipeWire input device.

An explicit `-fps_mode passthrough` or `vfr` is useful to make timestamp policy deterministic, but it is not the cadence fix. `cfr` would fill acquisition gaps with duplicate frames and could make metadata say 60 FPS while preserving the visible stalls.

## What was requested and what was encoded

The exact recorder command from `capture.json` was:

```text
ffmpeg -nostdin -y -threads 2 \
  -f x11grab -framerate 60 -video_size 1024x768 \
  -window_id 0xc00004 -i :1 \
  -an -c:v libx264 -preset ultrafast -crf 28 \
  -pix_fmt yuv420p -threads 2 continuous.mp4
```

The input option ordering is correct: `-f x11grab`, `-framerate`, `-video_size`, and `-window_id` all occur before `-i :1`. The first `-threads 2` is global/input-side and the second is output-side, but neither explains the timestamp pattern. The encoder used the ultrafast preset and reported approximately real-time speed throughout. No encoder error, queue overflow, non-monotonic timestamp warning, or forced finalization appears in the log.

`ffprobe` reports:

| Measure | Result |
|---|---:|
| Duration | 234.666667 s |
| Frames | 12,786 |
| Requested/nominal rate | 60/1 |
| Average encoded rate | 19179/352 = 54.485795 FPS |
| Expected 60 Hz slots over duration | 14,080 |
| Difference | 1,294 frames |
| FFmpeg final counters | `dup=0 drop=1293` |

The one-frame difference between 1,294 missing duration slots and `drop=1293` is the initial inclusive frame/interval boundary. The counters otherwise reconcile exactly. `r_frame_rate=60/1` is the finest encoded timestamp cadence, not proof of constant-rate output. `avg_frame_rate=19179/352` describes the actual frame count over duration.

Frame PTS analysis of the source MP4 found 12,785 inter-frame intervals:

| PTS step | Count |
|---|---:|
| 16.667 ms | 11,982 |
| 33.333 ms | 532 |
| 50.000 ms | 162 |
| 66.667 ms | 63 |
| 83.333 ms | 27 |
| 100.000 ms | 11 |
| 116.667 ms | 3 |
| 133.333 ms | 2 |
| 150.000 ms | 1 |
| 183.333 ms | 1 |
| 616.667 ms | 1 |

There were 803 gaps over 25 ms, 177 over 50 ms, and 9 over 100 ms. The largest gaps occurred at capture PTS 125.300-125.416667, 126.833333-126.966667, 133.233333-133.350, 150.250-150.383333, 167.433333-167.550, 171.416667-171.516667, 186.366667-186.983333, 187.566667-187.716667, and 192.150-192.333333.

## Root cause

The first operational message in `ffmpeg.log` is decisive:

```text
Cannot get the image data event_error: response_type:0 error_code:8
sequence:10 resource_id:14680064 minor_code:4 major_code:130.
Continuing without shared memory.
```

Resource ID 14680064 is `0xe00000`; the failure occurred in X11 MIT-SHM request major opcode 130, minor opcode 4. FFmpeg then continued through its non-SHM `xcb_get_image` path. Each uncompressed 1024x768 BGR0 frame is 3,145,728 bytes, so the fallback requires a synchronous X server request/reply and copy for every nominal 16.667 ms sampling period.

FFmpeg 8.1.2's `libavdevice/xcbgrab.c` explains the resulting shape:

1. `wait_frame()` advances a fixed deadline by one frame duration. If work has fallen behind, it returns immediately until the deadline catches up.
2. `xcbgrab_read_packet()` takes the current wall-clock timestamp before retrieving each frame.
3. After `xcb_shm_get_image()` fails, FFmpeg permanently sets `has_shm=0` and uses `xcb_get_image()` for the rest of the run.
4. Slow X11/GPU/compositor responses therefore create a long wall-clock PTS gap, followed by immediate catch-up grabs with timestamps close together.
5. FFmpeg's default output `fps_mode=auto` chooses VFR for a capable MP4 muxer. VFR passes timestamps through but drops frames when two would have the same output timestamp. That is why the file has visible PTS gaps, `dup=0`, and `drop=1293`.

Sources: the preserved `ffmpeg.log`; the local FFmpeg 8.1.2 help/manual; and the matching upstream [`xcbgrab.c`](https://github.com/FFmpeg/FFmpeg/blob/n8.1.2/libavdevice/xcbgrab.c#L190-L205), [`xcbgrab_read_packet`](https://github.com/FFmpeg/FFmpeg/blob/n8.1.2/libavdevice/xcbgrab.c#L388-L445), and [FFmpeg `fps_mode` documentation](https://ffmpeg.org/ffmpeg-all.html#toc-Advanced-options).

This is a mixed load-sensitive failure with one primary capture defect:

- Primary: the per-window MIT-SHM capture failed, forcing synchronous X11 frame reads. This is directly logged and explains both delayed samples and catch-up bursts.
- Secondary: boot, loading, console setup, rendering, and host scheduling changed how badly the fallback missed deadlines. Cadence varies sharply by run phase.
- Timestamp policy: default VFR discarded catch-up packets that quantized to the same output timestamp. It exposes and slightly reshapes the acquisition defect; it did not cause the initial stalls.
- Game/render repeats: the selected 10-second interval has 153 consecutively identical decoded frames and 375 first-or-changed frames out of 528. The longest identical run is 24 frames including its first frame. Since FFmpeg reports `dup=0`, these were separately captured identical screen images, not FFmpeg-generated duplicates. They may be static scene holds, a game/render cadence below 60, or compositor/game stalls. The media alone cannot distinguish those cases.
- GPU/game stall attribution: not proven. The run used direct accelerated rendering on an AMD Radeon RX 460 with Mesa 26.1.8. Gamescope used its headless backend at 60 Hz and `timerfd` vblank and advertised PipeWire node 208. No GPU utilization, fence latency, CPU load, scheduler latency, or game-present telemetry was recorded. A blocked compositor could contribute to slow `xcb_get_image`, but there is no evidence supporting a GPU fault as the primary cause.

## Whole-run cadence versus the demonstration

FFmpeg's input start was wall-clock epoch 1790505060.763217. The route report began at 1790505200.9497485 and finished at 1790505295.1340692. Therefore:

- Capture before route start: 140.186532 s, about 59.7% of the entire recording.
- Route duration: 94.184321 s.
- Route start to first phase-1 creative marker: 66.930729 s.
- First phase-1 marker to route finish: 27.253792 s.
- Capture tail after route finish: about 0.296 s.

The full-file average is dominated by boot, load, save restoration, tick advancement, overlay/console setup, and cleanup. It is not a measurement of the scale demonstration alone.

Cadence by bounded source-media interval:

| Capture interval | Meaning | Effective frame rate | Largest gap | >25 ms | >50 ms | >100 ms |
|---|---|---:|---:|---:|---:|---:|
| 0-140.186532 s | boot/window-to-route | 56.327 | 133.334 ms | 341 | 62 | 3 |
| 140.186532-180 s | early route/load | 50.657 | 133.333 ms | 235 | 57 | 3 |
| 180-200 s | setup/console approach | 44.587 | 616.666 ms | 160 | 44 | 3 |
| 200-206.117261 s | final setup/pre-marker | 59.674 | 33.333 ms | 2 | 0 | 0 |
| 206.117261-216.117261 s | exact selected representative interval | 52.800 | 83.333 ms | 46 | 11 | 0 |
| 216.117261-220 s | immediate post-clip route | 60.000 | 16.667 ms | 0 | 0 | 0 |
| 220-234.666667 s | completion/cleanup | 58.294 | 66.667 ms | 19 | 3 | 0 |

For the exact selected 10 seconds (`marker - 1 s` through `marker + 9 s`), the source contains 528 frames. Its 527 internal intervals span 9.983334 s and yield 52.787976 interval transitions/s; counting the boundary frame over the 10-second selection yields 52.8 frames/s. The distribution is 481 x 16.667 ms, 29 x 33.333 ms, 10 x 50 ms, 5 x 66.667 ms, and 2 x 83.333 ms.

The representative clip is not the exact full native demonstration. `capture.json` timestamps only the first phase-1 marker. `kotorphasor.log` contains phase 1, phase 2, phase 3, restored, and complete lines, but those lines carry no timestamps. The `log-gate-17.json` file mtime places an upper bound of roughly capture PTS 221.97 s on completion detection, not the exact completion time. Consequently, existing evidence supports exact metrics for the selected interval and bounded metrics around it, but not a precise phase-1-to-complete cadence. Future receipts need timestamped markers for every phase and completion.

## Current code defect

The frozen run used `harness-snapshot/runtime/kpharness/recording.py`:

- `OwnedWindowRecorder.start()` always builds an `x11grab -window_id <child>` command.
- The watcher verifies ownership, geometry, process identity, recorder liveness, and the display lease every 250 ms.
- `stop()` marks capture passed when FFmpeg exits acceptably and the identity watcher did not fail.
- `receipt()` leaves encoded rate, duplicates, drops, and distinct game frames as `null`/unvalidated.
- `schema2_receipt()` and `execution_evidence_ready()` require the expected command identity but do not reject SHM fallback, dropped frames, large PTS gaps, a low average rate, or a representative clip that ends before the completion marker.

Thus `capture.status = passed` currently means the correct window was recorded and finalized. It does not mean the requested sampling cadence was delivered.

## Smallest portable design

Keep route control separate from capture, but replace the hard-coded `OwnedWindowRecorder` source construction with a small capture-adapter contract. Each platform adapter should return a source identity, immutable argv/pipeline, timestamp clock, start-ready evidence, and stop/finalize evidence. The common recorder should own marker timestamps, `ffprobe`/PTS analysis, frame-change analysis, cadence thresholds, and receipts.

Recommended adapters:

1. Linux private Gamescope/Xwayland adapter: verify the lease, root geometry, and exactly one owned visible game window as today; capture `:<display>.0` root without `-window_id`; disable mouse drawing; require the FFmpeg startup log to remain free of `Continuing without shared memory`. This works the same whether the host desktop is Wayland or X11 and whether it is KDE or GNOME because capture stays inside the private nested Xwayland server.
2. Linux PipeWire fallback: consume the specific Gamescope-published PipeWire node through GStreamer `pipewiresrc`, retaining the node identity in the receipt. Use this only when the root MIT-SHM preflight fails. A desktop portal picker is unsuitable for an unattended owned-display harness unless the portal session/token itself is explicitly admitted and recorded.
3. Windows adapter: use Windows Graphics Capture or Desktop Duplication through a small native helper, selected by an owned HWND/process identity. Do not make the generic layer parse Windows-specific handles. `gdigrab` may be retained as a diagnosed fallback, subject to the same cadence gate.
4. macOS adapter: use ScreenCaptureKit through a small native helper, selected by the owned window/application identity and explicit Screen Recording permission. Do not claim window identity from an AVFoundation display index.

Common output policy should be explicit. Prefer timestamp-preserving VFR/passthrough for evidence and calculate cadence from PTS. If a consumer requires CFR, generate a separate presentation derivative and declare its duplicates; retain the timestamp-preserving master as proof.

## Tests and acceptance gates

Add tests before the next content run:

1. Unit command-contract tests: input flags precede `-i`; private-root mode contains no `-window_id`; platform-specific identifiers remain in their adapters; unsupported hosts fail before mutation.
2. Unit FFmpeg-log parser tests: parse final `dup`/`drop`; reject SHM fallback, early recorder exit, forced kill, non-monotonic timestamps, and unavailable final diagnostics.
3. Unit PTS analyzer tests using fixed timestamp fixtures: verify frame count, duration-slot reconciliation, interval histogram, p95/p99/max gap, contiguous stall runs, and per-marker windows. Include this run's 12,786/234.666667/1,293 case as a regression fixture.
4. Unit marker tests: record capture-clock times for phase 1/2/3/restored/complete and require a selected master interval that covers the complete demonstration with configurable lead/tail.
5. Linux bounded integration test under an owned private Gamescope display: run an animated test pattern, capture root, assert no SHM fallback, at least 99% of requested frame slots, no gap over 50 ms, drop ratio below 0.5%, and expected visual changes. Test under both a Wayland and X11 login where available; KDE/GNOME should only affect host admission, not source selection.
6. PipeWire fallback integration test: bind the recorded Gamescope node, ensure no portal/user-desktop source is selected, and apply the same cadence assertions.
7. Windows/macOS adapter contract tests with fake helpers, followed by one real-host integration test per platform that binds the owned app/window, survives resize/refusal paths, and meets the common cadence receipt.
8. Receipt gate: `capture.status` can be `passed` only after source identity, finalization, parsed diagnostics, and cadence thresholds pass. Preserve a separate `recorded_but_cadence_failed` state so route success and media failure remain independently visible.

For a 60 Hz acceptance recording, a practical initial gate is average source frame rate >=59.4, dropped/collapsed input frames <=0.5%, no unexplained PTS gap >50 ms inside the marker-to-complete demonstration, and no FFmpeg-generated duplicates in the evidence master. Those values should be configuration fields rather than Linux-specific constants. Distinct-frame percentage should be reported, but not used alone as a pass/fail criterion because a valid demonstration can intentionally hold a static image.

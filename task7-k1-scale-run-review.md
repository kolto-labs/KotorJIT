# Independent review — Task 7 K1 physical native scale run

Reviewed run: `/home/brunner56/kp-live-20260922/next-k1-preparations/20260927-task7-scale-102038-74cb804b/runs/20260927-102706-0523fa70`

Review date: 2026-09-27

## Verdict

**Behavioral result: PASS. Presentation result: FAIL. Overall creative acceptance: FAIL.**

The run proves the exact K1 physical-console/native-model route that it executed. One verified owned K1 window accepted three real F12 keyboard submissions in one runtime/session. The native model readbacks then proved the same player/model/creature traversed `1.0 -> 0.35 -> 2.40 -> 1.0`, stayed in peaceful gameplay in `danm14aa`, restored the original effective scale, and restored local slots 5 through 9 after the physical cleanup command.

The retained media does not present that result acceptably. At scale 2.40 the player fills almost the full 1024x768 height, the head and upper body extend beyond the top edge, and the body occludes most of the scene. This confirms the reported giant-clipping failure. It is a camera/framing failure, not a refutation of the native scale mutation or restoration. The prepared `creative-run.json` correctly leaves `ok=false` and `acceptance_ready=false` pending visual review.

The requested capture rate was 60 FPS, but this run does not prove a sustained 60 FPS master or a 60 FPS game render cadence.

## Critical findings

1. **The 2.40 giant phase is visibly clipped and cannot pass creative presentation.** Original-resolution review at master timestamps 202 s, 208 s, 214 s, and 220 s shows normal, tiny, giant, and restored states respectively. Normal and tiny are fully readable. At 214 s the enlarged player extends through the top edge; the head is absent, the cloak occupies most of the vertical center, and party/environment readability collapses. The transition back to 1.0 is visible in the full master and restores ordinary framing. Phase contact sheets independently place the tiny transition near 206.5 s, giant transition near 211.75 s, and restoration near 218.0 s.

2. **The 10-second representative clip does not include the restored phase.** `media.json` selects `[206.117260618, 216.117260618]` from the master. Visual review places restoration around 218 s, after that interval ends. The clip includes normal/tiny/giant behavior but cannot demonstrate the final `2.40 -> 1.0` visual restoration. The 234.666667-second continuous master does contain it.

3. **Do not accept this run as a creative/media completion.** The behavioral route is reusable evidence for this exact candidate, but the clipped giant and truncated representative selection require a new presentation run. Existing media must remain failed evidence rather than be relabeled or replaced in place.

## Important findings

1. **Snapshot and input provenance pass.** The sealed snapshot manifest SHA-256 is `691ab195fd11ea490ab58415f09350943f6d95504c933c06bfd0b88fad2f7b6e`; prepared and immediately-before-launch snapshot records agree and report source equality. The executed route is byte-identical to the prepared route, SHA-256 `2e8e403a4ce0873aeeabd810624955502f65c9acc719737bab9dfdb473ee9e0e`. The frozen helper is SHA-256 `07c533c28bb588507b473918b90abdb1a440d6099083155e7a86cfff32584a0e` in the selected source, deployed stage, and retained run source. Staged DLLs match the selected build: `kphasor.dll` `fd8e069a1ff5a7b489f32a6492222f396f85e7b74539deb56228395b297dfac2` and `binkw32.dll` `1b25f37125237aefb67271533f88c48dcf07ddd37bf180743a3b0dfa2ff729d9`. Selected K1 address-table hashes also match the independently retained staged-input record. `launch-once.json` records one invocation through `/usr/bin/python3.14 -I -S -B` and the frozen snapshot driver.

2. **Canonical lock and Gamescope/Xwayland admission pass.** Preflight found the canonical lock free. The live lease later records an exclusive FD on `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/tmp/harness-locks/live-game.lock`. The controller was a dedicated subreaper. Gamescope PID/start `1252153/59907062` owned admitted Xwayland PID/start `1252163/59907101` on displayfd-selected `:1`, with pathname and abstract X11 listeners, the same controller network namespace, no TCP listener, and the explicit host-local no-cookie model. There were no unknown group members and no rejected ready child. Hardware rendering was direct and accelerated on the AMD Radeon RX 460.

3. **Owned-window capture and physical-console behavior pass.** The admitted game window was `0xc00004`, PID/start `1257609/59913887`, title `Star Wars: Knights of the Old Republic`, geometry 1024x768, and lease `gamescope-a628da919fa042bdabc4fec6bfe329b3`. The recorder captured that exact window rather than the root display. Timeline review shows the F12 console visible during construction/arming and again for cleanup.

   The three standalone receipts use runtime identity `17c8ecf0a4c7ed4decbf410c4bcd13a67635bbb646f0c9df2bfea1cb1bc6b428`, session decimal string `"1"`, and request decimal strings `"1"`, `"2"`, `"3"`. Their submitted baselines are `"0"`, `"1"`, `"2"`, so each physical Enter increments the count by exactly one. Outcomes match the same session/request, are `Succeeded`, report return count `"1"`, contain exactly one typed Boolean `true`, are not truncated, and contain empty error code/text. Correlated input/result sequences are respectively `2/3`, `4/5`, and `6/7`; there is no replay or duplicate sequence.

4. **Native route and restoration pass.** All 23 route steps completed without an error or skip, with build `k1_gog_103` and requested/effective game speed 1.0. Independent native predicates passed for the original state, 0.35 phase, 2.40 phase, 1.0 phase, completion, and post-cleanup restoration. Native logs show the same object `2147483644` and the same creature/model pointers changing base/effective scale `1 -> 0.35 -> 2.4 -> 1`; the route separately checks stable module, area, object/model/creature identity, no combat, no conversation, exact effective ratio, completion slots, and restored local slots 5 through 9. Log gates found exactly three phase lines and one `complete phases=3 restored=1` line.

5. **Source and save preservation pass.** The run's 5,945-entry `source-before.json` and `source-after.json` are byte-identical and have the same canonicalized SHA-256 `0cd1db94ce1ee8aa6140c9d0f57e459c513ae1c185ed26fd19e39d0693115588`. That scope includes the executable, INIs, runtime/proxy, logs, saves, Override, and helper source. Preflight also independently matched the five selected autosave file hashes. The run operated on the private staged copy and records `source_unchanged=true` and `inputs_unchanged=true`.

6. **Ordered cleanup passes.** Cleanup completed on the first attempt in order `recorder -> game_wine -> display`, with no errors. The X1 socket was already absent in the admitted controller namespace at cleanup; protected sibling endpoint identities/listeners were unchanged. All recorded controller, Gamescope, Xwayland, and ready-child PIDs are currently absent. This is good cleanup evidence, subject to the lease's stated unavoidable final-stat race against an uncooperative replacement.

7. **The master is valid route media, but 60 FPS is not established.** `continuous.mp4` is SHA-256 `53831eb032b9d154766d67a762c92f22de57bac1291ab841db829ed161ac14c5`, 1024x768, 234.666667 seconds, 12,786 encoded frames, nominal `60/1`, and encoded average `19179/352` (about 54.49 FPS). The retained per-frame timestamps span 0.000000 through 234.650000 seconds: 11,982 of 12,785 intervals are approximately 16.667 ms, 803 exceed 16.8 ms, 271 exceed 33.4 ms, 109 exceed 50.1 ms, eight exceed 100.1 ms, and the worst is 616.666 ms. The recorder's final diagnostic reports `dup=0 drop=1293`. These measurements describe encoded capture cadence only; distinct game-rendered frames remain unvalidated.

## Minor findings

1. **The physical-command files are not fully portable by themselves.** Each `console-command-*.json` contains the exact runtime/session/submission/request/result correlation and states `input="real owned-window keyboard"`, but it does not repeat the window PID/start, lease ID, display, or geometry. Those facts are joined at run level through `creative-run.json`, `capture.json`, and `gamescope-lease.json`. The bundle is sufficient for this review, but embedding the stable window/lease identity in every command receipt would make each receipt independently auditable and match the preparation brief literally.

2. **Marker timing is intentionally approximate.** `capture.json` records marker detection at master time 207.117260618 s using a 100 ms native-log poll and explicitly says capture startup latency is not calibrated. This is adequate for finding the scene in the continuous master, but it should not be used to claim sub-frame synchronization or exact phase duration.

3. **The initial X11 shared-memory error did not invalidate capture, but it is part of the record.** The recorder logged one X11 image-data error and continued without shared memory. The master completed and remained reviewable; the cadence/drop results above are the practical limit of what this run proves.

## Smallest framing change for the next run

Keep the same actor position, facing, phase timing, and single static viewpoint. Before the creative marker, snap the existing chase camera farther back and let it settle; do not move or zoom it during any scale transition. Choose the fixed distance so the normal 1.0 actor occupies no more than roughly 25-30% of the 768-pixel frame height (about 190-230 pixels), centered with headroom and floor below the feet. A 2.40 multiplication would then occupy roughly 456-552 pixels and remain fully inside the frame.

The smallest route-level change is to replace the current default-distance `SetCameraFacing(GetFacing(p))` setup with the same facing plus an explicit larger distance and a snap transition, retaining a modest fixed pitch. Calibrate that distance in a preparation-only framing check, then freeze it for the one authorized run. Do not chase the actor with per-phase camera calls: that would introduce visible zoom/pan motion and make the scale effect harder to judge. If the K1 chase camera still applies collision-driven movement at that distance, use one fixed observer camera established before the marker; do not animate it during the scene.

## Conditions before authorizing another K1 attempt

A next live run should be authorized only after all of the following are concrete and reviewed:

1. A new private preparation/stage/prefix/output path and one-attempt launch receipt are selected; the failed run and its media remain immutable.
2. The route differs only in pre-scene framing and any necessary post-scene clip tail. Native scale values, physical F12 construction/arming/cleanup, identity checks, local-slot restoration, game speed, and phase timing remain unchanged.
3. A preparation-only framing receipt demonstrates, without launching another game, that the chosen static composition targets normal-body height at 25-30% of the frame and leaves enough head/foot margin for a 2.40 projection. If that cannot be established without live calibration, authorize one bounded framing run rather than calling it acceptance.
4. Camera distance/facing/pitch are set once with a snap before the creative marker, followed by a settle interval. No camera input or scripted camera movement occurs from normal through restored.
5. Representative-media selection is lengthened or shifted so it visibly includes stable normal, tiny, giant, and restored holds. It must extend beyond the observed restoration plus a short stable tail; the previous 10-second `[206.117, 216.117]` selection is disallowed.
6. The same snapshot/input/source/save/lock/display/window/physical-console/cleanup gates are regenerated and independently checked. No evidence from this run is carried forward as proof of a new run.
7. Acceptance requires original-resolution visual inspection showing the whole body, including head and feet, throughout the 2.40 hold; readable surroundings; no camera collision, zoom, pan, or recovery lurch; and a stable restored composition matching the pre-effect view.
8. Capture cadence is reported from measured timestamps and recorder diagnostics. A nominal 60 FPS setting may be stated only as requested/encoded nominal rate unless measured cadence and distinct rendered-frame evidence support a stronger claim.

With those conditions met, one new K1 presentation attempt would be reasonable. This review does not itself authorize or launch it.

# Task 7 K1 scale acceptance attempt — behavior passed, media rejected

**Overall acceptance: FAIL.** Exactly one fresh supported Gamescope/K1 attempt ran. All 23 route steps passed, including three physical F12 console requests, the independent native normal→tiny→giant→normal scale gates, and state restoration. Ordered cleanup and source preservation passed. The master fails full-body framing and cadence, and the runner's representative interval omits visible restoration. No acceptance command or supplemental 25 FPS GIF was produced. No display/game retry occurred.

## Exact retained paths

- Preparation: `/home/brunner56/kp-live-20260922/next-k1-preparations/20260927-task7-scale-102038-74cb804b`
- Run: `/home/brunner56/kp-live-20260922/next-k1-preparations/20260927-task7-scale-102038-74cb804b/runs/20260927-102706-0523fa70`
- Fresh snapshot: preparation directory's `harness-snapshot`
- Supplementary media review: preparation directory's `media-review`
- Master: run directory's `continuous.mp4`
- Definitive full-resolution failure frame: `media-review/frame-213s.png`
- Detailed phase sheets: `media-review/phases-01.png` through `phases-04.png`
- Whole-timeline sampling: `media-review/timeline-01.png` through `timeline-05.png`
- Final independent teardown/preservation check: preparation directory's `final-cleanup-verification.json`

The complete invocation is retained in `launch-once.json`, with the launcher PID/start data in `launcher-process.json`. The one supported creative invocation began at 10:27:04 UTC. Gamescope was launched after staging around 10:29:29 UTC, and K1 connected at 10:30:59 UTC. The route executed for 94.184 seconds, and ordered teardown completed around 10:34:59 UTC. The supervisor finished its independent source verification at 10:43:26 UTC; its graceful 1,800-second deadline never fired. No outer timeout killed the controller. The launcher exited 1 because the schema-2 output intentionally remained unaccepted.

## Preconditions, selected inputs and provenance

Followed `/home/brunner56/kp-live-20260922/task7-next-k1-run-brief.md`. The route was generated verbatim from the brief into new private storage. The frozen snapshot's `Scenario.load` parsed 23 steps and exactly three `console_command` operations, each requiring one exact typed Boolean true. Every route verb was checked before launch. Requested and observed game speed were both 1.0. No product/worktree file was edited, no old stage/prefix reused, and no handwritten or monkeypatched game/window session was substituted.

Read-only preflights passed: no conflicting Gamescope/game/Wine/FFmpeg workload, canonical lock available, selected tool binaries present, no caller display reuse, more than 4 GiB MemAvailable and 1 GiB SwapFree, and 33,513,279,488 bytes free at the final launch preflight. The preflight probe released its lock before invocation; the supported runner acquired and held its own canonical flock through teardown. The protected X0/X94/X100 endpoint identities and named socket-table rows and the historical quarantine identities were recorded before launch.

Exact selected and independently verified deployed hashes:

| Input | SHA-256 |
| --- | --- |
| `kphasor.dll` | `fd8e069a1ff5a7b489f32a6492222f396f85e7b74539deb56228395b297dfac2` |
| `binkw32.dll` | `1b25f37125237aefb67271533f88c48dcf07ddd37bf180743a3b0dfa2ff729d9` |
| Source `swkotor.exe` | `9c10e0450a6eeca417e036e3cde7474fed1f0a92aab018446d156944dea91435` |
| `model_scene.lua` | `07c533c28bb588507b473918b90abdb1a440d6099083155e7a86cfff32584a0e` |
| `k1_gog_103.json` | `44a5984b71bf994dd5ee520e49198ced4953a3ff2e385673e9264a44ee36d4f2` |
| `k1_steam_103_unpacked.json` | `541c5c3e7890406ce08d2959ed90cd3a97eee8974ceff6d34ae8522ccb7182c5` |
| Exact private route | `2e8e403a4ce0873aeeabd810624955502f65c9acc719737bab9dfdb473ee9e0e` |
| Snapshot manifest | `691ab195fd11ea490ab58415f09350943f6d95504c933c06bfd0b88fad2f7b6e` |

The worktree and candidate-source address tables matched the brief before launch; the tables deployed under the private stage also matched. Both DLLs matched the retained `build-artifacts.json`. Copied `baseline-source-provenance.json`, `reviewed-overlay.json`, and `build.log` describe base commit `ca329e52dd27d1a3f5a56748d93c8ab0fd7f24f2` plus overlays. This was not represented as a clean build of the dirty worktree or a verified public release package.

All five files in source save `000001 - AUTOSAVE` matched the brief before and after execution. The supported runner and independent supervisor each retained source preservation maps covering executable, INIs, runtime/proxy, logs, saves, Override and source Lua. The independent map contained 5,945 entries; its before/after contents were identical. Selected route/helper/build evidence and all exact brief inputs remained unchanged. The 27-module fresh snapshot included every required module, was source-equal before and after the attempt, and its complete file hash map stayed unchanged after sealing files 0444/directories 0555. The supported driver used isolated absolute Python and verified repository context; readiness used `-I -S -B`.

## Runtime, physical-input and native behavior results

K1 reported `build=k1_gog_103`, 19 hooks, and `live=True`. The save loaded into `danm14aa` with main_menu=0, a valid living PC at approximately (105.676254, 96.463966, 0.996142), and 96/96 HP. The initial native gate required no combat/conversation, available native model support, and base scale 1.0 before saving the model/module/area identities and local slots 5–9.

The selected Gamescope lease was `gamescope-a628da919fa042bdabc4fec6bfe329b3`; the verified game window was `0xc00004`, owned by game PID 1257609/start 59913887, geometry 1024×768, on `:1`. It was admitted through the dedicated controller/subreaper PID 1239962, Gamescope PID 1252153, and adopted Xwayland PID 1252163. The renderer was direct and accelerated AMD Radeon RX 460. Capture used only the admitted window, not the root desktop.

All three physical receipts say `input="real owned-window keyboard"`. They share runtime identity `17c8ecf0a4c7ed4decbf410c4bcd13a67635bbb646f0c9df2bfea1cb1bc6b428` and session `"1"`:

| Route step | Baseline submitted | Request | Exact outcome |
| --- | --- | --- | --- |
| 8: construct scene | `"0"` | `"1"` | `Succeeded`, return_count `"1"`, Boolean true |
| 10: arm delayed timer | `"1"` | `"2"` | `Succeeded`, return_count `"1"`, Boolean true |
| 20: verify completion/release state | `"2"` | `"3"` | `Succeeded`, return_count `"1"`, Boolean true |

`physical-command-audit.json` independently checks canonical decimal IDs, submitted+1, exact request/session correlation, untruncated typed return values, empty untruncated errors, and separate input/result lines with distinct sequences. The result lines decode to `boolean: true`; they are not inferred from the input text. F12 overlay opening, typing/output, and closure are visible in the retained master sampling. Native `assert_lua` operations were independent state evidence and were not counted as physical console submissions.

All three native phase gates passed for 0.35, 2.4, and 1.0 base scales, matching effective ratios and the original PC/model/creature/module/area identities, without combat/conversation. Completion/restoration and exactly three phase markers plus one `complete phases=3 restored=1` marker passed. Final native local slots 5–9 and original base/effective scale restoration passed after the physical cleanup command. There were no skipped route steps.

Proof limits remain explicit: the production console receipts do not retain every intermediate wire response, a DirectInput call-count delta, or separate window fields within each console file. Window/capture binding is in the schema-2 receipts and continuous video. Also, successful native Boolean assertions do not serialize every intermediate model value; their exact predicates and results are retained. The report retains initial HP/position/world state, but not a separate complete post-scene native HP/actor inventory. No unexpected movement, damage, new actors, or effects are apparent in the inspected scene frames; this is not a comprehensive native before/after world-state proof.

## Definitive visual failure and timing

The normal player is visible at 202 seconds, the tiny player at 208 seconds, and the restored player at 220 seconds. The giant player's head and upper body extend outside the top of the 1024×768 frame. Full-resolution `frame-213s.png` is decisive evidence.

Decoded-frame classification of the visually checked enlarged cloak occupying a fixed top-center region establishes:

- First giant/clipped frame PTS: **211.800000 seconds**.
- Last giant/clipped frame PTS: **218.016667 seconds**.
- First following restored frame PTS: **218.033333 seconds**.

`giant-frame-boundaries.json` records the ROI [450,40,100,100], luma threshold, decoded-frame count and observed values. Giant-region means were about 12.3–13.1 versus roughly 80–86 outside the giant phase; 0.25-second phase contact sheets visually crosscheck the classification. These are presentation timestamps from the recorded master, not invented native callback timestamps.

**Camera/framing attribution:** this was not a perfectly fixed camera. The door and background move horizontally between 202 and 220 seconds, and smaller drift is visible during the phase sheets. The giant nonetheless remains cropped for its entire approximately 6.23-second interval; there is no compensating zoom-out to fit the enlarged body. Thus the demonstrated problem is insufficient framing for scale 2.4, with camera/background drift also preventing a clean stable-camera claim. The retained evidence does not isolate an exact native camera cause, and no camera motion was added during review.

The built-in representative interval is **206.117260618–216.117260618 seconds**. It ends approximately 1.916 seconds before visible restoration at 218.033333 seconds, so it cannot satisfy normal→tiny→giant→normal clip coverage. No fallback interval was relabeled as the effect.

Review methodology: all-time coverage through five contact sheets sampled every two seconds; detailed 204–221-second coverage every 0.25 seconds; full-resolution phase frames; and decoding every master frame for timestamps and pixel cadence. This is transparent sampled visual inspection, not a claim to have viewed every frame at real-time speed. A definitive failure is visible without upgrading that method into exhaustive visual acceptance. The master also contains the expected menu/load lead-in and sampled black load-transition frames around 162–164 seconds; those were not mistaken for gameplay.

## Measured capture cadence

The master SHA-256 is **`53831eb032b9d154766d67a762c92f22de57bac1291ab841db829ed161ac14c5`**. It remained unchanged throughout analysis.

| Measure | Observed result |
| --- | --- |
| Requested acquisition | 60 FPS, 1024×768, exact `-window_id 0xc00004`, input `:1`, no interpolation |
| Encoded nominal rate | `60/1` |
| Encoded average rate | `19179/352` ≈ **54.4858 FPS** |
| Master frame count/duration | **12,786 / 234.666667 s** |
| FFmpeg final diagnostic | **dup=0, drop=1293** |
| Decoder result | exit 0, no decoder-error output |
| Median PTS spacing | 0.016667 s |
| Largest PTS spacing | **0.616666 s**, from 186.366667 to 186.983333 |
| Nonpositive PTS deltas | 0 |
| Unobscured 200–224 s interval | 1,366 decoded frames, 56.9167 frames/s |
| Central gameplay exact distinct image rate | mean 47.1667/s over 200–224 s; per-second values retained |
| Longest exact repeated central image | **0.633334 s**, 209.050000–209.666667 plus final nominal frame duration |
| Longest near-repeat, mean pixel delta ≤0.20 | **0.750001 s** in that gameplay interval |
| Giant sample 212–216 s | 205 decoded frames, 51.25/s; mean exact distinct ROI images 28.5/s |

Pixel cadence uses central gameplay crop [256,80,512,600], downsampled to 128×150 grayscale, excluding the HUD. It hashes decoded image content and also records mean absolute changes; it does not use HUD clock changes as game-frame proof. Compression/quantization and this threshold are explicitly documented limitations. Exact decoded-image repetition over 600 ms and the measured drops fail the brief's practical smoothness gate; native animation cadence is not inferred merely from nominal FPS. PTS data, histogram, gap list, decoder log, full per-frame ROI hashes/deltas, and scripts are retained under `media-review`.

The supported runner automatically generated `representative.mp4` and its usual **8 FPS** `representative.gif` after route success, before the later manual visual rejection. **Both outputs are unaccepted and quarantined in place as failure evidence**, excluded from accepted deliverables and presentation. They remain at their original private run paths, unchanged and undeleted; quarantine here is a disposition, not a filesystem move. No additional GIF was generated, no accepted 25 FPS deliverable exists, and neither preview is labeled accepted. No `creative_accept` command or acceptance receipt was created. The original master was never cut, re-encoded or replaced.

## Cleanup, preservation and final decision

Ordered teardown was exactly **recorder → game_wine → display**, in one passed attempt with no component errors or hidden failed cleanup attempts. The adopted Xwayland child PID 1252163 was reaped with wait status 0. The lease's socket-cleanup result was `already_absent`: Gamescope removed the fresh pathname, and the helper verified namespace-scoped absence. Its explicit unlink branch was not exercised in this attempt.

Independent final checks found all recorded lease/controller/game PIDs absent: 1252193, 1252163, 1252153, 1252191, 1239962, 1257609. No private `:1` pathname or abstract socket-table entry, `/tmp/.X11-unix/X1`, or `/tmp/.X1-lock` remained. The canonical flock was free. Protected X0/X94/X100 node identities and recorded socket-table rows, and both historical quarantine identities, were unchanged. Unrelated displays were left alone.

Supported and independent source/save/input/snapshot preservation all passed. The run remains `ok=false`, `visual_review.status=pending`, `acceptance_ready=false` in its original production receipt. `media-review/visual-failure.json` records the supplementary failed review without mutating the completed execution fields. `kpharness.creative_accept` and `verify_acceptance()` were not invoked because acceptance preconditions failed; no acceptance receipt was manufactured.

**Final disposition:** physical console/native scale integration succeeded for this exact candidate and save. Full Task 7 media acceptance failed on giant full-body framing, representative restoration coverage, and measured cadence. Camera drift and the stated evidence limits remain visible in the report. The one authorized attempt is consumed; no retry or fallback was performed. All private run/preparation evidence is retained and bound by the preparation's `artifact-hashes.json`.

# Task 7: bounded native scale framing correction

Prepared 2026-09-27. This is a read-only diagnosis and proposed later-run change. No worktree files were changed and no Wine, game, Gamescope, or FFmpeg process was launched for this investigation. This brief does not authorize another launch.

## Decision

Use a route-only reduction from **2.4 to 2.0** for the giant phase, keeping the existing 0.35 tiny phase, original-scale restoration, stationary player, settled camera, timing, and independent native assertions. The largest numeric giant value supported by the previously accepted full-body media is 2.0. Those earlier scenes placed NPC subjects farther from the camera, however: **2.0 is proven in that composition, not guaranteed to fit the current third-person player composition**. A later attempt must independently pass the player framing gate.

Do not add camera APIs, rotate the camera, switch the player to first-person, move the player, or introduce effects to rescue framing. There is no verified scale-aware camera distance adjustment in the current route. A smaller value such as 1.6 remains a candidate for a separately reviewed route if pre-launch review rejects 2.0; it is not an automatic fallback, a promised framing solution, or permission to retry a failed launch. At 2.0 the giant is twice normal scale and approximately 5.71 times the tiny phase, making the intended transformation readily distinguishable while reducing the failed giant value by one sixth.

## Evidence and cause

Failed preparation directory:

`/home/brunner56/kp-live-20260922/next-k1-preparations/20260927-task7-scale-102038-74cb804b`

Retained run:

`/home/brunner56/kp-live-20260922/next-k1-preparations/20260927-task7-scale-102038-74cb804b/runs/20260927-102706-0523fa70`

The run's `report.json` reports all 23 route steps passing. Native phase observations identify base scales 0.350, 2.400, and 1.000, followed by restoration and completion. The physical console commands have retained per-command receipts. These establish behavior execution; they do not establish acceptable framing.

The run's `capture.json` records exact-window X11 capture of window `0xc00004` on display `:1`, 1024×768, requested 60 fps, and `root_capture:false`. Its capture command contains no crop filter. The Gamescope lease identifier is `gamescope-a628da919fa042bdabc4fec6bfe329b3`. `gamescope-session-cleanup.json` reports passed. These values identify this retained run only and must not be reused as authority for a future run.

Existing `media-review/timeline-05.png` shows normal full-body player at 03:20–03:24, tiny player around 03:26–03:30, giant player with head/upper body outside the top edge at 03:32–03:36, and normal restored player from approximately 03:38. Floor position and background remain substantially fixed. The giant's failure is therefore scene composition under the enlarged player model, not an encoder crop. The contact sheet SHA-256 is `0d2e5b86d649b950ea83b7222b456b408a7d11bc9dc67990a7a7942efd71260a`. Two-second contact-sheet sampling bounds visible events; it is not a frame-accurate transition timestamp.

Earlier sheets show a temporary obstructed view during camera setup around 02:50–02:54, followed by the settled third-person view. The effect interval must begin after setup is visibly settled. Do not introduce further camera adjustments during the size sequence. Companions and the fixed environment provide useful scale references; the player's complete body must remain separately identifiable.

The original `generate-route.py` applies `SetCameraMode(p,2)` and `SetCameraFacing(GetFacing(p))` before the sequence. It does not adjust distance for model scale or assert a projected body bounding box. Raising resolution at the same aspect ratio, removing a nonexistent crop, or trimming out the giant phase cannot fix this cause.

## Cross-check against previously accepted full-body runs

1. `/home/brunner56/kp-live-20260922/media/native-size-swap/review.json` accepts source run `/home/brunner56/kp-live-20260922/stage-k1/runs/20260922-114443`, selected interval 6.25–16.00 seconds. Its source master SHA-256 is `0e5d3e69c1feceb2664fa5f0b75379d5fda80e8a1b8426efa8059ed29430955d`. The source is 1024×768 and 60/1 fps. Existing `verify-landscape-start.jpg`, `verify-landscape-opposite.jpg`, and `verify-landscape-restored.jpg` visibly show the whole heads, bodies, and feet of three stationary Sith NPCs, including giant phases and normal restoration, in a stable first-person view with UI hidden. These retained images were inspected directly.
2. `/home/brunner56/kp-live-20260922/media/f12-native-size-swap/review.json` accepts source run `/home/brunner56/kp-live-20260922/stage-k1/runs/20260922-124445`, all 28 route steps, a physical console-loaded Lua timer, six native scale phases, peaceful behavior, and cleanup. Its accepted interval is 15.5–34.5 seconds, or 19 seconds. The accepted MP4 SHA-256 recorded there is `4f5ee1cb4d25a411f8d1e610d432d03b795ae20ad034ee64b846c9be281348c2`. This diagnosis read the retained review and route; it did not newly decode that MP4.

Both adjacent `executed-route.toml` files use largest scale **2.0**, with tiny scale 0.4. The F12 scene uses `spawn=true`, `resref="g_sithtroop01"`, `forward=6`, `sides={-2,0,2}`, `hold_ticks=90`, and alternating arrays `{.4,2,.4}`, `{2,.4,2}`, and `{1,1,1}`. The subjects are six units in front of the viewer, not the close player character. Both routes include a custom `capture_free_look` step after camera mode/facing setup. Its report says visual confirmation is required. No `capture_free_look` handler was found in the current supported scenario/console/creative step modules. Copying that old verb would require a new unsupported harness path, and first-person viewing would defeat the current player-body requirement.

Consequently the accepted numerical value 2.0 is useful prior evidence for the reduced scale, but neither old receipt certifies current player framing. Recreating the three-NPC scene would change subject, spawn/cleanup obligations, route length, and camera handling; it is larger in scope than the proposed two-step route change.

## Exact proposed route change

Retained generator:

`/home/brunner56/kp-live-20260922/next-k1-preparations/20260927-task7-scale-102038-74cb804b/generate-route.py`

SHA-256: `9d430c2294e25641951f37cd9f6301a6e860607866a156ef34811911b114703a`.

Retained generated route:

`/home/brunner56/kp-live-20260922/next-k1-preparations/20260927-task7-scale-102038-74cb804b/physical-native-scale.toml`

SHA-256: `2e8e403a4ce0873aeeabd810624955502f65c9acc719737bab9dfdb473ee9e0e`.

For a new, separately reviewed preparation, change only:

- Generator line 20: `scales={{0.35},{2.4},{task7_body.base}}` to `scales={{0.35},{2.0},{task7_body.base}}`.
- Generator line 25: phase tuple `(2,2.4)` to `(2,2.0)`.

The resulting route changes exactly step 8, the physically typed scene-construction command, and step 13, the independently sampled phase-2 base/effective scale gate. The gate must check both base 2.0 and effective `task7_original.effective/task7_original.base*2.0`; changing only the displayed command or only its expected gate would be inconsistent.

Keep `spawn=false`, `hold_ticks=60`, the 180-callback initial delay, timer registration at 16, actor/model/creature identity assertions, module/area/combat/conversation checks, local slot restoration, original model restoration, all three physical console commands, F12 closure, and calm waits. Callback counts are not wall-clock frame counts: the retained giant phase spans several seconds. Do not shorten the behavior merely to fit a ten-second media default.

No product/harness camera change is proposed. Any later implementation must create fresh preparation files and a new frozen snapshot identity; never mutate the retained failed-run route or accepted historical media.

## Clip selection correction

The retained capture marker is approximately 207.117260618 seconds into capture. A ten-second interval starting one second before it would cover about 206.117–216.117 seconds, ending while the giant is still visible. It cannot show the restored normal phase at approximately 218 seconds. Marker polling is 100 ms and capture startup timing is not calibrated, so marker arithmetic alone is insufficient for exact visual boundaries.

For diagnosis of this retained run, **204–224 seconds** is a suitable 20-second review interval: normal lead-in at 204, tiny around 206, giant around 212–216, restored normal around 218, then a calm restored hold before the console opens around 228. This is not an accepted deliverable because the giant remains clipped. Do not promote the failed footage by trimming away the defect.

For a later run, select the equivalent interval from actual visual transitions and matched native phase evidence. Require at least two seconds of calm normal baseline before the first change and at least two seconds of normal restored full-body footage after restoration, with every complete tiny and giant hold retained. Around twenty seconds is a planning allowance, not a forced duration; preserve a longer interval if actual callback timing requires it. Do not reuse this run's absolute 204–224 timestamps.

A supported runner's default short clip must remain unaccepted if it omits a phase or restoration. A later authorized media step can derive a complete supplemental clip from the unchanged accepted master using explicit reviewed start/end timestamps and digest linkage. Any automated clip-window override would require its own focused change/review; this brief does not implement one.

## Offline validation performed and remaining

Performed without executing the route or generator:

- Parsed the retained TOML: 23 steps.
- Constructed the two proposed generator substitutions in memory and parsed the result with Python `ast.parse`: passed.
- Constructed the corresponding generated TOML substitutions in memory and parsed with `tomllib`: passed.
- Compared all parsed steps: only steps 8 and 13 differ; all other steps are equal and no `2.4` remains.
- In-memory proposed TOML SHA-256: `1114c1cb55ccfd25a9178a7583946e4ffafc92e0640706713df19d4f2d1d9210`. This is an audit reference for the literal minimal substitution, not a written or launched artifact.
- Inspected retained failure contact sheets and prior accepted native-size-swap full-body images; cross-checked old acceptance receipts and executed routes.

One initial read-only validation script used the wrong TOML key `steps`; it exited before validation. The corrected check used the actual `step` array and passed as described above. No executable route was run.

Before any later launch, independently review the generated route and its complete package/snapshot identity, require only the intended changes, and compare the baseline player silhouette against the available headroom and HUD. A static projection estimate can reject an obviously unsafe candidate; it cannot certify perspective behavior. If review rejects 2.0, prepare and review a separate 1.6 candidate before launch rather than making an in-session adjustment.

## Gates for a later single authorized attempt

- Follow `/home/brunner56/kp-live-20260922/task7-next-k1-run-brief.md` for fresh verified snapshot, package/DLL hashes, source preservation, canonical live lock, session/display ownership, game-state prerequisite, and cleanup. Refresh changing facts. No stale display/window/PID is authority.
- Acquire the canonical lock before shared live state and hold it through cleanup verification. Exactly one game launch, one route, and no retries. Do not overlap other Wine/game/Gamescope sessions. Failure of readiness, command outcome, framing, cadence, or cleanup is a failed attempt requiring review before any further launch.
- Require the intended peaceful loaded save/module, stable original player identity, original base scale 1.0, stationary subject, and settled third-person view before capture evidence. No disorienting camera movement or arbitrary effects. Keep camera fixed throughout normal → tiny → giant → normal.
- Physical F12 opening, typed command text, Enter submission, exact runtime/DLL identity, current session identifier, exact request identifiers, terminal success, return count and Boolean values must be joined in retained receipts. Socket-side observation may independently verify state but cannot replace physical console submission.
- Independently verify native scales 0.35, 2.0, and original 1.0 with unchanged actor/model identity and correct effective ratios, then restored local slots and completion. Logs and successful requests alone do not pass the visual gate.
- Review the exact 1024×768 game-window frames at baseline, tiny, giant, restoration, and transitions. The player must be clearly identifiable and fully visible from head through both feet in every phase, with at least 16 pixels of clear separation from the viewport edge and any overlapping HUD element. Evaluate actual HUD boundaries and scene occlusion, not an assumed fixed safe rectangle. The giant's head, feet, or limbs must not be clipped or hidden by companions/UI. The tiny phase must remain visible rather than disappearing behind geometry. No digital reframing, camera sweep, or omitted giant frames can repair failure.
- Retain an unchanged 60 fps MP4 capture master with exact-window source, digest, capture/window/session evidence, and reviewed cadence across the effect interval. Requested 60 fps or a nominal stream rate alone is insufficient: inspect timestamps, gaps, duplicate-frame runs, smoothness, and dropped-frame evidence. The retained failed run has a separate cadence concern (12786 recorded frame timestamps through about 234.65 seconds); this framing proposal does not claim to fix capture cadence.
- Produce the representative MP4 only from a behavior-accepted unchanged master, with the complete measured interval and calm lead-in/out above. A supplemental GIF may use a lower practical frame rate, but must look smooth, retain all phases/restoration, preserve framing/aspect, and name its exact source-master digest and interval. Record derived artifact hashes and acceptance reasons. No synthesized/interpolated frames or unrelated clip may substitute for runtime evidence.
- Restore model and locals, close console, stop only lease-owned processes, verify adopted-child/process/display/socket cleanup, retain all receipts, and verify canonical source preservation. Cleanup failure is not success even if the effect looked correct.

The current diagnosis is complete. The proposal reduces the oversized phase and fixes the acceptance interval; live full-body framing and smooth 60 fps media remain unproven until a separately authorized, reviewed attempt passes these gates.

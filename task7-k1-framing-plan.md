# Task 7 K1: framing plan for the next creative scale attempt

Prepared 2026-09-27. Read-only research. I edited no worktree files and launched nothing: no Wine, game, Gamescope or FFmpeg. I did not touch the canonical live lock. Every pixel number below comes from decoding the retained PNGs in memory with pure-Python zlib. No new frames were extracted from any MP4.

This plan does not authorize a launch. The next K1 attempt stays blocked until the separate capture diagnostic passes (see `task7-capture-cadence-round-10-brief.md`).

Paths used below:

- WT = `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`
- PREP = `/home/brunner56/kp-live-20260922/next-k1-preparations/20260927-task7-scale-102038-74cb804b`
- RUN = `PREP/runs/20260927-102706-0523fa70`
- CAL = `/home/brunner56/kp-live-20260922/stage-k1/runs/20260922-113712`. This is the legacy camera-calibration run. It used the same save, the same PC position `(105.7,96.5,1.0)` and the same `danm14aa` module.

## 0. Bottom line

1. **K1 has no way, proven or even in source, to set camera distance or pitch.** The `kp.*` API has no camera facility. K1's `SetCameraFacing` takes one float (`data/routines/k1.json:724-735`, `src/generated/routines_k1.inc:819`). The review's advice to pass an "explicit larger distance and a snap transition" (`task7-k1-scale-run-review.md:55`) is the NWN signature. It cannot be written for K1.
2. **The failed run's camera was too close and it never settled.**
   - A normal-height player measured 270–272 px, which is 35% of the 768 px frame.
   - The background panned at about 10 px/s for the whole scene: the door box moved from x=303 to 364 to 487 at 202, 208 and 220 s. Its rows and height stayed fixed.
3. **Scale 2.0 does not fit reliably at that camera.** I fitted the projection and kept only the fits that agree with the clipping seen at 2.4. Those fits put the largest giant scale that keeps a 16 px top margin at **1.87–2.04** (estimate). The framing brief's 2.0 sits at or past the edge.
4. **The 25–30% target needs the camera 1.11–1.48× farther along its view ray (estimate).**
   - The headroom figures use only the fits that agree with the observed 2.4 clip.
   - At 27.5% framing, a 2.0 giant keeps about **74–125 px** of headroom (estimate). The worst consistent fit still keeps ≥ 60 px up to about 28.2% (217 px).
   - 2.4 still clips at 27.5% (top row −116 to −12) and at 25% (−40 to +37). It would need about 23% framing or less.
   - The review's linear figure of "456–552 px" for 2.4 (`task7-k1-scale-run-review.md:53`) ignores perspective. The perspective estimate is well over 630 px, and the head leaves the frame.
5. **Same spot, different yaw, already gives about 28.6%.** In the calibration run, the chase camera measured 220 px (28.6%) at one yaw and about 270 px (35%) at another (CAL shots 0007 and 0006). This suggests yaw or collision sets the effective distance. That cause is `unverified`, and that view was also still drifting.
6. **Recommendation:**
   - Giant scale **2.0**, but accept only if the measured baseline is ≤ 27.5% (≤ 211 px) in the same run.
   - Get the farther composition from one of two sources:
     - (a) a small reviewed native `kp.camera` change. This is preferred.
     - (b) a route-only yaw/caller candidate that has first passed a separate, bounded framing diagnostic. This is not the acceptance run.
   - The current route cannot meet the 25–30% requirement at any giant scale, so scale reduction alone is not a fix.
7. **Conflict to resolve before any change.** The framing brief says "Do not add camera APIs, rotate the camera, … move the player" (`task7-scale-framing-fix-brief.md:9`). The current requirement asks for a farther camera at 25–30%. Both cannot hold. Either the requirement is relaxed, or brief:9 is superseded for camera setup done once before the marker.

---

## 1. Camera controls available today

The rule: `nwscript.call` is the only NWScript entry point (`WT/docs/nwscript-api.md:5`, registered at `WT/src/api/routines.cpp:562-566`). The caller bridge is `nwscript.with_caller(id, fn)` (`WT/src/api/routines.cpp:523-551`, `WT/docs/lua-api-complete.md:34`). Native helpers live under `kp` (`WT/docs/lua-api-complete.md:24-37`). No NWScript routine name is copied into `kp`.

### 1a. Lua-native `kp.*`: no camera facility

| Facility | Source | Camera use | Live status |
|---|---|---|---|
| `kp.model.{identify,matches,snapshot,resize,restore,capabilities}` | `WT/src/api/model_lua.cpp:100` | None. It sets scale, which is the subject of the effect. | Proven live: RUN `report.json` steps 12–15 and 22; `kotorphasor.log:155-166` |
| Object helpers in `entity.cpp` (`pc`, `position`, `area`, `find`, …). I did not confirm the Lua table name. | `WT/src/api/entity.cpp:430-462` | Read-only position. There are no setters. | Not needed |
| `kp.registertimer` | `WT/src/api/timers.cpp:334` | Only schedules work | Proven live (RUN step 10) |
| `kp.mem.*` (raw read/write, `findsig`) | `WT/docs/lua-api-complete.md:37` | Could poke camera memory in theory. It is documented as explicitly unsafe, with no reviewed camera offsets. | Not acceptable for an acceptance route |
| Any `kp.camera` | none: `grep -rniI camera WT/src WT/include \| grep -v generated \| wc -l` prints `0` | — | **Missing** |

### 1b. `nwscript.call` bridge, K1 catalog

| Routine (id) | Signature | Source | Live status |
|---|---|---|---|
| `SetCameraMode` (504) | `(object oPlayer, int nCameraMode)` | `WT/data/routines/k1.json:7092`, `routines_k1.inc:1277`; native path `WT/docs/research/camera-win-k1.md:19` | **Visible effect proven.** CAL shot 0002 (mode 0) shows an obstructed or odd view; 0006 (mode 2) shows a chase view. The RUN timeline also changes at 02:46 → 02:50 → 02:54 (`PREP/media-review/timeline-04.png`). What mode 2 means in K1 (for example "stiff chase") is `unverified`. |
| `SetCameraFacing` (45) | `(float fDirection)`. **No distance, pitch or transition.** | `k1.json:724-735`, `routines_k1.inc:819` | **Dispatch proven. Camera effect not proven.** Per `camera-win-k1.md:9` the routine is caller-sensitive and queues action 0x16. Every live use so far ran without `with_caller`. Per `camera-win-k1.md:15` the argument is multiplied by 57.29578 twice on the way to yaw. Per `camera-win-k1.md:17`, `CSWCameraOnAStick::Message` has no yaw branch and may ignore the request. CAL shots 0007, 0008 and 0009 (angles 90, 180, 270) look nearly identical. |
| `SetFacing` (10), `SetFacingPoint` (143) | PC facing (needs a caller) | `k1.json:229`, `k1.json:2137` | Their effect on the chase camera has never been measured (`unverified`) |
| `GetFacing` (28) | reads degrees | `k1.json:437`; `camera-win-k1.md:7` | Proven. RUN step 5 used it, and CAL returned 136.474. |
| `JumpToLocation` / `ActionJumpToLocation` | moves the PC | `k1.json:4620`, `k1.json:3188` | Would move the player. Brief:9 forbids this, so it is not proposed. |
| `SetDialogPlaceableCamera` (461), `SetLockOrientationInDialog` (505), `CutsceneMove` (507) | dialog or cutscene only | `k1.json:6577`, `7109`, `7143` | Out of scope. They need a dialog or cutscene context. |
| `SWMG_SetCameraClip` (610) | minigame clip planes | `k1.json:8425` | Not for gameplay |

K2 is the same for this purpose. `SetCameraFacing` also takes one parameter there (`WT/data/routines/k2.json:1059-1068`).

Native leads that already exist in the evidence (reading only, no API):

- `CSWCameraOnAStick::Message` handles "four m_f… property commands" (`camera-win-k1.md:17`).
- `data/codecaves.toml:9077-9082` labels `CSWCameraOnAStick::Control_CheckAndUpdateCameraStyle` at `0x00638FD1` (k1_gog_103).
- The warehouse has symbol names for `Control_ComputeNewCameraPosition_006398f0`, `Control_HitCheckCamera_0063b050`, `Control_SetCameraInintalState_00638fe0` and `CSWCameraOnAStick_00639fc0` under `~/biodecompwarehouse/kotorxid/output/binaries/K1__k1_win_gog_swkotor.exe/historical/ghidra_recovered_candidates/`. These are asm-only dumps, not recovered C.
- `camera-win-k1.md:23` explicitly proposed no native API.

---

## 2. Framing arithmetic from the retained evidence

### 2a. Measurements

These come from `PREP/media-review/frame-{202,208,213,220}s.png` (1024×768, the exact game window). I decoded them in memory, classified pixels by robe and hair colour, and read the rows off by hand.

| State | Still | Head-top row | Foot/hem row | Height | Share of 768 |
|---|---|---|---|---|---|
| normal (before) | 202 s | 414 | 686 (boots), 679 (robe hem) | **272 px** | 35.4% |
| tiny 0.35 | 208 s | 588 | 667 | **79 px** | 10.3% (0.29 × normal, not 0.35) |
| giant 2.4 | 213 s | above row 0 (clipped) | 713 | ≥ 713 px visible | ≥ 92.8% |
| normal (restored) | 220 s | 414 | 683–686 | **~270 px** | 35.2% |

- **Giant widths.** At row 0 the robe or hood is 139 px wide. Rows 120–320 are 301–316 px wide, against a normal maximum of 104–109 px. That is a torso ratio of about 2.9–3.0 for a scale of 2.4, so the projection grows faster than scale because of perspective.
- **Camera.** I measured the orange door box (bright panel, R>110):

  | Still | Rows | Columns |
  |---|---|---|
  | 202 s | 138–235 | 303–403 |
  | 208 s | 139–231 | 364–463 |
  | 213 s | occluded by the giant | — |
  | 220 s | 138–230 | 487–584 |

  Rows and height are constant, so pitch and distance to the door hold within about 4%. The x position drifts +184 px in 18 s, about **10.2 px/s of yaw pan**. The review's `visual-failure.json` makes the same observation ("door and background shift horizontally").

  Setup finished at about 02:54 capture time and the scene ran at 03:22–03:40, so the pan kept going more than 30 s after setup. The time between setup and scene came from RUN step timings: `report.json` steps 6–11 sum to about 24 s.
- **Calibration run at the same PC position, chase mode 2.**
  - Shot 0006 (step 19): player about 365 → 636, **~270 px (35%)**. The view looks down the door corridor, like RUN.
  - Shot 0007 (step 22): player about 405 → 625, **~220 px (28.6%)**. The view looks across the open floor toward the lit wall.
  - The right edge of the lit-panel box moved 935 → 952 px between shots 0008 and 0009, about 207 server ticks apart, so that composition was also drifting (estimate ~6 px/s; tick-to-second rate `unverified`).

### 2b. Model and maximum giant scale at the RUN camera

Points on the player's vertical axis at heights z (in units of normal height) project to image rows through a 1D projective map: `row(z) = (a·z + b)/(c·z + 1)`. Three points fix it, and **no field-of-view assumption is needed**. I checked this: full pinhole fits at 40°, 55° and 70° vertical FOV give identical row predictions.

Assumptions:

- The camera stays fixed across phases. For tiny against normal this is supported: the door box is the same in 202, 208 and 220.
- For the giant it is `unverified`, because the door is occluded at 213.
- The ground-contact row is the hem row of the tiny body.

**3-point fit.** Inputs: ground at 670, z=0.35 at 588, z=1.0 at 414.

- Predicted top@2.0 is row **73**; top@2.4 is **−98**.
- Largest scale with top ≥ 16 px: **2.13**.
- Cross-check: this fit predicts the giant shoulder (z ≈ 0.80·2.4 = 1.92) at row 104. The shoulder was observed at about row 40, where the 296–316 px shoulder band starts. So the 3-point fit underestimates the giant.

**4-point fit.** It adds the shoulder at 1.92 → row 40 and fits a pinhole with RMS 1.8 px.

- Top@2.0 is **−2**, top@2.4 is **−251**.
- Largest scale: **1.96**.

**Sensitivity.** Moving each input by ±5 px and trying ground at 670 or 686 spreads the largest scale from 1.87 to 3.35. That range is too wide to use on its own. Keeping only fits that reproduce the observed clipping at 2.4 (top@2.4 < 0 and giant shoulder ≤ about row 72) leaves:

| Ground | Tiny shift | Normal shift | Largest scale |
|---|---|---|---|
| 670 | 0 | −5 | 2.04 |
| 670 | +5 | −5 | 1.87 |
| 670 | +5 | 0 | 1.94 |
| 670 | +5 | +5 | 2.02 |

**Estimate: at the RUN camera, the largest giant scale with a 16 px top margin is 1.87–2.04.** 2.0 is not safe there: its top row is predicted between −2 and about +30. The framing brief already says 2.0 is unproven for this composition (`task7-scale-framing-fix-brief.md:7`). This arithmetic says it probably fails.

### 2c. Camera change needed for 25–30%

Model: dolly the camera back along its current view ray. Keep the pitch and keep the look-at point. I used a pinhole at a fixed 55° vertical FOV:

- For each of the four datasets that agree with the observed clip (§2b), three points fix the fit exactly.
- The 4-point set fits with RMS 1.8 px.

I did not use the central 3-point fit, which disagrees with the observed giant shoulder.

| Dataset (ground/tiny/normal) | Top@2.0 at RUN camera | k for 30% / 27.5% / 25% | Top@2.0 at 30% / 27.5% / 26% / 25% | Top@2.4 at 27.5% / 25% | Largest share with top@2.0 ≥ 60 px |
|---|---|---|---|---|---|
| 670 / 0 / −5 | 37 | 1.16 / 1.29 / 1.44 | 93 / 125 / 144 / 156 | −12 / 37 | 32.4% (249 px) |
| 670 / +5 / −5 (worst) | −62 | 1.18 / 1.32 / 1.48 | 26 / **74** / 100 / 116 | −116 / −40 | **28.2% (217 px)** |
| 670 / +5 / 0 | −14 | 1.15 / 1.28 / 1.44 | 50 / 92 / 116 / 131 | −82 / −15 | 29.4% (226 px) |
| 670 / +5 / +5 | 29 | 1.11 / 1.24 / 1.39 | 73 / 111 / 132 / 146 | −48 / 11 | 30.8% (237 px) |
| 4-point | −2 | 1.14 / 1.27 / 1.43 | 57 / 98 / 120 / 135 | −70 / −6 | 29.8% (229 px) |

All values are estimates. The feet land near row 618 at 27.5%. Conclusions:

- For 25–30%, the camera must be about 11–48% farther from its look-at point than in RUN. For 27.5%, the multiplier is about 1.24–1.32.
- At 27.5%, 2.0 has about **74–125 px** of headroom.
- The worst consistent fit keeps ≥ 60 px only up to 28.2% (217 px). So G1 for a 2.0 giant stays at **≤ 211 px (27.5%)**, which leaves margin to that limit.
- 2.0 at 30% framing is not safe: the worst case is 26 px.
- 2.4 clips at 27.5% (−116 to −12) and is marginal at 25% (−40 to +37). It needs about 23% framing or less, so do not use it.
- The tiny phase at 27.5% is about 62–67 px tall. That is still identifiable, but check it.

The effective distance probably changes with yaw because of wall collision behind the camera: 35% vs 28.6% at the same PC position. The engine has `Control_HitCheckCamera`. Collision as the cause is `unverified`. If collision caused the RUN framing, a yaw that looks into open floor is a route-only way to reach k ≈ 1.2.

---

## 3. Proposed route changes and framing gate

The harness TOML stays the separate test-driver layer. Product Lua (`model_scene.lua`) does not change. Any camera facility belongs under `kp`, not in the harness.

I checked every verb below against the **frozen** snapshot `PREP/harness-snapshot/runtime/kpharness/`, not the worktree copy that is being edited:

- `assert_lua`, `lua`: `scenario.py:697-700`
- `screenshot = true`: `scenario.py:280-295` and `1968-1999`. It uses in-runtime `glReadPixels` to write a PPM (`shots.py:3,90`). It already produced a 1024×768 PPM under Gamescope (`RUN/shots/0001_periodic.ppm`).
- `advance_ticks`, `mark_log`: `creative_steps.py:45-72`
- `console_*`: `console_steps.py:16`

Do not reintroduce `capture_free_look`. It does not exist (`task7-scale-framing-fix-brief.md:36`).

### 3a. Scale delta (both tracks)

This follows `task7-scale-framing-fix-brief.md:56-57`. In the generator `PREP/generate-route.py`:

- Line 20: `scales={{0.35},{2.4},{task7_body.base}}` becomes `{{0.35},{2.0},{task7_body.base}}`.
- Line 25: `(2,2.4)` becomes `(2,2.0)`.

The phase-2 gate must check base 2.0 and the effective ratio together.

### 3b. Camera setup deltas

Pick exactly one track after review.

**Track N (preferred): the new `kp.camera` exists and has been reviewed (see §4).**

1. Generator line 16. Remove `q('SetCameraMode',p,2); q('SetCameraFacing',q('GetFacing',p));` from the precondition assertion, so the assertion only checks state.
2. Insert one setup step after it:
   ```python
   check('one-time camera setup: chase mode, frozen distance, native readback',
    "local q=nwscript.call; local p=q('GetFirstPC'); q('SetCameraMode',p,2); task7_cam0=assert(kp.camera.snapshot()); assert(kp.camera.set_distance(task7_cam0.distance*TASK7_K)); return true")
   ```
   `TASK7_K` is a constant frozen before launch, around 1.24–1.32, from the §2c table (27.5% row) or from a framing diagnostic. The `kp.camera` names are illustrative. The final names come from the native review.
3. Replace generator line 17 (`advance_ticks 120`) with the following. The two screenshot steps sit before the console opens and before the marker, so they are outside the cadence interval.
   - `advance_ticks 600, timeout 120`
   - `screenshot = true`
   - `advance_ticks 180`
   - `screenshot = true`
   - an assertion that the camera readback is unchanged: `kp.camera.snapshot()` distance, pitch and yaw equal to the post-settle values within tolerance
4. Add the same camera-unchanged assertion inside each phase gate (lines 25–28). Nothing in the route changes the camera after setup.
5. Restore the original camera in the final cleanup step (line 37 or 39), for example `kp.camera.restore(task7_cam_original)`, then assert the readback. After cleanup, add one `screenshot = true`, outside the interval.

**Track R (route-only, unproven): run only after a separate framing diagnostic passes.**

1. Same removal from line 16.
2. Insert:
   ```python
   check('one-time camera setup with explicit PC caller',
    "local q=nwscript.call; local p=q('GetFirstPC'); q('SetCameraMode',p,2); nwscript.with_caller(p,function() q('SetCameraFacing',TASK7_CAM_ARG) end); return true")
   ```
   - `unverified`: no retained live run shows `nwscript.with_caller` succeeding from a harness `assert_lua`. A grep of `stage-k1/runs/*/report.json` for `with_caller` finds nothing. The code raises an error without a live VM context (`WT/src/api/routines.cpp:527-529`). The diagnostic must first prove that this dispatch returns true.
   - `TASK7_CAM_ARG` comes from the diagnostic.
   - The only arithmetic candidate is `x = desiredDeg/57.29578²` (`camera-win-k1.md:15`). It is unvalidated.
   - `CSWCameraOnAStick` may ignore yaw altogether (`camera-win-k1.md:17`).
   - A diagnostic variant should compare this against `with_caller(p, SetFacing(deg))`, on the untested idea that the chase camera settles behind the PC's facing. The acceptance route may carry only the variant the diagnostic proved.
3. The settle is the same as Track N step 3, but it cannot be checked inside the route. Drift is judged only offline from the two PPMs and the master. A failure is found only after the attempt is spent. That is why the diagnostic must come first.

**Framing diagnostic for Track R.** This is a separate authorization, not acceptance media. It uses one launch, the same save, and no F12 console. It runs the same `model_scene` with 2.0 through plain `assert_lua`, plus `screenshot = true` at:

- baseline, twice, 180 ticks apart
- each phase after its assertion passes
- restored

It passes only if gates G1–G6 below pass on those PPMs. Then freeze `TASK7_CAM_ARG`.

Risk (`unverified`): a `screenshot` taken inside the cadence interval may stall the render thread for more than 50 ms. The CAL round trip was 0.168 s (`CAL/report.json` step 7). That would break the acceptance cadence gate. So the acceptance route takes screenshots only outside the interval. Phase stills come from the master after the run.

### 3c. Timing and clip

Keep `hold_ticks=60`, the 180-callback delay, timer 16 and the three physical F12 submissions. Keep generator lines 19, 22 and 36 as they are.

- Lengthen the final `advance_ticks` (line 34) to at least 240 so the restored hold is long enough.
- Choose the export interval from actual frames, as in `WT/docs/creative-runner.md:113-131`: at least 2 s of calm normal before the first change, the full tiny and giant holds, and at least 2 s restored after.

### 3d. Framing gate (checkable on retained stills and decoded master frames)

Measure the body with a **connected-component silhouette**. Seed it at the torso centre found on the baseline PPM, and grow it with a colour-distance threshold against the torso median. Do not use a global colour threshold: my simple robe classifier fired on background at rows 9 and 22 of the normal frames. Measure HUD boxes from the baseline frame. Do not assume them. In RUN they were roughly:

- minimap: x 0–128, y 0–128
- top-right icon bar: x 770–1020, y 0–35
- portraits: x 0–175, y 630–768
- quick slots: x 835–1020, y 705–768

| Gate | Check | Pass rule | RUN value |
|---|---|---|---|
| G1 baseline share | head-top to foot-bottom on the baseline still | 192–230 px (25–30%). For a 2.0 giant also require ≤ 211 px (27.5%). | 272 px (fail) |
| G2 restored matches baseline | restored height and foot row vs baseline | each within ±6 px | 270 vs 272 (pass; camera drifted) |
| G3 giant fully visible | every decoded frame of the giant hold | silhouette rows ≥ 16 and ≤ 752; no silhouette pixel in rows 0–15 of the player column band; ≥ 16 px from every measured HUD box and from companion overlap | top clipped from 211.8 to 218.0 s (`PREP/media-review/giant-frame-boundaries.json`) (fail) |
| G4 tiny readable | tiny hold | height ≥ 48 px; silhouette not hidden by geometry or companions | 79 px (pass) |
| G5 camera stable | a fixed background feature (door box or lit-panel edge), sampled at ≥ 2 Hz from calm baseline start to restored end | max displacement ≤ 4 px in x and y, no zoom (feature height within ±2 px) | +184 px in x over 18 s (fail) |
| G6 prediction sanity (before launch, from the diagnostic PPMs) | fit the §2b projective map on baseline and tiny; include the giant shoulder if visible | predicted top@2.0 ≥ 60 px | at RUN camera about −2 to 73 (fail) |

Behaviour gates are unchanged: three physical F12 receipts, native readback of 1.0 → 0.35 → 2.0 → 1.0 with identity and ratio, restored locals, and cleanup.

---

## 4. Capability gaps and the smallest closing change

| Gap | Blocks | Smallest reviewed close |
|---|---|---|
| **No camera distance or pitch control in K1.** There is no NWScript routine (§1b) and no `kp` facility (§1a). | The 25–30% requirement, unless yaw alone happens to work (Track R, unproven) | **Step 1, read-only `kp.camera.snapshot()`.** It returns the active camera's behaviour identity, distance, pitch, yaw and height, found through `CSWCameraOnAStick` state (leads: `camera-win-k1.md:17`, `codecaves.toml:9077-9082`, warehouse `Control_ComputeNewCameraPosition_006398f0`). Use checked addresses in `data/addresses/k1_gog_103.json` and a signature guard like `model_backend`. Unsupported builds fail closed. This alone gives an in-route stability gate (G5 inside the route) and a native framing receipt. **Step 2, a checked `kp.camera.set_distance(d)` plus `restore(snapshot)`.** It verifies the active behaviour is OnAStick, clamps to a reviewed range, reads back the value, and restores exactly. Use distinct `kp` names and never wrap NWScript. This is a new native change. It needs RE of the field offsets, unit tests and one live diagnostic before any acceptance use. |
| `SetCameraFacing` yaw semantics and caller dependence unresolved (`camera-win-k1.md:9,15,17`) | Track R | A framing diagnostic that uses `with_caller` and the candidate arithmetic, and compares the `SetFacing` variant. No code change. |
| No in-route camera readback, so drift is only found after the attempt | Any single-attempt policy | Covered by step 1 above |
| Game `camerastyle.2da` override in the private stage (distance, pitch, height, view-angle columns) | An alternative to native code | `unverified`: column meanings and area binding are not in the evidence. It would also change the staged inputs, which are hash-bound. Only consider it after a reviewed decode of the 2DA and the `.are` CameraStyle binding. |
| Whether the chase camera re-targets when the model scales | Precision of §2b/§2c | Answered by the step-1 snapshot during the diagnostic's phases. Until then, keep the giant at 2.0 and require G1 ≤ 27.5%. |

---

## 5. Claim blocks

```
claim: K1 exposes no camera distance or pitch control, in kp.* or in NWScript.
referent: data/routines/k1.json:724-735 (SetCameraFacing, 1 float param); src/generated/routines_k1.inc:819,1277; grep -rniI camera WT/src WT/include finds only generated routine tables; kp registrations at model_lua.cpp:100, entity.cpp:430-462, timers.cpp:334
checked: grep and read in WT
verdict: holds
confidence: high; a kp.camera commit or a K1 routine with distance params would change it
```
```
claim: SetCameraMode(p,2) changes the view live, but SetCameraFacing has no proven camera effect.
referent: CAL shots 0002 (mode 0) vs 0006 (mode 2); CAL 0007/0008/0009 (angles 90/180/270) nearly the same view; camera-win-k1.md:9,15,17; no live run used with_caller with SetCameraFacing (grep of kp-live-20260922)
checked: viewed the PNGs; grep
verdict: holds
confidence: medium; the 0006→0007 yaw change could be drift or a one-time facing effect
```
```
claim: RUN normal player = 272 px (35.4%); tiny = 79 px; giant visible from row 0 to 713.
referent: PREP/media-review/frame-202s.png, frame-208s.png, frame-213s.png, frame-220s.png, decoded in memory
checked: pure-Python PNG decode with colour-class row scans
verdict: holds
confidence: medium (±5 px for the hair edge); a silhouette-segmentation pass would tighten it
```
```
claim: RUN camera panned about 10 px/s at fixed pitch and distance through the scene.
referent: door box rows 138-235 / 139-231 / 138-230 and columns 303 / 364 / 487 at 202 / 208 / 220 s
checked: decoded the PNGs; also visual-failure.json "camera_stability: not_passed"
verdict: holds
confidence: high for the pan; the cause is unverified
```
```
claim: at the RUN camera the largest giant scale with a 16 px top margin is 1.87-2.04, so 2.0 likely clips.
referent: §2b projective fits (3-point 2.13, 4-point 1.96, fits consistent with the observed 2.4 clip 1.87-2.04)
checked: computed here; FOV-invariant
verdict: holds as an estimate
confidence: medium; a live 2.0 still at this camera, or proof the camera re-targets with scale, would change it
```
```
claim: 25-30% normal height needs about 1.11-1.48x camera distance; at 27.5%, 2.0 has 74-125 px headroom (worst consistent fit keeps >= 60 px up to 28.2%) and 2.4 does not fit.
referent: §2c table (four clip-consistent 3-point datasets plus the 4-point fit, pinhole at 55 deg)
checked: computed here (dolly along the view ray, fixed pitch)
verdict: holds as an estimate
confidence: low-medium; KOTOR may change pitch and height with distance (camerastyle), and collision may cap the distance
```
```
claim: the review's "2.40 would occupy 456-552 px" is too low.
referent: task7-k1-scale-run-review.md:53 (linear 2.4x); §2c: 2.4 top row is -116 to -12 at 27.5% with feet near 618, so projected height exceeds 630 px; RUN torso width ratio 2.9-3.0 at scale 2.4
checked: computed and measured here
verdict: holds
confidence: medium-high
```
```
claim: the same PC position gives about 28.6% at another chase yaw.
referent: CAL shot 0007_step22.png player about 405 to 625 (220 px); 0006_step19.png about 365 to 636 (~270 px); same pc (105.7,96.5,1.0) in CAL report step 2 and RUN report step 2
checked: decoded the PNGs
verdict: holds
confidence: medium; that view was also drifting (lit-panel edge 935 to 952 between 0008 and 0009); collision as the cause is unverified
```
```
claim: runtime screenshot steps work under the frozen Gamescope harness.
referent: PREP/harness-snapshot/runtime/kpharness/scenario.py:280-295,1968-1999; shots.py:3,90; RUN/shots/0001_periodic.ppm (P6 1024x768)
checked: read the code; looked at the PPM header
verdict: holds for a periodic shot; a route-step shot inside a Gamescope run is unverified
confidence: medium
```

## 6. Open items (`unverified`)

- What K1 camera mode 2 means; whether chase yaw settles behind PC facing; whether effective distance comes from collision.
- Whether the camera re-targets when the model scales. This matters for the giant only; tiny vs normal showed a stable door box.
- Whether a mid-interval `screenshot` stalls rendering by more than 50 ms.
- `camerastyle.2da` column meanings and area binding.
- The exact server tick rate. RUN step 6 took 12.5 s for 120 ticks and step 18 took 5.7 s, so ticks are not wall time.

# Review: K1 scale attempt-2 prep (spec, then adversarial)

Reviewed 2026-09-27. Read-only. No Wine, game, Gamescope or FFmpeg. I did not touch the live-game lock, the prep directory or the worktree.

- PREP = `/home/brunner56/kp-live-20260922/next-k1-preparations/20260927-task7-scale-attempt2`
- WT = `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`
- FAILED = `/home/brunner56/kp-live-20260922/next-k1-preparations/20260927-task7-scale-102038-74cb804b`
- Scratch = `/home/brunner56/kp-live-20260922/review-probes-k1-scale2/`

The prep directory is unchanged. `sha256sum *` before and after the review diffs empty (`prep-before.sha`).

I read the route, the scene Lua and the fit script and formed a view before I opened `prep-report.md`.

## Verdict in one paragraph

The route, the scene script, the marker plan and the scale choice are careful and mostly correct. `validate.py` and `framing-fit.py` reproduce exactly. I found three problems:

1. **F1 (blocking).** The single-launch precondition `KP_MAX_BOOT_ATTEMPTS=1` is missing. The harness default allows up to 5 launches.
2. **F2.** The report says a failed route-step screenshot stops the run. That is false: the step still passes.
3. **F3.** Nothing in V1 makes the camera farther. The report explains why. But V1 is still offered as the acceptance attempt, and the governing review and framing plan say that is not allowed without a framing diagnostic first. The L1 diagnostic is only a recommendation in the report. It has to be a blocking precondition.

F1 and F3 are about preconditions, not route code. Each needs a few lines added to the report.

## Directive checklist

| Directive element | V1 status | Referent |
|---|---|---|
| calm normal → tiny → giant → restored normal | holds | scene `scales={{0.35},{1.9},{body.base}}` (`task7s2_scale.lua:171-172`). Lead ≥120 callbacks and ≥3 os.time s. Lead-out ≥120 callbacks and ≥3 s (`:39-41`, `:120,129,145`). |
| Three physical F12 submissions, exact outcome correlation | holds | V1 has 3 `console_command` steps (validate: `physical_console_commands=3`). Each has `expect_values=[Boolean true]` and `return_count=1`. Correlation is harness-side through `kp.console.v1` (`WT/scripts/harness/kpharness/physical_console.py:1,111,127`). The failed run proved it live: runtime `17c8…`, session 1, requests 1/2/3, sequences 2/3, 4/5, 6/7 (run review, Important 3). |
| Independent native readback of every phase and of restoration | holds | V1 phase polls read `kp.model.snapshot` base, effective ratio, id, model and creature (steps 23-26). After cleanup it checks locals 5-9 and scale again. The harness Lua does not reuse scene code. |
| Farther, settled, stable chase camera; normal = 25-30% (192-230 px) | **not met by construction**. The report records why (no distance knob). See F3. | Report §4a/§4b. FP §0.4-0.6: "The current route cannot meet the 25–30% requirement at any giant scale." |
| Full body visible at giant | holds **only if** the settled view is ≤ about 230 px | Re-derived, see Grill 4. At the failed-run camera, 1.9 leaves 1.6 px of headroom on the worst fit. That fails G3. |
| 60 FPS exact-window master | listed as prerequisite 4, with the cadence window `calm_start..calm_end` | `launcher-args.json`. validate: `cadence=calm_start..calm_end`. creative-runner.md:625 (`gamescope-cadence-v1`, 60 FPS, 99%). |
| Explicit reviewed clip bounds covering lead-in, phases, restoration, lead-out | procedure holds; the bounds themselves are post-run by design | Report §2 "Choosing reviewed clip bounds later". It matches creative-runner.md:185-189 (≥2 s before and after, frame-reviewed). All 7 capture markers are named and ordered (recorder `observe()`: `order=ordered duplicates=[]`). |
| Reject if body cut, camera disorienting, restoration omitted or cadence fails | holds as offline gates G1-G6 plus cadence | Report §4d. See F2 for the stills dependency. |
| Lua uses kp.* and nwscript.call only | holds | validate: "no bare routine names" across 39 chunks. The route aliases `local q=nwscript.call`. The scene wraps it as `call(name, …)` (`:55`). |
| Screenshots outside the cadence window | holds (placement) | Stills A and B come before `console_open` (steps 11, 13). Still C comes after `calm_end` (step 39). `shot_interval=0` disables periodic shots (scenario-toml.md:56; `shots.py` `maybe()` returns when `interval<=0`). |
| Needs a kp.camera build; fails early otherwise | holds | Step 5 raises `kp.camera missing: wrong build` before any F12 (SIM negative). Prerequisite 1 also greps the DLL. |
| Single launch (`KP_MAX_BOOT_ATTEMPTS=1`) listed | **does not hold** (F1) | `grep -rn BOOT_ATTEMPTS PREP` returns nothing. |
| Fresh harness snapshot listed | holds | Prerequisite 3. |

## Findings

### F1: the single-launch precondition is missing (blocking)

```
claim (implicit): the launch "as in the failed prep launch-once.json" is one launch.
referent: WT/scripts/harness/kpharness/session.py:74 `BOOT_ATTEMPTS = 5`; :76-79 "KP_MAX_BOOT_ATTEMPTS … down to 1 = exactly one game launch with no relaunch". FAILED/launch-once.json has no env entry for it. `grep -rn "BOOT_ATTEMPTS" PREP` returns 0 lines.
checked: the grep above, and session.py:70-120 read
verdict: does not hold
confidence: high. It would change only if the orchestrator's launch wrapper sets the variable, or the runner passes `max_boot_attempts=`. `grep -rn max_boot_attempts WT/scripts/harness/kpharness/creative*.py gamescope*.py` returns nothing, so the runner does not force it.
```

Fix: add to §0 "set `KP_MAX_BOOT_ATTEMPTS=1` in the driver environment". Then check that the run's `boot-attempts.json` records `source=env` and 1 attempt.

### F2: a failed route-step screenshot does not stop the run

```
claim: "Route-step screenshots under Gamescope have never run … If one fails, step 11 stops the run, before any F12." (prep-report §8)
referent: WT/scripts/harness/kpharness/scenario.py:1975-1977. `path = self.shooter.take(...) if self.shooter else None`, `detail = … "no screenshot taken"`, then a StepResult with status "ok". shots.py `take()` returns None on ChannelError or a missing file ("a bad frame must not fail a run").
checked: code read
verdict: does not hold
confidence: high
```

Impact: stills A, B and C can go missing without any error. G1, G2 and G5 (A vs B, A vs C) would then have no inputs. Only a stall of up to 30 s (`channel.screenshot(timeout=30)`) would show up, and it lands outside the window.

Fix, pick one:

- Add an offline precondition that `shots/000N_framing_still_*.png` exist before review, with a fallback to master frames at the same capture times.
- Or state that G1 and G2 use master frames.

This is not blocking for launch, but the report's claim must be corrected.

### F3: V1 is the acceptance attempt, but nothing makes the camera farther

V1's only farther-camera mechanism is to wait (600 ticks plus a 20 s anchor) and hope the settled view is about 220 px, as in CAL 0007, and not about 272 px as in RUN.

- FP §2a says CAL 0007 looked in a **different direction**: across the open floor, not down the door corridor. So the 220 px came from a different yaw, and possibly collision, not from settling. The report's Grill 3 marks this as `unverified`.
- The failed-run review, condition 3 (`task7-k1-scale-run-review.md`): "If that cannot be established without live calibration, authorize one bounded framing run rather than calling it acceptance."
- FP §0.6(b): a route-only candidate must first pass "a separate, bounded framing diagnostic. This is not the acceptance run."

The report does record why V1 cannot set distance, so the checklist item "explicitly records why not" is met. But it leaves L1 as "the orchestrator's decision". Given those two governing documents, L1 (or an equivalent framing diagnostic that measures the settled view at ≤230 px) must be a **blocking** prerequisite before V1 counts as the acceptance attempt.

```
claim: "Whether the one L1 diagnostic from CP §2h runs first is the orchestrator's decision."
referent: task7-k1-scale-run-review.md condition 3; FP §0.6(b); FP §2a CAL 0006 vs 0007 view direction
checked: files read
verdict: does not hold as a non-blocking recommendation
confidence: high on the precondition. It would change only if the user explicitly accepts spending the acceptance attempt as the framing diagnostic.
```

### Minor

- **M1.** Report §4b says the 16 px-margin maximum at the RUN camera is "1.868-2.089 across fits". The file `framing-fit-output.json` gives `run_max_scale_16px` 1.876-2.046. The conclusion does not change. The quoted range has no referent. Mark it `unverified` or correct it.
- **M2.** The quaternion sign-flip false positive and the `dolly≠0` distance recompute can both stop settle before F12. Both fail closed and are already recorded in §8.
- **M3.** Phase holds have no wall-clock floor. The FAILED timing is 124 server ticks in 12.5 s (report.json step 6), and the review measured about 11 timer callbacks per second. So a 60-callback hold is about 5.5 s. A route poll iteration is about 0.12 s of Lua plus a 0.3 s sleep (`scenario.py:713,732`), so a phase cannot be missed at that rate. If the timer pump ever reaches about 60 per second, a hold is about 1 s. The route should still catch it (about 2 polls per hold), but a 1 s giant hold is thin for review. This is recorded in §8, and I am not raising it further.

## Grill answers, attacked weakest first

**1. Can the in-route camera gate be trusted when the raw fields' meaning is unverified?** Their answer: it detects motion, it does not prove stillness, and G5 is authoritative.

I checked it against the failed run's pan. I re-derived it from the retained stills with pure-zlib decoding (`scratch/doorbox.py`, orange-panel median x):

| Still | Median x | Rows |
|---|---|---|
| 202 s | 352 | 114-243 |
| 208 s | 412 | 113-237 |
| 220 s | 534 | 122-231 |

That is about 10 px/s of yaw with constant rows. It matches FP §2a.

- **G5** (≤ 4 px at ≥ 2 Hz) catches it within one 0.5 s sample (about 5 px).
- **The in-route gate.** If `raw_28` is orientation, 10 px/s ≈ 0.0136 rad/s, and a component moves at most about δ/2. That crosses 1e-3 in about 0.15-0.3 s. If `raw_38` is position, about 0.085 units/s crosses 0.01 in about 0.12 s. The settle step needs ≥ 20 s inside tolerance of one anchor, so this pan would stop the run at step 8, before any F12.
- `t7_stable` runs on every poll iteration of steps 23-26, not only once per gate. The scene watch covers each callback from `calm_start` to `calm_end`.
- I cannot replay the raw fields: FAILED's DLL lacks kp.camera (report §0.1, `grep -a -c` = 0).

That holds, conditional on the raw-field meaning. G5 is the backstop and it catches this pan by more than 40×.

**2. Why not run L1 first?** They defer to the orchestrator. This does not hold as a deferral; see F3. It must be blocking.

**3. Why would waiting longer give a farther view?** They mark it `unverified`, correctly. The CAL 0006 → 0007 change also swapped the view direction (FP §2a), so this is at least as likely yaw or collision as settling. The honest status is `unverified`. The consequence is F3.

**4. Why 1.9 and not 2.0?** I re-ran `framing-fit.py`: byte-identical at 55°, and FOV-invariant at 40°. My own pass computed the top row at 1.9 after dollying to a given normal model height:

| Model px | Worst-fit top@1.9 | Best-fit top@1.9 |
|---|---|---|
| 192 | 150.8 | 183.4 |
| 230 | 75.7 | 129.8 |
| RUN camera (≈256) | 1.6 | 81.1 |

- Tiny at 0.35 is 59.7-73.3 px, which is ≥ 48 (G4).
- The feet row is 593-645, well above 752.

So 1.9 holds with ≥ 60 px headroom across the 25-30% band, and fails G3 (16 px margin) at the RUN view on the worst fit. That holds. It also shows why F3 matters: 1.9 is safe only if the view actually lands in the band.

**5. Does `calm_start` come after the console is closed?** Checked three ways:

- `CALM_CALLBACKS=180` and `CALM_SECONDS=4` (`task7s2_scale.lua:39,120`). At about 11 callbacks per second that is about 16 s.
- FAILED's console close took 0.23 s (report.json step 11).
- creative-runner.md:319-320 says a zero-minimum `await_log` is a snapshot, "not a timed proof of silence", so step 21 does not wait for its timeout.

That holds.

### My own questions the writer missed

- **Do harness-state globals persist from step 5 to later steps?** V1's settle, baseline and phase gates call `t7_cam`, `t7_camdev` and `t7_stable`, and read `T7`, `t7_cam0` and `t7_original`. All of these are defined in step 5. If they did not persist, step 8 would raise before any F12 and burn the launch. Live referent: FAILED route line 30, a harness `assert_lua`, sets `task7_original`, `task7_module`, `task7_area` and `task7_locals`. Line 138, a later harness `assert_lua`, reads all four, and FAILED `report.json` step 22 passed ("assert_lua == true"). That holds.
- **Does the timer find `_G.task7s2_tick` when the failed run used a bare global?** `timers.cpp:132` calls `lua_getglobal` on the owner state, and that lookup is non-raw. `WT/src` has no `setfenv` or `lua_setfenv`. Either way the name resolves. That holds.
- **Do `$`-anchored markers survive Windows line endings?** `grep -c $'\r' FAILED/runs/.../kotorphasor.log` gives 0. That holds.
- **Does `shot_interval=0` disable periodic shots or fire them constantly?** It disables them (`shots.py` `maybe()`: `if self.interval <= 0: return None`). That holds.

## Reruns

- `python3 -I -S -B validate.py` ran on a scratch copy, because the script writes into its own directory. Exit 0. `validation-output.txt` is identical to PREP's after the hash header (only the paths differ). Results:
  - V1 loads with 46 steps and 3 physical commands.
  - V2 is rejected.
  - 39 chunks compile.
  - The name scan is clean.
  - SIM nominal passes at 10 and 60 ticks per second.
  - All three negatives fail where the report says: step 25, step 5 and step 8.
- `python3 -I -S -B framing-fit.py` output is byte-identical to `framing-fit-output.json` (`cmp` prints nothing). 40° gives the same rows.

## Claim blocks

```
claim: V1 loads, has 3 physical F12 submissions, and its Lua compiles and scans clean.
referent: scratch/copy/validation-output.txt (rerun, exit 0)
checked: python3 -I -S -B validate.py
verdict: holds
confidence: high (offline only)
```
```
claim: 1.9 keeps ≥60 px of headroom up to 230 px model height on every clip-consistent fit.
referent: worst-fit top@1.9 = 75.7 px at 230 px; 1.6 px at the RUN camera
checked: framing-fit.py functions, my loop (see Grill 4)
verdict: holds in the band; fails at the RUN view
confidence: medium (calibrated on the RUN view only)
```
```
claim: the stability gates would catch the failed run's lateral pan.
referent: door box median x 352→412→534 at 202/208/220 s (scratch/doorbox.py)
checked: pure-zlib decode of FAILED/media-review stills
verdict: holds for G5; holds for the in-route gates only if raw_28/raw_38 mean orientation/position
confidence: high (G5), low-medium (in-route) until L1
```
```
claim: the prep lists all launch preconditions.
referent: session.py:74 BOOT_ATTEMPTS=5; no KP_MAX_BOOT_ATTEMPTS in PREP
checked: grep
verdict: does not hold
confidence: high
```

## Required before PASS

1. Add `KP_MAX_BOOT_ATTEMPTS=1` to §0 as a launch precondition (F1).
2. Make L1, or any bounded framing diagnostic showing the settled view at ≤ 230 px measured, a **blocking** prerequisite for V1 as the acceptance attempt. Or get the user's explicit waiver (F3).
3. Correct the §8 screenshot claim and add a stills-present or master-fallback rule for G1, G2 and G5 (F2).
4. Optional: fix the M1 range.

**Question I could not settle:** is the settled mode-2 chase view at this spot ≤ 230 px, and do `raw_28` and `raw_38` move with the view? One check settles both: CP §2h L1. Take two kp.camera snapshots 180 ticks apart, each with a still, on a kp.camera build, as a non-acceptance launch.

K1 scale attempt-2 prep verdict: FAIL

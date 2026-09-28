# Review: K1 scale attempt-2 prep, round 2 (spec, then adversarial)

Reviewed 2026-09-27. Read-only against PREP and WT. No Wine, game, Gamescope or FFmpeg. Did not touch the live-game lock. No git writes. All probes ran on a scratch copy under `/home/brunner56/kp-live-20260922/review-probes-k1prep-r2/copy/`, with `TMPDIR` exported under the same probe dir.

- PREP = `/home/brunner56/kp-live-20260922/next-k1-preparations/20260927-task7-scale-attempt2` (`prep-report.md` sha256 `949657b0fda68096d1d6a1137d0550f0f0111ac0fbea592ec5e973f948d5232e`, matching the orchestrator's cited hash)
- WT = `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation` (read-only reference)
- Prior review = `/home/brunner56/kp-live-20260922/k1-scale-attempt2-prep-review.md` (FAIL: F1, F2, F3, M1)
- Scratch = `/home/brunner56/kp-live-20260922/review-probes-k1prep-r2/`

PREP directory mtimes are unchanged after this review (all files last modified 2026-09-27, before this session; no write tool ever targeted PREP or WT in this session).

I read `prep-report.md` in full, formed a view of whether F1/F2/F3/M1 actually landed, then read its "Grill me" section.

## Verdict in one paragraph

All four required fixes landed and each one I could independently re-derive holds: `KP_MAX_BOOT_ATTEMPTS=1` is now a documented and (for F1/F2) code-enforced precondition, a missing/empty/wrong-size/wrong-label still now fails the run through a real `postrun-gate.py`, the M1 range is now sourced from `framing-fit-output.json` and reproduces exactly, and a concrete, well-built L1 camera diagnostic (`l1-camera-diagnostic.toml`, 47 steps) now exists and is declared blocking. I reran `validate.py`, `framing-fit.py`, and `postrun-gate.py` from scratch, and additionally re-derived the 76-chunk count and the NWScript-name scan independently through the WT `Scenario` loader (not the prep's own `validate.py` code), and all match. I also constructed several adversarial fixtures beyond the ones `validate.py` already carries (wrong-label still, missing `boot-attempts.json`) and the gate caught all of them.

I found one **Important**, not-blocking gap: F3's "BLOCKING" status is enforced only by prose and orchestrator discipline, not by any script in this directory. I built a synthetic V1 run directory containing zero trace that L1 ever happened, and `postrun-gate.py` on that directory prints `PASS`. Nothing here would stop an operator (or a future, less careful invocation) from launching V1 without ever running L1. This does not undermine the L1 diagnostic itself, which is well designed, faithful to CP §2h, and its own admission rule (A1-A6) is sound — it just means the "blocking" word describes a step in a checklist that a human/orchestrator must follow, not a gate a machine enforces. Everything else checks out.

## Directive re-check (orchestrator's rulings)

| Ruling element | Status | Referent |
|---|---|---|
| F1: `KP_MAX_BOOT_ATTEMPTS=1` mandatory | holds | `prep-report.md` §0 P3, item 6; `l1-launcher-args.json` `"env":{"KP_MAX_BOOT_ATTEMPTS":"1"}` |
| F1: fresh harness snapshot containing it (grep ≥1) | holds | §0 item 6: `grep -c KP_MAX_BOOT_ATTEMPTS session.py` = 4 on current WT (re-verified this pass, same count) |
| F1: post-run `boot-attempts.json` check (max 1, launch_count 1) | holds, executable | `postrun-gate.py` lines 33-38; re-derived independently below |
| F2: a missing still fails the run | holds, executable | `postrun-gate.py` lines 54-69; re-derived independently below (missing, empty, wrong-size, wrong-label all tested) |
| F3: L1 camera diagnostic is a blocking precondition, matching CP §2h | **design holds; enforcement is prose-only** | see Finding I1 below |
| F3: same save/spot, `SetCameraMode(p,2)`, settle, two `kp.camera.snapshot()` 180 ticks apart, each with a still outside any cadence window | holds | `generate-l1.py` `build()`; `l1-camera-diagnostic.toml` steps 7-13, 27-33; sim output `cadence=None..None` |
| F3: raw fields logged | holds | §5b `a`-`f` receipts (`behavior`, `dolly`, `raw_28/38/50_unverified`, PC pose); `validate.py` SIM L1 nominal prints `R1a...R1f` |
| F3: on-screen height measurement instructions | holds | §5b "Offline checks" item 3 (silhouette-growth procedure, seed/threshold/rows recording) |
| F3: fail early if kp.camera absent | holds | L1 step 5 = V1 step 5 code, byte-identical (`generate-l1.py:23`); SIM negative fails at step 5 with `kp.camera missing: wrong build` |
| F3: one launch | holds | `l1-launcher-args.json` env + no `--dev-max-boot-attempts` (`validate.py:385` asserts this) |
| §4b range 1.876-2.046 | holds | `framing-fit-output.json` `run_max_scale_16px`; reproduced bit-identical via `framing-fit.py` |
| L1 route loads with WT harness loader (steps=47) | holds, re-derived independently | direct `Scenario.load('l1-camera-diagnostic.toml')` via WT's own `kpharness.scenario` → 47 steps |
| Lua uses only `kp.*` + `nwscript.call`, no bare NWScript names | holds, re-derived independently | see "Independent NWScript scan" below |
| 76-chunk count | holds, re-derived independently | direct count via WT `Scenario` objects: 1 (scene) + 18 (V1 code steps) + 20 (V2 raw code entries) + 36 (L1 code steps) + 1 (probe) = 76 |
| Nothing claims live/visual proof | holds | grep for "observed/confirmed live/verified live/on screen" across `prep-report.md` returns only one hit, itself marked "Unverified live" |

## Independent re-derivations (this pass, not trusting the prep's own scripts alone)

**76-chunk count**, loading V1 and L1 through WT's `Scenario` class directly (not `validate.py`'s counting code):

```
v1 steps 46, v1 code-bearing 18
l1 steps 47, l1 code-bearing 36
v2 raw code entries 20
1 + 18 + 20 + 36 + 1 = 76
```

**NWScript-name scan**, independently reimplementing the strip-then-scan against `WT/data/routines/k1.json`'s 772 names, run only on `l1-camera-diagnostic.toml`'s code steps plus `l1_camera_probe.lua` (the two files r2 actually added):

```
capitalized identifier tokens present before stripping sanctioned call forms:
  GetArea, GetFacing, GetFirstPC, GetIsDead, GetIsInCombat, GetIsInConversation,
  GetIsObjectValid, GetLocalNumber, GetModuleFileName, GetPosition, SetCameraMode
post-strip bare routine-name hits: []
```
All of those names appear only as quoted string arguments to `nwscript.call(`/`q(`. None survive the strip, so none are bare NWScript calls in Lua.

**`postrun-gate.py`**, reruns plus two adversarial fixtures the prep's own `validate.py` did not carry:

- `python3 -I -S -B validate.py` on the scratch copy: exit 0, output identical in content to `validation-output.txt` (same claims, same step numbers, same PASS/FAIL fixture list).
- `python3 -I -S -B framing-fit.py`: byte-identical to `framing-fit-output.json` (`cmp` silent). `run_max_scale_16px` min/max = `1.876 2.046`, matching M1's corrected claim exactly.
- Adversarial fixture: still-step report entry present, file present, right size, but **label mismatched** (simulating a renamed/misattributed still) → gate correctly reports `step 11 label 'WRONG LABEL HERE' != 'framing still A: ...'` and FAILs.
- Adversarial fixture: `boot-attempts.json` **absent entirely** (not just wrong values) → gate correctly FAILs with `boot-attempts.json unreadable: [Errno 2] No such file or directory`.
- Confirmed real V1/L1 TOMLs give every screenshot step an explicit `label=` (so the fixture-vs-gate default-string mismatch inside `validate.py`'s own test harness, `'x'` vs `'screenshot'`, is never exercised on the real routes — not a live bug, just noted for completeness).
- Confirmed `session.py:1493-1494` really does write `outcome: "channel"` on a normal successful launch, so `postrun-gate.py`'s literal `outcome != 'channel'` check is checking a real, not invented, field.
- Confirmed `creative.py:150-171`'s `boot_budget()` always resolves to `budget_source='default_single'` on the *current* WT build regardless of whether `KP_MAX_BOOT_ATTEMPTS` was set (an explicit kwarg of `1` always wins per `session.py:104`), which is exactly why the report's Grill answer 3 is right that gating on `max_boot_attempts_source=='env'` would fail every correct run, and why the env precondition has to be proven through the separate `env` field instead (`creative.py:163`, `os.environ.get(...)`). This also means: on the current WT build, forgetting the env var doesn't currently change actual launch behavior (default is already 1 attempt) — the mandatory-env-var rule is pure insurance against a different `$SNAP`, exactly as the report says, and `postrun-gate.py`'s `env` check is what actually enforces the operator sets it regardless.
- Confirmed WT is still moving: `creative.py` sha256 this pass = `f160f81f0acdab15b8815aa12395fd47db5c0879ce86fb428dcf69e9c4e29ee6`, matching the report's own "moved again" re-verification exactly, and `git status --porcelain` in WT shows dozens of modified files, corroborating "other writers are active."

## Finding I1 (Important, not blocking): F3's "blocking" is prose, not code

```
claim: L1 is a BLOCKING precondition for V1 to count as the acceptance attempt.
referent: prep-report.md §0 P5 ("This is BLOCKING, not optional"); §5b admission rule A1-A6.
checked: constructed a synthetic V1 run directory (report.json, boot-attempts.json,
  creative-run.json, three correctly-sized/labelled stills) containing no reference
  to any L1 run, anywhere. Ran postrun-gate.py --route task7s2-v1-readonly-camera.toml
  --run-dir <that directory>.
result: verdict PASS.
verdict: the blocking rule does not hold as an executable gate. It holds only if a
  human or orchestrator reads §5b and refuses to authorize the V1 launch without a
  prior passing L1 run — nothing in postrun-gate.py, validate.py, or the route TOMLs
  themselves checks for L1's existence or its admission rule (A1-A6) before accepting
  a V1 run as PASS.
confidence: high. This is different in kind from F1: F1 has an actual runtime
  enforcement path (session.py's boot-attempt loop) in addition to the offline check,
  so a violating run is either impossible or self-reports as impossible. F3 has no
  runtime enforcement path at all — L1 and V1 are two independent launches, and
  nothing here ties them together mechanically.
```

This does not roll back F3 to "not fixed" — the diagnostic itself, the admission rule, and its faithfulness to CP §2h are all sound (see re-derivations above), and the report is honest that "the orchestrator runs these [checks]" (§5b) rather than claiming automation it doesn't have. But given the review brief's explicit instruction to check that "every ruling is actually enforced by something executable," this is worth surfacing and fixing before this is treated as unconditionally safe against operator error.

**Suggested fix** (optional, not required for this verdict): add a `--require-l1 <l1-run-dir>` flag to `postrun-gate.py` that, when given, re-evaluates A1-A6 from L1's own `report.json`/stills and refuses PASS on the V1 run unless L1's admission rule holds. Cheap because A1-A6's inputs (heights, deltas, `report.json` entries) are already all offline-readable.

## Grill answers, attacked weakest first

**1. (Weakest) Will the §5b admission thresholds actually be met, or does L1 just move the failure one launch earlier?** Their answer: `unverified`, and that's the intended outcome (spend a non-acceptance launch instead of the acceptance attempt).

That holds. I have no live evidence either way, and the honest `unverified` tag is correct — CAL 0006/0007 give 272 px and ~220 px respectively at two different view directions (FP §2a, unchanged since round 1), so the true settled height at this exact spot and yaw is still an open question that only L1's live run answers. No referent contradicts this.

**2. Can a route step really not check that a still exists?** Their answer: no, `scenario.py:1968-1985` always returns `"ok"`.

I re-read those lines directly (unchanged from round 1's F2 finding) and confirm: `Shooter.take` returning `None` still produces a `StepResult` with `status="ok"` and `detail="no screenshot taken"`. That holds, and it's exactly why `postrun-gate.py` has to exist as an offline gate rather than a route step.

**3. Why not gate `max_boot_attempts_source == "env"`?** Their answer: the kwarg always wins on this build (`default_single`), so gating on `source=='env'` would fail every correct run; the env precondition is instead proven through the `env` field.

I re-derived this myself from `creative.py:150-171` and `session.py:101-125` (see "Independent re-derivations" above): `boot_budget()` unconditionally calls `resolve_max_boot_attempts(1)` when no dev override is given, and an explicit kwarg always wins over the env var per `resolve_max_boot_attempts`'s own docstring and logic. So `budget_source` is always `'default_single'`, never `'env'`, no matter what the operator sets. That holds exactly as claimed.

**4. Does the L1 settle rehearsal test exactly what V1 will run?** Their answer: yes for the code (byte-identity asserted for steps 5, 6, 8, 9, 14), not for the timing (L1's settle starts later after mode 2 than V1's would, because of the R1/R2 pair in between).

I re-verified the byte-identity independently by loading both TOMLs through WT's own `Scenario` class and comparing `raw['code']` at the claimed step-index mapping (5→5, 6→7, 8→27, 9→28, 14→47): all five pairs matched exactly, matching both `generate-l1.py`'s module-level asserts and `validate.py`'s check 7. That holds. The timing caveat is correctly marked `unverified` — V1 has its own 300 s settle budget regardless, so this is a soft risk, not a hard gap.

**5. Do the receipts survive report.json truncation?** Their answer: yes in simulation (worst case 136 chars, cut is ~200 including a 20-char prefix; nominal receipts are 77 chars).

Confirmed via my own rerun of `validate.py`'s SIM L1 huge-values case: `all 15 R1/R2 receipts... longest 136 chars (limit 150)`. That holds for the simulated cases; the live value-type risk (e.g. `dolly` being garbage) is correctly flagged as separately `unverified`.

**6. Is the 76-chunk split verified, not just quoted?** Their answer: yes, `validate.py:117-128`, plus an independent recount matching `1 + 18 + 20 + 36 + 1 = 76`.

I redid this recount completely independently (their own recount used their own harness-loading helpers; I loaded both TOMLs via WT's `Scenario` class with no shared code with `validate.py`) and got the identical breakdown: v1 code-bearing=18, l1 code-bearing=36, v2 raw code entries=20. That holds, twice over now.

### My own grill questions the writer didn't ask

- **Does `postrun-gate.py` catch a still that exists, is the right size, but was silently mislabeled in `report.json` (e.g., due to a step-numbering drift after a future route edit)?** Yes — I constructed this fixture (see "Independent re-derivations") and the gate correctly fails on the label mismatch, not just on missing/empty/wrong-size files. That's stronger than the round-1 F2 finding demanded.
- **Does anything mechanically stop V1 from running without L1 ever having happened?** No — see Finding I1. This is the one real gap this round.
- **Is `doorbox.py`, referenced in §5b item 4 by hash, actually present and does the hash match?** Yes: `sha256sum /home/brunner56/kp-live-20260922/review-probes-k1-scale2/doorbox.py` = `a8ec2c9d5b35d88ec7233fd0c6fe809c312b1b8074c5cfae10770f14fce8fc6c`, matching the report's citation exactly.

## Minor

- **M2 (carried from round 1, unchanged, not re-raised as blocking).** Quaternion sign-flip false positives and `dolly≠0` recompute risk are still recorded in §8 as before; nothing new here.
- The `validate.py` postrun-gate test harness's own fixture builder defaults an unlabelled step to `'x'` while `postrun-gate.py` itself defaults to `'screenshot'` — a latent inconsistency between the *test* and the *gate under test* that happens to never matter because every real screenshot step in both real routes carries an explicit `label=`. Not a live risk; noted for completeness only.

## Claim blocks

```
claim: F1, F2 and M1 are fixed and reproduce independently.
referent: python3 -I -S -B validate.py (exit 0, scratch copy); python3 -I -S -B
  framing-fit.py (byte-identical to framing-fit-output.json via cmp);
  postrun-gate.py adversarial fixtures (label-mismatch FAIL, absent
  boot-attempts.json FAIL) beyond what validate.py already carries
checked: this pass, on scratch copies under review-probes-k1prep-r2/
verdict: holds
confidence: high
```
```
claim: the L1 diagnostic is faithful to CP §2h (setup, step 2's paired snapshot,
  step 3's correlation admission rule, step 1's precondition) except step 4
  (yaw-sweep collision test), which the report explicitly and correctly says
  is out of scope for V1 admission.
referent: kp-camera-api-plan.md:228-248 (§2h); prep-report.md §5b, A1-A5;
  l1-camera-diagnostic.toml, generate-l1.py
checked: side-by-side read of both documents, plus the independent step-mapping
  and NWScript-scan re-derivations above
verdict: holds
confidence: high
```
```
claim: F3's "BLOCKING" status is not enforced by any executable check in this
  directory; only F1 and F2 are.
referent: constructed V1-only run directory with no L1 trace; postrun-gate.py
  on it prints PASS (see Finding I1)
checked: this pass
verdict: holds (this is the one real gap found this round)
confidence: high
```
```
claim: the 76-chunk count and the "no bare NWScript names" scan both hold,
  independent of validate.py's own implementation.
referent: direct WT Scenario.load counts (18+20+36+1+1=76); independent
  strip-then-scan against k1.json's 772 names, run on l1-camera-diagnostic.toml
  and l1_camera_probe.lua only
checked: this pass, code shown above
verdict: holds
confidence: high
```

## Required before unconditional PASS

Given the review brief's framing (F1/F2/F3/M1 were the required fixes, and I1 is a new, narrower finding about F3's enforcement rather than its design), I read this as a PASS with one open, non-blocking recommendation:

1. Optional, recommended: give `postrun-gate.py` (or a sibling script) a way to refuse V1 acceptance when no corresponding passing L1 run is supplied, so the "blocking" word in §0 P5 is enforced the same way F1 and F2 now are.

**Question I could not settle:** same as round 1 — is the settled mode-2 chase view at this spot 192-230 px, and do the raw fields move with the view? Only the L1 launch itself settles this; nothing offline can, and the report does not claim otherwise.

K1 prep round 2 verdict: PASS

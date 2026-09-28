# Doppelganger fix and proof brief

## Verdict

**Open defect. Do not call `cursed/70_doppelganger.lua` fixed until it captures the PC's original appearance before the Malak mutation, gives every eligible hostile that captured row, and restores the exact script-added disguise effects for every still-valid touched actor on both ordinary completion and each abort/failure path.**

The recorded 2026-09-22 run proves the inversion. The PC was row 136 before the script fired, then row 21; the three copied Sith also became row 21. The existing counter gate passed only because three requests succeeded. It did not inspect the enemy rows.

## Scope and ownership

| File | Smallest required change |
|---|---|
| `scripts/examples/cursed/70_doppelganger.lua` | Implement a small per-run transaction: capture, apply/track, copy from capture, and cleanup/verify. |
| `tools/tests/examples/fixture.lua` | Extend the controlled backend only enough to model per-object appearance and effect handles, effect enumeration, removal, and controlled failures. |
| `tools/tests/examples/cursed.lua` | Replace the current count-only Doppelganger assertions with capture-before-mutation, exact copied row, retry/rollback, and cleanup assertions. |
| `scripts/harness/scenarios/cursed/70_doppelganger.toml` | Preserve three live copied actors long enough to read their rows, then invoke a deterministic cleanup transition and independently assert restoration for every still-valid touched actor. |
| `tools/tests/examples/manifest.json` | Keep the same identity and live predicates, but revise `hostile_copy` and `guards_once` obligation wording to require the captured-row and restoration observations. Update the source SHA after the code change. |
| `docs/original41-live-evidence-audit.md` | Leave the historical failure intact; add a later, hash-bound receipt only after the new run passes. |

The source is retained at `scripts/examples/cursed/70_doppelganger.lua`; it was not retired to `tools/tests/examples/fixtures/legacy/`. Its manifest identity is `cursed/70_doppelganger.lua`, SHA-256 `479b743031a489bee35279deecfd318828a4199f3af5280d571c0aa8eef983dd` before the fix.

## Minimal implementation contract

1. **Capture before mutation.** On the first eligible PC-involved attack, call `GetAppearanceType(pc)` before `malak(pc)`. Require a positive integer and store it in one `original_pc_appearance` value for the run. Do not recalculate it after the PC has row 21. `copy(who, pc)` must use that captured value, never `GetAppearanceType(pc)`.

2. **Track only the script's disguise effects.** Before each permanent `ApplyEffectToObject` call, enumerate that actor's effects with `GetFirstEffect`, `GetNextEffect`, and `GetIsEffectValid`. Apply the newly constructed `EffectDisguise`; after the successful protected call, enumerate again and retain only the newly introduced disguise-effect handle(s) attributable to this transaction. Store per actor: original appearance row, target row, and the exact effect handle(s) inserted by this script. Do this before optional VFX/speech so a partially failed cosmetic request cannot obscure ownership.

3. **Make each mutation transactional.** A `Type::Void` `ApplyEffectToObject` returns zero Lua results, so protected-call success is only a successful request. Treat the mutation as successful only after the actor's independent `GetAppearanceType` readback equals its requested row and the inserted effect handle(s) have been recorded. If construction, apply, enumeration, or readback fails, immediately remove every recorded just-added handle for that actor with `RemoveEffect`, verify the pre-mutation row, do not set `pc_cursed`/`copies[who]`, and do not increment local number 7. A missing cleanup handle or failed readback is an explicit script failure, not a successful copy.

4. **Deterministic finalization.** Implement one idempotent `restore_all(reason)` that removes every tracked valid effect from every still-valid touched actor, reads each actor's appearance again, and only clears its bookkeeping after it equals the stored pre-mutation row. Call it before state reset in `OnModuleLoad` and `OnAreaEnter`, on every transaction-failure/abort path, and after the fight has ended by a bounded `OnTick` combat-settle rule. The settle rule must require an observed PC combat period and a documented consecutive non-combat window, so arming/load does not instantly tear down the scene. Invalid/dead actors may be recorded as no-longer-valid; they are not silently counted as a restored valid actor.

5. **No ambient state overwrite.** Cleanup removes only handles captured in step 2. It must not blanket-remove effects, use `RemoveAllEffects`, or paint row 136/another guessed row back onto actors. The original rows are per actor: PC row before Malak, hostile rows before their copy. This preserves pre-existing effects and makes a rollback verifiable.

The current script violates step 1 at `copy()` because it calls `GetAppearanceType(pc)` after `malak()` applies the permanent row-21 disguise. Its only reset path clears Lua flags and local 5; it neither tracks nor removes permanent disguise effects.

## Exact host-test oracle

Extend the existing controlled Lua fixture, not the native runtime, and retain the existing arming/party/dead/retry cases. Add these deterministic cases in `tools/tests/examples/cursed.lua`:

| Case | Setup | Required assertion |
|---|---|---|
| Capture-before-Malak | PC base/current row 136; eligible hostile 20 row 28; arm; call `OnCreatureAttacked(1,20)`. | PC current row is 21; hostile 20 current row is **136**, never 21; counter is 1. |
| Frozen capture | Trigger another eligible hostile after the PC is already 21. | Second hostile gets 136, proving it did not reread the mutated PC. |
| Guards and once | NPC-vs-NPC, party, invalid, dead, and duplicate attack events. | No new effect/handle/counter; no actor outside the eligible set is touched. |
| Apply failure and retry | Make `EffectDisguise` fail, then make `ApplyEffectToObject` throw, then restore normal behavior. | No permanent row change, no tracked handle, no `pc_cursed`/copy count/log success from either failure; later valid event applies exactly once. |
| Post-apply/readback failure | Simulate an apply that changes the visible row but makes post-apply enumeration/readback fail. | The recorded new handle is removed, current row returns to its pre-mutation value, and the attempted actor remains retryable. |
| End-of-combat cleanup | Start PC and three living hostiles with distinct original rows; produce copies; mark combat seen then satisfy the settle rule. | PC returns to 136 and each valid hostile returns to its own original row; all script-added handles are gone; a second cleanup is a no-op. |
| Transition/area abort cleanup | Repeat with active, living actors and call `OnModuleLoad` and separately `OnAreaEnter`. | The same restoration assertions hold before run state is cleared. |

The fixture must model effects as actor-owned handles and update `GetAppearanceType` according to the currently active disguise, then recompute it after `RemoveEffect`. A fake global `GetAppearanceType() == 6`, as it exists now, cannot catch this bug. These are controlled-backend proofs of decision, request ownership, rollback, and scripted cleanup only; they do not establish an engine effect landed.

Run the normal source/host gate after the implementation:

```sh
/usr/bin/python3 tools/example_validation.py \\
  --host /absolute/build/kp_luatest \\
  --receipt /absolute/build/example-validation.json
python3 tools/nwscript_boundary_test.py
ctest --test-dir /absolute/build -R 'example_validation|nwscript_boundary' --output-on-failure
```

The required pass condition is the named enhanced Doppelganger cases in the generated receipt, all 41 syntax/host sources passing, and zero boundary-check violations. A prior receipt is stale once the script, fixture, suite, or manifest hash changes.

## Exact live-test oracle

Use a fresh serialized K1 route derived from `scripts/harness/scenarios/cursed/70_doppelganger.toml`, with current source/deployed Lua and runtime hashes captured. Do not reuse run `20260922-104259` as success evidence.

1. Before arming, independently record the PC's current appearance row **P** and the object IDs plus rows **E1, E2, E3** of three living, eligible hostile fixtures. Require `P != 21`; the recorded failed route had `P = 136`.
2. Arm, make the PC and all three hostiles exchange attacks, and use the observer/harness state query to read each row after the effect is applied. Required active-scene state: PC is 21; every live eligible Ei is exactly P; no Ei is 21 unless P itself was 21 (disallow that fixture).
3. Exercise the same actor again plus NPC-vs-NPC, party, invalid, and dead candidates. Independently show no extra qualifying copy/appearance mutation and that the copy counter increments only for first successful eligible copies.
4. Force one controlled failed disguise request before a later valid event. The failed actor keeps its original row and does not advance the counter; the later valid event yields row P exactly once. Retain the request/error trace and the independent actor row reads.
5. Keep PC and E1..E3 alive. End combat and wait for the documented settle window, or use a module/area transition dedicated to cleanup. Independently query all valid touched actors: PC returns to P; each Ei returns to its own pre-copy Ei. Capture effect enumeration before active application, while active, and after cleanup to prove the script-added disguise effect handles are removed while baseline effects remain.
6. Demonstrate advancing ticks, combat actions, and no crash/freeze while active, then capture a continuous recording through cleanup. Retain route report, current staged Lua copy/hash, runtime hash, checkpoint hash, observer/raw state artifacts, and video.

Set every existing manifest predicate true only when its corresponding independent observation is present. In particular, `cursed.70_doppelganger.hostile_copy` requires the three post-application rows equal P, `guards_once` requires the negative cases and cleanup ownership, `failed_request_retry` requires the failed-then-valid proof, and `animation_safety` requires advancing live ticks. The live evidence importer also requires a clean session, exact current hashes, all predicate keys, and retained hash-verified artifacts.

## Boundary assessment

There is **no required conflict** with the strict native `kp` versus engine `nwscript.call` boundary if the implementation stays in the existing API surface:

- `GetAppearanceType`, `EffectDisguise`, `ApplyEffectToObject`, `GetFirstEffect`, `GetNextEffect`, `GetIsEffectValid`, and `RemoveEffect` are K1 engine routines and must be invoked as `nwscript.call("...")` (or through the existing guarded `q`).
- `ApplyEffectToObject` and `RemoveEffect` are `Void`; use `pcall` plus independent state readback, never a truthy return value.
- `kp.print` remains an oracle/log facility. It cannot certify a landed effect. `kp.registertimer` may be used only for native timer ownership if needed, but polling/restoration semantics remain Lua state plus explicit NWScript calls.
- Do not add `kp.GetAppearanceType`, `kp.RemoveEffect`, a raw native appearance setter, or an alias to a catalogued NWScript routine. The repository's lexical boundary test explicitly rejects direct routine members on `kp`/`nwscript` and allows `nwscript.call("GetFirstPC")` plus `nwscript.with_caller`.

Therefore this is a script/fixture/scenario/manifest proof repair, not a native API change. If effect-handle enumeration cannot reliably identify the newly inserted disguise effect on the target K1 runtime, stop before mutation or add a separately reviewed engine capability; do not claim deterministic restoration based on a counter, log line, or guessed appearance row.

## Evidence inspected

- `docs/original41-live-evidence-audit.md`: current defect status and the row-136-to-21 observation.
- `/home/brunner56/kp-live-20260922/stage-k1/runs/20260922-104259/kotorphasor.log`: PC row 136 before firing; PC and copied Sith rows 21 afterward.
- `/home/brunner56/kp-live-20260922/live-findings.json`: open `doppel-original-appearance` finding.
- `tools/tests/examples/manifest.json`, `tools/tests/examples/fixture.lua`, and `tools/tests/examples/cursed.lua`: current source identity, unvalidated predicates, and insufficient count-only fixture contract.

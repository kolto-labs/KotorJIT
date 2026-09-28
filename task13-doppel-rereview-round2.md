# Task 13 Doppelganger round-two scoped rereview

## Verdict

**FAIL — one Important live-proof gap remains; no Critical code finding.**

The current source hash is `5d9864b22241ff135d3bb0c1ecb3f2671af218b58cdf2f44eb7bc62c95f62c42`, exactly matching `tools/tests/examples/manifest.json:457`. The retained-token implementation, failure state machine, terminal transition behavior, tests, and restored cosmetics correct the previous code blockers. The route now creates same-payload hostile baselines, retains their constructor tokens through GC, and later removes them independently. It still does not independently observe the script-owned same-row disguise while active, so it cannot establish that the owned token landed before cleanup.

## Finding

### Important

1. **`scripts/harness/scenarios/cursed/70_doppelganger.toml:63-65,84-87` does not prove the script-owned same-`P` disguise was installed alongside the identical baseline.** Each marked hostile already reads row `P` and already has one retained `EffectDisguise(P)` baseline before the Doppelganger callback. The active-scene oracle checks only row `P` and counter `3`; both pass if the script's second same-row `ApplyEffectToObject` request is accepted but no engine effect lands. The post-cleanup oracle checks that the disguise count returned to the recorded baseline count; that also passes in the same no-op case. Later removal of the baseline token proves the baseline remained independently removable, but it still does not prove there was an owned delta to remove. This is exactly the evidence boundary called out by the manifest wording that counter/request evidence alone is insufficient. During the active scene, enumerate each marked actor and require its disguise count to equal recorded baseline slot 101 plus one. Then the existing post-cleanup `== baseline` check and final baseline-token removal establish the full `1 -> 2 -> 1 -> 0` sequence under GC pressure.

## Previous blockers now resolved

- **Remove success and same-row ownership:** `scripts/examples/cursed/70_doppelganger.lua:60-65` requires both protected `RemoveEffect` success and original-row readback before releasing the exact token. `tools/tests/examples/cursed.lua:139-147` covers same-row removal failure, retention without rearm, and successful retry.
- **Transition terminal semantics:** `scripts/examples/cursed/70_doppelganger.lua:72-92,114-143` moves terminally unavailable actors out of active pending state, reports them as unavailable rather than restored, restores all still-valid actors, and permits a fresh run only after the terminal result. Valid removal failures remain pending and block rearm.
- **Transition tests:** `tools/tests/examples/cursed.lua:149-160` separately exercises successful `OnAreaEnter` and `OnModuleLoad` restoration of the PC and three living copies. Lines 124-137 cover unavailable terminal handling and later rearm.
- **Identical baseline mechanics:** `scripts/harness/scenarios/cursed/70_doppelganger.toml:48-50` now applies `EffectDisguise(P)` baselines to the same hostiles that the script later targets with `P`; the baseline tokens are held in a global table across collection. Lines 90-93 remove those exact baseline tokens after script cleanup. The missing active `baseline + 1` observation is the sole remaining proof defect.
- **GC and fresh wrappers:** route lines 34-36 demonstrate separately enumerated wrappers are unequal, keep the constructor token globally reachable, and force collection. Hostile baseline tokens are likewise retained across collection at lines 48-50.
- **Cosmetics:** `scripts/examples/cursed/70_doppelganger.lua:146-162,210-220` restores the temporary VFX, fades, and caller-scoped speech outside the permanent disguise transaction.
- **Manifest:** identity, retained source path, live-unvalidated status, explicit focused-live unmet precondition, and SHA-256 are consistent with the current bytes.

## Validation performed

- Direct LuaJIT syntax load of `scripts/examples/cursed/70_doppelganger.lua`: **PASS**.
- Static review of only the corrected source, focused tests, route, manifest, and prior native audit.
- No inventory generation, broad suite, build, or game process was run.

# Task 13 Doppelganger retained-token rereview

## Verdict

**FAIL / REQUEST CHANGES.** The retained-constructor-token design fixes the earlier production userdata-identity defect and is consistent with the native audit: each mutation creates one fresh `EffectDisguise` token, stores it before the void apply, applies it once, and passes that same strongly referenced token to `RemoveEffect`. Row 0 is accepted, active cleanup failures block new attacks and rearming, the route now requires exactly three copies, and the manifest SHA matches the current script. One rollback path can still abandon a permanent owned effect, and the route does not perform the focused identical-effect native proof required by the audit and its own manifest.

Current source SHA-256: `2de760ebc0e3a7bd07d18c60f46c4a7d0a3ab08901638344e0fd14d11bd04d9a`; exact match at `tools/tests/examples/manifest.json:457`.

## Findings

### Critical

1. **`scripts/examples/cursed/70_doppelganger.lua:56-59,69-74` treats a failed `RemoveEffect` as successful whenever the actor's original and target rows are equal, then releases the only exact ownership token.** `remove_owned()` discards the boolean from protected `RemoveEffect` and decides solely from `GetAppearanceType(actor) == state.original`. If a hostile already has the PC's captured row, applying the owned disguise leaves the visible row unchanged. A thrown removal then also leaves that row unchanged, so `resolve_state()` deletes `pending[actor]`, increments `restored`, and eventually allows rearming even though the permanent owned effect remains installed and its constructor token becomes unreachable. This violates exact cleanup on failure/rollback paths. A focused controlled probe against the current bytes reproduced the leak: 30 cursed cases passed, then a hostile with `original == target` plus forced removal failure was cleared from bookkeeping while `active_disguises(20) == 1` after the PC completed cleanup. Require successful protected removal as well as row verification before releasing the token; add the same-row failed-removal regression. A live exact-identity observation is still needed because a successful void request alone cannot prove removal.

### Important

2. **`scripts/harness/scenarios/cursed/70_doppelganger.toml:34-36,48-50,84-87` does not implement the native audit's identical-effect ownership proof despite claiming that it does.** The PC baseline targets `P` while the script-owned PC token targets 21. Each hostile baseline targets its own `E`, while the script-owned hostile token targets `P`. Those are different disguise payloads unless an accidental row collision occurs. The route never retains the baseline constructor token, never enumerates twice to demonstrate fresh wrappers, never forces GC while the owned token remains reachable, and never removes the baseline by its original token to prove independent validity. Counts and final rows are useful but weaker than the audit's required same-row `B`/`O` discrimination. The manifest correctly leaves this exact live proof unmet at `tools/tests/examples/manifest.json:478-482`; the route comments and labels should not claim it has already established identical-handle preservation. Add the audit's focused serialized proof before enabling or promoting the permanent mutation path.

3. **`scripts/examples/cursed/70_doppelganger.lua:60-67,109-128,133-143` has no terminal disposition for unavailable actors, so an ordinary area/module transition can permanently wedge the example.** An invalid or dead touched actor stays in `pending` forever. The `unavailable` count is incremented, but `finish_if_resolved()` can never reach its `unavailable > 0` report because it returns while that pending entry exists. After a transition, every tick retries the impossible cleanup and returns before arming. This safely avoids a false restored claim and satisfies “no rearm while unresolved,” but it does not provide a deterministic terminal area/module outcome and retains the token/run state indefinitely. Record unavailable actors in a separate terminal ledger, restore every still-valid actor, emit the partial terminal result, and define whether the new module may begin a fresh run; do not count unavailable actors as restored.

4. **`tools/tests/examples/cursed.lua:119-132` does not cover normal `OnAreaEnter` cleanup or the terminal-unavailable state described by the implementation.** The transition test calls only `OnModuleLoad`, after first making the PC unavailable, and asserts that cleanup remains unresolved. There is no current regression showing that both module and area callbacks restore a PC plus three still-valid actors, no assertion that unavailable actors are never included in the restored count, and no bounded terminal-state assertion. Add distinct normal module, normal area, and unavailable-transition cases.

5. **`scripts/examples/cursed/70_doppelganger.lua:1-4` removes the original scene's VFX, fades, and speech despite the task brief explicitly requiring visual presentation to remain separate from fixture simplification.** The retained-token cleanup work does not require deleting temporary visual effects or the two caller-scoped speech requests. Restore the presentation after the ownership state machine is correct, keeping those temporary/cosmetic operations outside the permanent disguise token transaction.

## Checks that pass

- Exact token ownership now follows `/home/brunner56/kp-live-20260922/doppel-effect-identity-audit.md`: one fresh constructor token per mutation, stored before apply, reused unchanged for removal, and never compared with enumerated wrappers.
- Apply-that-mutates-then-throws retains ownership and enters cleanup-pending; failed cleanup blocks subsequent attacks and rearming until a retry succeeds.
- `OnModuleLoad` and `OnAreaEnter` both enter the same cleanup path, and still-valid actors are removed only through their own retained tokens.
- Unavailable actors are logged as unresolved rather than falsely reported as restored, though their terminal lifecycle remains incomplete as noted above.
- Appearance row 0 is accepted and covered by the controlled test.
- The live route requires `copied == 3` and local counter `== 3`, rejects an additional unmarked hostile with row `P`, and keeps marked targets alive through cleanup.
- The manifest identity, source path, retained disposition, live-unvalidated status, and SHA-256 are internally consistent.
- Engine routines use explicit `nwscript.call`; native `kp` use is limited to logging.

## Focused validation

A bounded Lua probe ran only `tools/tests/examples/cursed.lua` against the current source/fixture: **30 cursed cases passed**. A second inline case then reproduced Critical finding 1 with `original == target` and forced `RemoveEffect` failure. No broad suite or game process was run.

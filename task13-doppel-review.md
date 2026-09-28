# Task 13 Doppelganger independent review

## Verdicts

- **Specification verdict: FAIL.** The original PC row is now captured before the Malak mutation and reused for later copies, the native/NWScript namespace boundary is clean, and the manifest SHA matches the current source. The required exact effect ownership and deterministic failure cleanup are not satisfied, and the live route cannot prove the claimed ownership contract.
- **Quality verdict: BLOCK / REQUEST CHANGES.** The controlled suite passes because its effect representation has stronger identity semantics than the real Lua bridge. Current code can remove pre-existing effects and can permanently lose ownership after partial failures.

No broad suite was rerun. The implementer already supplied a passing 41-source receipt, and the blocking issues below are established by the reviewed bytes and the bridge's effect-value contract. Current source SHA-256 is `8ddca28a915b83c7cf432acf9dc2fbed76bfff80750a37417f3824c5e0958cd7`, matching `tools/tests/examples/manifest.json:457`.

## Findings

### Critical

1. **`scripts/examples/cursed/70_doppelganger.lua:47-50` cannot compute an effect-handle delta in the real runtime and will classify every post-apply effect as newly owned.** `effects_on()` keys `before` by the returned effect value, then `newly_added()` looks up separately enumerated post-apply values in that table. The native bridge represents every popped engine structure as a fresh opaque full userdata/private engine copy; it does not expose a stable effect ID. Separate enumerations therefore do not produce the same Lua table key for the same ambient engine effect. With any pre-existing effects, `handles` contains those baseline effects as well as the disguise, and `restore_actor()` removes all of them at lines 70-87. This directly violates exact newly-added disguise ownership and baseline preservation. `tools/tests/examples/fixture.lua:51-61` hides the defect by returning stable integer handles, so the host pass is a false model of the production identity boundary. The code also never filters the delta through `GetEffectType`, despite the contract requiring disguise handles only. Per the proof brief, this needs a separately reviewed stable engine identity/capability or the script must stop before mutation; the present before/after userdata-table comparison is not safe.

2. **`scripts/examples/cursed/70_doppelganger.lua:120-139` can strand an applied disguise without a removable handle, and a retry can erase the only failed-rollback bookkeeping.** A protected `ApplyEffectToObject` error returns immediately at line 120 without post-enumeration or row rollback, even though an error can occur after the void request mutated the actor. A failure in the first post-apply `GetFirstEffect`/`GetIsEffectValid` call similarly leaves `handles` empty while the row is changed. When rollback fails, line 136 records that incomplete state, but `pc_cursed` remains false; `OnTick` exits at line 193 and never retries normal cleanup. A later eligible attack calls `apply_disguise()` again at lines 142-149 and can overwrite `touched[pc]`, permanently losing the earlier transaction. The fixture case at `tools/tests/examples/cursed.lua:102-115` only tests an apply error that performs no mutation and an enumeration error after one numeric handle has already been captured, so it does not exercise these paths. Failed application, first-enumeration failure, failed readback, and failed rollback need an explicit poisoned/cleanup-pending state that prevents another mutation and retains all recoverable ownership until deterministic restoration succeeds.

### Important

3. **`scripts/examples/cursed/70_doppelganger.lua:175-178` disarms even when restoration fails, allowing a partially restored run to rearm with inconsistent flags.** `restore_all()` can restore and delete some actors while retaining another, yet `disarm_after_cleanup()` always calls `set_armed(false)`. After 200 ticks the script rearms. If the PC was restored but a hostile failed, `pc_cursed` remains true because the global state is only reset on complete success; a later attack skips reapplying Malak while copying more actors. If the PC failed, the retry/overwrite problem above applies. A failed cleanup must remain in a cleanup-only state, retry deterministically, and block rearming/new mutations until all still-valid owned effects are resolved.

4. **`scripts/examples/cursed/70_doppelganger.lua:79-95` silently counts unavailable actors as restored and immediately discards the record.** `restore_actor()` sets `state.unavailable = true` and returns success; `restore_all()` then deletes that state and may print the aggregate `restored` oracle. This does not preserve or report the required distinction between a restored living actor and an actor that became invalid/dead. Keep a durable unavailable outcome for the run/receipt, and do not describe it as restored.

5. **`scripts/harness/scenarios/cursed/70_doppelganger.toml:34-36,48-50,63-87` proves appearance rows and disguise counts, not exact handle ownership or baseline preservation.** It stores only the number of disguise effects. It neither records handle identities before/while/after nor deliberately gives a touched actor a baseline disguise/effect, so a zero-before/zero-after run passes without testing preservation. Equal counts also cannot show that the same baseline effect survived. The route additionally has no controlled failed request/retry or invalid/dead/party/duplicate probes even though those remain required manifest predicates at `tools/tests/examples/manifest.json:470-487`. Add hash-bound live observations that identify the owned effect delta and retain a known baseline effect, plus the required failure and guard branches, or leave those predicate obligations explicitly unproved by this route.

6. **`tools/tests/examples/cursed.lua:102-130` omits several required failure oracles and therefore overstates cleanup coverage.** There is no unavailable-original query followed by retry, no apply-that-mutates-then-throws case, no failure at the first post-apply enumeration call, no post-apply appearance-readback failure, no `RemoveEffect` failure followed by deterministic retry, and no cleanup with an unavailable touched actor. The current assertions also rely on the fixture's stable numeric-handle model. Add cases for each state transition after production ownership semantics are made representable; otherwise the 41-source pass does not validate the failure-path contract.

### Minor

7. **`scripts/harness/scenarios/cursed/70_doppelganger.toml:65` accepts a copy counter greater than three while claiming exactly three marked copies.** `>=3` cannot detect an unintended fourth eligible copy. This weakens the once/scope oracle; require exactly three and independently verify that no unmarked actor acquired the captured row or an owned disguise.

## Satisfied checks

- `scripts/examples/cursed/70_doppelganger.lua:144-165` captures a positive PC row before Malak and copies only that frozen value.
- Both PC-involved callback orientations, multiple hostiles after PC mutation, party/invalid/dead/duplicate exclusions, and ordinary settle/module/area restoration are represented in the controlled tests.
- Engine routines remain behind explicit `nwscript.call`; only `kp.print` uses the native namespace.
- Manifest identity, source path, retained disposition, and SHA-256 match the current source bytes.
- The live route keeps its three marked targets alive while checking active copied rows and later restoration.

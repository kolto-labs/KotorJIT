# Doppelganger effect identity and ownership audit

Date: 2026-09-27  
Scope: K1 Lua/NWScript bridge in `.worktrees/lua-boundary-validation`, K1 routine metadata, and the locally retained K1 GOG max-C/AgentDecompile corpus.  
Method: source and original-byte assembly audit only. No game process, build, or test was run.

## Verdict

K1 effects do have a stable native identity: the first eight bytes of `CGameEffect` are a 64-bit `id`. `GetFirstEffect`/`GetNextEffect` return private copies that preserve that ID, and `RemoveEffect` accepts such a copied effect structure. The K1 removal handler searches the target's effect list and compares both 32-bit halves of the supplied 64-bit ID before removing only the matching entry.

That identity is not directly comparable in Lua. Every engine-structure return becomes a fresh full userdata around a fresh native copy. The userdata metatable has no `__eq` and exposes no fields. A Lua table keyed by pre-enumeration userdata therefore cannot identify the same native effect in a later enumeration. The public K1 routine catalog also has no `GetEffectId`, effect tag, or disguise-payload accessor.

The safest implementable ownership algorithm does **not** need an enumeration delta: retain the original userdata returned by each fresh `EffectDisguise(row)` call, use it for exactly one `ApplyEffectToObject`, then pass that same retained userdata to `RemoveEffect(actor, token)` during rollback or cleanup. The bridge pushes a copy of the token into the VM; the apply handler modifies duration/subtype/creator data but does not rewrite the ID at offsets `+0` and `+4`; the installed list entry therefore retains the constructor token's ID. `RemoveEffect` uses that ID as the exact key. Pre-existing identical disguise effects have different IDs and are not selected.

This retained-constructor-token algorithm is strongly supported by the code and original-byte handler evidence, but it still needs one focused live K1 proof before the Doppelganger example can claim the ownership contract. Until that proof passes, the current fail-closed behavior is the safe release behavior.

There is no public K1 `SetCreatureAppearanceType` or `SetAppearanceType` routine. `DuplicateHeadAppearance` exists, but it changes only a head appearance and offers no full appearance-row snapshot/restore contract. It cannot implement the Malak/full-PC Doppelganger scene or replace exact disguise-effect cleanup.

## Evidence

### 1. Lua wrappers are fresh opaque owned copies

The bridge documents that `StackPopEngineStructure` calls the engine's `CopyGameDefinedStructure` and returns memory owned by the bridge (`src/api/enginestruct.hpp:98-106`). It also states that effect/event/location/talent values are opaque userdata with no readable layout and that every popped value is a private copy (`src/api/enginestruct.hpp:198-209`).

The implementation stores only `{type, ptr, owned}` in the Lua userdata (`src/api/enginestruct.cpp:49-55`). Its metatable provides `__gc` and `__tostring`; it does not provide `__eq` or `__index` (`src/api/enginestruct.cpp:244-259`). Thus two userdata values created by separate enumerations compare by Lua userdata object identity, not by `CGameEffect::id`.

Every effect return is popped through `pop_engine_structure`, then wrapped as a new owned userdata (`src/api/routines.cpp:349-366`). Passing an effect back to an NWScript routine unwraps its native pointer and calls the VM's `push_engine_structure` (`src/api/routines.cpp:216-224`). This is why an enumerated copy remains valid as an input to `RemoveEffect`, while separately enumerated Lua wrappers cannot be compared directly.

### 2. The engine effect structure carries a 64-bit ID

The local K1 GOG corpus defines `CGameEffect` with `unsigned long long id` at offset zero, followed by `type`, `subtype`, duration, expiration, creator, spell, and payload fields:

- `/run/media/brunner56/MyBook/Documents/Codex/2026-09-16/handoff-agentdecompile-bioware-recovery-objective-build/work/maxc-package/k1_win_gog_swkotor.exe/ExecuteCommandApplyEffectAtLocation_0052e430.c:1337-1356`
- corroborating duplicate layout: `.../ExecuteCommandGetEffectSpellId_00537b90.c:760-779`

The max-C package labels some handlers as compile-only assembly substrates, so the semantic names around raw instructions are not themselves byte-equivalence proof. The emitted handler bytes are the retained original bytes, however, and their offsets/comparisons can be audited directly.

### 3. `RemoveEffect` accepts a copy and matches exactly by ID

K1 metadata declares routine 87 as `RemoveEffect(object oCreature, effect eEffect) -> void` (`data/routines/k1.json:1293-1308`; generated table `src/generated/routines_k1.inc:861`). The bridge passes the native structure carried by any valid effect userdata, including a copied enumeration result.

In the original-byte `ExecuteCommandRemoveEffect` substrate, the handler walks the target object's effect pointer array. For each candidate it compares candidate dword 0 with supplied dword 0, then candidate dword 1 with supplied dword 1. Only after both comparisons match does it mark the candidate for removal:

- effect-list iteration and first/second dword comparisons: `.../ExecuteCommandRemoveEffect_0054ae40.c:145-202`
- the two comparisons are the instructions represented at lines 168-180; the matching entry is retained at lines 182-194 and then passed into the removal path at lines 203-252.

Because `CGameEffect::id` occupies exactly those first eight bytes, `RemoveEffect` is ID-exact. It does not compare type, creator, duration, or disguise appearance payload. A copied structure carrying the same ID is sufficient, and an otherwise identical effect carrying a different ID is not selected.

### 4. Applying the retained constructor token preserves the identity needed for removal

`EffectDisguise(int)` returns an effect (`data/routines/k1.json:6593-6603`; generated table `src/generated/routines_k1.inc:1236`). The bridge wraps the returned private native effect copy and keeps it alive until Lua releases it (`src/api/routines.cpp:349-366`; `src/api/enginestruct.cpp:70-90`). Holding that userdata in the per-actor transaction state therefore keeps the removal token alive.

`ApplyEffectToObject` is routine 220 and returns `void` (`data/routines/k1.json:3278-3304`; generated table `src/generated/routines_k1.inc:994`). The original-byte apply handler edits fields at `+0x0a`, `+0x0c`, `+0x18`, and `+0x24` while setting duration/subtype/creator-related data (`.../ExecuteCommandApplyEffectToObject_0052e570.c:129-197` and `:239-309`). It then passes the effect into the target object's apply path (`:354-374`). There is no store to offsets `+0` or `+4` anywhere in the handler. The 64-bit ID is therefore preserved through this command.

The bridge also confirms the engine's ordinary structure-copy path: a pushed/popped engine structure is a full `CopyGameDefinedStructure` copy (`src/api/enginestruct.hpp:98-106`), rather than a new logical effect manufactured from public fields. This makes the original `EffectDisguise` userdata an exact token for the subsequently installed copy.

This is materially different from comparing `GetFirstEffect` results. A later enumeration produces a different Lua wrapper, but both the later enumeration copy and the retained constructor token carry the same native ID as the installed effect.

### 5. Public field matching cannot replace identity

K1 exposes only these general effect inspectors in the relevant API area:

- `GetIsEffectValid`
- `GetEffectDurationType`
- `GetEffectSubType`
- `GetEffectCreator`
- `GetEffectType`
- `GetEffectSpellId`

See `data/routines/k1.json:1310-1356`, `:2488-2498`, and `:4472-4482`. These fields are not unique. Two permanent disguise effects created by the same caller can have the same type, subtype, creator, duration type, and spell ID while carrying different appearance payloads or IDs. K1 does not expose the disguise appearance integer payload. Field matching can therefore remove an ambient identical effect and is not an ownership algorithm.

Using `nwscript.with_caller` plus `GetEffectCreator` to manufacture a unique creator is possible in principle, but is needlessly indirect and carries object-lifetime/collision questions. The retained constructor token is simpler and uses the engine's actual removal key.

### 6. No reversible non-effect appearance primitive exists in the public K1 catalog

The K1 catalog contains `GetAppearanceType(object) -> int` at routine 524 (`data/routines/k1.json:7353-7364`) and `EffectDisguise(int) -> effect` at routine 463 (`:6593-6603`). Searches of the complete 772-routine catalog and the source `nwscript.nss` found no `SetCreatureAppearanceType`, `SetAppearanceType`, or equivalent full-row setter.

`DuplicateHeadAppearance(object oidCreatureToChange, object oidCreatureToMatch) -> void` is routine 500 (`data/routines/k1.json:6998-7017`). Its scope is head duplication, not the complete `appearance.2da` row used by `EffectDisguise`. There is no corresponding getter for a reversible head transaction, and it cannot turn the PC into row 21 Malak or make arbitrary hostiles exact copies of a captured full appearance row.

A raw native appearance-field write would require a new reviewed API with engine refresh/replication/save semantics. No such supported KotorPhasor API is present in this worktree. It is a larger, riskier change than retaining the exact effect token already provided by the engine.

## Recommended transaction

For each actor, keep a record with `actor`, `before_row`, `target_row`, `token`, and a cleanup state. Use one token for one apply only.

1. Read and validate `before_row` before any mutation.
2. Construct `token = nwscript.call("EffectDisguise", target_row)` and store it in the actor record immediately so Lua GC cannot release it.
3. Call `ApplyEffectToObject(PERMANENT, token, actor, 0.0)` in a protected call.
4. Regardless of whether the protected call reports success, retain the record until the actor is independently resolved. A bridge/handler error can be ambiguous about whether mutation occurred.
5. On reported success, require independent `GetAppearanceType(actor) == target_row` before counting/logging success.
6. On any apply, enumeration, or readback failure, call `RemoveEffect(actor, token)` even if application may not have occurred. No matching ID makes this a harmless no-op; a partially applied matching effect is removed exactly.
7. For normal cleanup, call `RemoveEffect(actor, token)`, then require `GetAppearanceType(actor) == before_row`. Delete the record and release the userdata only after that verification.
8. If removal or verification fails, keep the record in cleanup-pending state, block rearming and all new mutations, and retry on a bounded deterministic path. Never overwrite the record with a retry.
9. Never apply the same effect userdata to two actors or twice to one actor. Each mutation gets a freshly constructed effect/ID.
10. Record invalid/dead/unavailable actors separately; do not report them as restored.

The before/after `GetFirstEffect`/`GetNextEffect` enumeration can remain as an observational proof aid, but it must not decide ownership. The retained token decides ownership.

## Proof test required before enabling mutation

The decisive live K1 test should be small and serialized:

1. Choose a living test actor with original row `E`.
2. Create and apply a permanent baseline disguise `B` to row `X`; retain its constructor token. Confirm the actor is `X` and record the baseline disguise count.
3. Create a second fresh disguise token `O`, preferably to the same row `X` for the strongest identical-effect case, and apply it once. Keep `O` strongly referenced.
4. Enumerate effects twice and demonstrate that the Lua wrappers are fresh/non-equal while both enumerations remain valid. This confirms that wrapper equality is not being used.
5. Force Lua collection while `O` remains reachable in the transaction table; confirm the scene remains active.
6. Call `RemoveEffect(actor, O)` using the original constructor token, not an enumerated copy.
7. Confirm the actor still has baseline row `X`; the baseline disguise count is unchanged; only the one added delta disappeared; ticks continue; no crash/freeze occurs.
8. Finally remove `B` with its own retained token and confirm row `E` returns. This second removal proves the baseline token remained independently valid.
9. Repeat the ownership portion with different target rows so removal order/visible-effect precedence cannot hide a mistaken deletion.
10. Exercise a controlled failure after token storage and verify the same token-driven rollback. A failed cleanup must retain its record and succeed on a later retry before rearming.

Bind the proof to the exact staged DLL, Lua source, scenario, and game build hashes. Host fixtures should model fresh enumeration wrappers and a stable internal native ID, but they remain a controlled-boundary proof; only the live K1 test establishes that the retained constructor token removes the installed engine copy.

## Release decision

- Safe immediately: keep the example fail-closed, with no permanent disguise application.
- Safe to enable after the focused live proof: retained fresh constructor token per actor, exact token-based removal, independent row readback, and cleanup-pending retry state.
- Unsafe: before/after Lua userdata set difference, effect-count difference, first/last enumeration position, public-field matching, blanket effect removal, guessed appearance restoration, or `DuplicateHeadAppearance` as a full-row substitute.

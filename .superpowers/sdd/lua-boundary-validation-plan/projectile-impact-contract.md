# Object-blaster impact and engine knockback: bounded WinK1 contract

Read-only audit, 2026-09-22. No games, attachments, builds, recovery jobs or source edits. Original executable `/home/brunner56/krayt/tmp/k1_harness/swkotor.exe`, independently SHA256 verified `9c10e0450a6eeca417e036e3cde7474fed1f0a92aab018446d156944dea91435`. x86 PE image base0x400000; addresses are preferred virtual addresses, use rebased RVA only after exact build verification. Names/signatures used as locators from mode=ro `/home/brunner56/agentdecompile-nvme/corpus-work/corpus.sqlite`, binary8; behavioral conclusions below come from original objdump bytes. No raw disassembly should enter public product/browser artifacts.

## Outcome

A stronger engine-owned displacement route exists below the parameterless script effect: force-push reads a floating distance, checks a proposed destination and drives native quickwalk movement. It is NOT physical tumbling. Ranged attack planning supplies useful source/target/subattack identity, but the inspected ResolveRangedHit routine is NOT an actual projectile-impact callback. There is not yet a complete, safe impact-timed hook contract; implement observation/identity first and keep impact-time acceptance pending.

## Ranged planning and exact byte-backed ABI

- `0x5bb590 ResolveRangedAttack`: ECX attacker creature, stack target object plus SIX additional32-bit slots, RET0x1c. Prior feasibility wording suggesting seven integer arguments in addition to target was wrong. Exact extra parameter meanings remain incomplete; no callable full signature should invent them.
- It obtains current attack from attacker+0x9c8 combat-round pointer; current index is byte round+0x96c, passed to GetAttack0x4d2b50. Attack+0x0c receives target object+4 ID. Attack+0 receives incremented round+0x974 BYTE sequence. This byte wraps and is insufficient as a persistent unique key.
- Calls GetWeaponDischargeShots0x5b5230, GetWeaponHitShots0x5b52e0, GetTotalAttacks0x4d2eb0; loops per discharge with EBX zero-based loop ordinal. Offhand state is set through0x4d29f0 and read through0x4d2a00. Attack+0x3a becomes1 or2 from offhand boolean. This is stronger evidence than assuming every visual bolt equals one damage event.
- Attack+0x5c is reset4 each iteration; attack-roll/special/parry logic changes it. Numeric branches classify outcomes; do not publish guessed names for the entire result enum. Some decompiler-looking comparisons are actually `movzx byte` then compare EAX with0xffffffff, which can never match. Preserve original-byte behavior; do not normalize to signed-byte semantics.
- At0x5bb7bf the chosen hit branch calls ResolveRangedHit0x5b6db0; alternate0x5bb805 calls ResolveRangedMiss0x5b6e90. ResolveDamage0x5bb440 and ResolvePostRangedDamage0x5b8c20 are conditionally called after the hit bookkeeping, not every nominal hit branch. Parry processing can enter the hit path with distinct outcome codes.
- ResolveRangedHit ABI: ECX attacker, one stack target pointer, void, RET4. It sets attack metadata, copies target position to attack+0x68, calculates a distance-derived word at+0x10. It does not itself apply a knockback or establish that the visible projectile has arrived. Corpus caller edge set shows only ResolveRangedAttack; original callsite is independently verified.
- At0x5bb835 ResolveAttackToRangedSubAttack0x4d5b60 receives ECX attack, five stack args: discharge ordinal, value from GetWeaponDischargeTime, selected-attack boolean, hit-branch boolean, value from GetWeaponDischargeHand; RET0x14. Raw code copies current result/hand/position/damage/effect data into a0xd0-byte subattack record and appends it. The time field unit and client-projectile correlation remain unproven. This callsite is a useful telemetry seam, NOT yet a physical impact seam.
- ResolvePostRangedDamage inspects current attack damage, target creature conversion and HP-like virtual return; builds effects in attack-owned lists. Its name is not proof damage has already been committed. Need the downstream subattack execution/damage-application consumer and timing before implementing hit-synchronized impulse.

Recommended identity telemetry: engine epoch + monotonically assigned outer ranged-call sequence + attacker server ID + target server ID + discharge ordinal + hand/result snapshot. Use only copied scalar data, not long-lived attack/creature pointers. The8-bit engine sequence and a victim/game-second cooldown lose valid bursts or collide. One impact response per proven damage-bearing subattack, not per visual decoration and not once per whole attack. No observed all-blaster/dual-wield/miss coverage is claimed by this static extraction.

## Native force-push contract

`0x4e3800 OnApplyForcePush`: stack object*, effect*, third32-bit argument, callee RET0x0c (stdcall-style). Third arg is not used in inspected body; do not assign it a semantic name. First object is converted via vtable+0x30 to a creature; creator ID comes from effect+0x18 and is freshly resolved through manager0x7a39fc→server+8→GetGameObject0x4ae750; creator also must convert through vtable+0x10. Missing target/creator exits. Return EAX is0 even after the successful path, so boolean return is NOT success proof.

Effect accessors: GetInteger0x503690, SetInteger0x5036a0, GetFloat0x5036c0, SetFloat0x5036d0. Read indexes are byte-backed:

- integer0==0: source/reference point is creator object position+0x90.
- integer0!=0: floats0,1,2 provide the reference point; integer1 then controls whether the direct-line test is skipped.
- float3 is the displacement distance. Exact ordered-zero value defaults to5.0 at0x4e38dd. This is not a robust finite-positive validation: wrapper must reject NaN/infinity/negative/too-large values itself.
- Direction is normalized `(target_position-reference_point)`. Proposed destination is target position plus direction*distance. The reference point is thus not a destination. Target orientation is set to negative direction via0x4cd170.
- integer1==0 takes native TestDirectLine0x4aee80 at0x4e39df. Return1 keeps destination; return0 replaces it with current position; other returns use the hit-info point. Nonzero skips this test: do not expose this as a safe strength option.
- Native handler allocates a16-byte XY start/end record, replaces the existing path buffer if present, sets path state+0x8c=4, path pointer+0x90, index+0x9c=0 on creature+0x340 controller; creature+0xa8c=4. Calls QuickWalk0x51d9c0 with1, then clones/applies a secondary effect. These fields describe observed engine ownership, NOT authorization for direct writes or malloc/free substitution.

Script constructors independently inspected: EffectForcePushed handler0x5349f0 sets type and creator but no distance. EffectForcePushTargeted handler0x534ab0 sets integer0=1, integer1 from script argument, floats0–2 from location; it also does NOT set float3. Therefore stronger distance is a native effect-configuration extension, not an existing script argument. Avoid directly calling the apply-handler in isolation: effect ownership, expiry and paired removal belong to the engine effect pipeline, whose complete native wrapper is not audited here.

## Movement and recovery

`0x51c0d0 WalkUpdateLocation_QuickWalk_ForcePushed`: ECX creature, no stack args (inspect final epilogue before installing a detour; captured range ends mid-epilogue). If creature+0xa8c==4, rate is constant25.0 from0x745e5c. Otherwise rate derives from XY path length *3.030303 at0x747d94. Rate multiplies creature DWORD+0xd0 and0.001; the DWORD behaves as elapsed milliseconds in this arithmetic but its writer was not audited. It calls WalkUpdateLocationDistance0x516630, UpdateSubareasOnMoveTo0x51b7b0 on the moving branch, and server SetPosition0x4cd1a0 with vector*,1,1,0. Native quickwalk owns movement/propagation; bypassing it with raw XYZ writes loses this behavior.

Progress branch updates creature+0xa90 and+a94; completion branch zeros+a90 and returns2 (otherwise1). These are observed state results, not proof the complete action controller returns to idle. QuickWalk caller dispatches to this routine at0x51e665. Longer float3 distance changes path extent; no new independent speed parameter was proven, and longer travel may exceed stock effect timing. Bound small and test expiry/recovery before escalating strength.

`0x4de400 OnRemoveForcePush`: RET8, two stack slots despite incomplete corpus one-parameter signature; only target argument explicitly read here. Converts creature, calls SetLockOrientationToObject0x4f34a0 with0x7f000000 and0, creates/applies another effect (type0x17, duration bits0x40233333≈2.55, integer0=-351). Do not label that effect as idle/standup from numeric type alone. It does not simply undo every controller field written by apply. Complete cleanup/interrupt/death/load interaction still requires downstream controller/effect lifetime proof.

## Required filtering and safe first implementation boundary

A hit observer must fresh-resolve controlled PC ID (verified resolver exists elsewhere; this pass does not re-prove it), match the attacker, convert the target to a creature, exclude self/party/dead/destroyed/cross-area targets, and retain current-session epoch. Do not infer these exclusions from ResolveRangedHit itself: it does not enforce the feature's policy. Party/death/native query sites and result-enum meanings remain required dependencies before enabling general enemy knockback. Recheck at actual delivery time, since a target alive during planning may die before projectile arrival.

Telemetry should correlate stock subattack execution with projectile creation/arrival and final damage commitment. Negative cases: miss/parry/reflection/NPC shooter/party/dead target produce no impulse; duplicate delivery produces no second effect; distinct burst/offhand hits remain distinct. Damage stays stock and is never reapplied by the mod. Movement acceptance must independently measure displacement, wall stopping, native client propagation, normal AI/action recovery, existing-force-push overlap, disable, death and load. Do not overwrite a stock force-push controller already active merely to amplify a duplicate hit.

Smallest truthful next step: instrument copied ranged/subattack outcomes and locate their execution consumer; separately prototype finite bounded native distance on owned disposable target using the normal effect lifecycle. Only join the two after timing and cleanup are measured. Physical whole-body rotation/bone physics remains the next explicit stage; this native knockback path has no demonstrated angular impulse, skeletal constraints or ragdoll pose writer.

## Private evidence

Original raw disassembly is retained only under `/home/brunner56/kp-live-20260922/projectile-research/`: ranged.asm, hit.asm, subattack.asm, postdamage.asm, push.asm, pushmove.asm, unpush.asm, effectpush.asm, effecttargeted.asm, quickwalk.asm. Some extraction ranges intentionally stop before a full function ending; do not use partial files as full relocation proofs. Prefix guards alone never prove a detour trampoline is safe.

Private evidence SHA256:
ranged.asm f3bd82250f88a1c71be17971e5a38bd3daa915bf5ef728136aaa99453fb5217d
hit.asm a03a4f33f80d9bffe1350122f27732965fd70e4ee0075ea678da4fd04fee87d8
subattack.asm fff464272caf92a6ff97ce7ad0b701c11c84d39a3b92b43eeb41243195fafdc8
postdamage.asm f714970cbf68602755d0360d201b5d1f2547131aa04d8c07640d4d8523d88228
push.asm ffaca7894a92d78b282f87f8c15aae4d878cd0aeb2567063dfa685a39bcac3d0
pushmove.asm 3c3cdcf9ce7b1983e456875a6db214ed07dc69cfb415e881170c071e69fe1c8b
unpush.asm 040b46135a6b6224b5b702c0229b8b8628d42fffb54bba6945a09e2ffd5a237e
effectpush.asm 7b8e00864a9dab7f7a0a8ac267418f949aefa8f500ba3f8471766ad4d2b6d05a
effecttargeted.asm 63b88d04c38470e0faf0cd89de046a3f9b93163cdd7202d04808769962af2f9d
quickwalk.asm 070eadca9603a97211e412303a0d81a7cb186ff178f7b0d4cdd123a96076674d

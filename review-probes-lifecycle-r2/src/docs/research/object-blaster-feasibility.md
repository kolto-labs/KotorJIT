# Console-configurable object blasters: bounded feasibility audit

Read-only source/corpus inspection, 2026-09-22. Worktree `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`; corpus `/home/brunner56/agentdecompile-nvme/corpus-work/corpus.sqlite` opened mode=ro. No builds, games, source edits, recovery jobs or subagents. Addresses below are exact corpus locators, NOT newly verified callable sites: no original-byte/stack/callsite audit was completed for these new projectile functions. Do not install hooks using guessed signatures.

## Finding

The requested feature has a plausible native route: substitute the model of the game's actual client projectile, preserving its trajectory/lifetime and attack identity. Existing public Lua facilities cannot yet implement that route. Spawning a footlocker near the PC on OnCreatureAttacked would not meet the request. All-PC-blaster coverage, burst/offhand multiplicity, misses, impact knockback and ragdoll-like tumbling remain explicit requirements.

## Current interfaces versus missing capabilities

| Requirement | Existing evidence | Gap |
|---|---|---|
| Observe attack-like events | `data/events.toml:266` OnCreatureAttacked carries creature/attacker; corpus evidence identifies outer0xF melee-attacked handling. | Not established as every ranged bolt, both hands or misses. Existing shout deduplicates by victim/game-second, which explicitly loses burst multiplicity. |
| Safe projectile event | `data/events.toml:519–532` OnCreatureBroadcastSafeProjectile, outer21, creature + attacker, nonblocking/Passthrough. Evidence resolves weapon ammunition and broadcasts a projectile. | No exposed projectile identity, weapon hand, spawn socket, hit/miss outcome, per-bolt sequence, model resource or replacement return value. Native typed event extension needed, after payload and cadence validation. |
| Visible model operation | `src/api/model.hpp` capture/resize/restore resolves creature model and scalar scale. | No model-resource swap, projectile capture, root rotation, bone transform or rigid-body operation. Do not stretch the creature capture type into a projectile pointer. |
| Animation | `src/api/animation.hpp` named-clip query/cue and rate controls. | Clip animation is not skeletal physical ragdoll, and no arbitrary bone pose/impulse API is exposed. |
| Placeable movement | Prior byte audit `/tmp/kp-native-motion-audit.md` identifies Win server CSWSObject::SetPosition0x4cd1a0, client readback setter0x63f340; fresh typed resolver/propagation contract. | No implemented motion module appeared in scoped src inventory. Floor-level relocation is not flight, collision, rotation, rigid-body simulation or an actual blaster projectile. |
| Push/knockdown | K1 routine catalog134 EffectKnockdown(),269 EffectForcePushTargeted(location,int=0),392 EffectForcePushed(). `scripts/examples/cursed/20_fus_ro_dah.lua` applies EffectForcePushed via explicit bridge. | No strength parameter on EffectForcePushed, no independently demonstrated large displacement in existing original-example ledger, and no ragdoll claim supported. |

## Concrete native projectile sites to extract next

Corpus func rows, binary_id8 `K1__k1_win_gog_swkotor.exe`, x86/32-bit. These are virtual addresses in the named image, not portable offsets or proof that Ghidra's parameter recovery is correct.

- **0x6d2c50 CSWCProjectile::LoadModel**: recorded `undefined4 __thiscall(this, CResRef*, byte, byte)`. Most promising model-resource substitution locus. Prove resource lifetime, both flag meanings, model ownership and return/error behavior before use.
- **0x6d2d30 CSWCProjectile::UnloadModel**: recorded void thiscall(this); second overload0x6d2db0 takes byte. Resource cleanup/swap ownership needs exact caller inspection.
- **0x6501b0 CSWCMessage::HandleServerToPlayerSafeProjectileProjectile**, recorded thiscall(this). Candidate creation path containing attack source/target and projectile parameters. **0x6631c0 HandleServerToPlayerSafeProjectile(this,byte)** dispatches the family; spell variant0x650b90 must be excluded unless explicitly enabled.
- **0x5bb590 CSWSCreature::ResolveRangedAttack**: recorded thiscall(this,CSWSObject*,seven int arguments). **0x5b49c0 ResolveSafeProjectile**: thiscall(this,four int arguments). Prove which fields distinguish main/offhand, burst count, misses, deflection and reflected projectiles; do not guess int flags from names.
- **0x4cdb00 CSWSObject::BroadcastSafeProjectile** and **0x56e5f0 CSWSMessage::SendServerToPlayerSafeProjectileProjectile**: server event/network bridge candidates. These must retain stock game damage/hit semantics; replacing visuals must not accidentally duplicate attacks.
- **0x6d6ee0 CSWCProjectile::SetProjectileType**, **0x6d33c0 SetProjectileVelAndAccel(Vector*)**, **0x6d7590 MoveProjectileToPosition**, **0x6d70d0 UpdateCurrentBehavior**, **0x6d7bc0 AIUpdate**: trajectory/lifetime research points. A function's name does not prove support for arbitrary geometry or collisions.
- **0x6d42a0 SetSpawnCombatVisualOnImpact(byte,int,short)** is impact-visual control, not established hit notification or impulse application. Avoid treating it as damage authority.
- **0x5ed5e0 CClientExoApp::GetProjectileByGameObjectID** and **0x5f1270 internal variant** are recorded typed projectile lookups. Verify server-to-client ID conversion and lifetime; never cache raw projectile pointers beyond a verified callback/capture scope.

MacK1 historical i386 locator parallels: HandleServerToPlayerSafeProjectileProjectile0x91292, ResolveRangedAttack0x1f06aa, SetProjectileType0xc99e6, SetProjectileVelAndAccel0xc5d48, MoveProjectileToPosition0xca13c, typed client lookup0x1e5d8/internal0x22470. Mac corpus signatures often say undefined and include generated thunks elsewhere; they are not callable ABI proof or current Steam Mac64 profiles. No MacK2 projectile equivalence audit completed in this bounded pass.

## Knockback and retained tumbling goal

Win corpus locators: OnApplyForcePush0x4e3800 (recorded stdcall(object,effect,int)), OnRemoveForcePush0x4de400, WalkUpdateLocation_QuickWalk_ForcePushed0x51c0d0; OnApplyKnockdown0x4d99b0 and OnRemoveKnockdown0x4d9c50. Native extraction should inspect destination, velocity/duration, collision/path constraints and controller state transitions. These could support stronger engine-owned root displacement than the parameterless bridge effect, but that is not proven yet.

No public rigid-body/ragdoll API exists in inspected src/api, and targeted func-name searches for Ragdoll/RigidBody in K1 Win/Mac returned no names. This does not prove engine-wide absence. It does mean physical ragdoll cannot presently be claimed.

**Retain ragdoll-like tumbling as a real implementation goal.** Two explicit stages are possible:

1. Native whole-body tumbling: freshly resolved actor/model root transform with position plus quaternion/rotation and controlled velocity, exclusive override of normal locomotion/animation for the owned impacted actor, swept collision or verified engine movement constraints, then reliable recovery. This is a rigid animated-body tumble, not limb ragdoll. Requires proving root-transform setter/child propagation, interpolation and controller handback; current uniform scale/clip APIs are insufficient.
2. Skeletal physics: map model bones to constrained rigid bodies; simulate gravity/angular/linear impulses and terrain collisions; write safe local bone transforms after animation or suspend the animation writer; preserve skinning hierarchy and reset/rebind on death/load/model changes. Requires verified bone layout/pose-write pipeline, collision data provider, animation ownership and a physics solver. A standalone physics library alone does not integrate with game skinning or collision. Prototype on owned disposable enemies before any generic enemy opt-in.

Do not replace these stages in the product claim with EffectForcePushed/knockdown. Those can be a labelled interim impact response only. User-visible wording must say whether the currently demonstrated result is knockback, whole-body tumble or physical skeletal ragdoll.

## Minimal truthful implementation and acceptance

First bounded implementation should prove a complete native projectile chain on verified WinK1: observe actual projectile creation, associate PC shooter and attack/hand/bolt identity, resolve a locally installed allowed model resource, replace the actual projectile's visual before first display, then preserve stock flight/miss/impact/destruction behavior. Footlocker resource/appearance mapping must come from the user's installed assets or a trusted resource query; no arbitrary guessed model name and no game asset redistribution.

Expose proposed scoped console configuration (not an existing API), e.g. an object-projectile module with configure/status/disable, using the shared Console service and engine-thread mutation boundary. Settings should be immutable snapshots/versioned per spawned projectile so changing the selected resource mid-flight affects new shots predictably. Validate resource/type and finite scale/impulse bounds before enabling; cap concurrent replacements and clean up on disable/load/exit without touching unrelated objects. Missing resource/build/ABI must leave stock shots unchanged and return a specific unavailable/error outcome.

Acceptance matrix must include single pistol, dual pistols, rifle/heavy/repeating variants available to the current PC, rapid/burst attacks, misses, blocked paths and any deflection/reflection routes. Record actual engine bolt IDs/cadence and correlate each PC projectile with replacement count: zero duplicates, zero missed supported bolts, no NPC/melee/spell replacement. Show a continuous camera-stable muzzle-to-target trajectory and stock bolt suppression, not a crate spawn near the player. Two rapid console-selected resources must take effect on subsequent shots without restarting.

For impacts separately correlate actual hit authority once per hit, independently measure target displacement/velocity/state, and verify miss/party/dead/non-PC exclusions. Track no repeated damage, no stuck action queue, no wall tunnelling, no leaked projectiles and recovery/cleanup after disable. Add tumbling only with independently measured root/bone motion and reliable recovery; retain that milestone as pending if only knockdown is implemented.

Public host tests can use synthetic callback records and resources for identity filtering, burst multiplicity, hand selection, ownership, resource rejection, allocation failure, configuration changes and cleanup. Actual all-blaster/native visual/impact proof still requires serialized live acceptance. New corpus/source payloads are private analysis inputs under the no-retail-assets publishing constraint and must not be copied into browser/public artifacts.

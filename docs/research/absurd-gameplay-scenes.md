# Absurd gameplay demonstrations

The user rejected the rave recording: flashing effects obscured the actors and did not communicate the purpose of the integration. It is a rejected showcase candidate even though its route predicates passed. Increasing the frame rate did not fix its content.

The creative target is recognizable game behavior made absurd through live control of models, animation, objects and time. A viewer should understand the change with the caption removed. These are implementation targets, not claims of working capabilities.

## Historical grounding

[Chaos Mod V's original changelog](https://github.com/gta-chaos-mod/ChaosModV/blob/master/CHANGELOG.md) records tiny vehicles, doubled animation speed, mannequins, moving props and disassembled vehicles. The transferable idea is changing familiar objects and behavior in a visually legible way. KotOR has different animation and movement systems; those effects do not establish that it supports GTA-style physics.

[KK's Disguise Armband](https://deadlystream.com/files/file/808-kks-disguise-armband/) demonstrates KotOR's history of selecting character head/body combinations through disguise effects. A new Lua scene should expose the timing and composition of transformations and identify its NWScript bridge use honestly.

[The enlarged creature-model discussion](https://deadlystream.com/topic/5384-enlarged-creature-models-in-kotor-1/) explains static model scaling and inherited animations, including combat-alignment limits. Our native scale operation instead changes a loaded model through its engine setter. It still needs visual and child-model validation.

## First scene collection

| Scene | Immediate visual joke and sequence | Capability and acceptance |
| --- | --- | --- |
| Size dispute | Two matching Sith face each other. One becomes knee-high; the other towers over it. They swap sizes, then return to normal. | Native model scale. Same actor identities throughout, per-phase base/effective readbacks and full restoration. Avoid ceiling clipping. |
| Pocket monster | A large creature shrinks beside a humanoid; a small creature grows taller than that humanoid. Hold the absurd pair in the same frame. | Native scale plus explicit NWScript creature setup. Peaceful actors only; verify supported animation/model loading and clean up only owned identities. |
| The wrong body | One stationary NPC changes between three unmistakably different creatures, then recovers its original body. A second unchanged NPC supplies a reference. | Explicit NWScript disguise, with fresh native model resolution after every change. Confirm appearance and object identity separately; do not call this native animation injection. |
| Malak nesting dolls | Three Malaks form a staircase of sizes. The large one shrinks while the small one grows, leaving the center unchanged. | Native scale, owned actors and a staged reference. A distinctive silhouette carries the joke without VFX. |
| The furniture follows you | A crate trails the player through a short L-shaped path, stops when the player stops, then returns home. | New typed native placeable movement. Verify server/client positions; separately test interaction and collision at old/new locations. No physics claim from coordinates alone. |
| Reluctant furniture delivery | Three crates line up, travel to marked destinations one at a time, and park around an unchanged NPC. | Same placeable operation, deterministic trajectories and bounded lag tolerance. Keep all paths in view. |
| One actor missed the pause | Three identical actors perform a clear gesture. The middle actor freezes mid-gesture while the others finish; it resumes afterward. | Per-model animation time/rate control under investigation. A global game-speed change is insufficient. Require actual animation/time readback and visual pause/resume. |
| Rewind the Sith | Two actors perform the same recognizable movement: one forward, one backward. Reverse their roles once. | Native animation playback with negative-rate semantics only if verified. No reversed video; the recorded game must render both directions simultaneously. |
| Synchronized incompetence | Four actors repeat distinct gestures with a deliberate delayed wave, stop together, then perform one final synchronized gesture. | Distinguish queued NWScript animation from direct native channel control. Verify actual clip/time where available; logging requests is insufficient. |
| Identity crisis lineup | Three different creatures exchange appearances while retaining positions and identity labels. Restore every original appearance. | Explicit NWScript transformation choreography plus native identity refresh. Model replacement must invalidate old captures. |

## Capture and presentation acceptance

- Use a steady camera and ordinary lighting. Exclude flashes, fades, explosions, camera shake and combat clutter.
- Start the selected clip at the first defining change. Show a reference character or object so scale and motion are legible.
- Hold major states for roughly two seconds. Keep each finished clip to one clear joke, normally 10–20 seconds.
- Capture actual game frames at 60 fps. Retain continuous source video and inspect cadence; encoded frame rate alone is insufficient.
- Preserve a clean landscape master. A portrait export may add a short truthful caption, but must not crop out the defining action.
- Verify behavior, cleanup and media separately. Reject a visually unclear clip even if the test passes.
- Keep native operations under `kp`, NWScript calls under `nwscript.call`, scene logic in Lua and routes in harness TOML.

## Current proof boundary

Native scale now has two successful Dantooine player runs (17 and 18 route gates), including six independent base/effective scale readbacks and original restoration. The second run held the camera steady. Both are rejected as final showcase footage because the enlarged player extends above the frame. The first Endar PC lookup failure exposed an incorrect client-ID sentinel assumption; its code correction has an original-engine-byte regression, but that exact Endar PC case still needs its own successful live retry. Native animation control and placeable motion have researched engine sites but no completed live implementation. None of those research findings should be presented as finished demonstrations.

Native animation details and exact guarded sites are recorded separately in [native-animation-sites.md](native-animation-sites.md). Additional researched scene concepts are in the controller report `/tmp/kp-absurd-scenes.md`; its old `kp.as` spelling is obsolete and must be `nwscript.with_caller` in any implementation.

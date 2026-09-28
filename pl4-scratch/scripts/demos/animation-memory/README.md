# Two actors, one frozen native clock

Load `two_actor_freeze.lua` in a peaceful K1 scene and set PC local number5 to8.
Two identical friendly, command-disabled Sith troopers appear six units ahead,
1.5 units to either side. After a short `pause1` baseline, both play `dance` at
half rate. Actor A freezes at one third of the clip while B continues; A resumes
when B reaches80%. Both then return to the known `pause1` baseline and are removed.
This is a single finite sequence, not repeated animation requests or a VFX effect.

Use the creative driver's `--script scripts/demos/animation-memory/two_actor_freeze.lua`
and `--route scripts/harness/scenarios/animation-memory/freeze.toml` with the usual
owned source/stage/prefix/build/checkpoint arguments. The supplied route uses
`endar_room3`; a reviewed outdoor checkpoint variant can improve framing.
Camera setup belongs to the recording driver. Do not assume NWScript camera yaw
frames the actors. Capture continuous real60fps footage and review both full bodies,
the held pose, continuing comparison actor, and resumed movement before calling a
clip suitable for presentation. Encoded60fps and native clock assertions alone do
not prove a visible pose or rendering cadence.

The route independently captures the new actors, samples both clocks, observes12
client ticks, requires one unchanged clock and one progressing clock, then checks
resumption, baseline reset, and removal. A missed short phase fails the route; it
must not be relabeled as a Lua defect without diagnosis. Local6 is phase1..7;
local7 records completion, local8 failure, local9 actor count. These local numbers
are scene coordination only, not independent native effect evidence.

Ownership is captured immediately after each spawn, before model readiness. Every
active tick checks context, ownership, model identity, and noncombat state. A
replacement, controller override, absent clip, ignored pause, or timeout fails
closed. Cleanup refuses changed identities/context. It cannot promise removal if
that refusal or an engine deletion failure occurs. Unload restores the prior
local6..9 values where the original context still matches.

`pause1` is a deliberate known baseline for disposable actors. The API does not
capture or restore an arbitrary prior animation stack, blend weights, or callbacks.
Host fixtures exercise actual Lua with controlled independently advancing clocks;
real native ABI, visual pose, and Mac execution need their own live evidence.

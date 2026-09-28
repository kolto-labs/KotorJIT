# Native model animation API

`kp.animation` calls verified client-model animation methods directly. It is
separate from `nwscript.call`; scene spawning and faction setup still use the
explicit NWScript bridge. Binding requires the exact model image SHA, loaded base,
OS/ABI, pointer width, and guarded animation code bytes. Darwin32 and Darwin64
calling adapters are implemented, but the current runtime has no Darwin loader:
this does not claim macOS runtime or live animation support.

```lua
local owner = assert(kp.model.identify(actor))
local capture = assert(kp.model.snapshot(actor, owner))
local s = assert(kp.animation.inspect(capture, "dance"))
assert(s.available and s.duration > 0)
assert(kp.animation.cue(capture, "dance", 0.5, 0)) -- new run
-- On a later tick, after confirming progress:
assert(kp.animation.cue(capture, "dance", 0))      -- preserve clock, pause
-- Later:
assert(kp.animation.cue(capture, "dance", 0.5))    -- preserve clock, resume
```

`inspect(capture, clip)` returns `{available, active, time, duration, units="seconds"}`.
A valid inactive clip has `active=false,time=-1,duration>=0`. An absent clip has
`available=false,active=false,time=-1,duration=-1`. The engine's run pointer is
consumed only as a Boolean; no raw animation pointer is retained or exposed.
Every operation freshly resolves the protected model capture and checks identity.
The existing identity protection is pointer/context comparison, not an invented
engine generation counter.

`cue(capture, clip, rate [, start])` returns the immediate observed state or
`nil,error`. Rate must be finite0..2. Start must be finite, nonnegative, and below
clip duration. Omitted start begins a new inactive run at0, or preserves an active
run's clock. A different explicit start on an active run is refused: seek/restart
is not exposed. Clip names are1..31 ASCII letters/digits/underscore; `NULL` and
`current` are reserved case-insensitively. Empty/NUL-containing names, absent or
zero-duration clips, negative/reverse rates, and arbitrary flags are rejected.
The fixed policy is flags2, without force-new0x40.

A successful cue proves only immediate active clock/duration readback. The actor
controller may replace it on a later frame, and a clock is not a rendered pose.
Call `inspect` on later ticks to validate progress, pause, and resumption. Never
repeat cues to hide an override. `capabilities().available` reports binding;
individual operations recheck code and captured identity before native access.

The four profile address/ABI sources are documented in
[the byte audit](research/native-animation-sites.md). Guard comparison includes
rebasing the Mac K2i386 absolute canary-load operand rather than ignoring it.
Original model profile hashes remain authoritative; animation has no hash bypass.

Run `kp_animationtest`, `animation_scene_test`, and the creative harness tests for
controlled host coverage. These cover all four layouts, call contracts, rejected
inputs, stale/forged captures, clock-preserving pause/resume, native readback failures,
and actual scene lifecycle failures. They do not execute a Darwin engine or prove
an injected model's visual pose. Attach source/DLL/route hashes, independent clock
samples, and continuous raw footage to a live receipt before asserting live success.

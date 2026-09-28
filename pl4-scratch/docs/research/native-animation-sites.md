# Native model animation audit and implementation brief

Date: 2026-09-22. Scope: read-only source/corpus/original-byte inspection, followed by this explicitly requested report write. No repository changes, games, live memory calls, imports, builds, or recovery jobs were performed.

## Decision

The smallest grounded capability is named client-model clip playback and playback-state queries through `Gob::PlayAnimation` and `Gob::GetAnimation`. This is native animation control below NWScript, not `ActionPlayAnimation`, an effect, disguise, VFX, or world-time manipulation.

Windows K1 GOG has original-byte evidence for the getter, setter, and clip-clock arithmetic. Corresponding Mac functions exist, with verified entry ABIs and detailed K2 i386 recovered pseudocode. This is implementation grounding, not a claim that a live rig has already accepted or retained an injected clip.

## Original image identities

All addresses below are preferred-image virtual addresses. Add the verified runtime image slide. Windows preferred base is `0x400000`; old Mac i386 is `0x1000`; Mac K2 x86-64 is `0x100000000`.

| Build | Original image | SHA-256 |
|---|---|---|
| Windows K1 GOG i386 | `/home/brunner56/biodecompwarehouse/kotorxid/output/binaries/K1__k1_win_gog_swkotor.exe/artifacts/raw_image` | `9c10e0450a6eeca417e036e3cde7474fed1f0a92aab018446d156944dea91435` |
| Mac K1 i386 | `/home/brunner56/biodecompwarehouse/kotorxid/output/binaries/K1__k1_mac_swkotor.app/artifacts/raw_image` | `aa6283733d3c738d11d12453f77dfc6b7e87f95326a07ee97daab1a37734b032` |
| Mac K2 i386 | `/home/brunner56/biodecompwarehouse/kotorxid/output/binaries/TSL__k2_mac_swkotor2.app/artifacts/raw_image` | `f14f285b1b6ed7e4bf000fe19ebcd0d6528d1d3e86d2832be6092761557c130d` |
| Mac K2 x86-64 | `/run/media/brunner56/MyBook/Workspaces/ai-projects/AgentDecompile/target/imports/2026-09-08-nwn-kotor/slices/1c536c3ef2e8bed348b38934b381e3dc427f3ebee21faddfbd7524fbb2388d77/KOTOR2sub.x86_64` | `469067c416f1a3ff391df73c7ace2d44a8d0a246253e8ad5752f6413ea033be4` |

Hashes were computed earlier in this same audit session; entry bytes below were reread directly. Corpus database `/home/brunner56/agentdecompile-nvme/corpus-work/corpus.sqlite`, binary IDs 8, 5, 19, 83 respectively. The old Mac K1 i386 profile is not evidence for the newly discovered Steam Mac depot's possible 64-bit executable.

## Callable sites and ABI

| Build | Gob::PlayAnimation | Gob::GetAnimation |
|---|---|---|
| Windows K1 GOG | `0x485bd0` | `0x484d20` |
| Mac K1 i386 | `0x2e10a2` | `0x2de5c6` |
| Mac K2 i386 | `0xff606` | `0xffbac` |
| Mac K2 x86-64 | `0x1000ec558` | `0x1000ecb4c` |

Semantic signatures:

```cpp
int play_animation(Model* model, const char* clip_name,
                   float playback_rate, int animation_flags,
                   float start_time_seconds);
AnimRun* get_animation(Model* model, const char* clip_name,
                       float* current_time_seconds,
                       float* duration_seconds);
```

Windows: model is ECX. Playback has four stack arguments and `ret 0x10`; query has three stack arguments and `ret 0x0c`. Query returns its active-run pointer in EAX. Original playback success epilogue at `0x486081` sets EAX=1 and returns at `0x48608d`; do not rely on the catalog's summed instruction size as a contiguous function endpoint.

Mac i386: explicit stack `this`, name, and remaining arguments; caller cleanup. Do not use Windows ECX-this based on Ghidra's generic `__thiscall` label.

Mac x86-64 playback: RDI=model, RSI=name, XMM0=rate, EDX=flags, XMM1=start time. Entry code saves these exact incoming registers. Query: RDI=model, RSI=name, RDX=time-output address, RCX=duration-output address, RAX=active-run result.

The name is a NUL-terminated input C string. The two query outputs are individual 4-byte float buffers, not strings, arrays, or returned vector structs. Allocate and initialize both local floats before the call; keep their storage alive for the entire synchronous call. Do not let Lua pointers or unvalidated addresses become output arguments.

## Query semantics and meaningful predicates

Windows original `Gob::GetAnimation` and K2 i386 pseudocode agree:

- Active named run: non-null return; time output is that run's playback position; duration comes from its animation metadata.int play_animation(Model* model, const char* clip_name
- Existing but inactive clip: null return; time=-1; duration is the model clip length.
- Absent clip: null return; duration=-1 (and time=-1).
- Names are compared case-insensitively by the engine.

Use duration > 0, finite, as the initial playable-clip prerequisite. Zero duration should be rejected for this demo even though the higher-level `AnimationExists` helper accepts duration >= 0. Do not confuse null return with absent clip: a valid inactive clip still has a nonnegative duration.

The native query uses seconds. `CSWCAnimBase::GetAnimationTime` multiplies the underlying output by 1000, so that different helper uses milliseconds.

No active-run pointer should escape into the Lua API or be dereferenced after the call. A native ownership token may compare a newly returned pointer against its prior identity, but must re-resolve the current actor/model and requery before doing so; pointer equality alone is not a full generation guarantee.

## Rate/time structures and pause evidence

Windows K1 Gob active-run list pointer is `model+0xb0`, count `model+0xb4`. The query reads the run clock from `AnimRun+0x10` and clip duration from the animation metadata at `+0x50`. Playback writes its supplied rate into `AnimRun+4` at VA `0x485ece`.

Windows `Gob::Animate` VA `0x486670` contains the independently read instructions:

```text
0x486b01 fld  [frame_delta]
0x486b08 fmul dword ptr [run+4]
0x486b0b mov  edx,[run+0x10]
0x486b0e mov  [run+0x0c],edx
0x486b11 fadd dword ptr [run+0x10]
0x486b14 fst  dword ptr [run+0x10]
```

Thus the run's own rate, not global game speed, controls clock advance. A zero rate has genuine per-run pause semantics at this layer. The K2 i386 recovered `Gob::Animate` performs the same `current += rate*delta`, with previous time at +0x0c/current time at +0x10 and explicit negative-rate wrap logic. K2 i386 Gob list offsets are +0xdc/+0xe0; K2 x86-64 query entry shows list pointer +0x110/count +0x118. Do not extrapolate 32-bit AnimRun field offsets to 64-bit without separate evidence.

Do not implement pause by writing these fields. They are behavioral evidence; use the playback method so the engine maintains its lists and callbacks.

`CSWCAnimBase::SetAnimationInternal` normalizes rate zero to one. Therefore the higher-level `CSWCAnimBase::SetAnimation` entry is unsuitable for a direct zero-rate pause demo. `CSWCCreature::SetSWAnimationSpeed` merely stores two creature fields in the inspected implementation; no claim of reliable clip pause is grounded through that method.

Negative time integration is evidenced, but negative-rate rig playback, endpoints, event ordering, and visible correctness have not been verified on Windows. Do not expose negative rates in the initial API/demo.

## Flags and bounded argument policy

There is a concrete engine callsite in K2 i386 GUI model setup that invokes the model's animation virtual method with `("pause1", 1.0f, 2, 0.0f)` (pseudocode lines 376159 and 376164). This is the initial supported argument pattern, not proof that every actor has that clip.

The recovered playback implementation shows:

- Flag bit 0x2 controls whether the new run is initialized into the clip's fade/blend ramp. Use fixed flags=2 initially; do not label arbitrary integers as supported channels.
- Flag 0x40 bypasses normal named-run reuse and can create/restart a run. Do not use it for pause/resume or a timer-based keepalive.
- Flag 0x80 selects targeted removal of the matching/current run, with completion callbacks and deletion. See cleanup limitations below.
- Other bits affect overlays, deferred playback, reuse, or fade behavior. They are not sufficiently specified for general public exposure in this first slice.
- Null name, empty name, or case-insensitive `NULL` clears animation runs. Reject these as playback names.
- `current` is a special engine selector for an existing run, not an ordinary asset name. Reject it in the initial public playback operation.
- Start time is wrapped against clip duration using a loop. Require finite duration > 0 and `0 <= start < duration` to avoid pathological/zero-duration behavior.

Proposed initial wrapper bounds (implementation policy, not inferred engine limits): normal ASCII clip identifiers of 1–31 characters, rate in [0, 4], fixed flags=2, finite start in [0,duration). A 31-character cap leaves room in the observed 64-byte callback-name buffers for prefixes such as `done`. For the demo use rate 1, then 0, then 1; no negative rates.

Before playback, query the actual model for the clip. `pause1` is an evidenced name. A distinct gesture/full-body clip must come from actual model assets or successful query probes; dance/taunt names must not be promised without that check.

## Controller overwrite: established risk, not solved by command disabling

K2 i386 `CSWCCreature::AnimationUpdate` (pseudocode line 382515) rotates and moves the creature, invokes looping animation selection for nonstationary animation, runs `AnimateFireAndForget`, and conditionally selects pause/injury animations. There is no universal commandable-state guard around this function.

`DriveAnimationUpdate` (line 382587) has additional state/creature guards and can choose animation updates from drive state. The presence of these routines means server command disabling alone does not prove that a Gob cue survives the next client frame.

For the first demo, command-disabled owned NPCs in a noncombat stationary state are a reasonable bounded test setup, not a guarantee. Invoke native playback once, then query only for several frames. Require the same named active run with monotonically advancing time. If the normal controller replaces it, fail the demonstration and report that a scoped actor-controller ownership mechanism remains necessary.

Do not fix overwrite by repeatedly restarting the clip every timer tick. That would fake persistence and may keep the clock near zero. Do not modify world time, globally disable Scene animation, or stop ordinary animation on unrelated actors.

## Cleanup and restoration limits

There is no independently verified universal `StopAnimation` public method in this audit. `StopOutOfOrderAnimation` exists, but it is for the separate out-of-order animation path and should not be substituted for ordinary named playback cleanup.

K2 i386 `Gob::PlayAnimation` flag 0x80 finds a matching run, removes it, emits `done<clip>` behavior callbacks, clears associated custom-animation links, and deletes the run. This is real targeted stop logic, but callback/reentrancy and exact Windows stop behavior require a bounded follow-up before public exposure. Do not claim that stopping one clip restores the prior entire animation stack.

`GetAnimation(name)` does not enumerate the current stack, return the original clip name, rate, flags, blend weights, callbacks, or queued state. Therefore it cannot capture and restore an arbitrary preexisting actor's complete animation state. Saving only time/duration is not lossless restoration.

For the first scene, use two explicitly owned disposable NPCs. Establish their known baseline clip (`pause1` if present) before the trial. Returning each to that known baseline is scene reset, not restoration of arbitrary original state. Destroying only those owned NPCs after the recording is also acceptable cleanup. Never destroy player/party/unowned NPCs to conceal cleanup limitations.

If the first API offers an ownership token, it should bind actor ID and current model generation, reject external changes, and report scope loss rather than attempt rollback into a replaced object. Preserve independent world/actor state; do not promise whole-stack capture until native stack enumeration and safe restoration are separately implemented.

## Proposed stable-camera two-actor acceptance scene

1. Spawn or select two explicitly owned disposable NPCs on clear ground, stationary and outside combat/dialog; fix camera position/framing. Keep model scale, appearance, position, lighting and global time unchanged.
2. Query baseline `pause1` and an asset-derived distinct gesture on each model; require finite positive duration. Reject missing names rather than silently falling back.
3. Put both in the known baseline via native playback. Start actor A's gesture once, then actor B's gesture once after a visible stagger.
4. While both run, query each named clip at several frames. Require active=true and advancing time, with no repeated playback commands.
5. Pause actor A by reusing its named run with rate 0, fixed flags=2; keep actor B at rate1. Require A's clock to stay stable over ~2 seconds, B's clock and independent client/frame counters to advance, and the camera/world to remain live.
6. Resume A at rate1. Require its clock to advance from its held region and visible movement to resume. Do not expose reverse in this first run.
7. Reset to known baseline or destroy only the two owned NPCs, verifying no actor/token references remain.

Record one continuous shot containing the same actors throughout. Positive proof: named runs active, advancing/frozen/advancing clip times, independent live client ticks, visible distinct poses. Negative tests: missing clip, invalid actor, nonfinite rate/time, reserved/empty name, stale/replaced model. If ordinary animation control overwrites the cue, report failure rather than masking it with repeated restarts.

## Current API and source evidence

Scoped existing `src/api/model.cpp`, `entity.cpp`, `compat.cpp` had no exposed native named-clip control. `model.cpp:67` already validates the current animation/model resolution span, which is reusable. Keep the native API module independent of NWScript and harness driver ownership.

Detailed recovered source:

`/home/brunner56/biodecompwarehouse/kotorxid/output/binaries/TSL__k2_mac_swkotor2.app/analysis/ghidra_cexport/TSL__k2_mac_swkotor2.app.c`

- 170769: Gob::PlayAnimation, flags, run reuse/deletion and callbacks.
- 171013: Gob::GetAnimation query outputs and absent/inactive distinction.
- 170510: rate/time integration and blend progression.
- 329633: CSWCAnimBase::SetAnimationInternal normalizes zero rate.
- 376159, 376164: model `pause1`, rate1, flags2, start0 callsites.
- 382515: CSWCCreature::AnimationUpdate can replace client animation.
- 382587: DriveAnimationUpdate state-dependent animation control.
- 389126: SetSWAnimationSpeed writes creature fields only.

Pseudocode has known type/decompiler errors; exact ABI and critical Win behavior above were checked against original bytes. Names/symbol identities came from the bounded SQLite catalog query. Do not turn placeholder generated struct declarations into memory-layout authority.

## Exact 32-byte entry guards

The following hashes cover exactly the first 32 original bytes at the listed VA. They are not whole-function hashes; catalog `size` can exclude instruction gaps. Relocations/ASLR must be handled when comparing runtime bytes, particularly Mac i386 prefixes containing absolute loads.

### Windows K1 GOG

Play `0x485bd0`:
`81ec48010000538b9c2450010000555633ed3bdd578bf10f8436040000803b00`

SHA-256 `6272cd9a9d49793fb45e4255a33118a6f0fcf5284e30029777e674547669b638`

Query `0x484d20`:
`53558b6c240c568bf18b86b40000005733db33ff85c07e2feb068d9b00000000`

SHA-256 `24626d9840470c9866b3cae79b1881850eb4adfbb898f06c70f88748fc5dcb12`

### Mac K1 i386

Play `0x2e10a2`:
`5589e557565381ec4c0100008b5d0c85db74208b450c803800741889442404c7`

SHA-256 `406b6dd735956f33e670e3ad3746aa6db0b6425b5c5aa725eea2650398a9cf3d`

Query `0x2de5c6`:
`5589e557565383ec1c31f631dbeb3e89df8b450c894424048b55088b82b00000`

SHA-256 `6b0a01e63cdb1610bab64fd90d6f8d4bbeb74625a6a0c3b16fa6c0215177e5d8`

### Mac K2 i386

Play `0xff606`:
`5589e553575681ec6c0100008b4d0c8b7d08a128c055008b008945f085c97478`

SHA-256 `99d3b0177b951e38507cadde763384f867d5093dae3ce8fc0f657de6568c5176`

Query `0xffbac`:
`5589e553575683ec0c8b5d0c8b750883bee0000000007e5331ff8b86dc000000`

SHA-256 `6858bb6db7eb312a4b50c4adfe2d157e7617f24cdb3ac1b3741347f2d602ddb9`

### Mac K2 x86-64

Play `0x1000ec558`:
`554889e54157415641554154534881ec68010000f30f118d80feffff89d3f30f`

SHA-256 `458ec8c747ff2d2e65253a441364554f83dfecaa7eb932577be15809242c2f07`

Query `0x1000ecb4c`:
`554889e5415741564155415453504989ce4989d74989f44989fd4183bd180100`

SHA-256 `e1731eb4b0ecddd2222e611a7e9002d8dbfe8eb49bbec1d49f132734f0fba02c`

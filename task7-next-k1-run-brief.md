# Next Task 7 K1 creative acceptance run — preparation only

Prepared 2026-09-27 from the current supported runner. **No launch was made.**
Only this brief was written; no worktree or product file was edited. All commands
below are for a later authorized execution, not commands executed by this brief.

## Selected scenario and exact claim

Use one peaceful, finite **player model scale** scene: original 1.0 → 0.35 →
2.40 → original 1.0, then restore all scene-owned local slots. Construct and arm
it through real owned-window F12 keyboard input, observe each phase through
independent native readbacks, and record the visible sequence in one unaltered
exact-window master. This establishes physical-console/native-model integration
for this exact candidate; it does not establish every example or Doppelganger.

Do not select the present `cursed/70_doppelganger.toml` for this run. Its steps
use `assert_lua`, not physical `console_command`; its fixture deliberately seeds
hostile baseline appearance P before the script adds its own P disguise. The
owned-token delta can therefore be correct with no visible hostile appearance
transition. It also requires three living combat fixtures and Endar checkpoint
state. Those are useful effect-ownership tests, but add dependencies and do not
visually isolate the requested physical-console behavior.

The selected private route below uses existing supported `kp.model` operations,
`kp.registertimer`, `console_open`, `console_command`, `assert_lua`, `await_log`
and `advance_ticks`. The shared helper is an existing frozen artifact; it is not
copied from an old harness snapshot. This shortened route is **new preparation,
not a previously accepted run**. Earlier native-scale/F12 evidence used older
DLL identities and must not be carried forward as current acceptance.

## Evidence and inputs verified during preparation

Current display-only prerequisite:
`/home/brunner56/kp-live-20260922/task7-display-only-topology-gate-report.md` records
one successful installed display-only run at
`display-only-runs/20260927-100845-8cd691c3`. It proves the reviewed subreaper,
adopted Xwayland, both no-cookie transports, 1024×768 hardware renderer and
cleanup. It proves no game/window/F12/media behavior. Build a new snapshot for
this creative run; do not reuse that display-only snapshot blindly.

The following hashes were recalculated from current files, not merely copied
from a prior receipt:

| Input | SHA-256 |
| --- | --- |
| `/home/brunner56/kp-console-protocol-20260927/build/kphasor.dll` | `fd8e069a1ff5a7b489f32a6492222f396f85e7b74539deb56228395b297dfac2` |
| `/home/brunner56/kp-console-protocol-20260927/build/binkw32.dll` | `1b25f37125237aefb67271533f88c48dcf07ddd37bf180743a3b0dfa2ff729d9` |
| `/home/brunner56/krayt/tmp/k1_harness/swkotor.exe` | `9c10e0450a6eeca417e036e3cde7474fed1f0a92aab018446d156944dea91435` |
| `/home/brunner56/kp-live-20260922/frozen-model-393f68d/model_scene.lua` | `07c533c28bb588507b473918b90abdb1a440d6099083155e7a86cfff32584a0e` |
| Worktree and candidate-source `data/addresses/k1_gog_103.json` | `44a5984b71bf994dd5ee520e49198ced4953a3ff2e385673e9264a44ee36d4f2` |
| Worktree and candidate-source `data/addresses/k1_steam_103_unpacked.json` | `541c5c3e7890406ce08d2959ed90cd3a97eee8974ceff6d34ae8522ccb7182c5` |

Both DLLs match `/home/brunner56/kp-console-protocol-20260927/build-artifacts.json`.
Retain that manifest, `baseline-source-provenance.json`, `reviewed-overlay.json`,
`build.log`, and the selected build hashes in the new preparation directory.
The source provenance names base commit
`ca329e52dd27d1a3f5a56748d93c8ab0fd7f24f2` plus reviewed overlays; do not represent
the DLL as a clean build of the current dirty worktree or a verified public
release package. `session.stage()` copies address tables from repository context,
so hash the selected K1 tables before launch and after staging as well.

Selected source save: `/home/brunner56/krayt/tmp/k1_harness/Saves/000001 - AUTOSAVE`.
Its current identities are:

| File | SHA-256 |
| --- | --- |
| `GLOBALVARS.res` | `fcdab52917af2125e7349609ad1a8b11f2f07f13705f48fb1298bd6cf7828e07` |
| `PARTYTABLE.res` | `f380d0217e2db39d105b6851cd2fce4b48258291e68c654d822e4694820a2477` |
| `SAVEGAME.sav` | `d879c65a63144a8668c1b7c566cb47fb3d66af3da0721d486701d4b2ace95bae` |
| `pifo.ifo` | `a181c82c1a8d74d79344df5c8e99d9b277517f5fc048eccca39e82bea1b14676` |
| `savenfo.res` | `d4d04f597d279266ebcd2ceb8a1917524f68e0dac780994eba6280e0b24b4c39` |

A retained older run `stage-k1/runs/20260922-133724/report.json` loaded this save
name into `danm14aa`, near (105.676,96.464,0.996), with one healthy PC and gameplay.
That is historical context. The new run must independently require `danm14aa`,
valid living PC, gameplay/main_menu=0, bound VM, no combat/conversation, native
model support, base scale 1.0, and stable model/creature/module/area identity.
Fail rather than pick another save or reposition through an ad-hoc recovery.

## One attempt, new private paths, preserved source

Choose one unique preparation ID, for example `20260927-task7-scale-<UUID>`.
Set these absolute paths, all new and disjoint:

```sh
KP_TASK7_ROOT=/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation
KP_TASK7_PREP=/home/brunner56/kp-live-20260922/next-k1-preparations/20260927-task7-scale-<UUID>
KP_TASK7_SNAPSHOT="$KP_TASK7_PREP/harness-snapshot"
KP_TASK7_ROUTE="$KP_TASK7_PREP/physical-native-scale.toml"
KP_TASK7_OUTPUT="$KP_TASK7_PREP/runs"
```

Use `stage-k1`, `wineprefix-k1`, and `checkpoints-k1` beneath that preparation
directory, never any old stage/prefix. Refuse a nonempty preparation target.
The runner's canonical lock is exactly:
`/run/media/brunner56/MyBook/Workspaces/KotorPhasor/tmp/harness-locks/live-game.lock`.

Preflight is read-only until new private artifacts are created. Recheck free
space, memory/swap, the lock, all game/Wine/Gamescope/FFmpeg ownership, and
protected X0/X94/X100 endpoints. Refuse conflicting workloads; do not kill them.
Record protected endpoint identities/listener rows and historical quarantines
from the successful display-only report. Never remove or restore those old
quarantine entries. Do not infer a free display number from old evidence.

The creative runner itself acquires and holds the canonical flock in the same
single-purpose process that becomes the subreaper, through teardown. **Do not
wrap its invocation in a second independently acquired flock:** that would make
its own lock acquisition fail. The separate display-only supervisor needed
`pass_fds`; this supported creative path holds its own FD already. A preflight
lock probe must release its probe before invoking the runner. Its acquisition
closes the race by refusing another cooperating runner.

Hash source preservation scope before and after: executable, INIs, runtime/
proxy, logs, saves, Override, and source Lua. The supported runner supplies
`source-before.json`, `source-after.json`, source/input unchanged predicates and
frozen deployed inputs. Independently retain hashes for the save, address tables,
DLL manifest, exact private route and helper; compare the deployed DLLs and
helper with their selected originals. No source save writes, export, checkpoint
replacement, or source-tree cleanup is authorized by this brief.

## Materialize this exact private route before launch

The following generator is preparation-only. Run it later against the unique
private path; it edits no worktree. It emits ordinary ScenarioRunner TOML and
uses three physical submissions, each requiring an exact typed Boolean `true`.
Do not substitute RPC `lua` for any `console_command`.

```python
# Save/run only inside the new private preparation directory.
import json, os, pathlib, tomllib
out = pathlib.Path(os.environ['KP_TASK7_ROUTE'])
steps = []
def add(**s): steps.append(s)
def check(label, code, **kw):
    add(label=label, do='assert_lua', code=code, equals=True, **kw)
def physical(label, code):
    add(label=label, do='console_command', code=code, contains=['boolean: true'],
        expect_values=[{'type':'Boolean','value':True}], return_count=1, timeout=30)
add(do='load_save', dir='000001 - AUTOSAVE', timeout=600)
add(wait='phase', equals='gameplay', timeout=600)
add(do='clear_auto_pause')
add(do='advance_dialog', until='gameplay', timeout=120)
check('peaceful danm14aa, checked native model, original scale',
 "local q=nwscript.call; local p=q('GetFirstPC'); if q('GetModuleFileName')~='danm14aa' or q('GetIsObjectValid',p)~=1 or q('GetIsDead',p)==1 or q('GetIsInCombat',p)~=0 or q('GetIsInConversation',p)~=0 or not kp.model.capabilities().available then return false end; task7_original=assert(kp.model.snapshot(p)); task7_module=q('GetModuleFileName'); task7_area=q('GetArea',p); task7_locals={}; for i=5,9 do task7_locals[i]=q('GetLocalNumber',p,i) end; q('SetCameraMode',p,2); q('SetCameraFacing',q('GetFacing',p)); return math.abs(task7_original.base-1)<0.001")
add(do='advance_ticks', ticks=120, timeout=30)
add(do='console_open', open=True)
physical('physically construct finite native scale scene',
 "local q=nwscript.call; task7_pc=q('GetFirstPC'); task7_body=assert(kp.model.snapshot(task7_pc)); task7_local5=q('GetLocalNumber',task7_pc,5); task7_scene=dofile('kotorphasor/scripts/model_scene.lua').new{name='task7scale',trigger=1,hold_ticks=60,spawn=false,scales={{0.35},{2.4},{task7_body.base}}}; return task7_scene.state=='waiting' and math.abs(task7_body.base-1)<0.001")
add(do='mark_log')
physical('physically arm delayed finite scene with a native timer',
 "task7_delay=0; function task7_tick() task7_delay=task7_delay+1; if task7_delay<=180 then return true end; task7_scene:tick(); return task7_scene.state~='complete' and task7_scene.state~='failed' end; task7_timer=kp.registertimer(16,'task7_tick'); nwscript.call('SetLocalNumber',task7_pc,5,1); return task7_timer>0")
add(do='console_open', open=False)
for phase, scale in ((1,0.35),(2,2.4),(3,1.0)):
    check(f'independent native phase {phase}, identity, effective ratio, peaceful gameplay',
      "local q=nwscript.call; local p=q('GetFirstPC'); if q('GetLocalNumber',p,8)~=0 then error('scene failed') end; if q('GetLocalNumber',p,6)~="+str(phase)+" then return false end; local c=assert(kp.model.snapshot(p)); return q('GetModuleFileName')==task7_module and q('GetArea',p)==task7_area and q('GetIsInCombat',p)==0 and q('GetIsInConversation',p)==0 and c.id==task7_original.id and c.model==task7_original.model and c.creature==task7_original.creature and math.abs(c.base-"+str(scale)+")<0.001 and math.abs(c.effective-task7_original.effective/task7_original.base*"+str(scale)+")<0.001",
      poll=True, timeout=45)
check('native completion and exact original scale restored',
 "local q=nwscript.call; local p=q('GetFirstPC'); if q('GetLocalNumber',p,8)~=0 then error('scene failed') end; local c=assert(kp.model.snapshot(p)); return q('GetLocalNumber',p,7)==1 and q('GetLocalNumber',p,6)==3 and c.model==task7_original.model and c.creature==task7_original.creature and math.abs(c.base-task7_original.base)<0.001 and math.abs(c.effective-task7_original.effective)<0.001",
 poll=True, timeout=60)
add(do='await_log', pattern=r'\[model-scene:task7scale\] phase=', minimum=3, maximum=3, timeout=10)
add(do='await_log', pattern=r'\[model-scene:task7scale\] complete phases=3 restored=1', minimum=1, maximum=1, timeout=10)
add(do='advance_ticks', ticks=120, timeout=30)
add(do='console_open', open=True)
physical('physically verify completion and release only scene-owned state',
 "assert(task7_scene.state=='complete' and task7_scene.phase==3); task7_scene:unload(); nwscript.call('SetLocalNumber',task7_pc,5,task7_local5); task7_scene=nil; task7_tick=nil; task7_body=nil; return true")
add(do='console_open', open=False)
check('native local slots and scale remain restored after physical cleanup',
 "local q=nwscript.call; local p=q('GetFirstPC'); for i=5,9 do if q('GetLocalNumber',p,i)~=task7_locals[i] then return false end end; local c=assert(kp.model.snapshot(p)); return q('GetModuleFileName')==task7_module and q('GetArea',p)==task7_area and q('GetIsInCombat',p)==0 and q('GetIsInConversation',p)==0 and c.model==task7_original.model and c.creature==task7_original.creature and math.abs(c.base-task7_original.base)<0.001 and math.abs(c.effective-task7_original.effective)<0.001")
add(do='advance_ticks', ticks=120, timeout=30)
def value(v):
    if isinstance(v, dict): return '{'+', '.join(k+'='+value(x) for k,x in v.items())+'}'
    if isinstance(v, list): return '['+', '.join(value(x) for x in v)+']'
    return json.dumps(v, ensure_ascii=True)
text = 'name="Task 7 physical native scale"\ntarget="k1"\n[settings]\ngame_speed=1.0\nhang_seconds=90\ndefault_timeout=45\nload_timeout=600\n'
for s in steps: text+='\n[[step]]\n'+'\n'.join(k+'='+value(v) for k,v in s.items())+'\n'
tomllib.loads(text)
with out.open('x') as f: f.write(text)
print(out, 'steps=',len(steps))
```

Before launch, parse this private TOML using the snapshot's `Scenario.load`,
confirm all verbs and the three console predicates, hash it, and retain it. The
180-callback delay gives the real F12 close time before the first visible effect;
timer callbacks renew on real engine ticks, without catch-up or speed changes.
Sixty callbacks per phase are a bounded choreography choice, **not proof of a
one-second duration or smooth cadence**. If the camera hides the PC, a phase is
missed, combat begins, or the visible interval does not fit the representative
clip, retain a failed acceptance result. Do not change timing or reposition and
retry within this attempt.

## Fresh verified harness and the one allowed launch

Independent display-gate review is PASS and the parent authorizes exactly one
K1 attempt. This brief does not execute that authorization. Create the
snapshot from the current worktree. The source must remain stable throughout
snapshot creation and verification. The manifest closure must include
`gamescope_socket`, `gamescope_processes`, `gamescope_xwayland`,
`physical_console`, `console_protocol`, `console_steps`, `owned_x11`,
`creative`, `creative_wine`, `recording`, `scenario`, and their static imports.

```sh
PYTHONPATH="$KP_TASK7_ROOT/scripts/harness" /usr/bin/python3 -B -m kpharness.gamescope_snapshot create \
  --source-root "$KP_TASK7_ROOT/scripts/harness" --snapshot "$KP_TASK7_SNAPSHOT"
PYTHONPATH="$KP_TASK7_ROOT/scripts/harness" /usr/bin/python3 -B -m kpharness.gamescope_snapshot verify \
  --snapshot "$KP_TASK7_SNAPSHOT" --source-root "$KP_TASK7_ROOT/scripts/harness"
```

Retain the canonical manifest digest and complete snapshot-file hash map; seal
files 0444 and directories 0555 only after all preparation validation. Verify
source equality and hashes again immediately before and after the run. The
supported driver launches isolated Python (`-I -S`) with the snapshot runtime
and verified repository context. Do not switch to a private monkeypatched
session, handwritten window ID, caller DISPLAY, or a legacy harness snapshot.

The exact single creative launch, once preflight and preparation pass:

```sh
PYTHONPATH="$KP_TASK7_ROOT/scripts/harness" /usr/bin/python3 -B -m kpharness.gamescope_snapshot driver \
  --snapshot "$KP_TASK7_SNAPSHOT" -- \
  --backend linux-wine-k1-gamescope --target k1 \
  --script /home/brunner56/kp-live-20260922/frozen-model-393f68d/model_scene.lua \
  --route "$KP_TASK7_ROUTE" \
  --build-dir /home/brunner56/kp-console-protocol-20260927/build \
  --source /home/brunner56/krayt/tmp/k1_harness \
  --staged "$KP_TASK7_PREP/stage-k1" \
  --wineprefix "$KP_TASK7_PREP/wineprefix-k1" \
  --checkpoint-root "$KP_TASK7_PREP/checkpoints-k1" \
  --output "$KP_TASK7_OUTPUT" --width 1024 --height 768 --capture-fps 60 \
  --boot-timeout 120 --marker '\[model-scene:task7scale\] phase=1 actor=1'
```

The runner acquires its canonical lock, creates a fresh single-purpose subreaper,
starts one Gamescope and one game, admits exactly one PID/start-owned game
window, and records only that window. Record the launcher command, absolute
Python identity, launch count, parent/controller identities and timestamps.
No outer timeout may kill the controller without allowing its ordered `finally`
cleanup; use a bounded supervisor deadline with graceful termination and retained
failure evidence, not an automatic restart policy.

## Physical-input and native-behavior acceptance

Require all route steps passed with no skips, `build=k1_gog_103`, game speed
requested/effective 1.0, and no capture identity changes. Each of the three
`console-command-<step>.json` files must demonstrate:

- `input="real owned-window keyboard"`; verified window owner PID/start, exact
  Gamescope lease/display/geometry; actual F12 open/close visible in the master.
- Nonempty exact runtime identity, canonical decimal-string session/request IDs,
  exactly baseline submitted + 1 for the physical Enter, no replay, unchanged
  runtime/session throughout observation.
- Exact request outcome `Succeeded`, return count `"1"`, untruncated typed values
  exactly `[{"type":"Boolean","value":true}]`; no error/cancel/expiry/duplicate,
  missing output, or dropped relevant output.
- Separate correlated input and result lines for the same request/session and
  distinct sequences. The result must not be inferred from `completed` or a log
  substring copied from input.

The production port exposes only status/outcome/output; the physical entry
creates each console request. Independent `assert_lua` reads are labeled native
state evidence, not counted as F12 execution. The successful production receipt
contains the baseline submitted and last-line values; it does not currently
retain every intermediate wire response or a DirectInput input_calls delta.
Do not invent that evidence. The keyboard route, exact request correlation and
master video are the available supported proof; any stronger raw-wire audit is
an additional preparation requirement, not an implied result.

Native gates require stable PC/model/creature/module/area, all three distinct
base/effective scale phases, no combat/conversation, exactly three phase markers,
completion/restoration marker, original scale and slots 5–9 restored after the
physical cleanup. The helper spawns no actors. Baseline/post scene comparison
must also show no unexpected damage, movement, actors, or source/save mutation.

## Media acceptance: no FPS-only success

Preserve and hash `continuous.mp4`, `capture.json`, FFmpeg log, `media.json`,
`representative.mp4`, the built-in `representative.gif`, and all route/native
receipts. Verify `-window_id` equals the frozen game window, input is the admitted
display, capture geometry is 1024×768, sampling requested 60, no interpolation,
and recorder lives continuously from mapped-window capture through route finish.
Require a 60 FPS encoded MP4 master as well as 60 FPS requested acquisition;
keep actual distinct-frame cadence as the separate acceptance test below.
The Gamescope backend starts recording after the owned game window is mapped;
it does not prove video of pre-window game launch.

Review the **whole unchanged master**, then the representative interval. It must
show F12 physical interaction and an unobscured, intelligible normal → small →
large → restored PC, stable camera/background, no black/foreign frames, no
loading/menu mistaken for gameplay, and visible restoration. The full body must
remain in frame at every scale, including feet and the giant head; tiny must
still be identifiable. Require no disorienting camera movement, camera spin,
arbitrary added effects, teleportation, or cropping used to conceal a failure.
The one initial camera setup must settle before the baseline; the subject,
background and reference objects should make normal → tiny → giant → normal
restoration immediately understandable. A giant clipped by the top edge is a
failed framing gate even when its native scale readback passes. The first-marker
10-second representative interval is only a hint. It must include defining
phases and restoration; retain failure if it does not. Do not label fallback
final-interval footage as the effect.

After teardown, use media tools only on the retained master. Retain probes of
frame count, actual PTS spacing, encoded average/nominal FPS, decoder errors,
FFmpeg drop/duplicate diagnostics, and distinct-frame/repeated-frame-run analysis
on the unobscured gameplay interval. A practical review gate is no unexplained
freeze >200 ms, no timestamp discontinuity, and visibly fluid native animation;
record distinct frames per second and longest repeat run, allowing expected
60-Hz acquisition of a lower native cadence. A header saying 60 FPS or hashing
HUD clock pixels is not proof. Missing diagnostics remain unknown. Do not set
acceptance merely because the encoder or route exited successfully.

The built-in GIF is **8 FPS**, so it cannot be called the smooth deliverable.
After the unchanged master has passed the visual/behavior/cadence review and
its digest-bound acceptance is recorded, without editing product code or the
master, create an additional
`representative-25fps.gif` at 25 FPS (40 ms GIF frame timing), from the identical
reviewed interval. Downsampling is allowed; interpolation and fabricated frames
are not. Keep the original runner media and receipts unchanged and write a
supplemental sidecar with master SHA-256, exact start/duration, command, output
SHA-256, frame count/delays and visual result. Example later postprocessing:

```sh
ffmpeg -nostdin -v error -threads 2 -ss REVIEWED_START -t REVIEWED_DURATION \
  -i RUN_DIR/continuous.mp4 -filter_complex_threads 1 \
  -filter_complex 'fps=25,scale=640:-1:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=3' \
  -threads 2 RUN_DIR/representative-25fps.gif
```

Use real reviewed numeric times and absolute paths; do not overwrite existing
outputs. Require the supplemental GIF itself to look visually smooth and readable at
25 FPS; a lower encoded rate alone is not grounds for accepting a choppy GIF.
Its sidecar must link to the accepted unchanged master digest and acceptance
receipt. The GIF remains a preview; the 60 FPS master/MP4 is the primary media.
Only after all master behavior, provenance, cadence, visual and cleanup checks pass,
run `kpharness.creative_accept` from the same verified snapshot runtime with the
actual reviewer identity and continuous-master digest, then verify
`verify_acceptance()`. Until then schema 2 intentionally has visual review
pending and `ok=false`; the launch command's nonzero result from pending review
is not permission to replay the game. Keep supplementary cadence/GIF evidence
separate from the completed execution fields bound by acceptance.

## Cleanup and one-launch/no-retry rule

Require ordered teardown `recorder → game_wine → display`, no component failures
or failed attempt hidden by later cleanup, no owned PID/start survivors, unchanged
source/input/runtime/helper/save identities, no private pathname/abstract endpoint
rows in the admitted namespace, no leftover candidate pathname or display lock,
and protected display/quarantine identities unchanged. Retain the adopted-child
reap and exact-node/namespace/lock evidence; independently check the canonical
lock is released. `already_absent` and explicit `removed` are different outcomes.

A preflight refusal before launch is a zero-launch receipt. Once this attempt
starts Gamescope, it consumes the **one launch** even if game startup, window
admission, physical input, phase timing, recording, or cleanup fails. Retain all
logs, partial master video, route/candidate/cleanup evidence and artifacts; stop.
Do not change geometry, script, source save, delays, credentials, window discovery
or capture, and do not retry an unchanged failed gate. Diagnose and review any
new proposal separately. No fallback to Xvfb or an existing display can satisfy
this Gamescope acceptance run.

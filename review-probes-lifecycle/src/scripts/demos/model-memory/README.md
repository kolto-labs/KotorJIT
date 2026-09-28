# Finite native scale scenes

These are separate authored demos, outside the41-example validation inventory.
They require the checked native `kp.model` backend. No complete Darwin runtime or
Mac live validation is implied by the recovered Mac profiles.

- `player_scale.lua`: six visible phases,0.35 →2.4 →1.0 repeated twice, then
  restoration to the actual original base/effective scale.
- `npc_wave.lua`: three newly spawned humanoids placed forward and to both sides
  of the PC using its facing: six metres forward and side offsets−2/0/2metres. Friendly faction2 is independently read back and
  commandability disabled. Alternating0.4/2.0 sizes swap twice, with1.0 interludes,
  then original scales are restored and the scene-owned actors removed.
- `model_scene.lua`: reusable finite state machine. Deploy it alongside exactly
  one of the authored scenes; it can also load as an inert host script.

No effect waits for an attack. The first visible phase starts on the first tick
with ready models after the explicit trigger; newly created models have a bounded
180-tick readiness window. Each phase lasts90 OnTick callbacks, not a promised
wall-clock duration. Both scenes finish after six phases plus a90-tick hold at restored original scale. Independent native
snapshots verify each mutation; a setter return or log counter alone is not proof.
Completion is only published after original scales have been verified, and after
owned NPC destruction is observed. Errors/unload attempt restoration; module/area
changes or replacement actor/model identities refuse cleanup writes/deletion.
Such refusals remain errors and can leave scene-owned actors for diagnosis rather
than deleting a replacement actor. There is no recovered engine generation counter.

The shipped routes load `endar_room3`, finish the remaining tutorial dialog,
require peaceful gameplay, frame the camera to the PC facing, trigger the scene,
and independently sample each phase. They also verify final PC restoration and,
for the wave, the removal of new actors while preserving pre-existing area IDs.
A different cleared checkpoint can be selected in a reviewed route copy. Keep
input bytes and the route copy with the recording receipt. The K1 showcase uses
1024x768; wider requested modes may be reset by the game.

```sh
PYTHONPATH=scripts/harness /usr/bin/python3 -m kpharness.creative \
  --backend linux-wine-k1 \
  --source /path/to/protected/game --build-dir /path/to/build \
  --staged /path/to/private/stage --wineprefix /path/to/private/prefix \
  --checkpoint-root /path/to/checkpoints/k1 --output /path/to/runs \
  --capture-fps 60 --width 1024 --height 768 \
  --script scripts/demos/model-memory/model_scene.lua \
  --script scripts/demos/model-memory/player_scale.lua \
  --route scripts/harness/scenarios/model-memory/player.toml \
  --marker '\[model-scene:player\] phase=1 actor=1'
```

For the wave use `npc_wave.lua`, `wave.toml` and marker
`\[model-scene:wave\] phase=1 actor=1`. The helper and scene paths above are
relative to the repository working directory. The Linux/Wine adapter needs
runner-owned staging/prefix directories; see [creative runner](../../../docs/creative-runner.md).

These scripts reserve PC local numbers5–9 while deployed:5is the trigger
(1player/2wave),6the completed phase index,7final completion,8failure and9actor
count. Set5only once after setup. Run exactly one scene per load and do not deploy
examples using the same local slots.6–9are restored on unload within the original
module/area. The trigger is consumed to0, not replayed during reload.

A60FPS encoded recording can contain duplicated game frames. Review actual
render cadence, framing and visible changes before selecting a short-form clip.
Use the full continuous MP4 as raw evidence and the representative MP4 as an
initial edit candidate; the GIF is an8FPS preview. Reviewers should see the scale
change immediately in the selected clip, the opposite phase, and restoration.
An automatic ten-second excerpt may omit final restoration; retain its independently
verified full recording and choose a longer/manual edit when necessary. Route
success does not automatically establish that the clip is clear or compelling.

Offline: `luajit tools/model_scene_test.lua scripts/demos/model-memory` exercises
both actual scripts in fresh environments, including phase counts, repeated-tick
suppression, failed mutation/readback/restoration, unload, module transition and
reused object-ID cleanup refusal. CTest also runs the native core/Lua boundary.
Live video/readbacks are still required before these demos are marked validated.

Cleanup requires a retained native ownership identity for every actor it deletes.
Ownership is captured immediately after creation, independently of model readiness.
On Windows this uses the server creature, so delayed client/model creation is
allowed for that same actor. If initial ownership cannot be captured, the scene
fails and never adopts a later object at that ID. Partial model captures are
retained too; both ownership and any existing model capture must still match
before deletion. Known identities are never overwritten by readiness samples. Every active tick
checks each actor's validity, area and combat state; this is a tick-level guarantee,
not continuous observation between ticks. The compact six-metre-forward lineup is
intended for an outdoor, cleared area with a stable camera; validate framing live.

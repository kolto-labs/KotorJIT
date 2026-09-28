# Original 41: next three retained proof slices

Read-only priority audit performed against the isolated
`lua-boundary-validation` worktree. No game, Wine session, build, source edit,
or new acceptance run was started. The source of truth is
`.worktrees/lua-boundary-validation/tools/tests/examples/manifest.json`, with
the live-gap and retirement decisions in
`docs/original41-live-evidence-audit.md` and `docs/user-directive-audit.md`.

The ranking assumes the already-identified `cursed/70_doppelganger.lua`
appearance-order fix is completed first. It selects immediate, retained
harness examples whose Lua is an in-game request/return operation. The new
physical F12 route can type the request into the real console and correlate the
result with the same K1 session; it does not require a new native C++ routine.
Use a copied/staged K1 save per slice and reload the original checkpoint for
cleanup. A console result, a queued count, or a local counter is not the
behavioral oracle by itself.

## Ranked list

### 1. `harness/110_loot_container.lua` — stocked and empty container

**Exact source and route.**
Use `scripts/examples/harness/110_loot_container.lua`, with the existing
`endar_room3` K1 checkpoint. The matching route is the corridor section of
`scripts/harness/scenarios/k1_endar_room3_onward.toml`: it loads `endar_room3`,
walks to the stocked `metalbox` near `(43.0,55.7,-1.275)`, and documents the
nearby `footlker` fixture. The current combined example route exercises this
source at `/home/brunner56/kp-live-20260922/harness-examples.toml:170-197`.
For the physical proof, type the source-equivalent Lua through F12 (or the
approved physical-console snippet), then close F12 before any movement or
combat input.

**Missing behavioral oracle.**
The manifest obligations are `stocked_nearest`, `inventory_acquired`,
`empty_noop`, and `clean_recording`. The existing route has useful positive
coverage: it snapshots the nearest stocked `metalbox`, checks that the
selected object is the returned container, waits until its inventory is empty,
checks ordinary item possession, and checks that credits increased. It still
needs an independent same-session receipt that (a) the selected container was
the nearest *stocked* same-tag object while another same-tag object was empty,
(b) every original item ID moved to the PC and the source has no remaining
items, and (c) a second invocation after emptying returns `taken=0` without a
take action. Record the pre/post source object ID, item IDs/tags, possessors,
and PC gold; do not accept the returned `taken` count as acquisition proof.

**Visual proof.**
Capture a continuous gameplay segment showing the loaded Endar corridor, the
PC moving to the wall-flush `metalbox`, the F12 command/result, F12 closing,
and the PC continuing in the room. The useful visual event is the real
inventory/container change and continued game input, not a console transcript
or a screenshot of an item count. Keep the complete MP4 and a short review
clip keyed to the physical request and the independent state receipt.

**Restoration and cleanup proof.**
End the run by stopping movement, closing F12, and reloading the untouched
`endar_room3` checkpoint in a fresh staged save. Re-query the corridor and
show that the `metalbox` is stocked again, the PC gold/inventory match the
checkpoint baseline, and no owned game/recorder/process remains. This is
separable because it uses one placeable and inventory transaction, has no
event-handler registration or combat-model dependency, and the route already
has the exact corridor coordinates and item expectations. It is the fastest
high-value retained example because the positive route and independent
container/gold checks are already written.

### 2. `harness/50_doors.lua` — authored plot-door open

**Exact source and route.**
Use `scripts/examples/harness/50_doors.lua` against the same `endar_room3`
checkpoint and `end_door05` fixture. The route's documented configured
exercise is `/home/brunner56/kp-live-20260922/harness-examples.toml:111-142`;
the larger authored route opens this door after loading the room3 checkpoint at
`scripts/harness/scenarios/k1_endar_room3_onward.toml:6-32`; its later
`StartNewModule` transition is separately recorded at `:358-380`. Physically
type the inspection and
`OPEN=true` operation through F12, then use the ordinary game input with the
overlay closed. If the engine leaves the door in its first opening phase,
record `door_commit_open` as an engine/client completion step; do not hide it
or call that intervention a pure Lua success.

**Missing behavioral oracle.**
The manifest obligations are `door_facts`, `self_open`, `invalid_or_open`, and
`clean_recording`. The current route already names the needed fields, but the
acceptance receipt must independently compare tag/id, `GetIsOpen`, lock/key/
plot flags, `GetIsDoorActionPossible`, and distance before and after. It must
also exercise the negative cases: a missing tag raises/refuses without
queueing an action, and an already-open door is not requeued. For the positive
case, require both `GetIsOpen==1` and a passable/arrived postcondition after
the documented completion path; an `ActionOpenDoor` queue or an output line is
not enough.

**Visual proof.**
The recording should show the PC approaching the Endar plot door, the
physically typed command and returned facts, F12 closing, the door visibly
opening, and the PC crossing or standing at the newly passable doorway. Keep
the full continuous recording and tie the door-open frame to the independent
state/route timestamps. A static open-door screenshot is only a sanity check.

**Restoration and cleanup proof.**
Reload `endar_room3` in a clean staged copy and verify the door's checkpoint
open/locked state before the test. After the positive and negative passes,
reload again and verify the original state and PC position, then close the
overlay and reap only the run-owned recorder/game processes. This is
separable because the example operates on one resolved door, has no global
save arbitration, no combat causality, and no unfinished placeable/projectile
motion. The only special branch is the already-documented client animation
completion, which is observable and can be reported independently.

### 3. `harness/100_module_transition.lua` — `end_m01ab/from_01a`

**Exact source and route.**
Use `scripts/examples/harness/100_module_transition.lua` from the
`endar_room3` K1 checkpoint. The existing route explicitly documents
`StartNewModule('end_m01ab','from_01a')`, waits for `module=end_m01ab`, waits for
a valid gameplay/dialog/paused phase, and saves the resulting starboard entry
at `scripts/harness/scenarios/k1_endar_room3_onward.toml:358-390`. The current
combined example route contains the inspect and configured forms at
`/home/brunner56/kp-live-20260922/harness-examples.toml:466-506`. Type the
configured operation through physical F12 and close the overlay before the
arrival observation.

**Missing behavioral oracle.**
The manifest obligations are `inspect_facts`, `target_module`,
`waypoint_arrival`, and `clean_recording`. The existing combined route checks
the source module, valid door, party count, destination module, phase, and
one-party final state. Add the missing independent arrival receipt: capture
the source module/PC/party before the request, then after load query the exact
destination module, phase, PC position and the authored `from_01a` entry
behavior (plus the first arrival dialog if it appears). Preserve the exact
request identity and reject a result that merely says the request was queued.

**Visual proof.**
Record the source Endar gameplay, physical F12 request/result, F12 closing,
the actual module load, and the PC arriving in the starboard section. Include
the authored arrival dialog when present, then a short period of normal
movement after the transition. The video must be continuous gameplay; a
module-name log or a destination screenshot alone cannot establish arrival.

**Restoration and cleanup proof.**
Reload the original `endar_room3` checkpoint (or the preserved
`endar_starboard` checkpoint for the destination-side repeat) in a separate
staged save. Verify the expected source module, PC/party state, and no stale
pending transition before ending the run. Close F12, stop the recorder
cleanly, and verify that the original save directory is unchanged. This is
separable because it is one engine module request with a known retail
destination/waypoint, no script event ownership, no combat or projectile
simulation, and no dependency on the unfinished placeable-motion capability.

## Selection boundaries

The eight `retired_public` identities (the six former showcase files plus
`cursed/50_chaos_roulette.lua` and `cursed/60_rave.lua`) are excluded even
where old partial receipts exist. `cursed/20_fus_ro_dah.lua`,
`cursed/30_necromancer.lua`, and the other combat curses remain slower because
their current evidence is counter-derived or causally confounded; a local
counter, corpse count, beat count, or observer delta cannot close the required
push, timed replacement, ownership, or branch oracle. `cursed/100_item_airstrike.lua`
and the unfinished projectile/placeable-motion work are also outside this
slice. `coverage/10_cover.lua` is retained and valuable, but its
console-handler ownership plus module/autosave/conversation sequence makes it
the next slice after these three rather than a quickest closure. The retained
`harness/10_world_probe.lua` is a good fourth candidate, but it has weak
visible behavior compared with a real inventory change, door opening, or
module arrival.

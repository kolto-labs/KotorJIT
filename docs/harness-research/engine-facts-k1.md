# engine-facts-k1

The KotOR 1 (GOG 1.03 / Steam-unpacked, same .text) engine behaviours the
headless harness depends on. Each fact is a mechanism plus the evidence that
established it, cited as it appears in the repo sources: `engine_k1.cpp` is
`src/harness/engine_k1.cpp`, `fields.hpp` is `src/harness/fields.hpp`,
`hooksites` is `data/hooksites.toml`, `bindings` is
`data/adjudication/k1_gog_103_harness_bindings.json`, `scenario.py` is
`scripts/harness/kpharness/scenario.py`, `README` is
`scripts/examples/harness/README.md`, and the two routes are
`scripts/harness/scenarios/k1_fresh_trask_quest.toml` (Trask) and
`k1_endar_room3_onward.toml` (Room3). Corpus paths (`Dev/...`, `UN/...`,
`types.h`) are the kotor_readable tree those sources cite; VAs are quoted
from them, not re-derived here.

Commands below assume a booted session:
`PYTHONPATH=scripts/harness python3 -m kpharness.cli boot --target k1`.
`state` is `... kpharness.cli state --target k1`; `exec` is
`... kpharness.cli exec --target k1 "<lua>"`; a raw harness command is a
`pioneer step` body such as `{"do": "clear_auto_pause"}`.

## 1. Timers and autopause

- Three `CWorldTimer`s matter to a headless run: the client world timer, the
  server world timer and the client animation timer. `phase()` reads
  `CWorldTimer+0x24 timer_paused` on each and reports them as a bit mask in
  `phase_detail.timers_paused`: bit 1 client world, bit 2 server world, bit 4
  animation. Evidence: `engine_k1.cpp` phase() (`flag(...)` calls);
  `fields.hpp` Layout `timer_paused = 0x24` citing `types.h:12353-12371`.
- `CServerExoAppInternal::pause_state` is a u8 at +0x10078: bit 1 player
  pause, bit 2 combat / time stop. The server loop snapshots the world timer
  only while bits 1|2 are clear. Evidence: `hooksites` `server.pause_state`;
  `bindings` `CServerExoAppInternal::pause_state` (`types.h:11727-11821`,
  `serverexoappinternal.cpp:4903-4911`).
- Autopause sets the pause byte and pauses the world and animation timers.
  Clearing the byte alone leaves scripts and dialog running but freezes
  everything time-integrated: no movement, no combat rounds, no door
  animation. That is what a stall looks like: `phase_detail.pause == 0`
  with `timers_paused != 0`, ticks advancing, nothing moving. Evidence:
  `engine_k1.cpp` phase() comment and `clear_auto_pause()`; `README`
  "Reading a stalled world".
- `unpause_timers` calls `CWorldTimer::UnpauseWorldTimer` (0x4ae030) on
  each timer. It restores the snapshot base from the pause timer rather than
  clearing a byte; a raw write to `timer_paused` left the snapshots where the
  pause put them and wedged the control channel with the process alive. It
  then calls `SetPausedByCombat(0,0,0)` and `SetAutoPaused(0,0)` on the
  client. `clear_auto_pause` writes `pause_state` to 0 and then runs
  `unpause_timers`. Evidence: `engine_k1.cpp` `unpause_timers()`,
  `clear_auto_pause()`; `hooksites` `timer.unpause_world_timer`.
- The staged `swkotor.ini` sets every `[Autopause Options]` key to 0 so the
  engine stops re-pausing mid-route; the route verbs still clear autopause on
  every poll because combat events re-pause anyway. Evidence:
  `scripts/harness/kpharness/targets.py` ini list; `scenario.py`
  `_clear_room` / `_move_to` docstrings.

Verify: `state` -> `phase_detail.pause`, `phase_detail.timers_paused`; send
`{"do": "unpause_timers"}` and read again.

## 2. Dialog engine

- `CSWSObject+0x48` (`object.dialog_send_pending`, binding
  `CSWSObject::field_48`) is nonzero while the owner is mid-send: the entry's
  VO and its authored node delay both hold it. `ReplyDialog` zeroes it
  (`c7 46 48 00 00 00 00` at 0x4cb480). The harness reports
  `dialog.waiting_on_sound = active && send_pending > 0`; an unreadable owner
  (-1) is not a wait. Evidence: `bindings` `CSWSObject::field_48`
  (`nwsobject.cpp:878-884`); `engine_k1.cpp` `dialog()`; `_DialogDriver`
  comment in `scenario.py` ("covers a node's authored delay as well as its
  VO").
- Dialog delays are stamped against the server world timer, so they scale
  with game speed. VO waits do not: `IsDialogDelay` reports
  `IsSoundPlayingInDialog`, which is the real audio stream. Headless and
  muted, a VO node hangs indefinitely. Evidence: `hooksites`
  `dialog.skip_past` purpose; `docs/harness-research/fill-time-scale.md`.
- `dialog_skip` is `CServerExoApp::SkipPastDialog(this, ownerId)`
  (`UN/_004a.cpp:7396`). It sets the owner's skip-requested flag, honoured by
  `IsDialogDelay` only when the DLG is `Skippable`
  (`CSWSDialog+0x3c`, binding `CSWSDialog::field_3c`; `IsDialogDelay`
  0x4cd2d0 reads `8b 48 3c`). It is the Escape key: on a Skippable cinematic
  it ends the whole conversation and drops every later node's script
  (end_cut04 lost its reinforcement spawn and party-AI restart that way).
  Evidence: `engine_k1.cpp` `dialog_skip()`; `bindings`
  `CSWSDialog::field_3c`; `scenario.py` `_drive_dialog` comment; `README`
  "Cutscenes and scripts".
- Forcing `Skippable` by a struct write was tried and reverted: it made the
  skip take, but a save afterward was reproducibly corrupted
  ("ERF member '' has unmapped restype 0xffff"), including one taken well
  before the targeted stall. Do not reintroduce a raw write there without
  proving a later save loads. Evidence: `engine_k1.cpp` `dialog_skip()`
  comment; `fields.hpp` write funnel comment.
- `dialog_clear_sound_wait` writes `send_pending` to 0 on the owner. The node
  then ends the way finished playback would, so later nodes and their scripts
  still run. `send_pending` is a runtime field never serialised to a save; a
  save taken after the write loads cleanly. Evidence: `engine_k1.cpp`
  `dialog_clear_sound_wait()`; Trask route comment at `end_door02`.
- `dialog_abort` is `HandleDialogSelection(gui, -2, count)`, which returns
  to `CloseDialog` before any array read; never `SetDialogSelection(-3, ...)`,
  because `UpdateDialog` indexes the reply arrays before it looks at the
  sentinel. `CSWSObject::StopDialog` (`nwsobject.cpp:891`) is the server-side
  fallback. Evidence: `engine_k1.cpp` `dialog_abort()`; `hooksites`
  `gui.set_dialog_selection`, `gui.handle_dialog_selection`.
- A reply is accepted only when: dialog active, no selection pending, rows
  present, server `current_reply == -1`, owner `send_pending == 0`, and the
  panel's entry equals the server's; any -1 refuses. `reply` goes through the
  panel's vtable `SelectReply` slot (27, +0x6c), which refuses
  `idx >= count`. Evidence: `fields.hpp` `reply_accepted`; `engine_k1.cpp`
  `reply()`.
- After a talk or a fight the engine can raise the XP status summary
  (`phase_detail.status_summary == 1`, world paused) or a tutorial popup
  (`phase_detail.tutorial == 1` with `modal_count >= 1`).
  `dismiss_status_summary` feeds event 0x27; `advance_tutorial` feeds 0x1F6
  one page at a time and `finish_hidden_tutorial` covers a queued page.
  `phase_detail.tutorial` is also set for other modals (party selection), so
  a refused dismiss is skipped, not fatal. Evidence: `hooksites`
  `gui.status_summary_handle_input`, `gui.tutorial_handle_input`;
  `scenario.py` `_drive_dialog`.
- The ladder (`_drive_dialog`, shared by `advance_dialog`, `clear_room`,
  `move_to`): answer a declared authored bark; else if
  `waiting_for_player`, pick the first active reply; else leave the node alone
  for `dialog_grace` (default 10 s, above Endar's longest authored delay of
  about 6 s at 1x); then once per second: `dialog_clear_sound_wait` only if
  `waiting_on_sound` (each try counts an attempt), `dialog_skip` after 3
  attempts and 6 s stuck, `dialog_abort` after 5 attempts and 12 s. Clearing a
  delay early ended the ambush chain before its faction scripts, which is why
  the grace exists. Evidence: `scenario.py` `_DialogDriver`, `_drive_dialog`,
  `DEFAULT_SETTINGS["dialog_grace"]`.
- A conversation that is active while the panel shows `entry == -1` and
  nobody is in it is still initialising; `dialog_skip` fails on it
  ("dialog owner has no game object") and the ladder keeps polling.
  Evidence: `scripts/examples/harness/20_dialog_state.lua`; `scenario.py`
  `_dialog_request`.
- Cutscenes that pause and resume their conversation on `DelayCommand`
  (Trask's sacrifice chain `k_pend_traskdie1 -> ... resume2 -> cut14 ...`,
  the room5 ambush `k_pend_cut2_1..3`) die at 16x and complete at 1x. Routes
  wrap those beats in `speed 1.0` / `speed 16.0`. The harness scale is a
  factor applied inside the `SetGameSpeed` detour, so the engine's own
  death-sequence slow-mo still slows. Evidence: Room3 route comments;
  `README`; `engine_k1.cpp` detour header comment.

Verify: `state` -> `dialog.{entry, waiting_for_player, waiting_on_sound,
replies}`; `exec "$(cat scripts/examples/harness/20_dialog_state.lua)"`.

## 3. Doors

- Endar's story doors (`end_door01/02/05`, ...) are plot doors the PC cannot
  use: `GetIsDoorActionPossible(d, 0) == 0`; a PC-queued `ActionOpenDoor`,
  the retail `door_use` message (`ChangeDoorState` 0x2725, category 6 /
  subtype 3) and `DoDoorAction` all drop silently; `door_security` refuses
  them (`door.lockable` false). Evidence:
  `scripts/examples/harness/50_doors.lua`; `hooksites`
  `msg.change_door_state`; `scenario.py` `_scripted_door_open` docstring.
- The authored scripts open them by having the door command itself:
  `AssignCommand(oDoor, ActionOpenDoor(oDoor))` with no `SetLocked`, which
  is the entire effect of `k_pend_traskdl40` (end_door01) by decompilation
  and proven live on end_door02. `scripted_door_open` replays exactly that
  (`kp.as(d, function() kotor.ActionOpenDoor(d) end)`); it needs no party
  proximity or pathing. Evidence: Trask route comment at Entry 43;
  `scenario.py` `_scripted_door_open`.
- Opening is two-phase. `CSWSDoor::OpenDoor -> SetOpenState` writes only
  `also_open_state` (+0x2cd) and the animation id (+0xd4 = 0x2742). The
  committed `open_state` (+0x2cc, what `GetIsOpen` and the walkmesh read) is
  written only by `CSWSDoor::MoveToNextOpenState` (0x00589680), whose sole
  retail caller is the client's model-animation-done callback
  `CSWCDoor::MoveNextDoorState` (0x683f7a). The headless client never delivers
  that callback for some doors (seen live on end_door04 and both end_door05s,
  doors unlocked at runtime). A door stuck with +0xd4 != 0x2726 (closed),
  +0x2cd = 1, +0x2cc = 0 makes every later creature-path open a no-op at
  `AIActionOpenDoor` (`cmp [door+0xd4], 0x2726`) and blocks the PC.
  Evidence: `engine_k1.cpp` comment above `door_commit_open()`; `bindings`
  `CSWSDoor::MoveToNextOpenState` (`nwsdoor.cpp`, `nwcdoor.cpp`, raw
  disassembly); `hooksites` `door.move_to_next_open_state`.
- `door_commit_open` runs phase two once on the `CSWSDoor` `this` (reached
  through the `AsSWSObject` vtable slot, not by assuming offset 0). It commits
  a pending state only; it does not open a closed door. `scripted_door_open`
  sends it once if `GetIsOpen` is still 0 about 2.5 s after the self-command
  (`_DOOR_COMMIT_AFTER`). Evidence: `engine_k1.cpp` `door_commit_open()`;
  `bindings` limits field; `scenario.py` `_DOOR_COMMIT_AFTER`.
- `CGameObject`'s internal type byte is 10 for doors (5 for creatures),
  unlike NWScript's door mask 8; `door_use`, `door_commit_open` and
  `attack` check it. Evidence: `hooksites` `object.type`; `engine_k1.cpp`.
- Locked doors with an `OnFailToOpen` script are opened by running that
  script with the door as `OBJECT_SELF` via `ExecuteScript`, because the
  in-game trigger (a click on the locked plot door) has no headless
  equivalent. `k_pend_door20` on `end_door08` needs `END_ROOM8_DEAD >= 2`;
  `k_pend_door15` on `end_door15` needs `END_ROOM7_DEAD >= 2` and a level-2
  PC; each unlocks and opens its door itself, and refuses under its
  threshold. Read the door afterwards; do not trust the call. Evidence:
  Room3 route comments; `scripts/examples/harness/90_run_script.lua`;
  `scenario.py` `run_script` verb.

Verify: `exec "$(cat scripts/examples/harness/50_doors.lua)"` (set
`OPEN = true` to self-command); `{"do": "scripted_door_open", "tag": "..."}`.

## 4. Movement and combat

- `GetCurrentAction` codes the verbs gate on: `65534` idle, `0` move to
  point, `3` attack object, `7` dialog object, `38` follow leader (companion
  AI re-asserts it every heartbeat), `39` in a combat round. Evidence:
  `README` "Action codes"; `scenario.py` `_clear_room` `idle_actions`.
- Action queues are per object. `kp.as(obj, fn)` is `AssignCommand`: inside
  it `OBJECT_SELF` is `obj` and `Action*` calls queue there; outside it they
  go nowhere. A conversation suspends the PC's action queue, so a move or
  attack issued during dialog is dropped; the verbs wait it out and re-issue.
  Evidence: `README` "How the API is shaped"; `scenario.py` `_move_to`,
  `_clear_room`.
- Combat takes the queue: while `GetIsInCombat(pc)` is 1 the engine's combat
  AI owns it, so `move_to` expects no distance progress, spends no retry, and
  re-issues the walk when combat clears. Re-issuing `ActionAttack` every
  tick restarts the combat round, so `clear_room` issues it only when the
  nearest target changed or the PC went idle. Evidence: `scenario.py`
  `_move_to` (`fought`), `_clear_room` docstring;
  `scripts/examples/harness/40_attack_nearest.lua`.
- The native `attack` command sends `Input_Attack(target, combatFeat=0)`
  through the client message handler (category 6 / subtype 2); dispatch is
  not combat completion. Evidence: `hooksites` `msg.attack`;
  `engine_k1.cpp` `attack()`.
- `move_to` gates: done when observed distance <= `range` + 0.5 (object
  default 1.5, position default 0.75); when the best distance has not
  improved by 0.25 for `stall` seconds (default 4) the move is re-issued once
  and a second stall fails the step; an idle queue (65534) short of the target
  is a cut path, re-issued once. A closed door in the way looks like
  oscillation with the move still queued. Evidence: `scenario.py` `_move_to`.
- `clear_room` gates: `GetGlobalNumber(until_global) >= until_value` (the
  room's `END_*_DEAD` counter) or, without a global, no live hostile within
  `radius`; with a global and no hostiles it waits `grace` (default 8 s) then
  fails. Autopause is cleared on every poll; the dialog ladder runs first.
  Evidence: `scenario.py` `_clear_room`.
- `ActionMoveToObject` parks the PC at the engine's own interaction
  distance: `end_locker01`'s collision footprint stops it 1.79 units from the
  origin. Measured live, `tmp/k1_harness/runs/20260915-071620`. Evidence:
  Trask route comment above the locker step.

Verify: `exec "$(cat scripts/examples/harness/10_world_probe.lua)"`;
`{"do": "move_to", "tag": "end_door05", "range": 1.5}`.

## 5. Saves and checkpoints

- `save` is `CClientExoApp::SendSaveGameRequest(slot, &dirName,
  &displayName)` (`UN/_005e.cpp:8006`). The server forms
  `SAVES:%06d - %s` and runs the whole save in one server tick
  (`StallEventSaveGame`); the request returns before any file exists.
  Evidence: `engine_k1.cpp` `save()`; `hooksites`
  `client.send_save_game_request`.
- `SAVEGAME.sav` is the last artifact written and it is streamed: the file
  exists with a fresh mtime long before it is whole. A checkpoint copied on
  first sight, then quit, left an 8 KB `SAVEGAME.sav` that loads as
  "ERF member '' has unmapped restype 0xffff". The completion predicate is
  therefore: mtime >= request time - 1 s, size > 0, same size on two polls a
  second apart, mtime at least 1 s old. The engine blocks its main thread
  during a large module save, so the control channel may not answer until
  the files are whole. Evidence: `scenario.py` `save` verb.
- A `checkpoint` copy is taken only at a fresh, complete, idle gameplay
  boundary: two `state` reads plus a full world probe must satisfy
  `World.stable_gameplay` (complete world, matching idle PC, tick progress,
  noncombat, no dialog). Checkpoints live under
  `tmp/checkpoints/<target>/<name>/` and reload through the engine's own
  `load_save`. Evidence: `scenario.py` `save` verb;
  `scripts/harness/kpharness/checkpoints.py` docstring.
- Bisected clean: `endar_first_door` (after end_door01 opens by
  self-command) is a saveable, non-paused idle state, bisected against the
  end_door02 issue; `endar_room3` saved and reloaded clean after the
  `dialog_clear_sound_wait` path replaced the reverted `Skippable` write.
  Evidence: Trask route CHECKPOINT ENDPOINT comments (2026-09-15).
- `load_save` replays the main-menu branch of `CSWGuiSaveLoad::LoadGame` in
  one client tick. The harness itself exports the `SAVEGAME.sav` ERF members
  into the `GAMEINPROGRESS:` directory (`<game>/gameinprogress` unless
  `KOTORPHASOR_GAMEINPROGRESS_DIR`), cleaning stale files first, because
  `LoadModule` resolves `GAMEINPROGRESS:<module>.sav` from inside that
  archive; slot 0xffffffff makes the server use the name verbatim;
  `LASTMODULE` comes from `savenfo.res`. Evidence: `engine_k1.cpp`
  `load_save()`, `export_savegame_to_gameinprogress`, `read_last_module`.
- Headless loads deadlock on the client's `AreaLoaded`: the server only
  places the player after it, and the client only sends it when the load
  bar completes, which needs an update the server never sends for an
  unplaced player. The harness sends `AreaLoaded` once
  (`step_load_completion`), gives up after 20 s, and watches
  `load_from_savegame` 1 -> 0 and `player_creature_id` leaving
  `OBJECT_INVALID`. Evidence: `engine_k1.cpp` comment above
  `step_load_completion()`; `docs/harness-research/fill-client-load-completion.md`.

Verify: run a route with a `save` step and watch `SAVEGAME.sav` size settle;
`{"do": "load_checkpoint", "name": "endar_room3"}` then `wait phase ==
gameplay`.

## 6. Module transitions

- `warp` is `ExecuteCommandStartNewModule` (`nwvmachinecommands.cpp:
  20932-20953`) minus the fade: `SetMoveToModuleString`,
  `SetMoveToModuleStartWaypoint("")`, then `SetMoveToModulePending(1)`. The
  server loop consumes it on its next tick. The only MainLoop gate,
  `CGuiInGame+0xdc` (controller-loss pause), is dead on every PC build.
  Evidence: `engine_k1.cpp` `warp()`;
  `docs/harness-research/fill-Engine_gates_that_can_stall_sc.md`.
- A transition door's own effect is `StartNewModule(module, waypoint)`, so a
  route crosses a plot transition (end_door10 -> `end_m01ab` at `from_01a`)
  by calling `kotor.StartNewModule` from Lua and gating on
  `wait module == "end_m01ab"` then `phase_any` in
  `[gameplay, dialog, paused]`, since an arrival often opens with a dialog
  (Carth's comlink call). `warp` lands at no waypoint; `StartNewModule`
  carries one. Evidence: `scripts/examples/harness/100_module_transition.lua`;
  Room3 route end.
- STUNT_00 quirk: the escape-pod exit was observed as the module sequence
  `end_m01ab -> STUNT_00 -> tar_m02af`, i.e. a cutscene module sits between
  the source and the destination. A route that gates on the first module
  change would stop inside STUNT_00; gate on the destination module name.
  Evidence: `.mission/receipts/2026-09-15-k1-starboard-to-taris-checkpoint.json`
  (`escape.modules`). Observation only; no engine source in the repo
  describes STUNT_00's load path.
Verify: `exec "kotor.StartNewModule('end_m01ab','from_01a'); return 1"` then
`state` -> `module`; or `{"do": "warp", "module": "end_m01ab"}`.

## 7. Level-up

- `CSWSCreature::stats` is a `CSWSCreatureStats*` at `CSWSCreature+0xA74`
  (`GetLevel` 0x5a5fec `mov esi,[ecx+0xA74]`; `DoAutoLevelup` 0x6aecb9
  reads the same then jumps to `AutoLevelup` 0x5b27e0).
  `CSWSCreatureStats::experience` is an unsigned total at +0x68
  (`SetExperience` 0x5af54c; `CanLevelUp` 0x5a683f and `AutoLevelup`
  0x5b2864 compare it against the XP table). Evidence: `bindings`
  `CSWSCreature::stats`, `CSWSCreatureStats::experience`; `hooksites`
  `creature.stats`, `stats.experience`.
- `auto_levelup` is the character screen's own Auto Level Up:
  `CSWSCreatureStats::AutoLevelup(this, package=0)`. The player stats are
  reached client party -> player character -> server creature -> `stats`.
  The call is armed and runs two frames later from `after_frame`, then
  checks: same player and stats pointer, `GetLevel(0)` rose, `experience`
  unchanged, and `CanLevelUp() == 0`. Any miss is a failed result, not a
  retry. Evidence: `engine_k1.cpp` `auto_levelup()`, `step_auto_levelup()`;
  `hooksites` `stats.auto_levelup`, `stats.get_level`.
- The bridge fight leaves the PC past 1000 XP; the route asserts
  `GetXP >= 1000`, runs `auto_levelup`, and asserts `GetHitDice == 2`.
  `k_pend_door15` needs that level. Evidence: Room3 route.

Verify: `exec "return kotor.GetXP(kotor.GetFirstPC())"`,
`{"do": "auto_levelup"}`, `exec "return kotor.GetHitDice(kotor.GetFirstPC())"`.

## 8. Authored-script patterns the routes use

- Door self-command (section 3): `kp.as(d, function()
  kotor.ActionOpenDoor(d) end)`; used for end_door01/02/05/10_cut2/16/19.
- `SignalEvent` when a script's guard cannot be met headless.
  `end_door10_cut2`'s OnOpen (`k_pend_room5_02`) requires
  `IsObjectPartyMember(GetLastOpenedBy())`, which a self-command never
  satisfies; its only non-cosmetic effect is `SignalEvent(area,
  UserDefined 20)` two seconds later, so the route fires
  `kotor.SignalEvent(kotor.GetArea(pc), kotor.EventUserDefined(20))` itself.
  The area handler (`k_pend_area02` case 20) has Trask start the cutscene
  whose scripts flip `end_cut2_sith1/2/4` to faction 1. Verified live minus
  the two cosmetic swings. Evidence: `80_signal_event.lua`; Room3 route.
- `ExecuteScript` with the right `OBJECT_SELF` for scripts whose trigger has
  no headless equivalent: `k_pend_door20` on `end_door08`, `k_pend_door15` on
  `end_door15` (OnFailToOpen), `k_pend_reinfrc03` on `end_jedicut` (the
  cutscene node that creates `end_reinforce1/2`), `k_pman_npcstart` on
  `end_trask` (restarts companion AI after a cutscene's `k_pman_npcstop`).
  The `run_script` verb wraps `kotor.ExecuteScript(script, obj)` with
  `tag`, `area = true`, or the PC. Evidence: `90_run_script.lua`;
  `scenario.py` `run_script`; Room3 route.
- Idempotent guards: re-run an authored script only when its effect is
  missing, so a cutscene that already did the work is not doubled. The Room3
  route checks `END_ROOM8_DEAD >= 2` and whether `end_reinforce1/2` exist
  before `k_pend_reinfrc03`, signals `end_jedicut` UserDefined 10
  (`k_pend_cut30`, makes them hostile) only while the counter is under 2, and
  runs `k_pman_npcstart` unconditionally because the restart is idempotent.
  Evidence: Room3 route "ensure the corridor reinforcements exist" step.
- Trask cutscene at 1x: `k_pend_traskdie1` (end_door19's OnOpen) jumps the
  PC to `wp_pc_final`, removes Trask and closes the door; its DelayCommand
  chain dies at 16x after `resume2` with Trask still in the party, so the
  route sets `speed 1.0`, self-commands the door, runs `advance_dialog` with
  `hold = 8.0` (the cutscene opens a beat after its trigger and flashes
  through gameplay first), asserts `GetPartyMemberCount() == 1`, then
  restores `speed 16.0`. Evidence: Room3 route; `scenario.py`
  `_advance_dialog` (`hold`).
- Authored barks: Trask's tutorial entries whose reply 0 is a
  `k_pend_time01` terminator (`authored_barks = [37, 48, 50, 53]`) are
  answered automatically whenever they interrupt a wait; entry 73 shares the
  shape but sets `end_attack`, so the route picks it itself. Evidence: Trask
  route `[settings]`; `scenario.py` `DEFAULT_SETTINGS["authored_barks"]`.
Verify: `exec "$(cat scripts/examples/harness/80_signal_event.lua)"` and
`exec "$(cat scripts/examples/harness/90_run_script.lua)"`, then read the
world (`10_world_probe.lua` globals, `50_doors.lua` flags).

## 9. Lua hooks: what the routine bridge answers from inside an event

Verified live 2026-09-16 on k1_steam_103_unpacked while building
`scripts/examples/cursed/` (a trace script printing every `OnRunScript` name
plus probes from inside the hook; the harness `lua` state answered the same
questions between events).

- **`GetIsEnemy(x, pc)` is 0 inside a RunScript/EventHandler hook** for a
  creature it answers 1 for from the harness state (a `g_sithtroop01` set
  to STANDARD_FACTION_HOSTILE_1). Hook code that wants "hostile" must use
  `IsObjectPartyMember(x) ~= 1` (or `GetStandardFaction`), not reputation.
- **`GetIsDead(corpse)` is still 0 while the death script runs.** The
  death hook is `OnRunScript` with `k_def_death01` (module deaths use their
  own `*dead*` resrefs) running ON the corpse; `OnCreatureDeath` never
  dispatches. Instant effects applied from the harness state do resolve
  synchronously (`EffectDeath` then `GetIsDead` == 1 in one chunk).
- **A lootless corpse is removed ~3 s after death** (spawned troopers
  killed by `EffectDeath` were `GetIsObjectValid` == 0 within 30 s; a rise
  timer at 3000 ms found the object gone, at 800 ms found it). Anything that
  wants the body must act inside that window.
- **`EffectResurrection` did not revive such a corpse** (`dead` stayed 1,
  hp -11, in the same chunk and 2.5 s later). Rebirth works: `CreateObject`
  on `GetPosition(corpse)`, `DestroyObject(corpse)`, `EffectDisguise` on the
  new body (`verify: valid=1 dead=0 hp=25 app=21`).
- **`OnCreatureAttacked` fires for NPC victims, not for the player**
  (`creature == pc` never seen while the PC was being hit; `attacker == pc`
  does fire). Read the PC's HP delta on `OnTick` for "you got hurt".
- **`OnModuleAcquireItem` is live** and fires more than once per item;
  debounce on the item id. `CreateItemOnObject("g_i_medeqpmnt01", pc, 1)` is
  the medpac (there is no `g_i_medpac01` in chitin.key).
- **`GetFirstPC()` is 0x7FFFFFFF in this session** and so is the `creature`
  argument the PC's own events carry; `GetIsObjectValid` == 1, position,
  local numbers, effects and `CreateObject` all work through that handle.
  The harness state snapshot shows `pc.id` the same way. Compare against it,
  do not treat it as OBJECT_INVALID.
- **`SetLocalNumber(pc, 6|7, n)` round-trips** between a script state and
  the harness state; it is the simplest cross-state channel for a route to
  gate on script progress (`assert_lua ... poll = true`).
- **`kp.speed` is whole ticks per frame (1..16) and cannot slow the game**;
  `kp.game_speed(scale)` (added 2026-09-16) is the engine SetGameSpeed
  scale in (0, 16] and does: 0.25 is real slow motion. The harness `speed`
  command accepts the same range now.
- **Names carry a trailing NUL** (`GetName` -> "Sith Trooper\0"); a print
  with an embedded NUL truncates the log line there. Strip with
  `s:gsub("%z+$", "")` before formatting.
- **`GetFirstObjectInArea` answers the whole area**, including cutscene
  actors in other rooms (Carth, Darth Bandon on the bridge of end_m01aa);
  demos that touch "everyone" want a distance cap.

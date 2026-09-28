# Headless harness: design

How KotorPhasor drives a live game with no screen, no keyboard, and no
person at the desk. The runtime already sits inside the process. The
harness is a control plane on top of it, plus a driver outside it.

The rule this design exists to enforce: the driver never waits a fixed
number of seconds and never types at a pixel. Every step is a request
to the engine, followed by a read of engine state that proves the step
took. A screenshot is a periodic sanity check of that state, never the
thing the driver waits on.

Why the old harness failed is recorded in `scripts/harness/` and
`.mission/`. In short: the cheat console is a gameplay surface fed by
DirectInput, so a headless session had to click Load Game at guessed
coordinates and then wait a fixed time for a LOADING splash it could
only detect by one pixel. Under llvmpipe that wait was wrong in both
directions.

## Shape

```
+---------------------------- game process ---------------------------+
|  engine                                                             |
|    client MainLoop ---> [harness drain] ---> commands run here       |
|    server MainLoop ---> OnTick, timers, Lua                          |
|    hooks -----------> event ring (RunScript, module, area, save...)  |
|                                                                     |
|  kphasor.dll / libkphasor.so                                        |
|    src/harness/channel   listener thread, 127.0.0.1 TCP, JSON lines |
|    src/harness/commands  status, state, lua, events, screenshot...  |
|    src/harness/engine_*  per-game adapters: load, warp, reply, speed |
+---------------------------------------------------------------------+
                ^ newline-delimited JSON over loopback
+---------------------------- driver ---------------------------------+
|  scripts/harness/kpharness/   Python, stdlib first                  |
|    session   boot Xvfb + Wine, or native ELF; connect; tear down     |
|    client    request ids, timeouts, event cursor                     |
|    waits     wait_until(predicate) on engine state, never on time    |
|    oracle    hang, crash, softlock detectors                         |
|    scenario  TOML step files; runner; checkpoints                    |
|    shots     periodic screenshots, optional OCR cross-check          |
+---------------------------------------------------------------------+
```

Three properties fall out of this shape.

1. Every command runs on the game's own main thread, inside a hook body,
   under `KP_HOOK_GUARD`. A harness bug poisons the harness site and
   nothing else.
2. The channel is the same on K1 under Wine, K2 under Wine, and the
   native K2 ELF. Wine's `ws2_32` maps `AF_INET` onto host sockets, so a
   loopback listener inside the 32-bit DLL is a real Linux TCP socket.
   The cheat console is not involved. That matters because the console
   site is unresolved on `k2_steam_linux`.
3. The driver reads state, not pixels. `phase`, `module`, `tick`, the
   active dialog node and its reply list, globals, and journal all come
   from engine memory the corpus has named.

## Control plane

### Configuration

The listener is off unless asked for. Players never run it.

```
# <game>/kotorphasor.ini
harness_port = 27015        # 0 or absent: listener never starts
harness_bind = 127.0.0.1    # loopback only; anything else is refused
```

`KOTORPHASOR_HARNESS_PORT` overrides the file. INI section headers are ignored;
`[harness] port` and `bind` are ineffective keys. The runtime does not read
workspace or scenario TOML. See the separate [driver contract](harness-driver.md)
and [scenario TOML contract](scenario-toml.md) for their ownership and precedence.

### Threads

- The listener thread does `socket / bind / listen / accept` and then
  `recv` in a loop. It parses complete lines into a request struct and
  pushes them onto a mutex-guarded queue. It never touches engine
  memory or a `lua_State`.
- The drain runs at the top of the client MainLoop detour
  (`app.client_main_loop`). WinMain calls the client loop every
  iteration; the server loop only once a server exists. So the client
  loop is the only site that ticks on the main menu, and that is where
  menu-phase commands (load a save, start a game) have to run. The
  drain takes at most `max_per_tick` requests (default 8) so a flood
  cannot stall a frame.
- Replies are queued back to the listener thread and written there.
  The hook body never blocks on a socket.
- One client at a time. A second connection is refused with a JSON
  error line and closed. That keeps "who is driving" unambiguous.

### Wire protocol

Newline-delimited JSON, UTF-8. One request per line, one reply per
line, event frames interleaved only after `subscribe`.

Request:
```json
{"id": 12, "cmd": "state"}
{"id": 13, "cmd": "lua", "code": "return nwscript.call('GetModuleName')"}
{"id": 14, "cmd": "load_save", "dir": "000001 - AUTOSAVE"}
```

Reply:
```json
{"id": 12, "ok": true, "result": {...}}
{"id": 13, "ok": false, "error": "vm not bound: no script has run yet"}
```

Event frame (only after `subscribe`):
```json
{"event": "OnRunScript", "tick": 4471, "seq": 902, "script": "k_pend_door01", "object": 2147483650}
```

Numbers are JSON numbers. Object ids are unsigned 32-bit and are sent
as numbers. Strings are JSON strings. There is no binary framing;
screenshots are written to a file the reply names.

### Commands

| cmd | phase needed | result |
|---|---|---|
| `ping` | any | `{"pong": true, "tick": n}` |
| `status` | any | build, game, runtime phase, `live`, poisoned sites, installed hook count, client tick, server tick, pid, uptime ms |
| `state` | any | the state snapshot below |
| `events` | any | `{"seq": last, "items": [...]}`; args `since` (seq) and `limit` |
| `subscribe` / `unsubscribe` | any | event frames start / stop streaming |
| `lua` | any | runs `code` in the harness `lua_State` on the main thread; returns the chunk's return values serialised (nil, boolean, number, string, flat table). `nwscript.call` needs the VM bound; the error says so |
| `reload` | any | `Host::load_all` then `set_live(true)`. The headless replacement for typing `lua reload` |
| `load_save` | menu or gameplay | begins the engine's own load path for `dir` (a save folder name) |
| `new_game` | menu | the engine's chargen-free start into the first module, if the build supports it; else `unsupported` |
| `save` | gameplay | `slot`, `name`: begins the engine's own save path |
| `warp` | gameplay | `module`: the engine's move-to-module path |
| `dialog` | gameplay | current entry, strref, text (TLK), reply list with link index and active flag, waiting flags |
| `reply` | dialog | `index`: consume the reply through the conversation manager |
| `dialog_skip` / `dialog_abort` | dialog | fast-forward VO wait / end the conversation through its abort script |
| `speed` | any | `scale` (1.0 to 16.0): world-timer scale, re-applied every client frame |
| `fixed_step` | any | `hz` or 0: deterministic snapshot rate |
| `movies` | any | `enabled`: toggle the movie-list no-op |
| `unpause_timers` | any | UnpauseWorldTimer on the client and server world timers, the pair `load_save` pauses. Never a raw write to a paused byte |
| `screenshot` | any | `path`: `glReadPixels` after the frame, written as PPM; the driver converts |
| `quit` | any | clean process exit after the reply is flushed |

A command that the current build cannot honour replies
`{"ok": false, "error": "unsupported on <build>: <site> unresolved"}`.
The driver treats that as a skipped step with a reason, not a crash.

### State snapshot

`state` returns one object. Every field is either read from a named
engine structure or computed from those reads. Nothing is inferred
from a screenshot.

```json
{
  "phase": "gameplay",
  "phase_detail": {"server_mode": 2, "loading_module": 0, "area_not_ready": 0,
                   "input_class": 0, "main_menu": false, "game_over": 0,
                   "pause": 0, "movie": false, "load_error": 0},
  "module": "end_m01aa",
  "server_tick": 4471, "client_tick": 9012,
  "pc": {"id": 2147483649, "x": 1.2, "y": 3.4, "z": 0.0, "hp": 24, "max_hp": 24},
  "party": [ {"id": ..., "tag": "trask"} ],
  "dialog": null,
  "globals_hash": "9c1b...", "journal_hash": "aa02...",
  "counts": {"globals": 812, "journal": 3},
  "live": true, "poisoned": []
}
```

`phase` values and their engine predicates, from the recovered source:

| phase | predicate |
|---|---|
| `menu` | no server, or the main-menu panel exists |
| `loading` | reentrant stats `continue_message_processing == 1`, or server `loading_module == 1`, or client `area_not_ready_to_display == 1` |
| `gameplay` | server `server_mode == 2` and client `input_class == 0` and in-game GUI status is normal |
| `dialog` | client `input_class == 3` or the in-game GUI dialog flag is set |
| `movie` | movie player `movie_playing` |
| `paused` | server `pause_state` bit 0 (player) or bit 1 (combat / time stop) |
| `minigame` | client `input_class == 1` |
| `gameover` | client `game_over_state != 0` |
| `error` | reentrant stats `load_game_error != 0` |

Those offsets are per build. They are data, in the address tables,
under `field` entries next to the function sites. A build that lacks
one reports `phase: "unknown"` with the fields it does have.

`pc` and `party` come from the routine bridge (`GetFirstPC`,
`GetPosition`, `GetCurrentHitPoints`, party routines) and are `null`
until the VM is bound. `globals_hash` and `journal_hash` are FNV-1a
over a walk of the global variable table and the journal list, so the
driver can detect "nothing changed" without pulling every value.
`globals` and `journal` commands pull the values.

### Events

Every existing hook body already has a point where it knows what the
engine is about to do. Each pushes one record into a fixed ring (4096
entries, lock-free single producer per thread is not needed: all
producers run on the main thread). Records carry `seq`, `server_tick`,
event name, and up to four scalar fields. `OnRunScript` records the
script name and object id. Module, area, save and load handlers record
their names. The ring never allocates after startup.

This is how the harness tests KotorPhasor's own event functions:
a scenario asserts that `OnModuleLoad` was followed by `OnAreaEnter`
was followed by a `k_pend_*` `OnRunScript` after a warp to the Endar
Spire, by cursor, not by sleeping.

### Engine adapters

`src/harness/engine.hpp` declares the surface the commands call:

```cpp
struct EngineAdapter {
    virtual ~EngineAdapter() = default;
    virtual const char* name() const = 0;             // "k1", "k2"
    virtual Phase phase(PhaseDetail* out) = 0;
    virtual std::string module_name() = 0;
    virtual Result load_save(const std::string& dir) = 0;
    virtual Result new_game() = 0;
    virtual Result save(int slot, const std::string& name) = 0;
    virtual Result warp(const std::string& module) = 0;
    virtual Result dialog(DialogState* out) = 0;
    virtual Result reply(int link_index) = 0;
    virtual Result dialog_skip() = 0;
    virtual Result dialog_abort() = 0;
    virtual Result set_speed(float scale) = 0;
    virtual Result set_fixed_step(int hz) = 0;
    virtual Result set_movies(bool enabled) = 0;
    virtual Result walk_globals(GlobalsVisitor&) = 0;
    virtual Result walk_journal(JournalVisitor&) = 0;
};
```

`Result` is `{bool ok; std::string error;}`. An adapter is built from
the resolved address table. Every engine function and field it uses is
a logical site in `data/hooksites.toml`, resolved per build by the
existing registry. A site that did not resolve makes the matching
method return `unsupported`, and the adapter logs which sites it is
missing once at install. The adapter never dereferences an address it
did not get from the table.

K1 gets the full adapter first. K2 GOG Aspyr (symbol-sourced) is next.
Unbound builds report unsupported and remain unpatched until target-native
bindings exist.

The adapter is called only from the drain, on the main thread. The
engine functions are `__thiscall` on Windows and the corpus records
the convention per site; the existing `hooks/thiscall.hpp` shims are
the way to call them.

### New sites

Named logically, resolved per build. All were located in the corpus
during the Understand phase; the file and line for each is in the
mapper reports that produced this document.

Detours:
- `app.client_main_loop` (kind changes from `reference` to `detour`): the drain, the screenshot, the speed re-apply.
- `client.set_game_speed`: the per-frame `SetGameSpeed(1.0|0.25)` call would clobber a harness scale; the detour applies the harness scale after the engine's.
- `client.play_movies`: `PlayMoviesInExoArrayList`; no-op when movies are disabled.

Calls (not hooked, called by the adapter):
- `app.create_server`, `net.start_connect_to_session`, `msg.request_status`
- `app.set_load_from_savegame`, `client.set_loading_savegame`, `client.send_load_game_request`, `client.send_save_game_request`
- `app.start_new_module`, `app.load_module`
- `dialog.reply_dialog`, `dialog.handle_reply`, `dialog.check_script`, `dialog.send_replies`, `dialog.skip_past`, `gui.close_dialog`, `gui.handle_dialog_selection`
- `timer.set_snapshot_scale`, `timer.set_fixed_snapshot_rate`, `client.get_world_timer`, `server.get_world_timer`
- `app.get_global_variable_table`, `app.get_party_table`, `app.get_module`

Fields (address plus offset, no code):
- `server.server_mode`, `server.loading_module`, `server.move_to_module_pending`, `server.move_to_module_string`, `server.pause_state`
- `client.input_class`, `client.main_menu`, `client.area_not_ready_to_display`, `client.loading_savegame`, `client.disable_movies`, `client.game_over_state`, `client.input_disabled`
- `stats.continue_message_processing`, `stats.phase`, `stats.load_game_error`
- `gui.dialog_active`, `gui.reply_count`, `gui.reply_texts`, `gui.visible_to_link`
- `dialog.current_entry`, `dialog.current_reply`, `dialog.entries`, `dialog.link_stride`
- `gvt.identifiers`, `gvt.bools`, `gvt.numbers`, `gvt.strings`, `journal.entries`

Adding a field kind to the registry is the one schema change this
design needs. It is additive to the in-flight hook-pack work: a `field`
site has `addr`, `offset`, `size`, and `expected_bytes` on the owning
function when there is one.

## Driver

`scripts/harness/kpharness/` is a Python package that runs under the
system interpreter (`/usr/bin/python3`, which has Pillow and
pytesseract; the linuxbrew one on `PATH` does not). Everything except
the optional screenshot conversion and OCR is standard library.

```
kpharness/
  __init__.py
  cli.py          kpharness boot|status|state|exec|run|shots|down
  session.py      GameSession: discover, stage, boot, connect, teardown
  client.py       Channel: JSON lines, ids, timeouts, event cursor
  waits.py        wait_until, wait_phase, wait_module, wait_event
  oracle.py       Watchdog: hang, crash, softlock
  scenario.py     TOML steps -> runner
  checkpoints.py  named save folders in and out of the save dir
  shots.py        periodic screenshot, PPM -> PNG, optional OCR
  targets.py      per-game facts: exe name, ini path, save dir, start module
  discover.py     thin wrapper over tools/kpdiscover.py
scenarios/
  k1_smoke.toml
  k1_events.toml
  k1_dialog_walk.toml
  k1_softlock_detect.toml
  k2_smoke.toml
```

### Session

`GameSession(target)` where `target` is `k1`, `k2-wine`, or `k2-native`.

1. Discover the install by content (`kpdiscover`). Never a hard-coded
   path.
2. Stage a writable tree under `tmp/<target>_harness/`: real
   directories for anything the game or the runtime writes (`saves`,
   `kotorphasor/`, the ini), symlinks for the rest. Copying the game is
   not allowed; the K2 depot is 36 GB.
3. Install the runtime from `build/` with `scripts/install_to_game.sh`,
   write `kotorphasor.ini` with a free port, tune the game ini
   (windowed, cheats on, movies off, frame buffer off under llvmpipe).
4. Take the per-display lock (`lock.sh` semantics, reimplemented),
   start Xvfb, start the game: `wine <exe>` in an isolated desktop
   session env for Windows builds; `LD_PRELOAD=libkphasor.so ./kotor2`
   with `XDG_DATA_HOME` pointed into the staged tree for the ELF.
5. Connect to the port. Boot is complete when `status` answers and
   reports the expected build. There is no window scan.
6. Teardown kills by process name, stops Xvfb, releases the lock, and
   keeps every log under `tmp/<target>_harness/runs/<timestamp>/`.

### Waits

`wait_until(fn, timeout, poll=0.25)` calls `state` (or `events`) until
`fn` says yes. The timeout is a ceiling that turns a hang into a
failure with a state dump, not a schedule. Provided predicates:
`phase_is`, `module_is`, `event_seen(name, after_seq)`,
`dialog_waiting`, `global_equals`, `journal_state`.

### Oracles

- **Crash**: process gone, or Wine stderr contains
  `wine: Unhandled` / `starting debugger`, or the runtime log has
  `fault in hook body` / `[fault] unrecoverable`.
- **Hang**: process alive and `client_tick` unchanged across
  `hang_seconds` (default 20). The oracle then attaches `winedbg` (or
  `gdb -p` for the ELF) for one stack dump before killing.
- **Load stuck**: `phase == loading` beyond `load_seconds` (default
  300 under llvmpipe) with `stats.phase` not advancing.
- **Softlock**: `phase == gameplay` or `dialog`, and the fingerprint
  `(module, quantised pc position, dialog node, globals_hash,
  journal_hash, party)` unchanged for `stagnation_seconds` while the
  scenario is waiting on a progress predicate. Reported with the last
  200 events and the last screenshot.
- **Refusal**: runtime log `refusing to install`. Fails the boot at
  once with the reason.

### Screenshots

`shots.py` asks the game for a frame every `interval` seconds (default
120), converts it, and stores it next to the run log with the `state`
that was current when it was taken. A scenario can add
`expect_screen = "dialog"` on a step; the check runs OCR over the reply
region and fuzzy-matches the TLK text the engine reported for the
node. A mismatch is a warning with both images attached, never a wait
condition.

### Scenarios

Scenarios are TAS runs by default. `settings.game_speed` is applied before the
first step, defaults to the engine's maximum supported `16.0`, and accepts any
finite value in `(0, 16]`. An explicit `1.0` selects retail timing and does not
require a speed binding. The report records the requested and engine-reported
effective scale. State and event predicates remain the authority at every
scale; file I/O, llvmpipe rendering, and voice playback remain wall-clock work.

```toml
name = "k1 endar spire: events and dialog"
target = "k1"
[[step]]
do = "load_checkpoint"; name = "endar_start"
[[step]]
wait = "phase"; equals = "gameplay"; timeout = 300
[[step]]
expect_events = ["OnModuleLoad", "OnAreaEnter"]
[[step]]
do = "warp"; module = "end_m01aa"
[[step]]
wait = "module"; equals = "end_m01aa"
[[step]]
do = "lua"; code = "nwscript.with_caller(nwscript.call('GetFirstPC'), function() nwscript.call('ActionStartConversation', nwscript.call('GetObjectByTag','end_trask',0), '') end)"
[[step]]
wait = "phase"; equals = "dialog"
[[step]]
do = "reply"; pick = "first_active"
[[step]]
wait = "global"; name = "END_TRASK_TALK"; equals = 1
[[step]]
screenshot = true
```

`load_checkpoint` copies a named save folder into the save dir and
calls `load_save`. Checkpoints are created by scenarios too:
`do = "save"; checkpoint = "endar_start"` after a wait, and the folder
is kept under `tmp/checkpoints/<target>/<name>/`.

### Softlock scenario

`k1_softlock_detect.toml` proves the detector by inducing one: set the
global a door script reads to a value that keeps the door shut, walk
the PC to the door, ask the scenario to wait for the next area, and
assert the run fails with `softlock` inside the budget. Then clear the
global and assert the same wait succeeds.

## Time

`kp.speed` calls the server loop extra times; the engine's world timers
still read the wall clock, so delays did not shrink. The harness uses
the engine's own scaling instead: `SetSnapshotScale` on every client
and server world timer, re-applied in the client-loop detour after the
engine's per-frame `SetGameSpeed`. `fixed_step` switches all timers to
`SetFixedSnapshotRate`, the mode the engine's own input-playback
feature uses, so a scenario can run frame-exact.

## Self-test

Offline, in `ctest`:
- `kp_harnesstest`: starts the channel on a free loopback port in the
  test process, drives it with a client thread, and proves that
  requests execute on the thread that calls the drain, that malformed
  lines get an error reply and do not kill the connection, that the
  event ring keeps order under wrap-around, and that the JSON codec
  round-trips every value type the protocol uses.

Live, opt-in, through the driver:
- `k1_smoke`: boot, `status`, `load_save` of the shipped autosave,
  `wait phase gameplay`, `state`, screenshot, `quit`.
- `k1_events`: the event ordering assertion above.
- `k1_dialog_walk`: every reply of one conversation from a checkpoint,
  rolled back between picks.
- `k1_softlock_detect`: the induced softlock.
- `k2_smoke`: the native ELF, same as `k1_smoke` minus `reply`.

## Work packets and file ownership

Packets run in parallel and touch disjoint files.

| packet | owns |
|---|---|
| A channel | `src/harness/{channel,commands,json,ring}.{cpp,hpp}`, `src/harness/harness.cmake`, `tools/kp_harnesstest.cpp`, the additive edits in `src/runtime/runtime.cpp` (`[harness]` ini keys, `optional[]` row, `on_state_created` row, `select_game` call), `src/runtime/hook_bodies.cpp` (drain call and ring pushes), `CMakeLists.txt` include line |
| B adapter K1 | `src/harness/engine.hpp`, `src/harness/engine_k1.cpp`, `src/harness/engine_k2.cpp` (stub that binds what resolves), `src/harness/fields.hpp` |
| C sites | `data/hooksites.toml` new rows, `field` site kind in `src/hooks/registry.{cpp,hpp}` (additive), per-build address entries for `k1_gog_103`, `k1_steam_103_unpacked`, `k2_gog_aspyr`, `k2_steam_linux`, `data/adjudication/*_harness_bindings.json` |
| D driver | `scripts/harness/kpharness/`, `scripts/harness/scenarios/`, `scripts/harness/kpharness.sh` |
| E docs | `docs/user/harness.md`, `CONTRIBUTING.md` testing tier, `CHANGELOG.md` |

Packet A defines the `EngineAdapter` call sites by including
`engine.hpp`; packet B owns that header. The two agree on the
signatures above, and neither edits the other's files.

## Amendments from the feasibility audit

These override anything above that disagrees with them.

1. **Engine calls run outside the armed guard.** `KP_HOOK_GUARD` claims
   any fault while the top frame is armed, and its `longjmp` skips
   engine frames, leaving engine state torn and all Lua switched off.
   So the adapter wraps every engine call in `enter_hook_body()` /
   `leave_hook_body()` (an unarmed frame: a fault there is a real
   crash and the crash oracle sees it). The guard is armed only around
   request parsing, `is_readable` field reads, and reply serialisation.
2. **The drain gates on its own poison, never on `live()`.** Otherwise
   `reload` could never re-arm anything. Commands that need the host
   check `live()` and `active_host()` themselves and reply with an
   error. `reload` also closes and recreates the harness `lua_State`.
3. **No lock inside the guard.** The drain swaps the pending batch
   into a local vector before `KP_HOOK_GUARD_BEGIN` and pushes replies
   after `KP_HOOK_GUARD_END`. A claimed fault runs no destructors.
4. **Reentrancy.** During LOADING the client loop calls `UpdateScreen`,
   which runs the server loop nested inside the client loop. The drain
   keeps a thread-local `draining` flag and skips when set.
5. **`field` sites** get `SiteKind::Field`. `resolve_from_signatures`
   skips them, the generator emits no `expected_bytes` for them and
   records `offset` and `size`, and `parse()` reads those in both the
   hook-pack and per-build branches. Fields stay `required = false`.
6. **Calling convention is per platform.** `KP_THISCALL` is `thiscall`
   on every i386 target, but the native `kotor2` ELF is GCC code:
   `this` is the first stack argument, cdecl. The adapter picks the
   call shape from `AddressTable::platform_name()`. The existing
   server-loop detour on `k2_steam_linux` has the same latent problem
   and is fixed the same way before any K2 native scenario runs.
7. **Build wiring.** `src/harness/harness.cmake` is included before
   `src/runtime/runtime.cmake` and only sets `KP_HARNESS_SOURCES` and
   defines `kp_harnesstest`. `runtime.cmake` appends those sources to
   the win32 object loop and to `libkphasor.so`, and adds `-lws2_32`
   to the DLL link. Object names are flat `rt_<basename>.obj`, so the
   harness basenames are `channel`, `commands`, `json`, `ring`,
   `engine_k1`, `engine_k2`. `channel.cpp` includes `<winsock2.h>`
   before `<windows.h>`. `Config` gains `harness_port` and
   `harness_bind`; the ini parser ignores section headers, so the keys
   are the global `harness_port` and `harness_bind`.
8. **Address data is generated, not hand-edited.** The runtime gates on
   the JSON `kind`, so `app.client_main_loop` becomes a detour in the
   per-build JSON through `tools/gen_address_tables.py`, regenerated
   against the image in the K1 harness tree. The generator's overlay
   loader globs `<alias>_*_bindings.json` so harness bindings live in
   their own file next to the VM bindings.
9. **`select_game`** is called in `boot_scripts` before `load_all`,
   from the table's game. It is never called today, so a K2 process
   currently gets the K1 routine table.
10. **Screenshot timing.** GL entry points are resolved with
    `GetProcAddress` / `dlsym`, no link dependency, and the read happens
    after `orig(self)` returns inside the client-loop detour, from the
    front buffer.
11. **Listener I/O** uses `select()` over the listen and client sockets
    so replies flow while waiting and a second connection is refused.
12. **`kp_harnesstest`** links only `channel`, `json`, `ring` and the
    platform layer, with the executor as a callback, so it drags in no
    runtime, Lua, or generated tables.
13. **Assumed until read:** the six-call load sequence completing with
    no GUI panel alive, `SetSnapshotScale` / `SetFixedSnapshotRate`
    surviving the per-frame `SetGameSpeed`, and a save-complete
    predicate. The adapter answers `unsupported` with a reason until a
    corpus read settles each, so a scenario failure there is classified
    as a corpus gap.

Facts settled by the gap fills that the adapter relies on:

- The reply path is `CSWGuiDialog::SelectReply(visibleIdx)`, reached
  through the vtable slot at `+0x6c` of the dialog panel
  (`CGuiInGame+0x3c`), or `CGuiInGame::SetDialogSelection(idx, count,
  1)` consumed by the per-frame `UpdateDialog`. Never call
  `ReplyDialog` directly. Visible replies: count at `CGuiInGame+0x114`,
  texts at `+0x118`, link index per row at `+0x11c`. Pick accepted iff
  `+0xb4 != 0`, `+0xd0 == 0`, count `> 0`, and the server dialog's
  current reply `+0x74 == -1`. Abort is `SetDialogSelection(-3, n, 1)`.
- The only server gate on a pending module move is
  `CGuiInGame+0xDC == 0` (K2 `+0xF4`), which is a dead controller-loss
  flag on every PC build. `StartNewModule` from the harness is
  `SetMoveToModulePending(1)` plus the module string and waypoint.
- The client loop has no early return on the menu or during loading,
  but it does not iterate while a movie plays. Movies must be off in
  the ini and neutered by the `client.play_movies` detour.
- Returning 1 from the client-loop detour is a clean `quit`: WinMain
  ORs it into its exit flag.

## Amendments from the reverse-engineering audit

These override the sections above where they disagree.

1. **Load a save** is the engine's own main-menu branch replayed in one
   client tick: `UnpackGame` (this unused), `CreateServer` if no server
   exists, pause both world timers, `StartConnectToSession(net, 0,
   &clientName, &"", 10, 0x10)`, `RequestStatus(message_handler)`,
   `SetPlayerCharacterName("test")` (mandatory: without it the client
   never logs a character in), `SetInputClass(0, 1)`, `DisableInput`,
   `SetLoadFromSaveGame(1)`, `SetLoadingSaveGame(1)`,
   `SendLoadGameRequest(slot, &dir, &lastModule)`. `RunModule` then
   fires by itself: the server broadcasts status 1, the client answers
   `sModule.Run`, and the loopback player is sys-admin. Boot is complete
   when `server_mode == 2`, `loading_module == 0`, the reentrant stats
   are idle with no load error, and `area_not_ready_to_display == 0`.
   The login reads `TEMP:test.bic`; no corpus path writes that file,
   so the adapter logs every step and the driver treats a module with
   no player as a corpus gap, not a harness bug.
2. **Abort a conversation** with `HandleDialogSelection(gui, -2, n)` or
   `StopDialog(owner)`. Never `SetDialogSelection(-3, ...)`: the update
   path indexes the reply arrays before it looks at the sentinel.
3. **Fixed-step time** must be bracketed by `PauseWorldTimer` and
   `UnpauseWorldTimer` on every timer, because `SetFixedSnapshotRate`
   zeroes the snapshot clock and rewinds world time. Five timers carry
   the game speed: client world, pause, animation; server world, pause.
   The engine's per-frame `SetGameSpeed` writes only the scale, so a
   scale re-applied after the client loop returns survives the next
   frame, and a fixed rate composes with it.
4. **Voice-over waits do not scale.** `IsDialogDelay` short-circuits on
   real audio playing. `dialog_skip` calls `SkipPastDialog(server,
   ownerId)` once per entry; the driver calls it whenever the dialog
   state reports waiting on sound.
5. **Phase reads.** `menu` is `PanelExists(gui_manager, &main_menu->panel)`,
   not the stale `main_menu` pointer. `gameplay` also needs
   `sw_gui_status`. `movie` reads `movie_player->internal->movie_playing`
   or calls `IsMoviePlaying`. `server_mode` is two bytes.
6. **Conventions are hardcoded per call in the adapter.** The registry
   never parses `convention`, and the corpus column is advisory.
   `CheckScript` is `__stdcall` and static. All load-side calls are
   `__thiscall`. On the native ELF every one of them is stack-`this`.
7. **Server-side dialog state** is reached from the panel's owner id
   (`CSWGuiDialog+0x19c0`) through `ClientToServerObjectId`,
   `GetGameObject`, and the object's `CSWSDialog*` at `+0x34`. The
   accept predicate also requires the owner's send-pending flag at
   `+0x48` to be zero.
8. **Never write engine strings raw.** `move_to_module_string` is a
   `CExoString` the engine frees on assignment. Module moves go through
   `SetMoveToModulePending`, `SetMoveToModuleString`, and
   `SetMoveToModuleStartWaypoint`. Every `CExoString*` argument is a
   harness-owned `{char*, len}` the engine never assigns into.
9. **Dropped from the adapter's call list:** `dialog.reply_dialog`,
   `dialog.handle_reply`. `new_game` stays unsupported until a writer
   for the login character file is located. The journal pointer at
   `CSWPartyTable+0x11c` may be null.
10. **Sites added** by the audit: `client.set_player_character_name`,
    `gui.unpack_game`, `client.get_client_name`, `client.net_layer`,
    `client.message_handler`, `client.get_pause_timer`,
    `client.get_animation_timer`, `server.get_pause_timer`,
    `timer.pause_world_timer`, `timer.unpause_world_timer`,
    `gui.panel_exists`, `client.gui_manager`, `client.movie_player`,
    `client.is_movie_playing`, `gui.sw_gui_status`, `gui.dialog_owner`,
    `server.client_to_server_object_id`, `server.get_game_object`,
    `object.dialog_ptr`, `object.dialog_send_pending`,
    `object.stop_dialog`, `server.set_move_to_module_pending`,
    `server.set_move_to_module_string`,
    `server.set_move_to_module_start_waypoint`, `module.name`.

## What this does not do

It does not replace the coverage scanner. Static reachability over the
dialog graph stays the fast path for "is this node reachable at all";
the harness is how a suspect is confirmed live.

It does not speed up llvmpipe. A module load is still tens of seconds.
Checkpoints are how a plot point costs one load instead of a chain.

It does not make the retail GUI speakable, and it does not claim K2
parity the corpus cannot yet support. A K2 build reports which
commands it lacks and the scenarios skip them by name.

## Known issues in the injected runtime

A threading review of the harness in flight raised four findings that are
not harness findings: they describe the runtime the harness was built on
top of. They are recorded here rather than fixed, because each one is a
redesign of the injected runtime, and the runtime as it stands is the one
thing that currently works in a live game. Any attempt on them belongs in
its own change, with a live boot behind it.

1. `src/runtime/hook_bodies.cpp:233-254, 293-315, 641-675, 749-772`,
   `src/harness/commands.cpp:541-675`, `src/api/routines.cpp:298-327` --
   armed guards enclose Lua dispatch, reload callbacks and `nwscript.call` VM
   calls. A script engine call faults, the guard claims it, and the
   `longjmp` leaves engine and VM state without running destructors. The
   fix is to keep every Lua path that can reach the engine outside an
   armed guard and guard only parsing, serialisation and safe probes.

2. `src/runtime/runtime.cpp:545-565`, `src/lua/host.cpp:260-266,
   290-294` -- `Runtime::start()` runs on the bootstrap worker, and
   `Host::load_all()` and `OnScriptLoad` run Lua there. A callback that
   calls `nwscript.call` reaches the game VM from the wrong thread, and `live`
   is published before `OnScriptLoad` finishes. The fix is to load
   scripts on the game thread and publish `active_host` / `live` after
   lifecycle initialisation.

3. `src/runtime/runtime.cpp:221-235, 249-250, 556, 589, 660`,
   `src/runtime/runtime.hpp:70-72` -- `phase_` and the runtime's
   lifecycle strings are read by hook, status and log threads while
   start and stop write them, with no synchronisation.

4. `src/runtime/runtime.cpp:228-234` -- the log spin lock is held across
   file I/O while a caller may be inside an armed guard. A fault during
   logging skips the unlock, and fault recovery then logs and spins for
   ever.

Two smaller notes from the same pass, kept for the next reader:

- `gui.reply_inactive_count` is an optional field row. Without it every
  dialog reply reports `active: true`, because the client's reply table
  stores only the total row count; active rows come first and greyed
  rows are appended, and only the inactive count separates them
  (`nwsdialog.cpp:3796-3802`). A build whose table carries the row gets
  the exact split with no code change.
- `timer.paused` is unresolved on K2, so `fixed_step` reports
  unsupported there. Bracketing a timer without knowing whether the
  engine had already paused it would unpause a paused timer.

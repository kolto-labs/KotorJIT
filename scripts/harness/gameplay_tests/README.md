# Gameplay tests

Two shapes live here, and the difference is what each is actually checking.

**Before `--live`:** if live tests fail instantly with `Xvfb failed`, run
`quota -s` and check `/tmp`. Xvfb writes `/tmp/.tX<n>-lock` and a full tmpfs
user quota looks exactly like a harness bug.

**Console timing:** heartbeats fire while the LOADING splash is still up.
`live_session.sh` and `drive_k1_console.sh` wait until the menu chrome pixel
at (40,46) is no longer `#292E36` (gameplay HUD / minimap) before opening the
console. `POST_LOAD_WAIT` is only a short pad after that (default 2s).
`SPLASH_WAIT` (default 120s) is the ceiling for the splash poll. Typing
before the splash clears lands on the loading bar and never reaches
`hyperstim.log`.

**Console input:** KOTOR reads keyboard through DirectInput. Harness typing must
use focused **XTEST** events (`xdotool type` after `windowactivate`), not
`xdotool --window` (XSendEvent), which the game ignores.

**Recording:** `ffmpeg` x11grab competes for the same display and can swallow
console keystrokes if started before the console smoke test passes.
`live_session.sh` starts recording only after `lua status` succeeds.

**Research game data offline:** `./scripts/harness/kq.sh grep '\.Tag =' -t utc -m manm26ad`
indexes the install (tags, scripts, modules) so warp targets and object tags in
tests match real blueprints. Requires `cleanhouse/kq-cli` built or `KQ_BIN` set.

**Gameplay demo recordings (scripts in action, ~1 min each):**

Discover sequences first (inline queue commands, no batch driver). See
`docs/showcase-demos/`. Only record after a single demo passes:

```bash
./scripts/harness/pick_save.sh dantooine_party   # when party required
./scripts/harness/demo_play.sh 30_battle_meditation
./scripts/harness/demo_play.sh all            # 30/40/50 only
# ./scripts/harness/demo_play.sh all-wip       # 10/20/60. Not release-ready
```

`demo_play.sh` drives real movement (`#click` / `#key w`), combat (`Tab` +
attack clicks), and log oracles after each warp. Output: `tmp/demos/<name>.mp4` +
`.gif`. Do not treat flawed prior recordings as canonical. Re-run after playbook
changes.

## Fast: the Lua host without the game

`test_arbitration.sh` and `test_quarantine.sh` link `kp_luatest`, which loads a
script directory and dispatches one synthetic event through the real
`lua::Host` and the real arbitration rule. No game, no Wine, no Xvfb. These
run in under a second and belong in any regular CI. Write one of these when
what you're checking is the **host itself**: dispatch order, return
arbitration, error quarantine, hot reload. If `kp_luatest --list` shows the
event you need and you can hand-write plausible arguments for it, this is the
right shape.

```bash
./build/kp_luatest scripts/examples/arbitration OnRunScript k_def_heartbt01 0 0
```

## Slow: a real, running game

Everything else needs the actual engine. The thing under test is
whether a real hook fires with real arguments during real gameplay.
A hand-written `kp_luatest` argument list cannot stand in for that.
These take minutes, need Xvfb + Wine + a copy of the game, and
belong in a manual or nightly run, not a fast loop.

The pattern, every time:

1. **Deploy.** Copy `scripts/examples/probe/00_probe.lua` alongside whatever
   you're testing, into `$GAME_DIR/hyperstim/scripts/`. Nothing else in the
   runtime logs which stock scripts the engine ran. The probe does, by
   defining `OnRunScript` and printing what it receives, and it is also the
   gameplay-reached oracle `live_session.sh` depends on. Skipping this means
   the boot itself hangs at "no gameplay script ran" until `LOAD_WAIT` expires.
   See `lib.sh`'s `deploy_scripts`.

   If the test drives movement (`#key w` and friends), also deploy
   `scripts/examples/probe/10_position_trace.lua`. There is no visual way to
   confirm a keypress actually moved the character under headless llvmpipe.
   The world renders black there as of this writing, so this is the only
   confirmation that `#key w` did anything at all rather than landing on an
   unfocused window. It prints `[trace] t=<tick> pos X Y Z face F` whenever the
   player's position or facing changes by more than a small threshold. A test
   that drives movement and sees no `[trace]` lines has a focus or input
   problem, not a combat problem, and should fix that before doubting anything
   else.

2. **Boot once, drive many.** `live_session.sh` boots the game, loads the
   first save, opens the console, and then blocks reading a queue file.
   Append a line, it gets typed. `#screenshot` / `#console` / `#key X` /
   `#sleep N` are control lines, everything else is typed as a console
   command. This exists because rebooting per-assertion costs 60-90 seconds
   each and a real investigation needs dozens of small checks in one session.

   ```bash
   GAME_DIR=/dev/shm/kp_k1 OUT=tmp/live RECORD=1 ./scripts/harness/live_session.sh &
   until [[ -f tmp/live/ready ]]; do sleep 1; done

   Q=tmp/live/queue; D=tmp/live/done
   send() { echo "$1" >> "$Q"; local n=$(wc -l < "$Q")
            until [[ "$(cat "$D" 2>/dev/null)" == "$n" ]]; do sleep 0.5; done; }

   send "lua exec nwscript.call('GetFirstPC')"
   send "warp end_m01aa"          # a warp CLOSES the console. See below
   send "#console"                # reopen it before typing anything else
   send "lua exec nwscript.call('GetName',nwscript.call('GetFirstPC'))"

   touch tmp/live/stop            # tears down cleanly
   ```

3. **Drive real state changes, not scripted ones.** The console's
   `lua exec nwscript.call('ActionAttack',...)` queues an engine action but does not
   reliably resolve while the console is holding focus. Real keyboard input
   (`#key w` a few times, console closed) reliably produces real combat. This
   was verified empirically, not assumed: raw movement into the Endar Spire's
   scripted encounter produced `k_def_attacked01` / `k_def_damage01` /
   `k_def_combend01` every time; console-driven `ActionAttack` frequently did
   not. `GetNearestCreature`'s first argument is `CREATURE_TYPE_REPUTATION`
   which is **3**, not 4. `4` is `CREATURE_TYPE_IS_ALIVE` and silently
   returns `OBJECT_INVALID` for a hostility query, which reads exactly like
   "no hostiles nearby" and cost real time to catch.

4. **Assert on the log, not the screen.** `$GAME_DIR/hyperstim.log` is
   flushed per line. `wine.log` (the game's own stdout) is block-buffered
   under Wine and can lag by minutes. Reading it reads as "nothing
   happened" when something happened five minutes ago. Every example script
   calls `kp.print()` once when it actually acts (`[ahto] strike N...`,
   `[meditation] round N...`); grep for that line, not for the event having
   merely been dispatched, since a script can be dispatched, decide the
   condition doesn't apply, and correctly do nothing.

5. **Tear down.** `touch "$OUT/stop"`; `live_session.sh`'s own trap kills the
   game, wineserver and Xvfb and releases its display lock (see
   `scripts/harness/lock.sh`). A session whose *host* process dies without
   reaching that trap (the host process died mid-run, or the session moved to
   another machine) leaves Xvfb and wine running with nothing to notice. The next
   `live_session.sh` invocation on the same `DISPLAY_NUM` detects that
   automatically (a dead or PID-recycled lock owner is reclaimed without
   needing `FORCE=1`) rather than requiring a human to remember to clean up.

## A bug this pattern actually found

Every `OnRunScript` example compared `script_name == "k_def_attacked01"` and
none of them ever fired, despite the probe log proving the real script ran.
Hex-dumping the bytes in a live, instrumented copy of the deployed script
(edit the copy under `$GAME_DIR/hyperstim/scripts/`, `lua reload`, retrigger,
read the log. Never edit the committed copy for this) showed
`k_def_attacked01\0`: the engine's `CExoString::length` for this specific
string includes a trailing NUL, so every name arriving through
`vm.run_script` was one byte longer than any literal comparison could ever
match. Fixed once in `read_exostring()` (`src/runtime/hook_bodies.cpp`) rather
than in each of the N scripts that would otherwise need to know about it.
That fix could not have been found by reading the code. The C++ faithfully
copied exactly what the engine reported as the string's length, and nothing
about the type signature said the length was wrong. Only running the real
game and looking at the real bytes found it.

## Writing a new test

Fast (host-only): copy `test_arbitration.sh`, point it at a script directory
under `scripts/examples/`, dispatch the event `kp_luatest --list` names, assert
on stdout with `assert_contains` / `assert_contains_re` from `lib.sh`.

Slow (live game): decide what real state the script needs (a module, a party
member, a combat event) and how to reach it from a fresh save with console
commands. `warp <module>`, `heal`, `givecredits N`, `addlevel`,
`revealmap`, real `#key` presses. Deploy, drive, assert on the log, tear down.
If you are not sure the state you think you're producing is the state you're
actually producing, add a diagnostic print to the *deployed* copy, `lua
reload`, and look at the raw log. That is exactly how the NUL-byte bug above
was found. Guessing instead of looking is the failure mode this whole
pattern exists to avoid.

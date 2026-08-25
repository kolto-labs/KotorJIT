# Gameplay tests

Two shapes live here, and the difference is what each is actually checking.

## Fast: the Lua host without the game

`test_arbitration.sh` and `test_quarantine.sh` link `kp_luatest`, which loads a
script directory and dispatches one synthetic event through the real
`lua::Host` and the real arbitration rule -- no game, no Wine, no Xvfb. These
run in under a second and belong in any regular CI. Write one of these when
what you're checking is the **host itself**: dispatch order, return
arbitration, error quarantine, hot reload. If `kp_luatest --list` shows the
event you need and you can hand-write plausible arguments for it, this is the
right shape.

```bash
./build/kp_luatest scripts/examples/arbitration OnRunScript k_def_heartbt01 0 0
```

## Slow: a real, running game

Everything else needs the actual engine, because the thing under test is
whether a real hook fires with real arguments during real gameplay -- which is
exactly the kind of thing a hand-written `kp_luatest` argument list cannot
stand in for. These take minutes, need Xvfb + Wine + a copy of the game, and
belong in a manual or nightly run, not a fast loop.

The pattern, every time:

1. **Deploy.** Copy `scripts/examples/probe/00_probe.lua` alongside whatever
   you're testing, into `$GAME_DIR/kotorphasor/scripts/`. Nothing else in the
   runtime logs which stock scripts the engine ran; the probe does, by
   defining `OnRunScript` and printing what it receives, and it is also the
   gameplay-reached oracle `live_session.sh` depends on. Skipping this means
   the boot itself hangs at "no gameplay script ran" until `LOAD_WAIT` expires.
   See `lib.sh`'s `deploy_scripts`.

   If the test drives movement (`#key w` and friends), also deploy
   `scripts/examples/probe/10_position_trace.lua`. There is no visual way to
   confirm a keypress actually moved the character under headless llvmpipe --
   the world renders black there as of this writing -- so this is the only
   confirmation that `#key w` did anything at all rather than landing on an
   unfocused window. It prints `[trace] t=<tick> pos X Y Z face F` whenever the
   player's position or facing changes by more than a small threshold; a test
   that drives movement and sees no `[trace]` lines has a focus or input
   problem, not a combat problem, and should fix that before doubting anything
   else.

2. **Boot once, drive many.** `live_session.sh` boots the game, loads the
   first save, opens the console, and then blocks reading a queue file --
   append a line, it gets typed; `#screenshot` / `#console` / `#key X` /
   `#sleep N` are control lines, everything else is typed as a console
   command. This exists because rebooting per-assertion costs 60-90 seconds
   each and a real investigation needs dozens of small checks in one session.

   ```bash
   GAME_DIR=/dev/shm/kp_k1 OUT=tmp/live RECORD=1 ./scripts/harness/live_session.sh &
   until [[ -f tmp/live/ready ]]; do sleep 1; done

   Q=tmp/live/queue; D=tmp/live/done
   send() { echo "$1" >> "$Q"; local n=$(wc -l < "$Q")
            until [[ "$(cat "$D" 2>/dev/null)" == "$n" ]]; do sleep 0.5; done; }

   send "lua exec kotor.GetFirstPC()"
   send "warp end_m01aa"          # a warp CLOSES the console -- see below
   send "#console"                # reopen it before typing anything else
   send "lua exec kotor.GetName(kotor.GetFirstPC())"

   touch tmp/live/stop            # tears down cleanly
   ```

3. **Drive real state changes, not scripted ones.** The console's
   `lua exec kotor.ActionAttack(...)` queues an engine action but does not
   reliably resolve while the console is holding focus -- real keyboard input
   (`#key w` a few times, console closed) reliably produces real combat. This
   was verified empirically, not assumed: raw movement into the Endar Spire's
   scripted encounter produced `k_def_attacked01` / `k_def_damage01` /
   `k_def_combend01` every time; console-driven `ActionAttack` frequently did
   not. `GetNearestCreature`'s first argument is `CREATURE_TYPE_REPUTATION`
   which is **3**, not 4 -- `4` is `CREATURE_TYPE_IS_ALIVE` and silently
   returns `OBJECT_INVALID` for a hostility query, which reads exactly like
   "no hostiles nearby" and cost real time to catch.

4. **Assert on the log, not the screen.** `$GAME_DIR/kotorphasor.log` is
   flushed per line; `wine.log` (the game's own stdout) is block-buffered
   under Wine and can lag by minutes -- reading it reads as "nothing
   happened" when something happened five minutes ago. Every example script
   `print()`s once when it actually acts (`[ahto] strike N...`,
   `[meditation] round N...`); grep for that line, not for the event having
   merely been dispatched, since a script can be dispatched, decide the
   condition doesn't apply, and correctly do nothing.

5. **Tear down.** `touch "$OUT/stop"`; `live_session.sh`'s own trap kills the
   game, wineserver and Xvfb and releases its display lock (see
   `scripts/harness/lock.sh`). A session whose *host* process dies without
   reaching that trap -- an agent killed mid-run, a session moved to another
   machine -- leaves Xvfb and wine running with nothing to notice; the next
   `live_session.sh` invocation on the same `DISPLAY_NUM` detects that
   automatically (a dead or PID-recycled lock owner is reclaimed without
   needing `FORCE=1`) rather than requiring a human to remember to clean up.

## A bug this pattern actually found

Every `OnRunScript` example compared `script_name == "k_def_attacked01"` and
none of them ever fired, despite the probe log proving the real script ran.
Hex-dumping the bytes in a live, instrumented copy of the deployed script
(edit the copy under `$GAME_DIR/kotorphasor/scripts/`, `lua reload`, retrigger,
read the log -- never edit the committed copy for this) showed
`k_def_attacked01\0`: the engine's `CExoString::length` for this specific
string includes a trailing NUL, so every name arriving through
`vm.run_script` was one byte longer than any literal comparison could ever
match. Fixed once in `read_exostring()` (`src/runtime/hook_bodies.cpp`) rather
than in each of the N scripts that would otherwise need to know about it.
That fix could not have been found by reading the code -- the C++ faithfully
copied exactly what the engine reported as the string's length, and nothing
about the type signature said the length was wrong. Only running the real
game and looking at the real bytes found it.

## Writing a new test

Fast (host-only): copy `test_arbitration.sh`, point it at a script directory
under `scripts/examples/`, dispatch the event `kp_luatest --list` names, assert
on stdout with `assert_contains` / `assert_contains_re` from `lib.sh`.

Slow (live game): decide what real state the script needs (a module, a party
member, a combat event) and how to reach it from a fresh save with console
commands -- `warp <module>`, `heal`, `givecredits N`, `addlevel`,
`revealmap`, real `#key` presses. Deploy, drive, assert on the log, tear down.
If you are not sure the state you think you're producing is the state you're
actually producing, add a diagnostic print to the *deployed* copy, `lua
reload`, and look at the raw log -- that is exactly how the NUL-byte bug above
was found, and guessing instead of looking is the failure mode this whole
pattern exists to avoid.

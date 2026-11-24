# Test the game without a screen

When a managed Xvfb cannot be created because `/tmp` is quota-limited, set
`KP_HARNESS_REUSE_DISPLAY=<display>` to reuse an already running headless X
server. The harness then leaves that display's lifetime untouched. If the
variable is omitted and `/tmp` rejects the Xvfb lock, the harness automatically
selects the first verified existing display in the managed range (100-399).
The harness runs KOTOR with no display and no keyboard, and drives it by
calling the engine. A script asks the game to load a save, warp to a
module, pick a dialog reply, or read the party. The game answers with
its own state. Nothing waits on a pixel and nothing types a key.

This is how ScriptForge tests itself. It is also how a mod author can
find a soft-lock without playing to it.

## What you need

- A KOTOR install. The harness finds it by content, so no path goes in a
  config file.
- Xvfb and Wine, for KOTOR 1 and for KOTOR 2 on Windows.
- A build of the runtime: `cmake -S . -B build && cmake --build build`.
  When the workspace is on a slow or contended drive, use an independent tmpfs
  build without changing the default tree: `cmake -S . -B /tmp/scriptforge-build
  -G Ninja && cmake --build /tmp/scriptforge-build -j3`.  Run the harness with
  `KP_BUILD_DIR=/tmp/scriptforge-build` (or `--build-dir /tmp/scriptforge-build`)
  so staging uses that runtime.
  If the source volume is congested, move both the *existing full* K1 staged
  tree and its dedicated prefix to tmpfs for an isolated live run, then pass
  `--staged /tmp/k1-harness --wineprefix /tmp/wineprefix-k1` (or set
  `KP_STAGED_DIR` and `KP_WINEPREFIX`).  These are opt-in paths: the driver
  never relocates, deletes, or overwrites the default external trees.

## Run a scenario

```sh
./scripts/harness/kpharness.sh run k1_smoke
```

That boots the game, loads the shipped autosave, waits until the engine
reports gameplay, reads the module name back, saves one frame, and
quits. Every log lands under `tmp/k1_harness/runs/<timestamp>/`.

The other scenarios live in `scripts/harness/scenarios/`. List them with
`kpharness.sh list`.

To audit binary coverage without launching a game, run
`tools/harness_coverage_report.py`. It reports each table's total sites,
signature-backed sites, absolute-only sites, and unresolved sites.

The gameplay scenarios include `k1_state_drive` (live alignment and XP
mutation/readback), `k1_quest_drive` (deferred journal update), and
`k1_softlock_detect` (watchdog verdict and recovery exercise). K2-native uses
the same format with only its adjudicated sites enabled; unresolved sites fail
closed.

`assert_lua` makes an engine value a scenario postcondition. It compares both
the JSON type and value, so `true` does not accidentally pass for integer `1`:

```toml
[[step]]
do = "assert_lua"
code = "return nwscript.call('GetHasFeat', 44, nwscript.call('GetFirstPC')) == 1"
equals = true
```

The fresh K1 smoke uses this after gameplay begins to require class-granted
feats 44 and 45. Only the live engine can satisfy that assertion; the offline
fake tests assertion plumbing with a neutral return value.

## Drive it yourself

```sh
./scripts/harness/kpharness.sh boot --target k1
./scripts/harness/kpharness.sh state
./scripts/harness/kpharness.sh exec "return nwscript.call('GetModuleName')"
./scripts/harness/kpharness.sh down
```

`state` returns what the engine believes: the phase, the module, the
party, the active dialog with its reply list, and a hash of the globals
and the journal. A driver waits on those values, never on a clock.

The same engine controls are available inside any loaded Lua script as
`kp.harness.*`. Use `kp.harness.dialog()` and `reply(index)` to drive
authored conversations, `load_save`/`warp` for transitions, and the
`take_*_result()` functions to poll deferred party, item, level, and security
operations. The full operation and return table reference is in
[lua-harness-api.md](../lua-harness-api.md).

## Turn the channel on

Configuration has three independent owners: the runtime's game INI, optional
operator/workspace TOML, and immutable route TOML. The [driver contract](../harness-driver.md)
documents machine paths and precedence; the [scenario TOML contract](../scenario-toml.md)
documents execution policy, resources, ordered steps, and legacy normalization.

The game opens a loopback port only when asked. Add two lines to
`<game>/scriptforge.ini`:

```
harness_port = 27015
harness_bind = 127.0.0.1
```

`SCRIPTFORGE_HARNESS_PORT` overrides the file. With no port the listener
never starts, so a player's install is untouched.

Commands run on the game's own main thread, inside the frame. That is
the only thread on which engine calls are safe.

`dismiss_messagebox` accepts a top modal using the native `CSWGuiMessageBox`
handler, currently bound for K1 GOG 1.03. It validates the handler identity,
sends OK (`0x1f6`, active), and requires the modal stack to shrink and the old
top to disappear. The engine owns cleanup and callbacks; input classes before
and after appear in the runtime log. Inspect the prompt before accepting it,
then verify the next engine action. TOML steps use `do = "dismiss_messagebox"`.

`door_use` takes an exact unsigned 32-bit `door` object id and dispatches the
retail client door-use message after checking that the id names a live door.
For example, `channel.request("door_use", door=74)` returns `dispatched=true`
when the sender was called. Check the door state, player movement, and any
module transition separately: dispatch does not prove the server completed
the action. This command is currently bound for K1 GOG 1.03.

`attack` sends a normal retail attack against an exact unsigned 32-bit client
`target` id: `channel.request("attack", target=14)`. The adapter validates the
corresponding server creature and rejects the player itself. A successful
response reports `dispatched=true`; verify combat, damage, and encounter
completion through subsequent engine observations. Currently bound for K1 GOG
1.03, this path uses combat feat zero.

Container inventory panels can be closed without keyboard input using the
`dismiss_container` command. The adapter first proves the top modal is a live
`CSWGuiContainer`, then sends its native `0x28` close event so the engine sends
the server close message, removes the panel, restores input, and clears pause.

Use `take_all_container` to take every item from an ordinary container and
close its inventory panel. The K1 adapter verifies the top modal is the live,
listed `CSWGuiContainer`, checks that it is in normal inventory mode with Take
All enabled, and sends the panel's native `0x27` event. The engine performs the
item transfer and normal close path; the harness does not write inventory or
GUI state. A K2 build without the equivalent binding reports the command as
unsupported.

```toml
[[step]]
do = "take_all_container"
```

Use `accept_party_selection` when the native party-selection modal is ready.
The K1 adapter requires an initialized in-game GUI, proves the top modal is a
live `CSWGuiPartySelection`, validates the selected-count, selection-mode, and
forced-entry state, then invokes the engine's `AcceptParty` wrapper. It proves
the modal retired and gameplay input and pause were restored. Party membership
is route-specific and should be checked separately with `assert_lua`.

```toml
[[step]]
do = "accept_party_selection"
```

## Write a scenario

```toml
name = "endar spire: first reply"
target = "k1"

[settings]
# Scenarios default to the engine's fastest supported scale (16x). Set this to
# 1.0 when a test specifically needs retail timing; any value in (0, 16] works.
game_speed = 16.0

[[step]]
do = "load_checkpoint"
name = "endar_start"

[[step]]
wait = "phase"
equals = "gameplay"
timeout = 300

[[step]]
expect_events = ["OnModuleLoad", "OnAreaEnter"]

[[step]]
do = "reply"
pick = "first_active"
```

A step either asks the game to do something or waits for the game to
report something. `expect_events` reads the event stream the runtime
records, so a test can assert that a module load was followed by an area
entry without sleeping between them.

The runner applies `settings.game_speed` before the first step and records both
the requested and engine-reported effective scale in `report.json`. The default
is `16.0`, so route tests run as fast as the engine permits while their waits
continue to use engine state and event postconditions. Set `game_speed = 1.0`
to opt out. Game speed accelerates world timers, movement, combat, and scripted
delays; it does not accelerate file I/O, software rendering, or voice playback.

## What the watchdog catches

- **Crash**: the process is gone, or Wine reports an unhandled
  exception, or the runtime logs a fault.
- **Hang**: the frame counter stops while the process lives. The
  harness takes one stack dump before it kills the game.
- **Stuck load**: the engine stays in a load with nothing advancing.
- **Soft-lock**: the module, the player position, the dialog node, the
  globals and the journal all stop changing while a step waits for
  progress. The report carries the last events and the last frame.

## Screenshots

The harness takes a frame every couple of minutes and on request. A
frame is a cross-check of the state the engine already reported, and a
mismatch is a warning. No step ever waits on an image.

## Complete live-proof recordings

After a live scenario succeeds, record the same run with the display-aware
wrapper so the video and report refer to one session:

```bash
scripts/harness/record_proof.sh k1_smoke
```

The wrapper writes `live-proof.mp4` and a copy of the exact `report.json`
beside the driver log, and only exits successfully when the scenario itself
passes and both artifacts are non-empty. Pair that bundle with the requested
gameplay screenshot; videos from failed boots are diagnostic captures, not
proof artifacts.

## Checkpoints

A checkpoint is a save folder the harness keeps by name. A scenario
saves one after it reaches an interesting point, then later scenarios
start from it. That is what makes a plot point cost one load instead of
a chain of warps.

## Known limits

- Starting a brand new game is not wired up. Load a save instead.
- KOTOR 2 native (k2-native) does not need a system package install for the
  32-bit GLU library: `kpharness` finds a working copy inside the Steam
  Linux runtime trees on its own (`discover.libglu_dirs()`) and stages the
  case-matching Miles audio symlinks the ELF needs, both automatically at
  `stage()` time. If discovery finds nothing usable on a given machine, set
  `KP_LIBGLU_DIR` or `[harness] libglu_dir` in `kotorphasor.toml` to a
  directory that actually contains `libGLU.so.1`.
- A module load under software rendering takes tens of seconds. Budget
  for it, or start from a checkpoint.

The design, and why it is built this way, is in
[`../harness-design.md`](../harness-design.md).
# Native Steam CLI

For native K2, `KP_HARNESS_STEAM_CMD` may override the Steam CLI command (shell
word splitting, no shell evaluation). The command receives the harness
`DISPLAY`, and the session cleans up the process it starts. Use this to point
the harness at the authenticated Steam launcher available on the host.

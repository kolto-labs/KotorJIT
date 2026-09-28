# Task 7 package-proof audit — 27 September 2026

## Verdict

**Not packageable.**  The approved physical-console boundary has strong host-only
coverage, but no immutable, minimal source/artifact manifest recreates the
current adapter, and no live receipt binds an installed runtime, the runner
snapshot, the exact owned window, and the resulting media to the same bytes.

The current tree must not be copied wholesale.  Its modified `CMakeLists.txt`
also carries independent Mach-O and projectile additions, and `scenario.py`
also carries cancellation changes.  A full-file hash of either would silently
pull unrelated work into a supposed Task 7 snapshot.

This is a read-only audit.  No game, build, package, or source change was made.

## What is approved today

The checked-in Task 7 path is a narrow physical-console implementation:

1. The native `kp.console.v1` adapter observes the existing console service.
2. `PhysicalConsoleDriver` records the pre-input runtime/session/submitted
   identity, sends one physical entry, and accepts only the exact next request,
   outcome, and attributed input/result lines.
3. `OwnedX11Input` obtains a window only from `GameSession` and refuses an
   unowned/reused/malformed display or window.
4. `ScenarioRunner` delegates four verbs: `console_open`, `console_command`,
   `owned_input`, and `advance_ticks`.

The Task 7 report records 22 host tests and a focused CTest pass.  That is good
boundary evidence; it is not a live package receipt.  Existing private frozen
DLL receipts (including the older input-round2 artifact) cannot be substituted
for this current, uncommitted protocol/adapter source without a byte-binding
build and installed-run receipt.

## Minimal source allowlist to freeze

The snapshot must contain **only** the following Task 7 implementation paths,
plus their exact hashes.  `Hunk-only` means the current file has unrelated
dirty changes, so a full-file copy is prohibited until a clean, materialized
Task 7 version is produced.

| Role | Path | SHA-256 | Freeze rule |
|---|---|---|---|
| Python wire schema | `scripts/harness/kpharness/console_protocol.py` | `6b60936c68437c82ab31b068f5be07d35644feb1db8a571369a7b3a6df662e7c` | whole file |
| Exact physical correlation | `scripts/harness/kpharness/physical_console.py` | `e8c972aec6c591fcc5bad47ce3878f5f95551fa3f246e970e15495c1d441e4a5` | whole file |
| Owned X11 keyboard adapter | `scripts/harness/kpharness/owned_x11.py` | `171a7da1711637ec39df0c524dcbbec51dbe47e3929ccde63d2dfa722a3fee12` | whole file |
| Scenario console actions | `scripts/harness/kpharness/console_steps.py` | `41c7745064b313face29c1e656c158f384cb8c5aa829b08668bc390477fb59fd` | whole file |
| Scenario integration | `scripts/harness/kpharness/scenario.py` | `98f1b3678bdd5f363184a621cd5ad8ee12b2f7976c7e1262a8df9931c1bfdf47` | **hunk-only**: four-verb delegation at current lines 593–602; do not take cancellation hunks |
| Session-owned window discovery | `scripts/harness/kpharness/session.py` | `3064be71c6c798bcc43c69e902980169ea58835a146594a73447d1f61005fde3` | Task 7 capture fields/method only; it is otherwise a shared harness file |
| Native wire implementation | `src/harness/console_protocol.cpp` | `a67cb4baabcfc2d92881104ad9399dcb2bff68dcd134fc32050e15b0ad462cd0` | whole file |
| Native wire header | `src/harness/console_protocol.hpp` | `04672437550986c48ade315b4c0a0b2cbb8ba40b85dd9b2baff78f47c0821fa2` | whole file |
| Native dispatch hook | `src/harness/commands.cpp` | `b7e8fb5bba5bac2c7b9d85ab3d2d98e714170abfdc3907a743ff08f1178aea01` | Task 7 include and `protocol` dispatch hunk only |
| Runtime source registration | `src/harness/harness.cmake` | `a9ed1917dd4092accd9dd46f20044e61dfc45e83091feec20f5899a50d81b0ec` | Task 7 one-line source-list hunk only |
| Python boundary regression | `tools/kpharness_physical_console_test.py` | `786d65fd9872f370b006c4496a7b0ea3abebd2e2104e3d7556769e8f55001a1c` | whole file |
| Native wire regression | `tools/kp_consoleprotocoltest.cpp` | `a671fa7ea4beeafd829f531f0064ebd93ab83648752894aabf17df4ea5d4375b` | whole file |
| Test registration | `CMakeLists.txt` | `27b7dbd7e7ad19039423214911c68f39553758820f41df5ed291311fb6a08767` | **hunk-only**: add physical-console Python gate and `kp_consoleprotocoltest`; exclude Mach-O/projectile hunks |
| Wire-contract documentation | `docs/devtools-protocol.md` | `8923a497e2c52ca4f617a677d68b0d6d3f5c8c7a0d619bde9aced2fcce69e4a4` | whole file, documentation only |

The current source hashes are **audit inputs**, not a valid release manifest:
the hunk-only entries must first be rendered onto a declared base revision and
given new full-file hashes.  That rendered tree, its source-archive hash, and
the produced `kphasor.dll`/proxy pair must be the actual snapshot manifest.

### Required runner closure

The supported console verbs run through the creative/ScenarioRunner path, so
the frozen runner must retain this import closure.  These current-byte hashes
are required as dependencies; they do not authorize copying unrelated product
modules.

| Path | SHA-256 |
|---|---|
| `scripts/harness/kpharness/__init__.py` | `9282a855bb913f8b0a3168df7bb6a92c278977f05625e8c649dcc51f74fad4c5` |
| `scripts/harness/kpharness/creative.py` | `f4a7633da12bcf84c4cdc63bcb3bc764452fb39cf42d684c83e6ae6d148325f3` |
| `scripts/harness/kpharness/creative_wine.py` | `aaec2ddcd2a1df7e77ddaead3ec5f05e1642212a8fd4d161757b13cf753d2af7` |
| `scripts/harness/kpharness/recording.py` | `c31a3758f69a70af664b91e3695473c4fa3800d0808c3dfef43d2eb324d9dba7` |
| `scripts/harness/kpharness/creative_checkpoints.py` | `aae80bdef1db9cc218a36c4e0622bcabcb0ae6779334362a9e1bca51e5faff2b` |
| `scripts/harness/kpharness/creative_steps.py` | `b18c70538ef81fe29ce84209b715ee63c546339df59e62a80dd251781706deba` |
| `scripts/harness/kpharness/checkpoints.py` | `c844589b971a468fdb8ef2990b05347b9ca827ab247158bde0b17087abdeec25` |
| `scripts/harness/kpharness/client.py` | `4c9ca9d24ff2d44e85f844cbd5409838a55e2ac0eb230ee28e22e2444e120fb9` |
| `scripts/harness/kpharness/discover.py` | `0e554e0d325f1f97c9994b03ded0eaa4be44d9b9ac62e4d0463872ec5ca7f75f` |
| `scripts/harness/kpharness/targets.py` | `2cd427a49c9c0f34415b7443ff56f8c075cfa1d323db6701640285e7b54a54cd` |
| `scripts/harness/kpharness/resources.py` | `03bd74b28285c69528dde880119353c71383e713467abcfad017463458876963` |
| `scripts/harness/kpharness/oracle.py` | `f6eb286ab13ad88b4dfe052a2c6e7fc125988d9fda8470112a2a18c730e2fa07` |
| `scripts/harness/kpharness/waits.py` | `ac1141c71df4e2960e97a35beac274567d0ed87d93f8d770a4db5d8abfec6f9f` |
| `scripts/harness/kpharness/shots.py` | `b5e903ebab783b9d33bdc3cbee6d7df346c76edb6acc59405845227fe9073bf8` |
| `scripts/harness/kpharness/world.py` | `4d232f9b33dfba1172bc8e1aefdb49fa94c436e83a93f86f8d94d2144bc251e3` |
| `scripts/harness/kpharness/bwm.py` | `4d9e1226bdaafe3727d075ac0ecfb2173e0075a177c0928c6ae3e50e2a845f1e` |
| `docs/creative-runner.md` | `8db35422e6a78d3d67e874166287ac1e3d785ff070f92c08574937bff2364ec1` |
| `docs/lua-boundary-validation-plan.md` | `5c869644f60a3b5476a20b3a55d2737a8fa02c497122aa58d865400f38579ae5` |

The eventual manifest also needs the selected console route TOML and every Lua
file it stages, plus the newly produced runtime/proxy artifacts and exact K1
address profile.  Each must have a SHA-256 in `manifest.json`; paths and
historical labels alone are not sufficient.

## Adapter and recording facts

`LinuxWineCreativeSession` is safe **for the display it owns**, with important
limits.  It rejects `KP_HARNESS_REUSE_DISPLAY`, preflights `/tmp`, rejects an
already-used display, allocates Xvfb, takes the shared live-game lock, owns its
stage/prefix, and scopes game PID teardown to that stage plus Wine prefix.
It inherits `GameSession.capture_owned_game_window()`.  When an actual
physical-console action asks for input, that method requires the live session's
exact `DISPLAY`, a live Xvfb process, a live game/launcher PID, exactly one
visible PID-owned window, and verifies the same PID and positive geometry on
reuse.  This is a safe input target; it does **not** itself create a window or
invoke discovery before the console action.

The recorder is different.  `LinuxWineCreativeSession.start_xvfb()` immediately
calls `X11Recorder.start(display, screen, ...)`, before game launch.  The
current command is `ffmpeg -f x11grab ... -video_size <screen> -i :<display>.0`.
There is no `-window_id`, no call to `capture_owned_game_window()`, no recorded
window PID/geometry, and no resize/lost-window failure.  It captures the X11
root at the configured screen size, not the verified game window.  The Task 7
brief explicitly records that root capture of Gamescope is black; therefore
this recorder cannot support a truthful GPU/window-capture claim.

The inherited session environment also sets `LIBGL_ALWAYS_SOFTWARE=1` and
`GALLIUM_DRIVER=llvmpipe`.  No checked-in Gamescope/Xwayland GPU adapter exists
in this worktree.  The documentation accurately says the current implementation
is `linux-wine-k1` on its own Xvfb, but it must not be marketed as the required
GPU adapter.

## Package scope

A truthful private package today could contain the frozen **physical-console
control boundary** and label recording as an owned-Xvfb root capture with
unvalidated render cadence and mandatory visual review.  It could not claim:

* GPU acceleration, Gamescope/Xwayland operation, or non-black GPU capture;
* exact game-window video capture;
* a dedicated checked-in physical-console scenario (the repository's scenario
  tree has no `console_open` or `console_command` fixture; the private TOMLs
  are controller inputs and must be frozen separately if selected);
* a current DLL/proxy artifact matched to these uncommitted sources;
* Mac support, projectiles, playback, Mach-O work, or any other dirty path;
* visual/showcase acceptance merely because the route or media encoder passes.

Explicitly exclude `scripts/harness/kpharness/playback.py`, `src/api/projectiles*`,
`src/image/macho*`, their CMake hunks/tests, K2/Mac address and research paths,
and every unlisted dirty file.  The current whole `CMakeLists.txt` hash is
recorded above only to detect drift; it is not an admissible package file.

## One decisive live gate

Build a clean, hunk-materialized Task 7 snapshot, write a complete manifest,
and run one selected private console TOML under the newly implemented owned GPU
display adapter.  The gate passes only if one atomic receipt contains all of:

1. source-archive and every allowlisted-file hash, plus the built
   `kphasor.dll`, proxy, address-profile, route, staged Lua, and deployed-Lua
   hashes; before/after hashes prove source and snapshot immutability;
2. owned display and renderer evidence (Gamescope/Xwayland identity plus an
   accelerated renderer), followed by the actual owned game window ID, PID and
   geometry;
3. an ffmpeg command that targets that same window ID, starts only after it is
   mapped, and fails on resize/replacement/loss; its continuous MP4 hash and
   ffprobe metadata must be retained;
4. the pre-input and post-input `kp.console.v1` identity transcript, one
   physical F12/Enter sequence, exactly `submitted + 1`, exact successful
   outcome, and undropped request/session-filtered input and result lines; and
5. route predicates, source preservation, recorder-before-display cleanup, and
   required visual review recorded as independent statuses.

Anything less is a useful host or prototype result, not package proof.

## Evidence consulted

* `.superpowers/sdd/lua-boundary-validation-plan/task-7-brief.md`
  (`3090495196a1767c39aca94d0804673c972e091dee3d36334c3445a087670b17`)
* `.superpowers/sdd/lua-boundary-validation-plan/task-7-supported-console-report.md`
  (`9ec619ac272113896760d218e60d75c64880579b3304a0602659b240b53dac67`)
* Task-plan/review diff package, current worktree source, and existing private
  package-readiness/controller material.  No historical receipt was promoted
  to proof of the current bytes.

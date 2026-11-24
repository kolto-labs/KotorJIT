# Harness driver contract

The Python driver owns discovery, staging, process lifetime, channel requests,
and reports. It requires Python 3.11 or newer. `kpharness.sh list` and the offline
tests do not launch a game. `boot`, `run`, and Pioneer `step` are live operations.

## Configuration ownership

| File | Reader and owner | Scope |
| --- | --- | --- |
| `<game>/hyperstim.ini` | Native runtime | Runtime options, including the optional listener |
| `kotorphasor.toml` | `tools/kpdiscover.py:read_workspace_config`, shared by path discovery and Python harness | Optional operator paths for this workspace/machine |
| `scripts/harness/scenarios/**/*.toml` or an explicit route path | `Scenario.parse`, also used by Pioneer | Immutable execution policy, declared resources, ordered actions and predicates |

There is no merge between these scopes. Workspace paths cannot override route
execution settings. Route files cannot change listener or machine settings.
Supported build identities, executable names, addresses, and target capabilities
remain code/data facts in `targets.py` and the existing build/address tables;
they are not operator configuration. Generated API metadata and hook tables are
outside this harness contract.

## Runtime listener

```ini
# <game>/hyperstim.ini
harness_port = 27015
harness_bind = 127.0.0.1
```

Section headers are ignored. `port` and `bind` inside `[harness]` do not enable
anything. An absent/zero port disables the listener; only loopback is accepted.
`HYPERSTIM_HARNESS_PORT` takes precedence over the INI. The driver writes these
prefixed keys into the staged game's INI with its selected/free port; ordinary
driver users do not need to edit the source installation's INI.

## Optional workspace paths

```toml
[paths]
k1 = "../games/kotor"
k2 = "../games/kotor2/steamassets"
corpus = "../kotorxid/db/kotorxid.sqlite"

[harness]
build_dir = "build"
k2_exe = "../windows-kotor2/swkotor2.exe"
libglu_dir = "../runtime/lib/i386-linux-gnu"
```

One file is selected: search the current directory, then its ancestors, then
the checkout root. The first existing file wins in its entirety; missing tables
do not inherit from another file. There is no import-time snapshot: callers read
the current selected file. Relative paths are relative to that file, and `~`
expands to the user's home directory. Explicit command-line and environment paths
retain their existing current-directory interpretation. An invalid selected file,
non-table section, non-string path, or unknown `[harness]` key fails explicitly.

| Setting | Precedence, highest first |
| --- | --- |
| Game data directory | Explicit Python discovery argument; `KOTOR1_DIR`/`KOTOR2_DIR` (or generic app environment); `[paths].k1/k2`; content-based install discovery |
| Corpus | Explicit discovery argument; `KOTORXID_DB`; `[paths].corpus`; existing corpus discovery |
| Runtime build directory | `--build-dir`; `KP_BUILD_DIR`; `[harness].build_dir`; checkout `build/` |
| K2 Windows executable | Valid `KP_K2_EXE`; valid `[harness].k2_exe`; executable in discovered installation |
| K2 GLU candidates | Valid `KP_LIBGLU_DIR`; valid `[harness].libglu_dir`; discovered Steam/UMU runtime libraries |
| Staged tree | `--staged`; `KP_STAGED_DIR`; existing target/game staging fallback under checkout `tmp/` |
| Wine prefix | `--wineprefix`; `KP_WINEPREFIX`; existing dedicated prefix fallback under checkout `tmp/` |
| Listener and display | `--port`/`--display`; free values selected by the driver |

Game and corpus explicit paths are authoritative: invalid explicit paths fail
discovery. Environment/config installation candidates still have to pass the
existing content checks; an invalid candidate falls through. GLU discovery can
return multiple valid directories, ordered by the table above. Staging and Wine
prefix keys have no workspace TOML equivalents. These are the existing supported
knobs, not a mechanism for adding target capabilities.

## Driver lifecycle and results

`run NAME_OR_PATH` resolves the route (including `cursed/NAME`), parses and
validates its header and declarations before creating the session, stages its
typed resources, boots, executes steps, writes `report.json`, and tears down.
`--target` overrides the route's session target when explicitly supplied. The
route remains immutable and keeps its authored target; the generated report and
automatic checkpoint namespace record the effective session target.
The stage has writable saves/runtime data and links to installation assets;
scenario runs reset the staged saves from their source under the stage lock.
The driver never rewrites a route during replay. Resource bytes come from the
selected installation via `kq`, verified by size and SHA-256; matching staged
bytes can be reused. Failure to obtain or verify bytes aborts before launch.

`boot` leaves a session attached for `state`, `exec`, `events`, `shots`, `reply`,
and `down`. Pioneer `init` creates a route, `step` executes against an attached
session and records a pending result, and explicit `commit` appends it. Pioneer
uses the same validated header and step/resource normalization as replay,
allowing an empty route only during authoring. It does not restage resources into
an already running session; referenced bytes must already be staged and still
pass the runner's hash/readback check.

CLI exit statuses are 0 for success, 1 for execution/channel failure, 2 for boot
failure, and 3 for invalid input/configuration. A `report.json` is evidence of the
recorded predicates, not proof of unobserved gameplay. See [user harness guide](user/harness.md)
for live commands, watchdogs, and recording.

## Offline gate

### Concurrency policy

`scripts/harness/gameplay_tests/run_all.sh` runs independent host-only checks in
parallel by default (`KP_FAST_JOBS=3`). Set `KP_FAST_JOBS` to a smaller positive
integer on a constrained machine, or raise it when the checks are known to be
CPU- and I/O-safe. Each test keeps its own log and exit status, and the summary
is emitted in stable test-list order.

Live game checks, including the `--live-all` work-in-progress group, are never
parallelized by this setting. They remain behind the
single `tmp/harness-locks/live-game.lock` slot because staging, saves, Xvfb,
Wine, and the engine process are shared mutable state. Parallel live sessions
require separate staged trees, prefixes, displays, and an explicit orchestration
layer; the default driver refuses to infer that isolation.

```sh
cmake -S . -B build
cmake --build build -j3
ctest --test-dir build --output-on-failure
```

CTest includes `kpharness_offline_test` (fake server, temporary synthetic staging,
workspace/parser/resource/Pioneer checks, all recursively discovered routes) and
`kpharness_world_test`. The existing CI CTest step runs both. No Wine, display,
game installation, recovery session, or additional Python framework is needed.
Live testing remains a separate explicitly authorized gate.

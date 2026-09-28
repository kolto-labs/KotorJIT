# Pioneer authoring transactions

Pioneer executes proposed steps through the same `ScenarioRunner.run_step`
used by route replay. It supports `init`, `step`, `commit`, `discard` and
`status`, plus an attached playback owner with `attach`, `play`,
`fastforward` and `stop` (below). It does **not** implement world pause,
checkpoint rewind or full game-state rollback yet.

An attached `step` applies the route's execution speed before dispatch,
including setting 1× when the attached game was previously accelerated.
The route's normal default remains 16×. On completion or failure it restores
the captured multiplier if that temporary setting is still current and the
same attached runtime remains present. A successful explicit `do="speed"`
step retains its requested setting, including when it equals the route
setting. A Lua step or another owner that changes the multiplier to a
different value also retains that value. This is a scoped compare-and-restore
policy, not a native ownership-token service; independently writing the same
value cannot be distinguished. Attached calls require speed read/write
capability, even for 1×. Full managed runs retain their existing fresh-process
1× opt-out.

Before touching the game, `step` validates the exact rendered append and
writes an `issued` receipt beside the route. It includes the original route
hash, normalized settings hash, step hash, expected index and attached session
identity: session paths/start/port/launcher metadata plus runtime PID/build
and uptime. A completed result receives its own digest. Another step cannot
overwrite unresolved work. If a request times out, policy restoration fails,
or route/session identity changes, the receipt remains `issued` and cannot
be committed—even with `--force`. Inspect the live state; do not blindly
repeat the mutation.

`commit` reconnects to the recorded target and checks the current session and
route against that receipt. Old receipts without provenance, changed route
bytes/settings, foreign runtimes, malformed results and unfinished executions
are rejected. `--force` allows an explicitly recorded failed result; it does
not waive provenance checks. An expected failure is an accepted test result,
not a gameplay success claim.

The append preserves existing TOML bytes, comments and line endings. It
writes a `committing` journal before atomically replacing the route, then
records `committed`. Retrying after a crash between those writes recognizes
the exact candidate hash and does not append twice. The committed receipt
remains until a new step or explicit discard; it is the retry receipt, not
another uncommitted edit. Pending and route files use same-directory temporary
files, fsync and atomic replacement. A per-route advisory lock serializes
Pioneer commands using flock on Linux/macOS and msvcrt byte-range locks on
Windows. Windows uses file fsync and atomic replacement without claiming
directory-fsync durability. Noncooperating external editors must not edit while a
command runs. Hash checks reject detected external changes but do not provide
a filesystem compare-and-swap against arbitrary concurrent editors.

`discard` deletes pending **metadata only**. It does not undo Lua execution,
movement, inventory changes, effects, timers, dialog choices or any other
live side effect. It is not rewind. Native checkpoint restoration and
pending-edit rollback require the forthcoming shared playback service.

These receipts describe the current authoring session, not cryptographic
attestation or a complete engine state snapshot. PID/build/start/uptime
checks detect ordinary replacement/restart; they do not supply a native load
epoch or prove that a world has not changed inside the same process. Native
save/load, per-checkpoint mod state and branch-aware execution cursors remain
required for RenPy-like game-state control.

## Playback owner

```sh
kpharness pioneer attach      --out R.toml
kpharness pioneer play        --out R.toml --verify-current 'return true' --until 3
kpharness pioneer fastforward --out R.toml --speed 8
kpharness pioneer status      --out R.toml
kpharness pioneer stop        --out R.toml
kpharness pioneer reclaim     --out R.toml
```

`attach` starts one owner process for the route. `play` and `fastforward`
start it when needed. The owner opens the only engine connection and keeps
it. `status`, `stop` and new jobs reach it over an authenticated loopback
control socket. The socket address and token sit in `R.toml.playback.json`
(mode 600). The owner's cursor journal is `R.toml.playback-state.json`.

The owner holds two locks for its whole life:

- The route lock, so Pioneer `step`, `commit` and `discard` for that route
  go to the owner. It runs them over its own connection.
- A per-engine lock at `$XDG_STATE_HOME/kpharness/playback-locks/localhost-PORT.lock`,
  or `~/.local/state/...` when that is unset (`%LOCALAPPDATA%` on Windows).
  The directory must be owner-only (0700). A second owner, or a plain
  Pioneer `step` or `commit` on another route, is refused before it
  connects to the same engine. `status` skips its live read instead.
  `kpharness exec`, `reply`, `state`, `events` and `shots` take the same
  lock, so they are refused while an owner is attached.

`status` and `stop` do not check the route bytes. Editing the route while
an owner is attached does not lock you out. The owner refuses new jobs for
changed bytes, and a running job stops with the world uncertain.
The control server runs at most 16 connections at a time, each on its own
thread. A connection must send its whole request line within 1 second, or
the server drops it. When all 16 are busy, the server drops the oldest
connection that has not sent a full line and serves the new one. A pile of
idle sockets cannot block `status` or `stop`. Clients wait 5 seconds.

A first `play` needs a starting point. That is either an initial
`load_save`/`load_checkpoint` step with `--restart`, or a
`--verify-current` Lua predicate that must return `true`. After that each
job continues from the completed boundary. Arguments are checked before
anything is sent to the engine. A request that fails those checks, or an
execution precondition such as a missing start point, leaves the world
state unchanged and the owner idle. Jobs are never retried. A client that
times out while waiting only stops polling; it does not resend the job.

A step that fails, or a cancelled step that could have changed the game,
marks the world uncertain. Stop the owner and restart from a native initial
load. A `stop` during a wait, event expectation or `sleep` step is a clean
stop: that step issued nothing, and the boundary stays where it was.

`stop` stops execution and detaches the owner. It does **not** pause the
game world. The game keeps running, and `world_paused` stays `false`.
Native world pause is a later stage. SIGTERM, SIGHUP and SIGINT sent to
the owner act like `stop`. The journal records the cause in `stop_reason`.

A cancelled wait is treated as read-only. A wait can still answer a
declared `authored_barks` entry or take a screenshot while it polls, and a
cancel after such a bark reply is still reported as a clean stop. Routes
with `authored_barks` should not rely on a clean stop during a wait.

The owner also stops if it cannot write its journal. It removes its
descriptor, logs the error and exits non-zero. It never keeps serving a
state that is not on disk. Cleanup runs each step on its own, so one
failure does not keep the owner alive.

### Speed

The speed is the engine's **configured multiplier** (`kp.game_speed()`),
not a measured simulation rate. `play` uses the route's `game_speed`.
`fastforward --speed X` accepts a finite X in (0,16]; the default is 4.
After setting the speed, the owner reads it back. `effective_speed` is
published only from that readback. If the readback does not match, the job
issues no step and reports `observed_speed` with the world uncertain.

Before its first speed write, each job records the prior multiplier in
the journal (`speed_before_job`, `speed_restore_owed: true`). At job end
the owner restores it. That holds when the job completes, fails, reads
back a different speed, is stopped, or stops because the route changed.
It holds for authoring steps sent through the owner too. The owner holds
the engine lock, so no one else can have changed the speed. The one gate
is that the engine is still the same game process. Route bytes and
pending receipts do not matter. A route `do = "speed"` step keeps its own
setting. `speed_after_job` is the readback after the restore or retain.
If the restore readback does not match, `speed_restore_error` says so and
the world is marked uncertain.

### Recovery after a killed owner

SIGKILL, a crash or power loss skip the owner's cleanup. The descriptor
stays, `status` and `stop` report that the owner is not reachable, and the
engine may be left at the job's speed. Run:

```sh
kpharness pioneer reclaim --out R.toml
```

`reclaim` first takes the engine lock and the route lock. The owner held
both for its whole life, so getting both proves it is dead. No PID is
trusted. If either lock is held, `reclaim` refuses; use `stop`. Then it:

- removes the descriptor,
- restores `speed_before_job` if a restore is still owed and the engine is
  the same game process the owner recorded, and checks it by readback,
- otherwise only reports the recorded prior speed (`speed_restored: false`
  with a `note`),
- marks the world uncertain if the owner died during a job.

A later `play` then needs `--restart` from a native initial load.

The descriptor also records `owner_pid`. It is for sending SIGTERM by hand
when the descriptor mode was changed and the client refuses to use it.
It is never used to decide ownership.

`attach` gives a new owner `KP_PLAYBACK_START_TIMEOUT` seconds (default 30)
to publish its descriptor. A short launcher process starts the owner and
exits, so the caller never keeps the owner as an unreaped child.

After a step goes through the owner, `play` waits until it is committed or
discarded. Committing a successful step made at the end of the route moves
the boundary onto it. Discarding one marks the world uncertain, because its
live effects were not undone.

Host regression checks (no game):

```sh
PYTHONPATH=scripts/harness python3 tools/kpharness_playback_test.py
python3 tools/kpharness_pioneer_policy_test.py
python3 tools/kpharness_offline_test.py TestPioneer TestScenario
```

`kpharness_playback_test.py` runs a synthetic engine and a real owner as
subprocesses. Its round 2 tests assert the engine's speed after each exit
path: readback mismatch, route edit, SIGTERM, SIGHUP, SIGKILL plus
`reclaim`, an unwritable journal and a tampered descriptor. It does not
prove behavior against a live game. Live proof
is still pending: attached K1 `play --until 3`, `status`, `stop`, speed
readback restored, game PID alive, state `execution_stopped`.

Add native pause ownership and verified asynchronous checkpoints before
advertising world pause or rewind. Preserve route branches after
restored-state edits; moving an editor cursor or deleting a receipt cannot
stand in for game-state restoration.

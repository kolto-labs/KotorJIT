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
Native world pause is a later stage.

### Speed

The speed is the engine's **configured multiplier** (`kp.game_speed()`),
not a measured simulation rate. `play` uses the route's `game_speed`.
`fastforward --speed X` accepts a finite X in (0,16]; the default is 4.
After setting the speed, the owner reads it back. `effective_speed` is
published only from that readback. If the readback does not match, the job
issues no step and reports `observed_speed` with the world uncertain.

The previous multiplier is restored when a job finishes, fails or is
stopped. This uses the compare-and-restore policy above. A route
`do = "speed"` step keeps its own setting. `speed_after_job` is the
readback after that restore or retain.

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
subprocesses. It does not prove behavior against a live game. Live proof
is still pending: attached K1 `play --until 3`, `status`, `stop`, speed
readback restored, game PID alive, state `execution_stopped`.

Add native pause ownership and verified asynchronous checkpoints before
advertising world pause or rewind. Preserve route branches after
restored-state edits; moving an editor cursor or deleting a receipt cannot
stand in for game-state restoration.

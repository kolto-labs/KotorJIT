# Pioneer authoring transactions

Pioneer executes proposed steps through the same `ScenarioRunner.run_step`
used by route replay. This foundation supports `init`, `step`, `commit`,
`discard` and `status`; it does **not** implement play/pause, fast-forward,
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

Host regression checks (no game):

```sh
python3 tools/kpharness_pioneer_policy_test.py
python3 tools/kpharness_offline_test.py TestPioneer TestScenario
```

The next slice should provide one persistent attached owner for
`play`/`stop`/`fastforward`, scheduling this same runner and maintaining one
channel, execution cursor and cancellation state. Add native pause ownership
and verified asynchronous checkpoints before advertising world pause or
rewind. Preserve route branches after restored-state edits; moving an editor
cursor or deleting a receipt cannot stand in for game-state restoration.

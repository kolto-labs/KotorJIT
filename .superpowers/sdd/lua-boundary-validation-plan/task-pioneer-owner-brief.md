# Pioneer attached playback owner: implementation slice

Prerequisite: foundation independently reviewed. This slice must implement actual play/fastforward/stop scheduling through the common runner, not just command placeholders. Native world pause and checkpoint rewind remain next gated work under pioneer-controls-brief.md.

## Ownership and scope

One implementer owns new scripts/harness/kpharness/playback.py (or a small playback package), focused pioneer.py / cli.py integration, narrowly required cooperative runner/wait hooks, meaningful tests and separate harness documentation. Preserve all other edits. No native code, CMake, live games, index or commits. Freeze code and return report/test evidence for independent review.

## Required behavior

A persistent attached-session owner holds the single engine Channel and serialized runner. CLI processes use its authenticated loopback control endpoint; never open a second competing game Channel. Keep the endpoint/session token in an owner-only sidecar, never logs or status output. Bind descriptor to route revision and attached runtime identity; reject stale/foreign descriptors or session changes. Do not infer ownership from PID alone. Prevent two owners for the same attached engine, including different routes. Use tested cross-platform locking from the foundation where appropriate.

Expose pioneer play --out R [--until N], fastforward --out R [--until N] [--speed S], stop --out R, and status. Normal play uses authored execution policy; bounded fastforward changes the speed for this operation and restores prior speed on finish/stop/failure. State speed ownership precisely when a route explicitly changes speed. Execute each committed step via ScenarioRunner.run_step, preserving all gates and reports; never append source while replaying. Reject unresolved pending edits or unverified cursor/session state rather than replaying blindly.

Define initial attachment explicitly: beginning a route requires a known initial-state step, or an explicit verified current-state boundary. Do not silently run from the middle of a route against an arbitrary world. Record before-dispatch intent, then observed completion. A timed-out mutation is uncertain, not automatically retryable; preserve it in status and require verified restoration before resuming.

Long operations return job IDs and expose --wait for terminal outcome. The control endpoint remains responsive during engine waits. Stop cancels scheduling promptly and cooperatively stops active waits at a safe boundary, restores owned execution policy, retains final evidence and detaches without game teardown. A native save/load already issued reports stop-pending until its terminal/uncertain state can be classified; no unsafe reentrant calls. Preserve completed cursor and operation errors honestly.

Status separates authored step count, verified completed boundary, active step, operation state, effective/requested speed, runtime identity, dirty/uncertain world state and last error. Play/stop lifecycle must be useful for live debugging and tests before the larger editor exists. Use the same service methods for direct test clients and CLI commands.

Do not label scheduler suspension as native game pause. Do not add fake rewind that only changes a cursor. Native pause research is /home/brunner56/kp-live-20260922/pioneer-native-pause-contract.md. Actual controls follow after this service is reviewed.

## Verification

Use real subprocess/socket/file tests with a synthetic engine endpoint plus common-runner spies only where necessary. Verify one engine connection, action ordering, every assertion executed, status during active wait, stop during wait, speed restoration on failure, stale descriptor rejection, different-route owner conflict, invalid arguments before mutation, interrupted operation uncertainty, and no automatic retry of a mutating command. Exercise the actual CLI entry path. Keep tests resource bounded and deterministic. Native gameplay and native pause are separate controller acceptance gates.

Report .superpowers/sdd/lua-boundary-validation-plan/task-pioneer-owner-report.md with changed paths, command lines/results, unresolved concerns and exact next native-control dependency. No broad unrelated cleanup.

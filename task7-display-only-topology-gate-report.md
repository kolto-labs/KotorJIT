# Task 7 reviewed topology/socket display-only gate

**PASS for the bounded display-only acceptance predicate.** Exactly one Gamescope launch ran from 2026-09-27 10:08:50 to 10:09:02 UTC. It established the dedicated subreaper/controller, admitted the orphan-adopted Xwayland endpoint through both local transports, verified 1024×768 geometry and accelerated hardware rendering, and completed cleanup with all recorded owned processes and the newly allocated display endpoint absent. No Wine, game, FFmpeg, creative game driver, or visual-acceptance command was launched. Product source was not edited.

This is installed display/topology/renderer/teardown proof. It does not establish K1 behavior, a game window, console input, recording, media quality, or final Task 7 acceptance.

## Exact run and provenance

- Run: `/home/brunner56/kp-live-20260922/display-only-runs/20260927-100845-8cd691c3`
- Snapshot: `/home/brunner56/kp-live-20260922/harness-snapshots/task7-display-only-topology-20260927-100845-8cd691c3`
- Snapshot manifest SHA-256: `b0b45c34b1369a72507832196e2974952c5e76c82891766ec9e84ecacd2a3ba3`
- Source: `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/scripts/harness`
- Private driver: `display_gate.py` in the run. `invocation.json` binds its SHA-256, exact command, and inherited lock descriptor. `artifact-hashes.json` hashes retained run files.

The fresh manifest contains 27 Python modules, explicitly including `kpharness/gamescope_socket.py`. Snapshot creation and the production verifier established source equality before launch. Files were made read-only (0444; directories 0555), and every snapshot file hash and repository input was reverified after exit against current source. No bytecode was introduced. This sealing is filesystem read-only plus hash verification, not protection against an owner deliberately changing permissions.

The private child and actual readiness child used absolute `/usr/bin/python3.14 -I -S -B`. The child inserted only the snapshot runtime into its isolated Python import path. It loaded repository context from the verified manifest and checked that the manifest root matched the selected worktree. The canonical live-game flock was held by the supervisor and passed with `pass_fds=(lock.fileno(),)` to the controller. The production `canonical_lock_guard()` confirmed FD 3, exclusive flock, device 2065, inode 40769209, and the canonical repository lock path in both the controller and socket-cleanup receipts.

Before execution, the gate read the current implementer topology/socket report, the independent `task7-topology-socket-review.md` including its final scoped PASS, the authority audit, and prior topology/stale-socket evidence. The writer's host tests were not rerun or promoted into this run's live proof.

## Historical X1 quarantine and preserved preflight refusal

The first prepared directory, `/home/brunner56/kp-live-20260922/display-only-runs/20260927-100344-e6c09841`, refused before any rename or launch. Its driver compared the audit's device value `34` as decimal, while Python reported decimal 52. The audit value was hexadecimal: `0x34 == 52`. Every other historical identity field matched. That refused preflight, its zero-launch receipt, and its unused snapshot are retained unchanged.

The fresh successful directory changed only that radix interpretation in the copied driver. The controlling task explicitly authorized treating the historical X1 socket and `.X1-lock` as failed-run artifacts and moving them to recoverable quarantine. Under the canonical flock, the driver rechecked the audited socket's device/inode/type/mode/UID/GID/nanosecond timestamps, exact lock bytes containing PID 816616, no named pathname/abstract endpoint rows, absence of all recorded old PIDs, and absence of conflicting Gamescope/game/Wine/FFmpeg processes. Each original entry was atomically renamed within its own parent directory, and that directory was fsynced. Neither historical entry was unlinked or restored.

| Historical artifact | Quarantine path | Preserved identity |
| --- | --- | --- |
| `/tmp/.X11-unix/X1` | `/tmp/.X11-unix/.task7-quarantine-20260927-100845-8cd691c3-X1` | device 52, inode 1231594, socket, UID/GID 1000, mode 0755 |
| `/tmp/.X1-lock` | `/tmp/.task7-quarantine-20260927-100845-8cd691c3-X1-lock` | device 52, inode 1231593, regular file, UID/GID 1000, mode 0444 |

`historical-x1-quarantine.json` retains the old/new paths, all pre/post stat fields, exact lock bytes in hexadecimal, lock PID, lock digest, final checks and rename time. Rename changed ctime as expected; inode, mode, ownership, size, and mtime remained identical. The quarantined artifacts' complete post-rename identities stayed unchanged through the gate. The lock SHA-256 is `7d74ab6254d1ef400efe783cc2619e516ecdc1c67b43a3403946686acd54ef92`. No abstract-X1 reservation was used.

## Installed topology and endpoint evidence

| Role | PID / start | Verified relationship |
| --- | --- | --- |
| Dedicated controller | 1142286 / 59783384 | subreaper true; dedicated single launch; network namespace device 5/inode 4026531833 |
| Gamescope leader | 1142304 / 59783448 | direct child of controller; PGID/SID 1142304 |
| Ready child | 1142374 / 59783562 | verified Gamescope descendant |
| Xwayland | 1142335 / 59783517 | PPID 1142286, PGID/SID 1142304: adopted by the recorded controller |

Xwayland was `/usr/bin/Xwayland`, selected display `:1`, and retained argv including `-rootless`, `-terminate`, two `-listenfd` values and `-displayfd`. Its two-link adopted chain reached the recorded controller and matched the launch group/session. Candidate relation, command, executable, process state, socket FDs, socket-table rows, namespace identities, and ancestry are retained in the lease/access receipt.

The pathname listener inode was 567350540 and the abstract listener inode was 567350539. Both were held by Xwayland. Independent credential-free X11 setup checks succeeded through the pathname and abstract transports. Both SO_PEERCRED results identified UID 1000 and the owned Gamescope leader PID/start, consistent with the inherited listener descriptors. No TCP listener was admitted. Controller and Xwayland network-namespace device/inode identities matched and were rechecked.

The exact access model is `owned-endpoint-host-local-no-cookie`; `xauthority_present=false` and `xauthority_mode=no-cookie-sentinel`. This proves the owned local endpoint and successful credential-free access, not exclusive access against other local users.

The captured fresh pathname node `/tmp/.X11-unix/X1` had device 52, inode 1300302, socket type, UID/GID 1000, mode 0755, and mtime/ctime 1790503733951171430 ns. Its root-owned parent was device 52/inode 3/mode 01777. These values differ from the quarantined historical socket and are bound to the admitted live listener evidence.

## Geometry and renderer

The lease completed startup and remained alive before close. The retained independent geometry command returned exit 0 and exactly `1024 768`. Production `glxinfo -B` verification passed, with `direct=true`, `accelerated=true`, and renderer:

`AMD Radeon RX 460 Graphics (radeonsi, polaris11, ACO, DRM 3.64, 7.1.9-200.fc44.x86_64)`

The complete renderer output is retained in `renderer.txt`; the lease's parser accepted hardware rendering. No game was used to produce this evidence.

## Teardown and preservation

The private driver called `close()` once in `finally` after successful startup. One cleanup attempt passed. Boot, evidence, and cleanup errors are separately retained as null. Gamescope exited normally with return code 0. All four recorded lease members (1142374, 1142335, 1142304, 1142369) and the dedicated controller 1142286 were absent after the child exited. No Gamescope, Wine, game, wineserver, or FFmpeg process remained.

The socket-cleanup receipt reports **`status=already_absent`**: Gamescope had removed the fresh pathname before the helper's final cleanup check. Both pathname and abstract endpoint rows were absent, the candidate pathname was absent, and `/tmp/.X1-lock` was also absent. The helper retained the admitted node, namespace, canonical lock, repeated endpoint-absence checks and protected sibling evidence. **The helper's explicit `os.unlink` fallback branch was not exercised by this live run.** Its host tests remain the separate evidence for that branch.

The protected X0, X94 and X100 socket identities and complete named socket-table rows were identical before and after. The original Xwayland `:0` PID 7277 remained. Historical quarantines remained unchanged. The snapshot remained hash-identical and source-equal. The canonical flock was released and independently reacquired nonblocking to prove it was free.

Endpoint absence is scoped to the admitted controller network namespace. This run does not claim absence in unrelated namespaces. The implementation's receipt also preserves the final-stat/unlink race limitation; no atomic inode-conditioned unlink guarantee is claimed.

## Acceptance predicate and receipts

All 17 recorded checks passed: one launch, successful isolated driver, exact geometry, live admitted lease, both-transport local access, verified subreaper, inherited canonical lock, pathname-cleanup absence, protected displays, unchanged historical quarantines, one successful cleanup attempt, unchanged source-equal snapshot, absent owned PIDs, absent candidate display, no game/Wine/FFmpeg, free final lock, and no gate errors.

Primary evidence is in `gate-result.json`, `driver-result.json`, `lease-before-close.json`, `gamescope-lease.json`, `gamescope.log`, `renderer.txt`, `preflight.json`, `invocation.json`, `snapshot-before.json`, `snapshot-after.json`, `protected-sockets-original.json`, `protected-sockets-before.json`, `protected-sockets-after.json`, `historical-x1-quarantine.json`, and `prelaunch-radix-correction.json` in the successful run. The prior zero-launch refusal remains separately retained. No second Gamescope launch was performed after the reviewed topology/socket fix.

# Task 7 display-only topology gate: independent review

Review date: 2026-09-27 (America/Chicago)

## Verdict

**PASS for the bounded display-only gate. A single fresh, serialized K1 run is authorized, subject to the run's normal same-window preflight and continued exclusive ownership of the canonical `live-game.lock`.**

The successful run is `/home/brunner56/kp-live-20260922/display-only-runs/20260927-100845-8cd691c3`. I independently reviewed its retained receipts, current snapshot bytes and modes, current selected-source bytes, run-artifact hashes, protected-display receipts, quarantine artifacts, and the writer report at `/home/brunner56/kp-live-20260922/task7-display-only-topology-gate-report.md`. I did not launch a display, Gamescope, Wine, a game, or FFmpeg; did not signal a process; and did not alter the quarantine or product files.

This PASS authorizes one next serialized K1 attempt. It is not K1 runtime acceptance, game-window proof, input proof, console proof, recording proof, media proof, or final Task 7 acceptance.

## Findings by severity

### Critical

None.

### Important

None.

### Minor

1. The writer report says Gamescope removed the fresh X1 pathname before helper cleanup. The receipt proves only that `/tmp/.X11-unix/X1` was already absent when `cleanup_socket_node()` performed its checks. It does not identify the exact remover. This is a wording-level attribution issue and does not weaken the absence or cleanup result. The report correctly and prominently states that the helper's explicit `os.unlink` fallback branch was not exercised.

## Independently reproduced evidence

### Snapshot identity and source equality

For the successful run, I recomputed every hash in `snapshot-before.json` against the retained snapshot and recomputed all 27 manifest module hashes and every repository-input hash against the selected source. There were no mismatches. The manifest hash, its sidecar, and the receipt all equal:

`b0b45c34b1369a72507832196e2974952c5e76c82891766ec9e84ecacd2a3ba3`

The 29 retained snapshot-file hashes are identical before and after execution. No retained file or directory in the snapshot has an owner/group/other write bit. This independently confirms the run's exact snapshot identity, post-run byte stability, and present source equality. As the writer report says, mode sealing is not protection against the owner deliberately changing permissions.

I separately rechecked the preserved zero-launch refusal snapshot. Its manifest hash remains `5510726388bcd425ee2bcccb9fec221d5ab80cabd8e6639f445165f36ee422e9`; its current snapshot, manifest modules, repository inputs, and selected source all match the receipt, and it has no writable snapshot entries. That refusal has no `snapshot-after.json`, because control stopped before launch and the post-launch verification path; current independent hashing supplies the present-state comparison without rewriting the original receipt.

The successful private-driver digest is `52011111643384a82bab95ab679f10388505ee7d4cb36ef13a2feee3416bec24`, matching `invocation.json` and `artifact-hashes.json`. I also recomputed every one of the 18 hashes in `artifact-hashes.json`; all matched, and every other regular run file was covered except the hash receipt itself.

### Preserved refusal and exact correction

The preserved run `/home/brunner56/kp-live-20260922/display-only-runs/20260927-100344-e6c09841` acquired the canonical lock, created and sealed its snapshot, then refused before quarantine and before launch with `historical X1 identity no longer matches audited failed run`. Its `gate-result.json` records `launches=0`, `verdict=FAIL`, and `lock_free_after=true`. It contains no quarantine receipt, driver result, or driver log, consistent with stopping before those actions.

The refused driver's SHA-256 is `e6b57a2fdc83402e69aec4ecac90f3b219673bd9a8c634abb0d702080fca8629`, exactly matching its invocation receipt. A direct diff of the refused and successful copied drivers shows one code change: the expected device value changed from decimal `34` to hexadecimal `0x34`. Python's observed decimal device value is 52, and `0x34 == 52`. `prelaunch-radix-correction.json` records this correction, the zero prior launches, and `other_relaxations=false`.

### Canonical lock and launch count

The successful supervisor acquired `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/tmp/harness-locks/live-game.lock` and passed FD 3 into the isolated child. The child's production guard recorded an exclusive lock on device 2065/inode 40769209 at that canonical path; the cleanup receipt records the same lock identity. A current read-only stat still gives device 2065/inode 40769209 for that path. After the child completed, the supervisor successfully reacquired the lock nonblocking and recorded `lock_free_after=true`.

The successful gate records exactly one launch and one successful driver invocation. The earlier refusal records zero launches. Thus the two reviewed prepared directories together contain one Gamescope launch, with no launch retry hidden in the refused run.

### Historical X1 quarantine

The quarantine basis is sufficiently bounded and receipt-backed. The earlier stale-X1 audit classified the old X1 as a run-correlated stale pathname rather than a proved creator identity; the writer report does not upgrade it to byte-level creator proof. Before rename, the fresh driver required and recorded:

- the exact audited socket device/inode/type/mode/UID/GID and nanosecond mtime/ctime;
- exact `.X1-lock` bytes `2020202038313636313600`, naming old Gamescope PID 816616;
- no pathname or abstract X1 socket-table row;
- absence of all six recorded old owned PIDs;
- absence of a conflicting Gamescope, game, Wine, wineserver, or FFmpeg process; and
- exclusive ownership of the canonical live-game lock.

The old socket was renamed to `/tmp/.X11-unix/.task7-quarantine-20260927-100845-8cd691c3-X1`; it remains device 52/inode 1231594, UID/GID 1000, mode 0755, size 0, with the audited mtime. The old lock was renamed to `/tmp/.task7-quarantine-20260927-100845-8cd691c3-X1-lock`; it remains device 52/inode 1231593, UID/GID 1000, mode 0444, size 11, with SHA-256 `7d74ab6254d1ef400efe783cc2619e516ecdc1c67b43a3403946686acd54ef92`. Rename changed ctime, as expected. The post-run receipt and my current read-only stat/hash checks agree with the retained post-rename identities. Neither quarantine artifact was deleted.

### Subreaper and orphan topology

The live receipt establishes a fresh dedicated controller PID/start `1142286/59783384`, initially single-threaded with no children and then verified as a Linux child subreaper. Gamescope PID/start `1142304/59783448` was its direct child and session/group leader with PGID/SID 1142304. The ready child was `1142374/59783562` through gamescopereaper `1142369/59783555`.

The admitted Xwayland was `/usr/bin/Xwayland` PID/start `1142335/59783517`, PPID 1142286 after orphan adoption, while retaining PGID/SID 1142304. Its recorded chain reaches the exact subreaper identity, and each non-controller member in the adopted chain remained in the launch group/session. The retained live topology contains the Gamescope leader, adopted Xwayland, gamescopereaper, and readiness child with exact PID/start/group/session values. This addresses the earlier ancestry failure rather than assuming that an orphan's current parent must still be Gamescope.

### Socket ownership and access

The admitted display was `:1`. The candidate evidence binds `/usr/bin/Xwayland`, its exact PID/start, safe argv, process relationship, network namespace, socket FDs, and socket-table rows. Xwayland held the pathname listener inode 567350540 and abstract listener inode 567350539 through FDs 42 and 41. The live pathname node was a different inode from the quarantine: device 52/inode 1300302, socket type, UID/GID 1000, mode 0755, under the recorded root-owned mode-01777 parent.

Credential-free X11 setup completed over both pathname and abstract transports. Both peer checks returned UID 1000 and the exact Gamescope leader PID/start, consistent with inherited listener descriptors. The candidate, controller, and peer ancestry checks were retained; controller and Xwayland network namespace identities both equal device 5/inode 4026531833. No TCP listener was admitted. The correct claim is `owned-endpoint-host-local-no-cookie`; the receipts do not claim exclusivity against other local users.

### Geometry and renderer

The lease reached ready state and remained alive before close. `xdotool getdisplaygeometry` returned status 0 and exact output `1024 768`. The retained `renderer.txt` independently reports `direct rendering: Yes`, `Accelerated: yes`, and:

`AMD Radeon RX 460 Graphics (radeonsi, polaris11, ACO, DRM 3.64, 7.1.9-200.fc44.x86_64)`

Gamescope's log independently identifies the RADV POLARIS11 physical device. Its normal headless startup warning that X0 was already in use is followed by Xwayland selection of `:1`; it does not contradict the successful private-display evidence.

### Cleanup and protected displays

There was one cleanup attempt and it passed. The lease closed, the Gamescope leader returned 0, and the postcheck found no survivor among the four recorded lease members or the dedicated controller. The final selected-process inventory contains only the pre-existing host Xwayland PID 7277 on `:0`; no Gamescope, game, Wine, wineserver, or FFmpeg process remained. The candidate `:1` pathname, pathname/abstract socket rows, and owned Xwayland were absent.

The cleanup receipt records `status=already_absent`, empty endpoint rows, and no observed candidate node. In the production cleanup code, `os.unlink()` executes only when the final verified node value is non-null and produces `status=removed`. Therefore the custom unlink branch was not exercised in this run. The live result proves the already-absent path, while branch behavior remains supported only by the separately attributed host tests mentioned by the writer.

I compared the complete captured identities and named socket-table rows for X0, X94, and X100. Each is byte-for-byte equal in `protected-sockets-original.json`, `protected-sockets-before.json`, and `protected-sockets-after.json`. The cleanup receipt's sibling identities and listener rows are also equal before and after. The quarantined historical X1 is deliberately the one exception between `original` and `before`; fresh X1 is absent after cleanup. `/tmp/.X1-lock` is absent after the successful run.

The endpoint-absence proof is correctly limited to the admitted controller network namespace. The cleanup receipt also retains the unavoidable limitation that `unlinkat` cannot atomically reject an uncooperative replacement after the final stat. Since this run took the already-absent branch, that unlink race was not exercised.

## Authorization boundary

The display gate removed the earlier topology/socket blocker and passed all 17 recorded predicates. It is sufficient to authorize exactly one fresh K1 run in the serialized live harness. That run must acquire the same canonical lock, repeat the normal process/storage/protected-display preflight, use a fresh source-equal snapshot, and stop fail-closed if current state differs. The authorization does not permit parallel live sessions or treating this display-only proof as K1 acceptance.

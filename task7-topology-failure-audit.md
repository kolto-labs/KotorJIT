# Display-only topology failure audit

Audited 2026-09-27, read-only except this report. No display, game, Wine, capture, or test process was launched; no signals were sent. The examined run is `/home/brunner56/kp-live-20260922/display-only-runs/20260927-092903-52fe911a`; the examined source is `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/scripts/harness/kpharness`.

## Finding

The readiness child passed its identity and full ancestry checks. The failure occurred later, in `verify_private_xwayland()` at `gamescope_processes.py:104`, while checking the ancestry of a process whose executable basename was `Xwayland` and whose file descriptors held both listening sockets for `:1`. The traceback ends at `verify_ancestry():31`: a traversed process had a PGID or SID different from 816616. It does **not** identify whether that process was Xwayland itself or an ancestor.

The likely explanation is wlroots' double-forked Xwayland being adopted by an external subreaper, while retaining Gamescope's group/session. The ancestry walk would reach the adopter and reject its different group/session. This is stronger than an unsupported claim that Xwayland called `setsid()`: the pinned upstream launch implementation double-forks without `setsid()`. The historical candidate PID, PPID, executable, command line, and rejected relation were never retained, so this explanation remains an inference.

There is no defensible way to supply exact commands and relationships for all six recorded PIDs from these artifacts. Reporting all six as proven descendants would overstate the evidence. The cleanup implementation adds all matching group/session processes to `_known_members` when **any** ownership anchor survives, including candidates whose ancestry check failed.

## Recorded identities and commands

| PID | Recorded start token | Recorded parent | Recorded PGID / SID | Command / role evidence |
| --- | --- | --- | --- | --- |
| 816616 | `59550695` | 816495, parent start `59550643` | 816616 / 816616 | Gamescope leader; exact launch argv retained in `gamescope-lease.json` |
| 816722 | `59550819` | Not retained | Matching 816616 / 816616 is implied by the cleanup collection code, not directly serialized | Command unavailable; plausible original Xwayland, unproven |
| 816778 | `59550869` | 816616 | 816616 / 816616 | Exact command unavailable; likely gamescopereaper intermediary |
| 816785 | `59550878` | 816778 | 816616 / 816616 | Readiness publisher; exact intended Python argv is in the Gamescope launch command; `/proc` argv was not retained |
| 816853 | `59550962` | Not retained | Matching 816616 / 816616 implied by cleanup code | Command unavailable; plausible Xwayland restart fork/helper, unproven |
| 816854 | `59550962` | Not retained | Matching 816616 / 816616 implied by cleanup code | Command unavailable; plausible Xwayland restart process, unproven |

Recorded verified ancestry is `816785@59550878 -> 816778@59550869 -> 816616@59550695`. The known-members list also includes 816722, 816853, and 816854, but it contains only PID/start pairs. The six PIDs were absent in both postchecks. The initial and later process inventories show the unrelated host Xwayland 7277 on `:0`, PPID 6093, PGID/SID 6081, start `15877`.

The exact recorded launch argv, expressed as a shell-style display, is:

```text
gamescope --backend headless -w 1024 -h 768 -W 1024 -H 768 -r 60 -- /usr/bin/python3.14 -I -S -B -c "import runpy,sys;sys.path.insert(0,'/home/brunner56/kp-live-20260922/harness-snapshots/task7-display-only-20260927-092903-52fe911a/runtime');runpy.run_module('kpharness.gamescope_xwayland',run_name='__main__')" --ready-child /home/brunner56/kp-live-20260922/display-only-runs/20260927-092903-52fe911a/gamescope-6c3bf82d44a749c193d8318c4e5cdddd.ready.json
```

The recorded leader's parent is consistent with the isolated Python driver invocation, but the artifacts do not serialize a PID binding for that invocation. Do not promote the inference to an observed `/proc` command.

## Gamescope, reaper, and Xwayland topology

The locally installed RPMs report `gamescope-3.16.25-1.fc44.x86_64` and `xorg-x11-server-Xwayland-24.1.13-1.fc44.x86_64`. Package versions are current observations; no reconstruction of the Fedora source package or binary-equivalence proof was performed.

Gamescope 3.16.25's application launcher calls `SpawnProcessInWatchdog`. That helper launches `gamescopereaper -- <primary-command>`. The reaper becomes a subreaper, starts its primary child, and forwards termination to descendants. It normally retains its group/session; `--new-session-id` explicitly enables `setsid()`. The default call does not include that option. This explains the retained readiness branch through 816778 and why the log mentions a reaper; it does not prove that intermediary's historical argv. Sources: [application launcher](https://github.com/ValveSoftware/gamescope/blob/3.16.25/src/steamcompmgr.cpp#L8302), [process helper](https://github.com/ValveSoftware/gamescope/blob/3.16.25/src/Utils/Process.cpp#L354), [reaper](https://github.com/ValveSoftware/gamescope/blob/3.16.25/src/Apps/gamescopereaper.cpp#L86).

The tag's wlroots submodule is `88a869855742281c98c22cab9641b317b8d065ef`, verified through the GitHub contents API. Its Xwayland startup separately double-forks; the intermediate exits and the grandchild execs Xwayland. It passes the inherited X listener descriptors and a display notification descriptor. This branch is distinct from the primary-command gamescopereaper branch. The reaper cannot adopt a sibling branch merely by being a subreaper. Source: [pinned wlroots server.c, lines 383–399](https://gitlab.freedesktop.org/wlroots/wlroots/-/blob/88a869855742281c98c22cab9641b317b8d065ef/xwayland/server.c#L383).

Thus a plausible historical topology is Gamescope -> short-lived wlroots helper -> Xwayland, followed by Xwayland adoption outside Gamescope; alongside it is Gamescope -> gamescopereaper -> Python readiness child. Adoption does not require a group/session change. Walking Xwayland's current parent chain can therefore encounter a foreign group/session even though Xwayland itself inherited the original group/session. This explains both the strict verifier failure and the later group-based cleanup collecting a plausible Xwayland identity. The exact adopter and failing chain link remain unknown.

The log reports Xwayland started on `:1`, later restarted, then Gamescope's fatal X11 I/O error and reaper shutdown. Leader return code is `-6` (SIGABRT). The two late identities are consistent with restart activity. The log does not timestamp individual lines sufficiently to assign the two PIDs or prove which cleanup signal triggered each event.

## Lost evidence in the exception path

1. The endpoint verifier discovers `pid`, executable, argv, and socket inodes locally. At the ancestry failure, none of these are attached to the exception or persisted.
2. `verify_ancestry()` reads a relation, checks group/session, and raises **before** appending that rejected link to its local chain. Even a caller receiving the accepted prefix could not recover the failing relation with the current API.
3. `self.xwayland_access = verifier(...)` assigns only on successful return. On rejection, it remains null. The outer failure receipt contains a generic message and the already-verified readiness candidate, not the failed Xwayland candidate.
4. `start()` immediately invokes cleanup. The driver collects `owned_topology` only when `boot_passed` is true; therefore it misses the failed live topology entirely. By the time its final receipt is written, the processes are gone.
5. `_ready_display` is set only after endpoint verification. `lease_after_close.x11.display` is null on failure. The supervisor treats that missing value as no socket to inspect and records `private_display_absent=true`. The later explicit check of rejected `:1` finds `/tmp/.X11-unix/X1` still present as a socket inode, despite no listener or Xwayland. The initial boolean is a vacuous pass, not proof of pathname removal.

Before rejection and before cleanup, retain a sanitized candidate record: display; PID/start; executable identity; safe argv with authority paths redacted; comm/state; each observed PID/start/PPID/PGID/SID link, including the rejected link; expected root identities; precise rejection category and failing PID; first and second observations; socket names/inodes and per-process FD attribution; endpoint peer credentials if reached; and validation phase. Record unavailable fields with error categories. Keep candidates separate from verified ownership. Do not serialize environment dumps, authority paths, or cookies.

An evidence callback or structured rejection exception can deliver this record to the lease. The durable failure receipt must be written before close. Its original boot error must survive cleanup errors. Failed displays need an explicit `candidate_display` for postchecks; missing display evidence should produce an unknown/failed check, not a successful absence assertion.

## Ownership rule that can support the installed launch topology

Use `(PID, start-token)` nodes with recorded parent identities, not process-group membership as ownership. Admission requires a complete stable chain to a recorded harness-owned launch boundary. Read every relation twice and verify the root identity. Group/session are recorded constraints and diagnostics; they cannot substitute for the chain. A descendant making a new group/session can remain an owned descendant when its ancestry is verified, but a same-group process with an unverified parent is not thereby owned.

The pinned double-fork requires a launch boundary that survives adoption. A narrowly scoped dedicated helper can establish itself as a Linux child subreaper **before** spawning exactly one Gamescope leader, record its own identity and the leader's identity, and own no unrelated workloads. Orphaned Xwayland then adopts under that dedicated boundary; its stable parent chain remains harness-owned. Alternatively, retain a trustworthy, complete pre-adoption identity chain through the short-lived helper. Opportunistic `/proc` polling may miss that helper and cannot claim completeness. If neither mechanism supplies the chain, reject with retained evidence.

The dedicated helper must be part of the recorded ownership contract, not an arbitrary pre-existing desktop/Codex/systemd subreaper. Admit only descendants of that isolated helper whose endpoint binding and executable checks pass; do not generalize to all children of a shared user-service ancestor. Keep the existing exact socket-inode binding, unique endpoint requirement, peer UID checks, both local-transport setup handshakes, forbidden access-flag checks, and TCP-listener exclusion.

This design is a proposed way to accommodate the installed launch mechanism. These receipts cannot prove it will pass a fresh installed run, nor justify admitting the historical orphan retrospectively.

Cleanup must use the same ownership ledger. Current `survivors()` swallows ancestry failures, places those candidates in `observed`, and promotes the entire set when any valid anchor exists (`gamescope_xwayland.py:418–440`). An unrelated same-group process can therefore be promoted. Fixing admission alone leaves that defect. Unknown same-group processes must remain unknown; they cannot be signalled via a group kill just because a different group member is owned. Prefer signalling verified identities through pidfds, or a dedicated containment boundary with all membership controlled and verified. Record and handle reparenting and zombie state explicitly. No claim of race-free signalling follows from a PID/start check followed by ordinary `kill(pid)`.

## Concrete regression fixtures

Use fake process relationships and socket tables; these fixtures need no real display or game launch. Numbers below are synthetic except the separately replayed recorded chain.

| Fixture | Input | Required result |
| --- | --- | --- |
| Recorded ready chain | 816785 -> 816778 -> 816616 with the exact recorded start/group/session values | Accept readiness ownership and retain the full chain |
| Dedicated adoption | Boundary 100@10; leader 200@20 parent 100; Xwayland 202@22 parent 100 after helper exit; both listener inodes and peer identities verified | Accept only under explicitly established single-launch subreaper boundary |
| Changed descendant group | Xwayland 202@22 parent 201@21 parent 200@20, with its own PGID/SID | Transitive ownership can pass; record divergence and use identity-aware cleanup |
| Historical orphan without provenance | 202@22 keeps PGID/SID 200 but parent is foreign 900@90 | Reject; do not infer ownership from group or endpoint name |
| Foreign group member beside anchor | Valid 200@20 plus 299@29 in group/session 200 with foreign parent 900@90 | Never add 299 to verified ledger and never include it in a group signal |
| Recycled intermediate/root | Start token changes on second read | Reject with both relations retained and zero endpoint admission |
| Candidate relation failure | Xwayland first relation has wrong session, or ancestor 900 does | Persist candidate PID/argv/listeners and the exact rejected link before cleanup |
| Read/parent race | Parent disappears, relationship unreadable, cycle, or parent changes between reads | Fail closed with explicit incomplete-chain reason; do not promote a partial chain |
| Restarted endpoint | Xwayland/inode/peer changes during handshake | Reject old binding; restarted process requires fresh verified ownership |
| Cookie/TCP/foreign peer | Existing negative endpoint fixtures | Continue rejecting; topology accommodation must not weaken access checks |
| Rejected-display cleanup | Access fails while candidate display is `:1`, final admitted display null, stale pathname remains | Inspect `:1`; pathname absence check fails even if listener table is empty |
| Failed start topology retention | Endpoint verifier raises before lease admission | Driver saves topology/candidate evidence before cleanup, and boot error remains primary |

Current `test_reaper_ancestry_accepts_shared_identity_and_rejects_changed_topology` tests a synthetic shared-group chain and deliberately rejects a group/session change. Existing socket fixtures likewise use 200 -> 201 -> 202 with identical groups/sessions. They do not model wlroots' adopted double-fork child. Tests were inspected, not run in this read-only audit.

## Verification and proof limits

All 13 hashes listed in `artifact-hashes.json` match the present files. The before/after snapshot hash maps agree; all 28 snapshot files match the recorded hashes. Current `gamescope_processes.py` and `gamescope_xwayland.py` hashes match the snapshot (`8c0932349ecc53684192f2c1ada89993ef1599dec24e290636c82aac41918fc2` and `38487695ac43b6e23e55a2c3db77ca7750721e61c51ad02650f636a9ed6178cc`). This ties the line-level explanation to the captured implementation.

The retained run proves one failed display admission and reported successful cleanup of its six recorded identities. It proves neither a functioning credential-free endpoint handshake nor display geometry, GL acceleration, capture, input, game execution, or complete historical process ancestry. The stale pathname check is explicit and must not be hidden by the earlier null-display check. No source edit or new runtime validation was performed by this audit.

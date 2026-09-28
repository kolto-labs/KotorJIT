# Task 7 topology and socket repair: independent review

## Current disposition after fix round 1

Scoped re-review on 2026-09-27: **I1 ADDRESSED; I2 ADDRESSED. Specification verdict: PASS for the two requested fixes. Code-quality verdict: PASS for the scoped fix round. No new Critical or Important findings.** The initial review below is retained as history and its changes-required/gate-blocking disposition is superseded for these two issues.

The re-review inspected the current implementation, the added host-test source, the revised documentation, and the writer's round-1 report. It did not run tests or launch any display, game, Wine, or other workload; no signals, source edits, or socket mutations were performed. Only this review artifact was updated. The writer reports 126 passing host tests; that run count was not independently reproduced here.

**I1 — ADDRESSED.** `gamescope_socket.py` no longer contains or invokes the blanket `fd_users` scan. Admission retains owned-Xwayland FD-to-listener binding, captures controller and Xwayland network-namespace device/inode identities, verifies equality and the established controller namespace, and rechecks them through endpoint handshakes. Cleanup requires those admitted namespace identities and rechecks the current controller namespace before and after complete socket-table scans. Both exact pathname and abstract names block removal regardless of state. Empty tables, wrong headers, truncated rows, read errors, and namespace mismatches fail closed. The receipt and documentation explicitly scope endpoint absence to the admitted controller network namespace and no longer claim absence of arbitrary filesystem FD references.

The added tests directly cover the old operational counterexample: one uses the real local `/proc/net/unix` and real namespace identity with a disposable stopped socket while forbidding `/proc` and `/proc/1/fd` enumeration. The writer reports the actual host's PID-1 directory was unreadable during that successful regression. Separate fixtures cover connected and listening rows on both names, malformed table evidence, wrong namespace at admission/cleanup, and namespace changes during rechecks. These tests retain the relevant endpoint refusal behavior without requiring foreign-process FD privileges.

**I2 — ADDRESSED.** The parsed, regex-constrained candidate display is now assigned and durably written immediately after readiness JSON parsing, before child identity, authority, environment, and ancestry admission checks. Cleanup begins with an explicit unknown socket state. Rejected candidates use `lstat` and exact socket-table checks, never gain unlink authority, and cannot pass while the node or either endpoint remains. A launched process without an established candidate display now raises a cleanup failure and retains unknown socket evidence. Explicit authority refusal and original boot-error priority remain intact.

The new rejection matrix covers explicit authority, environment mismatch, and failed ancestry with a preserved stale pathname and abstract/connected table evidence; it asserts the candidate, cleanup failure, original boot error, unchanged inode, and absence of target unlink. Malformed JSON and missing-display fixtures separately assert unknown socket status and a lease that has not closed successfully.

**Gate implication:** these two review findings no longer block preparation of the fresh serialized display-only gate. The separate supervisor must still present the actual canonical lock FD to the controller, use a fresh verified snapshot and correct repository-root metadata, and preserve historical X1 and protected displays. This scoped PASS is not installed Gamescope or live-cleanup proof.

## Initial review, before fix round 1

Reviewed 2026-09-27 in `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation` against the task brief, topology failure audit, stale-node audit, and writer report. Source inspection included comparison against the failed display gate's retained runtime snapshot. No source changes, tests, display/game/Wine launches, signals, or socket-node changes were performed by this review. The only review artifact written is this report. Read-only host inspection confirmed `/proc/1/fd` is inaccessible to the current account.

**Specification verdict: changes required.** The core ownership and exact-node cleanup design meets the intended direction, but rejected readiness can still evade pathname cleanup evidence. The all-process FD prerequisite also prevents a successful cleanup on the present host.

**Code-quality verdict: changes required, two Important findings.** No Critical finding. The reported 121 passing host tests were inspected as source and as the writer's report, not rerun or independently certified here. They do not cover the rejected-readiness counterexample below or successful production cleanup with the host's actual permissions.

## Critical findings

None found within the reviewed scope. In particular, no surviving same-group observation is promoted merely because a different process is owned; signals use verified identities and pidfds.

## Important findings

### I1. Ordinary cleanup cannot pass the unconditional foreign descriptor scan

Location: `scripts/harness/kpharness/gamescope_socket.py:85–106`, called by `gamescope_xwayland.py:521–524`.

`fd_users()` enumerates every numeric `/proc` directory, then every process's FD directory. A `PermissionError` propagates and prevents unlink. This is safe refusal, but it is a present operational failure, not only a hypothetical limitation: read-only inspection returned `ls: cannot open directory '/proc/1/fd': Permission denied`. Thus even an otherwise successfully admitted and completely stopped display cannot complete stale-node cleanup under the current unprivileged controller.

The existing scanner fixture substitutes a readable fake `/proc` and the successful cleanup fixtures substitute an empty `users_reader`. Neither exercises the production permission boundary. The writer acknowledges the risk, but a new display gate unchanged would encounter a known cleanup blocker after already creating resources.

Recommended resolution: remove the requirement to read unrelated processes' FD tables for this endpoint absence proof, rather than grant the controller broader privileges. Preserve admission's owned-Xwayland FD-to-listener attribution. At cleanup, retain repeated complete socket-table checks for both exact endpoint names in every state, exact captured filesystem-node identity, independently verified owned-process absence, canonical lock proof, and protected sibling checks. If the literal audit requirement of no FD references is revised to no live endpoint users, record that change explicitly in the contract and tests.

The relevant Linux implementation copies a stream listener's address to its accepted sockets; `/proc/net/unix` prints addresses for sockets in all states. This supports endpoint absence from the complete table without reading arbitrary root-owned FDs. A socket FD's kernel socket inode is distinct from the pathname node; an `O_PATH` reference to the latter is not an active X11 endpoint. However, `/proc/net/unix` is network-namespace local, not globally authoritative. Preserve or verify the admitted endpoint's network-namespace scope before making this substitution; do not claim absence in unrelated namespaces. Primary source: [Linux AF_UNIX implementation, `unix_stream_connect`, `unix_get_first`, and `unix_seq_show`](https://raw.githubusercontent.com/torvalds/linux/master/net/unix/af_unix.c).

Required regression: cleanup of a stopped admitted endpoint succeeds despite an unrelated unreadable FD directory under the revised endpoint contract, while pathname, abstract, accepted/connected rows, unreadable socket-table evidence, and wrong namespace evidence still refuse cleanup. No real display is needed.

### I2. Candidate display is retained too late to cover rejected readiness

Location: `scripts/harness/kpharness/gamescope_xwayland.py:273–309` and `:525–533`.

`candidate_display` is assigned only after readiness ancestry, child environment equality, and explicit-XAUTHORITY rejection. A syntactically valid display is already retained in `_rejected_ready_child['display']`, but `_close()` does not use it. Consequently, these earlier failures skip both socket cleanup branches and can produce `cleanup_phase=passed` after process teardown while the failed display's pathname remains.

Concrete counterexample: readiness contains a valid non-host `DISPLAY=:9191` plus an otherwise valid explicit authority path; the ready child and leader identities are stable and ancestry is owned. The deliberate explicit-authority refusal at line 307 fires before line 308. Cleanup terminates and reaps all verified processes, but `xwayland_access` and `candidate_display` are both null. Lines 525–533 do not inspect `/tmp/.X11-unix/X9191`, and `_closed` becomes true even if its stale socket exists. This reproduces the audit's null-admitted-display blind spot on a different rejection path. Child environment mismatch or early ancestry rejection can follow the same route.

Recommended resolution: retain a safely parsed candidate display immediately when readiness supplies one, independently of acceptance. Use that candidate only for preservation and absence checks until full endpoint admission grants exact-node deletion authority. If Gamescope was launched but a candidate display cannot be established, record socket cleanup as unknown rather than imply endpoint absence. Keep explicit authority refusal and original boot-error priority unchanged.

Required regressions: valid display plus rejected explicit authority, environment mismatch, and ancestry rejection must preserve the candidate and fail cleanup when its pathname or either transport remains; none may unlink an unadmitted node. A malformed/no-display readiness failure must not assert successful endpoint absence.

## Verified design and integration observations

| Area | Review result |
| --- | --- |
| Subreaper establishment | Set before `Popen`, read back, controller PID/start recorded. Existing subreaper, multiple threads, or existing children refuse launch. Process-wide state intentionally remains until dedicated controller exit; this is documented, and a second lease in the same process refuses. No restoration claim is made. |
| Ordinary versus adopted ownership | Ordinary ancestry is checked twice to the recorded launch owner and may cross group/session changes. Adoption requires the recorded controller PID/start and verified boundary flags; every intervening adopted chain member must retain the owner's PGID/SID. A foreign adopter and controller reuse are rejected. |
| Candidate topology evidence | Endpoint-verifier candidates retain executable, redacted argv, relationship, socket FD/listener evidence, and failed first/second ancestry observations through the evidence callback before close. The earlier readiness gap is I2. |
| Signaling and reaping | Each signal opens a pidfd, rechecks start identity, and closes the descriptor. No group kill remains. `Popen.poll()` owns direct leader status; PID-specific `waitpid(WNOHANG)` excludes that leader and applies only to recorded adopted direct children. Live or unreaped recorded children prevent absence proof. |
| Same-group observations | Each newly discovered identity independently passes ancestry or remains unknown. An unknown same-group member beside a valid anchor is not signaled and blocks cleanup success. |
| Exact node provenance | Full admission captures parent and node identity while verified Xwayland holds both listener inodes; both transport handshakes and repeated identity checks precede acceptance. Historical X1 evidence grants no deletion authority. |
| Canonical lock | Guard requires the actual matching lock-file inode through a controller FD whose fdinfo proves an exclusive whole-file flock. A mere recorded path or external assertion does not pass. |
| Production creative integration | `creative.py` enters `live_lock()` before constructing/booting the session and keeps it through teardown. `LinuxWineGamescopeCreativeSession` calls the lease in that same Python process. The snapshot driver supplies repository-root metadata, and canonical worktree resolution converges on the same lock. The separate display-only supervisor still needs the inherited actual FD as identified by the writer. |
| Snapshot closure | Static import traversal visits `creative -> creative_wine -> gamescope_xwayland -> gamescope_socket`; the additional local import in `gamescope_processes` is also visible to AST traversal. The new module is therefore part of a freshly generated closure. This is source-traced closure, not a newly generated snapshot receipt. |
| Path traversal and replacement | The production display is regex-constrained before path construction; capture requires an exact numeric X basename. Cleanup consumes that in-memory capture and unlinks only its basename relative to a verified directory FD. No disk receipt or arbitrary caller-supplied pathname is loaded as authority in this flow. Full identity comparison rejects changed inode/type/uid/mode/timestamps and parent changes. |
| Siblings and idempotence | All other numeric X nodes and their listener rows are compared before/after; target absence still requires process and listener checks. A replacement after a prior removal fails identity checks rather than borrowing the old receipt. |
| Residual unlink race | The documented final-stat/unlink race is a Linux interface limitation accepted by the parent ruling. This review does not require nonexistent atomic inode-conditioned unlink. Existing injected replacement tests cover detectable pre-unlink changes, not impossible atomicity. |
| Error separation | Original boot error and cleanup attempts remain separate; cleanup failure does not replace the original boot exception. Read errors in required node/lock/listener evidence fail closed. |

## Gate disposition

Do not run the fresh serialized display-only gate unchanged. Resolve I1 and I2, review the narrow changes and their host regressions, then generate a fresh verified snapshot. Keep the historical X1 and protected host displays untouched. A later live gate remains required to establish installed Gamescope topology, handshake, geometry, renderer, and cleanup behavior; this review and the writer's host-test counts do not establish those outcomes.

# Task 7 stale X11 socket audit

Audit date: 2026-09-27 (America/Chicago). This is a read-only audit. No
process was launched, no signal was sent, and no filesystem entry was
removed. The host `:0`, the `:94` Xvfb, and the `:100` Xvfb were left alone.

## Finding

`/tmp/.X11-unix/X1` is currently a stale pathname node: it is a socket inode,
but there is no corresponding pathname or abstract UNIX listener in the
kernel socket table, no process owns or references it, and no `Xwayland :1`
or Gamescope process remains. It is safe to unlink this exact node only after
the fail-closed contract below passes in the same serialized cleanup window.
It was intentionally preserved for this audit because the task explicitly
forbade deletion.

The strongest attribution is **run-correlated and very likely created by the
failed owned Gamescope/Xwayland attempt**, with a small proof limit: the run
did not retain an open descriptor or a pre-launch inode snapshot that could
prove the historical creator byte-for-byte. The pathname's ownership, exact
creation/change time, mode, and the Gamescope log all line up with that run;
the absence of a live listener proves staleness now, not historical authorship
by itself.

## Current pathname and host state

The exact current `lstat` observations are:

| Path | Type | device | inode | mode | uid:gid | mtime/ctime (CDT) |
| --- | --- | ---: | ---: | ---: | --- | --- |
| `/tmp/.X11-unix/X0` | socket | 34 | 123 | 0755 | 1000:1000 | 2026-09-20 07:06:46 |
| `/tmp/.X11-unix/X1` | socket | 34 | 1231594 | 0755 | 1000:1000 | 2026-09-27 04:30:06.951145127 |
| `/tmp/.X11-unix/X94` | socket | 34 | 941784 | 0777 | 1000:1000 | 2026-09-26 23:52:02 |
| `/tmp/.X11-unix/X100` | socket | 34 | 905457 | 0777 | 1000:1000 | 2026-09-22 15:58:58 |

The parent `/tmp/.X11-unix` is the expected root-owned sticky directory
(`01777`, inode 3). The audited node is owned by uid 1000, the current user,
and has the 0755 mode recorded in the retained receipt. Its nanosecond
timestamps are both `1790501406951145127`; the corresponding coarse epoch
reported by `stat` is `1790501406`.

The retained run started at `2026-09-27T09:30:03.532842Z`, spawned Gamescope
at `09:30:05.749490Z`, and reached readiness at `09:30:07.988392Z`. The X1
node's timestamp is `09:30:06.951145127Z`, inside that interval. The retained
Gamescope log says it failed to bind the already-used host `@/tmp/.X11-unix/X0`
and then started Xwayland on `:1`. The lease later failed its Xwayland
group/session ancestry predicate and closed at `09:30:10.542549Z`. This is
strong correlation with the failed lease's Xwayland pathname creation.

The run's supplemental postcheck at `09:30:43.389383Z` already recorded:

* rejected display `:1`;
* all six recorded lease PIDs absent;
* no `:1` pathname or abstract socket-table match;
* no private Xwayland process;
* the canonical live-game lock free;
* the filesystem pathname still present.

The direct read-only recheck agrees. `/proc/net/unix` has no
`/tmp/.X11-unix/X1` or `@/tmp/.X11-unix/X1` entry. `ss -xlnp` has no X1
listener. Exact `lsof -nP /tmp/.X11-unix/X1` and `fuser -v
/tmp/.X11-unix/X1` produced no process. The only Xwayland process is the
desktop server `/usr/bin/Xwayland :0` (PID 7277, PGID/SID 6081); the other
display listeners belong to `/usr/bin/Xvfb :94` (PID 3567254) and `Xvfb :100`
(PID 1433656). No `gamescope` or `gamescopereaper` process is present.

The live listener inventory is therefore:

* `:0`: pathname and abstract listeners, owned by the desktop Xwayland/KWin
  process group;
* `:94`: pathname and abstract listeners, owned by Xvfb PID 3567254;
* `:100`: pathname and abstract listeners, owned by Xvfb PID 1433656;
* `:1`: none, despite the filesystem node remaining.

The retained receipts are consistent with this distinction. The initial gate
said `private_socket_path_exists=false` because it only considered the
admitted display field, which was null after boot failure. The later
`postcheck-rejected-display.json` explicitly corrected the rejected-display
case and said `socket_path_exists=true` with no socket-table match. The
`remaining-socket-stat.json` says `action: preserved; no unlink`. The source
and sealed snapshot hashes match, so this is not an artifact of post-run
source mutation.

## Ownership conclusion and proof boundary

The node can be classified as a **stale run-correlated X11 pathname**. It is
not a live X11 endpoint. Its uid, mode, exact path, and timestamp fall within
the failed run, and the Gamescope log names `:1`; those facts make creation by
that run's Xwayland the practical explanation. A historical creator claim
stronger than that is unavailable because the run did not preserve a
preflight `lstat`, creator PID/start identity tied to inode 1231594, or the
Xwayland listener FD set while it was live. The audit must therefore avoid
claiming a byte-level creator proof.

The node is not evidence that the desktop `:0` server is stale. `X0` has live
pathname and abstract listeners and a live Xwayland process. `X94` and `X100`
also have live listeners and must not be touched. The numeric display alone
is never sufficient cleanup authority.

## Fail-closed cleanup contract

Future cleanup may remove only the exact pathname
`/tmp/.X11-unix/X1`, and only while holding the canonical
`/run/media/brunner56/MyBook/Workspaces/KotorPhasor/tmp/harness-locks/live-game.lock`
exclusively. Failure to acquire that lock is `unknown`, leaves the node, and
must fail the gate. The cleanup must never glob `X*`, remove the directory,
touch `X0`, or infer authority from a display number or an old report alone.

The operation must capture and retain a pre-unlink record containing the
absolute path, exact parent directory device/inode/mode, target device/inode,
socket type, uid/gid, mode, size, mtime_ns, ctime_ns, and UTC timestamp. For
this particular node, the expected target identity is device 34, inode
1231594, socket type, uid/gid 1000:1000, mode 0755, size 0, and the recorded
nanosecond timestamps above. A mismatch, a symlink, a regular file, a
directory, an unexpected owner/mode, a missing parent, or any stat error is
`unknown`; do not unlink.

Before unlinking, the cleanup must fail closed if any of the following is
true or cannot be checked:

1. Any `/proc/net/unix` row names either `/tmp/.X11-unix/X1` or
   `@/tmp/.X11-unix/X1`, regardless of state (`LISTEN`, connected, or other).
2. An Xwayland process advertises `:1`, an owned lease member from the
   retained PID/start set is still live, or a Gamescope/reaper process from
   the current lease is live. A PID that exists with a changed start identity
   is PID reuse/uncertainty and also refuses cleanup.
3. Exact `lsof`/`fuser`/descriptor inspection, when used by the implementation,
   reports a user of this node or returns an unreadable/indeterminate result.
4. The canonical lock cannot be acquired, the parent directory is not the
   expected sticky directory, or any identity/stat/socket-table read fails.
5. A final `lstat` of the exact name differs from the captured identity. The
   final socket-table scan and process checks must be repeated immediately
   before the unlink.

The unlink itself must use the opened expected parent directory and the
literal basename `X1`; it must not follow symlinks or accept a path assembled
from untrusted display text. The implementation should use directory-FD
relative operations and retain the before/after identity record. The lock and
immediate rechecks bound races with cooperating harness processes; the receipt
must state that no pathname unlink can make an uncooperative concurrent
creator impossible. If a final check races or returns an error, report
`unknown` and leave the node whenever the kernel operation has not already
removed it.

After a successful unlink, the receipt must independently prove:

* `lstat('/tmp/.X11-unix/X1')` is `ENOENT`;
* `/proc/net/unix` has no pathname or abstract X1 row;
* `ss -xapn` has no X1 entry and exact `lsof`/`fuser` have no user;
* the parent directory's device/inode/mode and the sibling X0/X94/X100
  identities/listeners are unchanged;
* all recorded owned PIDs are absent by `(pid,start)` and the canonical lock
  is released.

Any failed postcondition makes cleanup `failed` or `unknown`, never
`passed`. The receipt should distinguish `already_absent` (only when the
precondition also proves no X1 listener) from `removed`; a replacement file,
socket, symlink, or active endpoint is never treated as already absent.

## Required tests

The cleanup contract needs focused, host-only tests. They can use temporary
UNIX sockets and injected `/proc` readers; they do not need Gamescope, a real
Xwayland, Wine, or a game.

1. **Stale pathname success.** Bind a temporary pathname socket, close the
   listener so only the node remains, provide an empty socket table, and
   unlink the exact target. Assert `removed`, exact inode match, target
   `ENOENT`, and unchanged sibling sockets.
2. **Live pathname listener refusal.** Keep the listener open and expose its
   pathname row. Assert refusal and preservation of the node.
3. **Live abstract listener refusal.** Leave a stale pathname node but keep
   `@/tmp/.X11-unix/X1` bound. Assert refusal; pathname absence alone is not
   enough.
4. **Established/peer row refusal.** Supply a non-`LISTEN` X1 row. Assert
   refusal, because a connected endpoint is still live.
5. **Identity replacement race.** Replace X1 after the first stat with a
   different socket, symlink, regular file, or directory. Assert refusal and
   preservation of the replacement.
6. **Wrong ownership/type/mode/parent.** Exercise uid/gid mismatch, wrong
   mode if the contract pins it, non-socket type, symlink, missing parent, and
   stat errors. Every case must leave the target untouched.
7. **PID and process uncertainty.** Exercise a recorded PID with a changed
   start time, a live `Xwayland :1`, an owned lease member that remains live,
   unreadable `/proc`, and a process descriptor scan error. All are
   fail-closed; none may authorize a signal or unlink.
8. **Lock contention.** Hold `live-game.lock` from another process. Assert
   cleanup returns `unknown` without inspecting or changing X1.
9. **Host and sibling preservation.** Place live X0, X94, and X100 listeners
   beside a stale X1. Assert only X1 changes and every sibling inode,
   listener, and owning PID remains identical.
10. **Idempotence and replacement after cleanup.** A second run reports
    `already_absent` only with a clean no-listener scan. If a new X1 socket or
    any other node appears, the second run re-admits the full identity checks
    and never treats the old receipt as authority.
11. **Final-check race.** Inject a replacement between the final stat and the
    unlink operation. The test must prove the implementation cannot silently
    delete a different node; if the chosen kernel primitive cannot provide
    that guarantee, the operation must return `unknown`, retain the node, and
    document the residual race instead of reporting success.
12. **Receipt integrity.** Verify that failures retain the pre/post evidence,
    exact path, reason, and sibling preservation facts without rewriting the
    original run receipts or disclosing Xauthority/cookie data.

The existing run's `gamescope-lease.json` cleanup pass proves cleanup of the
recorded Gamescope process group only. It does not prove pathname-node
cleanup, so a future gate must keep these two predicates separate.

## Evidence paths

Primary retained run:

`/home/brunner56/kp-live-20260922/display-only-runs/20260927-092903-52fe911a/`

Relevant files are `config.json`, `preflight.json`, `gamescope.log`,
`gamescope-lease.json`, `driver-result.json`, `gate-result.json`,
`postcheck-rejected-display.json`, `remaining-socket-stat.json`,
`snapshot-before.json`, `snapshot-after.json`, and `artifact-hashes.json`.

The accompanying gate narrative is
`/home/brunner56/kp-live-20260922/task7-display-only-gate-report.md`. The
reviewed cleanup implementation is the hash-matched
`scripts/harness/kpharness/gamescope_xwayland.py` and
`gamescope_processes.py` in the `lua-boundary-validation` worktree; its
process-group cleanup is fail-closed for known process identities, while the
remaining X1 pathname requires the separate contract above.

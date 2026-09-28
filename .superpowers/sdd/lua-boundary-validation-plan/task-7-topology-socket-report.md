# Task 7 topology/socket repair report

Status: **DONE_WITH_CONCERNS**. Implementation and host checks are complete for
independent scoped review. No Gamescope, Xwayland, Wine, game, or display gate
was launched. The existing `/tmp/.X11-unix/X1` was not modified or deleted.
No commits, PRs, or unrelated source edits were made.

## Implementation

- `scripts/harness/kpharness/gamescope_processes.py`: fresh Linux controller
  subreaper establishment and verification before Gamescope launch; exact
  recorded PID/start boundary; stable ordinary ancestry and constrained orphan
  adoption; structured rejected chain observations; redacted candidate process,
  executable, command and FD/listener evidence; per-process pidfd signalling.
- `scripts/harness/kpharness/gamescope_xwayland.py`: durable candidate evidence
  before rejection/close; explicit candidate display; no same-group promotion;
  independently verified ownership ledger; adopted-child PID-specific reaping
  that excludes the Popen leader; exact socket cleanup integration and retained
  failure evidence. Boot errors remain primary over cleanup failures.
- New `scripts/harness/kpharness/gamescope_socket.py`: capture admitted pathname
  and parent identities while listeners are owned; require a canonical live
  lock capability; repeat owned-process, both-transport, FD-user, node and parent
  checks; use directory-relative unlink of one literal recorded basename;
  compare all protected sibling node identities and listener rows. Ambiguity is
  `unknown` and raises a cleanup failure. No historical receipt grants authority
  to delete the preserved X1.
- `tools/kpharness_gamescope_boot_repair_test.py` and
  `tools/kpharness_gamescope_backend_test.py`: focused host counterexamples and
  updates from group-signalling expectations to identity-specific signalling.
- `docs/creative-runner.md`: controller lifetime, ownership, evidence, cleanup,
  lock inheritance, and proof limitations.

Normal transitive ancestry can cross PGID/SID changes per the linked topology
analysis because pidfd cleanup no longer signals a shared group. Adoption under
the recorded controller still requires the Gamescope PGID/SID. The readiness
branch continues to require stable ancestry to the direct launch owner.

## Validation

All commands ran in the lua-boundary-validation worktree, with each test suite
bounded by `timeout 60s`:

| Check | Result |
| --- | --- |
| `python tools/kpharness_gamescope_boot_repair_test.py` | 36 tests passed, 0.337 s |
| `python tools/kpharness_gamescope_backend_test.py` | 35 tests passed, 1.740 s |
| `python tools/kpharness_creative_test.py` | 28 tests passed, 0.456 s |
| `python tools/kpharness_physical_console_test.py` | 22 tests passed, 0.011 s |
| `python -m py_compile` on 3 changed Gamescope modules and 2 test modules | passed |
| `git diff --check` including explicit no-index checks for untracked implementation/test files | passed |

The creative suite intentionally prints its injected cleanup failure; the suite
still exits zero with all 28 tests passing. Total: **121 tests passed**.

Counterexamples cover the exact recorded ready chain; normal ancestry with
changed groups; double-fork adoption with endpoint handshakes; external adopter;
controller reuse and missing/unverified boundary; parent/read/cycle races;
redacted candidate retention before rejection and before cleanup; unknown
same-group members beside a valid anchor; pidfd reuse refusal; adopted zombie
reap versus unreaped/live descendant failure; exact stale node removal;
pathname, abstract, and established rows; FD users; live/PID uncertainty;
unreadable FD/table evidence; inode/type/uid/mode/parent changes; protected X0,
X94, and X100 siblings; idempotence/replacement after cleanup; lock capability
and independent-open lock contention; and injected final-check replacements.
Socket tests use only disposable temporary UNIX sockets, fake process tables,
and injected process actions. They never launch a display or signal real PIDs.

## Required external follow-up and limitations

1. Independent scoped review remains required. There has been no live gate in
   this implementation turn; test success is not installed Gamescope proof.
2. The next display-only supervisor must pass its actual canonical lock FD into
   the isolated controller with `pass_fds=(lock.fileno(),)`, and set
   `KP_GAMESCOPE_REPO_ROOT` for the snapshot runtime to the correct repository.
   Merely recording that the supervisor holds a lock is insufficient. The
   existing failed-run supervisor does not pass this FD and must be updated
   before a reviewed fresh gate. No old run artifact was edited here.
3. Unreadable `/proc/<pid>/fd` or other required descriptor evidence fails
   closed. Unprivileged controllers may encounter this for other users' or
   protected processes, blocking stale-node removal. No incomplete FD scan is
   treated as proof that there are no users. This must be assessed before a
   live gate; do not retry a failed gate unchanged.
4. Linux has no unlink-by-inode primitive. Exact dirfd/basename operations and
   final identity rechecks protect cooperating harness activity under the lock;
   an uncooperative change after the final stat and before unlink is not
   eliminated. Injected pre-unlink changes are refused and preserved. The
   receipt states the residual race; this is not a claim of atomic inode-bound
   unlink. This implements the parent's explicit ruling on the audit's
   otherwise unattainable final-race guarantee.
5. Controller subreaping remains process-wide for the dedicated process's
   lifetime. A fresh controller is required per lease. Existing children,
   multiple threads, or an already enabled subreaper refuse launch.
6. The current preserved X1 remains unadmitted historical evidence. This code
   deliberately cannot delete it from old correlation alone. Any separate
   historical-node remediation remains outside this change.

## Independent review fix round 1 (2026-09-27)

Addressed both Important findings in
`/home/brunner56/kp-live-20260922/task7-topology-socket-review.md`.
This section supersedes the original report's all-process FD scan requirement
and concern 3 above; the original text is retained as implementation history.

**I1 — ordinary cleanup blocked by foreign FD permissions:** removed the
unconditional all-process FD scanner. Admission still binds the owned Xwayland
FDs to both exact listener inodes. The controller records its network namespace
kernel device/inode at establishment; endpoint admission records and verifies
both controller and Xwayland namespace identities and rechecks them during
handshakes. The admitted node carries those identities into cleanup. Cleanup
verifies the current controller namespace against both admitted identities
before and after repeated complete `/proc/net/unix` reads. Both exact pathname
and abstract names block removal in every state, including accepted/connected
rows. Empty, malformed, unreadable, or wrong-namespace evidence fails closed.

This deliberately revises “no FD references anywhere” to “no live named endpoint
in the admitted controller network namespace.” It does not claim absence in
unrelated namespaces or require absence of harmless `O_PATH` references to the
filesystem node. No additional privilege is requested or used. The current-host
regression confirmed `Current-host /proc/1/fd unreadable: True`, then removed
only a disposable stopped UNIX-socket pathname using the real local socket
table, while explicitly forbidding all-/proc or PID-1 descriptor enumeration.

**I2 — candidate display retained after early rejection:** sanitized display
retention now happens immediately after readiness JSON parsing, before process,
authority, environment or ancestry checks. Cleanup starts with an explicit
unknown socket status and exact candidate pathname when available. Rejected
unadmitted candidates are never unlinked; a remaining node or either endpoint
transport causes cleanup failure. A launched process whose display cannot be
established records socket cleanup as unknown and cannot pass. Original boot
errors remain primary over these cleanup failures.

New regressions cover explicit-authority, environment-mismatch, and ancestry
rejection against stale pathname and abstract/connected evidence; malformed or
missing readiness displays; namespace mismatch at admission and cleanup;
namespace change during rechecks; actual listening and connected row parsing;
malformed table refusal; and the host's unrelated unreadable PID-1 FD directory.

Validation after round 1:

| Check | Result |
| --- | --- |
| Repair suite, `timeout 60s python tools/kpharness_gamescope_boot_repair_test.py` | 41 passed, 0.834 s |
| Backend suite, `timeout 60s python tools/kpharness_gamescope_backend_test.py` | 35 passed, 2.714 s |
| Creative suite, `timeout 60s python tools/kpharness_creative_test.py` | 28 passed, 0.560 s |
| Physical-console suite, `timeout 60s python tools/kpharness_physical_console_test.py` | 22 passed, 0.027 s |
| Python compilation of changed implementation/test modules | passed |
| Tracked and explicit untracked whitespace checks | passed |

Total: **126 tests passed**. Independent re-review remains required. No display,
Gamescope, Xwayland, Wine, game, or live gate was launched, and current X1 was not
modified or deleted. The canonical-lock inheritance requirement and documented
final-stat/unlink residual race remain unchanged.

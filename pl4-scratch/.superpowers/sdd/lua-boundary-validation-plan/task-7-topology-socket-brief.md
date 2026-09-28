# Task 7: installed Gamescope topology and stale X11 node repair

Authoritative evidence:

- `/home/brunner56/kp-live-20260922/task7-topology-failure-audit.md`
- `/home/brunner56/kp-live-20260922/task7-stale-x11-socket-audit.md`
- failed run `/home/brunner56/kp-live-20260922/display-only-runs/20260927-092903-52fe911a`

## Required implementation

1. Establish and record a Linux child-subreaper boundary in the single-purpose harness process before launching Gamescope. Record controller PID/start and verify the subreaper state. Accept an orphan-adopted Xwayland only when its PID/start is stable, PPID is the recorded controller, and its PGID/SID equal the verified Gamescope owner. Keep the existing ordinary transitive owner chain. Never accept a shared external adopter.
2. Persist the candidate PID/start/PPID/PGID/SID/executable/cmdline and failed chain before rejection. Retain socket process evidence as part of admission.
3. Cleanup may signal/reap only independently verified identities. Remove the current promotion of all matching PGID/SID observations after one anchor. Reap recorded adopted children safely without stealing the direct `Popen` leader's status.
4. During successful endpoint admission capture the exact pathname socket node identity (parent, basename, device, inode, type, uid, mode) while the owned Xwayland holds the matching listener. After all verified owned processes and both pathname/abstract listeners are absent, and after confirming no FD users plus an unchanged exact node, unlink only that recorded basename using directory-relative operations. Recheck before unlink and prove protected sibling X displays are untouched. On ambiguity, retain the node and fail cleanup evidence.
5. Preserve the reviewed no-cookie access model, snapshot/provenance, boot/cleanup error separation, and explicit-authority refusal.

## Tests and gate

Host tests must cover normal owner chain; double-fork orphan adopted by recorded subreaper; external adopter refusal; controller PID reuse; candidate evidence retention; unknown same-group process never gaining signal authority; adopted zombie reap and live descendant failure; owned stale node removal; pathname/abstract active refusal; FD user; inode replacement; wrong type/uid; protected siblings; idempotence; final race and unreadable evidence.

No game/display launch during implementation. Independent scoped review is required. Only after review run one new serialized display-only gate from a fresh verified snapshot. Do not retry a failed live gate unchanged.

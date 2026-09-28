# Task 7 Gamescope/Xwayland authority mechanism audit

Audit date: 2026-09-27

Scope: read-only review of the retained failed run
`private-gpu-runs/20260927-081255-56942ef0`, the boot-cause report, the
Gamescope/Xwayland lease in
`/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`,
and the locally installed Gamescope/Xwayland package material. No game,
Wine, Xwayland, Gamescope, display, or test process was launched and no
product-tree file was edited.

The requested `task-7-boot-repair-brief.md` was not present under either the
worktree or `/home/brunner56/kp-live-20260922` during the audit. The
conclusions below therefore use `task7-actual-boot-cause.md`, the retained
run, the current source on disk, and the installed package documentation as
the available brief/evidence set.

## Finding

The failed run published a readiness payload containing a display and no
Xauthority or Wayland authority:

```json
{"pid": 486796, "start": "59098686", "environment": {"DISPLAY": ":1"}}
```

This is an observed fact from the retained JSON. It is not, by itself, proof
that the Xwayland server had no authorization file: a server could use an
authorization file without exporting `XAUTHORITY` to a child. In this setup,
however, the lease launches Gamescope with a sanitized environment and the
readiness child serializes only the three authority variables it actually
inherits (`gamescope_xwayland.py:194-195, 447-453`). The log records Gamescope
starting a headless compositor and Xwayland on `:1` after the `:0` abstract
socket collision (`gamescope.log:24-45`). It does not record an Xauthority
file, cookie, Xwayland command line, socket ownership, process IDs, or
process ancestry. Consequently the strongest historical statement is
“DISPLAY-only was published”; the server-side access model remains an
inference until a process/socket snapshot or an equivalent live probe is
retained.

The old validator described by `task7-actual-boot-cause.md` rejected this
payload before ancestry, geometry, renderer, or game launch. Its cleanup
predicate also treated any matching `/proc` identity as alive because
`process_relationship()` discarded the `/proc/PID/stat` state field. A
matching zombie can retain PID, start token, PGID, and SID; sending SIGKILL
cannot remove it. That is a code-proven explanation for the retained
“survived SIGKILL” cleanup error, but the run did not retain the historical
`stat` or process-tree evidence, so it does not prove that this particular
leader was a zombie.

The current worktree changed while this audit was in progress. The latest
source read includes `gamescope_processes.py`, a DISPLAY-only verifier, state
filtering, survivor enumeration, cleanup attempts, and a separate
`boot_error`. Earlier reads showed the pre-repair implementation. The
observations below distinguish the retained run/old implementation from the
current source and should be checked again after the repair settles.

## What the installed Gamescope/Xwayland materials establish

The installed package is Fedora `gamescope-3.16.25-1.fc44.x86_64`, with
`/usr/bin/gamescope`, `/usr/bin/gamescopereaper`, and
`/usr/bin/Xwayland`. There is no installed `gamescope(1)` man page and no
Gamescope source checkout in the inspected local package paths. The package
README (`/usr/share/doc/gamescope/README.md:5-12`) says that Gamescope gets
game frames through Wayland/Xwayland and that the game runs in its own
personal Xwayland sandbox desktop. That documents compositor isolation and
the nested-display concept; it does not promise a cookie, an `XAUTHORITY`
environment variable, a same-user boundary, or a no-TCP guarantee.

The local Xwayland binary and man pages support the following facts:

* Xwayland accepts `-auth`, `-displayfd`, `-listenfd`, `-nolisten`, and
  `-rootless` (`/usr/share/man/man1/Xwayland.1.gz` and the inherited
  Xserver options in `/usr/share/man/man1/Xserver.1.gz`).
* `Xserver(1)` says `-auth` supplies authorization records, and when records
  exist only clients presenting a matching record are accepted. It says
  `-nolisten tcp` disables TCP transport. It also says that with no other
  authorization mechanism, the host-based list initially permits the local
  host. Thus “no cookie” is not equivalent to “private to this harness”.
* The installed Gamescope binary contains the Xwayland/reaper symbols and
  option strings, but stripped binary strings do not establish which internal
  Xwayland flags this Gamescope build passes for a particular run.

The safest interpretation is therefore: the retained payload proves
DISPLAY-only child publication; local documentation supports a nested
Xwayland desktop; neither source nor retained runtime evidence proves a
private Xauthority cookie. Treating the payload as a private authority
contract would overclaim the evidence.

## Authority contract recommendation

There are two defensible contracts, and they must not be reported as the same
thing.

### Strict private authority (recommended for the existing backend name)

Require all of the following before admitting the Gamescope backend as a
private X11 display:

1. The readiness child publishes `DISPLAY` and a nonempty absolute
   `XAUTHORITY` path that is a regular file owned by the run user. The path
   and cookie contents never enter receipts or logs. The child environment
   must exactly match the observed `/proc/PID/environ` authority subset.
2. The Xwayland command/process evidence proves the authority file is the
   one used by that server (normally an `-auth` argument or an equivalent
   server-side proof), and rejects inherited host authority.
3. Xwayland has no TCP listeners. The pathname and abstract local sockets,
   if both are exposed, must be tied to the same Xwayland process. Socket
   file ownership alone is insufficient because abstract sockets have no
   filesystem owner.
4. The Xwayland process is in the owned Gamescope process group/session and
   its ancestry reaches the recorded Gamescope identity. Intermediate
   `gamescopereaper` processes are admissible when the entire chain retains
   the recorded group/session and start identities.
5. An X11 probe made with the exact child authority succeeds, while a probe
   without that authority is rejected. This is a validation check; do not
   store the cookie or probe handshake bytes.

If Gamescope 3.16.25 does not expose a way to create this cookie contract,
the adapter should remain refused under the strict private contract. A
separate Xwayland runner that creates and owns an xauth file can establish
such a contract, but that is a product design change and was not performed by
this audit.

### DISPLAY-only local-socket contract (weaker, conditional)

The observed payload can be admitted only under an explicitly weaker access
model, such as `owned-local-unix-no-cookie`, and only after all of these are
proven at the time of admission:

* `DISPLAY` is syntactically valid, differs from the caller display, and is
  the display selected by this Gamescope instance.
* The Xwayland PID is identified from `/proc` and is a descendant of the
  owned Gamescope identity through any reaper intermediary, with unchanged
  PID start tokens, PGID, and SID before and after the socket probe.
* Both pathname and abstract AF_UNIX listeners for that display are present
  and their inodes belong to the Xwayland process. TCP listener inodes are
  absent. The local X11 setup handshake succeeds without a cookie.
* The connected socket peer has the expected UID and is the verified
  Xwayland process. This establishes the server endpoint; it does not prove
  that another local user cannot connect to a host-authorized, cookie-free
  server.
* The receipt says “same-user/local-socket, no-cookie” and keeps
  `xauthority_present=false`; it must not call this “private Xauthority”.

The current `verify_private_xwayland()` follows most of this shape and
explicitly documents that other local users are not excluded
(`gamescope_processes.py:44-50`). That is the right honesty boundary. It is
not yet sufficient as a proved Gamescope contract for two reasons:

* It requires the Xwayland command line to contain `:N`
  (`gamescope_processes.py:58-60`). Xwayland supports `-displayfd`, where the
  display number is written to a launcher's file descriptor rather than
  necessarily appearing as a `:N` argument (`Xserver.1`, `-displayfd`). A
  fresh process snapshot must establish the actual Fedora Gamescope argv;
  otherwise this check can reject a valid server or match the wrong process.
* The verifier proves a same-user local endpoint and successful no-cookie
  setup, not authorization against unrelated same-host clients. That is a
  weaker contract and should be reflected in backend admission and receipt
  terminology.

The verifier should also record enough nonsecret evidence to distinguish
“both X11 socket transports belong to this Xwayland” from “a display number
was found”: Xwayland PID/start, socket inode set, peer PID/start/UID, TCP
absence, and the process-chain identities. It should re-read those identities
after the handshake, as the current code attempts.

### Review of the proposed `/dev/null` client mechanism

The concrete proposal is technically viable as a *same-user, local-socket,
no-cookie* contract, with two qualifications that must be made explicit.

On Linux, `SO_PEERCRED` on a connected `AF_UNIX` stream socket returns the
credentials of the peer process at the time of `connect(2)` (the installed
`unix(7)` man page, section “SO_PEERCRED”, says this explicitly). For a client socket
connected to an Xwayland listener, that peer is the server side that accepted
the connection, so checking the returned peer PID/UID and then walking that
PID's ancestry is a useful endpoint binding. This applies to abstract and
pathname AF_UNIX sockets. It does not prove X11 authorization, and it is a
point-in-time result: the peer PID/start and the Xwayland/socket identity must
be checked again after the setup handshake. A test double that merely returns
the expected credentials is insufficient; the host-only test should model a
different peer PID, a different UID, and PID reuse.

The proposal should connect to and peer-check both transports when both are
claimed. The current verifier connects only to `/tmp/.X11-unix/XN` while it
maps both pathname and abstract listener inodes to the Xwayland FD set. That
mapping is useful, but a second connection to the abstract address (Python
uses an address beginning with `\0`, not the `/proc/net/unix` display spelling
`@/tmp/...`) closes the remaining “abstract endpoint is different” race. If
the implementation intentionally relies on pathname plus inode mapping for
the abstract endpoint, retain that as a documented limitation and test the
inode race.

Setting the child `XAUTHORITY` to `/dev/null` is acceptable only as an
explicit no-cookie sentinel. It prevents Xlib from falling back to the
user's `~/.Xauthority`, which is valuable, but it is not an authority file,
and it cannot authenticate to a server that actually requires a cookie. The
readiness contract must therefore either omit `XAUTHORITY` and use a private
launch environment, or define `XAUTHORITY=/dev/null` as a special
`no-cookie-sentinel` value. A generic “absolute existing XAUTHORITY file”
check must not treat `/dev/null` as a credential file; it is a character
device, not a regular authority file. Receipts should say
`access_model=owned-local-unix-no-cookie` and
`xauthority_mode=no-cookie-sentinel`, never `xauthority_present=true` or
“private Xauthority”. A regression should set a hostile `HOME` and a hostile
host `XAUTHORITY`, then assert the probe environment contains only the
sentinel and the selected display.

The current source sets this sentinel only in the post-verification client
environment (`gamescope_xwayland.py:283-288`), while `receipt()` derives
`xauthority_present` from the nonempty environment value
(`gamescope_xwayland.py:342-344`). Unless the receipt is changed to distinguish
the sentinel, a successful no-cookie run will falsely report that an
Xauthority value is present.

The handshake proves that this client can open this server without
credentials. Together with the two listener checks, no TCP listeners, the
same-user peer, and stable Gamescope ancestry, it is enough for a conditional
owner-endpoint lease. It does **not** prove a same-user access boundary for
future clients: `SO_PEERCRED` describes the peer of the verifier's own
connection, not the credentials that Xwayland will require from the next
client. If Xwayland is using host-based access with no cookie, another local
user can make a separate connection. Abstract socket permissions cannot close
that gap (`unix(7)` explicitly says they have no meaning). The no-cookie
proposal therefore cannot honestly be called “same-user private”; call it
“owned endpoint, host-local/no-cookie” and keep it below the strict private
backend contract. Reject an explicit `-ac` flag in this mode, although absence
of `-ac` still does not supply a cookie boundary.

The installed `unix(7)` page also states that abstract socket permissions have
no meaning and that abstract sockets disappear when their last references are
closed. Therefore an abstract listener cannot be admitted from a pathname
owner/mode check; process FD/inode binding and a live peer check are required.

## Process ancestry and gamescopereaper

The retained log proves only that `gamescopereaper` emitted “Parent of
gamescopereaper was killed. Killing children” and that Gamescope later
restarted Xwayland and reported an X11 I/O error. It does not give reaper
PID/PPID/PGID/SID/start data. Do not infer an observed ancestry mismatch from
that log.

The current `verify_ancestry()` is a reasonable ownership primitive: it walks
the parent chain to the recorded Gamescope PID, requires the expected PGID/SID,
checks the Gamescope start token, and re-reads each relation before returning
(`gamescope_processes.py:19-41`). A gamescopereaper intermediary is therefore
allowed by policy. A changed group/session, a missing chain, or a reused
ancestor must fail closed. The chain must be retained as sanitized PID/start/
group/session evidence if it is used to justify the lease.

One cleanup gap remains in the current shape: a readiness child is added to
`ready_child` and `_known_members` only after authority and ancestry pass
(`gamescope_xwayland.py:265-279, 364-370`). If DISPLAY-only authority fails,
the JSON has nevertheless supplied a child PID/start and often a matching
group/session, but cleanup may know only the Gamescope leader. If the leader is
already reaped while that rejected child remains live, survivor enumeration
can lack an ownership anchor and skip the child. Retain the observed child
identity and verified relationship as a *rejected candidate* for cleanup,
without promoting it to an admitted display child. Add a test for leader-dead
plus rejected-child-live.

## Cleanup and exception-preservation review

The current cleanup direction is materially safer than the retained-run
implementation:

* `survivors()` calls `Popen.poll()` before `/proc` adjudication
  (`gamescope_xwayland.py:364-367`), so the direct Gamescope child can be
  reaped before deciding whether a process remains.
* It reads process state and excludes `Z` and `X` from runnable survivors
  (`gamescope_processes.py:13-16`, `gamescope_xwayland.py:396-403`). Unknown
  state is conservatively treated as live, which is appropriate for cleanup.
* It rechecks known PID start tokens, group/session, and ancestry immediately
  before each signal; it sends SIGTERM, waits, then SIGKILL, and waits again.
* It retains cleanup attempts and a separate `boot_error` in preliminary
  evidence (`gamescope_xwayland.py:132-165, 344-355`). This addresses the old
  failure mode where cleanup replaced the original authority rejection.

Required review checks before accepting this repair:

1. **Zombie direct leader:** fake `/proc` state changes S to Z while PID,
   start, PGID, and SID remain unchanged. Fake `Popen.poll()`/`wait()` must
   reap it. Assert no SIGKILL is sent solely because the zombie remains in
   `/proc`, and cleanup reaches a passed terminal receipt.
2. **Zombie descendant:** a descendant becomes Z while the Gamescope leader
   remains live. Assert the group is still signalled if any runnable member
   remains, and that a zombie-only group does not produce “survived SIGKILL”.
3. **Live counterexample:** preserve a matching descendant in state S or R;
   assert SIGTERM then SIGKILL behavior and a bounded failure if it refuses to
   die. This prevents state filtering from hiding real survivors.
4. **Leader-dead child:** the Gamescope `Popen` is already reaped while a
   retained, identity-verified ready/rejected child remains live. Assert the
   child authorizes group cleanup, while an unverified same-group PID does not.
5. **PID reuse and topology mutation:** change a known start token, parent,
   PGID, or SID between scans. Assert no signal is sent and the receipt says
   exactly which identity changed. Test Gamescope -> gamescopereaper -> child
   as accepted only with a stable shared group/session.
6. **Socket race:** mutate the Xwayland PID, socket inode, peer PID, or
   process chain between the pre-connect and post-handshake reads. Assert
   admission fails closed and no foreign socket is used.
7. **Authority modes:** DISPLAY-only must call the socket verifier; a valid
   XAUTHORITY path must use the cookie contract; host DISPLAY, inherited host
   XAUTHORITY, malformed/relative/missing authority paths, TCP listeners,
   missing abstract/pathname listener, and a failed no-cookie handshake must
   all refuse admission. Receipts must preserve the selected access model.
8. **Original exception preservation:** inject an authority rejection and a
   separate cleanup failure. Assert `boot_error`/route failure remains the
   authority error, cleanup receipt records its own error and attempts, and a
   second teardown does not duplicate the global cleanup order or replace the
   original route diagnosis. A cleanup-only failure after a successful boot
   should remain cleanup-only.
9. **Historical payload regression:** feed the exact retained DISPLAY-only
   JSON. Assert that the old validator would reject it, while the new mode
   either proves the complete local-socket contract or refuses with a
   specifically labeled access-model error. Do not make a synthetic
   `/private/auth` fixture the only authority test.

These are host-only tests with injected readers/time and do not require a live
Gamescope or game. A later live run should retain the Xwayland PID/argv,
socket inode/peer evidence, process-chain identities, child authority subset,
and cleanup state so that authority and reaper claims are independently
reviewable.

## Sources inspected

* `/home/brunner56/kp-live-20260922/task7-actual-boot-cause.md`
* `/home/brunner56/kp-live-20260922/private-gpu-runs/20260927-081255-56942ef0/gamescope-b12ab845ccbc4a5e9efe224f4d6cc26b.ready.json`
* `/home/brunner56/kp-live-20260922/private-gpu-runs/20260927-081255-56942ef0/gamescope.log`
* `/home/brunner56/kp-live-20260922/private-gpu-runs/20260927-081255-56942ef0/driver.log`, `session.log`, and `creative-run.json`
* current `gamescope_xwayland.py`, `gamescope_processes.py`,
  `display_backends.py`, and `tools/kpharness_gamescope_backend_test.py`
  in `codex/lua-boundary-validation` (the files changed during this audit)
* installed Fedora `gamescope-3.16.25-1.fc44.x86_64`,
  `/usr/share/doc/gamescope/README.md`,
  `/usr/share/man/man1/Xwayland.1.gz`, and
  `/usr/share/man/man1/Xserver.1.gz`

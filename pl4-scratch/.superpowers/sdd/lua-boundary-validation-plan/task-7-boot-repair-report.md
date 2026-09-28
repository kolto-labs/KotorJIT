# Task 7 Gamescope boot repair report

Status: DONE_WITH_CONCERNS — host implementation and regressions complete; independent review and one owned display-only bring-up remain required before any game retry.

Scope: sole writer for the Gamescope lease/process helpers, Gamescope creative-session teardown, focused tests, the appended creative-runner documentation, and this report. No game, Gamescope, Wine, renderer, recorder, or desktop process was launched or signalled. No commits or PRs were created. Unrelated dirty files and the reviewed snapshot/provenance implementation were preserved.

## Diagnosis carried forward

Read `.superpowers/sdd/lua-boundary-validation-plan/task-7-boot-repair-brief.md` and `/home/brunner56/kp-live-20260922/task7-actual-boot-cause.md` before editing. The exact retained payload is exercised as synthetic input, not promoted into historical traceback proof. The original failure remains inferred from that payload and the prior validator. The historical leader's state is not reconstructed by these tests.

## Implementation

- `gamescope_processes.py` supplies process-state reading, twice-read full ancestry validation, and owned Xwayland socket/access verification. DISPLAY-only candidates require the actual owned Xwayland executable, matching display argument or a displayfd selection tied by socket/ancestry evidence, both abstract/pathname listener inodes held in that process's descriptors, no TCP listener descriptors, same-user owned peer ancestry for both pathname and abstract sockets, and successful credential-free X11 setup replies under one absolute two-second deadline. Both process/peer identities and socket inodes are reread after each handshake and retained as nonsecret evidence. Explicit `-ac` is refused. The access model is exactly `owned-endpoint-host-local-no-cookie`, with `xauthority_present=false` and `xauthority_mode=no-cookie-sentinel`. No credentials are sent. Host display aliases are rejected before admission. Cookie-free clients use `/dev/null` as XAUTHORITY to suppress implicit HOME authority lookup. Existing explicit-authority checks are retained.
- `gamescope_xwayland.py` polls the direct Popen leader before adjudicating survivors. Zombie/dead states are not executable survivors. All matching group/session members are considered, including unpublished descendants and ancestry-verified rejected children; an identity anchor is required before signalling. PID/start/group/session changes refuse cleanup. Newly observed unanchored processes do not become trusted on a retry. The lease records its original boot error separately from cleanup attempts and continues retaining preliminary candidate and snapshot evidence.
- The Gamescope class in `creative_wine.py` reraises the original boot exception even if teardown fails. Durable `gamescope-session-cleanup.json` keeps boot error, distinct cleanup failures, canonical component order, and individual retry orders. Completed phases are skipped and duplicate failure strings are not accumulated. A historical session-cleanup failure keeps the run failed even after resources are released.
- `tools/kpharness_gamescope_boot_repair_test.py` adds 16 host-only tests covering S-to-Z direct-child reaping, a live unpublished descendant, recycled leader with a live child, unanchored retry, host-display alias rejection, exact retained DISPLAY-only payload rejection/admission, lease dual error, session dual error and repeated teardown, shared reaper topology versus changed group/session/reused ancestor, and socket/access countercases. Audit additions cover leader-dead/rejected-child-live cleanup, a zombie descendant with a live leader, displayfd compatibility, post-handshake socket/process/peer replacement, foreign UID and abstract peer, explicit access-control disable, and an absolute handshake deadline. Both missing pathname and missing abstract listener ownership are refused before socket creation, as are TCP listeners. Denied setup and foreign peer identity are rejected.
- Existing backend fixtures were corrected to provide deterministic process inventories, remove synthetic process relationships when declaring death, and include the leader identity required by cleanup. Snapshot/provenance regression logic is unchanged.

## Exact validation commands and results

Working directory for all commands:
`/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`

1. `timeout 90s python tools/kpharness_gamescope_backend_test.py` — 35 tests passed (1.777 seconds in the successful run).
2. `timeout 90s python tools/kpharness_gamescope_boot_repair_test.py` — 16 tests passed after authority-audit fixes (see final verification below).
3. `timeout 90s python tools/kpharness_creative_test.py` — 28 tests passed (0.445 seconds). The printed `RuntimeError: cleanup failed: session: RuntimeError: parent cleanup failed` is expected fault-fixture output; suite exits zero.
4. `timeout 90s python tools/kpharness_physical_console_test.py` — 22 tests passed (0.016 seconds).
5. `python -m py_compile scripts/harness/kpharness/gamescope_processes.py scripts/harness/kpharness/gamescope_xwayland.py scripts/harness/kpharness/creative_wine.py tools/kpharness_gamescope_backend_test.py tools/kpharness_gamescope_boot_repair_test.py` — exit zero.
6. `git diff --check` — exit zero.

Earlier bounded backend run failed 3 old fixtures: a relationship remained live after the fixture removed its lease field, one fixture supplied no recorded owner, and the old DISPLAY-only fixture reached the new environment/socket verification without an injected reader. These fixture assumptions were corrected and the suite rerun successfully. The initial repair suite passed 9 tests, then 2 more regression cases were added and the full 11 passed. An initial test resource warning from deliberately failed cleanup was resolved by explicitly releasing its fake process/log after asserting the failure evidence.

## Evidence limits and next gate

The installed package reports `gamescope-3.16.25-1.fc44.x86_64` and links `libwlroots-0.19.so`. The generic wlroots implementation creates/passes local listener descriptors without requiring a published cookie file; see [wlroots Xwayland server source](https://raw.githubusercontent.com/swaywm/wlroots/master/xwayland/server.c). That upstream source is explanatory context, not proof of this installed binary's live topology or access behavior. The implementation therefore measures those facts at admission instead of trusting a version or log line.

The credential-free access model establishes lease-owned local sockets; it does not provide exclusive access against other local users. A deployment with different ancestry, inaccessible `/proc` evidence, authority requirements, or a TCP listener will refuse admission. These tests use injected process/socket state; they establish host logic only. Independent review and a serialized, bounded, owned display-only bring-up must validate actual topology/handshake and complete teardown. No live K1 result is claimed, and the failed historical run is not promoted. A game retry must use a newly verified snapshot incorporating these exact modules after review.

## Authority-audit follow-up

Read and addressed `/home/brunner56/kp-live-20260922/task7-authority-mechanism-audit.md` before freezing. The audit correctly separated owned endpoints from exclusive/private authority. Both transports now receive independent bounded peer checks, post-handshake identity/inode validation, and retained per-transport peer/ancestry evidence. The no-cookie sentinel is explicitly reported rather than counted as an authority file. No authority boundary against other local users is claimed. Rejected children become cleanup anchors only after full PID/start/group/session/ancestry verification while the owner is still identifiable. Unverified group observations remain untrusted across retries.

Final verification after authority-audit changes, using the exact commands above:

- Repair suite: 16 passed in 0.145 seconds.
- Backend suite: 35 passed in 1.743 seconds, including existing snapshot/provenance regressions.
- Creative suite: 28 passed.
- Physical-console suite: 22 passed.
- Focused `py_compile`: exit zero.
- `git diff --check`: exit zero.

Final writer status: DONE_WITH_CONCERNS. Audit requests are implemented and host tests pass. A settled independent code review and actual owned display-only topology/access/teardown validation remain external gates; no game or display launch was performed by this writer.

## Fix round 1 of 5: independent review I1 and I2

Read `/home/brunner56/kp-live-20260922/task7-boot-repair-review.md` and addressed both Important findings. This section supersedes the earlier statement that explicit-authority checks remain supported.

**I1 — explicit XAUTHORITY admission:** chose the review's fail-closed option. A readiness child that publishes any explicit XAUTHORITY cannot be admitted or reach geometry/renderer/game operations. Identity and ancestry verification may still establish its cleanup ownership; that does not admit its display. The refusal is `explicit XAUTHORITY is unsupported without verified owned server authentication`. The separate DISPLAY-only owned-endpoint/host-local/no-cookie mechanism remains available only through its complete socket/process/peer verifier. A future explicit-authority mode must implement server binding, applicable display/address/family record matching, authenticated setup and no-cookie refusal before it can be enabled.

Regression countercases cover an existing empty authority file for a foreign candidate endpoint, a file containing only another display's record, and a symlink alias of the caller's authority. All refuse before display probes. The unrelated-display test record contains zero-length authentication data; no cookie or credential is generated, recorded or exposed. The old backend success fixture now exercises verified no-cookie endpoint admission rather than treating an existing authority file as sufficient.

**I2 — unreadable recorded member:** survivor scans now treat only confirmed disappearance (FileNotFoundError/ProcessLookupError or ENOENT/ESRCH) as absent. KeyError remains the explicit injected mapping-reader missing-entry contract. Permission, malformed-relation and transient I/O errors for a recorded member fail cleanup without signalling it or marking the lease closed. The failure identifies the recorded PID and error class; it is retained as an individual cleanup attempt. Unreadable unrelated `/proc` entries cannot establish ownership.

The regression first reaps the leader while retaining an identity-verified runnable child. PermissionError, malformed-relation RuntimeError and transient I/O OSError each fail without signals. A subsequent readable retry performs exactly one owned SIGTERM cleanup. All three failed attempts and the successful retry remain in the lease receipt. Separate disappearance cases prove confirmed exit still permits cleanup.

Exact commands, run from the worktree after these fixes:

- `timeout 90s python tools/kpharness_gamescope_boot_repair_test.py` — 19 tests passed in 0.192 seconds; exit zero.
- `timeout 90s python tools/kpharness_gamescope_backend_test.py` — 35 tests passed in 1.741 seconds; exit zero.
- `python -m py_compile scripts/harness/kpharness/gamescope_xwayland.py tools/kpharness_gamescope_backend_test.py tools/kpharness_gamescope_boot_repair_test.py` — exit zero.
- `git diff --check` — exit zero.

Round status: DONE_WITH_CONCERNS. Both requested review corrections are implemented and the focused checks pass. A new independent review remains necessary; actual endpoint/installed-topology/teardown proof still requires the separately authorized display-only gate. No live process was launched and no commit was created in this fix round.

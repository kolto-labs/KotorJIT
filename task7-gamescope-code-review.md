# Task 7 Gamescope exact-window backend review

## Verdict

**Spec verdict: FAIL**

**Quality verdict: BLOCKED**

The writer report is candid that this is only a primitive boundary and is not
selected by `creative.py`.  That limit is materially smaller than the supplied
Task 7 implementation brief, which requires the executable Gamescope session,
explicit CLI selection, route-integrated asynchronous failure checks,
recorder-first game/display teardown, schema-2 publication, documentation, and
host-only coverage of the integrated lifecycle.

The useful pieces are real: the FFmpeg argv uses `-window_id`, requested and
encoded cadence are not conflated, Xvfb's existing recorder remains intact,
and PID start identities are attempted.  They are not yet safe to connect.
Several primitive APIs can admit an unrelated authority/lease or produce a
false passing receipt.

## Critical findings

### C1. The backend is not executable through the creative runner

`scripts/harness/kpharness/creative.py:36-41` still accepts only
`linux-wine-k1`, constructs `LinuxWineCreativeSession` plus `X11Recorder`, and
rejects every other identifier.  It still creates schema 1 at `creative.py:168`
and computes success without physical-console correlation or visual acceptance
at `creative.py:252-254`.  `creative_wine.py` contains no Gamescope session,
lease ownership, window-recorder start, or recorder -> game/Wine -> Gamescope
teardown.  The route loop never calls `X11WindowRecorder.check()` before and
after each step.  `docs/creative-runner.md` has no Gamescope backend contract.

Impact: the user-requested command cannot run; no actual run can bind the
lease, renderer, window, physical console, media, and cleanup.  This is the
largest spec failure.  The writer report's “acceptance limit” accurately
discloses it but does not satisfy the implementation brief.

Required fix: add the separately selected Gamescope creative session and
recorder construction, perform capability admission before directory claims,
start recording after the first verified mapped window, consume asynchronous
failure around every route step, stop recorder before game/Wine and lease,
write the complete schema-2 receipt, and document the exact support/refusal
matrix.  Preserve `linux-wine-k1` behavior.

### C2. `schema2_receipt()` can certify mismatched capture evidence

`scripts/harness/kpharness/display_backends.py:212-247` sets `ok=true` from
booleans and `capture.status == "passed"`.  It does not prove that:

* `capabilities.adapter_id == lease.adapter_id`;
* `window.lease_id == lease.lease_id`;
* capture `window_id`, input display, geometry, and `-window_id` command match
  the supplied `OwnedWindow`;
* the recorder's lease is the supplied lease;
* retained media exists and hashes successfully; or
* failure evidence is absent.

The test at `tools/kpharness_gamescope_backend_test.py:149-164` passes an
arbitrary capture dictionary and demonstrates this weakness: changing its
window ID to `0xdead` would still return `ok=true` after `visual_status` becomes
`accepted`.

Impact: a schema-2 receipt can make the central atomic identity claim while its
capture belongs to another window/display/lease.  This is a false-success
boundary, not merely missing metadata.

Required fix: build the receipt from recorder/lease-owned typed snapshots or
validate every cross-component identity and command relationship before
allowing `capture.status=passed` or `ok=true`.  Add negative tests that mutate
each link independently.

### C3. Gamescope readiness accepts an unrelated process and authority

`scripts/harness/kpharness/gamescope_xwayland.py:100-121` accepts any readiness
file whose PID exists with the stated start token.  It does not prove the PID
is the launched child, a descendant of Gamescope, or a member of the recorded
process group/session.  It also accepts any nonempty `XAUTHORITY` path and any
syntactically valid `DISPLAY`; neither is tied to the owned process group or
checked against caller authority.  `is_alive()` at lines 140-150 repeats only
PID/start checks.

Impact: a raced/forged readiness file can redirect X11 enumeration, input, and
capture to a foreign display while the receipt calls it owned.  The generated
UUID makes accidental collision unlikely, but ownership must be proven rather
than inferred from filename unpredictability.

Required fix: record and validate the Gamescope PGID/session identity, verify
the child is in that group and has the expected parent/ancestry, and validate
the published authority as the newly created nested server rather than caller
authority.  Include the verified PGID/child relationship in the immutable
receipt and tests.

### C4. Recorder ownership and finalization contain false-pass paths

`X11WindowRecorder` accepts only `lease_alive: Callable[[], bool]`
(`recording.py:150-158`) and never receives the lease identity.  At start it
therefore cannot enforce `target.lease_id == active_lease.lease_id`; a live
lease callback and an `OwnedWindow` from another lease are accepted.

Separately, `stop()` marks `_stopping` before checking process liveness
(`recording.py:242-263`).  If FFmpeg exits naturally with return code 0 after
the last watcher poll but before `stop()`, `was_live` is false, return code 0 is
accepted, and capture becomes `passed`.  The brief explicitly requires every
early exit, including successful-looking exit 0, to fail.

Impact: capture may target a foreign lease or silently end early while still
being serialized as passed.

Required fix: bind the recorder to a concrete lease ID/identity, validate the
target against it at start and on every poll, and classify any already-exited
process at the beginning of finalization as `recorder_exited` regardless of
return code.  Add direct tests for cross-lease refusal and the exit-0 stop race.

## Important findings

### I1. Environment construction is a denylist, contrary to the authority boundary

`gamescope_xwayland.py:25-33` copies every source variable except two small
denylists; `start()` repeats a different denylist at lines 91-95.  The brief
requires a newly constructed allowlist.  Variables such as portal/session
authority not named in `_DESKTOP_KEYS`, credential-agent sockets, injected
library variables, Python/module variables, and future desktop authority keys
can flow into Gamescope, probes, game, and FFmpeg.

Required fix: define the minimal executable/runtime/game variables explicitly,
then overlay only the child-published nested authority.  Test hostile unknown
variables and representative portal/session/loader variables.  Ensure the
Gamescope launch environment also removes the three forced software-renderer
variables or deliberately admits only required keys.

### I2. PID start parsing is not robust to spaces in `/proc/<pid>/stat` comm

`display_backends.py:160-164` uses `read_text().split()[21]`.  The comm field is
parenthesized and may contain spaces, shifting every subsequent field.  The
existing `session.pid_start()` already parses after the closing parenthesis.

Impact: PID/start identity can be wrong for a valid process name, weakening
window ownership and cleanup checks.

Required fix: reuse the robust parser or parse after the final `)` and add a
fixture whose comm contains spaces and parentheses.

### I3. Lease cleanup can leave the readiness child/process group alive

`GamescopeXwaylandLease.close()` signals the group only while the Gamescope
leader's `Popen.poll()` is `None` (`gamescope_xwayland.py:173-200`).  If the
leader exits but the readiness child or another group member remains, close
does not signal the recorded group.  The code also assumes PGID equals the
leader PID without recording or revalidating PGID.

Impact: failure paths can leak an owned readiness child/Xwayland group and the
receipt cannot prove zero owned processes.

Required fix: record PGID/session identity immediately after launch, enumerate
or otherwise verify owned group liveness independently of the leader, and
clean verified remaining members even after leader exit.  Test leader-dead /
child-live, child-dead / leader-live, timeout escalation, and repeated close.

### I4. Window/input revalidation is incomplete and no production verifier exists

`discover_owned_x11_window()` creates a fresh `OwnedWindow` with a new
`discovered_monotonic` value (`display_backends.py:207-209`).  The recorder
compares full dataclass equality at `recording.py:229-234`, so using discovery
itself as the verifier would report an identity change even when all stable
identity fields match.  No production verifier is implemented or wired.

`OwnedX11Input.from_owned_window()` stores the target but performs no
PID/start/window/lease revalidation before action groups; it only focuses and
sends keys.  Replacement after construction is therefore not detected by this
path.

Required fix: define a verifier that checks stable identity fields while
preserving the original discovery timestamp, share it between recorder and
input, and revalidate before each input action group.  Test replacement, PID
reuse, resize, visibility loss, and query timeout.

### I5. The immutable-record claim is only shallow

`HostFacts.__post_init__()` wraps a shallow dictionary copy
(`display_backends.py:25-43`); nested probe values remain mutable.
`OwnedWindow` does not coerce `capture_capabilities` or `input_capabilities` to
`frozenset`, so callers may supply mutable sets to a frozen dataclass.
`schema2_receipt()` deep-copies capture/cadence/media/display but only shallow
copies cleanup and freshly allocates other pieces.

Required fix: normalize all nested records into immutable typed structures or
deep immutable copies at construction, then deep-copy only at the JSON
boundary.  Add mutation-after-construction tests for every nested field.

### I6. Focused coverage is too narrow and is not registered in CTest

`tools/kpharness_gamescope_backend_test.py` passes 13 tests, but it omits many
mandatory cases: readiness timeout/death/malformed authority; child/PGID
ownership; GNOME-Wayland and KDE-X11 variants; cross-lease target; PID reuse;
visibility/query timeout; lease death; stop-time exit-0 race; boot-error and
double-teardown ordering; partial media; route pre/post failure checks; and
schema cross-identity mismatches.

The file is not registered in `CMakeLists.txt`; the reported CTest invocation
ran only `kpharness_creative_test`, which contains no Gamescope assertions.

Required fix: add the missing host-only cases and register the focused gate or
fold it into the existing creative test as the implementation brief requested.

## Exact-window and Xvfb observations

The new FFmpeg argument array at `recording.py:181-185` correctly contains the
actual target geometry, `-window_id <target.window_id>`, and the target display.
It does not shell-concatenate arguments.  This part passes static review once
cross-lease binding is added.

The existing `X11Recorder` root-capture implementation remains unchanged, and
the existing creative tests passed.  This is evidence that the software path
was not mechanically broken by the primitive additions.  Because there is no
Gamescope session integration, recorder-first cross-backend teardown and CLI
compatibility are not yet testable.

## Validation run by reviewer

* `python3 tools/kpharness_gamescope_backend_test.py`: **13/13 PASS**.
* `python3 tools/kpharness_creative_test.py`: **28/28 PASS**.
* `python3 -m py_compile` for `display_backends.py`,
  `gamescope_xwayland.py`, `recording.py`, `session.py`, and `owned_x11.py`:
  **PASS**.
* No game, Wine, Xvfb, Gamescope, or real FFmpeg process was launched.

These results establish syntax and the assertions currently encoded.  They do
not close the Critical or Important findings above.

## Acceptance state

* Xvfb regression gate: **PASS, 28/28 host tests**.
* Gamescope primitive host gate: **PASS, 13/13 host tests**.
* Gamescope executable creative backend: **not implemented**.
* Schema-2 atomic evidence chain: **not established**.
* Live installed-K1 GPU/physical-console/media acceptance: **not run**.
* Accepted support cell: **none added by this change**.
* Refused/unimplemented cells remain: native/shared Wayland, Windows, macOS,
  ChromeOS, K2, GNOME-specific live acceptance, and KDE-specific live
  acceptance.

The change is not review-clean until the four Critical and six Important
findings are fixed and scoped re-review passes.

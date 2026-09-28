# Browser A1 root-fix review

## Verdict

**PASS for the reviewed host and source boundary, with one publication
limitation recorded below.** The current bridge and browser client reject
replay after upstream loss, bind mutations to the explicit runtime/session/
request handle, preserve native protocol identities and bytes, and publish
only the two files named by the checked-in `web/devtools/MANIFEST`. The review
does not claim attached live-game proof: `--attach` remains explicitly
unsupported and the native receipts are host/protocol evidence.

## Claims

claim: queued calls do not replay after upstream loss.

referent: `Bridge.forward` serializes calls under `_lock`, sets `_lost` on
`ChannelTimeout`/`ChannelClosed`, closes the channel, and checks `_lost` again
before sending a queued call (`scripts/harness/kpharness/devtools_bridge.py:61-91`).

checked: `python3 -m unittest tools.kpharness_devtools_bridge_test.BridgeUnitTest.test_queued_calls_never_send_after_upstream_loss tools.kpharness_devtools_bridge_test.BridgeUnitTest.test_timeout_closes_and_never_replays`

verdict: holds

confidence: high; both tests passed and the fake channel observed one upstream
call for two concurrent callers.

claim: native id-less connection refusals are preserved as errors and do not
become fabricated request responses.

referent: `src/harness/channel.cpp:91` emits the native busy line without an
`id`. `StandaloneChannel._read_frame` in
`scripts/harness/kpharness/devtools_bridge.py:38-46` recognizes an id-less
`ok:false` error, closes the channel, and raises `ChannelClosed` with the
native message. Startup wraps that as `upstream unavailable` at `:261`.

checked: `python3 -m unittest tools.kpharness_devtools_bridge_test.BridgeSubprocessTest.test_busy_startup_exits_before_serving tools.kpharness_devtools_bridge_test.BridgeSubprocessTest.test_upstream_tcp_drop_is_not_replayed` — both passed. The busy fixture now uses the exact native id-less line
`{"ok":false,"error":"busy: another client is connected"}`.

verdict: holds

confidence: high; this is a narrow source/fixture check and does not alter the
native wire semantics for accepted requests.

claim: browser mutations cannot retarget a request through a global or stale
identity.

referent: `web/devtools/kotor-console.mjs:43-50` requires
`cancel({runtime, session, request})` and canonical nonzero session/request
strings; `evaluate` captures a baseline and sends that same full identity for
submit, outcome, and output (`:61-104`). Every response is required to carry
the accepted runtime (`:23-30`).

checked: `node --test web/devtools/kotor-console.test.mjs`; the 8 tests passed,
including `cancel retains the accepted request owner across baseline changes`,
`stale outcome rejects without replay`, `wrong outcome identity and hung fetch
are failures without replay`, and canonical/overflow identity rejection.

verdict: holds

confidence: high; the native cancel/complete protocol intentionally omits
session/request fields in their replies, so the browser checks the runtime and
returns the explicit native status rather than inventing a reply identity.

claim: native protocol identity and value boundaries are lossless and fail
closed.

referent: `src/harness/console_protocol.cpp:178-333` emits a stable 64-hex
runtime identity, canonical decimal uint64 fields, explicit StaleRuntime and
StaleSession states, base64 byte objects, typed NaN/infinity/negative-zero,
bounded source/prefix handling, and explicit terminal/cancel statuses. The
actual Lua/serialization/lifecycle/bounds receipt is
`/tmp/kp-browser-native-console.log`.

checked: `/tmp/kp-browser-native-console.log` contains
`PASS console protocol actual Lua/serialization/lifecycle/bounds`; the focused
Python host run below also passed all bridge and physical-console checks.

verdict: holds

confidence: high; the receipt is from the checked native protocol harness, and
the Python protocol consumer independently rejects stale runtime/session,
wrong outcome request, missing terminal state, dropped output, and replay.

claim: the publication checker serves and stages only trusted web files.

referent: `web/devtools/MANIFEST` contains exactly `index.html` and
`kotor-console.mjs`. `Bridge.static` resolves a decoded URL, refuses traversal,
loads only a manifest member, and requires the resolved parent/name to remain
inside `WEB_ROOT` (`scripts/harness/kpharness/devtools_bridge.py:113-129`).
`validate_publication` rejects root/file symlinks and requires the staged file
set to equal the source manifest (`:131-138`).

checked: `python3 -m unittest tools.kpharness_devtools_bridge_test.BridgeUnitTest.test_publication_exact_staged_files tools.kpharness_devtools_bridge_test.BridgeUnitTest.test_queue_bound_and_manifest_allowlist tools.kpharness_devtools_bridge_test.BridgeSubprocessTest.test_page_bootstrap_and_manifest`

verdict: holds

confidence: high for the checked file-set and traversal boundary; the tests
passed and reject `leak.bif`, `leak.tga`, missing files, and symlinked files.

claim: this proves an attached browser-to-live-game console route.

referent: `scripts/harness/kpharness/devtools_bridge.py:267-270` exits with
`attach unsupported: playback owner has no devtools forwarding API`.

checked: source inspection and the bridge startup path; no live/game/Wine
launch was used.

verdict: does not hold

confidence: high; A1 is a standalone authenticated loopback bridge and native
protocol check. Attached-owner acceptance requires a separate owner forwarding
API and live receipt.

## Focused receipts

```text
python3 -m unittest tools.kpharness_devtools_bridge_test tools.kpharness_physical_console_test -v
Ran 34 tests in 1.028s
OK

node --test web/devtools/kotor-console.test.mjs
8 tests passed, 0 failed
```

The provided native receipts also pass:

```text
/tmp/kp-browser-native-console.log: PASS console protocol actual Lua/serialization/lifecycle/bounds
/tmp/kp-browser-native-harness.log: all listed harness checks PASS
```

## Would change / unresolved

`validate_publication` compares a staged directory with the live source
`WEB_ROOT/MANIFEST`; it does not hash or copy the manifest into the staged
publication. This is a future release-hardening consideration, not an A1
blocker under the current publication contract: the checked-in allowlist and
the staged file set are exact, and the existing tests cover the current gate.
If a later release contract requires immutable publication provenance, the
single settling check is a manifest-digest field in the publication receipt,
followed by a changed-source-manifest test.

## Grill me

1. Why accept cancel when its response omits session/request? The native
   protocol contract intentionally returns only the status for cancel; the
   request was already bound by the explicit triple, and the browser requires
   the runtime on the response. Native `kp_consoleprotocoltest` covers exact
   queued cancellation and terminal cancellation.
2. Could a stale completion be mistaken for success? No: native completion
   returns `StaleSession`, while the browser returns that status with no names;
   the caller cannot receive a `Found` completion from that path. The native
   dispatch check is at `src/harness/console_protocol.cpp:277-290`.
3. Is the publication checker live-asset proof? No. It checks the exact web
   file set and symlink/traversal boundary only; attached owner/live-game proof
   remains unresolved by design.

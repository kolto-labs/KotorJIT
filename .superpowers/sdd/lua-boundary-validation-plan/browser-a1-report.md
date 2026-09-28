# Browser A1 report — authenticated devtools bridge

Date: 2026-09-28

Scope was limited to the Browser/WASM A1 transport slice. No game, Wine,
Gamescope, FFmpeg, native console semantics, or live process was touched.
The Pioneer playback owner was inspected first; `playback.py` exposes no
devtools forwarding or attach API, so the bridge is standalone-only for now
and reports attach as explicitly unsupported. No owner changes were made.

## Implemented candidate

- `scripts/harness/kpharness/devtools_bridge.py`: stdlib HTTP bridge,
  loopback-only binding, private 256-bit token file, exact Host/Origin checks,
  bearer auth for POST, manifest-only static files, six-op allowlist,
  transport-reserved field rejection, bounded in-flight slots, and upstream
  timeout/disconnect invalidation without replay.
- `web/devtools/index.html`, `kotor-console.mjs`, `MANIFEST`: dependency-free
  page and `window.kotor.lua.evaluate()` client.
- Additive CLI command: `kpharness devtools-bridge --standalone --port PORT`
  plus explicit unsupported `--attach OWNER` mode.
- Additive protocol and console documentation.
- `tools/kpharness_devtools_bridge_test.py`: host-only unit coverage for auth,
  origin, allowlisted forwarding, request limits and page bootstrap.

The playback owner remains the only future attach owner. Until it publishes a
forwarding API, standalone mode owns one Channel directly and exits on a busy
engine; it never opens a second connection or retries a mutation.

## Claim blocks

claim: The bridge accepts only the six existing `kp.console.v1` operations and
cannot forward another harness command.
referent: `devtools_bridge.py:24-26,73-91`; `Bridge.forward` forces
`protocol=kp.console.v1`, rejects non-`devtools` commands, checks the string op
against `status/submit/outcome/output/complete/cancel`, and rejects reserved
transport fields.
checked: source inspection; no full test run in this wave because the host
entered severe I/O pressure and root is taking bounded test ownership.
verdict: holds
confidence: medium; a fake TCP subprocess test would raise this to high.

claim: Static page bootstrap does not require a token, while POST API calls do.
referent: `devtools_bridge.py:125-145`; `_guard` always checks canonical Host,
checks Origin and bearer auth only for POST; `do_GET` serves only MANIFEST files.
checked: source inspection after correcting the initial auth-on-GET defect.
verdict: holds
confidence: medium; navigation test is present but not executed after the
host I/O stall.

claim: The JS client uses the native identity-aware wire contract.
referent: `web/devtools/kotor-console.mjs:13-48`; it captures status first,
passes runtime/session to submit and subsequent operations, uses the baseline
last_line as the output cursor, rejects stale/expired/unavailable responses,
and decodes native `String.bytes` objects while filtering output by both
session and request.
checked: source inspection against `docs/devtools-protocol.md` and the native
schema described in `src/harness/console_protocol.cpp`.
verdict: holds
confidence: medium; Node transcript tests are still required.

claim: Playback attach is available.
referent: `scripts/harness/kpharness/playback.py` has owner lifecycle/control
operations but no devtools forwarding method or endpoint.
checked: source inspection.
verdict: does not hold
confidence: high; the bridge therefore refuses attach explicitly rather than
opening a competing Channel.

claim: This slice proves browser/WASM gameplay support.
referent: `fanout-browser-wasm-plan.md:1-20, §3`; A1 only advances the
shared-pipeline audit row. Browser/WASM capability cells remain not attempted.
checked: plan and directive audit read.
verdict: does not hold
confidence: high.

## Evidence and remaining gates

The first test shell (`python3 -m py_compile ... && python3
tools/kpharness_devtools_bridge_test.py`) became stuck in uninterruptible I/O;
its parent was stopped, but the D-state child was not killable at the time.
After the host recovered, I reran bounded tests with
`PYTHONDONTWRITEBYTECODE=1`, `PYTHONPATH=.`, and a 60-second timeout per run:

```text
python3 tools/kpharness_devtools_bridge_test.py: 7 tests, OK, rc=0
node --test web/devtools/kotor-console.test.mjs: 4 tests, 4 pass, rc=0
```

The Python suite launches the bridge as a subprocess against a real synthetic
loopback TCP harness and verifies page bootstrap, manifest traversal rejection,
auth/origin/path/reserved-field rejection before upstream, exact protocol and
large decimal IDs, native byte objects, identity propagation and Requested
cancellation. The Node suite verifies the transcript client preserves
String.bytes, filters by session/request and rejects StaleSession without
replay. The Python unit additions also prove timeout closure with no replay,
queue saturation through concurrent public `forward` calls, token-file mode
and page non-leakage, manifest publication failure with a planted `.bif`, and
busy startup refusal through the real subprocess handshake. The Node
transcript suite covers wrong outcome identity, hung-fetch aborts, a
nonterminal `Requested` outcome followed by a terminal failure, and native
error byte retention.

These are host proofs only. Live cross-client F12/browser proof remains a
separate canonical-lock gate and cannot be inferred from this candidate.

## Grill me

1. **Weakest answer: why is there no attach implementation?** The inspected
   playback owner has no devtools forwarding API. Opening another Channel would
   violate the single-owner rule, so attach is rejected with an explicit
   unsupported message until that API exists.
2. **How does the page load before the token is entered?** GET is authenticated
   only by exact canonical Host; POST alone requires exact Origin plus bearer
   token. Static paths still go through MANIFEST and traversal checks.
3. **Can a timeout be retried automatically?** No. A Channel timeout or close
   closes the upstream Channel and returns `upstream_lost`; no request is
   replayed.
4. **What remains unproven?** The fake TCP and Node suites, native browser
   delivery behavior, and live F12/browser same-session proof. None is claimed
   here.

Open question: what stable devtools-forwarding method will Pioneer Stage 0/6
publish for the single playback owner? The answer must include owner identity,
request serialization, timeout invalidation, and the same wire receipts before
attach can be enabled.

## Root independent review and repair

The earlier candidate was not accepted as-is. Root reproduced a queued-call-after-timeout defect (2 upstream calls instead of 1) and a wrong-runtime submit accepted as successful, then fixed both with red-to-green tests. A separate reviewer reproduced cancellation retargeting through global session identity. The final API requires an explicit `{runtime, session, request}` handle; no global identity is used to choose a cancel target.

The final host receipts are 12 Python bridge tests, 8 Node protocol-client tests, 22 physical-console tests, native `kp_harnesstest` zero failures, and native `kp_consoleprotocoltest` PASS. The native targets were rebuilt from current source. Tests cover actual fake-TCP disconnect with one mutation sent, queued loss, 16-call saturation, startup busy, authorization/Origin/Host/op/body bounds, uint64/binary fidelity, cancellation remaining nonterminal, source JSON escaping, and exact staged publication including planted `.bif`/`.tga` and symlink refusal. The production publication CLI passed a clean two-file stage and refused a planted `.tga`.

Durable logs, red receipts, current source hashes, and publication CLI output: `/home/brunner56/kp-live-20260922/browser-a1-root-verification/`. Independent review: `/home/brunner56/kp-live-20260922/browser-a1-root-fixes-review.md`.

Verdict: A1 host slice PASS. No actual browser UI, physical F12 cross-client live route, attached-owner transport, or playable browser/WASM proof is claimed. The native H0 tests use the offline executor callback; the game runtime was not launched.

Grill me: Why is cancel stricter? Request numbers are session-scoped, and the recorded global-identity race targeted a different session. Explicit triple handles avoid retargeting without a historical cache. Why does the HTTP body cap exceed16KiB? Native SourceLimit applies after JSON decoding; a legal source byte can use six JSON bytes. What is unverified? The actual attached live F12/browser route; it requires the owner API and a separately authorized live run.

Final narrow follow-up: the startup test now uses the actual native ID-less `busy: another client is connected` frame. Root observed the old client discard that message, added `StandaloneChannel` connection-refusal handling, and verified red-to-green. The independent reviewer reran busy/drop tests and accepted the fix. Python transport keyword `self` is refused before forwarding. Publication-only CLI validation no longer creates/chmods the runtime token directory. The durable source hashes and12-test receipt were refreshed.

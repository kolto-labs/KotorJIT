# Browser A1 HTTP security boundary review

Date: 2026-09-28. Source-only review of the current browser bridge against
`fanout-browser-wasm-plan.md` §4.5. No server, game, Wine, browser, or network
launch was performed.

claim: the bridge enforces loopback binding, canonical Host/Origin, bearer
token authentication, bounded bodies, and a strict console operation set.

referent: `scripts/harness/kpharness/devtools_bridge.py:121-171` rejects any
listen address other than `127.0.0.1`, requires exact Host for all requests,
requires exact Origin and `Authorization: Bearer <token>` for POST, and
`Bridge.forward()` at `:57-91` allows only the six `kp.console.v1` operations.
`MAX_BODY` is enforced at `:190-202` before JSON/upstream work.

checked: direct source read against plan §4.4-§4.5.

verdict: holds
confidence: high for the static boundary; runtime test evidence is pending.

claim: static file serving is constrained to the manifest and does not follow
symlinks outside the web root.

referent: `Bridge.static()` at `:92-119` URL-decodes the path, rejects `..`,
requires an exact `MANIFEST` entry, resolves the path, and requires
`path.parent == self.web_root`.

checked: source read. No filesystem mutation or HTTP request was issued.

verdict: holds
confidence: medium-high; a test should still cover encoded traversal and a
symlink planted in a temporary web root.

claim: the current source does not yet satisfy the full A1 acceptance boundary.

referent: the plan requires an attach mode, bridge subprocess tests, token
non-disclosure checks, upstream-drop/no-replay checks, and publish-manifest
verification. Current `main()` explicitly exits with
`attach unsupported: playback owner has no devtools forwarding API` at
`:245-247`; no `tools/kpharness_devtools_bridge_test.py` or JS client test was
present in the reviewed source listing.

checked: source and plan comparison; no test execution.

verdict: does not hold for full A1 acceptance
confidence: high; this is a scope/completion finding, not a claim that the
standalone static checks are unsafe.

claim: one security behavior remains an implementation question: malformed
JSON is rejected but the HTTP connection is kept alive by the standard
`BaseHTTPRequestHandler` path.

referent: `do_POST()` catches parse errors at `:203-211`, replies 400, and
returns without setting `Connection: close`; the plan's H0 cross-protocol
concern applies to the native harness, while this HTTP bridge has already
consumed one Content-Length-delimited request body.

checked: source read only.

verdict: unresolved
confidence: medium; settle with a test sending malformed JSON followed by a
valid request and verify the bridge's intended keep-alive behavior, plus a
request with duplicate/conflicting Content-Length headers if the HTTP server
layer is in scope.

## Verdict

The standalone bridge's static loopback, origin, token, body-size, operation,
and manifest checks hold. Full Browser A1 is **BLOCKED pending implementation
and tests**, chiefly the unsupported owner attach path and absent required
bridge/JS acceptance suites. No live or browser security proof is claimed.

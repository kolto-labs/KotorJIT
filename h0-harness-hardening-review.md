# H0 independent security review — control-port hardening

Date: 2026-09-27. Reviewed worktree:
`/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`.

This was a read-only review of the worktree. I made no worktree edit, did not
run Wine/a game/a display server, and did not touch the live-game lock. Probe
sources and binaries are under the permitted
`/home/brunner56/kp-live-20260922/review-probes-h0/` directory.

## Scope and method

I independently read H0 in
`/home/brunner56/kp-live-20260922/fanout-browser-wasm-plan.md` §4.1, then
examined the changed channel and drain code before reading the implementation
report. I verified the current source hashes against the prior real-drain
probe's saved hashes, reran that probe through `host-cmd`, and wrote a small
separate Channel-level reproduction for the reply property.

Current H0-related worktree diff count (`git diff --numstat --` the four named
files): `channel.cpp` +34, `channel.hpp` +38, `commands.cpp` +36/-5, and
`kp_harnesstest.cpp` +346/-6. The review does **not** make a claim about a
whole-worktree status; constrained Git commands were used because the mounted
worktree is heavily loaded.

## Result

The request-intake half is substantially correct and the real drain path
passes its hostile-input checks. H0 nevertheless fails its stated reply
property: **a reply queued after a client generation is condemned is still
sent to that condemned client.** This is observable on the current objects,
not merely a theoretical race.

`Channel::push_reply()` filters only `client != 0 && client ==
current_client()` (`src/harness/channel.cpp:267-278`). It does not use
`admit()`, which additionally rejects `condemned_gen_`. The listener then
pulls all replies for the current generation (`channel.cpp:354-365`) before
the `doomed` branch does its one send and closes (`channel.cpp:367-377`).
Consequently, an event from `stream_events()` after `drain()` calls
`condemn()`, or an async completion from `after_frame()`, can be appended to
the bad-request error and delivered.

The production paths exist: `drain()` calls `stream_events(*ch)` after
`ch->condemn(condemned)` (`commands.cpp:1486-1489`); `stream_events()` calls
`push_reply()` (`commands.cpp:1309-1332`); and async completion paths do the
same at `commands.cpp:1516,1536,1555,1577,1597,1632`.

### Reproduction

I compiled the 32-bit public-API probe against the same existing current
`channel.o` that the real-drain probe uses:

```sh
host-cmd sh -c 'g++ -m32 -std=c++17 -pthread -Isrc \
  review-probes-h0/condemned_reply_probe.cpp review-probes-h0/obj/channel.o \
  review-probes-h0/obj/platform.o review-probes-h0/obj/platform_linux.o \
  -o review-probes-h0/condemned_reply_probe && \
  review-probes-h0/condemned_reply_probe'
```

The probe connects, queues `{"error":"first"}`, calls `condemn(gen)`, then
queues `{"secret":"post-condemn reply"}`. Its actual received payload was:

```text
generation=1 bytes=50 payload={"error":"first"}
{"secret":"post-condemn reply"}
```

It intentionally returns exit 1 when the forbidden marker is observed. This
is sufficient to disprove “replies to condemned clients are dropped.”

### Required correction and regression

The minimal correction is to make `Channel::push_reply()` reject a condemned
generation, for example `if (!admit(client)) return;`, rather than checking
only `current_client()`. The drain already queues the one error reply before
calling `condemn()` (`commands.cpp:1486-1487`), so that error remains
deliverable. Add a direct Channel regression that queues an error, condemns,
attempts a later reply, and asserts the client receives only the error and
EOF. A real-commands test should also subscribe, create a ring event, send a
bad line, and assert no event frame follows the error.

This needs re-review after the correction; it is not authorized by this
read-only assignment and was not changed here.

## What verified

- `src/harness/channel.hpp:92-103` gives `admit()` the intended current
  generation plus not-condemned rule, and `commands.cpp:1467-1487` consults
  it for every request in the real drain.
- A one-client, eight-per-tick batch makes the local `condemned` marker enough
  to skip the rest of the current batch; persistent `condemned_gen_` makes
  later batches reject the same generation. `close_client()` clears queued
  requests and replies (`channel.cpp:235-253`).
- New accepted clients get `next_gen_++` (`channel.cpp:429-440`), and an old
  condemnation does not equal the new current generation. That is the desired
  fresh, unpoisoned generation model.
- The `screen_request_line()` byte screen is intentionally conservative:
  after space/tab/CR it permits only `{` (`channel.cpp:106-118`). It therefore
  rejects HTTP request lines, headers, HTTP/2 preface, WebSocket upgrade,
  BOM-prefixed JSON, whitespace-only lines, and non-object JSON before
  parsing. CRLF JSON and leading ordinary whitespace still work because the
  splitter removes a terminal CR (`channel.cpp:463-479`).
- A line above 1 MiB triggers the listener's bounded close (`channel.cpp:489-
  494`) and cannot be truncated into a parsed request. Queued request/reply
  ceilings are also present.

## Re-run real drain evidence

I reran the already-built, scratch-only `drain_probe` through the required
host wrapper. It links the real current `commands.cpp` drain/`execute_line()`
with engine calls stubbed and uses a real loopback socket.

```sh
host-cmd sh -c 'timeout 45s review-probes-h0/drain_probe \
  > review-probes-h0/resume-real-drain.txt 2>&1'
```

Exit was 0: **94 PASS, 0 FAIL**. It exercised plain and `kp.console.v1`
browser POST bodies in one write; deterministic parked cross-batch bodies;
malformed and non-object JSON; BOM/whitespace; CRLF; deep input; WebSocket
upgrade; HTTP/2 preface; pipelined POSTs; stale requests after client A leaves
and B connects; fresh client behavior; long and overlong lines; and a
256-KiB post-request-line RST probe. In particular, both cross-batch variants
reported `body in batch 2 ... is not executed`, and the stale-A case reported
only the in-flight request ran.

That passing test does not cover the finding: its cases do not create a reply
after calling `condemn()` while the generation remains current.

## K2 preservation check

The pre-H0 snapshots available in `/tmp/h0base` show the only current changes
relative to those snapshots are H0 drain changes at `commands.cpp` around
1242/1264/1460 and harness-test changes. In particular, the previously dirty
K2 protocol dispatch in `cmd_devtools` and the K2 phase/load-completion test
hunks were already in those snapshots and are byte-preserved. Current source
hashes match the real-drain probe's saved `sources.sha256` for all four named
files, so the rerun tested the reviewed source revision.

## Token and Lua `os`/`io` assessment

A per-session token is worthwhile defense in depth but is not a replacement
for H0. The current raw port is unauthenticated and no harness token setting
was found in `src`, `scripts`, `tools`, or `docs` by the scoped search. An
env-only secret is weak for same-UID attackers because `/proc/<pid>/environ`
and inherited child environments can expose it. If pursued separately, use a
256-bit token in a 0600 user-private file, constant-time compare, first-line
hello protocol, mandatory re-handshake after reconnect, and ensure it is not
logged or placed in a URL. It expands the compatibility surface and must be
reviewed with all drivers/fakes.

Removing `os`/`io` from the console alone does not secure the raw harness:
`cmd_lua` invokes the full harness Lua state (`commands.cpp:732-743`), and
that state calls `luaL_openlibs` (`commands.cpp:239-249`); script hosts do so
too (`src/lua/host.cpp:124-126`). The devtools Console also calls
`luaL_openlibs` (`src/devtools/console.cpp:374-387`) and retains `io_ref_` for
its output-routing code (`console.cpp:433-457`), so removing all `io` would
break it. A console-only removal of direct process-spawn primitives could
reduce blast radius, but it cannot cure the raw port and is outside H0.

## Claim blocks

claim: Remaining and cross-batch requests from a condemned generation do not execute.
referent: `commands.cpp:1467-1487`; `review-probes-h0/resume-real-drain.txt`, 94 PASS/0 FAIL, including parked cross-batch cases.
checked: `host-cmd sh -c 'timeout 45s .../drain_probe'`
verdict: holds
confidence: high for the reviewed current source and stubbed real drain; a live-game run was intentionally out of scope.

claim: A stale batch from a disconnected client does not execute, and a new connection is a fresh generation.
referent: `channel.cpp:235-253,429-440`; real-drain probe stale-A-to-B and fresh-client cases.
checked: same 94-pass run
verdict: holds
confidence: high; would change with a different channel generation implementation.

claim: Replies to condemned clients are dropped.
referent: none; counterexample payload from `review-probes-h0/condemned_reply_probe` contains `post-condemn reply` after `condemn(gen)`.
checked: 32-bit Channel API probe against current `obj/channel.o`; exit 1 is the expected proof-of-failure result.
verdict: does not hold
confidence: high; would change if `push_reply()` uses the not-condemned admission rule and a regression proves it.

claim: The uncommitted K2 load-completion hunks in commands.cpp and kp_harnesstest.cpp are unchanged.
referent: `/tmp/h0base/{commands.cpp,kp_harnesstest.cpp}.orig` versus current constrained diffs; only H0 regions differ.
checked: `diff -u` against the pre-H0 snapshots and current SHA-256 comparison to `sources.sha256`.
verdict: holds
confidence: high for those snapshots/current files; no whole-worktree rewrite was attempted.

## H0 verdict: FAIL

The intake/drain exploit is blocked in the reviewed cases, but H0 explicitly
requires condemned-client replies to be dropped. The current post-condemn
reply delivery is a concrete security/correctness failure and must be fixed
and regression-tested before a PASS is justified.

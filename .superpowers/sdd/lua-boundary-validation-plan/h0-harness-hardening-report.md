# H0: harness control-port hardening report

Date: 2026-09-27. Worktree: `.worktrees/lua-boundary-validation`. No commit, stash, staging, Wine or game.
Plan: `/home/brunner56/kp-live-20260922/fanout-browser-wasm-plan.md` §4.1.

## What changed

Mechanism: the main thread condemns a client generation, the drain skips it, and the listener closes it.

- `src/harness/channel.hpp:55-56`, `channel.cpp:106`: `screen_request_line()` is a byte screen, not a parse. A line whose first non-whitespace byte is not `{` fails. `Http` (method token, `HTTP/1.`, `HTTP/2`) only words the reply.
- `channel.hpp:92` `admit(client)`: true only when `client == current_client()` and the client is not condemned. This also closes the stale-generation execution gap.
- `channel.hpp:101` `condemn(client)` sets `condemned_gen_` (`channel.hpp:159`). Generations only grow, so one slot is enough.
- `channel.cpp:348` reads the condemned flag *before* the reply pull. `channel.cpp:371` then makes one non-blocking send of the queued replies (the error line) and calls `close_client()`. Only the listener closes sockets, same as `overflow_`.
- `commands.cpp:1249-1278` `execute_line(..., bool& condemn)`: condemn on a failed screen, a parse failure or a non-object. A JSON object without `cmd` is still answered and does not condemn.
- `commands.cpp:1466-1487` `drain()`: skip `rq.client == condemned || !ch->admit(rq.client)`. Condemned stays local until the batch's replies are pushed, then `ch->condemn()`. So the error reply is queued before the listener can close (fixes the reply/close race). Poison refusals skip the condemned client.
- One-client semantics are unchanged: busy refusal, generations and ceilings are untouched.

## Tests (`tools/kp_harnesstest.cpp`)

- New `cross_protocol_cases()` at `:586` with its own `Channel`, over a real loopback socket.
  - `hard_executor` (`:487`) mirrors `execute_line`, using the same `screen_request_line` plus parse/object check. It counts `cmd=="devtools"` as the stand-in for console `status.submitted`, the side effect a browser body line is after.
  - `hard_pump` (`:514`) mirrors the new `drain()` shape.
- (a) The full `POST / HTTP/1.1` + headers + blank + devtools submit body goes in ONE `send`. Asserts:
  - exactly one error reply, and it is not `busy`;
  - EOF follows;
  - the devtools counter is unchanged;
  - a replayed POST on a new connection is condemned again;
  - a fresh JSON client afterwards is served and stays open.
- (a2) (`:707-744`) covers a real browser POST, which carries a dozen or more headers. The drain takes `kMaxPerTick = 8` per frame (`commands.hpp:45`), so the body lands in a later batch. The test sends a 13-line POST (request line, 11 headers, body) in one send and waits for 13 queued. It takes two batches (8+5) and runs batch 1, which condemns. Batch 2 must run 0 devtools lines. This proves that the condemnation outlives the batch that raised it.
- (b) `{bad json\n` plus a valid devtools line in one send: one error reply, EOF, and the valid line is not dispatched.
- (c) Three devtools lines are taken into a batch by the "drain". The client closes and a new client connects before the batch executes. Asserts 0 of 3 executed.
- (d) Valid traffic is unchanged: 3 lines in one send (with leading whitespace, CRLF, and Lua code containing `POST / HTTP/1.1`) plus one more. All four are answered in order, the devtools line is dispatched, and the connection stays up.
- There is also a pure screen check (the first line of the section).
- Existing `channel_cases`: the old assertions "malformed line gets an error reply" and "connection survives the malformed line" encoded the behaviour this task removes. The bad-json step moved to (b), and that check became "second request on the same connection answered" (`:401`). The shared `pump` now calls `ch.admit()` (`:280`), as the real drain does.

### Red (pre-fix channel.cpp/commands.cpp, pump shaped like the old drain), 3 identical runs, `8 failure(s)`

```
== cross-protocol lines ==
  [FAIL] (a) HTTP POST gets exactly one error reply
  [FAIL] (a) HTTP POST connection is closed after the error
  [FAIL] (a) the POST body line is never dispatched
  [FAIL] (a) a replayed POST on a new connection is condemned again
  [PASS] (a) a fresh JSON client after the POST is served and kept
    post1: 4 line(s), eof=0; post2: 4 line(s), eof=0
  [FAIL] (b) malformed line gets one error reply
    (b) line: {"id":null,"ok":false,"error":"json: expected string at offset 1"}
    (b) line: {"id":2,"ok":true,"result":{"cmd":"devtools"}}
  [FAIL] (b) malformed line closes the connection
  [FAIL] (b) the valid line behind a malformed one is not dispatched
  [PASS] (c) three requests were taken before the client left
  [FAIL] (c) a batch from a client that has gone is not executed
    stale batch executed: 3 of 3
  [PASS] (d) valid lines, one send, all answered in order
  [PASS] (d) a devtools line that mentions HTTP/1.1 in its code is still dispatched
  [PASS] (d) the connection stays up after valid traffic

== phase classifier ==
```

Red total: 123 PASS / 8 FAIL. Test (a) fails on current code as required. On old code, post1 got 4 lines and no EOF: 3 header errors, then the body line **executed**.

### Red, second shape: new channel.cpp, drain glue removed

(a2) was added after the first red run. To prove that it, and the drain glue generally, is load-bearing, `/tmp/h0_oldpump_test.cpp` is the current test file with `hard_pump`'s admit/skip/condemn lines removed (the old drain shape). It was compiled against the *new* `channel.cpp` with `g++ -std=c++20 -m32 -Isrc ... -pthread`. Result, 3 of 3 runs: `9 failure(s)`, with the FAIL lines below. (a2) shows `later batch executed: 1; lines queued 13, batches 8+5`.

```
  [FAIL] (a) HTTP POST gets exactly one error reply
  [FAIL] (a) HTTP POST connection is closed after the error
  [FAIL] (a) the POST body line is never dispatched
  [FAIL] (a) a replayed POST on a new connection is condemned again
  [FAIL] (b) malformed line gets one error reply
  [FAIL] (b) malformed line closes the connection
  [FAIL] (b) the valid line behind a malformed one is not dispatched
  [FAIL] (c) a batch from a client that has gone is not executed
  [FAIL] (a2) the body in the next batch of a condemned client is not dispatched
```

This shows that the listener half alone does not protect anything. The drain's condemn and admit calls are what close the hole, which is why residual 1 matters.

### Green (after the fix), final binary 8 of 8 runs `0 failure(s)`, 133 PASS (the output below predates (a2); (a2) prints `later batch executed: 0; lines queued 13, batches 8+5`)

```
== cross-protocol lines ==
  [PASS] line screen: only a line that opens an object passes; HTTP is named
  [PASS] (a) HTTP POST gets exactly one error reply
  [PASS] (a) HTTP POST connection is closed after the error
  [PASS] (a) the POST body line is never dispatched
  [PASS] (a) a replayed POST on a new connection is condemned again
  [PASS] (a) a fresh JSON client after the POST is served and kept
    post1: 1 line(s), eof=1; post2: 1 line(s), eof=1
  [PASS] (b) malformed line gets one error reply
    (b) line: {"id":null,"ok":false,"error":"json: expected string at offset 1"}
  [PASS] (b) malformed line closes the connection
  [PASS] (b) the valid line behind a malformed one is not dispatched
  [PASS] (c) three requests were taken before the client left
  [PASS] (c) a batch from a client that has gone is not executed
    stale batch executed: 0 of 3
  [PASS] (d) valid lines, one send, all answered in order
  [PASS] (d) a devtools line that mentions HTTP/1.1 in its code is still dispatched
  [PASS] (d) the connection stays up after valid traffic

== phase classifier ==
```

- Baseline before the task: 118 PASS / 0 FAIL (`/tmp/h0_baseline_run.txt`). The count now is 118 − 2 retired + 1 replacement + 16 new = 133.
- Build: `host-cmd sh -c 'cmake -S <wt> -B /tmp/h0build && cmake --build /tmp/h0build --target kp_harnesstest'`. The build is out of tree, and the worktree was not polluted.
- `commands.cpp` and `channel.cpp` also compile cleanly for the native `kphasor` target (`-Wall -Wextra`) and the mingw `kphasor.dll` objects (`win32/rt_commands.obj`, `win32/rt_channel.obj`), with no warnings.
- The whole `kp_harnesstest` binary ran every section green (json, ring, channel, limits, cross-protocol, phase, stuck-load, normal load completion, ERF, bounds, chargen).

## Preserved-diff proof

- Snapshots taken before any edit: `/tmp/h0base/{commands.cpp,kp_harnesstest.cpp}.{orig,diff}`.
- `diff -u /tmp/h0base/commands.cpp.orig src/harness/commands.cpp` has hunks only at `@@ -1242`, `@@ -1258` (`execute_line`) and `@@ -1448` (`drain`). The K2 hunks (include at :2, `cmd_devtools` protocol dispatch at :712) are not touched.
- `diff -u /tmp/h0base/kp_harnesstest.cpp.orig tools/kp_harnesstest.cpp` has hunks only at `@@ -276`, `-324`, `-397` (`channel_cases` and `pump`), `-469 +469,312` (the new section, inserted before `predicate_cases`) and `-787 +1093` (`main`). This was rechecked after (a2) and the report, because another writer is active in the worktree. The K2 hunks (phase-classifier main-menu checks, normal-load-completion guards) are not touched.
- Script check: every `+`/`-` line of the pre-task `git diff` is still present in the current `git diff`.
  - commands.cpp: 8/8 present, 0 missing.
  - kp_harnesstest.cpp: 33/33 present, 0 missing.
- `git status --short` against the baseline:
  - Mine: only `M src/harness/channel.{hpp,cpp}` (this report is under the gitignored `.superpowers/sdd`).
  - Also new, and not mine: untracked `docs/user/creative-harness.md`, `scripts/harness/kpharness/{commit_inputs,export_verify}.py`, `tools/{creative_host_check,package_creative_harness,kpharness_commit_inputs,kpharness_export_verify}*.py`. These appeared during this session from another writer, and I did not touch them.

## Python clients never send a non-JSON line

- `scripts/harness/kpharness/client.py:137-142` `_send_line` always sends `json.dumps(obj) + "\n"`. That is the only harness socket writer in `scripts/harness/kpharness` (the grep of `sendall|.send(`).
- `playback.py:502` talks to the playback owner, not the harness.
- `grep -rnE '/dev/tcp|\bnc\b|\bncat\b|socat' scripts tools docs` found one hit only: `docs/harness-research/map-prior-art.md:12`, about RetroArch, not this port. No shell script writes to the harness port raw. `session.py:136` only binds to find a free port.
- So real clients are unaffected. This was checked by grep, not by a live run.

## Evaluation (write-up only, no code)

### Per-session token handshake set via env by the Python driver

- Shape: `KOTORPHASOR_HARNESS_TOKEN`, or an INI key written by the driver into the staged INI. The first line must be `{"cmd":"hello","token":...}`, compared in constant time. On a mismatch the client is condemned, reusing this mechanism.
- Benefit: it blocks any local process or page that cannot read the token.
  - Against browsers it adds little on top of H0. A browser cannot make its first line start with `{`: the request line always comes first, so H0 already closes the browser path.
  - Against same-user local processes it adds little. They can read the env (`/proc/<pid>/environ`) or the staged INI.
  - It mainly helps other local users on a shared host (the loopback port is reachable by any uid).
- Cost and consequences:
  - Config parsing lives in `src/runtime/runtime.cpp:152,259` (forbidden here).
  - Every client needs a hello: `client.py` `connect()`, the creative/pioneer/playback owners, `tools/kpharness_*_test.py` fakes, and any hand-driven `nc` workflow in the docs.
  - Reconnect paths (`client.py` wait reconnector) must resend it.
  - A token in the env leaks into child processes (Wine and the game inherit it).
- Recommendation: do it later as a separately reviewed change, as the plan says. Prefer a token file (0600, in the staging dir) over env.

### Remove `os`/`io` from the console Lua state?

- It does not make the port safe. `cmd_lua` (`commands.cpp:732`) runs arbitrary Lua in the *script host* state, and that state gets full `luaL_openlibs` (`src/lua/host.cpp:126`). The harness port is host code execution by design, so the fix has to be at the transport, which is H0.
- It breaks console output unless reworked. `Console::pump` caches `io` in `io_ref_` (`src/devtools/console.cpp:385-386`). `Console::execute` routes `io.write` and the file-handle `write` through it (`console.cpp:441-456`). Removing `io` makes `lua_rawgeti(io_ref_)` push nil, then `lua_getfield` on nil raises an error. That would need a private output shim.
- It would break examples and workflows that use them:
  - `scripts/examples/multiplayer/10_avatar_sync.lua:316,324,334` (`io.open`, `os.remove` for peer files) and `:508,693` (`os.time`, `os.clock`, guarded with `and`, so those degrade).
  - `10_avatar_sync_test.lua:18-25` (`os.tmpname`, `os.execute`, `io.stderr`), but that is an offline test harness, not console code.
  - These run in the script host state, not the console. So removing them from the console state *only* affects user one-liners typed in the F12 console (for example `io.open` or `os.date` in a REPL).
- A narrower option: remove `os.execute`, `io.popen`, `os.exit` and `package.loadlib` from the console state only. Keep `io.write` and `os.time`/`os.clock`. That is cheap, keeps output routing working, and removes the most direct shell primitives from console submissions. But it does not change the port's exposure, because of `cmd_lua`. Not done here (`src/devtools/**` is forbidden).

## Residual risks

1. The drain glue in `commands.cpp:1466-1487` and the condemn flags in `execute_line` are covered by review plus a structural mirror (`hard_pump`/`hard_executor`), not by a test that links `commands.cpp`. `kp_harnesstest` does not link it, and changing `harness.cmake` is out of scope.
2. The `harness.cmake:37-44` comment still says "a malformed line gets an error reply and keeps the connection". It is now stale; that file was out of scope.
3. `tools/kpharness_offline_test.py:530` `test_malformed_line_does_not_kill_connection` tests the Python *fake* server, which still keeps the connection. The fake's contract now differs from native. The test still passes against the fake, but it encodes the old contract.
4. A *valid JSON object* line from a non-HTTP local attacker still runs. H0 is a cross-protocol fix, not authentication. The token (above) is the follow-up.
5. The browser delivery path stays `unverified` (Chrome LNA/PNA and blocked ports were not tested). The fix is justified by the code path and test (a).
6. The one best-effort send before close may truncate if the socket buffer is full. The error line is short and the batch was otherwise skipped, so the worst case is EOF without the error line.
7. Not run live: no Wine or game. The Python tests `tools/kpharness_*_test.py` were not rerun: they use a fake server, and this change touches no Python.

## Claim blocks

```
claim: A browser-shaped POST body line is dispatched on pre-fix code and not after.
referent: red run "(a) the POST body line is never dispatched" FAIL, post1 4 lines eof=0; green PASS, post1 1 line eof=1
checked: /tmp/h0build/kp_harnesstest, 3 red runs, 8 green runs
verdict: holds
confidence: high for channel.cpp mechanism; medium-high for commands.cpp glue (review + mirror, residual 1)

claim: Stale-generation batches no longer execute.
referent: (c) "stale batch executed: 3 of 3" red -> "0 of 3" green
checked: same binary
verdict: holds
confidence: high

claim: The condemnation persists across drain batches (body of a 13-line POST in batch 2 does not run).
referent: (a2) green "later batch executed: 0; batches 8+5"; old-pump shape "later batch executed: 1"
checked: /tmp/h0build/kp_harnesstest (8 runs) and /tmp/h0_oldpump (3 runs)
verdict: holds
confidence: high for the pump mirror; commands.cpp glue by review (residual 1)

claim: Unrelated uncommitted K2 hunks are preserved byte-for-byte.
referent: 8/8 and 33/33 baseline diff lines present; my hunks at disjoint ranges listed above
checked: diff -u against /tmp/h0base/*.orig; python line check
verdict: holds
confidence: high
```

## Follow-up: replies to condemned clients (2026-09-27)

The independent review
(`/home/brunner56/kp-live-20260922/h0-harness-hardening-review.md`) failed H0
on one property. A reply queued after `condemn()` still reached the condemned
client. `Channel::push_reply()` checked only `client == current_client()`.
The listener pulls every queued reply for the current generation before its
`doomed` branch sends and closes. `drain()` calls `stream_events()` after
`condemn()`, and deferred completions in `after_frame()` also use
`push_reply()`. So an event frame or a late completion could follow the error.

Starting state: a codex writer had been started on this and stopped. All four
allowed files hashed identical to the reviewed `sources.sha256`, so there was
no partial edit to continue from. Originals were copied to `/tmp/h0fu/orig/`.

### Change

- `src/harness/channel.cpp` `push_reply()`: the guard is now
  `if (!admit(client)) return;`. That is the request rule (current generation
  and not condemned) applied to replies. The drain already pushes the error
  reply before it calls `condemn()` (`commands.cpp:1486-1487`), so that one
  reply still goes out.
- `src/harness/channel.hpp`: the `push_reply()` and `condemn()` comments say
  so. `admit()` is unchanged.
- `src/harness/commands.cpp`: not touched. Every reply path already goes
  through `push_reply()` (`commands.cpp:1323,1330,1486,1516,1536,1555,1577,1597,1632`).
  SHA-256 still `1a90490c…469e29`, byte-identical to the reviewed file.
- `tools/kp_harnesstest.cpp`: 79 lines added at the end of
  `cross_protocol_cases()`, 0 removed. The K2 hunks are untouched.

### Regressions (`cross_protocol_cases`, cases (e) and (f))

- (e) Direct Channel: connect, push an error, `condemn(gen)`, push a
  `post-condemn reply`. Asserts the client receives exactly the error, no
  `post-condemn` line, then EOF.
- (f) Subscribed events: `set_subscribed(true)`, then a stand-in shaped like
  `stream_events()` (subscribed check, push to `current_client()`). Control
  round: a valid ping gets its reply and an event frame. Then the client sends
  `{bad json`. `hard_pump()` + the stand-in run. Asserts one error line, no
  `"event"` line, then EOF.

### Red (fix not applied, new tests only), 3 of 3 runs `4 failure(s)`, 136 PASS

```
  [FAIL] (e) the error queued before condemn() is delivered
  [FAIL] (e) a reply queued after condemn() is dropped
    (e) line: {"id":null,"ok":false,"error":"first"}
    (e) line: {"secret":"post-condemn reply"}
  [PASS] (f) control: a subscribed client in good standing gets its event
  [FAIL] (f) a subscribed client that sends a bad line gets one error reply
  [FAIL] (f) no event frame follows the error to a condemned client
    (f) line: {"id":null,"ok":false,"error":"json: expected string at offset 1"}
    (f) line: {"event":"test.event","seq":1}
```

The first (e) check went red only because two lines arrived. The error line
itself was delivered in every red run. It asserts "exactly the error", so the
leaked second line fails it too.

### Green (fix applied), 20 of 20 runs exit 0, 140 PASS, 0 FAIL

Built in `/tmp/h0build` (`make kp_harnesstest`, -m32, no warnings). Run with
`host-cmd sh -c 'cd /tmp/h0build && ./kp_harnesstest > FILE; echo $? > RC'`.
Output files: `/tmp/h0fu/g2_{1..20}.{txt,rc}`. An earlier batch piped stdout
through `host-cmd` and 2 of 10 logs came back truncated with exit 0. Writing
the log on the host side removed that; the 20 host-side logs all end in
`0 failure(s)`.

```
  [PASS] (e) the error queued before condemn() is delivered
  [PASS] (e) a reply queued after condemn() is dropped
  [PASS] (e) the condemned connection is closed
  [PASS] (f) control: a subscribed client in good standing gets its event
  [PASS] (f) a subscribed client that sends a bad line gets one error reply
  [PASS] (f) no event frame follows the error to a condemned client
  [PASS] (f) the condemned subscribed connection is closed
```

### The reviewer's probes, rerun against the fix

- `condemned_reply_probe.cpp` built against the fixed `channel.cpp` as
  `/tmp/h0fu/condemned_reply_probe_fixed`. Exit 0 (was 1). Payload:
  `generation=1 bytes=18 payload={"error":"first"}`.
- The real-drain probe was relinked with the reviewer's objects plus a fresh
  `channel.o` from the fixed source, as `/tmp/h0fu/drain_probe_fixed`. The
  reviewer's `platform*.o` were left out because `stubs.o` defines
  `platform::log`. Result: 94 PASS, 0 FAIL (`/tmp/h0fu/drain_fixed.txt`),
  the same as the reviewer's pre-fix run. `commands.o` is the reviewer's
  build of the unchanged `commands.cpp`. The header change is comments only.

### Real `stream_events()` with a condemned subscriber (scratch only)

`kp_harnesstest` does not link `commands.cpp`, so the checked-in (f) case uses
a stand-in. To test the real path, `/tmp/h0fu/subscriber_probe.cpp` links the
reviewer's `stubs.o`, `commands.o`, `console_protocol.o`, `json.o` and `ring.o`.
It sends `subscribe` and pushes a control ring record. Then it pushes a second
record, sends `{bad`, and calls the real `drain()` once. That call runs the bad
line, condemns, then calls `stream_events()`. `sub_red` links the reviewer's
pre-fix `obj/channel.o`; `sub_green` links `channel_fixed.o`.

- Red, 3 of 3 runs exit 1, `2 failure(s)`:
  ```
  after bad line: {"id":null,"ok":false,"error":"json: expected string at offset 1"}
  after bad line: {"event":"probe.after_condemn","tick":2,"seq":2}
    [FAIL] exactly one error line after bad line
    [FAIL] no event frame after the error to a condemned subscriber
  ```
- Green, 3 of 3 runs exit 0, `0 failure(s)`. The control event reaches the
  subscriber while it is in good standing. After `{bad` it gets one error line
  and then EOF.

Outputs: `/tmp/h0fu/sub_{red,green}_{1,2,3}.{txt,rc}`.

### Claim blocks

```
claim: A reply pushed after condemn() is not delivered to the condemned client.
referent: (e) red "(e) line: {"secret":"post-condemn reply"}" -> green PASS; reviewer probe exit 1 -> 0
checked: /tmp/h0build/kp_harnesstest 3 red + 20 green runs; /tmp/h0fu/condemned_reply_probe_fixed
verdict: holds
confidence: high at Channel level

claim: The one error reply queued before condemn() is still delivered.
referent: (e) and (f) green lines; drain probe "error line delivered: yes"
checked: same runs; /tmp/h0fu/drain_fixed.txt
verdict: holds
confidence: high

claim: A subscribed client that sends a bad line gets no event frame after the error.
referent: real drain()/stream_events(): red leaks {"event":"probe.after_condemn",...}, green sends only the error then EOF; (f) stand-in likewise
checked: /tmp/h0fu/sub_red and sub_green, 3 runs each; kp_harnesstest (f)
verdict: holds
confidence: high for the stubbed real drain; the checked-in regression is the stand-in only

claim: commands.cpp and the K2 hunks in kp_harnesstest.cpp are byte-preserved.
referent: commands.cpp SHA-256 matches sources.sha256; kp_harnesstest diff vs /tmp/h0fu/orig is 79 '>' lines, 0 '<' lines
checked: sha256sum; diff | grep -c
verdict: holds
confidence: high
```

### Grill me

1. **Case (f) uses a stand-in. Is the real `stream_events()` covered?**
   Only by a scratch probe, not by a checked-in test.
   `/tmp/h0fu/subscriber_probe.cpp` drives the real `drain()` and
   `stream_events()` with the reviewer's stubs. It leaks the event with the
   old `channel.o` (3/3) and does not leak it with the fix (3/3). Checking it
   in would mean linking `commands.cpp` and the stubs into a test target in
   `harness.cmake`, which is outside the allowed files.
2. **Is (e) racy? The listener might close the socket before the second
   push.** If it did, the old code would drop the reply too, and red would
   pass by luck. Red failed 3 of 3, so the window is wide in practice: the
   three calls run back to back while the listener sits in a 5 ms select.
   Green cannot flake from that race; the fix drops the reply either way.
3. **Could the fix drop a reply that a healthy client should get?** Only if
   `condemned_gen_ == client`. Only a bad line sets it. Generations only
   grow, so an old condemnation never matches a new client. The control in
   (f) and case (d) show healthy replies and events still arrive. All 140
   checks pass, including the stale-reply and reconnect cases.
4. **Is there a race between `condemn()` and `push_reply()`?** No. Both run
   on the main thread (drain and `after_frame()`). The listener only reads
   `condemned_gen_`. An error reply the listener pulls and sends before
   `condemn()` lands is the intended reply.
5. **Deferred completions for a condemned client: is their state cleared?**
   Yes. `push_reply()` returns void, so a dropped reply changes nothing
   upstream. All five pending-reply sites move the state out and reset it
   before the push (`commands.cpp:1501-1502,1525-1526,1544-1545,1563-1564,1585-1586`).
   The screenshot path builds its reply from a local `shot`
   (`commands.cpp:1632`).

Open question: should the real-`stream_events()` check be checked in? Today
it lives only in `/tmp/h0fu/subscriber_probe.cpp`. One change settles it: a
`harness.cmake` test target that links `commands.cpp` with the review stubs
and runs that probe. That change is outside this follow-up's allowed files.

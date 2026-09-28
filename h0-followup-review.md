# H0 follow-up re-review: condemned-client replies dropped

Date: 2026-09-27. Worktree (read-only):
`/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`.
Scratch: `/home/brunner56/kp-live-20260922/review-probes-h0-r2/`. No game, no
live-game lock, no git write. Every build is `-m32` and every run goes through
`/home/brunner56/.local/bin/host-cmd`.

## Independent view (formed before reading the writer's Grill me)

- The whole code change is one line: `channel.cpp:272`
  `if (!admit(client)) return;` replaces `if (client == 0 || client !=
  current_client()) return;`. `channel.hpp` changes comments only
  (`diff -u /tmp/h0fu/orig/channel.{cpp,hpp}` against the worktree). The
  pre-fix originals hash to the reviewed `sources.sha256` values (`8f66...`,
  `fa1f...`).
- `admit()` (`channel.hpp:93-95`) is the old rule plus
  `client != condemned_gen_`. So the fix can newly drop only a reply addressed
  to the condemned generation. Generations come from `next_gen_++` on accept
  (`channel.cpp:443`), and only the listener advances that counter. A healthy
  client, including a reconnect, never shares a generation with a condemned
  one.
- The error reply is still delivered. The drain pushes all batch replies and
  then condemns (`commands.cpp:1486-1487`). The listener's pull filters only
  on `r.client == gen` (`channel.cpp:361-365`), not on the condemned flag.
- There is no admit-then-queue race against `condemn()`. `push_reply` and
  `condemn` are called only from `commands.cpp`, which has no
  `std::thread`/`async`/`detach`. `drain()` and `after_frame()` are called
  only from frame hooks (`src/runtime/hook_bodies.cpp:769,1278-1280,1303-1304`).
  The screenshot completion (`commands.cpp:1600-1632`) is synchronous.

## Checks run

| check | result | evidence |
|---|---|---|
| `kp_harnesstest`, current sources, `g++ -m32 -std=c++20 -Wall -Wextra` | build rc 0, 0 warnings; **10/10 runs rc 0, 140 PASS, 0 FAIL** | `review-probes-h0-r2/ht_{1..10}.{txt,rc}` |
| same test against pre-fix `channel.cpp` (red control) | 3/3 rc 1, `4 failure(s)`: two of three (e) checks and two of four (f) checks. "condemned connection is closed" passes on red, as it should | `htr_{1,2,3}.*` |
| prior reviewer's 94-case hostile-input `drain_probe.o` relinked with my `channel_fixed20.o` (`-std=c++20`) | **rc 0, 94 PASS, 0 FAIL**. Includes `error line delivered: yes` and both `body in batch 2 of a condemned client is not executed` | `drain_fixed.{txt,rc}` |
| reviewer's `condemned_reply_probe.cpp` vs my freshly compiled `channel_fixed.o` | **rc 0**, payload `{"error":"first"}` only | `crp.txt`, `crp.rc` |
| same probe binary, pre-fix `obj/channel.o` | rc 1, `{"secret":"post-condemn reply"}` leaks | `crp_old.*` |
| my own real-drain probe `sub_probe_r2.cpp` (real `drain()` / `execute_line()` / `stream_events()` from `commands.o`, prior reviewer's stubs, loopback socket), red = old `channel.o`, green = `channel_fixed.o` | **red 20/20 rc 1**, failure is always `B the error is the last line`, with `{"event":"r2.after_bad",...,"seq":4}` after the error. **green 20/20 rc 0** (C++17 `channel_fixed.o`); **5/5 rc 0** relinked with the C++20 `channel_fixed20.o` | `red_{1..20}.*`, `green_{1..20}.*`, `g20_{1..5}.*` |
| files newer than `/tmp/h0fu/orig/channel.cpp` under `src tools cmake data CMakeLists.txt` | the only `src/` hits are `channel.cpp` and `channel.hpp`, so `commands.cpp` was not touched. `tools/kp_harnesstest.cpp` is expected. The other hits (camera, playback and gamescope tools, `.pyc`, one adjudication json) are not H0 files. They come from unrelated work running at the same time, not from this follow-up or from my scratch builds (my cmake `-B` was the scratch dir) | `find ... -newer` |

Probe cases in `sub_probe_r2.cpp`:

- A: a healthy subscriber still gets events.
- B: a subscribed client sends `{bad` while events are pushed every tick. It
  gets exactly one error line, nothing after it, then EOF.
- C: a fresh client after a condemn is not poisoned. It subscribes and gets
  both its events and its replies.
- D: `good\n{bad\ngood` in one send. The first good reply and the error are
  delivered. The request after the bad line is not answered. Then EOF.

C and D are the healthy-client cases the writer did not probe on the real
path.

Caveat: the `commands.o` in these links is the prior reviewer's object. A
fresh `commands.cpp` compile needs the LuaJIT headers from a cmake configure,
and that configure did not finish on this mount. The object is still valid
here for two reasons. `commands.cpp` is byte-identical to the file it was
built from (sha `1a90490c...469e29` both times). The only `channel.hpp`
change is in comments.

## Grill me: weakest first

1. *Stand-in (f), real `stream_events()` only in scratch.* The writer's
   answer is accurate. I closed the gap myself with an independent real-path
   probe (above: red 20/20 leak, green 20/20 clean). The checked-in test still
   uses only the stand-in, so a future edit to the `commands.cpp` drain order
   (for example `condemn()` before `push_reply`) would not be caught by
   `kp_harnesstest`. Non-blocking for H0; it is the one open item.
2. *Is (e) racy on red?* That holds. The pre-fix build failed 3 of 3 on my
   side too (`htr_*`). On green the reply is dropped at push time, so there is
   nothing left to race.
3. *Could a healthy client lose a reply?* That holds. The only new drop is
   `client == condemned_gen_` (`channel.hpp:93-95`), and generations are
   unique (`channel.cpp:443`). Probe C (fresh client after a condemn) and D
   (a good reply in the same batch before the bad line) both pass 20/20.
4. *Race between condemn and push.* That holds. All callers are on the frame
   thread (see the call sites above).
5. *Deferred state for a condemned client.* That holds. `push_reply` returns
   void, and the pending state is moved out before the push.

My grill questions the writer missed:

- *A deferred completion for a request that ran before the bad line (in an
  earlier tick) is now dropped. Is that intended?* Yes. It is addressed to the
  condemned generation, and H0 says those replies are dropped. Before the fix,
  its delivery depended on timing, so no driver could have relied on it.
- *`stream_events` advances `g_stream_cursor` even when a push is dropped.*
  That only matters for the condemned generation, which is closing. A new
  client has to re-subscribe, which resets the cursor. Probe C shows the new
  client gets its events. Harmless.
- *Can the doomed branch's single non-blocking `send` truncate the error
  line?* Yes, under a full socket buffer. This predates the follow-up and is
  out of scope. It does not leak anything extra.

## Claim blocks

claim: A reply pushed after condemn() is not delivered to the condemned client.
referent: `channel.cpp:272`; reviewer probe rc 1 -> 0; kp_harnesstest (e) red 3/3 -> green 10/10; real-drain probe B red 20/20 leak -> green 20/20 clean
checked: `review-probes-h0-r2/{crp,crp_old,htr_*,ht_*,red_*,green_*}`
verdict: holds
confidence: high; would change if a push_reply caller moved off the frame thread

claim: A subscribed condemned client gets exactly one error line then close on the real drain + stream_events path.
referent: `sub_r2_green` case B: one `"ok":false` line, it is the last line, eof=1, 20/20
checked: `sub_probe_r2.cpp` linked with the prior reviewer's `commands.o` (sha-matched source) + `channel_fixed.o`
verdict: holds
confidence: high for the stubbed real drain; not run in a live game

claim: admit() in push_reply cannot drop a reply a healthy current client should get.
referent: `channel.hpp:93-95` (the only new drop is `condemned_gen_`); `channel.cpp:443` (unique generations); probe C (fresh client after a condemn) and D (a good reply before the bad line in the same batch) pass 20/20
checked: code read + `green_*`
verdict: holds
confidence: high; would change if generations were ever reused or condemned_gen_ were set outside the drain

claim: The error reply queued before condemn() is still delivered.
referent: `commands.cpp:1486-1487` order; the pull filters on generation only (`channel.cpp:361-365`); (e) "error queued before condemn() is delivered" PASS; probe B/D error line present
checked: `ht_*`, `green_*`
verdict: holds
confidence: high

claim: commands.cpp and the K2 hunks are byte-preserved.
referent: commands.cpp sha `1a90490c...469e29` equals `review-probes-h0/sources.sha256`, and no `src/` file other than channel.* is newer than the fix; the pre-follow-up kp_harnesstest sha `fe08...` equals sources.sha256, and the current file differs by a single insertion `774a775,853` (79 added, 0 removed). The insertion sits inside `cross_protocol_cases()` (which opens at line 586): after case (d), before its `ch.stop()`. That is not a K2 test function
checked: `sha256sum`; `diff /tmp/h0fu/orig/kp_harnesstest.cpp tools/kp_harnesstest.cpp`
verdict: holds
confidence: high

## Open item

The prior review asked for two regressions under "Required correction and
regression" (`h0-harness-hardening-review.md:79-81`). One was a direct
Channel regression, which is checked in as (e). The other was a
real-commands test: subscribe, create a ring event, send a bad line, assert no
event frame follows. That second one landed only as the (f) stand-in plus
scratch probes (the writer's `/tmp/h0fu/subscriber_probe.cpp` and my
`sub_probe_r2.cpp`). The verdict below grades the fix against the H0
property: condemned-client replies are dropped. It does not certify that
every regression the prior review asked for is checked in.

The real `stream_events()` regression is not checked in: `kp_harnesstest`
does not link `commands.cpp`. One check settles it: add a `harness.cmake` test
target that links `commands.cpp` with the review stubs and runs a case like
`sub_probe_r2.cpp` case B. That is outside this follow-up's allowed files.

H0 follow-up: CONFIRMS (the fix and its property; the requested real-commands regression is covered only by a stand-in plus scratch probes, see Open item)

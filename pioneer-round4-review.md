# Pioneer playback round 4 review (M1 read/evict race, M2 flake loop)

Reviewer: opposer, read-only on `.worktrees/lua-boundary-validation`. Probes and logs: `/home/brunner56/kp-live-20260922/review-probes-pioneer-r4/`.
Reviewed bytes (sha256, same before and after the host suite):
- `scripts/harness/kpharness/playback.py` 0b11a8b1a628ba52e4543e659f539d7999235573589429efe3840cb786f6b77c
- `tools/kpharness_playback_test.py` 93457489067c14e62e352317b9164dfa6a8d7795f075651a419e3fc59d747557

Note: another session changed `capture_diagnostic.py` and `display_backends.py` in this worktree during the review (mtime 18:44:48). They are unrelated to playback. The two reviewed files did not change.

## Own view first (before reading the writer's Grill me)

`read_request_line` (playback.py:601-634) peeks. When the peeked chunk has no newline, it consumes exactly that chunk and peeks again. When the newline is in the chunk, it calls `admit()` and then consumes exactly `end` bytes. Every loop turn either consumes at least one byte or blocks in `recv` with the remaining deadline as the timeout. So it cannot busy-spin. Every blocking call is capped by `deadline`, so it cannot outlive 1 s.

`admitted()` (playback.py:694-700) and `_evict_one` (702-710) both take `_guard`. `_evict_one` skips any socket whose buffer holds a newline (`_line_waiting`, 663-671). That gives two outcomes:
- The line is in the buffer before the evictor looks. The socket is skipped, and `admit()` then succeeds.
- The evictor looked first and found no line. It removes the socket, `admit()` returns False, and the handler returns before `json.loads` and `command()` (647-648).

Once a socket is admitted it has left `_idle`, so nothing else reads it or shuts it down. The recv after the peek therefore sees the peeked bytes.

## Claim blocks

claim: "M1 fixed: the read -> admit gap never runs a command whose reply is then dropped"
referent asked for: test output, red then green
referent received: Round4ReadEvictTests plus the reviewer's r3 probes
checked:
- red against pioneer-r4-backup/playback.py (copied into /tmp/kp-r4-red), in `red-new-tests.txt`:
  - widened_gap FAIL "command ran ['play'] but the reply was dropped"
  - evicted_before_admission FAIL "['play'] != []"
  - empty_reply ERROR JSONDecodeError
- green on the worktree, in `green-new-tests.txt`: 3/3 ok
- r3 `race_read_then_evict.py` at widen 0.3, 0.05, 0.02 and 0: all four ok, executed ['play'] (`race-read-then-evict-r4.txt`)
- r3 `inproc_stress.py 300 4 0.02`: failures 0, evict_calls 1117, evict_saw_closed_socket 0 (`inproc-stress-r4.txt`). Round 3 had 2/300.
verdict: holds
confidence: high. It would change if a failing interleaving showed up in which `_line_waiting` returns False while a full line is in the buffer.
one line: fair, that holds. both orders are forced and both are red on the old code.

claim: Grill #1 "recv(n) after a peek of n bytes returns exactly those bytes; weakest point: no test forces a short recv"
referent asked for: a worked example with split, pipelined and partial-then-close clients
referent received: none from the writer beyond the source, so I built one (`grill_peek.py`, output in `grill-peek.txt`)
checked, fixed code:
- split mid-token with a 0.3 s pause: ok, executed once
- split right before the "\n": ok, executed once
- two lines pipelined in one segment: the first line runs, parsed exactly. The second line is never read.
- split plus pipelined (line 1 ends in segment 2 along with line 2): ok, executed ['play'] once
- partial line then FIN: "invalid control message", executed []
- LIMIT bytes exactly: accepted. LIMIT+1: refused.
- a fake socket whose recv returns 5 bytes where 92 were peeked: raises PlaybackError "invalid control message". The endswith check catches it. The old code would have returned the whole line.
- the same probe on the backup (`grill-peek-backup.txt`) gives the same results for every real-socket case, so there is no behaviour regression.
verdict: holds
confidence: high. A short recv cannot happen on a TCP socket with n bytes already queued and a single reader. Even if one did, the command does not run.
one line: that holds. i tried to split it and pipeline it, it wouldn't break lol

claim: the MSG_PEEK loop "can't busy-spin or hang past the 1 s deadline with a trickling client" (the task's check)
referent asked for: benchmark, meaning process CPU time and wall time
checked (`grill-peek.txt`):
- trickle 1 byte / 20 ms with no newline: refused at 1.004 s, 0.010 s process CPU
- a 92-byte line at 1 byte / 5 ms: ok at 0.751 s, 0.013 s CPU
- slowloris that finishes the line at about 1.4 s: refused at 1.005 s, not run
- idle socket, no bytes: refused at 1.011 s, 0.004 s CPU
verdict: holds
confidence: high
one line: no spin, no overrun. 10 ms of cpu for a full second of trickle.

claim: Grill #2 "a client gets an empty reply for a command that ran only if sendall fails"
referent asked for: mechanism, meaning a path where command() returns and no reply is written without sendall raising
referent received: the writer's two eviction tests, which cover eviction only
checked: playback.py source
- Handler reply block, 650-660
- stop: `command()` calls `request_stop` (346-351). The worker breaks out and runs `cleanup()` (571-586), which ends in `self.shutdown()`. `serve()` then leaves `serve_forever`, the finally at 765-766 joins the worker, and the process exits.
- Handler threads are daemon threads (`daemon_threads = True`, `block_on_close = False`).
- So a successful `stop` whose handler thread is descheduled between `command()` returning and `sendall` can be killed at interpreter exit. The client then gets "closed the control connection without a reply".
- The `json.dumps` path is safe: `snapshot()` round-trips through JSON (237-239).
verdict: does not hold as worded ("only on send failure"). It holds for eviction, which is what M1 was about.
confidence: medium
- Source-only; I did not reproduce it. It needs a real owner and the scheduler losing a race against journal I/O plus the 0.05 s serve poll.
- The old code has the same shape, so it is not a regression. Its effect is also harmless: a spurious "check status" on a stop that did happen. The client message already says "check status before retrying", which is the right advice.
one line: stop can exit under its own reply. rare, harmless, and the message already covers it. not blocking.

claim: M2 "probe_f 50/50 OK on host under load 120-259; not a diagnosis; tally 2 errors in 159"
referent asked for: the per-run logs
checked:
- `probe-f-host-x50/` holds 50 run logs. None contains FAIL, ERROR or Traceback. All end in OK.
- `probe-f-host-x50.txt` gives "SUMMARY ok=50 bad=0 of 50 burners=12" and owners_left=0 on every run.
- The 109 in the tally matches round-3 review lines 88-91.
- No probe_f_loop.sh or burner process is left on the host (ps).
- The current host load of about 154-166 on 12 cores comes from other programs (thumbnailer players days old, rustc builds, immich, chromium), not from the writer.
verdict: holds. The writer claims no fix, and the logs back the claim they do make.
confidence: high for the claim itself. The root cause of the 2 early errors is still unknown.
one line: fair, that holds as stated. 50 green runs don't tell us what the 2 early errors were.

claim: "suite 37 OK on host"
referent asked for: my own run
checked: host-cmd, Python 3.14.7, loadavg 153.69 at start: "Ran 37 tests in 71.691s OK", rc=0, no-owner-left (`suite-host.txt`). This load was not started by me or the writer.
verdict: holds
confidence: high

## Own grill questions the writer missed
- Does a successful stop always get its reply? No, see the Grill #2 block. It is a pre-existing race and harmless.
- Pipelined second line: it is silently discarded when the connection closes. That is fine for a one-request-per-connection protocol, and it was the same before.

## Open question I could not settle
What the 2 early host probe_f errors were. To settle it, run `pioneer-round4-logs/probe_f_loop.sh` until the first failure and keep its log. That is unchanged from the writer's own open question.

stop: referent arrived for every claim. Grill #2 is narrowed to eviction, with a non-blocking pre-existing stop/exit race noted.

Pioneer round 4: CONFIRMS

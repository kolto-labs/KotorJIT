# W1 follow-up confirmation: W1R3-m1 and W1R3-m2

Independent reviewer, read-only on the worktree
`/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`.
No game, Wine, real game folder, or live-game lock. No git writes. Scratch
under `/home/brunner56/kp-live-20260922/review-probes-w1-followup/`
(`TMPDIR` exported there).

Answers writer section "Follow-up: W1R3-m1 and W1R3-m2" in
`.superpowers/sdd/lua-boundary-validation-plan/platform-w0-w1-report.md:211-366`,
itself answering `/home/brunner56/kp-live-20260922/platform-w1-r3-review.md`.

## Claim 1: overlay change limited to the host/gl line format

claim: "Scope: ... consistent with the 'overlay.cpp host/gl line format only'
constraint." Writer admits it could not byte-diff against r3-final
(539e4cbb…, not preserved on disk).

referent asked for: `git diff -- src/devtools/overlay.cpp` plus any saved
copies under `/home/brunner56/kp-live-20260922/`.

referent received / checked: ran `git diff -- src/devtools/overlay.cpp`
myself. The diff against HEAD (not r3-final — that baseline genuinely
doesn't exist anywhere I could find either, confirming the writer's gap
honestly) shows `session_id()`, `log_session_start()`, `log_host_and_gl()`
as one uncommitted block spanning multiple rounds, not just this round's
edit. Inside that block, `log=esc1` appears exactly once, in the
`log_host_and_gl()` host-line format string
(`"kp-session=%s log=esc1 %s"`), and nowhere in `log_session_start()` or the
gl-line call. That is consistent with the writer's claim about *where* the
token lives, but does not independently establish that this round touched
*only* the host-line format — the round-3 baseline to diff against is
missing for both of us. `src/runtime/runtime.cpp` sha unchanged at
`83fec910…` (matches writer and r3 review), which does support "no
runtime.cpp edits this round."

verdict: unresolved on the byte-diff-to-r3-final specifically (no referent
exists for either of us to produce); holds on everything checkable
(token location, runtime.cpp untouched).

## Claim 2: log without the token is rejected by both parsers

claim: a host line without `log=esc1` is rejected by the Python validator
and the PS1 parser.

referent asked for: crafted fixture, run both parsers.

referent received: `tools/fixtures/platform-receipts/logs/old_dll_no_token.log`
already has exactly this shape (host line with no `log=esc1`).
`PRE_ESCAPE_HOST_RE` in `tools/platform_receipt_test.py:83` is `HOST_RE`
with `" log=esc1 host: "` replaced by `" host: "` — a real distinct
pre-token pattern, not a hand-wave. PS1 `$PreEscapeHostPattern`
(`scripts/receipts/windows-native-receipt.ps1:99`) is byte-identical in
shape. `ReceiptParserParity.test_ps1_parser_matches_python` globs all 16
fixture logs (`assertGreaterEqual(len(logs), 9)`,
`tools/platform_receipt_test.py:1083-1093`) including this one and
`escaped_*.log`, and runs the real PS1 block in pwsh against
`session_evidence()` — not a fixed pre-round list.

checked: read the two regex definitions and the fixture file directly; ran
the full suite (below), which includes this fixture in both the Python and
PS1-parity paths and passed.

verdict: holds.

## Claim 3: forged host line with log=esc1 inside Lua-appended content — residual honestly stated

claim (Grill Q1 in the writer's report): the token does not stop a script
with `io` access from forging a whole session block including the token;
only an old-DLL host line (no token at all) is closed off by this fix.

referent asked for: run the r3 residual case directly.

referent received / checked: read
`tools/fixtures/platform-receipts/logs/spoofed_later_host.log` — it
contains a real host line with `log=esc1` plus two forged host-like lines,
one with the token (via `info:` sink) and one without (`[spoof]`). The test
`test_spoofed_later_host_line_rejected`
(`tools/platform_receipt_test.py:578-583`) shows this specific composite
case is rejected — but for "3 host lines in the current session," not
because the token itself is unforgeable. The writer's own Grill Q1 answer
states plainly that a script writing the *entire* session block through
`io`, with the token included and no genuine host line to collide with,
still validates — the round-3 `IO1` case. This is not new information the
writer is hiding; it's stated as the answer to their own hardest question.

verdict: holds — as a residual honestly disclosed, not as a closed hole.
Docs (`docs/user/windows-native-install.md:70`) and the PS1 header
(`scripts/receipts/windows-native-receipt.ps1:28,37`) say exactly this: "A
script can still write the token itself."

## Claim 4: test_check_goes_red_without_the_escaping rebuilds and goes red alone

referent asked for: run the test in isolation.

checked:
```
host-cmd python3 tools/platform_receipt_test.py \
  RuntimeLogEscaping.test_check_goes_red_without_the_escaping -v
```
→ `ok`, `Ran 1 test in 4.553s`, `OK`. The test patches
`runtime.cpp`'s control-byte check and its `fprintf` call to bypass
escaping, rebuilds each mutant with MinGW, and asserts the compiled loop
then reports `escaped_print_newline` and `escaped_error_text` as VALID.

verdict: holds.

## Claim 5: docs text matches what the code checks

referent asked for: diff doc wording against the regex/refusal message.

checked: `docs/user/windows-native-install.md:70-71` — "A `kphasor.dll`
with the change writes `log=esc1` in its host line. The receipt refuses a
host line without it... A script can still write the token itself." /
"...does not check which build that hash belongs to. No list of release
hashes exists yet." matches `HOST_RE`/`PRE_ESCAPE_HOST_RE`
(`tools/platform_receipt_test.py:81-83`), the PS1 refusal message
(`scripts/receipts/windows-native-receipt.ps1:149`), and the SHA-only check
noted in the r3 review ("no allowlist of DLL shas exists anywhere"). The
old "so you can check which build ran" wording the r3 review flagged
(W1R3-m1) is gone from both files (grep confirms no match).

verdict: holds.

## Full suite runs (this session)

- `host-cmd python3 tools/platform_receipt_test.py` → `Ran 73 tests in
  406.836s`, `OK`, no `skipped=` in output (0 skipped). Matches writer's
  claimed 73/0.
- `host-cmd python3 tools/platform_profile_consistency_test.py` → `Ran 23
  tests in 1.653s`, `OK`. Matches writer's claimed 23.

## W1 follow-up verdict: CONFIRMS

All five claims check out against independently-read source, fixtures, and
test runs, with one honest gap the writer already flagged and I could not
close either: no preserved r3-final copy of `overlay.cpp` exists to
byte-diff against, so "host/gl line format only" rests on the source-level
regex pin (`test_host_line_carries_the_log_format_token`) plus the
unchanged `runtime.cpp` sha, not a diff. That gap is disclosed, not hidden,
and does not change the verdict on m1 or m2 themselves.

## Grill me

1. *Why not manufacture the r3-final baseline from the r3 review's own
   probes (`review-probes-w1-r3/`)?* Checked — the writer already tried
   this (`w1-fix-scratch/orig/overlay.cpp` predates round 3's own
   `kp-session=` mechanism, wrong baseline). I did not find a better one
   under `/home/brunner56/kp-live-20260922/` either. Unverified beyond
   the source-level pin.
2. *Does "3 host lines" rejection in `spoofed_later_host.log` mean the pure
   IO1-style single-forged-block case is actually tested anywhere in this
   round's new suite?* No — I did not find a fixture that is purely a
   forged block with the token and nothing else to collide with. That
   exact case rests on the writer's Grill Q1 prose answer, not a test.
   Unverified; would need a new fixture to close.

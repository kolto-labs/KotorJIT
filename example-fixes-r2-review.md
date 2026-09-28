# Example fixes round 2 review (2026-09-27)

Reviewer: independent, read-only on the worktree.  No Wine, game, capture,
or live-game lock access.  Review probes are in
`/home/brunner56/kp-live-20260922/review-probes-examples-r2/`.

## Resume record

There was no existing round-2 review file or round-2 probe output at start.
The worktree was already dirty with many unrelated writers' files.  I preserved
them.  The relevant current changes are the I1-fix round in
`scripts/examples/cursed/40_chain_reaction.lua`, `README.md`,
`tools/tests/examples/cursed.lua`, `manifest.json`, and the behavior ledger.
The writer report was read only *after* the independent code/test inspection.

## Re-run and immutable checks

Command (host-only, exact requested tool boundary):

```
/home/brunner56/.local/bin/host-cmd sh -c 'cd /run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation && /usr/bin/python3 tools/example_validation.py --luajit /usr/bin/luajit --host /home/brunner56/kp-validation-20260922-build/kp_luatest --receipt /home/brunner56/kp-live-20260922/review-probes-examples-r2/rerun-receipt.json'
```

Output/exit: `PASS: 41 original syntax/host regression sources, 93 per-file
cases; 8 retired from public catalog; 0 live receipts attached; no public
quality promotion`, exit 0.  The receipt is SHA-256
`844474036690078fbd0d89675a4c4001780c29b846a22e6234d64303e7e712fc`.
Its changed receipt metadata from receipt c is expected (`generated_utc` and
the dirty-tree hash); it records 93 total host cases, chain-reaction 10 cases,
chain bytes `24ad2057e6eb8e43b8a577cbd8dcc5459cb7095a6eb744baa1277f3f37c9a16e`,
and doppelganger 5 cases.  `sha256sum` confirms
`70_doppelganger.lua` remains
`5d9864b22241ff135d3bb0c1ecb3f2671af218b58cdf2f44eb7bc62c95f62c42`.

The three added host cases cover I1's original counterexamples: a party member
recreated under a new id, a PC recreated under a new id, and a missing member
that returns and is hit while its restore is pending.  They pass in the
validator.  This closes I1's original *new-id* failure.

## Claims

claim: A party-tag collision cannot cause a non-party NPC/boss to receive the
stored min-one-HP state through the `GetObjectByTag` fallback.
referent: `40_chain_reaction.lua:91-93` accepts fallback result only when
`IsObjectPartyMember(m)` is true; roster resolution at lines 85-89 also walks
only `GetPartyMemberByIndex` values.
checked: code inspection against the exact fallback and roster branches.
verdict: holds.
confidence: high; an incorrect `IsObjectPartyMember` engine response is beyond
the Lua code's available safety boundary.

claim: A pending member hit by a later blast retains its original prior rather
than recording the temporary `1` as its prior.
referent: `40_chain_reaction.lua:97-106` finds an existing entry through
`current`, moves it to the new id, and calls `SetMinOneHP(member, 1)` without a
fresh `GetMinOneHP`; test `cursed.lua` “a member that cannot be re-resolved…”
asserts final `min_one_hp==0`.
checked: validator run above (the test is among the 10 chain cases).
verdict: holds.
confidence: high.

claim: All resolvable pending entries are restored even if another pending
entry cannot be found, and retries are bounded by the next timer/transition
rather than an internal loop.
referent: `restore_guards` at `40_chain_reaction.lua:108-121` visits all table
entries once, removes only successful ids afterwards, and `chain_settle` at
lines 122-125 returns `false`; the missing-member regression checks PC restore
while Bastila is absent.
checked: code inspection and validator run.
verdict: holds.
confidence: high.  Per pass is O(number of guarded party entries squared) due
to `guard`'s pending-entry scan, but party size is bounded and this is not an
unbounded pending loop.

claim: The round-2 PC re-resolution is safe when the player-controlled PC
identity changes while the previously guarded PC object remains valid.
referent: none in the current regression suite. `current` at
`40_chain_reaction.lua:76-79` resolves every `entry.pc` solely as current
`GetFirstPC`, without checking whether it identifies the same actor.
checked: host-only probe
`review-probes-examples-r2/pc_swap_probe.lua`, run via
`host-cmd ... /usr/bin/luajit .../pc_swap_probe.lua`, output
`old_pc=1 replacement_pc=0`. The probe guards id 1, retains id 1, makes id 7
the `GetFirstPC` result, then calls `OnModuleLoad`: cleanup writes the original
prior (0) to id 7 and leaves id 1 at 1.
verdict: does not hold.
confidence: high for the Lua counterexample; medium for live impact. The
fixture does not establish whether K1's `GetFirstPC` can change under a party
leader/control swap while the original PC remains in the area. A live
before/after `GetFirstPC` identity readback across that exact swap settles it.

Classification: **Important.** If the engine permits that identity change, the
old player object can retain min-one-HP and the replacement's preexisting flag
can be overwritten. This is materially the same persistent protection class
I1 was intended to close. The existing new-id test covers replacement, not
coexistence. It does not promote fixture evidence to live proof.

claim: README and ledger accurately state the implemented re-resolution and
proof boundary.
referent: README row for `40_chain_reaction.lua` says old ids are not trusted,
describes PC `GetFirstPC`, tag/party resolution, pending retries, and the
save-within-3s limitation; header lines 16-31 says the same and says a live
chained kill decides VFX behavior. Ledger’s round-2 row calls these host-tested
and keeps live readback open.
checked: `scripts/examples/cursed/README.md:13`,
`40_chain_reaction.lua:16-31`, and `docs/example-behavior-ledger.md` round-2
text.
verdict: holds, with one caveat: the prose accurately describes the code, but
neither calls out the PC-identity ambiguity above.
confidence: high.

claim: The changed example code introduces no direct Lua duplicate of an
NWScript routine name.
referent: every engine access in the changed chain script is a string passed to
`nwscript.call` through `q` or `call`; the only top-level added callback is
`chain_settle`, and the local additions are `current`, `guard`, and
`restore_guards`. Case-insensitive declaration scan found no `Get*`, `Set*`,
or `Is*` Lua declaration.
checked: `rg -n -i '(^|[^[:alnum:]_])(Get[A-Za-z0-9_]+|Set[A-Za-z0-9_]+|Is[A-Za-z0-9_]+)\\s*=' scripts/examples/cursed/40_chain_reaction.lua` (only local constants
`SETTLE_MS`/`settle_gen` matched).
verdict: holds.
confidence: high.

## Writer grill follow-up

The writer report has no literal `Grill me` section. I attacked its weakest
remaining identity assertion (PC lookup after transition) with the coexistence
probe above. The reported new-id path itself holds under the added regression.
One unsettled question remains: can K1 return a different `GetFirstPC` during
a party-leader/control swap while the old object remains valid? A live identity
readback before/after that swap is the single settling check.

## Summary

- Critical: 0.
- Important: 1 — PC identity swap can misdirect restoration and leave the
  original PC min-one-HP guard set in the host model.
- Minor: 0 new.
- I1 original (object recreated under a new id): closed by current code and
  3 added regressions.
- No game, Wine, capture, process signaling, or live lock access occurred.

Example fixes round 2 verdict: FAIL

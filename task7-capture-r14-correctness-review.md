# Capture cadence round 14 correctness review

Date: 2026-09-28. Reviewed frozen writer report
`.superpowers/sdd/lua-boundary-validation-plan/ta[REDACTED].md`
and the current capture source. No source edits, builds, encodes, display,
Wine, game, or lock use were performed.

claim: the new two-region barcode rejects the specific period-7, period-14,
and half-region synthetic failures claimed by the writer.

referent: `display_backends.py:486-575` decodes 14 bits plus parity from both
regions, rejects parity/region mismatch and non-monotonic indices, and checks
index jumps against PTS. The writer report records healthy pass, loop7 with 52
non-monotonic violations, loop14 with 26, and half-freeze with 361 region
mismatches.

checked: writer report and source read. The report's adapted probe script,
encoded clips, and raw diagnostic JSON were not retained at named paths, so the
media receipt cannot be independently replayed from this review.

verdict: holds for the described synthetic result; evidence-replay unresolved
confidence: medium; a retained probe script plus raw output would raise this
to high.

claim: the barcode is wired into production capture probing and receipts.

referent: `recording.py:342-425` adds index crops and validates frame-major
stream alignment; `recording.py:720-728` passes the policy to the probe;
`display_backends.py:383-393` emits `index_sequence` and a typed
`capture_content_index` failure.

checked: direct source read.

verdict: holds
confidence: high.

claim: the lock-fd fix removes the btrfs device-field dependency and checks
exclusive ownership through a fresh descriptor.

referent: `gamescope_socket.py:83-130` matches fdinfo by inode, compares the
descriptor's inode with `fstat`, attempts a nonblocking exclusive flock on a
fresh descriptor, and closes/unlocks the probe on the unexpected-success path.

checked: writer report's btrfs probe receipt (`held True`, `fake_refused ...`)
and source read.

verdict: holds
confidence: high for the described host probe; the production ext4 lock was
not opened.

claim: Round 14 meets the brief's required full-family correctness evidence and
is ready for the serialized diagnostic.

referent: the brief requires every round-13 clean, drift, duplicate, and skip
family, plus noise margin across those families, and requires the production
probe path. The report contains only healthy, loop7, loop14, and half-freeze
adapted 8-second clips, with margin stated across those three failing/one clean
clips. It explicitly says the original probe was malformed under the new
policy, and it does not provide retained paths for the adapted probe or raw
outputs. The report's Grill #4 also calls the final btrfs suite exit lines
unresolved despite the earlier claim that all four suites passed.

checked: brief §Required validation versus the report's Host validation and
Adapted synthetic evidence sections; source constants show per-probe deadlines
are bounded by `probe_deadline_seconds`, but no retained full 34-second run
receipt is supplied here.

verdict: does not hold
confidence: high; the missing family sweep and contradictory/unreplayable
receipts are acceptance blockers, independent of the barcode implementation.

claim: a within-policy single source-frame drop is accepted by the new index
gate.

referent: `/tmp/kp-root-r14-one-drop.json` records a 600-frame synthetic source
with source frame 350 removed and corresponding PTS; `index_sequence` passes,
with one estimated dropped source frame, while the legacy level sequence
currently fails. The case has approximately 0.2% loss, maximum gap 0.0333 s,
and a distinct ratio around 0.998, all within the brief's stated skip/cadence
policy.

checked: receipt supplied by the independent adversarial probe; no source edit
was made by this review.

verdict: does not hold
confidence: high; this is a concrete acceptance blocker. The production gate
must reconcile allowed duplicate/skip tolerance across both the level and index
signals before claiming that within-policy skip families still pass.

## Grill me

1. Does a green host suite prove the round-13 families? No. The required
   families are semantic media cases; the report only proves four adapted
   cases.
2. Does the half-freeze test prove a compositor partial-frame freeze? No. The
   writer says it mutates decoded bottom arrays after a healthy decode; this is
   evaluator proof, not media-path proof.
3. Is the barcode implementation itself wired correctly? Yes, source reads
   show the policy is passed to probe, crops are frame-aligned, and the receipt
   contains typed index results.
4. Is btrfs fixed? The inode/exclusivity algorithm holds and the named probe
   result supports it, but the contradictory statement about suite exit lines
   needs one consistent retained receipt.

## Verdict

**FAIL pending evidence completion and a skip-tolerance correction.** The implementation-level barcode and
btrfs changes look correct, and the claimed loop/half-region evaluator cases
are plausible, but the brief's acceptance gate is not met: the required clean,
drift, duplicate, skip, stale-level, reorder, and longer production-budget
evidence is absent or not replayable from retained artifacts. In addition, the
retained one-drop receipt demonstrates that the index check accepts a
within-policy drop while the legacy level check rejects it. The next settling
step is a bounded source-frozen probe sweep that retains its script, clips,
raw evaluator JSON, hashes, and unambiguous suite exit receipts, followed by a
reviewed tolerance fix; no live diagnostic should proceed on this report alone.

Unsettled question: whether the exact production 34-second capture path stays
within its output/deadline budget while accepting policy-allowed duplicates and
drops. Single check: run the required retained full-family synthetic/encoded
sweep through the production probe and preserve `diagnostic-result.json` plus
the complete suite receipts.

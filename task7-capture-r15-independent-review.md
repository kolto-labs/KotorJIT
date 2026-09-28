# Task 7 Capture Round15 independent review

Date: 2026-09-27. Host-only review of the current dirty capture source in
`/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`.
No capture product file was edited. Review scripts and outputs are confined to
`/home/brunner56/kp-live-20260922/r15-independent-review/`. No media was
encoded, and no Wine, game, display, or live diagnostic process was launched.

## Readiness and ownership

The retained files `r15-focused-suite.log` and `r15-red-tests.log` predate this
review and contain no source hash, freeze marker, or motion-review handoff. I
therefore treated them as historical evidence only and reran focused tests
against the current source. No file named `*freeze*`, `*ready*`, or a Round15
motion handoff was present in `/home/brunner56/kp-live-20260922/` at review
time. The capture source paths remained read-only from this task.

Current source hashes used:

```
sha256 scripts/harness/kpharness/display_backends.py 6f82abd9a5a44ff2ede4bae59d221f1e4d64f66f2fbd46e5f141ce6b512513fe
sha256 scripts/harness/kpharness/recording.py        939160e924db2bf74321917ce27af6099f73d7bbbace31e3fc06c3eac735deb9
sha256 scripts/harness/kpharness/capture_diagnostic.py 9dd5a3c28cfa9a13986b14dbc893c4eb7d6f0443d4d8c429ffe0f391c55ebc
```

## Independent checks

claim: the shared cadence boundary accepts one isolated source drop and rejects
accumulated drops and an excessive maximum gap.

referent: `display_backends.py:587-600` computes accumulated source-drop ratio
and maximum source gap, while `:575-586` cross-checks each jump against PTS.

checked: `r15-independent-review/boundary_probe.py` imported the production
`display_backends.evaluate_content` and used the same policy table. Its saved
output is `boundary_probe.out`:

```
isolated_drop: status=passed index=passed level=passed drop_ratio=0.0033333333333333335 max_gap=0.016666666666666666
accumulated_drop: status=failed index=failed kinds=[source_drop_ratio] drop_ratio=1.0
excessive_maxgap: status=failed index=failed kinds=[index_step_disagrees_with_elapsed_time, source_gap] drop_ratio=0.004022988505747126 max_gap=0.11666666666666667
```

verdict: holds for the current implementation. Confidence: high for this
host-level policy path; this does not prove an encoded production clip.

claim: the focused Round15 policy tests pass against the current source.

referent: `tools/kpharness_capture_diagnostic_test.py:569-629` contains the
isolated drop, accumulated drop, maximum-gap, and duplicate acceptance tests.

checked: `python3 -m unittest -v
 tools.kpharness_capture_diagnostic_test.CriteriaTests.test_within_policy_source_drop_keeps_level_and_index_gates_green
 tools.kpharness_capture_diagnostic_test.CriteriaTests.test_sustained_delta_two_is_rejected_by_accumulated_source_drop_ratio
 tools.kpharness_capture_diagnostic_test.CriteriaTests.test_single_large_source_gap_is_rejected_even_under_total_drop_budget
 tools.kpharness_capture_diagnostic_test.CriteriaTests.test_pure_duplicate_and_duplicate_then_single_skip_within_policy_pass`
returned `Ran 4 tests ... OK`; exact output is
`r15-independent-review/focused-unittest.out`.

verdict: holds. Confidence: high. The older `r15-focused-suite.log` and
`r15-red-tests.log` recorded these same cases failing, so those logs are stale
relative to the hashed source checked here and must not be used as current
results.

claim: non-index behavior is preserved for the game policy.

referent: `display_backends.py:333-338` validates index fields only when the
policy supplies `index_bits`; `evaluate_content` adds the index gate only at
`:379-387` when that policy key exists.

checked: the boundary probe's `non_index_game_policy` case supplied rows with
only the six signalstats fields and `CONTENT_POLICIES["game-capture-v1"]`.
Output: `status=passed index=null level=null failures=[]`.

verdict: holds. Confidence: high for the host evaluator.

claim: half-region freeze is refused by the two-region index check.

referent: `display_backends.py:535-542` records `region_mismatch` when the two
regions decode different indices.

checked: the boundary probe froze the bottom region at index 179 while the top
continued. Output: `status=failed index=failed kinds=[region_mismatch]` with
181 recorded mismatches.

verdict: holds. Confidence: high for the synthetic boundary.

claim: loop7, loop14, stale replay, and reorder are refused as ordinary
per-frame failures.

referent: `display_backends.py:547-553` records `non_monotonic` but does not
append a corresponding entry to `source_deltas`; `evaluate_content` then
passes that list to `content_level_sequence` at `:392-395`, which indexes one
entry per acceptance interval.

checked: the boundary probe supplied source index sequences `i % 7`, `i % 14`,
`i % 2`, and one adjacent swap. Every case raised `IndexError: list index out
of range` instead of returning a failed/refused result. Output is saved in
`boundary_probe.out`.

verdict: FAIL: the requested loop7/loop14/stale/reorder refusal boundary is
not total. A malformed or adversarial index stream can escape the intended
fail-closed result as an uncaught host exception. This is a current-source
finding, independent of the stale Round15 logs. Confidence: high; it is a
deterministic direct call to production `evaluate_content` with policy-shaped
rows.

recommended settling check: make `source_deltas` positional for every decoded
interval, including non-monotonic and parity/region failures, or make
`content_level_sequence` refuse a missing/misaligned source-delta vector before
indexing it. Rerun the four adversarial cases and require a structured
`status=failed` with a `non_monotonic` or equivalent refusal reason and no
exception.

## Grill me

1. Did I independently verify the shared policy rather than trust the writer
   log? Yes. The four focused tests were rerun against the hashed current
   source, and the boundary script directly called the production evaluator.
2. Do the isolated drop and accumulated/max-gap controls have the expected
   split? Yes: isolated passes; accumulated and excessive max-gap fail with
   the corresponding aggregate reasons.
3. Does non-index behavior remain safe? The game policy passes without index
   fields; no diagnostic barcode claim is made for that policy.
4. Did loop7/14/stale/reorder pass? No. They raise `IndexError`, which is a
   blocking fail-closed defect for this review slice.
5. Is this a live capture or encoded-media proof? No. No media or live process
   was launched; this is host evaluator evidence only.

## Verdict

**Round15 independent review: FAIL pending source correction and a readiness
receipt.** The shared cadence policy boundaries and non-index path hold in the
current host source, but loop7/loop14/stale/reorder adversarial inputs produce
an uncaught `IndexError` rather than a structured refusal. The retained writer
red logs are stale because the same four focused tests pass on the current
hashed source. Source-freeze/motion-review readiness was not evidenced by a
marker or handoff file at review time.

Open question: after the source owner fixes the positional `source_deltas`
contract, does a fresh motion-review freeze receipt identify the exact source
hash reviewed? Settling evidence is one new focused host run plus a receipt
that names the same three capture source hashes above.

## Frozen-source re-review

The writer supplied an explicit freeze. I verified the named hashes in the
worktree before rerunning the independent controls:

```
scripts/harness/kpharness/display_backends.py
bca12b48d48b9d9545b6dead2f5f8314b06ac3ff96958328183dd35da4e32575

tools/kpharness_capture_diagnostic_test.py
7bdc2df4ae3750a58660465340eaf352eb3d6f36b38a2fea1bcdf231100cda2d

tools/kpharness_gamescope_backend_test.py
ccb220b6058db9c818b2978b14e0c9644560578b882e4949160e1f4af07ce48c
```

The prior `IndexError` is fixed. `content_index_sequence()` now appends a
`None` sentinel for non-monotonic deltas and `content_level_sequence()` treats
that sentinel as an ordinary fixed-step fallback rather than indexing a
shortened vector. The exact source locations are
`display_backends.py:465-468` and `:546-560`.

The frozen boundary probe is saved as
`r15-independent-review/boundary_probe_frozen.out`. Results:

```
isolated_drop             passed; index passed; level passed; drop 0.0033333333333333335
accumulated_drop           failed; source_drop_ratio
excessive_maxgap           failed; source_gap and index_step_disagrees_with_elapsed_time
loop7                      failed; non_monotonic
loop14                     failed; non_monotonic
stale_replay               failed; non_monotonic and level failure
reorder                    failed; non_monotonic and source_drop_ratio
halfregion_bottom_freeze  failed; region_mismatch
non_index_game_policy      passed without index fields
```

The frozen focused unittest run is
`r15-independent-review/focused-unittest-frozen.out`: **5/5 passed**, covering
isolated drop, accumulated drop, excessive gap, duplicate acceptance, and
separated stale content.

claim: the frozen source now turns the prior crash into a structured refusal.

referent: `display_backends.py:465-468,546-560`; frozen boundary output above.

checked: loop7, loop14, stale replay, and reorder all returned `status=failed`
with no exception. Half-region returned `region_mismatch`; non-index game
policy returned `passed`.

verdict: holds. Confidence: high for the host evaluator and synthetic
adversarial rows. No encoded-media or live-game proof is claimed here.

### Frozen verdict

**Round15 independent review: PASS for the requested host-only boundary slice.**
The supplied freeze hashes match the source reviewed. The prior crash is fixed;
isolated drop remains within policy, accumulated drops and excessive max-gap
fail, non-index behavior remains green, and loop7/loop14/stale/reorder/
half-region cases refuse structurally.

Remaining evidence boundary: this review did not launch media, Wine, a game, or
live diagnostics, so it does not upgrade the result to production encoded-media
or live runtime proof.

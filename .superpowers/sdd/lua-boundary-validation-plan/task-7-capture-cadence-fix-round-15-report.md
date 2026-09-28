# Task 7 capture cadence correction, round 15

## Verdict

**PASS for the R15 host correction; integration gate remains conditional on the
existing live Gamescope/media acceptance.** The host content gate now accepts a
single validated source advance within the shared cadence budget, while it
rejects accumulated source loss, an overlarge source gap, and same-brightness
index advances. No live game, Wine, display, encoder, or media launch was used.

## Claim and checked referent

The checked referent is the current worktree
`/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`.
The one-drop failure recorded in `/tmp/kp-root-r14-one-drop.json` showed an
index gate pass with a legacy level gate failure. R15 binds level expectations
to the decoded source advance: a fresh index delta `d` expects `3*d mod 7`,
while an index repeat remains an optical duplicate. The index gate also
accumulates decoded dropped source frames and records the maximum source gap.
Both aggregate checks use the shared `gamescope-cadence-v1` thresholds (0.5%
drop ratio and 50 ms gap), with a small `1e-12` comparison guard for binary
floating point at an exact threshold. Aggregate failures are retained before
the bounded per-frame violation details.

## Evidence

The bounded command below was run from the stated worktree, with no product
build or live process:

```text
python3 -m py_compile scripts/harness/kpharness/display_backends.py \
  tools/kpharness_capture_diagnostic_test.py \
  tools/kpharness_gamescope_backend_test.py
python3 -m unittest tools.kpharness_capture_diagnostic_test -v
```

Result: **61 tests passed in 21.455 s**. The focused R15 cases also passed,
including a direct regression probe for loop7, loop14, stale replay, and
adjacent reorder inputs: each returned a structured failed result without an
exception.

* one source drop within policy: index and level gates pass;
* sustained `delta=2`: accumulated `source_drop_ratio` fails;
* one `delta=7` same-brightness jump: `source_gap` fails even while total
  ratio stays below 0.5%;
* pure duplicates and duplicate followed by one within-policy skip pass;
* all prior stale/loop/ambiguous and lifecycle criteria remain green in the
  full host suite.

The complete stdout/stderr receipt is
`/home/brunner56/kp-live-20260922/r15-focused-suite.log`, SHA-256
`955b23b9d8a08ffaa223c8fd22f31bd027f38b1845bff06d17e9eeba20f37b72`.

Source hashes at command start were:

```text
bca12b48d48b9d9545b6dead2f5f8314b06ac3ff96958328183dd35da4e32575  scripts/harness/kpharness/display_backends.py
7bdc2df4ae3750a58660465340eaf352eb3d6f36b38a2fea1bcdf231100cda2d  tools/kpharness_capture_diagnostic_test.py
ccb220b6058db9c818b2978b14e0c9644560578b882e4949160e1f4af07ce48c  tools/kpharness_gamescope_backend_test.py
347e2942fc5a3153fb88b410aaab372ee077f1122252ed6c5f9e802deca04d7b  docs/creative-runner.md
```

## Integration gate

This is a host correctness PASS only. Before K1 acceptance, the independent
Gamescope run must still provide the required retained master, canonical PTS
binding, full prior clean/drift/duplicate/skip family evidence, 34-second
production deadline and byte budget, and the existing cleanup/renderer/window
proof. This report supplies no live-media evidence and does not waive those
gates.

## Unsettled question

The production diagnostic must serialize the new index aggregate fields into
its retained receipt and the acceptance verifier must recompute them from the
hashed artifact. A future receipt that only reports the legacy level sequence
is insufficient even if the host suite remains green.

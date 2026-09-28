# Round15 offline encoded media review

Date: 2026-09-27. Host-only synthetic media evidence. No game, Wine, mpv,
X11, Gamescope, live diagnostic, or product edit was used. Encodes were serial
with bounded 90-second encode attempts, `libx264 ultrafast crf 28`, 1024x768,
60 FPS, production `PATTERN_GRAPH` barcode suffix (`index_bits=14`,
`cell=32`, `inset=6`, height 768), and production real ELF
`/home/linuxbrew/.linuxbrew/bin/ffprobe`. The probe used inherited
`/proc/self/fd/N`, actual `probe_frame_pts`, and an instrumentation wrapper
around `_bounded_probe_output` only to record elapsed time and raw byte count.

Durable driver: `run_offline.py`; one-pair driver: `run_drift.py`.
Durable outputs: `offline-results-run5-recovered.json` (eight concise run5 receipts), `run5.stdout`, `drift.stdout`, `drift_pair_receipt.json`, and `media-manifest.json`. The live `offline-results.json` was later overwritten by the isolated drift rerun; it is not used as the eight-case provenance source.
Media directory: `/tmp/kp-r15-offline-media`.

## Verified cases

| case | actual frames / PTS | probe seconds | raw bytes | content/index result |
|---|---:|---:|---:|---|
| healthy8 | 480 / 0.0..7.983333 | 34.1468 | 5,590,526 | PASS / PASS |
| half_frozen_bottom8_true | 480 / 0.0..7.983333 | 37.2771 | 5,577,691 | FAIL / FAIL (`region_mismatch`) |
| duplicate8 | 480 / 0.0..7.983333 | 28.0758 | 5,590,357 | PASS / PASS |
| single_skip8 | 480 / 0.0..7.983333 | 32.9155 | 5,590,586 | PASS / PASS |
| healthy34 | 2040 / 0.0..33.983333 | 164.2064 | 23,761,716 | PASS / PASS |
| slowq8 | 480 / 0.0..7.983333 | 39.4448 | 5,592,217 | PASS / PASS |
| fast4_8 | 480 / 0.0..7.983333 | 49.4115 | 5,593,163 | PASS / PASS |
| static8 | 480 / 0.0..7.983333 | 75.3289 | 5,589,564 | PASS / PASS |
| drift_pair8 | 480 / 0.0..7.983333 | 57.6709 | 5,593,018 | FAIL / FAIL (`index_step_disagrees_with_elapsed_time`) |

The 34-second probe was bounded by
`probe_deadline_seconds(2040)=438` seconds and the 64 MiB output cap; it
completed in 164.2064 seconds with 23,761,716 raw bytes. All listed probes
returned exactly 480 or 2040 production rows matching actual PTS counts.

Media SHA-256:

```
healthy8.mp4                 11e17868875d95a4b0fce0c7f42cbb56919ccaac37a1b5e7e79aca5375ec850b
duplicate8.mp4               7bccf104c1952d25d5d64facad47246ce4f867010e052beee7f69d9c6d064f51
single_skip8.mp4              37bdb44d2013f372624c9a18c9a618a273360c80772c2654bb7bcf3c27c2974e
half_frozen_bottom8_true.mp4  5fefdd44f94c416a3e0be466f994810c4665a0a19fbb972ac9536e6a97846bee
healthy34.mp4                5f60da86a7f83593e57119b829b943d5e703fc1dfdf46228fe8f18c12949d51e
drift_pair8.mp4              97537f4e8f08cdd2e533fa187529e0ebad801524271f14e6296335e86787e458
slowq8.mp4                   4994d49aca7ecc3048a88547135d4e6782dffcacc33a347f67230edbbebfeb35
fast4_8.mp4                  bd1dbf748bc917ab18411040aa270151476965806daa59c33fed165550bf0409
static8.mp4                  0bc1c641c687f930ca52077f483de40dbae6fc5407017c13e6411573606eea3b
```

The frozen half control is a distinct `half_frozen_bottom8_true.mp4` generated
with a 384-pixel bottom-half overlay. The older 32-pixel-band artifact remains
separate as `half_frozen_bottom8.mp4` and is not used for the true-half claim.

## Round13 family coverage

The exact retained family definitions were read from
`/home/brunner56/kp-live-20260922/r13-work/encode_r13.py`. The clean families
requested from that source were adapted with the current barcode suffix:

- native healthy: covered by `healthy8` and the required 34-second `healthy34`;
- `slowq`: covered by `slowq8`, PASS;
- `fast4`: covered by `fast4_8`, PASS;
- `static`: covered by `static8`, PASS;
- duplicate control: `duplicate8`, a real encoded one-frame duplicate, PASS;
- single skip control: `single_skip8`, a real encoded one-frame skip, PASS;
- one duplicate-then-skip drift pair: `drift_pair8`, real encoded control, FAIL
  with the production index timing disagreement.

The old `isodup_*` families replace frames 100, 250, and 400 and were not
claimed as within-policy healthy controls. Their repeated source loss over a
short acceptance window can exceed the shared 0.5% source-drop budget. The
prior Round13 loop7/loop14 synthetic refusals were not rerun here because the
frozen host review already independently proved them; this report claims only
the encoded families listed above.

## Claims and verdicts

claim: the production barcode and content evaluator pass healthy native,
slowq, fast4, and static encoded controls.

referent: `offline-results.json`, `run5.stdout`, and the four media hashes above.

checked: each actual probe returned 480 rows and matching actual PTS; each
content and index result was PASS.

verdict: holds. Confidence: high for these synthetic encoded controls; no live
capture claim.

claim: a true encoded half-frame freeze is refused through independent barcode
regions.

referent: `half_frozen_bottom8_true.mp4`, distinct hash above; its graph crops
and freezes the bottom 384 pixels, then overlays them onto the advancing top.

checked: production decoder returned 480 rows; evaluator returned FAIL with
`region_mismatch`.

verdict: holds. Confidence: high for this encoded synthetic shape.

claim: a single duplicate and a single skip remain within the shared source
policy, while the constructed duplicate-then-skip drift pair is rejected by
index timing.

referent: `duplicate8.mp4`, `single_skip8.mp4`, `drift_pair8.mp4` and the
per-case receipts above.

checked: duplicate and skip both PASS; drift pair FAIL with
`index_step_disagrees_with_elapsed_time` and measured source drop ratio
0.002777777777777778.

verdict: holds with the stated distinction. Confidence: medium-high: these are
actual encoded controls, but the filter construction is a bounded synthetic
proxy for the X11 capture path.

## Grill me

1. Was the 34-second timing measured on the actual production index decoder?
   Yes: 2040 rows, actual PTS, 164.2064 seconds, 23,761,716 raw bytes, under
   438 seconds and 64 MiB.
2. Was the half freeze really half-frame rather than only the barcode band?
   Yes: it was regenerated under the distinct `_true` filename with a 384-pixel
   crop and has its own hash; the older band-only artifact is excluded.
3. Did the clean family sweep cover every Round13 family? No. It covered native,
   slowq, fast4, static, one duplicate, one skip, and one drift pair. The
   `isodup_*`, loop, torn, and other adversarial families are explicitly not
   claimed here.
4. Did the duplicate-then-skip pair pass? No; it failed the shared timing
   cross-check. The result is reported as a rejected drift control, not
   misrepresented as a healthy pass.
5. Was any live surface touched? No.

Final verdict: the requested offline encoded evidence is complete for the
listed families. Healthy production controls PASS, encoded true-half freeze
FAILs structurally, and the 34-second decoder stays within both requested
bounds. Live capture remains a separate gate.

## Tolerance-fix recheck

Root updated the frozen evaluator to account for six-decimal FFprobe timestamp
rounding by adding `index_fps * 1e-6` to the per-step tolerance. The aggregate
source-drop ratio and maximum-gap checks were unchanged. Verified source hashes:

```
scripts/harness/kpharness/display_backends.py
7ae70093eb8967d9cd80b7b464ef98f1b002356f1c65234362d12f2ab47e57eb

tools/kpharness_capture_diagnostic_test.py
bfd9ce2d13045dc023aa5af6e9d14c903fa678e3ef33a09c53d80cd771d88a73
```

The retained `drift_pair8.mp4` was decoded again without re-encoding through
real ELF ffprobe and the updated production evaluator. Its independent receipt
is `drift_pair_receipt.json`. It now returns `eval_status=passed`,
`index_status=passed`, `source_drop_ratio=0.002777777777777778`, and
`maximum_source_gap_seconds=0.03333333333333333`, with no violations. The
actual decoded neighborhood remains duplicate at frame 60 followed by the
single source skip at frame 62, so this is the intended within-policy control.

The updated boundary test
`test_duplicate_then_skip_accepts_ffprobe_microsecond_pts` passes and includes
a stricter timestamp perturbation (`0.00001` seconds) that still produces
`index_step_disagrees_with_elapsed_time`. The focused tolerance run is
`tolerance-tests.out`: **3/3 passed**. Additional retained adversarial
negatives are in `adversarial-negatives-frozen.out`: **4/4 passed** for
accumulated drop, excessive max gap, stale content, and sequence failure.

The prior drift failure in the original table was the pre-fix result. The
corrected final interpretation is: duplicate, single skip, and the one
duplicate-then-skip pair all pass within the shared policy; stricter timing
beyond the timestamp uncertainty remains rejected. The original pre-fix receipt
and output remain preserved separately in `drift_pair_receipt.json` history
through the saved `inspect_drift.stdout`; no media was overwritten.


## Provenance repair

The media hashes in this report were regenerated from the retained files by the
script that wrote `media-manifest.json`; the manifest is the authoritative file
size and SHA-256 receipt. The original eight-case JSON results file was
overwritten by the isolated `run_drift.py` run. The eight current decoder
receipts remain recoverable, without invention, as the concise JSON lines in
`run5.stdout` and the normalized copy `offline-results-run5-recovered.json`
(healthy8, half_frozen_bottom8_true, duplicate8, single_skip8, healthy34,
slowq8, fast4_8, static8). The separate current drift result is preserved in
`drift_pair_receipt.json` and `inspect_drift_frozen.stdout`. The older pre-fix
drift receipt is not represented as a current result; its exact violation is
retained in `inspect_drift.stdout` and was superseded by the tolerance-fix
recheck.

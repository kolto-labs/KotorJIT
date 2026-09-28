# R15 root correctness review

Verdict: PASS for the source-bound host boundary slice. The retained-media and full offline family requirements are tracked separately.

Checked frozen display_backends.py SHA256 bca12b48d48b9d9545b6dead2f5f8314b06ac3ff96958328183dd35da4e32575. Current four-suite run: 296 tests in32.646s, OK(skipped=1); log r15-root-four-suites.log.

Independent exact-boundary probe kp-root-r15-boundaries.py/JSON verifies ratio0.005 passes,0.0050125313 fails; gap0.050passes,0.0666667fails; sustained delta2fails; same-brightness delta7fails even below aggregate ratio. Retained encoded media decoded through production31-stream index path: healthy8s PASS22.64s; loop7typed indexFAIL19.41s, no exception. Scripts/results kp-root-r15-media-review.py/JSON.

claim: Per-frame source advance closes the within-policy one-drop false rejection without allowing sustained loss.
referent: exact boundary probe and frozen four-suite run.
checked: source and executable Python checks, retained encoded healthy/loop7 media.
verdict: holds
confidence: high for these cases; full prior codec/drift/duplicate/skip families and34sdecoderbudget still delegated to offline-media review.

Grill me: Does this prove actual mpv/x11grab cadence? No. No display, Wine, game, or live diagnostic was launched. Does it prove all partial frame freezes? No. The existing dual-region adversarial probe proves region disagreement; an actually encoded half-frozen control is still pending.

## Encoded drift-pair follow-up: timestamp serialization boundary

The real encoded duplicate/skip pair exposed a false rejection missed by idealized PTS fixtures. At frame62, source index60→62 spans serialized PTS1.016667→1.033333: elapsed_frames=.9999600000000042, so abs(2-elapsed)=1.0000399999999958 exceeds the one-frame tolerance. Aggregate source_drop_ratio=.002777777777777778 and source gap=.03333333333333333 are within policy.

Root added a duplicate/skip regression with six-decimal PTS, confirmed it fails with the same timing reason, and changed only the per-transition numeric allowance to fps*1e-6 seconds-equivalent: subtracting two microsecond-rounded timestamps incurs at most one microsecond of uncertainty. A ten-microsecond perturbation must still fail. Drop ratio and gap limits remain unchanged.

Current full diagnostic suite62 tests PASS; backend155 tests PASS with1 skip. Logs `r15-pts-red.log`, `r15-pts-green.log`, `r15-pts-backend.log`; current source hashes `r15-pts-source-hashes.json`. Independent reviewer decoded the retained drift_pair8 media again without encoding and now reports index/content PASS; focused stricter-boundary and adversarial tests PASS. No live display claim follows. The 34-second offline probe remains budget evidence; no additional expensive decode was required for unchanged probe code.

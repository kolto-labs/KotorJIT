# Capture round 14 independent adversarial review

Verdict: FAIL pending round15 skip-tolerance correction and full replayable family coverage. No display/game/live run.

Root independently decoded retained healthy and7-loop8s 1024x768 media through production probe_frame_content with14-bit two-region crops and the production policy. Healthy passed (42.85s including PTS probe); loop7 failed specifically capture_content_index with52 violations (32.19s). Script/source hashes/media hashes/evaluator JSON: kp-root-r14-media-review.py/.json beside this report. Input media remains machine-local /tmp/kp-r14-8s-2291a5l9; OS-managed retention.

Independent synthetic evaluator controls: clean passes; loop7/14/21/70, stale frame with correct periodic brightness, same-level reorder and frozen bottom region all reject with typed capture_content_index. Receipt kp-root-r14-adversarial-synthetic.json. This is evaluator proof only for these shapes.

Required round14 within-policy skip family fails: remove frame350 from600 source frames with source PTS preserved; acceptance1..9s has one missing source state (~0.2% loss) and0.0333s maximum gap, both within shared cadence thresholds. Index check passes with estimated_dropped_source_frames1, but legacy level check rejects brightness step6. Receipt kp-root-r14-one-drop.json. Fix must correlate brightness with validated source-index advance while enforcing aggregate source-drop and maximum-source-gap budgets; simply relaxing individual step tolerance would admit sustained loss.

Prior clean/drift/duplicate/skip family coverage and actual encoded partial-freeze/reorder/stale proof still need completion. The existing decoded-array half-freeze test is not media-path proof. Root inspected btrfs suite raw logs under /tmp/r14-btrfs-* and confirmed terminal OK (39/41/155+1skip/57); this resolves the writer report's contradictory final note but does not replace media gates.

No diagnostic launch authorized. Host proof must be repeated/reviewed for round15 source before any snapshot/live attempt.

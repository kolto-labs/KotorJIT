"""Round 11: re-label cached production-probe rows and summarize the noise-floor separation.

Labels follow FFmpeg's fps filter (round=near): input frame j of a source at rate r
lands in output slot floor(j * 60 / r + 0.5); an output frame is fresh iff it
starts a slot, and a duplicate otherwise. Reads <name>.rows.json written by
calibrate_noise_floor.py (production probe_frame_content/probe_frame_pts).
"""
import json, math, sys
from pathlib import Path
out = Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp/kp-r11-cal')
RATES = {'testsrc2_60': 60, 'testsrc2_30_to_60': 30, 'testsrc2_20_to_60': 20, 'testsrc2_6_to_60': 6,
         'testsrc2_59_to_60': 59, 'testsrc2_15_to_60': 15, 'testsrc2_45_to_60': 45,
         'testsrc_60': 60, 'testsrc_30_to_60': 30}
fresh_all, dup_all = [], []
for name, rate in RATES.items():
    path = out / f'{name}.rows.json'
    if not path.exists():
        print(json.dumps({name: 'missing'})); continue
    rows = json.loads(path.read_text())['rows']
    slots = {math.floor(j * 60 / rate + .5) for j in range(len(rows) * rate // 60 + 2)}
    fresh, dup = [], []
    for i in range(1, len(rows)):
        value = max(rows[i]['ydif'], rows[i]['udif'], rows[i]['vdif'])
        (fresh if i in slots else dup).append(value)
    if name.startswith('testsrc2_'):  # the diagnostic pattern; testsrc rows are shown only as contrast
        fresh_all += fresh; dup_all += dup
    print(json.dumps({name: {'fresh': len(fresh), 'dup': len(dup),
        'fresh_min': round(min(fresh), 4) if fresh else None, 'dup_max': round(max(dup), 4) if dup else None}}))
floor = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
print(json.dumps({'ALL_testsrc2': {'fresh_frames': len(fresh_all), 'dup_frames': len(dup_all),
    'fresh_min_maxdif': round(min(fresh_all), 4), 'dup_max_maxdif': round(max(dup_all), 4),
    'geometric_midpoint': round(math.sqrt(min(fresh_all) * max(dup_all)), 4),
    'floor': floor, 'margin_above_dup_max': round(floor / max(dup_all), 2),
    'margin_below_fresh_min': round(min(fresh_all) / floor, 2),
    'dups_above_floor': sum(v > floor for v in dup_all), 'fresh_at_or_below_floor': sum(v <= floor for v in fresh_all)}}))

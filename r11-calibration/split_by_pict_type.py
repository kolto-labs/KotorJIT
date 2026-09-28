"""Split the calibration's duplicate/fresh max(Y,U,V DIF) by coded picture type (I vs P)."""
import json, math, subprocess, sys
from pathlib import Path
out = Path('/tmp/kp-r11-cal'); FFPROBE = '/home/linuxbrew/.linuxbrew/bin/ffprobe'
RATES = {'testsrc2_30_to_60': 30, 'testsrc2_20_to_60': 20, 'testsrc2_6_to_60': 6, 'testsrc2_59_to_60': 59,
         'testsrc2_15_to_60': 15, 'testsrc2_45_to_60': 45, 'testsrc2_60': 60}
total = {'I': [], 'P': []}
for name, rate in RATES.items():
    rows = json.loads((out / f'{name}.rows.json').read_text())['rows']
    probe = subprocess.run([FFPROBE, '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'frame=pict_type',
                            '-of', 'json', str(out / f'{name}.mp4')], capture_output=True, text=True, check=True, timeout=1800)
    kinds = [frame['pict_type'] for frame in json.loads(probe.stdout)['frames']]
    assert len(kinds) == len(rows), (name, len(kinds), len(rows))
    slots = {math.floor(j * 60 / rate + .5) for j in range(len(rows) * rate // 60 + 2)}
    split = {}
    for i in range(1, len(rows)):
        value = max(rows[i]['ydif'], rows[i]['udif'], rows[i]['vdif'])
        key = ('fresh' if i in slots else 'dup', kinds[i])
        split.setdefault(key, []).append((value, i))
        if key[0] == 'dup':
            total.setdefault(kinds[i], []).append(value)
    print(json.dumps({name: {f'{a}_{b}': {'n': len(v), 'max' if a == 'dup' else 'min':
                              (max(v) if a == 'dup' else min(v)), 'at_index': (max(v) if a == 'dup' else min(v))[1]}
                             for (a, b), v in sorted(split.items())},
                      'I_frame_indices': [i for i, k in enumerate(kinds) if k == 'I']}, default=str))
print(json.dumps({'dup_max_by_pict_type': {k: (max(v) if v else None) for k, v in total.items()},
                  'dup_count_by_pict_type': {k: len(v) for k, v in total.items()}}))

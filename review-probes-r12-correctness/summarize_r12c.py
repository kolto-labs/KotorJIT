import json, sys
from pathlib import Path
OUT = Path(__file__).parent / 'cal'
dups, fresh, idups = [], [], []
print(f'{"family":24} {"fresh n/min":>16} {"dup n/max":>14} {"I-dup n/max":>12}  verdict')
for f in sorted(OUT.glob('*.json')):
    d = json.load(open(f)); L = d['labels']
    fr = [l for l in L if l['fresh']]; du = [l for l in L if not l['fresh']]; idu = [l for l in du if l['key'] == 'I']
    dups += [(l['v'], d['name'], l) for l in du]; fresh += [(l['v'], d['name'], l) for l in fr]; idups += [(l['v'], d['name'], l) for l in idu]
    fm = min((l['v'] for l in fr), default=None); dm = max((l['v'] for l in du), default=None); im = max((l['v'] for l in idu), default=None)
    st, ratio, fails, sep = d['diag']
    print(f'{d["name"]:24} {len(fr):5}/{fm if fm is None else round(fm, 3)!s:>10} {len(du):4}/{dm if dm is None else round(dm, 4)!s:>9} '
          f'{len(idu):3}/{im if im is None else round(im, 4)!s:>8}  {st} {ratio:.4f} {[x.split(":")[0] for x in fails]} '
          f'{sep["status"]} b/i/a={sep["below_band"]}/{sep["inside_band"]}/{sep["above_band"]}')
excl = ('skip7', 'pingpong', 'cycle3')   # families whose "fresh" frames are deliberately level-aliased or stale
fr_cal = [x for x in fresh if not x[1].startswith(excl)]
print('\nALL duplicates n=%d max=%.4f at %s %s' % (len(dups), max(dups, key=lambda x: x[0])[0], max(dups, key=lambda x: x[0])[1], max(dups, key=lambda x: x[0])[2]))
print('I-frame duplicates n=%d max=%.4f at %s %s' % (len(idups), max(idups, key=lambda x: x[0])[0], max(idups, key=lambda x: x[0])[1], max(idups, key=lambda x: x[0])[2]))
print('fresh (calibration families, excl skip7/pingpong/cycle3) n=%d min=%.4f at %s %s' % (len(fr_cal), min(fr_cal, key=lambda x: x[0])[0], min(fr_cal, key=lambda x: x[0])[1], min(fr_cal, key=lambda x: x[0])[2]))
dm, fm = max(dups, key=lambda x: x[0])[0], min(fr_cal, key=lambda x: x[0])[0]
print('margins: floor/dupmax=%.3f freshmin/floor=%.3f  band-edge 1.3/dupmax=%.3f  freshmin/11.7=%.3f' % (3.9 / dm, fm / 3.9, 1.3 / dm, fm / 11.7))
print('dups > 1.3:', [(round(v, 4), n, l['i'], l['key']) for v, n, l in dups if v > 1.3])
print('calibration fresh < 11.7:', [(round(v, 4), n, l['i']) for v, n, l in fr_cal if v < 11.7])
print('I-dup by level of repeated frame:', {lv: round(max([v for v, n, l in idups if l['lvl'] == lv], default=-1), 4) for lv in range(-3, 4)})
s7 = [x for x in fresh if x[1].startswith('skip7')]
if any(l['dist'] % 7 == 0 for v, n, l in s7):
  print('skip7 level-aliased fresh (dist %% 7 == 0): n=%d min=%.4f max=%.4f' % (
    sum(1 for v, n, l in s7 if l['dist'] % 7 == 0), min(v for v, n, l in s7 if l['dist'] % 7 == 0), max(v for v, n, l in s7 if l['dist'] % 7 == 0)))

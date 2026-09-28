#!/usr/bin/env python3
"""Mandatory post-run gate for V1 and L1 (offline; reads a finished run directory only).

  python3 -I -S -B postrun-gate.py --route <route.toml> --run-dir <runs/STAMP> [--size 1024x768]

FAIL (exit 1) unless all hold:
  F1  boot-attempts.json: max_boot_attempts == 1, launch_count == 1, one attempt, outcome "channel".
      creative-run.json boot_attempts: env == "1" (KP_MAX_BOOT_ATTEMPTS was set) and acceptance_eligible.
  F2  every screenshot step of the route has a report.json entry with the same index and label,
      status "ok", a path (not "no screenshot taken"), and that file exists, is non-empty and
      has a PNG or PPM header of the expected size.
A missing still is a run failure. There is no master-frame fallback.
Why offline: a route step cannot check it. Scenario._screenshot returns status "ok" even when
Shooter.take returns None, and take() unlinks the in-game PPM after conversion, so the only
copy is host-side under run_dir/shots, which no step kind can read.
"""
import argparse, json, pathlib, struct, sys, tomllib

def image_size(path):
    with open(path, 'rb') as f:
        head = f.read(64)
    if head[:8] == b'\x89PNG\r\n\x1a\n' and head[12:16] == b'IHDR':
        return struct.unpack('>II', head[16:24])
    if head[:2] == b'P6':
        tok = head.split()
        return int(tok[1]), int(tok[2])
    return None

def gate(route, run_dir, size):
    problems, stills = [], []
    run_dir = pathlib.Path(run_dir)
    # F1
    try:
        boot = json.loads((run_dir / 'boot-attempts.json').read_text())
        if boot.get('max_boot_attempts') != 1: problems.append('boot max_boot_attempts=%r' % boot.get('max_boot_attempts'))
        if boot.get('launch_count') != 1: problems.append('boot launch_count=%r' % boot.get('launch_count'))
        if len(boot.get('attempts') or []) != 1: problems.append('boot attempts=%d' % len(boot.get('attempts') or []))
        if boot.get('outcome') != 'channel': problems.append('boot outcome=%r' % boot.get('outcome'))
    except (OSError, ValueError) as e:
        boot = None; problems.append('boot-attempts.json unreadable: %s' % e)
    try:
        cb = json.loads((run_dir / 'creative-run.json').read_text()).get('boot_attempts') or {}
        if cb.get('env') != '1': problems.append('KP_MAX_BOOT_ATTEMPTS in driver env=%r (need "1")' % cb.get('env'))
        if cb.get('acceptance_eligible') is not True: problems.append('creative boot_attempts not eligible: %r' % cb.get('refusal'))
    except (OSError, ValueError) as e:
        problems.append('creative-run.json unreadable: %s' % e)
    # F2
    steps = tomllib.loads(pathlib.Path(route).read_text())['step']
    want = [(i + 1, s.get('label', 'screenshot')) for i, s in enumerate(steps) if s.get('screenshot') is True]
    try:
        rep = {s['index']: s for s in json.loads((run_dir / 'report.json').read_text())['steps']}
    except (OSError, ValueError, KeyError) as e:
        rep = {}; problems.append('report.json unreadable: %s' % e)
    for index, label in want:
        s = rep.get(index); entry = {'index': index, 'label': label, 'ok': False}
        stills.append(entry)
        if s is None: problems.append('still step %d not in report (run stopped earlier)' % index); continue
        if s.get('step') != label: problems.append('step %d label %r != %r' % (index, s.get('step'), label)); continue
        detail = str(s.get('detail', '')).split(';')[0].strip()
        if s.get('status') != 'ok' or not detail or detail == 'no screenshot taken':
            problems.append('still step %d: %s / %s' % (index, s.get('status'), detail or 'no detail')); continue
        path = pathlib.Path(detail)
        if not path.is_file(): path = run_dir / 'shots' / path.name
        if not path.is_file(): problems.append('still step %d: file missing %s' % (index, detail)); continue
        n = path.stat().st_size; dims = image_size(path) if n else None
        entry.update(path=str(path), bytes=n, size=list(dims) if dims else None)
        if n == 0: problems.append('still step %d: empty file' % index); continue
        if dims != size: problems.append('still step %d: size %r != %r' % (index, dims, size)); continue
        entry['ok'] = True
    return {'verdict': 'PASS' if not problems else 'FAIL', 'problems': problems,
            'boot': {k: boot.get(k) for k in ('max_boot_attempts', 'max_boot_attempts_source', 'launch_count', 'outcome')} if boot else None,
            'stills': stills}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--route', required=True); ap.add_argument('--run-dir', required=True); ap.add_argument('--size', default='1024x768')
    o = ap.parse_args()
    out = gate(o.route, o.run_dir, tuple(int(x) for x in o.size.split('x')))
    print(json.dumps(out, indent=1))
    return 0 if out['verdict'] == 'PASS' else 1

if __name__ == '__main__':
    sys.exit(main())

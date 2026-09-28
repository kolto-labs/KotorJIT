#!/usr/bin/env python3
"""Mandatory post-run gate for V1 and L1 (offline; reads finished run directories, and writes
back only its own postrun-gate-result.json receipt into the run-dir it just gated).

  python3 -I -S -B postrun-gate.py --route <route.toml> --run-dir <runs/STAMP> \
      [--size 1024x768] [--require-l1 <L1 runs/STAMP>]

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

REFUSE (exit 1, one line, before any F1/F2 verdict) unless, for an acceptance route (any route
other than the checked-in l1-camera-diagnostic.toml, identified by content hash, not by name):
  R0  --require-l1 <L1 run-dir> is given at all. Round 2's review (Finding I1) found that a V1
      run with zero trace of L1 having ever happened still printed PASS. This is the fix: a V1
      check with no L1 path now refuses instead of silently skipping the L1 precondition.
  R1  <L1 run-dir>/postrun-gate-result.json exists, its own recorded verdict is "PASS", and its
      own recorded route_sha256 equals the checked-in l1-camera-diagnostic.toml's hash. This is
      the receipt this same script writes into a run-dir every time it completes a full F1/F2
      gate on that run-dir (see write_receipt below) -- i.e. someone actually ran this gate *on
      the L1 route* against the L1 run-dir, and it passed.
  R2  <L1 run-dir>/creative-run.json's route_source.sha256 -- the hash the WT runner itself took
      of the route file at launch time (creative.py: route_copy / input_before), not merely the
      path an operator typed -- equals the sha256 of the l1-camera-diagnostic.toml checked into
      this directory right now. This is what proves *this* L1 run executed the checked-in L1
      route, rather than trusting a label.
  R3  <L1 run-dir>/boot-attempts.json (read directly, independent of R1's cached receipt, in case
      the receipt is stale) shows launch_count == 1.
  R4  <L1 run-dir>/admission.json exists and its recorded measurements satisfy prep-report.md
      section 5b's admission rule A1-A5, re-derived here against the stated thresholds (not just
      trusted as booleans, and rejecting non-finite/missing fields rather than treating them as
      zero): A1 (L1's own report.json reached step 47 "ok"), A2 (beh=chase/ps=-1 at R1a *and*
      R3a, dolly identical R1-R4), A3 (stills 3 and 4 each 192-230 px), A4 (still 3->4 feature
      motion <=4px in both x and y with the row span within +/-2px, and R4-vs-R3 idsame=1 with
      dcfg/dq/dp38/dp50 <=1e-4), A5 (the same rule applied to the 1->2 / R2-vs-R1 pair, with the
      "moved but fields still show motion" escape only when the feature moved >4px in x or y).
  R6  A6 (L1 and V1 share the build): <L1 run-dir> and the run-dir being gated each have a
      creative-run.json 'runtime' map (filename -> sha256 of the deployed runtime file,
      creative.py:326); every filename recorded for L1 must also appear for V1 with the same
      sha256. This does not check that L1 and V1 also share the *same $SNAP* (harness snapshot)
      -- no run record here identifies which $SNAP produced a run; that half of P6 is still an
      operator discipline, not a machine gate (Grill me).
  R5  <L1 run-dir>/report.json 'finished' is a positive number, the run-dir being gated has a
      boot-attempts.json whose first attempt has a positive 'started', and L1 finished strictly
      before this run started (run records, not filesystem mtimes).
"""
import argparse, json, pathlib, struct, sys, time, tomllib

HERE = pathlib.Path(__file__).resolve().parent
L1_ROUTE = HERE / 'l1-camera-diagnostic.toml'

def sha(path):
    import hashlib
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

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

def write_receipt(route, run_dir, out):
    """The audit trail R1 reads back later: proof this gate actually ran on run_dir and what
    it found. Written for every completed (non-REFUSEd) gate() call, PASS or FAIL alike."""
    receipt = {'verdict': out['verdict'], 'route': str(pathlib.Path(route).resolve()),
               'route_sha256': sha(route), 'run_dir': str(pathlib.Path(run_dir).resolve()),
               'checked_at': time.time()}
    (pathlib.Path(run_dir) / 'postrun-gate-result.json').write_text(json.dumps(receipt, indent=1))
    return receipt

def _num(x):
    """A finite float, or None. Missing, non-numeric, NaN and +-inf are all None -- never
    silently coerced to 0, and never allowed to slip past a `> threshold` check by being
    unorderable (NaN compares False against everything, which would otherwise pass every gate)."""
    import math
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None

def _require(d, key):
    """A finite number for d[key], or a problem string naming the missing/bad field."""
    if key not in d:
        return None, 'missing field %r' % key
    v = _num(d[key])
    if v is None:
        return None, 'field %r is not a finite number: %r' % (key, d[key])
    return v, None

def check_admission(adm, l1_report):
    """Re-derive prep-report.md section 5b's A1-A5 from recorded measurements, rather than
    trusting a boolean. A6 (build match) is checked separately in check_build_match, since it
    needs both run-dirs' creative-run.json, not just admission.json. Returns a list of problem
    strings; empty means all of A1-A5 hold. Every numeric field is required and must be finite:
    a missing or NaN value is a problem, never treated as 0 or as "no motion"."""
    problems = []
    # A1: L1 completed step 47 (settle, baseline and +180 rehearsal all ok).
    if not l1_report.get('ok', False):
        problems.append('A1: L1 report.json ok=%r' % l1_report.get('ok'))
    steps = {s.get('index'): s for s in (l1_report.get('steps') or [])}
    s47 = steps.get(47)
    if not s47 or s47.get('status') != 'ok':
        problems.append('A1: L1 step 47 status=%r' % (s47.get('status') if s47 else None))
    # A2: R1a and R3a both read beh=chase ps=-1; dolly identical across R1-R4.
    if adm.get('beh_r1a') != 'chase' or adm.get('ps_r1a') != -1:
        problems.append('A2: R1a beh=%r ps=%r (need chase/-1)' % (adm.get('beh_r1a'), adm.get('ps_r1a')))
    if adm.get('beh_r3a') != 'chase' or adm.get('ps_r3a') != -1:
        problems.append('A2: R3a beh=%r ps=%r (need chase/-1)' % (adm.get('beh_r3a'), adm.get('ps_r3a')))
    dolly = adm.get('dolly')
    if not (isinstance(dolly, list) and len(dolly) == 4):
        problems.append('A2: dolly is not a 4-element list: %r' % (dolly,))
    else:
        nums = [_num(d) for d in dolly]
        if any(n is None for n in nums):
            problems.append('A2: dolly has a missing/non-finite value: %r' % (dolly,))
        elif len({round(n, 9) for n in nums}) != 1:
            problems.append('A2: dolly not identical across R1-R4: %r' % (dolly,))
    # A3: stills 3 and 4 each measure 192-230 px.
    h3, p3 = _require(adm, 'height_still3')
    if p3: problems.append('A3: ' + p3)
    elif not (192 <= h3 <= 230): problems.append('A3: still 3 height=%r not in 192-230' % adm.get('height_still3'))
    h4, p4 = _require(adm, 'height_still4')
    if p4: problems.append('A3: ' + p4)
    elif not (192 <= h4 <= 230): problems.append('A3: still 4 height=%r not in 192-230' % adm.get('height_still4'))
    # A4: still 3->4 feature motion (dx and dy each within the band, |row_span_delta| <= 2), and
    # the R4-vs-R3 equality rule.
    problems += _feature_band_problems('A4', adm.get('feature_disp_3_4'), max_xy=4, max_span=2)
    problems += _equality_rule_problems('A4', adm.get('r4_vs_r3'))
    # A5: same check on the 1->2 / R2-vs-R1 pair, with the "fields see motion" escape.
    f12 = adm.get('feature_disp_1_2')
    if not isinstance(f12, dict):
        problems.append('A5: feature_disp_1_2 missing')
    else:
        dx12, px = _require(f12, 'dx'); dy12, py = _require(f12, 'dy')
        if px or py:
            problems.append('A5: feature_disp_1_2 %s' % (px or py))
        else:
            r21 = adm.get('r2_vs_r1')
            if not isinstance(r21, dict):
                problems.append('A5: r2_vs_r1 missing')
            elif abs(dx12) > 4 or abs(dy12) > 4:
                deltas = [_num(r21.get(k)) for k in ('dq', 'dp38', 'dp50')]
                if any(d is None for d in deltas):
                    problems.append('A5: feature 1->2 moved >4px but dq/dp38/dp50 has a missing/non-finite value: %r' % r21)
                elif not any(d != 0.0 for d in deltas):
                    problems.append('A5: feature 1->2 moved >4px but dq/dp38/dp50 are all zero: %r' % r21)
            else:
                problems += _equality_rule_problems('A5', r21, context='feature 1->2 did not move >4px, so R2-vs-R1')
    return problems

def _feature_band_problems(label, f, *, max_xy, max_span):
    if not isinstance(f, dict):
        return ['%s: feature displacement missing' % label]
    problems = []
    for key, limit in (('dx', max_xy), ('dy', max_xy)):
        v, p = _require(f, key)
        if p: problems.append('%s: feature %s' % (label, p))
        elif abs(v) > limit: problems.append('%s: feature %s=%r exceeds %spx' % (label, key, f.get(key), limit))
    v, p = _require(f, 'row_span_delta')
    if p: problems.append('%s: feature %s' % (label, p))
    elif abs(v) > max_span: problems.append('%s: feature row_span_delta=%r exceeds %spx' % (label, f.get('row_span_delta'), max_span))
    return problems

def _equality_rule_problems(label, delta, *, context=None):
    prefix = '%s: %s equality rule' % (label, context) if context else '%s: equality rule' % label
    if not isinstance(delta, dict):
        return ['%s failed: missing' % prefix]
    if delta.get('idsame') != 1:
        return ['%s failed: idsame=%r (need 1)' % (prefix, delta.get('idsame'))]
    problems = []
    for k in ('dcfg', 'dq', 'dp38', 'dp50'):
        v, p = _require(delta, k)
        if p: problems.append('%s failed: %s' % (prefix, p))
        elif v > 1e-4: problems.append('%s failed: %s=%r exceeds 1e-4' % (prefix, k, delta.get(k)))
    return problems

def check_build_match(l1_dir, run_dir):
    """A6: L1 and V1 share the build, checked via the runtime files the WT runner itself hashed
    and deployed (creative-run.json 'runtime': {filename: {'sha256': ...}}), not via session.build
    (a status string the game reports, not necessarily a content hash). Returns a problem string
    or None. Does not check that L1 and V1 share the same $SNAP: no run record here identifies
    which harness snapshot produced a run (see the docstring's R6 note and Grill me)."""
    try:
        l1_cr = json.loads((pathlib.Path(l1_dir) / 'creative-run.json').read_text())
    except (OSError, ValueError) as e:
        return 'A6: L1 creative-run.json unreadable: %s' % e
    try:
        v1_cr = json.loads((pathlib.Path(run_dir) / 'creative-run.json').read_text())
    except (OSError, ValueError) as e:
        return 'A6: run-dir creative-run.json unreadable: %s' % e
    l1_runtime, v1_runtime = l1_cr.get('runtime'), v1_cr.get('runtime')
    if not isinstance(l1_runtime, dict) or not l1_runtime:
        return 'A6: L1 creative-run.json has no runtime hashes recorded'
    if not isinstance(v1_runtime, dict) or not v1_runtime:
        return 'A6: run-dir creative-run.json has no runtime hashes recorded'
    for name, entry in l1_runtime.items():
        l1_sha = (entry or {}).get('sha256')
        v1_sha = (v1_runtime.get(name) or {}).get('sha256')
        if not l1_sha or l1_sha != v1_sha:
            return 'A6: build mismatch on runtime file %r: L1 sha256=%r V1 sha256=%r' % (name, l1_sha, v1_sha)
    return None

def check_require_l1(route, run_dir, l1_dir):
    """Returns None if the L1 precondition holds, else a short one-line reason. Every check here
    reads the L1 run's own records directly (not only the cached receipt), per the round-2 review
    (Finding I1): the point is to make F3's 'BLOCKING' word executable, the same way F1 and F2
    already are."""
    l1_dir = pathlib.Path(l1_dir)
    if not L1_ROUTE.is_file():
        return 'checked-in l1-camera-diagnostic.toml missing at %s' % L1_ROUTE
    l1_route_hash = sha(L1_ROUTE)
    # R1: L1's own gate result exists, passed, and was a check of the L1 route (not some other
    # route pointed at this run-dir by mistake).
    try:
        receipt = json.loads((l1_dir / 'postrun-gate-result.json').read_text())
    except (OSError, ValueError) as e:
        return 'L1 gate receipt unreadable: %s' % e
    if receipt.get('verdict') != 'PASS':
        return 'L1 gate did not pass: verdict=%r' % receipt.get('verdict')
    if receipt.get('route_sha256') != l1_route_hash:
        return 'L1 gate receipt was for a different route (route_sha256=%r != %r)' % (receipt.get('route_sha256'), l1_route_hash)
    # R2: L1's *recorded* route hash (from the runner itself, creative-run.json route_source,
    # not the receipt) equals the currently checked-in l1-camera-diagnostic.toml.
    try:
        cr = json.loads((l1_dir / 'creative-run.json').read_text())
    except (OSError, ValueError) as e:
        return 'L1 creative-run.json unreadable: %s' % e
    recorded = ((cr.get('route_source') or {}).get('sha256'))
    if recorded != l1_route_hash:
        return 'L1 route hash %r != checked-in l1-camera-diagnostic.toml %r' % (recorded, l1_route_hash)
    # R3: launch_count == 1, read directly (independent of the receipt, in case it is stale).
    try:
        boot = json.loads((l1_dir / 'boot-attempts.json').read_text())
    except (OSError, ValueError) as e:
        return 'L1 boot-attempts.json unreadable: %s' % e
    if boot.get('launch_count') != 1:
        return 'L1 boot-attempts.json launch_count=%r (need 1)' % boot.get('launch_count')
    # R4: the admission measurements (A1-A5) are recorded as passing.
    try:
        adm = json.loads((l1_dir / 'admission.json').read_text())
    except (OSError, ValueError) as e:
        return 'L1 admission.json unreadable: %s' % e
    try:
        l1_report = json.loads((l1_dir / 'report.json').read_text())
    except (OSError, ValueError) as e:
        return 'L1 report.json unreadable: %s' % e
    admission_problems = check_admission(adm, l1_report)
    if admission_problems:
        return 'admission rule failed: %s' % admission_problems[0]
    # R6: A6, build match via runtime file hashes (not session.build).
    build_problem = check_build_match(l1_dir, run_dir)
    if build_problem:
        return build_problem
    # R5: L1 finished strictly before this run started (run records, not mtimes).
    l1_finished = _num(l1_report.get('finished'))
    if l1_finished is None or l1_finished <= 0:
        return 'L1 report.json finished=%r (no completion time recorded)' % l1_report.get('finished')
    try:
        v1_boot = json.loads((pathlib.Path(run_dir) / 'boot-attempts.json').read_text())
    except (OSError, ValueError) as e:
        return 'run-dir boot-attempts.json unreadable: %s' % e
    attempts = v1_boot.get('attempts') or []
    v1_started = _num(attempts[0].get('started')) if attempts else None
    if v1_started is None or v1_started <= 0:
        return 'this run boot-attempts.json attempts[0].started=%r (no launch time recorded)' % (attempts[0].get('started') if attempts else None)
    if not (l1_finished < v1_started):
        return 'L1 finished (%r) did not happen before this run started (%r)' % (l1_finished, v1_started)
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--route', required=True); ap.add_argument('--run-dir', required=True); ap.add_argument('--size', default='1024x768')
    ap.add_argument('--require-l1', default=None, help='run-dir of a prior passing L1 diagnostic; mandatory for any route other than l1-camera-diagnostic.toml itself')
    o = ap.parse_args()
    size = tuple(int(x) for x in o.size.split('x'))

    is_l1_route = L1_ROUTE.is_file() and sha(o.route) == sha(L1_ROUTE)
    if not is_l1_route:
        if not o.require_l1:
            print('REFUSE: missing-l1: acceptance route %s requires --require-l1 <L1 run-dir> (round-2 Finding I1: '
                  'a V1 check with no L1 path must refuse, not silently pass)' % o.route)
            return 1
        try:
            reason = check_require_l1(o.route, o.run_dir, o.require_l1)
        except Exception as e:
            # admission.json (and the other L1 records) are hand-produced. A malformed one (not
            # a dict, a list, null, ...) must still refuse in one line, not a Python traceback.
            print('REFUSE: l1-precondition: unreadable record: %s: %s' % (type(e).__name__, e))
            return 1
        if reason is not None:
            print('REFUSE: l1-precondition: %s' % reason)
            return 1

    out = gate(o.route, o.run_dir, size)
    write_receipt(o.route, o.run_dir, out)
    print(json.dumps(out, indent=1))
    return 0 if out['verdict'] == 'PASS' else 1

if __name__ == '__main__':
    sys.exit(main())

"""Round-2 race probes. Fake trees only. Every probe catches its own refusal and cleanup always runs."""
import sys, os, json, hashlib, zipfile, shutil, threading, time, collections, traceback
from pathlib import Path
sys.dont_write_bytecode = True
W = '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W + '/tools'); sys.path.insert(0, W + '/scripts/harness')
import package_creative_harness_test as T
B = T.B
ROOT = Path('/home/brunner56/kp-live-20260922/review-probes-scanner/prior/race')
TARGET = 'scripts/examples/cursed/10_rancor.lua'


def rm(path):
    if not os.path.lexists(path):
        return
    if os.path.islink(path) or not os.path.isdir(path):
        os.unlink(path); return
    shutil.rmtree(path, ignore_errors=True)


def fresh(name):
    base = ROOT / name; rm(base); base.mkdir(parents=True)
    src = T.fake_tree(base / 'src')
    prov = T.provenance_for(src, base / 'prov.json')
    return base, src, prov


def shipped(r, rel=TARGET):
    return zipfile.ZipFile(r['zip']).read(B.TOP + '/' + rel)


def attempt(label, fn):
    try:
        print(label, '->', fn(), flush=True)
    except Exception as e:
        print(label, '-> REFUSED', type(e).__name__, str(e)[:160], flush=True)


rm(ROOT); ROOT.mkdir(parents=True)
real_clean = B.clean_bytes

# 1) prior race: tampered at staging read, reverted before any later read
def prior():
    base, src, prov = fresh('prior')
    orig = (src / TARGET).read_bytes()
    (src / TARGET).write_bytes(b'-- TAMPERED in window\n')
    def swap(rel, data):
        out = real_clean(rel, data)
        if rel == TARGET:
            (src / TARGET).write_bytes(orig)
        return out
    B.clean_bytes = swap
    try:
        r = B.build(src, base / 'out', provenance=prov)
        return f'BUILT shipped={shipped(r)!r}'
    finally:
        B.clean_bytes = real_clean
attempt('prior_edit_reverted_after_staging', prior)

# 2) edit after staging and leave it: must refuse at the final re-read
def edit_left():
    base, src, prov = fresh('edit_left')
    def swap(rel, data):
        out = real_clean(rel, data)
        if rel == TARGET:
            (src / TARGET).write_bytes(b'-- edited after staging\n')
        return out
    B.clean_bytes = swap
    try:
        r = B.build(src, base / 'out', provenance=prov)
        return f'BUILT shipped={shipped(r)!r}'
    finally:
        B.clean_bytes = real_clean
attempt('edit_after_staging_left', edit_left)

# 3) edit after staging, reverted before the final re-read: bytes that ship must be the bound ones
def edit_revert_late():
    base, src, prov = fresh('edit_revert_late')
    orig = (src / TARGET).read_bytes()
    real_zip = B._zip_bytes
    def swap(rel, data):
        out = real_clean(rel, data)
        if rel == TARGET:
            (src / TARGET).write_bytes(b'-- transient\n')
        return out
    def zipper(files):
        (src / TARGET).write_bytes(orig)
        return real_zip(files)
    B.clean_bytes = swap; B._zip_bytes = zipper
    try:
        r = B.build(src, base / 'out', provenance=prov)
        ov = json.loads((base / 'prov.json').read_text())['overlay_sha256'][TARGET]
        return f'BUILT shipped==overlay: {hashlib.sha256(shipped(r)).hexdigest() == ov}'
    finally:
        B.clean_bytes = real_clean; B._zip_bytes = real_zip
attempt('edit_after_staging_reverted_before_reread', edit_revert_late)

# 4) replace the file (new inode, same bytes) between read and post-read check inside read_source
def inode_swap():
    base, src, prov = fresh('inode_swap')
    real_open = os.open
    fired = []
    def opener(path, flags, *a, **k):
        fd = real_open(path, flags, *a, **k)
        if str(path).endswith(TARGET) and not fired:
            fired.append(1)
            tmp = src / (TARGET + '.new'); tmp.write_bytes((src / TARGET).read_bytes()); os.replace(tmp, src / TARGET)
        return fd
    B.os.open = opener
    try:
        r = B.build(src, base / 'out', provenance=prov)
        return 'BUILT (inode swap with identical bytes) shipped=' + repr(shipped(r))
    finally:
        B.os.open = real_open
attempt('inode_replaced_during_read', inode_swap)

# 5) symlink swap during build: a thread flips scripts/examples between the real folder and a symlink
#    to an outside folder holding secret bytes under the same names plus an extra outside-only file.
def symlink_swap(rounds=25, period=0.0005):
    base, src, prov = fresh('symlink_swap')
    outside = base / 'outside'
    shutil.copytree(src / 'scripts/examples', outside)
    for p in outside.rglob('*.lua'):
        p.write_bytes(b'-- OUTSIDE SECRET ' + p.name.encode() + b'\n')
    (outside / 'cursed' / 'zz_outside_only.lua').write_bytes(b'-- OUTSIDE ONLY SECRET\n')
    link = src / 'scripts/examples'; real = src / 'scripts/examples.real'
    stop = threading.Event(); flips = [0]
    def flipper():
        while not stop.is_set():
            try:
                os.rename(link, real); os.symlink(outside, link)
                time.sleep(period)
                os.unlink(link); os.rename(real, link)
                flips[0] += 1
                time.sleep(period)
            except OSError:
                pass
    t = threading.Thread(target=flipper, daemon=True); t.start()
    outcomes = collections.Counter(); leaks = []
    try:
        for i in range(rounds):
            out = base / f'out{i}'
            try:
                r = B.build(src, out, provenance=prov)
                z = zipfile.ZipFile(r['zip']); blob = b''.join(z.read(n) for n in z.namelist())
                if b'OUTSIDE' in blob or any('zz_outside_only' in n for n in z.namelist()):
                    leaks.append(i); outcomes['BUILT_LEAK'] += 1
                else:
                    outcomes['BUILT_clean'] += 1
            except Exception as e:
                key = str(e).split(':')[0][:70]
                outcomes[f'{type(e).__name__}: {key}'] += 1
    finally:
        stop.set(); t.join()
        if os.path.islink(link):
            os.unlink(link)
        if real.exists() and not link.exists():
            os.rename(real, link)
    return f'flips={flips[0]} outcomes={dict(outcomes)} leaks={leaks}'
attempt('symlink_swap_during_build', symlink_swap)

# 6) same, but the outside folder holds byte-identical copies (provenance cannot tell); does an
#    outside-only file get selected and shipped?
def symlink_swap_identical(rounds=25, period=0.0005):
    base, src, prov = fresh('symlink_swap_identical')
    outside = base / 'outside'
    shutil.copytree(src / 'scripts/examples', outside)
    (outside / 'cursed' / 'zz_outside_only.lua').write_bytes(b'-- OUTSIDE ONLY\n')
    # Bind the outside-only file in the overlay too, so provenance is not what refuses it.
    pj = json.loads((base / 'prov.json').read_text())
    pj['overlay_sha256']['scripts/examples/cursed/zz_outside_only.lua'] = hashlib.sha256(b'-- OUTSIDE ONLY\n').hexdigest()
    (base / 'prov.json').write_text(json.dumps(pj))
    link = src / 'scripts/examples'; real = src / 'scripts/examples.real'
    stop = threading.Event(); flips = [0]
    def flipper():
        while not stop.is_set():
            try:
                os.rename(link, real); os.symlink(outside, link)
                time.sleep(period)
                os.unlink(link); os.rename(real, link)
                flips[0] += 1
                time.sleep(period)
            except OSError:
                pass
    t = threading.Thread(target=flipper, daemon=True); t.start()
    outcomes = collections.Counter(); leaks = []
    try:
        for i in range(rounds):
            try:
                r = B.build(src, base / f'out{i}', provenance=base / 'prov.json')
                names = zipfile.ZipFile(r['zip']).namelist()
                if any('zz_outside_only' in n for n in names):
                    leaks.append(i); outcomes['BUILT_OUTSIDE_FILE'] += 1
                else:
                    outcomes['BUILT_clean'] += 1
            except Exception as e:
                outcomes[f'{type(e).__name__}: ' + str(e).split(':')[0][:70]] += 1
    finally:
        stop.set(); t.join()
        if os.path.islink(link):
            os.unlink(link)
        if real.exists() and not link.exists():
            os.rename(real, link)
    return f'flips={flips[0]} outcomes={dict(outcomes)} leaks={leaks}'
attempt('symlink_swap_identical_bytes_outside_only_file', symlink_swap_identical)

rm(ROOT)
print('cleanup done:', not ROOT.exists())

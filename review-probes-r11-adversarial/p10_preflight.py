"""R11 preflight attacks. Synthetic /proc rows, plus one read-only pass over the real /proc.
Real dummy processes: copies of /bin/sleep only (renamed). Signals are patched to raise."""
import os, shutil, signal, subprocess, sys, tempfile, json
from pathlib import Path
W = '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W + '/scripts/harness')
from kpharness import capture_diagnostic as C

def forbid(*a, **k):
    raise AssertionError('preflight tried to signal')
REAL_KILL = os.kill
os.kill = forbid; os.killpg = forbid

def proc(root, pid, comm, argv, *, cmdline_dir=False, exe=None, comm_dir=False):
    d = root / str(pid); d.mkdir()
    if comm_dir: (d / 'comm').mkdir()
    else: (d / 'comm').write_text(comm + '\n')
    (d / 'stat').write_text(f'{pid} ({comm}) S 1 ' + ' '.join(str(i) for i in range(5, 60)))
    if cmdline_dir: (d / 'cmdline').mkdir()
    else: (d / 'cmdline').write_bytes(b'\0'.join(a.encode() for a in argv) + b'\0')
    if exe: os.symlink(exe, d / 'exe')

cases = {
    'renamed_copy_exe_argv_comm': dict(comm='enc', argv=['/tmp/x/enc', '-f', 'lavfi'], exe='/tmp/x/enc'),
    'exe_symlink_name_differs': dict(comm='enc', argv=['enc'], exe='/usr/bin/ffmpeg'),
    'bash_c_string': dict(comm='bash', argv=['bash', '-c', 'ffmpeg -i x out.mp4; true']),
    'timeout_launcher': dict(comm='timeout', argv=['timeout', '60', 'ffmpeg', '-i', 'x']),
    'env_var_then_target': dict(comm='env', argv=['env', 'A=1', 'ffmpeg']),
    'python_dash_u_script': dict(comm='python3', argv=['python3', '-u', '/x/ffmpeg_shim.py']),
    'launcher_option_value': dict(comm='nice', argv=['nice', '-n', '10', 'ffmpeg']),
    'argv_later_real_binary': dict(comm='kworker', argv=['kworker', '--real', '/usr/bin/gamescope']),
    'unreadable_cmdline_same_uid': dict(comm='wineserver', argv=[], cmdline_dir=True),
    'unreadable_comm_same_uid': dict(comm='x', argv=['x'], comm_dir=True),
}
for name, spec in cases.items():
    with tempfile.TemporaryDirectory() as t:
        root = Path(t) / 'proc'; root.mkdir(); run = Path(t) / 'run'; run.mkdir()
        proc(root, 1234, spec['comm'], spec['argv'], cmdline_dir=spec.get('cmdline_dir', False),
             exe=spec.get('exe'), comm_dir=spec.get('comm_dir', False))
        try:
            C.preflight(root, run, self_pid=99999)
            verdict = 'ADMITTED'
        except C.DiagnosticRefused as e:
            verdict = 'refused: ' + str(e)
        print(f'{name}: {verdict}')

# Real /proc, read-only. Dummy renamed copies of /bin/sleep stand in for targets.
tmp = Path(tempfile.mkdtemp(prefix='kp-r11-p10-'))
for n in ('ffmpeg', 'enc'):
    shutil.copy('/bin/sleep', tmp / n)
procs = {'sleep_named_ffmpeg': subprocess.Popen([str(tmp / 'ffmpeg'), '30']),
         'sleep_named_enc_argv_ffmpeg_via_exec_a': subprocess.Popen(['bash', '-c', f'exec -a enc {tmp}/ffmpeg 30']),
         'renamed_enc_binary': subprocess.Popen([str(tmp / 'enc'), '30'])}
import time; time.sleep(.5)
rows = C.process_inventory(Path('/proc'))
blocked = {r['pid'] for r in C.forbidden_processes(rows, exclude=C._launch_chain(Path('/proc'), os.getpid()))}
for name, p in procs.items():
    row = next((r for r in rows if r['pid'] == p.pid), None)
    print(f'real {name}: detected={p.pid in blocked} comm={row and row.get("comm")} exe={row and row.get("exe")} argv0={row and row.get("argv", [None])[0]}')
unread = C.unreadable_processes(rows, exclude=C._launch_chain(Path('/proc'), os.getpid()))
exe_only = [r for r in rows if r.get('exe_unreadable')]
print(f'real rows={len(rows)} unreadable_refusing={len(unread)} exe_only_unreadable={len(exe_only)} '
      f'exe_only_uids={sorted({r["uid"] for r in exe_only})} exe_only_comms={sorted({r.get("comm") for r in exe_only})[:12]}')
other = [r for r in C.forbidden_processes(rows) if r.get('uid') != os.getuid()]
print('forbidden_other_uid=', [(r['pid'], r['comm'], r['uid']) for r in other])
print('forbidden_all=', [(r['pid'], r['comm'], r['uid']) for r in C.forbidden_processes(rows, exclude=C._launch_chain(Path('/proc'), os.getpid())) if r['pid'] not in {p.pid for p in procs.values()}])
with tempfile.TemporaryDirectory() as t:
    try:
        C.preflight(Path('/proc'), Path(t)); print('real preflight: ADMITTED')
    except C.DiagnosticRefused as e:
        ev = json.loads((Path(t) / 'preflight.json').read_text())
        print('real preflight: refused:', e, '| forbidden comms', sorted({r['comm'] for r in ev['forbidden']}),
              '| unreadable', len(ev['unreadable']))
for p in procs.values():
    REAL_KILL(p.pid, signal.SIGTERM); p.wait()  # only the dummies this probe started
shutil.rmtree(tmp)

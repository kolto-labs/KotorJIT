"""Adapted copy of review-probes-r12-correctness/ldso_probe.py: also prints the loader fields."""
import os, shutil, subprocess, sys, tempfile, time
from pathlib import Path
W = '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W + '/scripts/harness')
from kpharness import capture_diagnostic as C
t = Path(tempfile.mkdtemp(prefix='r13-ldso-'))
tool = t / 'toolbin'; shutil.copy2('/bin/sleep', tool)
tools = [{'role': 'ffmpeg', **C.native_elf_identity(str(tool))}]
copy = t / 'enc'; shutil.copy2(tool, copy)
named = t / 'ffmpeg'; shutil.copy2(tool, named)
L = '/lib64/ld-linux-x86-64.so.2'
procs = {'ldso_renamed_enc': subprocess.Popen([L, str(copy), '30']),
         'ldso_named_ffmpeg': subprocess.Popen([L, str(named), '30']),
         'ldso_options_then_relative_enc': subprocess.Popen([L, '--library-path', '/nonexistent/ffmpeg', '--argv0', 'x', './enc', '30'], cwd=t)}
time.sleep(.5)
rows = {r['pid']: r for r in C.process_inventory(Path('/proc'), tools=tools)}
blocked = {r['pid'] for r in C.forbidden_processes(list(rows.values()), exclude=C._launch_chain(Path('/proc'), os.getpid()))}
for n, p in procs.items():
    r = rows.get(p.pid, {})
    print(n, 'detected=', p.pid in blocked, 'loader_program=', r.get('loader_program'),
          'loader_match=', r.get('loader_tool_match'), r.get('loader_match_by'), 'exe_match=', r.get('exe_tool_match'),
          'comm=', r.get('comm'))
for p in procs.values(): p.terminate(); p.wait()
shutil.rmtree(t)

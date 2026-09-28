"""Renamed configured-tool copy launched through the dynamic loader: exe is ld.so, not the tool."""
import os, shutil, subprocess, sys, tempfile
from pathlib import Path
W = '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W + '/scripts/harness')
from kpharness import capture_diagnostic as C
t = Path(tempfile.mkdtemp(prefix='r12c-ldso-'))
tool = t / 'toolbin'; shutil.copy2('/bin/sleep', tool)
tools = [{'role': 'ffmpeg', **C.native_elf_identity(str(tool))}]
copy = t / 'enc'; shutil.copy2(tool, copy)
named = t / 'ffmpeg'; shutil.copy2(tool, named)
procs = {'ldso_renamed_enc': subprocess.Popen(['/lib64/ld-linux-x86-64.so.2', str(copy), '30']),
         'ldso_named_ffmpeg': subprocess.Popen(['/lib64/ld-linux-x86-64.so.2', str(named), '30'])}
rows = {r['pid']: r for r in C.process_inventory(Path('/proc'), tools=tools)}
blocked = {r['pid'] for r in C.forbidden_processes(list(rows.values()), exclude=C._launch_chain(Path('/proc'), os.getpid()))}
for n, p in procs.items():
    r = rows.get(p.pid, {})
    print(n, 'detected=', p.pid in blocked, 'match=', r.get('exe_tool_match'), 'comm=', r.get('comm'),
          'exe=', os.readlink(f'/proc/{p.pid}/exe'))
for p in procs.values(): p.terminate(); p.wait()
shutil.rmtree(t)

"""Ruling 4: renamed copy / hard link / same-size-different file of a configured tool, own-uid, real /proc.
Stand-in 'tool' = a private copy of /bin/sleep (so no host process matches by inode)."""
import os, shutil, subprocess, sys, tempfile
from pathlib import Path
W = '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W + '/scripts/harness')
from kpharness import capture_diagnostic as C
t = Path(tempfile.mkdtemp(prefix='r12c-exe-'))
tool = t / 'toolbin'; shutil.copy2('/bin/sleep', tool)
ident = C.native_elf_identity(str(tool)); tools = [{'role': 'ffmpeg', **ident}]
copy = t / 'enc'; shutil.copy2(tool, copy)
link = t / 'lnk'; os.link(tool, link)
diff = t / 'same_size_diff'; b = bytearray(tool.read_bytes()); b[-1] ^= 0xFF; diff.write_bytes(bytes(b)); diff.chmod(0o755)
procs = {n: subprocess.Popen([str(p), '30']) for n, p in (('renamed_copy', copy), ('hard_link', link), ('same_size_diff', diff))}
rows = {r['pid']: r for r in C.process_inventory(Path('/proc'), tools=tools)}
blocked = {r['pid'] for r in C.forbidden_processes(list(rows.values()), exclude=C._launch_chain(Path('/proc'), os.getpid()))}
for n, p in procs.All() if False else procs.items():
    r = rows.get(p.pid, {})
    print(n, 'detected=', p.pid in blocked, 'match=', r.get('exe_tool_match'), 'by=', r.get('exe_match_by'), 'comm=', r.get('comm'))
for p in procs.values(): p.terminate(); p.wait()
shutil.rmtree(t)

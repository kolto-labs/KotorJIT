"""R12 renamed-binary attacks on the real preflight classifier (process_inventory + forbidden_processes) with the
configured tool identities. Host only. Each target is a real, short synthetic lavfi -> null FFmpeg run started by
this probe; nothing is ever signalled by the classifier; the probe only waits for its own children."""
import ctypes, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path
W = '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W + '/scripts/harness')
from kpharness import capture_diagnostic as CD
FF = '/usr/bin/ffmpeg'
tools = [{'role': 'ffmpeg', **CD.native_elf_identity(FF)},
         {'role': 'ffprobe', **CD.native_elf_identity('/home/linuxbrew/.linuxbrew/bin/ffprobe')}]
tmp = Path(tempfile.mkdtemp(prefix='kp-r12-p19-'))
ARGS = ['-nostdin', '-v', 'error', '-re', '-f', 'lavfi', '-i', 'testsrc2=s=64x48:r=10', '-t', '25', '-f', 'null', '-']
LOADER = next(p for p in ('/lib64/ld-linux-x86-64.so.2', '/usr/lib64/ld-linux-x86-64.so.2') if os.path.exists(p))
enc = tmp / 'enc'; shutil.copyfile(FF, enc); os.chmod(enc, 0o755)
xonly = tmp / 'xonly'; shutil.copyfile(FF, xonly); os.chmod(xonly, 0o111)
memfd_launcher = ("import os,sys;fd=os.memfd_create('enc',0);src=open(%r,'rb').read();os.write(fd,src);"
                  "os.execv('/proc/self/fd/%%d'%%fd,['enc']+sys.argv[1:])") % FF
cases = {
    'loader_invocation_of_real_ffmpeg': [LOADER, FF, *ARGS],
    'loader_invocation_of_renamed_copy': [LOADER, str(enc), *ARGS],
    'renamed_copy_enc': [str(enc), *ARGS],
    'execute_only_renamed_copy': [str(xonly), *ARGS],
    'memfd_exec_copy': [sys.executable, '-c', memfd_launcher, *ARGS],
    'ld_preload_wrapper_real_ffmpeg': ['env', 'LD_PRELOAD=', FF, *ARGS],
}
procs = {name: subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE) for name, argv in cases.items()}
time.sleep(4)
rows = CD.process_inventory(Path('/proc'), tools=tools)
blocked = {row['pid'] for row in CD.forbidden_processes(rows)}
by_pid = {row['pid']: row for row in rows}
for name, p in procs.items():
    row = by_pid.get(p.pid, {})
    keys = {k: row.get(k) for k in ('comm', 'exe', 'exe_tool_match', 'exe_match_by', 'exe_identity_unreadable')}
    print(f'{name}: running={p.poll() is None} detected={p.pid in blocked} argv0..1={row.get("argv", [])[:2]} {keys}',
          flush=True)
for p in procs.values():
    err = p.communicate(timeout=60)[1].decode(errors='replace').strip()
    if p.returncode: print('  rc', p.returncode, err[:200])

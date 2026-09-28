"""R10 Part C: preflight detection on a synthetic /proc tree (no real processes touched)."""
import sys, tempfile, json
from pathlib import Path
W='/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation'
sys.path.insert(0, W+'/scripts/harness')
from kpharness import capture_diagnostic as C
def proc(root, pid, comm, argv, cmdline_dir=False):
    d = root/str(pid); d.mkdir()
    (d/'comm').write_text(comm+'\n')
    (d/'stat').write_text(f'{pid} ({comm}) S ' + ' '.join(str(i) for i in range(4, 60)))
    if cmdline_dir: (d/'cmdline').mkdir()
    else: (d/'cmdline').write_bytes(b'\0'.join(a.encode() for a in argv)+b'\0')
cases = {
 'potplayer_wineserver': ('wineserver', ['/usr/bin/wineserver']),
 'wine_exe_windows_path': ('swkotor.exe', ['C:\\Games\\swkotor.exe']),
 'kotor2': ('swkotor2.exe', ['swkotor2.exe']),
 'gamescope_wl_thread_name': ('gamescope-wl', ['/usr/bin/gamescope','-W','1']),
 'ffmpeg_via_wrapper_bash': ('bash', ['/bin/bash','/home/u/.local/bin/ffmpeg','-i','x']),
 'ffmpeg_via_python_interp': ('python3', ['python3','-m','ffmpeg_wrapper']),
 'renamed_comm_and_argv0': ('kworker', ['kworker','--real','/usr/bin/gamescope']),
 'unreadable_cmdline': ('wineserver', [], True),
 'xwayland_other': ('Xwayland', ['Xwayland',':5']),
}
for name, spec in cases.items():
    with tempfile.TemporaryDirectory() as t:
        root = Path(t); proc(root, 1234, spec[0], spec[1], *(spec[2:]))
        rows = C.process_inventory(root)
        print(f'{name}: detected={bool(C.forbidden_processes(rows))} inventoried={bool(rows)}')
import inspect; src = inspect.getsource(C)
print('signal_calls=', [l.strip() for l in src.splitlines() if any(k in l for k in ('kill(', 'killpg', 'send_signal', 'os.kill'))])

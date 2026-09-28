"""Adapted R12 _thread probe: the production supervisor_thread_count() against threading.active_count()."""
import _thread, sys, threading, time
sys.path.insert(0, '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/scripts/harness')
from kpharness import capture_diagnostic as CD
print('before: active_count', threading.active_count(), 'supervisor_thread_count', CD.supervisor_thread_count())
ev = threading.Event(); _thread.start_new_thread(lambda: ev.wait(5), ()); time.sleep(.2)
print('with _thread: active_count', threading.active_count(), 'supervisor_thread_count', CD.supervisor_thread_count())
ev.set()

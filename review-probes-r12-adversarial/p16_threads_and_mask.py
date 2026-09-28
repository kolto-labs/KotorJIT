"""(a) threading.active_count() vs OS threads: a _thread thread is invisible to the refusal check.
(b) A signal whose Python handler is still pending when pthread_sigmask(SIG_BLOCK) runs raises out of
pthread_sigmask itself (CPython calls PyErr_CheckSignals there): previous_mask is lost and the set stays blocked."""
import _thread, os, signal, threading, time
ev = threading.Event()
_thread.start_new_thread(lambda: ev.wait(5), ())
time.sleep(.2)
print('a) threading.active_count()=%d os_threads=%d' % (threading.active_count(), len(os.listdir('/proc/self/task'))))
ev.set()
S = (signal.SIGINT, signal.SIGHUP, signal.SIGTERM)
class Boom(BaseException): pass
def h(n, f): raise Boom(n)
signal.signal(signal.SIGTERM, h)
hits = 0; lost = 0
for i in range(2000):
    prev = None
    try:
        os.kill(os.getpid(), signal.SIGTERM); prev = signal.pthread_sigmask(signal.SIG_BLOCK, S)
    except Boom:
        hits += 1
        blocked = signal.pthread_sigmask(signal.SIG_BLOCK, ())
        if signal.SIGTERM in blocked:
            lost += 1
        signal.pthread_sigmask(signal.SIG_SETMASK, ())
        continue
    signal.pthread_sigmask(signal.SIG_SETMASK, prev)
print(f'b) handler_ran={hits}/2000 mask_left_blocked_after_raise={lost}')

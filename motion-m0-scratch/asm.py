import sys, re, bisect
L = open('/home/brunner56/kp-live-20260922/camera-rederive-scratch/text.asm').read().splitlines()
A = [int(l[:8], 16) for l in L]


def idx(a):
    return bisect.bisect_left(A, a)


def fstart(a):
    i = idx(a)
    while i > 0 and not (L[i - 1].endswith('nop ') or 'int3' in L[i - 1]):
        i -= 1
    return A[i]


def fn(a, maxn=400):
    i = idx(a); out = []
    while i < len(L) and len(out) < maxn:
        out.append(L[i])
        if ': ret' in L[i] and i + 1 < len(L) and (L[i + 1].endswith('nop ') or 'int3' in L[i + 1]):
            break
        i += 1
    return out


def show(a, b=10, f=10):
    i = idx(a)
    return L[max(0, i - b):i + f + 1]


def grep(pat):
    r = re.compile(pat)
    return [l for l in L if r.search(l)]


def callers(t):
    return grep(r'call 0x%x$' % t)


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'fn':
        for a in sys.argv[2:]:
            print('== %s' % a); print('\n'.join(fn(int(a, 16))))
    elif cmd == 'fstart':
        for a in sys.argv[2:]:
            print(a, 'in', hex(fstart(int(a, 16))))
    elif cmd == 'show':
        a = int(sys.argv[2], 16); b = int(sys.argv[3]) if len(sys.argv) > 3 else 10; f = int(sys.argv[4]) if len(sys.argv) > 4 else 10
        print('\n'.join(show(a, b, f)))
    elif cmd == 'callers':
        for a in sys.argv[2:]:
            cs = callers(int(a, 16)); print('== callers of %s: %d' % (a, len(cs)))
            for c in cs:
                print(c, ' fn', hex(fstart(int(c[:8], 16))))
    elif cmd == 'grep':
        for l in grep(sys.argv[2]):
            print(l)

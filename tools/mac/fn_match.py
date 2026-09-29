"""Cross-binary function matching by anchors + call-graph propagation.

match(A, B) -> dict a_addr -> (b_addr, reason)
A/B are {addr: Func}. use_shape enables instruction-shape anchors (same arch only).
"""
import re, hashlib
from collections import defaultdict, Counter

REG64 = re.compile(r'%[a-z0-9]+')
NUM = re.compile(r'-?0x[0-9a-f]+|-?\b\d+\b')


def shape(f, with_imm=False):
    h = hashlib.md5()
    for _, mn, ops in f.insns:
        o = ops
        if mn.startswith('call') or mn.startswith('j'):
            o = '*' if o.startswith('*') else ''
        else:
            o = NUM.sub('N', o) if not with_imm else re.sub(r'0x[0-9a-f]{6,}', 'A', o)
        h.update((mn + ' ' + o + ';').encode())
    return h.hexdigest()


def callee_label(c, amap):
    if isinstance(c, str):
        return c
    return ('m', amap.get(c)) if c in amap else None


def uniq_map(keysA, keysB):
    ia = defaultdict(list); ib = defaultdict(list)
    for a, k in keysA.items():
        if k is not None:
            ia[k].append(a)
    for b, k in keysB.items():
        if k is not None:
            ib[k].append(b)
    out = {}
    for k, la in ia.items():
        lb = ib.get(k)
        if lb and len(la) == 1 and len(lb) == 1:
            out[la[0]] = lb[0]
    return out


def lcs_align(sa, sb):
    n, m = len(sa), len(sb)
    if n * m > 250000:
        return []
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            if sa[i] == sb[j] and sa[i] is not None:
                dp[i][j] = dp[i + 1][j + 1] + 1
            else:
                dp[i][j] = max(dp[i + 1][j], dp[i][j + 1])
    pairs = []
    i = j = 0
    while i < n and j < m:
        if sa[i] == sb[j] and sa[i] is not None:
            pairs.append((i, j)); i += 1; j += 1
        elif dp[i + 1][j] >= dp[i][j + 1]:
            i += 1
        else:
            j += 1
    return pairs


def match(A, B, use_shape=True, log=print):
    amap = {}   # A addr -> B addr
    why = {}
    used_b = set()

    def add(a, b, reason):
        if a in amap or b in used_b:
            return False
        amap[a] = b; used_b.add(b); why[a] = reason
        return True

    def anchors():
        n0 = len(amap)
        freeA = {a: f for a, f in A.items() if a not in amap}
        freeB = {b: f for b, f in B.items() if b not in used_b}
        # strings + imports
        def skey(f):
            s = tuple(sorted(set(f.strings)))
            imps = tuple(sorted(set(c for c in f.calls + f.tail if isinstance(c, str))))
            if not s and len(imps) < 2:
                return None
            return (s, imps)
        for a, b in uniq_map({a: skey(f) for a, f in freeA.items()}, {b: skey(f) for b, f in freeB.items()}).items():
            add(a, b, 'strings+imports')
        def skey2(f):
            s = tuple(sorted(set(f.strings)))
            return s if s else None
        freeA = {a: f for a, f in A.items() if a not in amap}
        freeB = {b: f for b, f in B.items() if b not in used_b}
        for a, b in uniq_map({a: skey2(f) for a, f in freeA.items()}, {b: skey2(f) for b, f in freeB.items()}).items():
            add(a, b, 'strings')
        if use_shape:
            freeA = {a: f for a, f in A.items() if a not in amap}
            freeB = {b: f for b, f in B.items() if b not in used_b}
            def shk(f):
                return shape(f) if len(f.insns) >= 12 else None
            for a, b in uniq_map({a: shk(f) for a, f in freeA.items()}, {b: shk(f) for b, f in freeB.items()}).items():
                add(a, b, 'shape')
        return len(amap) - n0

    def propagate():
        n0 = len(amap)
        votes = defaultdict(Counter)
        for a, b in list(amap.items()):
            fa, fb = A[a], B[b]
            for la, lb in ((fa.calls, fb.calls), (fa.tail, fb.tail)):
                # label known callees
                sa = [callee_label(c, amap) if not isinstance(c, str) else c for c in la]
                sb = [('m', c) if (not isinstance(c, str) and c in used_b) else (c if isinstance(c, str) else None) for c in lb]
                # anchored alignment on known labels, then fill gaps of equal size
                pairs = lcs_align(sa, sb)
                bounds = [(-1, -1)] + pairs + [(len(la), len(lb))]
                for (i0, j0), (i1, j1) in zip(bounds, bounds[1:]):
                    ga = [la[i] for i in range(i0 + 1, i1)]
                    gb = [lb[j] for j in range(j0 + 1, j1)]
                    if len(ga) == len(gb) and ga:
                        for x, y in zip(ga, gb):
                            if not isinstance(x, str) and not isinstance(y, str) and x in A and y in B:
                                votes[x][y] += 1
        for x, c in votes.items():
            if x in amap:
                continue
            (y, n), *rest = c.most_common(2) + [(None, 0)]
            second = rest[0][1] if rest else 0
            if y is not None and y not in used_b and n > second:
                # guard: size sanity
                la, lb = len(A[x].insns), len(B[y].insns)
                if min(la, lb) * 3 >= max(la, lb) or max(la, lb) < 20:
                    add(x, y, 'callgraph(%d)' % n)
        return len(amap) - n0

    it = 0
    while True:
        it += 1
        na = anchors()
        np_ = 0
        while True:
            k = propagate()
            np_ += k
            if k == 0:
                break
        log('iter %d: anchors +%d propagate +%d total %d' % (it, na, np_, len(amap)))
        if na + np_ == 0 or it > 12:
            break
    return amap, why

import struct, sys
P = '/home/brunner56/biodecompwarehouse/kotorxid/output/binaries/K1__k1_win_gog_swkotor.exe/artifacts/raw_image'
D = open(P, 'rb').read()
IB = 0x400000
pe = struct.unpack_from('<I', D, 0x3c)[0]
ns = struct.unpack_from('<H', D, pe + 6)[0]
so = struct.unpack_from('<H', D, pe + 20)[0]
secs = []
for i in range(ns):
    o = pe + 24 + so + 40 * i
    name = D[o:o + 8].rstrip(b'\0').decode()
    vs, va, rs, ro = struct.unpack_from('<IIII', D, o + 8)
    secs.append((name, va + IB, vs, rs, ro))


def off(v):
    for n, va, vs, rs, ro in secs:
        if va <= v < va + max(vs, rs):
            return ro + (v - va) if v - va < rs else None


def rd(v, n):
    o = off(v)
    return D[o:o + n] if o is not None else b'\0' * n


def u32(v):
    return struct.unpack('<I', rd(v, 4))[0]


def f32(v):
    return struct.unpack('<f', rd(v, 4))[0]


if __name__ == '__main__':
    for n, va, vs, rs, ro in secs:
        print(n, hex(va), hex(vs), hex(rs), hex(ro))

"""Minimal Mach-O reader + llvm-objdump-driven function model for matching.

Supports thin or fat x86_64 / i386 images. Produces, per function:
  start, end, insns [(addr, mnem, ops)], calls [target or 'imp:_name'],
  strings [text], datarefs [addr]
"""
import struct, subprocess, re, os, pickle, hashlib
from collections import defaultdict

CPU_X86_64 = 0x01000007
CPU_I386 = 7


def read_uleb(b, i):
    r = 0; s = 0
    while True:
        x = b[i]; i += 1
        r |= (x & 0x7f) << s; s += 7
        if not x & 0x80:
            return r, i


class MachO:
    def __init__(self, path, arch='x86_64'):
        self.path = path
        data = open(path, 'rb').read()
        self.fat_offset = 0
        magic = struct.unpack('>I', data[:4])[0]
        want = CPU_X86_64 if arch == 'x86_64' else CPU_I386
        if magic == 0xcafebabe:
            n = struct.unpack('>I', data[4:8])[0]
            for k in range(n):
                ct, cs, off, size, al = struct.unpack('>iiIII', data[8 + 20 * k:28 + 20 * k])
                if ct == want:
                    self.fat_offset = off
                    data = data[off:off + size]
                    break
            else:
                raise ValueError('arch not in fat file')
        self.data = data
        self.arch = arch
        self.is64 = arch == 'x86_64'
        self.sha256 = hashlib.sha256(data).hexdigest()
        self._parse()

    def _parse(self):
        d = self.data
        if self.is64:
            magic, ct, cst, ft, ncmds, sz, flags, _ = struct.unpack('<IiiIIIII', d[:32]); off = 32
        else:
            magic, ct, cst, ft, ncmds, sz, flags = struct.unpack('<IiiIIII', d[:28]); off = 28
        self.segments = []
        self.sections = []
        self.symbols = {}          # addr -> name (defined)
        self.symlist = []
        self.fstarts = []
        indirect = None
        symtab = None
        for _ in range(ncmds):
            cmd, cmdsize = struct.unpack('<II', d[off:off + 8])
            if cmd in (0x19, 0x1):
                if cmd == 0x19:
                    segname = d[off + 8:off + 24].rstrip(b'\0').decode()
                    vmaddr, vmsize, fileoff, filesize, maxprot, initprot, nsects, fl = struct.unpack('<QQQQiiII', d[off + 24:off + 72])
                    so = off + 72; ssz = 80
                else:
                    segname = d[off + 8:off + 24].rstrip(b'\0').decode()
                    vmaddr, vmsize, fileoff, filesize, maxprot, initprot, nsects, fl = struct.unpack('<IIIIiiII', d[off + 24:off + 56])
                    so = off + 56; ssz = 68
                self.segments.append(dict(name=segname, vmaddr=vmaddr, vmsize=vmsize, fileoff=fileoff, filesize=filesize, maxprot=maxprot, initprot=initprot))
                for s in range(nsects):
                    b = so + s * ssz
                    sect = d[b:b + 16].rstrip(b'\0').decode(); seg = d[b + 16:b + 32].rstrip(b'\0').decode()
                    if self.is64:
                        addr, size, offset, align, reloff, nreloc, flags, r1, r2, r3 = struct.unpack('<QQIIIIIIII', d[b + 32:b + 80])
                    else:
                        addr, size, offset, align, reloff, nreloc, flags, r1, r2 = struct.unpack('<IIIIIIIII', d[b + 32:b + 68])
                    self.sections.append(dict(sect=sect, seg=seg, addr=addr, size=size, offset=offset, flags=flags, r1=r1, r2=r2))
            elif cmd == 0x2:
                symoff, nsyms, stroff, strsize = struct.unpack('<IIII', d[off + 8:off + 24])
                symtab = (symoff, nsyms, stroff, strsize)
            elif cmd == 0xb:
                vals = struct.unpack('<18I', d[off + 8:off + 80])
                indirect = (vals[12], vals[13])
            elif cmd == 0x26:
                doff, dsz = struct.unpack('<II', d[off + 8:off + 16])
                self._fs = (doff, dsz)
            off += cmdsize
        self.text_base = next(s['vmaddr'] for s in self.segments if s['name'] == '__TEXT')
        # symbols
        allsyms = []
        if symtab:
            symoff, nsyms, stroff, strsize = symtab
            esz = 16 if self.is64 else 12
            for i in range(nsyms):
                b = symoff + i * esz
                if self.is64:
                    strx, typ, sect, desc, val = struct.unpack('<IBBHQ', d[b:b + 16])
                else:
                    strx, typ, sect, desc, val = struct.unpack('<IBBhI', d[b:b + 12])
                e = d.index(b'\0', stroff + strx)
                name = d[stroff + strx:e].decode(errors='replace')
                allsyms.append((name, typ, sect, val))
                if (typ & 0xe0) == 0 and (typ & 0x0e) == 0x0e and sect != 0 and name:
                    self.symbols.setdefault(val, name)
        self.allsyms = allsyms
        # imports via indirect table
        self.stub_names = {}
        if indirect and symtab:
            ioff, n = indirect
            ind = struct.unpack('<%dI' % n, d[ioff:ioff + 4 * n])
            for s in self.sections:
                typ = s['flags'] & 0xff
                if typ in (6, 7, 8):  # non-lazy ptrs, lazy ptrs, symbol stubs
                    esize = s['r2'] if typ == 8 else (8 if self.is64 else 4)
                    if esize == 0:
                        continue
                    cnt = s['size'] // esize
                    for k in range(cnt):
                        idx = ind[s['r1'] + k]
                        if idx & 0xC0000000:
                            continue
                        self.stub_names[s['addr'] + k * esize] = allsyms[idx][0]
        # function starts
        if hasattr(self, '_fs'):
            doff, dsz = self._fs
            b = d[doff:doff + dsz]
            i = 0; addr = self.text_base
            while i < len(b):
                v, i = read_uleb(b, i)
                if v == 0:
                    break
                addr += v
                self.fstarts.append(addr)

    def sect(self, name):
        for s in self.sections:
            if s['sect'] == name:
                return s
        return None

    def read(self, addr, n):
        for s in self.segments:
            if s['vmaddr'] <= addr < s['vmaddr'] + s['filesize']:
                o = s['fileoff'] + (addr - s['vmaddr'])
                return self.data[o:o + n]
        return None

    def cstring(self, addr, limit=200):
        for s in self.sections:
            if s['sect'] in ('__cstring', '__const', '__objc_methname', '__data', '__objc_classname') and s['addr'] <= addr < s['addr'] + s['size']:
                if s['flags'] & 0xff == 1 and s['offset'] == 0:
                    return None
                o = s['offset'] + addr - s['addr']
                e = self.data.find(b'\0', o, o + limit)
                if e < 0:
                    return None
                raw = self.data[o:e]
                if s['sect'] != '__cstring':
                    if len(raw) < 4 or not all(32 <= c < 127 for c in raw):
                        return None
                try:
                    return raw.decode()
                except UnicodeDecodeError:
                    return None
        return None

    def cfstring(self, addr):
        s = self.sect('__cfstring')
        if s and s['addr'] <= addr < s['addr'] + s['size']:
            ptrsz = 8 if self.is64 else 4
            raw = self.read(addr + 2 * ptrsz, ptrsz)
            p = struct.unpack('<Q' if self.is64 else '<I', raw)[0]
            return self.cstring(p)
        return None


INSN_RE = re.compile(r'^\s*([0-9a-f]+):\s+(\S+)\s*(.*)$')
TARGET_RE = re.compile(r'0x([0-9a-f]+)')
COMMENT_RE = re.compile(r'##\s*0x([0-9a-f]+)')


class Func:
    __slots__ = ('start', 'end', 'insns', 'calls', 'strings', 'datarefs', 'name', 'jumps', 'tail')

    def __init__(self, start):
        self.start = start; self.end = start; self.insns = []; self.calls = []; self.strings = []
        self.datarefs = []; self.name = None; self.jumps = []; self.tail = []


def objdump_tool():
    for name in ('llvm-objdump', 'llvm-objdump-18', 'llvm-objdump-17', 'llvm-objdump-16', 'objdump'):
        for d in os.environ.get('PATH', '').split(os.pathsep):
            if os.access(os.path.join(d, name), os.X_OK):
                return name
    raise RuntimeError('llvm-objdump not found (install LLVM; on macOS use `xcrun llvm-objdump` via PATH)')


def disassemble(m, cache_dir=None):
    """Function model for every function start in __text.

    `cache_dir` keeps a pickle keyed by the slice's sha256 so repeated runs
    are cheap; pass None to always recompute."""
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
        cp = os.path.join(cache_dir, m.sha256 + '.pkl')
        if os.path.exists(cp):
            return pickle.load(open(cp, 'rb'))
    import tempfile
    with tempfile.NamedTemporaryFile(suffix='.macho', delete=False) as t:
        t.write(m.data)
        tmp = t.name
    try:
        out = subprocess.run([objdump_tool(), '-d', '--no-show-raw-insn', '--section=__text', '--arch=' + m.arch, tmp],
                             capture_output=True, text=True, check=True).stdout
    finally:
        os.unlink(tmp)
    text = m.sect('__text')
    starts = set(m.fstarts)
    for a, n in m.symbols.items():
        if text['addr'] <= a < text['addr'] + text['size'] and not n.startswith('l'):
            starts.add(a)
    starts = sorted(starts)
    import bisect
    funcs = {a: Func(a) for a in starts}
    for a, f in funcs.items():
        f.name = m.symbols.get(a)
    stubs = m.stub_names
    pic = None  # (reg, base) for i386
    prev = None
    for line in out.splitlines():
        mt = INSN_RE.match(line)
        if not mt:
            continue
        addr = int(mt.group(1), 16); mn = mt.group(2); ops = mt.group(3)
        k = bisect.bisect_right(starts, addr) - 1
        if k < 0:
            continue
        f = funcs[starts[k]]
        if addr == f.start:
            pic = None
        f.insns.append((addr, mn, ops.split('##')[0].strip()))
        f.end = addr + 1
        tgt = None
        if mn.startswith('call') or mn.startswith('jmp') or (mn.startswith('j') and mn != 'jmp'):
            t = TARGET_RE.match(ops.strip())
            if t and not ops.strip().startswith('*'):
                tgt = int(t.group(1), 16)
        if tgt is not None:
            if mn.startswith('call'):
                if not m.is64 and prev is not None:
                    pass
                f.calls.append(('imp:' + stubs[tgt]) if tgt in stubs else tgt)
            elif mn.startswith('jmp'):
                if tgt in stubs:
                    f.tail.append('imp:' + stubs[tgt])
                elif not (f.start <= tgt < (starts[k + 1] if k + 1 < len(starts) else 1 << 64)):
                    f.tail.append(tgt)
        # data references
        refs = []
        cm = COMMENT_RE.search(ops)
        if cm:
            refs.append(int(cm.group(1), 16))
        if not m.is64:
            # PIC base tracking: calll <next>; popl %reg
            if mn == 'calll' and tgt is not None and tgt == addr + 5:
                pic = ('pending', tgt)
            elif mn == 'popl' and pic and pic[0] == 'pending':
                pic = (ops.strip(), pic[1])
            else:
                if pic and pic[0] != 'pending':
                    mm = re.search(r'(-?0x[0-9a-f]+)\(' + re.escape(pic[0]) + r'\)', ops)
                    if mm:
                        refs.append(pic[1] + int(mm.group(1), 16))
                mm = re.match(r'\$0x([0-9a-f]+),', ops.strip())
                if mm:
                    v = int(mm.group(1), 16)
                    if v > 0x1000:
                        refs.append(v)
                mm = re.match(r'0x([0-9a-f]+)$', ops.strip()) if mn.startswith('push') else None
                if mm:
                    refs.append(int(mm.group(1), 16))
        for r in refs:
            if r in stubs:
                continue
            s = m.cstring(r) or m.cfstring(r)
            if s is not None and len(s) >= 2:
                f.strings.append(s)
            else:
                f.datarefs.append(r)
        prev = (addr, mn, ops)
    funcs = {a: f for a, f in funcs.items() if f.insns}
    if cache_dir:
        pickle.dump(funcs, open(cp, 'wb'))
    return funcs

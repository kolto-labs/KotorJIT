"""Synthetic subprocess CLI contract. No game assets or processes."""
import hashlib
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

TOOL = sys.argv[1]

def fixture(wide):
    b = bytearray(512)
    h, fixed, stride = (32, 72, 80) if wide else (28, 56, 68)
    def put(at, value, width=4):
        b[at:at + width] = value.to_bytes(width, 'little')
    put(0, 0xfeedfacf if wide else 0xfeedface)
    put(4, 0x1000007 if wide else 7)
    put(12, 2); put(16, 1); put(20, fixed + stride)
    put(h, 0x19 if wide else 1); put(h + 4, fixed + stride)
    b[h + 8:h + 14] = b'__TEXT'
    width = 8 if wide else 4
    base = 0x100001000 if wide else 0x1000
    put(h + 24, base, width); put(h + 24 + width, 512, width)
    put(h + 24 + 3 * width, 512, width)
    put(h + (64 if wide else 48), 1)
    s = h + fixed
    b[s:s + 6] = b'__text'; b[s + 16:s + 22] = b'__TEXT'
    put(s + 32, base + 256, width); put(s + 32 + width, 16, width)
    put(s + 32 + 2 * width, 256)
    return b


def run(*args, code=0):
    p = subprocess.run([TOOL, *map(str, args)], capture_output=True, text=True, timeout=10)
    assert p.returncode == code, (args, p.returncode, p.stdout, p.stderr)
    return p.stdout + p.stderr

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    for wide in (False, True):
        b = fixture(wide); path = root / 'thin'; path.write_bytes(b)
        for command in ('identify', 'sections'):
            out = run(command, path)
            assert hashlib.sha256(b).hexdigest() in out
            assert 'metadata-only' in out and '<unrecognised>' in out
            assert ('container_bits=64' if wide else 'container_bits=32') in out
        out = run('sections', path)
        assert ('0x0000000100001100' if wide else '0x0000000000001100') in out
        assert 'file_size=0x0000000000000010' in out
        for args in [('classify', path), ('dump', path, root / 'output'), ('sections', path, '--mapped'), ('identify', path, '--mapped')]:
            assert 'unsupported' in run(*args, code=2)
        assert not (root / 'output').exists()
        path.write_bytes(b[:32])
        assert 'Mach-O:' in run('identify', path, code=2)
        for magic in (0xcafebabe, 0xbebafeca, 0xcefaedfe, 0xcffaedfe):
            path.write_bytes(struct.pack('<I', magic) + bytes(32))
            assert 'unsupported' in run('sections', path, code=2)
    # A minimal valid ELF32 load segment exercises the unchanged legacy route.
    elf = bytearray(256)
    elf[:7] = b'\x7fELF\x01\x01\x01'
    struct.pack_into('<HHIIIIIHHHHHH', elf, 16, 2, 3, 1, 0, 52, 0, 0, 52, 32, 1, 40, 0, 0)
    struct.pack_into('<IIIIIIII', elf, 52, 1, 0, 0x8048000, 0, 256, 256, 5, 4096)
    path.write_bytes(elf)
    assert 'ELF32' in run('sections', path)
    assert 'ELF32' in run('sections', path, '--mapped')
    # Unknown legacy inputs retain identify's established hash/exit1 behavior.
    path.write_bytes(b'MZ' + bytes(64))
    assert '<unrecognised>' in run('identify', path, code=1)
print('PASS synthetic Mach-O CLI32/64, hashes, spans, malformed and unsupported modes')

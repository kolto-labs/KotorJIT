"""Offline tests for sigforge (synthetic binaries + real ELF/PE if available)."""
from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))

from sigforge import BinaryView, SectionView, extract_field_offset, synthesize_unique, unify_signatures  # noqa: E402


def _make_x86_view(chunks: list[tuple[int, bytes]], image_base: int = 0x400000) -> BinaryView:
    raw = bytearray()
    secs: list[SectionView] = []
    for va, buf in chunks:
        off = len(raw)
        raw.extend(buf)
        secs.append(SectionView(".text", va, len(buf), off, len(buf), True))
    return BinaryView(bytes(raw), format_kind="pe", arch="x86", bits=32, image_base=image_base, sections=secs)


class SigForgeUnitTests(unittest.TestCase):
    def test_rel32_and_imm_masking_preserves_struct_displacement(self) -> None:
        # Sub 1: call 0x402000; mov ecx, [esi + 0x3d4]; push ebx; ret (repeated nowhere else)
        # Wait: let's make unique prefix + call + struct disp
        fn1 = (
            b"\x55\x8b\xec"                      # push ebp; mov ebp, esp
            + b"\xe8" + struct.pack("<i", 0x402000 - (0x401003 + 5))  # call 0x402000 (masked)
            + b"\x8b\x8e\xd4\x03\x00\x00"        # mov ecx, [esi + 0x3d4] (kept concrete!)
            + b"\x33\xc0\x5d\xc3"                # xor eax, eax; pop ebp; ret
        )
        # Clone in build B with different call target + different base
        fn1_b = (
            b"\x55\x8b\xec"
            + b"\xe8" + struct.pack("<i", 0x509999 - (0x504003 + 5))
            + b"\x8b\x8e\xd4\x03\x00\x00"
            + b"\x33\xc0\x5d\xc3"
        )
        bv_a = _make_x86_view([(0x401000, fn1 + b"\x90" * 16), (0x402000, b"\xc3" * 8)], 0x400000)
        bv_b = _make_x86_view([(0x504000, fn1_b + b"\x90" * 16), (0x509999, b"\xc3" * 8)], 0x500000)

        res = synthesize_unique(bv_a, 0x401000, min_bytes=12)
        self.assertEqual(res.kind, "pattern")
        self.assertEqual(res.hit_count, 1)
        # Bytes 4..7 (rel32 of call) must be masked out (00), while 0xd4030000 must stay 0xFF
        msk = bytes.fromhex(res.mask)
        self.assertEqual(msk[4:8], b"\x00\x00\x00\x00")
        self.assertEqual(msk[10:14], b"\xff\xff\xff\xff")

        # Cross-build unification succeeds despite relocated CALL target!
        uni = unify_signatures([("A", bv_a, 0x401000), ("B", bv_b, 0x504000)])
        self.assertTrue(uni["unified"], uni)
        self.assertEqual(bv_a.scan_masked(bytes.fromhex(uni["pattern"]), bytes.fromhex(uni["mask"])), [0x401000])
        self.assertEqual(bv_b.scan_masked(bytes.fromhex(uni["pattern"]), bytes.fromhex(uni["mask"])), [0x504000])

    def test_thunk_xref_synthesis_resolves_short_wrapper(self) -> None:
        # Target body unique; two wrappers share identical `mov ecx, [ecx]` prefix but jump to different targets
        body1 = b"\x56\x8b\xf1\x57\x8d\xbe\xac\x01\x00\x00\x6a\x03\xc3"
        body2 = b"\x56\x8b\xf1\x57\x8d\xbe\xc4\x01\x00\x00\x6a\x04\xc3"
        thunk1 = b"\x8b\x09\xe9" + struct.pack("<i", 0x401800 - (0x401002 + 5))
        thunk2 = b"\x8b\x09\xe9" + struct.pack("<i", 0x401900 - (0x401022 + 5))
        code = thunk1 + b"\xcc" * (0x20 - len(thunk1)) + thunk2
        bv = _make_x86_view([
            (0x401000, code),
            (0x401800, body1),
            (0x401900, body2),
        ])
        res = synthesize_unique(bv, 0x401000, min_bytes=12, func_size=7)
        self.assertEqual(res.kind, "xref_thunk")
        self.assertEqual(res.thunk_prefix, "8b09")
        self.assertEqual(res.thunk_opcode, "e9")
        hits = bv.scan_masked(bytes.fromhex(res.target_pattern), bytes.fromhex(res.target_mask), max_hits=2)
        self.assertEqual(hits, [0x401800])

    def test_call_forwarder_xref_resolves_short_wrapper(self) -> None:
        # K2 GOG style wrappers: identical prologue + `mov ecx, [ecx+0x1c]; call rel32; mov esp, ebp; pop ebp; ret 4`
        body1 = b"\x55\x8b\xec\x56\x8b\xf1\x8d\xbe\xac\x01\x00\x00\x6a\x03\x5d\xc2\x04\x00"
        body2 = b"\x55\x8b\xec\x56\x8b\xf1\x8d\xbe\xc4\x01\x00\x00\x6a\x04\x5d\xc2\x04\x00"
        hdr = b"\x55\x8b\xec\x51\x89\x4d\xfc\x8b\x45\x08\x50\x8b\x4d\xfc\x8b\x49\x1c"
        suf = b"\x8b\xe5\x5d\xc2\x04\x00"
        w1 = hdr + b"\xe8" + struct.pack("<i", 0x402000 - (0x401000 + len(hdr) + 5)) + suf
        w2 = hdr + b"\xe8" + struct.pack("<i", 0x402100 - (0x401100 + len(hdr) + 5)) + suf
        pad = b"\xcc" * (0x100 - len(w1))
        bv = _make_x86_view([(0x401000, w1 + pad + w2), (0x402000, body1), (0x402100, body2)])
        res = synthesize_unique(bv, 0x401000, min_bytes=12)
        self.assertEqual(res.kind, "xref_thunk")
        self.assertEqual(res.thunk_opcode, "e8")
        self.assertEqual(res.thunk_suffix, suf.hex())

    def test_extract_field_offset(self) -> None:
        code = b"\x56\x8b\xf1\x8b\x86\xac\x01\x00\x00\xc3"
        bv = _make_x86_view([(0x401000, code)])
        fe = extract_field_offset(bv, 0x401000)
        self.assertIsNotNone(fe)
        self.assertEqual(fe.offset, 0x1AC)
        self.assertEqual(fe.size, 4)

    def test_guarded_early_ret_and_thunk_xref(self) -> None:
        # Stub at 0x401000: mov ecx, [ecx]; jmp target_int (0x401100)
        # Stub at 0x401010: mov ecx, [ecx]; jmp target_flt (0x401200)
        # Both targets share an identical 19-byte prologue with an early guard ret 4,
        # bypassed by `jg cont`, and differ ONLY at `cmp bl, 3` vs `cmp bl, 4` after it!
        def make_pop_target(tag: int) -> bytes:
            # test eax, eax; jg +5; xor eax, eax; ret 4; push ebx; cmp bl, tag; xor eax, eax; mov al, 1; pop ebx; ret 4
            return bytes([
                0x85, 0xC0,
                0x7F, 0x05,
                0x33, 0xC0,
                0xC2, 0x04, 0x00,
                0x53,
                0x80, 0xFB, tag,
                0x33, 0xC0,
                0xB0, 0x01,
                0x5B,
                0xC2, 0x04, 0x00,
            ])

        stub_int = b"\x8b\x09\xe9" + struct.pack("<i", 0x401100 - (0x401000 + 7)) + b"\x90" * 9
        stub_flt = b"\x8b\x09\xe9" + struct.pack("<i", 0x401200 - (0x401010 + 7)) + b"\x90" * 9
        buf = bytearray(b"\xCC" * 0x300)
        buf[0x000:0x000 + len(stub_int)] = stub_int
        buf[0x010:0x010 + len(stub_flt)] = stub_flt
        t_int = make_pop_target(3)
        t_flt = make_pop_target(4)
        buf[0x100:0x100 + len(t_int)] = t_int
        buf[0x200:0x200 + len(t_flt)] = t_flt

        bv = _make_x86_view([(0x401000, bytes(buf))])
        r_int = synthesize_unique(bv, 0x401000, min_bytes=12)
        r_flt = synthesize_unique(bv, 0x401010, min_bytes=12)
        self.assertEqual(r_int.kind, "xref_thunk")
        self.assertEqual(r_flt.kind, "xref_thunk")
        self.assertNotEqual(r_int.target_pattern, r_flt.target_pattern)
        hit_int = bv.scan_masked(bytes.fromhex(r_int.target_pattern), bytes.fromhex(r_int.target_mask))
        hit_flt = bv.scan_masked(bytes.fromhex(r_flt.target_pattern), bytes.fromhex(r_flt.target_mask))
        self.assertEqual(hit_int, [0x401100])
        self.assertEqual(hit_flt, [0x401200])


if __name__ == "__main__":
    unittest.main()

"""Command-line entry point for sigforge."""
from __future__ import annotations

import argparse
import json
import sys

from .binary_view import BinaryView
from .synthesizer import extract_field_offset, synthesize_unique


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="sigforge", description="Instruction-aware binary signature synthesizer")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_synth = sub.add_parser("synth", help="Synthesize unique signature at VA")
    p_synth.add_argument("binary")
    p_synth.add_argument("va")
    p_synth.add_argument("--min-bytes", type=int, default=12)
    p_synth.add_argument("--max-bytes", type=int, default=96)

    p_scan = sub.add_parser("scan", help="Scan binary for masked pattern + mask")
    p_scan.add_argument("binary")
    p_scan.add_argument("pattern")
    p_scan.add_argument("mask")

    p_field = sub.add_parser("field", help="Extract struct displacement from accessor VA")
    p_field.add_argument("binary")
    p_field.add_argument("va")
    p_field.add_argument("--occurrence", type=int, default=0)

    args = ap.parse_args(argv)
    bv = BinaryView.from_file(args.binary)

    if args.cmd == "synth":
        va = int(args.va, 0)
        res = synthesize_unique(bv, va, min_bytes=args.min_bytes, max_bytes=args.max_bytes)
        print(json.dumps(res.__dict__, indent=2))
        return 0 if res.kind != "unresolved" else 1

    if args.cmd == "scan":
        hits = bv.scan_masked(bytes.fromhex(args.pattern), bytes.fromhex(args.mask), max_hits=10)
        print(json.dumps({"hits": [hex(h) for h in hits], "count": len(hits)}, indent=2))
        return 0 if len(hits) == 1 else 1

    if args.cmd == "field":
        fe = extract_field_offset(bv, int(args.va, 0), occurrence=args.occurrence)
        print(json.dumps(fe.__dict__ if fe else None, indent=2))
        return 0 if fe else 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())

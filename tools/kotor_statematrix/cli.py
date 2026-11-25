"""CLI entry point for live KOTOR procedural state-matrix verification."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from kotor_statematrix.adapter import (  # noqa: E402
    KotorStateMatrixTransport,
    build_kotor_universes,
    load_kotor_routines,
)
from statematrix import (  # noqa: E402
    MatrixRunner,
    ProbeResult,
    generate_function_probes,
    synthesize_from_traces,
    write_reports,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run procedural KOTOR live state-matrix tests")
    parser.add_argument("--target", required=True, choices=("k1", "k2-wine", "k2-native"), help="Target build")
    parser.add_argument("--out-dir", required=True, help="Output directory for matrix JSON/MD")
    parser.add_argument("--save-dir", default=None, help="Optional save dir override")
    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    transport = KotorStateMatrixTransport(args.target, save_dir=args.save_dir)
    runner = MatrixRunner(transport, max_recoveries=2)
    universes = {u.universe_id: u for u in build_kotor_universes()}
    all_results: List[ProbeResult] = []

    try:
        # U0: Boot + lazy hooks + offline kp.* APIs + dynamic demand activation
        u0 = universes["U0_boot_lazy"]
        ctx0 = transport.prepare_universe(u0)
        for c in transport.build_u0_api_probes():
            if c.case_id == "U0:api:dynamic_lazy_hook_activation":
                all_results.append(transport.run_u0_dynamic_lazy_test())
            else:
                all_results.append(transport.execute_probe(u0, c, ctx0))
        transport.teardown_universe(u0, ctx0)

        # U1: Live gameplay APIs + full procedural routine sweep with VM stack balance
        u1 = universes["U1_gameplay_routines_and_apis"]
        ctx1 = transport.prepare_universe(u1)
        for c in transport.build_u1_api_probes():
            all_results.append(transport.execute_probe(u1, c, ctx1))

        fn_cases = generate_function_probes(
            load_kotor_routines(transport.target.game),
            u1,
            context_values=ctx1.get("context_values"),
        )
        all_results.extend(transport.run_routine_sweep_batched(u1, fn_cases, batch_size=40))
        transport.teardown_universe(u1, ctx1)

        # U2: Live events + paired A/B return-value tests
        u2 = universes["U2_events_and_returns"]
        ctx2 = transport.prepare_universe(u2)
        all_results.extend(transport.run_u2_suite())
        transport.teardown_universe(u2, ctx2)

        # U3: Capture live traces -> synthesize -> replay
        u3 = universes["U3_trace_capture"]
        all_results.extend(
            runner.run_universe(
                u3,
                [],
                on_trace_cases=lambda u, trs: synthesize_from_traces(trs, u),
            )
        )
    finally:
        transport.close()

    json_path = out_dir / f"{args.target}_matrix.json"
    md_path = out_dir / f"{args.target}_matrix.md"
    summary = write_reports(
        all_results,
        json_path,
        md_path,
        title=f"KotorJIT State Matrix Verification ({args.target})",
        metadata={
            "target": args.target,
            "build": transport.boot_status.get("build", ""),
            "game": transport.target.game,
        },
    )
    print(f"[kotor_statematrix] summary for {args.target}: {summary['by_status']}")
    print(f"[kotor_statematrix] wrote {json_path} and {md_path}")
    failed = summary["by_status"].get("failed", 0) + summary["by_status"].get("crashed", 0)
    return 1 if (failed > 0 or summary["invariant_failures"] > 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())

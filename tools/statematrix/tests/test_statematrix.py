"""Unit tests for the domain-agnostic tools/statematrix framework."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List

TOOLS_DIR = Path(__file__).resolve().parents[2]
PKG_DIR = Path(__file__).resolve().parents[1]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from statematrix import (  # noqa: E402
    EventSpec,
    FunctionSpec,
    MatrixRunner,
    ParamSpec,
    ProbeCase,
    ProbeResult,
    SafetyTier,
    TraceRecord,
    UniverseSpec,
    classify_functions,
    generate_event_ab_probes,
    generate_function_probes,
    synthesize_from_traces,
    write_reports,
)


class _MockTransport:
    def __init__(self) -> None:
        self.alive = True
        self.prepared: List[str] = []
        self.executed: List[str] = []

    def prepare_universe(self, universe: UniverseSpec) -> Dict[str, Any]:
        self.alive = True
        self.prepared.append(universe.universe_id)
        return {"booted": True}

    def execute_probe(
        self, universe: UniverseSpec, case: ProbeCase, context: Dict[str, Any]
    ) -> ProbeResult:
        self.executed.append(case.case_id)
        if case.target_name == "ExplodingFn":
            self.alive = False
            raise RuntimeError("simulated process crash")
        return ProbeResult(
            case_id=case.case_id,
            universe_id=universe.universe_id,
            kind=case.kind,
            target_name=case.target_name,
            variant=case.variant,
            status="passed",
            observed={"args": case.args},
            invariants_ok=True,
        )

    def capture_traces(self, universe: UniverseSpec, context: Dict[str, Any]) -> List[TraceRecord]:
        return [
            TraceRecord(source="mock", target_name="GetTickCount", args=[], return_value=42),
            TraceRecord(source="mock", target_name="Abs", args=[-7], return_value=7),
        ]

    def teardown_universe(self, universe: UniverseSpec, context: Dict[str, Any]) -> None:
        pass

    def is_alive(self) -> bool:
        return self.alive


class StateMatrixTest(unittest.TestCase):
    def test_no_domain_specific_identifiers(self) -> None:
        forbidden = ("kotor", "swkotor", "nwscript", "kotorjit")
        for py_file in PKG_DIR.rglob("*.py"):
            if py_file.resolve() == Path(__file__).resolve():
                continue
            text = py_file.read_text(encoding="utf-8").lower()
            for word in forbidden:
                self.assertNotIn(word, text, f"{py_file} contains forbidden identifier '{word}'")

    def test_classifier_and_procedural_generation(self) -> None:
        funcs = classify_functions([
            FunctionSpec("Abs", 1, "int", [ParamSpec("n", "int")], 1),
            FunctionSpec("GetPlayerName", 2, "string", [ParamSpec("id", "object")], 1),
            FunctionSpec("DestroyWorld", 3, "void", [ParamSpec("id", "object")], 1),
            FunctionSpec("DelayCommand", 4, "void", [ParamSpec("f", "float")], 1),
        ])
        self.assertEqual(funcs[0].safety_tier, SafetyTier.PURE_QUERY)
        self.assertEqual(funcs[1].safety_tier, SafetyTier.STATEFUL_READ)
        self.assertEqual(funcs[2].safety_tier, SafetyTier.DESTRUCTIVE_OR_UNSAFE)
        self.assertEqual(funcs[3].safety_tier, SafetyTier.CONTROL_FLOW_CLOSURE)

        uni = UniverseSpec(universe_id="u_idle", description="idle universe")
        probes = generate_function_probes(funcs, uni, context_values={"object": [0x100]})
        by_name = {p.target_name: p for p in probes}
        self.assertEqual(by_name["Abs"].args, [0])
        self.assertEqual(by_name["GetPlayerName"].args, [0x100])
        self.assertIn("skip_reason", by_name["DestroyWorld"].expected)
        self.assertTrue(by_name["DelayCommand"].expected.get("expect_error"))

    def test_ab_events_and_trace_synthesis(self) -> None:
        uni = UniverseSpec(universe_id="u_events", description="events")
        events = [
            EventSpec("OnGate", dispatchable=True, cancellable=True, return_type="bool", override_values=[False], allow_values=[True]),
            EventSpec("OnDead", dispatchable=False),
        ]
        ev_probes = generate_event_ab_probes(events, uni)
        self.assertEqual(len(ev_probes), 3)
        variants = [p.variant for p in ev_probes]
        self.assertEqual(variants, ["A_override", "B_allow", "skip_undispatchable"])

        traces = [TraceRecord(source="live", target_name="Abs", args=[-5])]
        synth = synthesize_from_traces(traces, uni)
        self.assertEqual(len(synth), 1)
        self.assertEqual(synth[0].args, [-5])

    def test_runner_recovery_and_reporting(self) -> None:
        uni = UniverseSpec(universe_id="u_run", description="runner test")
        cases = [
            ProbeCase("c1", "function", "u_run", "Abs", [-1]),
            ProbeCase("c2", "function", "u_run", "ExplodingFn", []),
            ProbeCase("c3", "function", "u_run", "GetTickCount", []),
        ]
        tr = _MockTransport()
        runner = MatrixRunner(tr, max_recoveries=2)
        res = runner.run_universe(uni, cases, on_trace_cases=lambda u, ts: synthesize_from_traces(ts, u))
        statuses = {r.case_id: r.status for r in res}
        self.assertEqual(statuses["c1"], "passed")
        self.assertEqual(statuses["c2"], "crashed")
        self.assertEqual(statuses["c3"], "passed")
        self.assertGreaterEqual(len(tr.prepared), 2)

        with tempfile.TemporaryDirectory() as tmp:
            jpath = Path(tmp) / "out.json"
            mpath = Path(tmp) / "out.md"
            summary = write_reports(res, jpath, mpath)
            self.assertEqual(summary["by_status"]["crashed"], 1)
            self.assertEqual(json.loads(jpath.read_text())["summary"]["total"], len(res))
            self.assertIn("u_run", mpath.read_text())


if __name__ == "__main__":
    unittest.main()

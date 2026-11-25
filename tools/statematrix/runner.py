"""Universe-oriented execution runner with crash/recovery handling."""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Protocol

from .schema import ProbeCase, ProbeResult, TraceRecord, UniverseSpec


class Transport(Protocol):
    def prepare_universe(self, universe: UniverseSpec) -> Dict[str, Any]: ...
    def execute_probe(self, universe: UniverseSpec, case: ProbeCase, context: Dict[str, Any]) -> ProbeResult: ...
    def capture_traces(self, universe: UniverseSpec, context: Dict[str, Any]) -> List[TraceRecord]: ...
    def teardown_universe(self, universe: UniverseSpec, context: Dict[str, Any]) -> None: ...
    def is_alive(self) -> bool: ...


class MatrixRunner:
    def __init__(self, transport: Transport, max_recoveries: int = 2) -> None:
        self.transport = transport
        self.max_recoveries = max_recoveries

    def run_universe(
        self,
        universe: UniverseSpec,
        cases: List[ProbeCase],
        on_trace_cases: Optional[Callable[[UniverseSpec, List[TraceRecord]], List[ProbeCase]]] = None,
    ) -> List[ProbeResult]:
        results: List[ProbeResult] = []
        context = self.transport.prepare_universe(universe)
        recoveries = 0

        try:
            for case in cases:
                skip_reason = case.expected.get("skip_reason")
                if skip_reason:
                    results.append(
                        ProbeResult(
                            case_id=case.case_id,
                            universe_id=universe.universe_id,
                            kind=case.kind,
                            target_name=case.target_name,
                            variant=case.variant,
                            status="skipped",
                            reason=str(skip_reason),
                        )
                    )
                    continue

                t0 = time.monotonic()
                try:
                    res = self.transport.execute_probe(universe, case, context)
                except Exception as exc:
                    elapsed = (time.monotonic() - t0) * 1000.0
                    alive = False
                    try:
                        alive = self.transport.is_alive()
                    except Exception:
                        alive = False
                    results.append(
                        ProbeResult(
                            case_id=case.case_id,
                            universe_id=universe.universe_id,
                            kind=case.kind,
                            target_name=case.target_name,
                            variant=case.variant,
                            status="crashed" if not alive else "failed",
                            duration_ms=elapsed,
                            reason=f"transport exception: {exc}",
                            invariants_ok=False,
                        )
                    )
                    if not alive:
                        if recoveries >= self.max_recoveries:
                            break
                        recoveries += 1
                        try:
                            self.transport.teardown_universe(universe, context)
                        except Exception:
                            pass
                        context = self.transport.prepare_universe(universe)
                    continue

                if res.duration_ms == 0.0:
                    res.duration_ms = (time.monotonic() - t0) * 1000.0
                results.append(res)

            if on_trace_cases is not None and self.transport.is_alive():
                traces = self.transport.capture_traces(universe, context)
                extra_cases = on_trace_cases(universe, traces)
                for case in extra_cases:
                    t0 = time.monotonic()
                    try:
                        res = self.transport.execute_probe(universe, case, context)
                        if res.duration_ms == 0.0:
                            res.duration_ms = (time.monotonic() - t0) * 1000.0
                        results.append(res)
                    except Exception as exc:
                        results.append(
                            ProbeResult(
                                case_id=case.case_id,
                                universe_id=universe.universe_id,
                                kind=case.kind,
                                target_name=case.target_name,
                                variant=case.variant,
                                status="failed",
                                duration_ms=(time.monotonic() - t0) * 1000.0,
                                reason=str(exc),
                                invariants_ok=False,
                            )
                        )
        finally:
            try:
                self.transport.teardown_universe(universe, context)
            except Exception:
                pass

        return results

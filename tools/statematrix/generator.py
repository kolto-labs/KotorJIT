"""Procedural generator for function sweeps, A/B event probes, and trace synthesis."""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .schema import (
    EventSpec,
    FunctionSpec,
    ProbeCase,
    SafetyTier,
    TraceRecord,
    UniverseSpec,
)

DEFAULT_SCALARS: Dict[str, Any] = {
    "int": 0,
    "i32": 0,
    "u32": 0,
    "float": 1.0,
    "f32": 1.0,
    "string": "statematrix",
    "cstr": "statematrix",
    "bool": False,
    "vector": {"x": 0.0, "y": 0.0, "z": 0.0},
}


def default_args_for_function(
    fn: FunctionSpec,
    context_values: Optional[Dict[str, List[Any]]] = None,
) -> Tuple[bool, List[Any], str]:
    """Build concrete call arguments for required parameters.

    Returns (constructible, args, skip_reason).
    """
    ctx = context_values or {}
    args: List[Any] = []
    req = fn.required_count if fn.required_count >= 0 else len(fn.params)
    for idx in range(req):
        if idx >= len(fn.params):
            break
        p = fn.params[idx]
        t = p.type_name.lower()
        if t in ctx and ctx[t]:
            args.append(ctx[t][0])
        elif t in DEFAULT_SCALARS:
            args.append(DEFAULT_SCALARS[t])
        else:
            return False, [], f"no context sample available for required type '{p.type_name}'"
    return True, args, ""


def generate_function_probes(
    functions: Sequence[FunctionSpec],
    universe: UniverseSpec,
    context_values: Optional[Dict[str, List[Any]]] = None,
    allowed_tiers: Optional[Set[str]] = None,
) -> List[ProbeCase]:
    tiers = allowed_tiers if allowed_tiers is not None else set(universe.allowed_tiers)
    cases: List[ProbeCase] = []
    for fn in functions:
        if not fn.callable:
            cases.append(
                ProbeCase(
                    case_id=f"{universe.universe_id}:fn:{fn.name}:uncallable",
                    kind="function",
                    universe_id=universe.universe_id,
                    target_name=fn.name,
                    variant="skip_uncallable",
                    expected={"skip_reason": fn.metadata.get("why_not", "marked uncallable")},
                    metadata={"func_id": fn.func_id, "tier": fn.safety_tier},
                )
            )
            continue

        if fn.safety_tier == SafetyTier.CONTROL_FLOW_CLOSURE:
            cases.append(
                ProbeCase(
                    case_id=f"{universe.universe_id}:fn:{fn.name}:closure_refusal",
                    kind="function",
                    universe_id=universe.universe_id,
                    target_name=fn.name,
                    variant="expect_error",
                    expected={"expect_error": True},
                    metadata={"func_id": fn.func_id, "tier": fn.safety_tier},
                )
            )
            continue

        if fn.safety_tier not in tiers:
            cases.append(
                ProbeCase(
                    case_id=f"{universe.universe_id}:fn:{fn.name}:tier_excluded",
                    kind="function",
                    universe_id=universe.universe_id,
                    target_name=fn.name,
                    variant="skip_tier",
                    expected={
                        "skip_reason": f"safety tier '{fn.safety_tier}' excluded in '{universe.universe_id}'"
                    },
                    metadata={"func_id": fn.func_id, "tier": fn.safety_tier},
                )
            )
            continue

        ok, args, reason = default_args_for_function(fn, context_values)
        if not ok:
            cases.append(
                ProbeCase(
                    case_id=f"{universe.universe_id}:fn:{fn.name}:missing_context",
                    kind="function",
                    universe_id=universe.universe_id,
                    target_name=fn.name,
                    variant="skip_context",
                    expected={"skip_reason": reason},
                    metadata={"func_id": fn.func_id, "tier": fn.safety_tier},
                )
            )
            continue

        cases.append(
            ProbeCase(
                case_id=f"{universe.universe_id}:fn:{fn.name}",
                kind="function",
                universe_id=universe.universe_id,
                target_name=fn.name,
                args=args,
                variant="default",
                expected={"check_balance": True, "returns": fn.returns},
                metadata={"func_id": fn.func_id, "tier": fn.safety_tier},
            )
        )
    return cases


def generate_event_ab_probes(
    events: Sequence[EventSpec],
    universe: UniverseSpec,
) -> List[ProbeCase]:
    cases: List[ProbeCase] = []
    for ev in events:
        if not ev.dispatchable:
            cases.append(
                ProbeCase(
                    case_id=f"{universe.universe_id}:ev:{ev.name}:not_dispatchable",
                    kind="event_ab",
                    universe_id=universe.universe_id,
                    target_name=ev.name,
                    variant="skip_undispatchable",
                    expected={"skip_reason": "event is marked not dispatchable"},
                )
            )
            continue

        if ev.override_values or ev.allow_values:
            if ev.override_values:
                cases.append(
                    ProbeCase(
                        case_id=f"{universe.universe_id}:ev:{ev.name}:A_override",
                        kind="event_ab",
                        universe_id=universe.universe_id,
                        target_name=ev.name,
                        args=[ev.override_values[0]],
                        variant="A_override",
                        expected={"effect": "override_or_suppress", "return_value": ev.override_values[0]},
                        metadata={"hook_site": ev.hook_site},
                    )
                )
            if ev.allow_values:
                cases.append(
                    ProbeCase(
                        case_id=f"{universe.universe_id}:ev:{ev.name}:B_allow",
                        kind="event_ab",
                        universe_id=universe.universe_id,
                        target_name=ev.name,
                        args=[ev.allow_values[0]],
                        variant="B_allow",
                        expected={"effect": "allow_or_pass", "return_value": ev.allow_values[0]},
                        metadata={"hook_site": ev.hook_site},
                    )
                )
        else:
            cases.append(
                ProbeCase(
                    case_id=f"{universe.universe_id}:ev:{ev.name}:observe",
                    kind="event_ab",
                    universe_id=universe.universe_id,
                    target_name=ev.name,
                    variant="observe",
                    expected={"effect": "observed"},
                    metadata={"hook_site": ev.hook_site},
                )
            )
    return cases


def synthesize_from_traces(
    traces: Iterable[TraceRecord],
    universe: UniverseSpec,
    existing_keys: Optional[Set[str]] = None,
) -> List[ProbeCase]:
    seen = set(existing_keys or ())
    cases: List[ProbeCase] = []
    for idx, tr in enumerate(traces):
        sig = f"{tr.source}:{tr.target_name}:{repr(tr.args)}"
        if sig in seen:
            continue
        seen.add(sig)
        cases.append(
            ProbeCase(
                case_id=f"{universe.universe_id}:trace:{idx}:{tr.target_name}",
                kind="trace_replay",
                universe_id=universe.universe_id,
                target_name=tr.target_name,
                args=list(tr.args),
                variant="trace_replay",
                expected={"check_balance": True, "trace_source": tr.source},
                metadata=dict(tr.metadata),
            )
        )
    return cases

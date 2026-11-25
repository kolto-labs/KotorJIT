"""Domain-agnostic data structures for state-space test synthesis."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


class SafetyTier:
    PURE_QUERY = "pure_query"
    STATEFUL_READ = "stateful_read"
    REVERSIBLE_MUTATION = "reversible_mutation"
    DESTRUCTIVE_OR_UNSAFE = "destructive_or_unsafe"
    CONTROL_FLOW_CLOSURE = "control_flow_closure"

    ALL = (
        PURE_QUERY,
        STATEFUL_READ,
        REVERSIBLE_MUTATION,
        DESTRUCTIVE_OR_UNSAFE,
        CONTROL_FLOW_CLOSURE,
    )


@dataclass(frozen=True)
class ParamSpec:
    name: str
    type_name: str
    optional: bool = False
    default: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FunctionSpec:
    name: str
    func_id: int
    returns: str
    params: List[ParamSpec] = field(default_factory=list)
    required_count: int = 0
    safety_tier: str = ""
    callable: bool = True
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def with_tier(self, tier: str) -> "FunctionSpec":
        return FunctionSpec(
            name=self.name,
            func_id=self.func_id,
            returns=self.returns,
            params=self.params,
            required_count=self.required_count,
            safety_tier=tier,
            callable=self.callable,
            tags=list(self.tags),
            metadata=dict(self.metadata),
        )

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["params"] = [p.to_dict() for p in self.params]
        return d


@dataclass(frozen=True)
class EventSpec:
    name: str
    dispatchable: bool = True
    cancellable: bool = False
    return_type: str = "void"
    hook_site: str = ""
    override_values: List[Any] = field(default_factory=list)
    allow_values: List[Any] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class UniverseSpec:
    universe_id: str
    description: str
    setup_config: Dict[str, Any] = field(default_factory=dict)
    allowed_tiers: List[str] = field(
        default_factory=lambda: [SafetyTier.PURE_QUERY, SafetyTier.STATEFUL_READ]
    )
    isolation_group: str = "default"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProbeCase:
    case_id: str
    kind: str  # "function" | "event_ab" | "api" | "trace_replay"
    universe_id: str
    target_name: str
    args: List[Any] = field(default_factory=list)
    variant: str = "default"  # e.g. "A_override", "B_allow"
    expected: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TraceRecord:
    source: str
    target_name: str
    args: List[Any] = field(default_factory=list)
    return_value: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ProbeResult:
    case_id: str
    universe_id: str
    kind: str
    target_name: str
    variant: str
    status: str  # "passed" | "failed" | "skipped" | "crashed"
    duration_ms: float = 0.0
    reason: str = ""
    observed: Dict[str, Any] = field(default_factory=dict)
    invariants_ok: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

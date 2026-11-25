"""Procedural state-space testing and matrix verification framework."""

from .classifier import ClassificationRules, classify_function, classify_functions
from .generator import (
    default_args_for_function,
    generate_event_ab_probes,
    generate_function_probes,
    synthesize_from_traces,
)
from .report import summarize_results, write_reports
from .runner import MatrixRunner, Transport
from .schema import (
    EventSpec,
    FunctionSpec,
    ParamSpec,
    ProbeCase,
    ProbeResult,
    SafetyTier,
    TraceRecord,
    UniverseSpec,
)

__all__ = [
    "ClassificationRules",
    "EventSpec",
    "FunctionSpec",
    "MatrixRunner",
    "ParamSpec",
    "ProbeCase",
    "ProbeResult",
    "SafetyTier",
    "TraceRecord",
    "Transport",
    "UniverseSpec",
    "classify_function",
    "classify_functions",
    "default_args_for_function",
    "generate_event_ab_probes",
    "generate_function_probes",
    "summarize_results",
    "synthesize_from_traces",
    "write_reports",
]

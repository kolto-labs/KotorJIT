"""KOTOR adapter for the domain-agnostic tools/statematrix framework."""

from .adapter import KotorStateMatrixTransport, build_kotor_universes, load_kotor_events, load_kotor_routines

__all__ = [
    "KotorStateMatrixTransport",
    "build_kotor_universes",
    "load_kotor_events",
    "load_kotor_routines",
]

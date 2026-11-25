"""Deterministic safety-tier classifier for arbitrary function specs."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Tuple

from .schema import FunctionSpec, SafetyTier


@dataclass(frozen=True)
class ClassificationRules:
    closure_names: Tuple[str, ...] = ("AssignCommand", "DelayCommand", "ActionDoCommand")
    destructive_substrings: Tuple[str, ...] = (
        "Destroy",
        "Kill",
        "Death",
        "Damage",
        "Quit",
        "Exit",
        "EndGame",
        "LoadModule",
        "StartNewModule",
        "JumpTo",
        "Delete",
        "RemoveFromParty",
        "SetGlobal",
        "SetLocal",
        "GiveXP",
        "AddJournal",
        "Create",
        "ApplyEffect",
        "Action",
        "ClearAll",
        "SetFacing",
        "SetCommandable",
        "PlayMovie",
        "Show",
        "Open",
        "SetGame",
        "SetLocked",
        "Surrender",
        "Adjust",
        "SetPlot",
        "SetMinOneHP",
        "SetImmortal",
        "Spawn",
        "Reset",
        "Bark",
        "Speak",
        "SendMessage",
        "FloatingText",
        "ExecuteScript",
        "SignalEvent",
        "Cancel",
        "ChangeToStandardFaction",
        "Unlock",
        "Lock",
        "Pause",
    )
    query_prefixes: Tuple[str, ...] = (
        "Get",
        "Is",
        "Has",
        "Check",
        "Find",
        "Count",
        "Query",
        "Abs",
        "Sin",
        "Cos",
        "Tan",
        "Asin",
        "Acos",
        "Atan",
        "Sqrt",
        "Pow",
        "Log",
        "IntTo",
        "FloatTo",
        "StringTo",
        "ObjectTo",
        "Vector",
        "Magnitude",
        "Normalize",
        "Random",
        "d2",
        "d3",
        "d4",
        "d6",
        "d8",
        "d10",
        "d12",
        "d20",
        "d100",
        "RoundsToSeconds",
        "HoursToSeconds",
        "TurnsToSeconds",
        "FeetToMeters",
        "YardsToMeters",
    )
    pure_prefixes: Tuple[str, ...] = (
        "Abs",
        "Sin",
        "Cos",
        "Tan",
        "Asin",
        "Acos",
        "Atan",
        "Sqrt",
        "Pow",
        "Log",
        "IntTo",
        "FloatTo",
        "StringTo",
        "Vector",
        "Magnitude",
        "Random",
        "GetString",
        "GetSubString",
        "FindSubString",
        "RoundsToSeconds",
        "HoursToSeconds",
        "TurnsToSeconds",
    )
    reversible_prefixes: Tuple[str, ...] = (
        "SetTag",
        "SetLockKeyRequired",
        "SetMaxHitPoints",
    )


DEFAULT_RULES = ClassificationRules()


def classify_function(
    fn: FunctionSpec, rules: ClassificationRules = DEFAULT_RULES
) -> FunctionSpec:
    """Assign a SafetyTier based on signature, return type, and naming rules."""
    if fn.safety_tier:
        return fn

    name = fn.name
    if name in rules.closure_names:
        return fn.with_tier(SafetyTier.CONTROL_FLOW_CLOSURE)

    if any(name.startswith(p) for p in rules.reversible_prefixes):
        return fn.with_tier(SafetyTier.REVERSIBLE_MUTATION)

    if any(sub in name for sub in rules.destructive_substrings):
        return fn.with_tier(SafetyTier.DESTRUCTIVE_OR_UNSAFE)

    if any(name.startswith(p) for p in rules.pure_prefixes) and fn.returns != "void":
        return fn.with_tier(SafetyTier.PURE_QUERY)

    if any(name.startswith(p) for p in rules.query_prefixes) and fn.returns != "void":
        return fn.with_tier(SafetyTier.STATEFUL_READ)

    if fn.returns == "void":
        return fn.with_tier(SafetyTier.DESTRUCTIVE_OR_UNSAFE)

    return fn.with_tier(SafetyTier.STATEFUL_READ)


def classify_functions(
    functions: Iterable[FunctionSpec], rules: ClassificationRules = DEFAULT_RULES
) -> List[FunctionSpec]:
    return [classify_function(f, rules) for f in functions]

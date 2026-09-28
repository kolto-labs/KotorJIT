"""Scenario actions for the physical F12 console, separate from input plumbing."""
from __future__ import annotations

import json
import time
from pathlib import Path
from collections.abc import Mapping as MappingABC
from typing import Any, Mapping

from .console_protocol import ConsoleProtocolError, display_text
from .owned_x11 import OwnedInputError, OwnedX11Input
from .physical_console import (ChannelConsoleProtocolPort, PhysicalConsoleDriver,
                               PhysicalConsoleFailure, thaw_receipt)


CONSOLE_VERBS = frozenset(("console_open", "console_command", "owned_input", "advance_ticks"))


class ConsoleStepError(RuntimeError):
    def __init__(self, detail: str, *, state: Any = None):
        super().__init__(detail)
        self.state = state


def _receipt(runner: Any, name: str, body: Mapping[str, Any]) -> None:
    try:
        path = Path(runner.run_dir) / name
        encoded = json.dumps(thaw_receipt(body), indent=None if path.suffix == ".jsonl" else 2) + "\n"
        if path.suffix == ".jsonl":
            with path.open("a") as stream:
                stream.write(encoded)
        else:
            path.write_text(encoded)
    except OSError:
        # A receipt failure must not turn an already diagnosed protocol error
        # into an unhelpful secondary failure.
        pass


def _typed_value_equal(actual: Any, expected: Any) -> bool:
    """Compare JSON-like typed values while allowing frozen lists and mappings."""
    if isinstance(actual, MappingABC) or isinstance(expected, MappingABC):
        if not isinstance(actual, MappingABC) or not isinstance(expected, MappingABC):
            return False
        return (len(actual) == len(expected) and actual.keys() == expected.keys()
                and all(_typed_value_equal(actual[key], expected[key]) for key in actual))
    if isinstance(actual, (list, tuple)) or isinstance(expected, (list, tuple)):
        if not isinstance(actual, (list, tuple)) or not isinstance(expected, (list, tuple)):
            return False
        return len(actual) == len(expected) and all(
            _typed_value_equal(left, right) for left, right in zip(actual, expected))
    return type(actual) is type(expected) and actual == expected


def _expect_values(raw: Mapping[str, Any], outcome: Mapping[str, Any]) -> None:
    expected = raw.get("expect_values")
    if expected is not None and (not isinstance(expected, list) or not _typed_value_equal(outcome.get("values"), expected)):
        raise ConsoleStepError("typed console returns do not match expect_values")
    if "return_count" in raw and str(outcome.get("return_count")) != str(raw["return_count"]):
        raise ConsoleStepError("console return_count does not match expected value")


def _evidence_strings(value: Any, field: str) -> tuple[str, ...]:
    if isinstance(value, str):
        values = (value,)
    elif isinstance(value, (list, tuple)):
        values = tuple(value)
    else:
        raise ConsoleStepError(f"{field} must be a string or array of strings")
    if not 1 <= len(values) <= 64:
        raise ConsoleStepError(f"{field} must contain 1..64 non-empty strings")
    if any(not isinstance(item, str) or not item or len(item) > 8192 for item in values):
        raise ConsoleStepError(f"{field} must contain 1..64 non-empty strings of at most 8192 characters")
    return values


def _console_command(runner: Any, step: Any) -> str:
    raw = step.raw
    try:
        input_adapter = OwnedX11Input.from_session(runner.session)
        entry = input_adapter.console_entry(keys_before_submit=raw.get("keys_before_submit", ()),
                                            suffix=str(raw.get("suffix", "")))
        source = str(raw["code"])
        input_evidence = _evidence_strings(raw.get("input_contains", (source,) if source else ()),
                                           "input_contains")
        result_evidence = _evidence_strings(raw.get("contains", ()), "contains")
        receipt = PhysicalConsoleDriver(ChannelConsoleProtocolPort(runner.ch), entry).execute(
            source, timeout=float(raw.get("timeout", 30)),
            input_evidence=input_evidence, result_evidence=result_evidence)
        _expect_values(raw, receipt.outcome)
        if "kind" in raw and not any(display_text(line.get("kind"), "line.kind") == raw["kind"]
                                      for line in receipt.lines):
            raise ConsoleStepError(f"console missing output kind {raw['kind']!r}")
        _receipt(runner, f"console-command-{step.index}.json", {
            "input": "real owned-window keyboard", "identity": receipt.identity.__dict__,
            "request": receipt.request, "outcome": receipt.outcome,
            "lines": list(receipt.lines), "code": raw["code"],
        })
        return f"physical console request {receipt.request} Succeeded"
    except (ConsoleProtocolError, PhysicalConsoleFailure, OwnedInputError, KeyError, TypeError, ValueError) as error:
        baseline = getattr(error, "baseline", None)
        last = getattr(error, "last", None)
        _receipt(runner, f"console-command-{step.index}-failure.json", {
            "error": f"{type(error).__name__}: {error}",
            "baseline": baseline.__dict__ if baseline else None, "last": last,
            "step": dict(raw), "last_state": getattr(runner.ch, "last_state", None),
        })
        raise ConsoleStepError(str(error), state=getattr(runner.ch, "last_state", None)) from error


def execute_console_step(runner: Any, step: Any) -> str:
    raw = step.raw
    verb = str(raw["do"])
    try:
        if verb == "console_open":
            wanted = bool(raw.get("open", True))
            input_adapter = OwnedX11Input.from_session(runner.session)
            PhysicalConsoleDriver(ChannelConsoleProtocolPort(runner.ch), input_adapter).open_overlay(
                wanted, timeout=float(raw.get("timeout", 10)))
            return f"F12 overlay open={wanted}"
        if verb == "console_command":
            return _console_command(runner, step)
        if verb == "owned_input":
            adapter = OwnedX11Input.from_session(runner.session)
            action = str(raw.get("action", "key"))
            adapter.action(action, raw)
            _receipt(runner, "owned-input.jsonl", {"step": step.index, "action": action,
                                                     "window": adapter.target.window})
            return f"sent {action} to owned game window {adapter.target.window}"
        if verb == "advance_ticks":
            clock = str(raw.get("clock", "server"))
            if clock not in ("server", "client"):
                raise ConsoleStepError("advance_ticks clock must be server or client")
            ticks = raw.get("ticks")
            if isinstance(ticks, bool) or not isinstance(ticks, int) or not 1 <= ticks <= 100000:
                raise ConsoleStepError("advance_ticks requires ticks in 1..100000")
            field = clock + "_tick"
            start = int(runner.ch.state()[field])
            deadline = time.monotonic() + float(raw.get("timeout", 120))
            last = None
            while True:
                last = runner.ch.state()
                current = int(last[field])
                if current < start:
                    raise ConsoleStepError(f"{clock} tick reset ({start} -> {current})", state=last)
                if current >= start + ticks:
                    return f"observed {clock} ticks {start} -> {last[field]}"
                verdict = runner.watchdog.check(last)
                if verdict:
                    raise ConsoleStepError(str(verdict), state=last)
                if time.monotonic() >= deadline:
                    raise ConsoleStepError(f"{clock} tick interval did not elapse", state=last)
                time.sleep(0.2)
    except (ConsoleProtocolError, OwnedInputError, KeyError, TypeError, ValueError) as error:
        raise ConsoleStepError(str(error), state=getattr(runner.ch, "last_state", None)) from error
    raise ConsoleStepError(f"unknown console verb {verb!r}")

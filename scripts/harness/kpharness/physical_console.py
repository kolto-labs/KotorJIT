"""Exact correlation of one physical F12 entry to one ``kp.console.v1`` result.

This boundary deliberately offers no submit, Lua, exec, or replay operation.
Only its owned-input port can create a Console request.
"""
from __future__ import annotations

import time
from collections.abc import Mapping as MappingABC
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Protocol, Sequence

from .console_protocol import ConsoleIdentity, ConsoleProtocolError, canonical_u64, display_text, _u64


class ConsoleProtocolPort(Protocol):
    def status(self, runtime: str | None = None) -> Mapping[str, Any]: ...
    def outcome(self, runtime: str, session: str, request: str) -> Mapping[str, Any]: ...
    def output(self, runtime: str, session: str, after_sequence: str) -> Mapping[str, Any]: ...


class OwnedInputPort(Protocol):
    def focus_owned_game_window(self) -> None: ...
    def press_f12(self) -> None: ...
    def select_all(self) -> None: ...
    def type_text(self, source: str) -> None: ...
    def press_enter(self) -> None: ...


class Clock(Protocol):
    def monotonic(self) -> float: ...
    def sleep(self, seconds: float) -> None: ...


class SystemClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


class FrozenMapping(MappingABC):
    """A non-``dict`` mapping whose nested receipt data cannot be altered."""

    __slots__ = ("__data",)

    def __init__(self, values: Mapping[Any, Any]):
        object.__setattr__(self, "_FrozenMapping__data", MappingProxyType(dict(values)))

    def __setattr__(self, name: str, value: Any) -> None:
        raise TypeError("physical console receipt is immutable")

    def __getitem__(self, key: Any) -> Any:
        return self.__data[key]

    def __iter__(self):
        return iter(self.__data)

    def __len__(self) -> int:
        return len(self.__data)

    def _blocked(self, *_: Any, **__: Any) -> None:
        raise TypeError("physical console receipt is immutable")

    __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = __ior__ = __or__ = _blocked


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return FrozenMapping({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def thaw_receipt(value: Any) -> Any:
    """Convert immutable receipt data to JSON-safe ordinary containers."""
    if isinstance(value, Mapping):
        return {key: thaw_receipt(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [thaw_receipt(item) for item in value]
    return value


@dataclass(frozen=True)
class PhysicalConsoleReceipt:
    identity: ConsoleIdentity
    request: str
    outcome: Mapping[str, Any]
    lines: tuple[Mapping[str, Any], ...]


class PhysicalConsoleFailure(ConsoleProtocolError):
    """Typed refusal retaining immutable pre-input identity and last response."""
    def __init__(self, code: str, baseline: ConsoleIdentity | None,
                 detail: str, last: Mapping[str, Any] | None = None):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.baseline = baseline
        self.last = _freeze(last) if last is not None else None


class ChannelConsoleProtocolPort:
    """Production wrapper exposing observations only; it cannot wire-submit."""
    def __init__(self, channel: Any):
        self._channel = channel

    def _call(self, op: str, **fields: str) -> Mapping[str, Any]:
        response = self._channel.request("devtools", protocol="kp.console.v1", op=op, **fields)
        if not isinstance(response, Mapping):
            raise ConsoleProtocolError(f"console {op} returned no object")
        return response

    def status(self, runtime: str | None = None) -> Mapping[str, Any]:
        return self._call("status", **({"runtime": runtime} if runtime is not None else {}))

    def outcome(self, runtime: str, session: str, request: str) -> Mapping[str, Any]:
        return self._call("outcome", runtime=runtime, session=session, request=request)

    def output(self, runtime: str, session: str, after_sequence: str) -> Mapping[str, Any]:
        return self._call("output", runtime=runtime, session=session, after_sequence=after_sequence)


def _require_protocol(response: Mapping[str, Any], op: str) -> None:
    if response.get("protocol") != "kp.console.v1":
        raise ConsoleProtocolError(f"console {op} did not acknowledge kp.console.v1")
    if not isinstance(response.get("runtime"), str) or not response["runtime"]:
        raise ConsoleProtocolError(f"console {op} omitted runtime")


def _identity(response: Mapping[str, Any]) -> ConsoleIdentity:
    _require_protocol(response, "status")
    if response.get("status") != "Found":
        raise ConsoleProtocolError(f"console status is {response.get('status')!r}")
    return ConsoleIdentity(str(response["runtime"]),
                           canonical_u64(response.get("session"), "session", nonzero=True),
                           canonical_u64(response.get("submitted"), "submitted"),
                           canonical_u64(response.get("last_line"), "last_line"))


class PhysicalConsoleDriver:
    """One physical entry.  Success needs exact identity, outcome, and evidence."""
    def __init__(self, protocol: ConsoleProtocolPort, input_port: OwnedInputPort,
                 clock: Clock | None = None):
        self.protocol, self.input, self.clock = protocol, input_port, clock or SystemClock()
        self._last: Mapping[str, Any] | None = None

    def _record(self, raw: Any) -> Mapping[str, Any]:
        if not isinstance(raw, Mapping):
            raise ConsoleProtocolError("console response is not an object")
        self._last = _freeze(raw)
        return raw

    def _status(self, baseline: ConsoleIdentity | None, phase: str) -> tuple[ConsoleIdentity, Mapping[str, Any]]:
        raw = self._record(self.protocol.status(baseline.runtime if baseline else None))
        _require_protocol(raw, "status")
        if raw.get("status") == "StaleRuntime" or (baseline is not None and raw["runtime"] != baseline.runtime):
            raise PhysicalConsoleFailure("StaleRuntime", baseline, f"runtime changed during {phase}", raw)
        if raw.get("status") != "Found":
            raise PhysicalConsoleFailure("StatusRefused", baseline, f"status {raw.get('status')!r} during {phase}", raw)
        current = _identity(raw)
        if baseline is not None and current.session != baseline.session:
            raise PhysicalConsoleFailure("StaleSession", baseline, f"session changed during {phase}", raw)
        return current, raw

    def _until_open(self, baseline: ConsoleIdentity, timeout: float) -> None:
        deadline = self.clock.monotonic() + timeout
        while True:
            _, raw = self._status(baseline, "F12 open")
            if raw.get("open") is True:
                return
            if self.clock.monotonic() >= deadline:
                raise PhysicalConsoleFailure("OpenTimeout", baseline, "F12 did not report open=true", raw)
            self.clock.sleep(0.1)

    def _submission(self, baseline: ConsoleIdentity, timeout: float) -> str:
        candidate = _u64(baseline.submitted, "submitted") + 1
        if candidate > 0xffffffffffffffff:
            raise PhysicalConsoleFailure("SubmissionOverflow", baseline, "submitted cannot advance past uint64", self._last)
        candidate_text = str(candidate)
        deadline = self.clock.monotonic() + timeout
        while True:
            current, raw = self._status(baseline, "physical submission")
            submitted = _u64(current.submitted, "submitted")
            if submitted < _u64(baseline.submitted, "submitted"):
                raise PhysicalConsoleFailure("SubmittedRegression", baseline, "submitted counter regressed", raw)
            if current.submitted == candidate_text:
                return candidate_text
            if submitted > candidate:
                raise PhysicalConsoleFailure("DuplicateSubmission", baseline,
                                             f"submitted {current.submitted}, expected {candidate_text}", raw)
            if self.clock.monotonic() >= deadline:
                raise PhysicalConsoleFailure("SubmissionTimeout", baseline,
                                             f"submitted remained {current.submitted}, expected {candidate_text}", raw)
            self.clock.sleep(0.1)

    def _outcome(self, baseline: ConsoleIdentity, request: str, timeout: float) -> Mapping[str, Any]:
        deadline = self.clock.monotonic() + timeout
        while True:
            raw = self._record(self.protocol.outcome(baseline.runtime, baseline.session, request))
            _require_protocol(raw, "outcome")
            if raw["runtime"] != baseline.runtime:
                raise PhysicalConsoleFailure("StaleRuntime", baseline, "runtime changed during outcome", raw)
            status = raw.get("status")
            if status == "StaleSession":
                raise PhysicalConsoleFailure("StaleSession", baseline, "session reset during outcome", raw)
            if status in ("Expired", "Unavailable"):
                raise PhysicalConsoleFailure(str(status), baseline, "exact request outcome unavailable", raw)
            if status != "Found" or not isinstance(raw.get("outcome"), Mapping):
                raise PhysicalConsoleFailure("OutcomeRefused", baseline, f"outcome status {status!r}", raw)
            outcome = raw["outcome"]
            if (canonical_u64(outcome.get("session"), "outcome.session", nonzero=True) != baseline.session
                    or canonical_u64(outcome.get("request"), "outcome.request", nonzero=True) != request):
                raise PhysicalConsoleFailure("IdentityMismatch", baseline, "outcome is not the physical request", raw)
            state = outcome.get("state")
            if state == "Succeeded":
                return _freeze(outcome)
            if state in ("Failed", "Cancelled"):
                raise PhysicalConsoleFailure(str(state), baseline, f"exact request {state.lower()}", raw)
            if state not in ("Pending", "Running"):
                raise PhysicalConsoleFailure("OutcomeRefused", baseline, f"unknown state {state!r}", raw)
            if self.clock.monotonic() >= deadline:
                raise PhysicalConsoleFailure("OutcomeTimeout", baseline, f"exact request remained {state}", raw)
            self.clock.sleep(0.1)

    def _output(self, baseline: ConsoleIdentity, request: str, input_evidence: Sequence[str],
                result_evidence: Sequence[str]) -> tuple[Mapping[str, Any], ...]:
        raw = self._record(self.protocol.output(baseline.runtime, baseline.session, baseline.last_line))
        _require_protocol(raw, "output")
        if raw["runtime"] != baseline.runtime:
            raise PhysicalConsoleFailure("StaleRuntime", baseline, "runtime changed during output", raw)
        if raw.get("status") == "StaleSession":
            raise PhysicalConsoleFailure("StaleSession", baseline, "session reset during output", raw)
        if raw.get("status") != "Found" or canonical_u64(raw.get("session"), "output.session", nonzero=True) != baseline.session:
            raise PhysicalConsoleFailure("OutputRefused", baseline, "output was not Found for baseline session", raw)
        if _u64(raw.get("dropped_through"), "dropped_through") > _u64(baseline.last_line, "last_line"):
            raise PhysicalConsoleFailure("DroppedOutput", baseline, "output cursor was evicted", raw)
        rows = raw.get("lines")
        if not isinstance(rows, list):
            raise PhysicalConsoleFailure("OutputRefused", baseline, "output omitted lines", raw)
        matched = tuple(_freeze(row) for row in rows if isinstance(row, Mapping)
                        and canonical_u64(row.get("session"), "line.session", nonzero=True) == baseline.session
                        and canonical_u64(row.get("request"), "line.request") == request)
        if not matched:
            raise PhysicalConsoleFailure("MissingOutput", baseline, "no output belongs to exact request", raw)
        by_kind: dict[str, list[Mapping[str, Any]]] = {"input": [], "result": []}
        for row in matched:
            kind = display_text(row.get("kind"), "line.kind")
            if kind in by_kind:
                by_kind[kind].append(row)
        if not by_kind["input"]:
            raise PhysicalConsoleFailure("MissingInputOutput", baseline, "exact request has no input line", raw)
        if not by_kind["result"]:
            raise PhysicalConsoleFailure("MissingResultOutput", baseline, "exact request has no result line", raw)
        for kind, evidence in (("input", input_evidence), ("result", result_evidence)):
            text = "\n".join(display_text(row.get("text"), "line.text") for row in by_kind[kind])
            missing = [item for item in evidence if item not in text]
            if missing:
                raise PhysicalConsoleFailure("MissingOutput", baseline,
                                             f"{kind} output lacks {missing!r}", raw)
        return matched

    def open_overlay(self, wanted: bool, *, timeout: float = 10.0) -> ConsoleIdentity:
        """Toggle F12 only on this owned input port and preserve failure context."""
        baseline, initial = self._status(None, "baseline")
        try:
            self.input.focus_owned_game_window()
            if initial.get("open") is not wanted:
                self.input.press_f12()
            deadline = self.clock.monotonic() + timeout
            while True:
                _, raw = self._status(baseline, "F12 toggle")
                if raw.get("open") is wanted:
                    return baseline
                if self.clock.monotonic() >= deadline:
                    raise PhysicalConsoleFailure("OpenTimeout", baseline,
                                                 f"F12 did not become open={wanted}", raw)
                self.clock.sleep(0.1)
        except PhysicalConsoleFailure:
            raise
        except ConsoleProtocolError as error:
            raise PhysicalConsoleFailure("MalformedProtocol", baseline, str(error), self._last) from error
        except Exception as error:
            raise PhysicalConsoleFailure("InputFailure", baseline, f"{type(error).__name__}: {error}", self._last) from error

    def execute(self, source: str, *, timeout: float = 30.0,
                input_evidence: Sequence[str], result_evidence: Sequence[str]) -> PhysicalConsoleReceipt:
        if not isinstance(source, str):
            raise TypeError("physical console source must be a string")
        # Discovery failure has no baseline. Every later failure is normalised.
        baseline, initial = self._status(None, "baseline")
        try:
            self.input.focus_owned_game_window()
            if initial.get("open") is not True:
                self.input.press_f12()
                self._until_open(baseline, timeout)
            _, ready = self._status(baseline, "post-focus before edit")
            if ready.get("open") is not True:
                raise PhysicalConsoleFailure("OverlayClosed", baseline, "overlay closed before edit", ready)
            self.input.select_all()
            self.input.type_text(source)
            self.input.press_enter()  # Sole physical submission; never replayed.
            request = self._submission(baseline, timeout)
            outcome = self._outcome(baseline, request, timeout)
            lines = self._output(baseline, request, input_evidence, result_evidence)
            return PhysicalConsoleReceipt(baseline, request, outcome, lines)
        except PhysicalConsoleFailure:
            raise
        except ConsoleProtocolError as error:
            raise PhysicalConsoleFailure("MalformedProtocol", baseline, str(error), self._last) from error
        except Exception as error:
            raise PhysicalConsoleFailure("InputFailure", baseline, f"{type(error).__name__}: {error}", self._last) from error

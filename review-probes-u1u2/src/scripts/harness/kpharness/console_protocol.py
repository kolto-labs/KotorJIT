"""Client-side contract checks for the ``kp.console.v1`` harness adapter.

The native Console is the only evaluator.  This module only sends versioned
``devtools`` observations and turns the wire contract into per-request facts
for a physical-keyboard scenario.  In particular, ``completed`` is recorded
for diagnostics but is never used as a success predicate.
"""
from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional


PROTOCOL = "kp.console.v1"
TERMINAL_STATES = frozenset(("Succeeded", "Failed", "Cancelled"))


class ConsoleProtocolError(RuntimeError):
    """A versioned-console response cannot prove the requested fact."""


class ConsoleIdentityError(ConsoleProtocolError):
    """The runtime or Console session changed during one operation."""


class ConsoleRequestError(ConsoleProtocolError):
    """The specific request cannot be observed to its required outcome."""


def _u64(value: Any, field: str, *, nonzero: bool = False) -> int:
    if not isinstance(value, str) or not value.isascii() or not value.isdecimal():
        raise ConsoleProtocolError(f"console {field} must be a decimal string")
    if len(value) > 1 and value.startswith("0"):
        raise ConsoleProtocolError(f"console {field} must not have leading zeroes")
    parsed = int(value)
    if parsed > 0xffffffffffffffff or (nonzero and parsed == 0):
        raise ConsoleProtocolError(f"console {field} is outside its unsigned64 contract")
    return parsed


def canonical_u64(value: Any, field: str, *, nonzero: bool = False) -> str:
    """Validate an adapter ID while preserving its exact wire representation."""
    _u64(value, field, nonzero=nonzero)
    return value


def decode_bytes(value: Any, field: str = "bytes") -> bytes:
    """Decode one lossless adapter byte object without treating it as text."""
    if not isinstance(value, Mapping):
        raise ConsoleProtocolError(f"console {field} must be a byte object")
    if value.get("encoding") != "base64" or not isinstance(value.get("data"), str):
        raise ConsoleProtocolError(f"console {field} has invalid byte encoding")
    size = _u64(value.get("byte_length"), f"{field}.byte_length")
    try:
        decoded = base64.b64decode(value["data"], validate=True)
    except (ValueError, TypeError) as error:
        raise ConsoleProtocolError(f"console {field} has invalid base64") from error
    if len(decoded) != size:
        raise ConsoleProtocolError(f"console {field} byte length does not match base64")
    return decoded


def display_text(value: Any, field: str = "bytes") -> str:
    """Make assertion text readable while retaining raw bytes in receipts."""
    return decode_bytes(value, field).decode("utf-8", errors="replace")


@dataclass(frozen=True)
class ConsoleIdentity:
    runtime: str
    session: str
    submitted: str
    last_line: str


@dataclass(frozen=True)
class ConsoleOutcome:
    identity: ConsoleIdentity
    request: str
    state: str
    raw: Mapping[str, Any]


class ConsoleClient:
    """Strict, small client for ``cmd=devtools, protocol=kp.console.v1``."""

    def __init__(self, channel: Any, *, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self.channel = channel
        self._clock = clock
        self._sleep = sleep

    def _call(self, op: str, **fields: Any) -> Mapping[str, Any]:
        result = self.channel.request("devtools", protocol=PROTOCOL, op=op, **fields)
        if not isinstance(result, Mapping):
            raise ConsoleProtocolError(f"console {op} returned no object")
        if result.get("protocol") != PROTOCOL:
            raise ConsoleProtocolError(f"console {op} did not acknowledge {PROTOCOL}")
        runtime = result.get("runtime")
        if not isinstance(runtime, str) or not runtime:
            raise ConsoleProtocolError(f"console {op} omitted runtime identity")
        return result

    @staticmethod
    def _identity(result: Mapping[str, Any], *, require_status: bool = True) -> ConsoleIdentity:
        if require_status and result.get("status") != "Found":
            raise ConsoleProtocolError(f"console status is {result.get('status')!r}, expected Found")
        return ConsoleIdentity(
            runtime=str(result["runtime"]),
            session=canonical_u64(result.get("session"), "session", nonzero=True),
            submitted=canonical_u64(result.get("submitted"), "submitted"),
            last_line=canonical_u64(result.get("last_line"), "last_line"),
        )

    def status(self, runtime: Optional[str] = None) -> ConsoleIdentity:
        fields = {"runtime": runtime} if runtime is not None else {}
        result = self._call("status", **fields)
        if runtime is not None and result["runtime"] != runtime:
            raise ConsoleIdentityError("console runtime changed while checking status")
        return self._identity(result)

    def capture(self) -> tuple[ConsoleIdentity, Mapping[str, Any]]:
        result = self._call("status")
        return self._identity(result), result

    def assert_identity(self, baseline: ConsoleIdentity) -> ConsoleIdentity:
        current = self.status(baseline.runtime)
        if current.runtime != baseline.runtime:
            raise ConsoleIdentityError("console runtime changed")
        if current.session != baseline.session:
            raise ConsoleIdentityError(
                f"console session reset/replaced ({baseline.session} -> {current.session})")
        return current

    def wait_open(self, baseline: ConsoleIdentity, wanted: bool, timeout: float,
                  *, poll: float = 0.1) -> ConsoleIdentity:
        deadline = self._clock() + timeout
        last: Optional[ConsoleIdentity] = None
        while True:
            raw = self._call("status", runtime=baseline.runtime)
            if raw.get("status") == "StaleRuntime" or raw.get("runtime") != baseline.runtime:
                raise ConsoleIdentityError("console runtime changed while toggling F12")
            current = self._identity(raw)
            if current.session != baseline.session:
                raise ConsoleIdentityError("console session reset while toggling F12")
            last = current
            if raw.get("open") is wanted:
                return current
            if self._clock() >= deadline:
                raise ConsoleRequestError(
                    f"F12 overlay did not become open={wanted}; last identity={last}")
            self._sleep(poll)

    def exact_submission(self, baseline: ConsoleIdentity) -> tuple[ConsoleIdentity, str]:
        """Require exactly one accepted request in the captured identity."""
        current = self.assert_identity(baseline)
        expected = _u64(baseline.submitted, "submitted") + 1
        current_submitted = _u64(current.submitted, "submitted")
        if current_submitted != expected:
            if current_submitted < expected:
                raise ConsoleRequestError(
                    f"physical console input created no request (submitted {baseline.submitted} -> {current.submitted})")
            raise ConsoleRequestError(
                f"physical console input created duplicate/extra requests (submitted {baseline.submitted} -> {current.submitted})")
        return current, str(expected)

    def outcome(self, identity: ConsoleIdentity, request: str) -> Optional[ConsoleOutcome]:
        result = self._call("outcome", runtime=identity.runtime, session=identity.session,
                            request=request)
        if result["runtime"] != identity.runtime:
            raise ConsoleIdentityError("console runtime changed while reading outcome")
        status = result.get("status")
        if status == "StaleSession":
            raise ConsoleIdentityError("console session reset while reading outcome")
        if status in ("Expired", "Unavailable"):
            raise ConsoleRequestError(f"console request {request} is {status}")
        if status != "Found":
            raise ConsoleProtocolError(f"console outcome has unexpected status {status!r}")
        raw = result.get("outcome")
        if not isinstance(raw, Mapping):
            raise ConsoleProtocolError("console Found outcome omitted outcome object")
        if canonical_u64(raw.get("session"), "outcome.session", nonzero=True) != identity.session:
            raise ConsoleIdentityError("outcome session does not match submitted session")
        if canonical_u64(raw.get("request"), "outcome.request", nonzero=True) != request:
            raise ConsoleRequestError("outcome request does not match keyboard submission")
        state = raw.get("state")
        if not isinstance(state, str):
            raise ConsoleProtocolError("outcome omitted state")
        return ConsoleOutcome(identity, request, state, raw)

    def wait_terminal(self, identity: ConsoleIdentity, request: str, timeout: float,
                      *, poll: float = 0.1) -> ConsoleOutcome:
        deadline = self._clock() + timeout
        last: Optional[ConsoleOutcome] = None
        while True:
            # The status read catches a reset even if a broken endpoint returns
            # a stale-looking Found outcome.
            self.assert_identity(identity)
            result = self.outcome(identity, request)
            if result is not None:
                last = result
                if result.state in TERMINAL_STATES:
                    return result
            if self._clock() >= deadline:
                state = last.state if last is not None else "missing"
                raise ConsoleRequestError(
                    f"console request {request} did not reach a terminal outcome (last={state})")
            self._sleep(poll)

    def output_for(self, identity: ConsoleIdentity, request: str) -> tuple[list[Mapping[str, Any]], Mapping[str, Any]]:
        result = self._call("output", runtime=identity.runtime, session=identity.session,
                            after_sequence=identity.last_line)
        if result["runtime"] != identity.runtime:
            raise ConsoleIdentityError("console runtime changed while reading output")
        status = result.get("status")
        if status == "StaleSession":
            raise ConsoleIdentityError("console session reset while reading output")
        if status != "Found":
            raise ConsoleProtocolError(f"console output has unexpected status {status!r}")
        if canonical_u64(result.get("session"), "output.session", nonzero=True) != identity.session:
            raise ConsoleIdentityError("output session does not match keyboard submission")
        dropped = _u64(result.get("dropped_through"), "output.dropped_through")
        if dropped > _u64(identity.last_line, "last_line"):
            raise ConsoleRequestError(
                f"console output was dropped through {dropped} after cursor {identity.last_line}")
        lines = result.get("lines")
        if not isinstance(lines, list):
            raise ConsoleProtocolError("console output omitted lines")
        matching: list[Mapping[str, Any]] = []
        for line in lines:
            if not isinstance(line, Mapping):
                raise ConsoleProtocolError("console output line is not an object")
            if canonical_u64(line.get("session"), "line.session", nonzero=True) != identity.session:
                continue
            if canonical_u64(line.get("request"), "line.request") == request:
                matching.append(line)
        return matching, result

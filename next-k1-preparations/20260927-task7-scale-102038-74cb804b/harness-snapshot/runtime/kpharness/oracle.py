"""Watchdog: turn "it is taking a while" into a named failure.

Every wait in the driver is a ceiling, not a schedule, so something has to
decide before the ceiling whether the game is still going anywhere. The
watchdog is polled from the wait loop with the latest state and answers
with a Verdict when one of these has tripped:

  crash      the process is gone, Wine printed an unhandled exception or
             started its debugger, or the runtime logged a fault.
  refusal    the runtime logged "refusing to install". Boot fails at once.
  hang       the process is alive but client_tick has not moved for
             hang_seconds, or the channel has not answered for that long.
             One stack dump is taken before the verdict is returned.
             While the last state said `loading` both of those use
             load_seconds instead: the client loop does not return during a
             load -- the engine runs its own nested screen-update loop, which
             is why the drain has a re-entry flag at all -- and a single frame
             there was measured at 8 to 30 seconds on 2026-09-09. Silence and
             a still tick are what a load looks like from outside, so
             load_stuck is the oracle that governs it, and a crash or a dead
             process is still reported the moment it is seen.
  load_stuck phase is `loading` beyond load_seconds with nothing in the
             load detail changing, or the authoritative server tick has not
             advanced for load_tick_seconds. llvmpipe loads are slow, so the
             latter has a conservative default above the measured long frame.
  softlock   phase is gameplay or dialog and the fingerprint (module,
             quantised pc position, dialog node, globals hash, journal hash,
             party) has not changed for stagnation_seconds while the
             scenario is waiting on a progress predicate. Reported with the
             last 200 events and the last screenshot.

A Verdict is data. The wait raises it as OracleTrip; the runner records it
and decides whether the scenario expected it.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Tuple

from .client import Channel

WINE_FATAL = re.compile(r"wine: Unhandled|starting debugger")
RUNTIME_FATAL = re.compile(r"fault in hook body|\[fault\] unrecoverable")
RUNTIME_REFUSAL = re.compile(r"refusing to install")


@dataclass
class Verdict:
    kind: str                     # crash | refusal | hang | load_stuck | softlock
    reason: str
    at: float = field(default_factory=time.time)
    state: Optional[Dict[str, Any]] = None
    events: List[dict] = field(default_factory=list)
    screenshot: Optional[str] = None
    stack_dump: Optional[str] = None
    detail: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind, "reason": self.reason, "at": self.at,
            "state": self.state, "events": self.events[-200:],
            "screenshot": self.screenshot, "stack_dump": self.stack_dump,
            "detail": self.detail,
        }

    def __str__(self) -> str:
        return f"{self.kind}: {self.reason}"


class OracleTrip(Exception):
    def __init__(self, verdict: Verdict):
        super().__init__(str(verdict))
        self.verdict = verdict


class Probe(Protocol):
    """What the watchdog needs from a session. GameSession provides it; the
    offline test provides a fake."""

    def process_alive(self) -> bool: ...
    def read_new_stderr(self) -> str: ...
    def read_new_runtime_log(self) -> str: ...
    def stack_dump(self) -> str: ...


def fingerprint(state: Dict[str, Any]) -> Tuple:
    """The parts of a state that change when the game makes progress.

    Position is quantised to half a metre so an idle animation or a
    floating-point drift does not count as movement.
    """
    pc = state.get("pc") or {}
    pos = None
    if pc:
        try:
            pos = (round(float(pc.get("x", 0.0)) * 2) / 2,
                   round(float(pc.get("y", 0.0)) * 2) / 2,
                   round(float(pc.get("z", 0.0)) * 2) / 2)
        except (TypeError, ValueError):
            pos = None
    dialog = state.get("dialog") or {}
    node = (dialog.get("entry"), dialog.get("reply")) if dialog else None
    party = tuple(sorted(str(p.get("id", p.get("tag", ""))) for p in (state.get("party") or [])
                         if isinstance(p, dict)))
    return (state.get("module"), pos, node, state.get("globals_hash"),
            state.get("journal_hash"), party)


def load_signature(state: Dict[str, Any]) -> Tuple:
    """Everything in phase_detail: any change means the load is advancing."""
    detail = state.get("phase_detail") or {}
    return tuple(sorted((str(k), str(v)) for k, v in detail.items())) + (state.get("module"),)


class Watchdog:
    def __init__(self, probe: Probe, channel: Optional[Channel] = None, *,
                 hang_seconds: float = 20.0, load_seconds: float = 300.0,
                 load_tick_seconds: float = 60.0,
                 stagnation_seconds: float = 120.0, log=None, shooter=None):
        self.probe = probe
        self.channel = channel
        self.hang_seconds = hang_seconds
        self.load_seconds = load_seconds
        self.load_tick_seconds = load_tick_seconds
        self.stagnation_seconds = stagnation_seconds
        self.log = log or (lambda s: None)
        self.shooter = shooter          # has .last_path when present
        self._tick: Optional[int] = None
        self._tick_since = time.monotonic()
        self._unresponsive_since: Optional[float] = None
        self._load_sig: Optional[Tuple] = None
        self._load_since = time.monotonic()
        self._load_server_tick: Optional[int] = None
        self._load_server_tick_since = time.monotonic()
        self._fp: Optional[Tuple] = None
        self._fp_since = time.monotonic()
        self._phase: Optional[str] = None      # last phase seen; None until a state is read
        self.tripped: Optional[Verdict] = None

    # ----------------------------------------------------------- helpers --
    def _verdict(self, kind: str, reason: str, state: Optional[dict], **detail) -> Verdict:
        events: List[dict] = []
        if self.channel is not None:
            try:
                events = self.channel.recent_events(200)
                if not events:
                    events = self.channel.events(since=max(0, self.channel.cursor - 200), limit=200)
            except Exception:  # the channel may be the thing that is broken
                events = list(self.channel.events_seen)[-200:]
        shot = getattr(self.shooter, "last_path", None)
        v = Verdict(kind=kind, reason=reason, state=state, events=events[-200:],
                    screenshot=str(shot) if shot else None, detail=detail)
        self.tripped = v
        self.log(f"oracle: {v}")
        return v

    def _stall_ceiling(self) -> Tuple[float, str]:
        """How long a silent or still process is given, and why.

        A load gets the load ceiling: the frames are legitimately that long.
        Anything else gets the hang ceiling, boot included -- the phase is
        None until the first state is read.
        """
        if self._phase == "loading":
            return self.load_seconds, "loading"
        return self.hang_seconds, "running"

    def reset_progress(self) -> None:
        """A new wait starts: stagnation is measured from here."""
        self._fp = None
        self._fp_since = time.monotonic()

    # ------------------------------------------------------------- crash --
    def check_logs(self) -> Optional[Verdict]:
        err = self.probe.read_new_stderr()
        rt = self.probe.read_new_runtime_log()
        if RUNTIME_REFUSAL.search(rt):
            line = next(l for l in rt.splitlines() if "refusing to install" in l)
            return self._verdict("refusal", line.strip(), None)
        if RUNTIME_FATAL.search(rt):
            line = next(l for l in rt.splitlines() if RUNTIME_FATAL.search(l))
            return self._verdict("crash", line.strip(), None)
        if WINE_FATAL.search(err):
            line = next(l for l in err.splitlines() if WINE_FATAL.search(l))
            return self._verdict("crash", line.strip(), None)
        return None

    def note_unresponsive(self) -> Optional[Verdict]:
        """The channel timed out. Crash first; then a hang after hang_seconds."""
        v = self.check_logs()
        if v:
            return v
        if not self.probe.process_alive():
            return self._verdict("crash", "process gone while the channel was silent", None)
        now = time.monotonic()
        if self._unresponsive_since is None:
            self._unresponsive_since = now
            return None
        ceiling, why = self._stall_ceiling()
        if now - self._unresponsive_since >= ceiling:
            dump = self.probe.stack_dump()
            v = self._verdict("hang", f"no channel reply for {ceiling:.0f}s while {why}", None)
            v.stack_dump = dump
            return v
        return None

    # ------------------------------------------------------------- check --
    def check(self, state: Optional[Dict[str, Any]], *,
              waiting_on_progress: bool = False) -> Optional[Verdict]:
        """Called once per poll with the state just read. None means carry on."""
        self._unresponsive_since = None
        now = time.monotonic()
        v = self.check_logs()
        if v:
            v.state = state
            return v
        if not self.probe.process_alive():
            return self._verdict("crash", "process gone", state)
        if state is None:
            return None

        # The phase is read before the tick check, because it decides the
        # ceiling that check uses.
        phase = state.get("phase")
        self._phase = str(phase) if phase is not None else None

        tick = state.get("client_tick")
        if isinstance(tick, int):
            ceiling, why = self._stall_ceiling()
            if tick != self._tick:
                self._tick, self._tick_since = tick, now
            elif now - self._tick_since >= ceiling:
                dump = self.probe.stack_dump()
                v = self._verdict("hang",
                                  f"client_tick {tick} unchanged for {ceiling:.0f}s while {why}",
                                  state)
                v.stack_dump = dump
                return v

        if phase == "loading":
            # Client frames can legitimately pause in the nested loading loop,
            # but the server tick is the harness's authoritative MainLoop
            # heartbeat.  A live channel with neither tick advancing was the
            # exact 20260910-095338 failure mode.
            server_tick = state.get("server_tick")
            if isinstance(server_tick, int):
                if server_tick != self._load_server_tick:
                    self._load_server_tick, self._load_server_tick_since = server_tick, now
                elif now - self._load_server_tick_since >= self.load_tick_seconds:
                    return self._verdict(
                        "load_stuck",
                        f"server_tick {server_tick} unchanged for {self.load_tick_seconds:.0f}s while loading",
                        state, server_tick=server_tick,
                        load_tick_seconds=self.load_tick_seconds)
            sig = load_signature(state)
            if sig != self._load_sig:
                self._load_sig, self._load_since = sig, now
            elif now - self._load_since >= self.load_seconds:
                return self._verdict("load_stuck",
                                     f"phase loading for {self.load_seconds:.0f}s with no change in "
                                     f"phase_detail", state, phase_detail=state.get("phase_detail"))
        else:
            self._load_sig = None
            self._load_server_tick = None

        if phase in ("gameplay", "dialog") and waiting_on_progress:
            fp = fingerprint(state)
            if fp != self._fp:
                self._fp, self._fp_since = fp, now
            elif now - self._fp_since >= self.stagnation_seconds:
                return self._verdict("softlock",
                                     f"fingerprint unchanged for {self.stagnation_seconds:.0f}s "
                                     f"while waiting for progress", state,
                                     fingerprint=[str(x) for x in fp])
        else:
            self._fp = None
        return None

"""CLI TAS: pioneer a route interactively, one verified step at a time.

The state-gated model (see scenario.py's module docstring) means a route is
reproducible because every step is gated on an observed engine-state
postcondition, not because it was typed correctly by hand. This module makes
that the actual authoring workflow instead of something inferred after the
fact from hand-edited TOML:

  kpharness pioneer init   --out ROUTE.toml --target k1 --name "..."
  kpharness pioneer step   --out ROUTE.toml '{"do": "lua", "code": "..."}'
  kpharness pioneer step   --out ROUTE.toml '{"wait": "phase", "equals": "gameplay"}'
  kpharness pioneer commit --out ROUTE.toml
  kpharness pioneer discard --out ROUTE.toml
  kpharness pioneer status --out ROUTE.toml

`step` executes the given step body against the live engine state right now,
over the same channel and the same verb/wait dispatch a real scenario run
uses (ScenarioRunner.run_step -- no separate code path, so nothing pioneered
here can drift from what replay actually does), and prints the result. It
never writes to ROUTE.toml itself; it only records what just happened as the
pending step. `commit` is the deliberate second action that appends exactly
that already-executed, already-inspected step to the file. `discard` drops
pending metadata only: it does not undo any change in the live game. This mirrors the session's own working method: run one
thing, look at the state, decide, only then bake it in.

ROUTE.toml must already exist (via `init`) before `step`/`commit`, and `step`
loads its current [settings] (authored_barks and friends) so what is
pioneered lives under the same policy replay will use.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import tempfile
import uuid
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from . import scenario as S
from .client import Channel
from .oracle import Watchdog
from .session import pids_by_name


class PioneerError(Exception):
    pass


class _SessionProbe:
    """Watchdog.Probe over an already-booted session's SessionInfo.

    Reads the same log files GameSession itself watches (session.py's
    ``_stderr_path``/``runtime_log``), by path rather than by a live process
    handle pioneer mode does not own. Each `pioneer step` is a fresh process,
    so there is no cross-call offset to remember -- this reads whichever
    files exist from the start every time, which is the honest cost of a
    one-shot CLI command rather than a long-lived watcher.
    """

    def __init__(self, info: Any):
        self.info = info

    def process_alive(self) -> bool:
        name = getattr(self.info, "process_name", "") or ""
        return bool(name) and bool(pids_by_name(name))

    def _read(self, path: Optional[Path]) -> str:
        if path is None or not path.is_file():
            return ""
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    def read_new_stderr(self) -> str:
        run_dir = getattr(self.info, "run_dir", "") or ""
        if not run_dir:
            return ""
        name = "wine.log" if getattr(self.info, "wineprefix", "") else "game.log"
        return self._read(Path(run_dir) / name)

    def read_new_runtime_log(self) -> str:
        game_dir = getattr(self.info, "game_dir", "") or ""
        return self._read(Path(game_dir) / "kotorphasor.log") if game_dir else ""

    def stack_dump(self) -> str:
        return "(stack dump not available in pioneer mode; attach gdb/winedbg directly if needed)"


def _pending_path(out: Path) -> Path:
    return out.with_name(out.name + ".pending.json")


@dataclass
class Pending:
    target: str
    step: Dict[str, Any]
    result: Dict[str, Any]
    recorded_at: float
    provenance: Dict[str, Any] = field(default_factory=dict)
    phase: str = "executed"

    def to_dict(self) -> Dict[str, Any]:
        return {"target": self.target, "step": self.step, "result": self.result,
               "recorded_at": self.recorded_at, "provenance": self.provenance, "phase": self.phase}

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Pending":
        return Pending(target=str(d["target"]), step=dict(d["step"]),
                       result=dict(d.get("result", {})), recorded_at=float(d.get("recorded_at", 0)),
                       provenance=dict(d.get("provenance", {})), phase=str(d.get("phase", "executed")))


def load_pending(out: Path) -> Optional[Pending]:
    p = _pending_path(out)
    if not p.is_file():
        return None
    try:
        return Pending.from_dict(json.loads(p.read_text()))
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise PioneerError(f"pending step at {p} is unreadable: {e}") from e


def save_pending(out: Path, pending: Pending) -> None:
    _atomic_write(_pending_path(out), json.dumps(pending.to_dict(), indent=1, allow_nan=False).encode())


def clear_pending(out: Path) -> None:
    p = _pending_path(out)
    if p.is_file():
        p.unlink()


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_hash(value: Any) -> str:
    return _digest(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())


def _atomic_write(path: Path, data: bytes) -> None:
    if path.is_symlink():
        raise PioneerError(f"refusing symlink destination: {path}")
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            os.chmod(temporary, path.stat().st_mode & 0o777)
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextlib.contextmanager
def route_lock(out: Path):
    """Serialize authoring commands, including the live execution transaction."""
    import fcntl
    lock = out.with_name(out.name + ".pioneer.lock")
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise PioneerError("another Pioneer command owns this route") from error
        yield
    finally:
        os.close(fd)


def session_proof(session: Any, channel: Channel) -> Dict[str, Any]:
    status = channel.status()
    if not isinstance(status, dict) or status.get("live") is not True:
        raise PioneerError("attached runtime is not live")
    if type(status.get("pid")) is not int or status["pid"] <= 0:
        raise PioneerError("runtime lacks a valid process identity")
    if not isinstance(status.get("build"), str) or not status["build"]:
        raise PioneerError("runtime lacks build identity")
    uptime = status.get("uptime_ms")
    if type(uptime) is not int or uptime < 0:
        raise PioneerError("runtime lacks uptime identity")
    fields = ("target", "started", "run_dir", "game_dir", "port", "launcher_pid", "build")
    attached = {name: getattr(session, name, None) for name in fields}
    if (not isinstance(attached["target"], str) or not attached["target"]
            or type(attached["started"]) not in (float, int)
            or not math.isfinite(attached["started"]) or attached["started"] <= 0
            or not attached["run_dir"] or not attached["game_dir"]
            or type(attached["port"]) is not int or not 0 < attached["port"] <= 65535):
        raise PioneerError("incomplete attached session identity")
    return {"identity": {"session": attached, "pid": status["pid"],
                         "runtime_build": status["build"], "version": status.get("version")},
            "uptime_ms": uptime}


def _same_session(before: dict, after: dict) -> bool:
    return (before.get("identity") == after.get("identity")
            and type(before.get("uptime_ms")) is int
            and after["uptime_ms"] >= before["uptime_ms"])


def execute_pending(out: Path, channel: Channel, session: Any, step: Dict[str, Any], *, log=None):
    """Persist an issued receipt before mutation; uncertain work is never retried."""
    with route_lock(out):
        if out.is_symlink():
            raise PioneerError("route must not be a symlink")
        prior = load_pending(out)
        if prior is not None and prior.phase != "committed":
            raise PioneerError("resolve the existing pending step before executing another")
        data = out.read_bytes()
        base = _load_header_only(out)
        proof = session_proof(session, channel)
        if base.target != proof["identity"]["session"]["target"]:
            raise PioneerError("route and attached session targets differ")
        candidate = data + ("\n" + render_step(step)).encode()
        # Validate the exact rendered route before touching the game.
        parsed = S.Scenario.parse(candidate.decode(), out)
        if len(parsed.steps) != len(base.steps) + 1 or parsed.steps[-1].raw != step:
            raise PioneerError("rendered step does not match requested step")
        provenance = {"schema": 2, "transaction": uuid.uuid4().hex,
                      "route": str(out.resolve()), "route_sha256": _digest(data),
                      "settings_sha256": _json_hash(base.settings), "session": proof,
                      "candidate_sha256": _digest(candidate), "index": len(base.steps) + 1,
                      "step_sha256": _json_hash(step)}
        pending = Pending(base.target, step, {}, time.time(), provenance, "issued")
        save_pending(out, pending)
        try:
            result = run_one_step(out, channel, session, step, log=log)
            if out.read_bytes() != data or not _same_session(proof, session_proof(session, channel)):
                raise PioneerError("route or attached session changed during execution; pending result is uncertain")
            pending.result = result.to_dict()
            pending.provenance["result_sha256"] = _json_hash(pending.result)
            pending.phase = "executed"
            save_pending(out, pending)
            return result
        except Exception as error:
            raise PioneerError(f"pending execution is uncertain; inspect before discarding: {error}") from error


def commit_pending(out: Path, channel: Channel, session: Any, *, force: bool = False) -> bool:
    """Atomic, retry-safe append. True=new append; False=already committed."""
    with route_lock(out):
        if out.is_symlink():
            raise PioneerError("route must not be a symlink")
        pending = load_pending(out)
        if pending is None:
            raise PioneerError("no pending step")
        p = pending.provenance
        try:
            valid = (p["schema"] == 2 and p["route"] == str(out.resolve())
                     and p["step_sha256"] == _json_hash(pending.step)
                     and p["result_sha256"] == _json_hash(pending.result)
                     and pending.phase in {"executed", "committing", "committed"}
                     and type(p["index"]) is int and p["index"] > 0
                     and pending.result.get("index") == p["index"]
                     and pending.result.get("status") in {"ok", "expected_failure", "failed"}
                     and pending.target == p["session"]["identity"]["session"]["target"]
                     and _same_session(p["session"], session_proof(session, channel)))
        except (KeyError, TypeError, ValueError) as error:
            raise PioneerError("malformed or legacy pending receipt; cannot commit") from error
        if not valid:
            raise PioneerError("stale, foreign or malformed pending receipt; cannot commit")
        if pending.result["status"] == "failed" and not force:
            raise PioneerError("failed pending step requires --force; this does not waive provenance")
        data = out.read_bytes()
        if _digest(data) == p["candidate_sha256"] and pending.phase in {"committing", "committed"}:
            pending.phase = "committed"
            save_pending(out, pending)
            return False
        if pending.phase == "committed" or _digest(data) != p["route_sha256"]:
            raise PioneerError("route changed since pending execution")
        base = _load_header_only(out)
        if (base.target != pending.target or _json_hash(base.settings) != p["settings_sha256"]
                or len(base.steps) + 1 != p["index"]):
            raise PioneerError("pending route settings/index no longer match")
        candidate = data + ("\n" + render_step(pending.step)).encode()
        if _digest(candidate) != p["candidate_sha256"]:
            raise PioneerError("pending append digest mismatch")
        parsed = S.Scenario.parse(candidate.decode(), out)
        if len(parsed.steps) != p["index"] or parsed.steps[-1].raw != pending.step:
            raise PioneerError("pending append no longer parses as its recorded step")
        pending.phase = "committing"
        save_pending(out, pending)
        # Detect non-cooperating edits made while writing the commit journal.
        if out.read_bytes() != data:
            raise PioneerError("route changed during commit")
        _atomic_write(out, candidate)
        pending.phase = "committed"
        save_pending(out, pending)
        return True


def discard_pending(out: Path) -> None:
    with route_lock(out):
        clear_pending(out)


# --------------------------------------------------------------- TOML out --
#
# tomllib (stdlib) is read-only, and the project takes no TOML-writing
# dependency, so `commit` only ever appends -- it never re-parses and
# rewrites the file -- and this serializer covers exactly the scalar/list
# shapes a step body can hold (JSON's, since `step` is parsed from JSON).
# A step is one flat [[step]] table, matching every hand-written route file
# in scripts/harness/scenarios/.

def _toml_value(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if not math.isfinite(v):
            raise PioneerError("a non-finite float has no TOML representation")
        s = repr(v)
        return s if ("." in s or "e" in s or "E" in s) else s + ".0"
    if isinstance(v, str):
        out = (v.replace("\\", "\\\\").replace('"', '\\"')
               .replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r"))
        return f'"{out}"'
    if isinstance(v, list):
        return "[" + ", ".join(_toml_value(x) for x in v) + "]"
    raise PioneerError(f"cannot render {v!r} ({type(v).__name__}) as a TOML value")


def render_step(step: Dict[str, Any]) -> str:
    lines = ["[[step]]"]
    for k, v in step.items():
        lines.append(f"{k} = {_toml_value(v)}")
    return "\n".join(lines) + "\n"


def init_route(out: Path, *, target: str, name: str, authored_barks: Optional[list] = None,
               force: bool = False) -> None:
    if out.exists() and not force:
        raise PioneerError(f"{out} already exists; pass force to overwrite")
    header = ['schema_version = 1', f'name = {_toml_value(name)}', f'target = {_toml_value(target)}']
    if authored_barks:
        for b in authored_barks:
            if isinstance(b, bool) or not isinstance(b, int):
                raise PioneerError("authored_barks must be a list of dialog entry integers")
        header += ["", "[execution]", f"authored_barks = {_toml_value(list(authored_barks))}"]
    text = "\n".join(header) + "\n"
    try:
        S.Scenario.parse(text, out, allow_empty=True)
    except S.ScenarioError as e:
        raise PioneerError(str(e)) from e
    _atomic_write(out, text.encode())


def append_step(out: Path, step: Dict[str, Any]) -> None:
    if not out.is_file():
        raise PioneerError(f"{out} does not exist; run `pioneer init` first")
    _atomic_write(out, out.read_bytes() + ("\n" + render_step(step)).encode())


def _load_header_only(out: Path) -> "S.Scenario":
    """Use replay validation, allowing only the empty step list during authoring."""
    try:
        return S.Scenario.parse(out.read_text(), out, allow_empty=True)
    except (S.ScenarioError, OSError) as e:
        raise PioneerError(f"{out}: {e}") from e


# ------------------------------------------------------------- execution --

def run_one_step(out: Path, channel: Channel, session: Any, step_body: Dict[str, Any],
                 *, log=None) -> "S.StepResult":
    """Execute one step body live, exactly as a real run would.

    Reuses ScenarioRunner.run_step verbatim -- the one dispatch path scenario
    replay itself uses -- against a Scenario reconstructed from ROUTE.toml's
    own current settings, so a pioneered step lives under the same
    authored_barks/timeout policy that will govern its later replay.
    """
    if not out.is_file():
        raise PioneerError(f"{out} does not exist; run `pioneer init` first")
    base = _load_header_only(out)
    if "do" not in step_body and "wait" not in step_body and "expect_events" not in step_body and not step_body.get("screenshot"):
        raise PioneerError('step body needs one of "do", "wait", "expect_events", or "screenshot"')
    step = S.Step(len(base.steps) + 1, dict(step_body))
    step.kind  # validate shape the same way Scenario.parse does
    declarations = {name: dict(kind=r.kind, source=r.source, file=r.file, size=r.size, sha256=r.sha256)
                    for name, r in base.resources.items()}
    try:
        resources = S.normalize_resources({"resources": declarations}, [step.raw], start_index=step.index)
    except S.ScenarioError as e:
        raise PioneerError(str(e)) from e
    scenario = S.Scenario(name=base.name, target=base.target, steps=[step],
                          settings=dict(base.settings), path=out, resources=resources)
    s = scenario.settings
    log = log or (lambda _msg: None)
    # session (a SessionInfo from an attached, already-booted process) has the
    # plain run_dir/game_dir/save_dir/build attributes ScenarioRunner wants,
    # but not the Probe methods GameSession implements; build the Watchdog
    # explicitly over the adapter instead of letting ScenarioRunner default to
    # treating session itself as the probe.
    watchdog = Watchdog(_SessionProbe(session), channel,
                        hang_seconds=float(s["hang_seconds"]),
                        load_seconds=float(s["load_seconds"]),
                        load_tick_seconds=float(s["load_tick_seconds"]),
                        stagnation_seconds=float(s["stagnation_seconds"]), log=log)
    runner = S.ScenarioRunner(scenario, session, channel, log=log, watchdog=watchdog)
    proof = session_proof(session, channel)

    def validate_owner():
        if not _same_session(proof, session_proof(session, channel)):
            raise PioneerError("attached session changed; refusing policy mutation")

    with runner.attached_execution(validate_owner) as ownership:
        result = runner.run_step(step)
        ownership["retain"] = step.raw.get("do") == "speed" and result.status == "ok"
        return result

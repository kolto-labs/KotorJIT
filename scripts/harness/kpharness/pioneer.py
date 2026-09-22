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
that already-executed, already-inspected step to the file. `discard` drops it
without writing. This mirrors the session's own working method: run one
thing, look at the state, decide, only then bake it in.

ROUTE.toml must already exist (via `init`) before `step`/`commit`, and `step`
loads its current [settings] (authored_barks and friends) so what is
pioneered lives under the same policy replay will use.
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
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

    def to_dict(self) -> Dict[str, Any]:
        return {"target": self.target, "step": self.step, "result": self.result,
               "recorded_at": self.recorded_at}

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Pending":
        return Pending(target=str(d["target"]), step=dict(d["step"]),
                       result=dict(d.get("result", {})), recorded_at=float(d.get("recorded_at", 0)))


def load_pending(out: Path) -> Optional[Pending]:
    p = _pending_path(out)
    if not p.is_file():
        return None
    try:
        return Pending.from_dict(json.loads(p.read_text()))
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise PioneerError(f"pending step at {p} is unreadable: {e}") from e


def save_pending(out: Path, pending: Pending) -> None:
    _pending_path(out).write_text(json.dumps(pending.to_dict(), indent=1, default=str))


def clear_pending(out: Path) -> None:
    p = _pending_path(out)
    if p.is_file():
        p.unlink()


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
    out.write_text(text)


def append_step(out: Path, step: Dict[str, Any]) -> None:
    if not out.is_file():
        raise PioneerError(f"{out} does not exist; run `pioneer init` first")
    with out.open("a") as f:
        f.write("\n" + render_step(step))


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
    return runner.run_step(step)

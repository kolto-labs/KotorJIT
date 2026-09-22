"""Scenarios: TOML step files and the runner that executes them.

A scenario is a name, a target, optional settings, and an ordered list of
steps. Each step is one of:

  do = "<verb>" ...            a request to the engine
  wait = "<kind>" ...          a state predicate with a timeout ceiling
  expect_events = [...]        events in this order since the last `do`
  screenshot = true            a frame, with expect_screen = "dialog" for OCR

Verbs: load_checkpoint (name), load_save (dir, globs allowed), save (slot,
name, checkpoint), warp (module), lua (code), assert_lua (code, equals), reply (pick), walk_dialog
(save or checkpoint, start, max_replies), door_transaction, door_security (door or tag),
door_commit_open (door or tag), placeable_transaction, dialog_skip, dialog_abort, dialog_clear_sound_wait, clear_auto_pause, new_game,
chargen_select_class (index), speed (scale), fixed_step (hz), movies (enabled),
advance_dialog (until phase), scripted_door_open (tag), clear_room (radius, until_global, until_value, grace),
move_to (tag or position, range, run, stall), equip_item (tag or item, slot), use_item (tag or item, if_hp_below), equipment_screen (visible),
set_global (name, value, type), unpause_timers, dismiss_messagebox, dismiss_container,
take_all_container, accept_party_selection, auto_levelup, set_party_leader (index), reload,
sleep (seconds), quit.

Waits: phase (equals), module (equals), event (name), global (name,
equals), journal (tag, equals), dialog, chargen, chargen_stage (equals). `timeout` is the ceiling in seconds
(default from settings). `progress = true` tells the softlock oracle that
this wait expects the game to move; module, event, global and journal waits
default to true, phase and dialog waits to false.

A wait may declare `expect_verdict = "softlock"`: the step passes only if
the oracle trips with that verdict inside the ceiling. That is how the
detector is proven against an induced softlock. A `do` may declare
`expect_error = "unsupported"` for a command a build is known to lack.

A command the build cannot honour ("unsupported on <build>") is a skipped
step with its reason, not a failure. The runner writes report.json next to
the run's logs and its exit status is non-zero on any failure.

Determinism / replay model (why a scenario is a headless TAS movie)
-------------------------------------------------------------------
A KotOR binary is a scriptable engine: this harness runs inside the process
with the full Lua routine API and native command access, and reads engine
state directly. So control is driven at the engine level, never through OS
keyboard/mouse input -- synthetic input is only for black-box engines and is
strictly worse here (wall-clock jitter, DirectInput, no frame lock).

Reproducibility comes from four rules, not from replaying timed keystrokes:

1. Fixed initial state. A route starts from `new_game` (or a `load_save` /
   checkpoint save state), so every run begins identically.
2. State-gated progression. Every action is followed by a `wait` on an
   independent engine-state postcondition before the next action runs. A step
   never advances on a timer; it advances on observed state (`wait global
   END_TRASK_DLG == 4`, a placeable's open-readback). Wall-clock `sleep` is a
   smell -- prefer a state gate.
3. Resolve by identity, not raw id. Object ids differ per run; address objects
   by tag + position (see world.select_route_object) so a route is stable
   across runs.
4. Fast, deterministic sim. `game_speed` (default 16x) and `fixed_step`
   decouple the run from real time; `save`/`load_save` provide TAS-style save
   states for branching and retry.

The TOML file is the movie: a high-level, editable action list whose replay
determinism is guaranteed by the state gates, not by input timing. Repeated
interaction patterns are generalized into composite verbs (e.g.
`placeable_transaction` = "walk to a container and open it") rather than
re-encoded per route.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import math
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    tomllib = None  # type: ignore[assignment]

from . import waits as W
from .checkpoints import CheckpointError, Checkpoints
from .client import Channel, ChannelError, summarise_state
from .oracle import OracleTrip, Verdict, Watchdog
from .shots import Shooter, check_screen
from . import world as World
from . import bwm as Bwm
from .resources import LEGACY_KEYS, Resource
from . import targets as T

DEFAULT_SETTINGS: Dict[str, Any] = {
    # A scenario is a headless/TAS run, so use the engine's fastest supported
    # timer scale unless the author explicitly asks for retail speed.  This is
    # applied once before the first step and the runtime re-applies it after
    # every engine SetGameSpeed call.
    "game_speed": 16.0,
    # Authored tutorial barks that wait on the player indefinitely. A route
    # lists the entries whose reply 0 is a terminator, and any of them that
    # interrupts a wait is answered instead of blocking it forever. A wait that
    # deliberately targets one of these entries is never answered out from
    # under itself.
    "authored_barks": [],
    "default_timeout": 120.0,
    "load_timeout": 300.0,
    "events_timeout": 60.0,
    "hang_seconds": 20.0,
    # Seconds a stuck dialog node is left alone before the ladder acts; see
    # _DialogDriver. Authored node delays on Endar run up to ~6s at 1x.
    "dialog_grace": 10.0,
    "load_seconds": 300.0,
    "load_tick_seconds": 60.0,
    "stagnation_seconds": 120.0,
    "shot_interval": 120.0,
}

FATAL_VERDICTS = ("crash", "hang", "refusal")


class ScenarioError(Exception):
    pass


def normalize_header(doc: Dict[str, Any], path: Optional[Path] = None) -> tuple:
    """One execution contract for replay and an empty Pioneer route."""
    version = doc.get("schema_version", 1)
    if type(version) is not int or version != 1:
        raise ScenarioError("schema_version must be 1 (or omitted for legacy routes)")
    unknown = set(doc) - {"schema_version", "name", "target", "settings", "execution", "resources", "step"}
    if unknown:
        raise ScenarioError(f"unknown scenario fields: {', '.join(sorted(unknown))}")
    name = doc.get("name", path.stem if path else "scenario")
    if not isinstance(name, str) or not name.strip():
        raise ScenarioError("name must be a non-empty string")
    target = doc.get("target")
    if target == "k2":
        target = "k2-native"
    if not isinstance(target, str) or target not in T.names():
        raise ScenarioError(f"{name}: target must be one of {', '.join(T.names())}")
    if "settings" in doc and "execution" in doc:
        raise ScenarioError(f"{name}: use [execution] or legacy [settings], not both")
    overrides = doc.get("execution", doc.get("settings", {}))
    if not isinstance(overrides, dict):
        raise ScenarioError(f"{name}: execution/settings must be a table")
    unknown = set(overrides) - DEFAULT_SETTINGS.keys()
    if unknown:
        raise ScenarioError(f"{name}: unknown execution settings: {', '.join(sorted(unknown))}")
    settings = dict(DEFAULT_SETTINGS, **overrides)
    for key, value in settings.items():
        if key == "authored_barks":
            if not isinstance(value, list) or any(type(b) is not int for b in value):
                raise ScenarioError(f"{name}: execution.authored_barks must be a list of dialog entries")
            settings[key] = list(value)
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ScenarioError(f"{name}: execution.{key} must be a finite number")
        try:
            value = float(value)
        except OverflowError as e:
            raise ScenarioError(f"{name}: execution.{key} must be a finite number") from e
        if not math.isfinite(value):
            raise ScenarioError(f"{name}: execution.{key} must be a finite number")
        if value < 0 or (key == "game_speed" and not 0 < value <= 16):
            raise ScenarioError(f"{name}: execution.{key} is out of range")
        settings[key] = float(value)
    return name, target, settings


def normalize_resources(doc: Dict[str, Any], raw_steps: List[dict], *, start_index: int = 1) -> Dict[str, Resource]:
    declarations = doc.get("resources", {})
    if not isinstance(declarations, dict):
        raise ScenarioError("resources must be a table of named resource tables")
    resources: Dict[str, Resource] = {}
    try:
        for name, raw in declarations.items():
            if not name.strip():
                raise ValueError("resource names must not be empty")
            resources[name] = Resource.parse(raw)
        for index, raw in enumerate(raw_steps, start_index):
            if any(key in raw for key in LEGACY_KEYS):
                if "resource" in raw:
                    raise ValueError(f"step {index}: cannot combine resource reference and inline declaration")
                resource = Resource.from_legacy(raw)
                name = next((key for key, value in resources.items() if value == resource), f"legacy-step-{index}")
                if name in resources and resources[name] != resource:
                    raise ValueError(f"step {index}: conflicting resource name {name!r}")
                resources[name] = resource
                raw["resource"] = name
                for key in LEGACY_KEYS:
                    raw.pop(key)
            if "resource" in raw:
                if not isinstance(raw["resource"], str) or raw["resource"] not in resources:
                    raise ValueError(f"step {index}: unknown resource reference {raw['resource']!r}")
                if raw.get("do") != "door_transaction":
                    raise ValueError(f"step {index}: resource is only supported by door_transaction")
        destinations: Dict[str, Resource] = {}
        for resource in resources.values():
            if resource.file in destinations and destinations[resource.file] != resource:
                raise ValueError(f"conflicting declarations for {resource.file}")
            destinations[resource.file] = resource
    except ValueError as e:
        raise ScenarioError(str(e)) from e
    return resources


def expand_semicolons(text: str) -> str:
    """Accept `do = "warp"; module = "x"` on one line.

    TOML has no statement separator, but the design document writes steps
    that way and it reads well for two-key steps. A `;` outside a string
    on a key = value line becomes a newline; lines inside multi-line
    strings and comments are left alone.
    """
    out: List[str] = []
    in_multiline: Optional[str] = None
    for line in text.splitlines():
        if in_multiline:
            out.append(line)
            if in_multiline in line:
                in_multiline = None
            continue
        stripped = line.lstrip()
        if not stripped or stripped[0] in "#[":
            out.append(line)
            continue
        for q in ('"""', "'''"):
            if q in line and line.count(q) % 2 == 1:
                in_multiline = q
        if in_multiline or ";" not in line:
            out.append(line)
            continue
        parts: List[str] = []
        cur: List[str] = []
        quote: Optional[str] = None
        i = 0
        while i < len(line):
            c = line[i]
            if quote:
                cur.append(c)
                if c == "\\" and quote == '"' and i + 1 < len(line):
                    cur.append(line[i + 1])
                    i += 1
                elif c == quote:
                    quote = None
            elif c in ('"', "'"):
                quote = c
                cur.append(c)
            elif c == "#":
                cur.append(line[i:])
                break
            elif c == ";":
                parts.append("".join(cur))
                cur = []
            else:
                cur.append(c)
            i += 1
        parts.append("".join(cur))
        out.extend(p.strip() for p in parts if p.strip())
    return "\n".join(out) + "\n"


@dataclass
class Step:
    index: int
    raw: Dict[str, Any]
    label: str = ""

    @property
    def kind(self) -> str:
        for key in ("do", "wait"):
            if key in self.raw and (not isinstance(self.raw[key], str) or not self.raw[key].strip()):
                raise ScenarioError(f"step {self.index}: {key} must be a non-empty string")
        if "expect_events" in self.raw:
            events = self.raw["expect_events"]
            if not isinstance(events, list) or any(not isinstance(e, (str, dict)) for e in events):
                raise ScenarioError(f"step {self.index}: expect_events must be an array of names or event tables")
        if "screenshot" in self.raw and type(self.raw["screenshot"]) is not bool:
            raise ScenarioError(f"step {self.index}: screenshot must be a boolean")
        kinds = [key for key in ("do", "wait", "expect_events") if key in self.raw]
        if self.raw.get("screenshot"):
            kinds.append("screenshot")
        if len(kinds) != 1:
            raise ScenarioError(f"step {self.index}: needs exactly one do/wait/expect_events/screenshot")
        if "do" in self.raw:
            return "do"
        if "wait" in self.raw:
            return "wait"
        if "expect_events" in self.raw:
            return "expect_events"
        if self.raw.get("screenshot"):
            return "screenshot"
        raise ScenarioError(f"step {self.index}: no do/wait/expect_events/screenshot")

    def describe(self) -> str:
        if self.label:
            return self.label
        k = self.kind
        r = self.raw
        if k == "do":
            args = {a: b for a, b in r.items() if a not in ("do", "label")}
            return f"do {r['do']} {json.dumps(args, default=str) if args else ''}".strip()
        if k == "wait":
            args = {a: b for a, b in r.items() if a not in ("wait", "label")}
            return f"wait {r['wait']} {json.dumps(args, default=str)}"
        if k == "expect_events":
            return f"expect_events {r['expect_events']}"
        return "screenshot" + (f" expect_screen={r['expect_screen']}" if r.get("expect_screen") else "")


@dataclass
class Scenario:
    name: str
    target: str
    steps: List[Step]
    settings: Dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_SETTINGS))
    path: Optional[Path] = None
    resources: Dict[str, Resource] = field(default_factory=dict)

    @staticmethod
    def parse(text: str, path: Optional[Path] = None, *, allow_empty: bool = False) -> "Scenario":
        if tomllib is None:
            raise ScenarioError("tomllib is not available; Python 3.11+ is required")
        try:
            doc = tomllib.loads(expand_semicolons(text))
        except tomllib.TOMLDecodeError as e:
            raise ScenarioError(f"{path or 'scenario'}: {e}") from e
        name, target, settings = normalize_header(doc, path)
        raw_steps = doc.get("step", [])
        if not isinstance(raw_steps, list) or any(not isinstance(s, dict) for s in raw_steps):
            raise ScenarioError(f"{name}: step must be an array of tables")
        if not raw_steps and not allow_empty:
            raise ScenarioError(f"{name}: no [[step]] entries")
        resources = normalize_resources(doc, raw_steps)
        steps = [Step(i + 1, dict(s), str(s.get("label", ""))) for i, s in enumerate(raw_steps)]
        for s in steps:
            s.kind  # validate
        return Scenario(name=name, target=target, steps=steps, settings=settings, path=path, resources=resources)

    @staticmethod
    def load(path: Path) -> "Scenario":
        return Scenario.parse(Path(path).read_text(), Path(path))


# ------------------------------------------------------------------ result --

@dataclass
class StepResult:
    index: int
    description: str
    status: str                      # ok | failed | skipped | expected_failure
    seconds: float
    detail: str = ""
    verdict: Optional[Dict[str, Any]] = None
    state: Optional[Dict[str, Any]] = None
    screen: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {"index": self.index, "step": self.description, "status": self.status,
             "seconds": round(self.seconds, 3), "detail": self.detail}
        if self.verdict:
            d["verdict"] = self.verdict
        if self.state:
            d["state"] = self.state
        if self.screen:
            d["screen"] = self.screen
        return d


@dataclass
class Report:
    scenario: str
    target: str
    build: str
    run_dir: str
    started: float
    steps: List[StepResult] = field(default_factory=list)
    finished: float = 0.0
    ok: bool = False
    verdict: Optional[Dict[str, Any]] = None
    error: str = ""
    execution: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"scenario": self.scenario, "target": self.target, "build": self.build,
                "run_dir": self.run_dir, "started": self.started, "finished": self.finished,
                "seconds": round(self.finished - self.started, 3) if self.finished else None,
                "ok": self.ok, "error": self.error, "verdict": self.verdict,
                "execution": self.execution,
                "steps": [s.to_dict() for s in self.steps]}

    def write(self, path: Path) -> Path:
        path.write_text(json.dumps(self.to_dict(), indent=1, default=str))
        return path


# ------------------------------------------------------------------ runner --

class _StepFailure(Exception):
    def __init__(self, detail: str, verdict: Optional[Verdict] = None, state: Optional[dict] = None):
        super().__init__(detail)
        self.detail = detail
        self.verdict = verdict
        self.state = state


class _StepSkipped(Exception):
    pass


# Nearest live hostile to the PC, for verbs that must fight through a
# blocked corridor: sets hd (distance, 999 when none) and hid (object id).
_NEAREST_HOSTILE_LUA = ('local hd,hid=999,0; local area=nwscript.call(\"GetArea\",pc); local c=nwscript.call(\"GetFirstObjectInArea\",area,1); while nwscript.call(\"GetIsObjectValid\",c)==1 do if nwscript.call(\"GetIsEnemy\",c,pc)==1 and nwscript.call(\"GetIsDead\",c)~=1 then local d=nwscript.call(\"GetDistanceBetween\",pc,c); if d<hd then hd,hid=d,c end end; c=nwscript.call(\"GetNextObjectInArea\",area,1) end; ')


class _DialogDriver:
    """Per-step memory for ScenarioRunner._drive_dialog.

    Holds the pick count, the retry gate and the skip ladder position for the
    entry that is currently stuck, so one poll of the helper can escalate
    (skip -> clear_sound_wait -> abort) exactly the way advance_dialog did
    before the logic was shared with clear_room.
    """

    def __init__(self, retry_interval: float = 1.0, grace: float = 10.0):
        self.picks = 0
        self.retry_interval = retry_interval
        # Seconds a node may sit before the ladder touches it. send_pending
        # (dialog.waiting_on_sound) covers a node's authored delay as well as
        # its VO: Endar's ambush cutscene walks six textless nodes on 2-6s
        # delays and completes by itself at 1x, and clearing one early ended
        # the chain before its faction scripts. A headless VO hang is
        # infinite, so waiting out the longest authored delay costs only
        # those seconds on a real hang.
        self.grace = grace
        self.next_retry = 0.0
        self.stuck_entry: Optional[int] = None
        self.stuck_since = 0.0
        self.skip_attempts = 0


class ScenarioRunner:
    """Executes a parsed scenario over a live channel.

    `session` is anything the Watchdog accepts as a probe plus `game_dir`,
    `save_dir`, `run_dir` and `build` attributes. The offline test passes a
    fake; the CLI passes a GameSession.
    """

    def __init__(self, scenario: Scenario, session: Any, channel: Channel, *,
                 log: Optional[Callable[[str], None]] = None,
                 checkpoints: Optional[Checkpoints] = None,
                 shooter: Optional[Shooter] = None,
                 watchdog: Optional[Watchdog] = None):
        self.sc = scenario
        self.session = session
        self.ch = channel
        self.log = log or print
        s = scenario.settings
        self.run_dir = Path(getattr(session, "run_dir"))
        self._awaited_entry: Optional[int] = None
        self.shooter = shooter
        if self.shooter is None and getattr(session, "game_dir", None):
            self.shooter = Shooter(channel, Path(session.game_dir), self.run_dir,
                                   interval=float(s["shot_interval"]), log=self.log)
        self.watchdog = watchdog or Watchdog(
            session, channel, hang_seconds=float(s["hang_seconds"]),
            load_seconds=float(s["load_seconds"]),
            load_tick_seconds=float(s["load_tick_seconds"]),
            stagnation_seconds=float(s["stagnation_seconds"]), log=self.log, shooter=self.shooter)
        self.checkpoints = checkpoints
        effective_target = getattr(getattr(session, "target", None), "name", scenario.target)
        if self.checkpoints is None and getattr(session, "save_dir", None):
            from . import targets as T
            self.checkpoints = Checkpoints(T.get(effective_target), Path(session.save_dir))
        self.mark_seq = 0
        self.report = Report(scenario=scenario.name, target=effective_target,
                             build=str(getattr(session, "build", "")),
                             run_dir=str(self.run_dir), started=time.time())

    # ----------------------------------------------------------- helpers --
    def sync_cursor(self) -> int:
        """Advance the cursor to the runtime's latest seq."""
        for _ in range(64):
            items = self.ch.events(since=self.ch.cursor, limit=500)
            if not items:
                break
        return self.ch.cursor

    def _timeout(self, step: Step, key: str = "default_timeout") -> float:
        return float(step.raw.get("timeout", self.sc.settings[key]))

    def _on_poll(self, state: dict) -> None:
        self._answer_authored_bark(state)
        if self.shooter is not None:
            self.shooter.maybe(state)

    def _answer_authored_bark(self, state: dict) -> bool:
        """Answer a declared tutorial bark that is blocking progress.

        These entries wait on the player forever, so anything queued behind one
        never completes. Only entries the route declared are answered, and never
        the entry a wait is currently targeting: a route that wants to read or
        choose a bark still sees it.
        """
        barks = self.sc.settings.get("authored_barks") or []
        if not barks:
            return False
        dialog = state.get("dialog")
        if not isinstance(dialog, dict) or dialog.get("active") is not True:
            return False
        entry = dialog.get("entry")
        if entry not in barks or entry == self._awaited_entry:
            return False
        if dialog.get("waiting_for_player") is not True:
            return False
        self.ch.request("reply", index=0)
        self.log(f"bark: answered authored entry {entry} with reply 0")
        return True

    def _wait(self, step: Step, pred: W.Predicate, what: str, progress: bool, timeout: float) -> dict:
        return W.wait_until(self.ch, pred, timeout, what=what, watchdog=self.watchdog,
                            progress=progress, on_poll=self._on_poll)

    def _configure_execution(self) -> None:
        """Apply scenario-wide execution policy before the first route step."""
        requested = float(self.sc.settings["game_speed"])
        self.report.execution["game_speed_requested"] = requested
        if requested == 1.0:
            # Every managed run starts a fresh process at retail speed.  The
            # explicit opt-out also works on builds without the speed binding.
            self.report.execution["game_speed_effective"] = 1.0
            self.log("execution: game speed 1x (retail-speed opt-out)")
            return
        result = self.ch.request("speed", scale=requested)
        if not isinstance(result, dict) or "scale" not in result:
            raise ScenarioError("speed command did not report its effective scale")
        effective = float(result["scale"])
        if not math.isclose(effective, requested, rel_tol=0.0, abs_tol=1e-6):
            raise ScenarioError(
                f"speed command reported {effective:g}x after {requested:g}x was requested")
        self.report.execution["game_speed_effective"] = effective
        self.log(f"execution: game speed {effective:g}x")

    # ------------------------------------------------------------- verbs --
    def _do(self, step: Step) -> str:
        r = step.raw
        verb = str(r["do"])
        # A load issues the engine's own sequence and returns; it does not wait
        # for the load to finish. It still gets the load budget rather than the
        # default reply timeout, because the reply comes back after several
        # engine calls and one archive extraction, which is not a 10s operation
        # on a cold cache.
        load_timeout = float(self.sc.settings["load_timeout"])
        if verb == "load_checkpoint":
            if self.checkpoints is None:
                raise _StepFailure("no checkpoint store for this session")
            folder = self.checkpoints.restore(str(r["name"]))
            self.ch.request("load_save", dir=folder, timeout=load_timeout)
            return f"load_save {folder!r} issued"
        if verb == "load_save":
            folder = self._resolve_save_dir(str(r["dir"]))
            self.ch.request("load_save", dir=folder, timeout=load_timeout)
            return f"load_save {folder!r} issued"
        if verb == "walk_dialog":
            return self._walk_dialog(step)
        if verb == "door_transaction":
            return self._door_transaction(step)
        if verb == "placeable_transaction":
            return self._placeable_transaction(step)
        if verb == "save":
            slot = int(r.get("slot", 1))
            name = str(r.get("name", "kpharness"))
            cp = r.get("checkpoint")
            if cp and self.checkpoints is not None:
                # A copied checkpoint is only meaningful at a fresh, complete,
                # idle gameplay boundary.  Two state reads make tick progress
                # an observed fact instead of accepting an old positive tick.
                before = self.ch.state()
                try:
                    world = World.observe_world(self.ch, timeout=min(self._timeout(step), 30.0))
                except World.WorldProbeError as e:
                    raise _StepFailure(f"checkpoint requires complete world: {e}") from e
                state = self.ch.state()
                if not World.stable_gameplay(state, world, before):
                    raise _StepFailure("checkpoint requires fresh stable gameplay (complete world, matching idle PC, tick progress, noncombat, no dialog)", state=state)
            t0 = time.time()
            self.ch.request("save", slot=slot, name=name)
            folder = f"{slot:06d} - {name}"
            save_dir = getattr(self.session, "save_dir", None)
            if self.checkpoints is not None:
                save_dir = self.checkpoints.save_dir
            if save_dir:
                # Save-complete: SAVEGAME.sav is the last artifact the engine
                # writes, and it is streamed -- the file exists with a fresh
                # mtime long before it is whole (a checkpoint copied on first
                # sight, then quit, left an 8 KB SAVEGAME.sav that loads as
                # "ERF member '' has unmapped restype 0xffff"). The predicate
                # is therefore the file no longer growing: same size on two
                # polls a second apart with an mtime at least a second old.
                deadline = time.monotonic() + self._timeout(step)
                sav = Path(save_dir) / folder / "SAVEGAME.sav"
                last_size = -1
                while time.monotonic() < deadline:
                    if sav.is_file():
                        st_ = sav.stat()
                        if (st_.st_mtime >= t0 - 1 and st_.st_size > 0
                                and st_.st_size == last_size and time.time() - st_.st_mtime >= 1.0):
                            break
                        last_size = st_.st_size
                    try:
                        st = self.ch.state()
                    except ChannelError:
                        # The engine blocks its main thread while it writes a
                        # large module save; the control channel answers
                        # again once the files are whole.
                        st = None
                    if st is not None:
                        v = self.watchdog.check(st)
                        if v is not None:
                            raise OracleTrip(v)
                    time.sleep(1.0)
                else:
                    raise _StepFailure(f"{sav} not written within the ceiling")
            if cp and self.checkpoints is not None:
                self.checkpoints.store(str(cp), folder, {"slot": slot})
                return f"saved {folder!r}, checkpoint {cp!r}"
            return f"save {folder!r} complete"
        if verb == "warp":
            self.ch.request("warp", module=str(r["module"]))
            return f"warp {r['module']} issued"
        if verb == "sleep":
            seconds = float(r.get("seconds", r.get("duration", 0)))
            if seconds < 0 or seconds > 300:
                raise _StepFailure("sleep: seconds must be between 0 and 300")
            time.sleep(seconds)
            return f"slept {seconds:g}s"
        if verb == "lua":
            result = self.ch.lua(str(r["code"]), timeout=float(r.get("timeout", 30)))
            return f"lua -> {json.dumps(result, default=str)[:200]}"
        if verb == "assert_lua":
            if "equals" not in r:
                raise ScenarioError(f"step {step.index}: assert_lua requires `equals`")
            expected = r["equals"]
            code = str(r["code"])
            # poll = true turns a one-shot assert into a state gate: retry the
            # postcondition until it holds or the ceiling expires, so a route
            # waits on an authored effect (a door unlocking) instead of guessing
            # a settle time. The watchdog still trips on a crash/hang mid-wait.
            poll = bool(r.get("poll", False))
            deadline = time.monotonic() + float(r.get("timeout", 30)) if poll else 0.0
            last = None
            while True:
                result = self.ch.lua(code, timeout=min(30.0, float(r.get("timeout", 30))))
                values = result.get("values") if isinstance(result, dict) else None
                if not isinstance(values, list) or len(values) != 1:
                    raise _StepFailure(
                        "assert_lua requires exactly one Lua return value, got " +
                        json.dumps(result, default=str), state=self.ch.last_state)
                actual = values[0]
                if type(actual) is type(expected) and actual == expected:
                    return "assert_lua == " + json.dumps(expected, default=str)
                last = actual
                if not poll or time.monotonic() >= deadline:
                    raise _StepFailure(
                        "assert_lua mismatch: expected " + json.dumps(expected, default=str) +
                        ", got " + json.dumps(last, default=str), state=self.ch.last_state)
                st = self.ch.state()
                v = self.watchdog.check(st)
                if v is not None:
                    raise OracleTrip(v)
                self._on_poll(st)
                time.sleep(0.3)
        if verb == "advance_dialog":
            return self._advance_dialog(step)
        if verb == "scripted_door_open":
            return self._scripted_door_open(step)
        if verb == "clear_room":
            return self._clear_room(step)
        if verb == "move_to":
            return self._move_to(step)
        if verb == "reply":
            return self._reply(step)
        if verb == "chargen_select_class":
            index = int(r["index"])
            self.ch.request(verb, index=index, timeout=float(r.get("timeout", self._timeout(step))))
            return f"chargen_select_class {index} ok"
        if verb == "set_party_leader":
            index = int(r["index"])
            self.ch.request(verb, index=index, timeout=float(r.get("timeout", self._timeout(step))))
            return f"set_party_leader {index} ok"
        if verb in ("door_security", "door_commit_open"):
            budget = float(r.get("timeout", self._timeout(step)))
            if "door" in r:
                door = int(r["door"])
            elif "tag" in r:
                door = self._door_by_tag(verb, str(r["tag"]), budget)
            else:
                raise ScenarioError(f"step {step.index}: {verb} requires `door` or `tag`")
            self.ch.request(verb, door=door, timeout=budget)
            return f"{verb} {door} ok"
        if verb in ("dialog_skip", "dialog_abort", "dialog_continue", "dialog_clear_sound_wait",
                    "clear_auto_pause", "reload", "new_game", "chargen_begin_play",
                    "unpause_timers", "dismiss_messagebox", "dismiss_container", "take_all_container",
                    "accept_party_selection", "auto_levelup"):
            # Fresh-game class selection constructs six character previews on
            # the game thread. Under llvmpipe that legitimately exceeds the
            # channel's ordinary 10-second request default, so scenario files
            # may give this engine operation its own bounded ceiling.
            self.ch.request(verb, timeout=float(r.get("timeout", self._timeout(step))))
            return f"{verb} ok"
        if verb == "equip_item":
            slot = int(r["slot"])
            tag = r.get("tag")
            item = r.get("item")
            if item is None:
                if not isinstance(tag, str) or not tag:
                    raise _StepFailure("equip_item requires an item id or a tag")
                # Resolve by tag from the PC's own inventory: object ids are not
                # stable route data, the tag on the authored template is.
                found = self.ch.lua(
                    "local pc=nwscript.call(\"GetFirstPC\"); local want=%s; "
                    "local it=nwscript.call(\"GetFirstItemInInventory\",pc); "
                    "while nwscript.call(\"GetIsObjectValid\",it)==1 do "
                    "if nwscript.call(\"GetTag\",it):gsub('%%z+$','')==want then return it end; "
                    "it=nwscript.call(\"GetNextItemInInventory\",pc) end; return 0"
                    % json.dumps(tag))
                values = found.get("values") if isinstance(found, dict) else None
                item = values[0] if isinstance(values, list) and values else 0
                if not isinstance(item, int) or item <= 0:
                    raise _StepFailure(f"equip_item: no inventory item tagged {tag!r}")
            self.ch.request(verb, item=int(item), slot=slot,
                            timeout=float(r.get("timeout", self._timeout(step))))
            return f"equip_item {tag or item} -> slot {slot}"
        if verb == "use_item":
            return self._use_item(step)
        if verb == "run_script":
            # Run an authored NCS with a named object as OBJECT_SELF -- the
            # way to fire a door's OnFailToOpen or a creature's handler when
            # the player-facing trigger (a click on a plot door) has no
            # headless equivalent. Postconditions belong to the next step.
            script = str(r["script"])
            tag = r.get("tag")
            if isinstance(tag, str) and tag:
                code = ("local o=nwscript.call(\"GetObjectByTag\",%s,0); if nwscript.call(\"GetIsObjectValid\",o)~=1 then "
                        "error('no object tagged '..%s) end; nwscript.call(\"ExecuteScript\",%s,o); return o"
                        % (json.dumps(tag), json.dumps(tag), json.dumps(script)))
            else:
                code = ("local pc=nwscript.call(\"GetFirstPC\"); nwscript.call(\"ExecuteScript\",%s,%s); return 1"
                        % (json.dumps(script), "nwscript.call(\"GetArea\",pc)" if r.get("area") else "pc"))
            self.ch.lua(code, timeout=float(r.get("timeout", self._timeout(step))))
            return f"run_script {script} on {tag or ('area' if r.get('area') else 'pc')}"
        if verb == "equipment_screen":
            visible = r["visible"]
            if not isinstance(visible, bool):
                raise _StepFailure("equipment_screen requires a boolean visible")
            budget = float(r.get("timeout", self._timeout(step)))
            # The engine will not run an in-game screen transition while a
            # conversation is up, and Endar's tutorial keeps starting them. Wait
            # for gameplay rather than firing into dialogue: declared barks are
            # answered, and automatic VO-gated nodes are skipped rather than sat
            # through. The transition itself is read back natively, which is why
            # nothing here asserts a modal the state never exposes.
            deadline = time.monotonic() + budget
            seen: Dict[str, Any] = {}
            # Only opening needs gameplay. Closing runs against the paused
            # screen the open transition just raised, which is not gameplay and
            # never will be until it is closed.
            while visible and time.monotonic() < deadline:
                state = self.ch.state()
                v = self.watchdog.check(state)
                if v is not None:
                    raise OracleTrip(v)
                dialog = state.get("dialog")
                seen = {"phase": state.get("phase"),
                        "entry": (dialog or {}).get("entry")}
                if state.get("phase") == "gameplay" and dialog is None:
                    break
                if (isinstance(dialog, dict) and dialog.get("active") is True
                        and dialog.get("waiting_for_player") is not True
                        and not self._answer_authored_bark(state)):
                    self.ch.request("dialog_skip")
                    continue
                self._on_poll(state)
                time.sleep(0.2)
            else:
                if visible:
                    raise _StepFailure(
                        f"equipment_screen visible={visible} never reached gameplay: {seen}",
                        state=self.ch.last_state)
            self.ch.request(verb, visible=visible, timeout=budget)
            return f"equipment_screen visible={visible}"
        if verb == "speed":
            self.ch.request("speed", scale=float(r.get("scale", 1.0)))
            return f"speed {r.get('scale', 1.0)}"
        if verb == "fixed_step":
            self.ch.request("fixed_step", hz=int(r.get("hz", 0)))
            return f"fixed_step {r.get('hz', 0)}"
        if verb == "movies":
            self.ch.request("movies", enabled=bool(r.get("enabled", False)))
            return f"movies {r.get('enabled', False)}"
        if verb == "set_global":
            name = str(r["name"])
            value = r.get("value", 1)
            kind = str(r.get("type", "boolean" if isinstance(value, bool) else "number"))
            if kind == "boolean":
                code = "nwscript.call(\"SetGlobalBoolean\",%r, %d)" % (name, 1 if value else 0)
            elif kind == "string":
                code = "nwscript.call(\"SetGlobalString\",%r, %r)" % (name, str(value))
            else:
                code = "nwscript.call(\"SetGlobalNumber\",%r, %d)" % (name, int(value))
            self.ch.lua(code)
            return code
        if verb == "quit":
            self.ch.quit()
            return "quit sent"
        raise ScenarioError(f"step {step.index}: unknown verb {verb!r}")

    def _placeable_transaction(self, step: Step) -> str:
        """Open one unopened corpus-addressed container through normal actions.

        This deliberately does not claim that every placeable use has the
        same result.  Consoles, dialog starters, and scripted terminals need
        their own measured result predicates before they become route verbs.
        """
        r = step.raw
        try:
            position = r["position"]
            object_type = int(r["type"])
            if object_type != 64:
                raise ValueError("placeable transaction requires source-declared type 64")
            interaction_range = float(r["interaction_range"])
            if not math.isfinite(interaction_range) or interaction_range <= 0:
                raise ValueError("interaction_range must be a positive finite number")
            pre_open = r["pre_open"]
            if not isinstance(pre_open, bool):
                raise ValueError("pre_open must be a boolean")
            if pre_open:
                raise ValueError("placeable transaction currently supports only unopened containers")
            tolerance = float(r.get("position_tolerance", 0.25))
            target = World.select_route_object(
                World.observe_world(self.ch, timeout=min(self._timeout(step), 30.0)),
                module=str(r["module"]), tag=str(r["tag"]), object_type=object_type,
                position=position, tolerance=tolerance,
                occurrence=(int(r["occurrence"]) if "occurrence" in r else None))
        except (KeyError, TypeError, ValueError, World.WorldProbeError) as e:
            raise _StepFailure(f"placeable target resolution failed: {e}") from e

        if target.get("open") is not pre_open:
            raise _StepFailure(f"placeable pre-open state mismatch: expected {pre_open!r}, got {target.get('open')!r}")
        target_id = int(target["id"])
        tag = json.dumps(str(r["tag"]).rstrip("\0"))
        pre_open_lua = "true" if pre_open else "false"
        occurrence = int(r["occurrence"]) if "occurrence" in r else None
        deadline = time.monotonic() + self._timeout(step)
        last_world: Optional[Dict[str, Any]] = None

        def remaining(what: str) -> float:
            value = deadline - time.monotonic()
            if value <= 0:
                raise _StepFailure(f"placeable transaction budget expired before {what}", state=self.ch.last_state)
            return min(30.0, value)

        def observe(phase: str) -> tuple[dict, Dict[str, Any], Dict[str, Any]]:
            """Read one complete world and prove the selected instance persists."""
            nonlocal last_world
            state = self.ch.state()
            verdict = self.watchdog.check(state)
            if verdict is not None:
                raise OracleTrip(verdict)
            try:
                current = World.observe_world(self.ch, timeout=min(10.0, remaining(f"{phase} observation")))
                current_target = World.revalidate_route_object(
                    current, target, module=str(r["module"]), tag=str(r["tag"]),
                    object_type=64, position=position, tolerance=tolerance,
                    occurrence=occurrence)
            except World.WorldProbeError as e:
                raise _StepFailure(f"placeable target identity changed during {phase}: {e}", state=state) from e
            last_world = current
            return state, current, current_target

        def cheap_poll(what: str) -> Dict[str, Any]:
            """One state read: phase, dialog and PC position, no world probe.

            A full probe costs seconds on a live process, so polling with it
            spends the entire budget observing instead of acting.
            """
            state = self.ch.state()
            verdict = self.watchdog.check(state)
            if verdict is not None:
                raise OracleTrip(verdict)
            return state

        # Movement and use must be separate engine drains.  A combined closure
        # can evaluate ActionInteractObject before ActionMoveToObject reaches
        # its range, leaving both actions ineffective on the real K1 queue.
        move_lua = ("local pc=nwscript.call(\"GetFirstPC\"); local placeable=%d; "
                    "if nwscript.call(\"GetIsObjectValid\",placeable)~=1 then error('placeable vanished') end; "
                    "if nwscript.call(\"GetTag\",placeable):gsub('%%z+$','')~=%s or nwscript.call(\"GetObjectType\",placeable)~=64 then error('placeable identity changed') end; "
                    "local p=nwscript.call(\"GetPosition\",placeable); if math.sqrt((p.x-(%.9g))^2+(p.y-(%.9g))^2+(p.z-(%.9g))^2)>%.9g then error('placeable position changed') end; "
                    "if (nwscript.call(\"GetIsOpen\",placeable)==1)~=%s then error('placeable pre-open state changed') end; "
                    "nwscript.with_caller(pc,function() nwscript.call(\"ActionMoveToObject\",placeable,1,%.9g) end)"
                    % (target_id, tag, float(position[0]), float(position[1]), float(position[2]),
                       tolerance, pre_open_lua, interaction_range))
        # Queueing the move is idempotent: re-issuing it when the PC already
        # stands in range is a no-op the engine discards, so a bark that clears
        # the action queue costs one requeue rather than a failed step.
        self.ch.lua(move_lua, timeout=remaining("movement action"))

        reached_range = False
        while time.monotonic() < deadline:
            state = cheap_poll("move")
            if self._answer_authored_bark(state):
                self.ch.lua(move_lua, timeout=remaining("movement action"))
                continue
            if state.get("phase") == "gameplay" and state.get("dialog") is None:
                state, current, current_target = observe("move")
                if current_target.get("open") is not pre_open:
                    raise _StepFailure("placeable pre-open state changed while moving", state=state)
                normal = (state.get("phase") == "gameplay" and state.get("dialog") is None
                          and current["pc"].get("current_action") in World.IDLE_ACTIONS
                          and current["pc"].get("in_combat") is False)
                if World.within_object_distance(current, current_target, interaction_range) and normal:
                    reached_range = True
                    break
            self._on_poll(state)
            time.sleep(0.2)
        if not reached_range:
            suffix = "no complete world observation" if last_world is None else json.dumps(
                {"pc": last_world.get("pc"), "module": last_world.get("module")}, default=str)
            raise _StepFailure(
                f"placeable move did not reach interaction range {interaction_range:g} with idle/noncombat gameplay: {suffix}",
                state=self.ch.last_state)

        # Revalidate again in the engine immediately before use.  The observed
        # range proves when interaction may be issued; this prevents an ID
        # reuse between that observation and the queued ActionInteractObject.
        interact_lua = ("local pc=nwscript.call(\"GetFirstPC\"); local placeable=%d; "
                        "if nwscript.call(\"GetIsObjectValid\",placeable)~=1 then error('placeable vanished') end; "
                        "if nwscript.call(\"GetTag\",placeable):gsub('%%z+$','')~=%s or nwscript.call(\"GetObjectType\",placeable)~=64 then error('placeable identity changed') end; "
                        "local p=nwscript.call(\"GetPosition\",placeable); if math.sqrt((p.x-(%.9g))^2+(p.y-(%.9g))^2+(p.z-(%.9g))^2)>%.9g then error('placeable position changed') end; "
                        "if (nwscript.call(\"GetIsOpen\",placeable)==1)~=%s then error('placeable pre-open state changed') end; "
                        "if nwscript.call(\"GetIsInCombat\",pc)~=0 then error('PC entered combat before placeable interaction') end; "
                        "if nwscript.call(\"GetCurrentAction\",pc)~=0 and nwscript.call(\"GetCurrentAction\",pc)~=65534 then error('PC is not idle before placeable interaction') end; "
                        "if nwscript.call(\"GetDistanceBetween2D\",pc,placeable)>%.9g then error('PC left declared interaction range') end; "
                        "nwscript.with_caller(pc,function() nwscript.call(\"ActionInteractObject\",placeable) end)"
                        % (target_id, tag, float(position[0]), float(position[1]), float(position[2]),
                           tolerance, pre_open_lua, interaction_range))
        self.ch.lua(interact_lua, timeout=remaining("interaction action"))

        interact_queued = True
        while time.monotonic() < deadline:
            state = cheap_poll("interaction")
            if self._answer_authored_bark(state):
                # The conversation discarded the queued interaction with the
                # rest of the action queue; it has to be asked for again.
                interact_queued = False
                continue
            state, current, current_target = observe("interaction")
            if (current_target.get("open") is True
                    and World.within_object_distance(current, current_target, interaction_range)):
                # Opening a container raises its own GUI, so the engine reports a
                # paused modal rather than idle gameplay. That is the expected
                # consequence of the interaction, not a reason to keep waiting:
                # the open readback and the range check are the postcondition.
                if World.stable_gameplay(state, current):
                    return (f"placeable id={target_id} open; PC within declared interaction range "
                            f"{interaction_range:g}; gameplay idle/noncombat/no-dialog")
                detail = state.get("phase_detail") or {}
                if (state.get("phase") == "paused" and state.get("dialog") is None
                        and int(detail.get("modal_count") or 0) >= 1
                        and current["pc"].get("in_combat") is False):
                    return (f"placeable id={target_id} open; PC within declared interaction range "
                            f"{interaction_range:g}; container GUI modal raised, noncombat/no-dialog")
            if not interact_queued:
                self.ch.lua(interact_lua, timeout=remaining("interaction action"))
                interact_queued = True
            self._on_poll(state)
            time.sleep(0.2)
        suffix = "no complete world observation" if last_world is None else json.dumps(
            {"pc": last_world.get("pc"), "module": last_world.get("module")}, default=str)
        raise _StepFailure(f"placeable interaction did not reach open/range/stable state: {suffix}",
                           state=self.ch.last_state)

    def _door_transaction(self, step: Step) -> str:
        """Move to one corpus-addressed door, open it, and prove the result.

        This intentionally uses the ordinary action queue.  It neither writes
        door state nor treats a queued ActionOpenDoor as a successful use.
        """
        r = step.raw
        if r.get("available") is False:
            raise _StepFailure("door transaction unavailable: " + str(r.get("unavailable_reason", "no resource-backed far-side destination")))
        try:
            position = r["position"]
            destination = r["destination"]
            if len(destination) != 3:
                raise ValueError("destination must contain three coordinates")
            self._verify_walkmesh_route(r, position, destination)
            target = World.select_route_object(
                World.observe_world(self.ch, timeout=min(self._timeout(step), 30.0)),
                module=str(r["module"]), tag=str(r["tag"]), object_type=int(r.get("type", 8)),
                position=position, tolerance=float(r.get("position_tolerance", 0.25)),
                occurrence=(int(r["occurrence"]) if "occurrence" in r else None))
            # Facing is deliberately a second, bounded probe: the initial
            # snapshot resolves the one live door id, and only that door gets
            # an engine GetFacing call.  Static WOK geometry never supplies
            # its orientation.
            target_id = int(target["id"])
            facing_world = World.observe_world(
                self.ch, facing_ids=(target_id,), timeout=min(self._timeout(step), 30.0))
            target = World.select_route_object(
                facing_world, module=str(r["module"]), tag=str(r["tag"]),
                object_type=int(r.get("type", 8)), position=position,
                tolerance=float(r.get("position_tolerance", 0.25)),
                occurrence=(int(r["occurrence"]) if "occurrence" in r else None))
            if int(target["id"]) != target_id:
                raise World.WorldProbeError("resolved door id changed before facing observation")
            # Odyssey's GetFacing reports degrees (the live first Endar door
            # reports ~180).  Python trigonometry is radians; converting here
            # keeps the engine-facing unit explicit at the sole geometry
            # boundary instead of baking a model-axis assumption into routes.
            facing_degrees = float(target["facing"])
            facing = math.radians(facing_degrees)
            # Odyssey's world plane uses +Y for heading zero after its screen
            # yaw convention is accounted for: (sin(yaw), -cos(yaw)).
            normal = (math.sin(facing), -math.cos(facing))
            approach, far = r["walkmesh_approach_centroid"], r["walkmesh_far_centroid"]
            if len(approach) != 3 or len(far) != 3:
                raise ValueError("walkmesh centroids must contain three coordinates")
            min_projection = float(r.get("walkmesh_min_projection", 0.5))
            if not math.isfinite(min_projection) or min_projection <= 0:
                raise ValueError("walkmesh minimum projection must be positive and finite")
            project = lambda p: ((float(p[0]) - float(position[0])) * normal[0]
                                 + (float(p[1]) - float(position[1])) * normal[1])
            near_projection, far_projection = project(approach), project(far)
            if (not all(math.isfinite(v) for v in (*approach, *far, near_projection, far_projection))
                    or near_projection > -min_projection or far_projection < min_projection):
                raise World.WorldProbeError(
                    "live door facing does not separate WOK approach/far centroids")
        except (KeyError, TypeError, ValueError, World.WorldProbeError) as e:
            raise _StepFailure(f"door target resolution failed: {e}") from e
        if target.get("locked") is not False:
            raise _StepFailure(f"door target is locked before ordinary open: {target.get('locked')!r}")
        target_id = int(target["id"])
        x, y, z = (float(v) for v in destination)
        tolerance = float(r.get("position_tolerance", 0.25))
        tag = json.dumps(str(r["tag"]).rstrip("\0"))
        # Revalidate the resolved identity, type and authored placement just
        # before queueing.  An object-id reuse must never operate a new object.
        open_lua = ("local pc=nwscript.call(\"GetFirstPC\"); local door=%d; "
                    "if nwscript.call(\"GetIsObjectValid\",door)~=1 then error('door vanished') end; "
                    "if nwscript.call(\"GetTag\",door):gsub('%%z+$','')~=%s or nwscript.call(\"GetObjectType\",door)~=%d then error('door identity changed') end; "
                    # Parenthesize authored coordinates: a negative Z must
                    # not serialize as `p.z--1.3`, which Lua treats as a line
                    # comment and therefore reports as an EOF syntax error.
                    "local p=nwscript.call(\"GetPosition\",door); if math.sqrt((p.x-(%.9g))^2+(p.y-(%.9g))^2+(p.z-(%.9g))^2)>%.9g then error('door position changed') end; "
                    "nwscript.with_caller(pc,function() nwscript.call(\"ActionMoveToObject\",door,1,0.75); nwscript.call(\"ActionOpenDoor\",door) end)"
                    % (target_id, tag, int(r.get("type", 8)), float(position[0]), float(position[1]), float(position[2]), tolerance))
        self.ch.lua(open_lua, timeout=min(self._timeout(step), 30.0))
        deadline = time.monotonic() + self._timeout(step)
        last_world: Optional[Dict[str, Any]] = None
        moved = False
        destination_tolerance = float(r.get("destination_tolerance", 0.75))
        while time.monotonic() < deadline:
            state = self.ch.state()
            verdict = self.watchdog.check(state)
            if verdict is not None:
                raise OracleTrip(verdict)
            try:
                current = World.observe_world(self.ch, timeout=min(10.0, max(1.0, deadline - time.monotonic())))
            except World.WorldProbeError:
                current = None
            if current is not None:
                last_world = current
                # Object ids can be recycled during an area update.  Every
                # post-queue observation must prove that this is still the
                # selected authored instance before its door state can drive
                # another action or count as completion evidence.
                try:
                    current_target = World.revalidate_route_object(
                        current, target, module=str(r["module"]), tag=str(r["tag"]),
                        object_type=int(r.get("type", 8)), position=position,
                        tolerance=tolerance,
                        occurrence=(int(r["occurrence"]) if "occurrence" in r else None))
                except World.WorldProbeError as e:
                    raise _StepFailure(f"door target identity changed after action queue: {e}") from e
                if not moved and World.door_open_unlocked(current, current_target):
                    # Only an observed open selected instance may authorize the
                    # far-side ordinary movement action.
                    self.ch.lua("local pc=nwscript.call(\"GetFirstPC\"); local where=nwscript.call(\"Location\",{x=%.9g,y=%.9g,z=%.9g},0); nwscript.with_caller(pc,function() nwscript.call(\"ActionMoveToLocation\",where,1) end)" % (x, y, z),
                                timeout=min(10.0, max(1.0, deadline - time.monotonic())))
                    moved = True
                pc = current.get("pc", {}).get("position", {})
                at_destination = all(isinstance(pc.get(axis), (int, float))
                                     and abs(float(pc[axis]) - wanted) <= destination_tolerance
                                     for axis, wanted in zip("xyz", (x, y, z)))
                if (moved and World.door_open_unlocked(current, current_target) and at_destination
                        and World.stable_gameplay(state, current)):
                    return (f"door id={target_id} open/unlocked; PC at resource-backed far side "
                            f"({x:g},{y:g},{z:g}) within {destination_tolerance:g}; gameplay idle/noncombat/no-dialog")
            self._on_poll(state)
            time.sleep(0.2)
        suffix = "no complete world observation" if last_world is None else json.dumps(
            {"pc": last_world.get("pc"), "module": last_world.get("module")}, default=str)
        raise _StepFailure(f"door transaction did not reach open/far-side/stable state: {suffix}",
                           state=self.ch.last_state)

    def _verify_walkmesh_route(self, r: Dict[str, Any], position: Any, destination: Any) -> None:
        """Verify the bytes that authorize a far-side action, before queueing it."""
        declaration = self.sc.resources[r["resource"]]
        resource = declaration.source
        expected_hash = declaration.sha256
        expected_size = declaration.size
        materialized = Path(declaration.file)
        if not materialized.is_absolute():
            materialized = Path(self.session.game_dir) / materialized
        try:
            data = materialized.read_bytes()
        except OSError as e:
            raise ValueError(f"walkmesh resource {resource!r} is not materialized at {materialized}: {e}") from e
        if len(data) != expected_size:
            raise ValueError(f"walkmesh resource {resource!r} size mismatch")
        if hashlib.sha256(data).hexdigest() != expected_hash:
            raise ValueError(f"walkmesh resource {resource!r} SHA-256 mismatch")
        mesh = Bwm.parse(data)
        path = [int(face) for face in r["walkmesh_path"]]
        approach_face, far_face = int(r["walkmesh_approach_face"]), int(r["walkmesh_face"])
        if not path or path[0] != approach_face or path[-1] != far_face:
            raise ValueError("walkmesh path endpoints do not match declared faces")
        if any(face < 0 or face >= mesh.walkable_count for face in path):
            raise ValueError("walkmesh path names a non-walkable face")
        graph = Bwm._graph(mesh)
        if any(right not in graph[left] for left, right in zip(path, path[1:])):
            raise ValueError("walkmesh path has no shared-edge connection")
        def centroid(face: int) -> tuple[float, float, float]:
            return mesh.faces[face].centroid
        def same(actual: Any, expected: Any) -> bool:
            return (isinstance(expected, (list, tuple)) and len(expected) == 3
                    and all(isinstance(x, (int, float)) and math.isfinite(x)
                            and abs(float(x) - y) <= 1e-5 for x, y in zip(expected, actual)))
        if not same(centroid(approach_face), r["walkmesh_approach_centroid"]):
            raise ValueError("walkmesh approach centroid mismatch")
        if not same(centroid(far_face), r["walkmesh_far_centroid"]):
            raise ValueError("walkmesh far centroid mismatch")
        if not same(centroid(far_face), destination):
            raise ValueError("destination is not the verified walkmesh far centroid")

    def _resolve_save_dir(self, pattern: str) -> str:
        """A save folder name, or a glob over the save dir (K2 cloud saves
        are named by the store, so the scenario says `*autosave*`)."""
        if "*" not in pattern and "?" not in pattern:
            return pattern
        if self.checkpoints is None:
            raise _StepFailure(f"cannot resolve {pattern!r}: no save dir for this session")
        names = sorted(p.name for p in self.checkpoints.save_dir.iterdir() if p.is_dir())
        for n in names:
            if fnmatch.fnmatch(n.lower(), pattern.lower()):
                return n
        raise _StepFailure(f"no save folder matches {pattern!r} in {self.checkpoints.save_dir}")

    def _walk_dialog(self, step: Step) -> str:
        """Every reply of the first node of one conversation, rolled back
        between picks through a checkpoint.

        Parameters: checkpoint (name) or save (folder), start (Lua that
        starts the conversation), max_replies (default 9), timeout per wait.
        Each pick waits until the node changes or the conversation ends and
        records the reply text and where it led.
        """
        r = step.raw
        start = str(r["start"])
        max_replies = int(r.get("max_replies", 9))
        timeout = self._timeout(step)
        load_timeout = float(r.get("load_timeout", self.sc.settings["load_timeout"]))
        walked: List[str] = []

        def reload() -> None:
            if r.get("checkpoint"):
                assert self.checkpoints is not None
                folder = self.checkpoints.restore(str(r["checkpoint"]))
            else:
                folder = self._resolve_save_dir(str(r["save"]))
            self.ch.request("load_save", dir=folder, timeout=load_timeout)
            self._wait(step, W.phase_is("gameplay"), "gameplay after rollback", False, load_timeout)

        def open_dialog() -> dict:
            self.ch.lua(start)
            self._wait(step, W.phase_is("dialog"), "dialog phase", False, timeout)
            self._wait(step, W.dialog_waiting(), "a reply list", False, timeout)
            return self.ch.request("dialog") or {}

        d = open_dialog()
        replies = [x for x in (d.get("replies") or []) if isinstance(x, dict)]
        active = [x for x in replies if x.get("active", True)][:max_replies]
        if not active:
            raise _StepFailure("the first node offers no active reply", state=self.ch.last_state)
        for n, rep in enumerate(active):
            if n > 0:
                reload()
                d = open_dialog()
                replies = [x for x in (d.get("replies") or []) if isinstance(x, dict)]
                active_now = [x for x in replies if x.get("active", True)]
                if n >= len(active_now):
                    walked.append(f"#{n}: gone after rollback")
                    continue
                rep = active_now[n]
            idx = int(rep.get("index", n))
            before = (d.get("entry"), d.get("reply"))
            self.ch.request("reply", index=idx)

            def moved(state: Dict[str, Any], _: Channel) -> bool:
                if state.get("phase") != "dialog":
                    return True
                dd = state.get("dialog") or {}
                return (dd.get("entry"), dd.get("reply")) != before
            st = self._wait(step, moved, f"node change after reply {idx}", False, timeout)
            after = st.get("dialog") or {}
            walked.append(f"#{idx} {str(rep.get('text', ''))[:40]!r} -> "
                          f"{'ended' if st.get('phase') != 'dialog' else 'entry ' + str(after.get('entry'))}")
            self.log(f"  walk: {walked[-1]}")
            if st.get("phase") == "dialog":
                try:
                    self.ch.request("dialog_abort")
                except ChannelError:
                    pass
        return f"walked {len(walked)} replies: " + "; ".join(walked)

    def _use_item(self, step: Step) -> str:
        """Use one inventory item on the PC, gated on the hit-point readback.

        ``tag`` names the item (resolved from the PC's inventory the way
        equip_item does) or ``item`` gives an object id. ``if_hp_below`` (a
        fraction of max hp) makes the step idempotent: at or above it the
        step is a no-op, so a route can say "heal if hurt" between fights.
        The native use_item transaction with no target acts on the PC; a
        target id is refused for the player's own reserved object id.
        """
        r = step.raw
        tag = r.get("tag")
        item = r.get("item")
        threshold = r.get("if_hp_below")
        budget = float(r.get("timeout", self._timeout(step)))
        probe = "local pc=nwscript.call(\"GetFirstPC\"); return {hp=nwscript.call(\"GetCurrentHitPoints\",pc), max=nwscript.call(\"GetMaxHitPoints\",pc)}"
        before = (self.ch.lua(probe, timeout=min(30.0, budget)).get("values") or [{}])[0]
        hp0, mx = int(before.get("hp", 0)), int(before.get("max", 0)) or 1
        if threshold is not None and hp0 >= float(threshold) * mx:
            return f"use_item skipped: hp {hp0}/{mx} is not below {float(threshold):g}"
        if item is None:
            if not isinstance(tag, str) or not tag:
                raise _StepFailure("use_item requires an item id or a tag")
            found = self.ch.lua(
                "local pc=nwscript.call(\"GetFirstPC\"); local want=%s; "
                "local it=nwscript.call(\"GetFirstItemInInventory\",pc); "
                "while nwscript.call(\"GetIsObjectValid\",it)==1 do "
                "if nwscript.call(\"GetTag\",it):gsub('%%z+$','')==want then return it end; "
                "it=nwscript.call(\"GetNextItemInInventory\",pc) end; return 0"
                % json.dumps(tag), timeout=min(30.0, budget))
            values = found.get("values") if isinstance(found, dict) else None
            item = values[0] if isinstance(values, list) and values else 0
            if not isinstance(item, int) or item <= 0:
                raise _StepFailure(f"use_item: no inventory item tagged {tag!r}")
        self.ch.request("use_item", item=int(item), timeout=budget)
        deadline = time.monotonic() + budget
        while time.monotonic() < deadline:
            state = self.ch.state()
            v = self.watchdog.check(state)
            if v is not None:
                raise OracleTrip(v)
            now = (self.ch.lua(probe, timeout=min(30.0, max(1.0, deadline - time.monotonic()))).get("values") or [{}])[0]
            hp1 = int(now.get("hp", 0))
            if hp1 > hp0 or hp1 >= mx:
                return f"use_item {tag or item}: hp {hp0} -> {hp1}/{mx}"
            self._on_poll(state)
            time.sleep(0.3)
        raise _StepFailure(f"use_item {tag or item}: hp stayed {hp0}/{mx}", state=self.ch.last_state)

    def _door_by_tag(self, verb: str, tag: str, budget: float) -> int:
        # Resolve by tag at execution time, not a raw id: an object id is
        # per-run, so a route must never pin one across replays.
        found = self.ch.lua(
            "local d=nwscript.call(\"GetObjectByTag\",%s,0); if nwscript.call(\"GetIsObjectValid\",d)~=1 then "
            "error('door tag not found') end; return d" % json.dumps(tag),
            timeout=min(30.0, budget))
        values = found.get("values") if isinstance(found, dict) else None
        if not isinstance(values, list) or not values or not isinstance(values[0], int):
            raise _StepFailure(f"{verb}: no live door tagged {tag!r}")
        return values[0]

    # How long a self-commanded ActionOpenDoor gets to reach GetIsOpen on its
    # own before the second phase is committed by hand (see below).
    _DOOR_COMMIT_AFTER = 2.5

    def _scripted_door_open(self, step: Step) -> str:
        """Open one authored scripted-only door, the way its own script does.

        Endar's doors that gate story progression (end_door01, end_door02, ...)
        have no working player-facing unlock: door_security refuses them
        (engine door.lockable is false) and a character-assigned ActionOpenDoor
        does nothing. Their own OnFailToOpen/escort scripts open them with
        AssignCommand(oDoor, ActionOpenDoor(oDoor)) -- the door commanding
        itself -- confirmed by decompiling k_pend_traskdl40 (end_door01) and
        proven live for end_door02. This replicates exactly that authored
        pattern rather than a character interacting with the door, and needs
        no party member proximity or pathing.

        Opening is two-phase in the engine. The self-command runs
        CSWSDoor::OpenDoor -> SetOpenState, which writes only the pending
        also_open_state and the opening animation. The committed open_state
        (what GetIsOpen and the walkmesh read) is written by
        CSWSDoor::MoveToNextOpenState, normally from the client's
        model-animation-done callback -- which the headless client never
        delivers for some doors (seen live on end_door04/end_door05). A door
        stuck there stays GetIsOpen==0 forever and every later open is a no-op,
        so if GetIsOpen is still 0 about ``_DOOR_COMMIT_AFTER`` seconds after
        the self-command this issues ``door_commit_open`` once, which runs
        that second phase on the door, and keeps polling.
        """
        r = step.raw
        tag = str(r["tag"])
        budget = float(r.get("timeout", self._timeout(step)))
        found = self.ch.lua(
            "local d=nwscript.call(\"GetObjectByTag\",%s,0); if nwscript.call(\"GetIsObjectValid\",d)~=1 then "
            "error('door tag not found') end; nwscript.with_caller(d,function() nwscript.call(\"ActionOpenDoor\",d) end); return d"
            % json.dumps(tag), timeout=min(30.0, budget))
        values = found.get("values") if isinstance(found, dict) else None
        if not isinstance(values, list) or not values:
            raise _StepFailure(f"scripted_door_open: no live door tagged {tag!r}")
        issued = time.monotonic()
        deadline = issued + budget
        committed = False
        while time.monotonic() < deadline:
            check = self.ch.lua(
                "local d=nwscript.call(\"GetObjectByTag\",%s,0); return nwscript.call(\"GetIsObjectValid\",d)==1 and nwscript.call(\"GetIsOpen\",d)==1"
                % json.dumps(tag), timeout=min(30.0, deadline - time.monotonic()))
            check_values = check.get("values") if isinstance(check, dict) else None
            if isinstance(check_values, list) and check_values and check_values[0] is True:
                return f"scripted_door_open {tag} open" + (" (committed)" if committed else "")
            if not committed and time.monotonic() - issued >= self._DOOR_COMMIT_AFTER:
                committed = True
                door = values[0] if isinstance(values[0], int) else self._door_by_tag(
                    "scripted_door_open", tag, max(1.0, deadline - time.monotonic()))
                self.ch.request("door_commit_open", door=door,
                                timeout=max(1.0, min(30.0, deadline - time.monotonic())))
            state = self.ch.state()
            v = self.watchdog.check(state)
            if v is not None:
                raise OracleTrip(v)
            self._on_poll(state)
            time.sleep(0.3)
        raise _StepFailure(f"scripted_door_open {tag} did not reach open within the ceiling",
                          state=self.ch.last_state)

    def _advance_dialog(self, step: Step) -> str:
        """Auto-advance an authored dialog chain to a target phase.

        Endar's tutorial auto-forwards through single-reply nodes whose exact
        entry index races the harness (44 may already be 45 by the time a wait
        fires). Rather than pin each entry, pick the first active reply on every
        waiting node -- answering declared barks as they appear -- until the
        conversation leaves dialog for the requested phase. This is the
        determinism the state-gated model wants: it depends on the observed
        phase boundary, not on catching a specific transient entry.

        An active node that is not waiting for the player (an auto/VO node) can
        hang indefinitely in a headless/muted environment on
        ``dialog.waiting_on_sound`` -- there is no real audio device to signal
        playback completion. ``dialog_skip`` is the harness's Escape-key
        equivalent (native CServerExoApp::SkipPastDialog, honoured when the DLG
        is Skippable, which Endar's are); send it whenever a node is active but
        not player-waiting, so the chain never stalls on unplayed VO.

        A tutorial popup (``phase_detail.tutorial == 1`` with a modal and no
        dialog) is a separate kind of stall a scripted cutscene can leave up;
        ``dismiss_messagebox`` clears it the way acknowledging the popup would.

        A textless node (``text == "strref:-1"``) stuck on ``waiting_on_sound``
        that ``dialog_skip`` does not clear within a few attempts is not
        Skippable (the flag ``dialog_skip`` requires); escalate to
        ``dialog_clear_sound_wait``, which clears the transient send_pending
        flag (CSWSObject+0x48) to simulate sound playback completing. Unlike
        forcing CSWSDialog::Skippable, this writes a runtime field that is
        never serialized to saves, so the dialog advances naturally through
        its remaining nodes with all scripted effects intact. Only if that
        also fails does the chain reach ``dialog_abort``.
        """
        r = step.raw
        until = str(r.get("until", "gameplay"))
        # ``hold``: keep driving for this long after the phase is first seen,
        # restarting whenever a dialog or modal appears, so a cutscene that
        # opens a beat after its trigger (door19's OnOpen) is not mistaken
        # for the gameplay it briefly flashes through.
        hold = float(r.get("hold", 0.0))
        deadline = time.monotonic() + self._timeout(step)
        drv = _DialogDriver(grace=float(self.sc.settings.get("dialog_grace", 10.0)))
        reached_at: Optional[float] = None
        while time.monotonic() < deadline:
            state = self.ch.state()
            v = self.watchdog.check(state)
            if v is not None:
                raise OracleTrip(v)
            detail = state.get("phase_detail") or {}
            if detail.get("pause") and state.get("dialog") is None:
                self.ch.request("clear_auto_pause")
            if state.get("phase") == until:
                now = time.monotonic()
                if hold <= 0:
                    return f"advance_dialog reached {until!r} after {drv.picks} picks"
                if reached_at is None:
                    reached_at = now
                elif now - reached_at >= hold:
                    return f"advance_dialog reached {until!r} after {drv.picks} picks (held {hold:g}s)"
            else:
                reached_at = None
            if self._drive_dialog(state, drv):
                continue
            self._on_poll(state)
            time.sleep(0.3)
        raise _StepFailure(
            f"advance_dialog did not reach {until!r} within the ceiling (picks={drv.picks})",
            state=self.ch.last_state)

    def _dialog_request(self, cmd: str, **args: Any) -> bool:
        """One dialog-driving request that must not abort the calling verb.

        While a conversation is still initializing the engine can refuse the
        request (e.g. "dialog_skip: dialog owner has no game object"); the
        next poll sees fresh state and the stuck-entry timer keeps running, so
        the ladder still escalates. Returns whether the engine accepted it.
        """
        try:
            self.ch.request(cmd, **args)
            return True
        except ChannelError as e:
            self.log(f"dialog: {cmd} refused, keep polling: {e}")
            return False

    def _drive_dialog(self, state: dict, drv: _DialogDriver) -> bool:
        """One poll of the dialog/tutorial ladder shared by advance_dialog and clear_room.

        Returns True when a reply was picked (a declared bark or the first
        active reply), meaning the caller should re-read state at once. Skip
        escalation and tutorial dismissal return False: they are rate-limited
        by ``drv.retry_interval`` and the caller polls normally.
        """
        if self._answer_authored_bark(state):
            drv.picks += 1
            return True
        dialog = state.get("dialog")
        if isinstance(dialog, dict) and dialog.get("active") is True:
            entry = dialog.get("entry")
            if entry != drv.stuck_entry:
                drv.stuck_entry, drv.stuck_since, drv.skip_attempts = entry, time.monotonic(), 0
            if dialog.get("waiting_for_player") is True:
                replies = dialog.get("replies") or []
                chosen = next((rep for rep in replies
                               if isinstance(rep, dict) and rep.get("active", True)), None)
                if chosen is not None:
                    if self._dialog_request("reply", index=int(chosen.get("index", 0))):
                        drv.picks += 1
                        return True
            elif time.monotonic() >= drv.next_retry:
                # Gentlest first: clearing the VO wait lets the node end the
                # way finished playback would, so every later node and its
                # scripts still run. dialog_skip on a Skippable cinematic is
                # the Escape key -- it ends the whole conversation and drops
                # the node scripts after the current one (end_cut04 lost its
                # reinforcement spawn and party-AI restart that way), so it
                # is only the second rung; abort is the last.
                stuck = time.monotonic() - drv.stuck_since
                if stuck < drv.grace:
                    pass
                elif drv.skip_attempts >= 5 and stuck >= 12.0:
                    if self._dialog_request("dialog_abort"):
                        drv.picks += 1
                        drv.stuck_entry = None
                elif drv.skip_attempts >= 3 and stuck >= 6.0:
                    self._dialog_request("dialog_skip")
                    drv.skip_attempts += 1
                else:
                    # Only a real VO wait is cleared; a node stalled for any
                    # other reason just burns an attempt toward the skip rung.
                    if dialog.get("waiting_on_sound") is True:
                        self._dialog_request("dialog_clear_sound_wait")
                    drv.skip_attempts += 1
                drv.next_retry = time.monotonic() + drv.retry_interval
        elif ((state.get("phase_detail") or {}).get("status_summary") == 1
              and ((state.get("phase_detail") or {}).get("modal_count") or 0) >= 1
              and time.monotonic() >= drv.next_retry):
            # The XP / level-available summary the engine raises after a
            # fight or a talk; it pauses the world until acknowledged.
            if self._dialog_request("dismiss_status_summary"):
                drv.picks += 1
            drv.next_retry = time.monotonic() + drv.retry_interval
        elif ((state.get("phase_detail") or {}).get("tutorial") == 1
              and ((state.get("phase_detail") or {}).get("modal_count") or 0) >= 1
              and time.monotonic() >= drv.next_retry):
            # phase_detail.tutorial can be set for other modal kinds too
            # (e.g. the party-selection panel), which neither of these close;
            # a wrong guess here must not abort the whole chain, only skip
            # this attempt and keep polling. advance_tutorial closes a
            # visible tutorial popup (e.g. the combat-tutorial hint that
            # appears on first reaching hostiles); finish_hidden_tutorial
            # covers one queued but not currently shown.
            try:
                self.ch.request("advance_tutorial")
                drv.picks += 1
            except ChannelError:
                try:
                    self.ch.request("finish_hidden_tutorial")
                    drv.picks += 1
                except ChannelError:
                    pass
            drv.next_retry = time.monotonic() + drv.retry_interval
        return False

    def _clear_room(self, step: Step) -> str:
        """Fight the hostiles around the PC until a postcondition holds.

        State-gated: the step ends on an observed fact, never on a timer. With
        ``until_global`` the fact is GetGlobalNumber(name) >= ``until_value``
        (a room's END_*_DEAD counter); without it, no live hostile within
        ``radius`` of the PC. Engine autopause re-pauses on combat events, so
        every poll clears it; the dialog/tutorial ladder shared with
        advance_dialog handles barks and the combat-tutorial popup.

        The PC is told to attack the nearest hostile only when the target
        changed (the previous one died) or the PC went idle; re-issuing
        ActionAttack every tick would reset the combat round.
        """
        r = step.raw
        radius = float(r.get("radius", 40.0))
        until_global = r.get("until_global")
        until_global = str(until_global) if until_global is not None else None
        until_value = int(r.get("until_value", 1))
        grace = float(r.get("grace", 8.0))
        budget = self._timeout(step)
        deadline = time.monotonic() + budget
        idle_actions = (65534, 0, 38)
        global_lua = ("nwscript.call(\"GetGlobalNumber\",%s)" % json.dumps(until_global)
                      if until_global is not None else "-1")
        probe_lua = (
            "local pc=nwscript.call(\"GetFirstPC\"); local area=nwscript.call(\"GetArea\",pc); local out={}; "
            "local c=nwscript.call(\"GetFirstObjectInArea\",area,1); "
            "while nwscript.call(\"GetIsObjectValid\",c)==1 do "
            "if nwscript.call(\"GetIsEnemy\",c,pc)==1 and nwscript.call(\"GetIsDead\",c)~=1 then "
            "local d=nwscript.call(\"GetDistanceBetween\",c,pc); "
            "if d<=%s then out[#out+1]={id=c,tag=nwscript.call(\"GetTag\",c),hp=nwscript.call(\"GetCurrentHitPoints\",c),dist=d} end end; "
            "c=nwscript.call(\"GetNextObjectInArea\",area,1) end; "
            "table.sort(out,function(a,b) return a.dist<b.dist end); "
            "return {hostiles=out,global=%s,act=nwscript.call(\"GetCurrentAction\",pc)}"
            % (json.dumps(radius), global_lua))
        drv = _DialogDriver(grace=float(self.sc.settings.get("dialog_grace", 10.0)))
        started = time.monotonic()
        seen: Dict[int, str] = {}
        target: Optional[int] = None
        empty_since: Optional[float] = None
        last_global = -1
        hostiles: List[dict] = []

        def summary() -> str:
            live = {int(h["id"]) for h in hostiles}
            down = sum(1 for oid in seen if oid not in live)
            out = f"clear_room: {down} hostiles down in {time.monotonic() - started:.1f}s"
            if until_global is not None:
                out += f", {until_global}={last_global}"
            return out

        while time.monotonic() < deadline:
            state = self.ch.state()
            v = self.watchdog.check(state)
            if v is not None:
                raise OracleTrip(v)
            detail = state.get("phase_detail") or {}
            if detail.get("pause"):
                self.ch.request("clear_auto_pause")
            if self._drive_dialog(state, drv):
                continue
            dialog = state.get("dialog")
            if isinstance(dialog, dict) and dialog.get("active") is True:
                # The PC's action queue is suspended by the conversation; an
                # attack issued now would be dropped or fight the dialog.
                self._on_poll(state)
                time.sleep(0.5)
                continue
            pc = state.get("pc") or {}
            hp = pc.get("hp")
            if isinstance(hp, (int, float)) and hp <= 0:
                raise _StepFailure(summary() + ": PC died", state=state)
            probe = self.ch.lua(probe_lua, timeout=min(30.0, max(1.0, deadline - time.monotonic())))
            values = probe.get("values") if isinstance(probe, dict) else None
            found = values[0] if isinstance(values, list) and values else None
            if not isinstance(found, dict):
                raise _StepFailure("clear_room: probe returned no table", state=state)
            raw_hostiles = found.get("hostiles") or []
            if isinstance(raw_hostiles, dict):      # empty/array table serialised as an object
                raw_hostiles = list(raw_hostiles.values())
            hostiles = sorted((h for h in raw_hostiles if isinstance(h, dict) and "id" in h),
                              key=lambda h: float(h.get("dist", 0.0)))
            for h in hostiles:
                seen.setdefault(int(h["id"]), str(h.get("tag", "")))
            g = found.get("global")
            last_global = int(g) if until_global is not None and isinstance(g, (int, float)) else -1
            act = found.get("act")
            if until_global is not None:
                if last_global >= until_value:
                    return summary()
            elif not hostiles:
                return summary()
            if not hostiles:
                if empty_since is None:
                    empty_since = time.monotonic()
                    self.log(f"clear_room: no hostile within {radius:g}, waiting up to {grace:g}s for {until_global}>={until_value}")
                elif time.monotonic() - empty_since >= grace:
                    raise _StepFailure(
                        summary() + f": no hostile within {radius:g} for {grace:g}s and "
                        f"{until_global}={last_global} < {until_value}", state=state)
            else:
                empty_since = None
                nearest = int(hostiles[0]["id"])
                if nearest != target or act in idle_actions:
                    target = nearest
                    self.log(f"clear_room: attack {seen.get(nearest, '')!r} id={nearest} "
                             f"dist={float(hostiles[0].get('dist', 0.0)):.1f} act={act}")
                    self.ch.lua(
                        "local pc=nwscript.call(\"GetFirstPC\"); local t=%d; "
                        "nwscript.with_caller(pc,function() nwscript.call(\"ClearAllActions\"); nwscript.call(\"ActionAttack\",t,0) end)"
                        % nearest, timeout=min(30.0, max(1.0, deadline - time.monotonic())))
            self._on_poll(state)
            time.sleep(0.5)
        raise _StepFailure(summary() + " but the ceiling passed before the room was clear",
                          state=self.ch.last_state)

    def _move_to(self, step: Step) -> str:
        """Walk the PC to an object (``tag``) or a point (``position``).

        State-gated: the step ends when the observed distance to the target
        is within ``range`` + 0.5, never on a timer. Party members follow on
        their own. A closed door in the way leaves the PC oscillating next to
        it with the move action still queued and no distance progress, so
        progress is the gate for retries: when the best distance has not
        improved by 0.25 for ``stall`` seconds the move is re-issued once and
        a second stall fails the step. An idle action queue (65534) short of
        the target means the path was cut; that is re-issued once as well.

        Autopause is cleared every poll and the dialog/tutorial ladder shared
        with advance_dialog runs first; while a conversation is active the
        PC's action queue is suspended, so no move is issued until it ends.
        """
        r = step.raw
        tag = r.get("tag")
        position = r.get("position")
        if (tag is None) == (position is None):
            raise _StepFailure("move_to needs exactly one of tag or position")
        run = 1 if bool(r.get("run", True)) else 0
        stall = float(r.get("stall", 4.0))
        deadline = time.monotonic() + self._timeout(step)
        if tag is not None:
            tag = str(tag)
            label = tag
            rng = float(r.get("range", 1.5))
            resolve = ("local t=nwscript.call(\"GetObjectByTag\",%s,0); "
                       "if nwscript.call(\"GetIsObjectValid\",t)~=1 then return {missing=1} end; "
                       % json.dumps(tag))
            probe_lua = (
                "local pc=nwscript.call(\"GetFirstPC\"); " + resolve +
                "local p=nwscript.call(\"GetPosition\",pc); " + _NEAREST_HOSTILE_LUA +
                "return {dist=nwscript.call(\"GetDistanceBetween\",pc,t),act=nwscript.call(\"GetCurrentAction\",pc),combat=nwscript.call(\"GetIsInCombat\",pc),hd=hd,hid=hid,x=p.x,y=p.y}")
            move_lua = (
                "local pc=nwscript.call(\"GetFirstPC\"); " + resolve +
                "nwscript.with_caller(pc,function() nwscript.call(\"ClearAllActions\"); nwscript.call(\"ActionMoveToObject\",t,%d,%s) end); "
                "return {issued=1}" % (run, json.dumps(rng)))
        else:
            if not isinstance(position, (list, tuple)) or len(position) != 3:
                raise _StepFailure("move_to: position must be [x, y, z]")
            x, y, z = (json.dumps(float(v)) for v in position)
            label = f"({x},{y},{z})"
            rng = float(r.get("range", 0.75))
            # Parenthesise the literals: "p.z--1.2" would open a Lua comment.
            probe_lua = (
                "local pc=nwscript.call(\"GetFirstPC\"); local p=nwscript.call(\"GetPosition\",pc); "
                "local dx,dy,dz=p.x-(%s),p.y-(%s),p.z-(%s); " % (x, y, z) + _NEAREST_HOSTILE_LUA +
                "return {dist=math.sqrt(dx*dx+dy*dy+dz*dz),act=nwscript.call(\"GetCurrentAction\",pc),combat=nwscript.call(\"GetIsInCombat\",pc),hd=hd,hid=hid,x=p.x,y=p.y}")
            move_lua = (
                "local pc=nwscript.call(\"GetFirstPC\"); "
                "nwscript.with_caller(pc,function() nwscript.call(\"ClearAllActions\"); "
                "nwscript.call(\"ActionMoveToLocation\",nwscript.call(\"Location\",nwscript.call(\"Vector\",%s,%s,%s),0.0),%d) end); "
                "return {issued=1}" % (x, y, z, run))
        drv = _DialogDriver(grace=float(self.sc.settings.get("dialog_grace", 10.0)))
        started = time.monotonic()
        issues = 0
        best: Optional[float] = None
        mark: Optional[float] = None        # distance at the last progress mark
        mark_at = started
        stall_reissued = False
        idle_reissued = False
        resume = False                      # a dialog interrupted the walk
        fought = False                      # combat took over the action queue

        def budget() -> float:
            return min(30.0, max(1.0, deadline - time.monotonic()))

        mark_tick = -1                      # server tick at the last progress mark
        # A stall is judged in simulation time as well as wall time: on a
        # starved host the world advances a few ticks per second and 4s of
        # wall clock is not enough walking to move 0.25 units.
        stall_ticks = int(r.get("stall_ticks", 20))

        def issue(why: str, dist: float, act: Any) -> None:
            nonlocal issues, mark_at, mark_tick
            issues += 1
            self.log(f"move_to {label}: {why} (issue #{issues}) dist={dist:.1f} act={act}")
            self.ch.lua(move_lua, timeout=budget())
            mark_at = time.monotonic()
            mark_tick = -1

        while time.monotonic() < deadline:
            state = self.ch.state()
            v = self.watchdog.check(state)
            if v is not None:
                raise OracleTrip(v)
            detail = state.get("phase_detail") or {}
            if detail.get("pause"):
                self.ch.request("clear_auto_pause")
            if self._drive_dialog(state, drv):
                continue
            dialog = state.get("dialog")
            if isinstance(dialog, dict) and dialog.get("active") is True:
                # The conversation suspends the PC's action queue; a move
                # issued now would be dropped. Re-issue once it ends.
                resume = issues > 0
                mark_at = time.monotonic()
                self._on_poll(state)
                time.sleep(0.4)
                continue
            pc = state.get("pc") or {}
            hp = pc.get("hp")
            if isinstance(hp, (int, float)) and hp <= 0:
                raise _StepFailure(f"move_to {label}: PC died", state=state)
            probe = self.ch.lua(probe_lua, timeout=budget())
            values = probe.get("values") if isinstance(probe, dict) else None
            found = values[0] if isinstance(values, list) and values else None
            if not isinstance(found, dict):
                raise _StepFailure(f"move_to {label}: probe returned no table", state=state)
            if found.get("missing"):
                raise _StepFailure(f"move_to {label}: no valid object with tag {tag!r}", state=state)
            dist = float(found.get("dist", 0.0))
            act = found.get("act")
            if dist <= rng + 0.5:
                return f"move_to {label}: dist {dist:.1f} in {time.monotonic() - started:.1f}s"
            now = time.monotonic()
            best = dist if best is None else min(best, dist)
            tick = int(state.get("server_tick") or 0)
            if mark_tick < 0:
                mark_tick = tick
            if int(found.get("combat") or 0):
                # An ambush on the way: the engine's combat AI owns the queue
                # until the fight ends, so no distance is expected and no
                # retry is spent. The walk is re-issued when combat clears.
                fought = True
                mark, mark_at, mark_tick = dist, now, tick
                self._on_poll(state)
                time.sleep(0.4)
                continue
            if mark is None or dist <= mark - 0.25:
                mark, mark_at, mark_tick = dist, now, tick
            if issues == 0:
                issue("walk", dist, act)
            elif fought:
                fought = False
                mark, mark_at, mark_tick = dist, now, tick
                issue("resume after combat", dist, act)
            elif resume:
                resume = False
                issue("resume after dialog", dist, act)
            elif act == 65534:
                if idle_reissued:
                    raise _StepFailure(f"move_to {label}: stopped short at dist {dist:.1f}", state=state)
                idle_reissued = True
                issue("idle short of target, re-issue", dist, act)
            elif now - mark_at >= stall and tick - mark_tick >= stall_ticks:
                hd = float(found.get("hd", 999.0))
                hid = int(found.get("hid") or 0)
                if hid and hd <= 12.0:
                    # A hostile standing in the corridor blocks the path
                    # without engaging (GetIsInCombat stays 0). Fight it:
                    # combat takes the queue, and the walk resumes after.
                    self.log(f"move_to {label}: blocked with hostile id={hid} at {hd:.1f}, attacking")
                    self.ch.lua("local pc=nwscript.call(\"GetFirstPC\"); local t=%d; if nwscript.call(\"GetIsObjectValid\",t)==1 then "
                                "nwscript.with_caller(pc,function() nwscript.call(\"ClearAllActions\"); nwscript.call(\"ActionAttack\",t,0) end) end; return 1"
                                % hid, timeout=budget())
                    fought = True
                    mark, mark_at = dist, now
                elif stall_reissued:
                    raise _StepFailure(
                        f"move_to {label}: no progress for {stall:g}s at dist {dist:.1f} (blocked?)",
                        state=state)
                else:
                    stall_reissued = True
                    issue(f"no progress for {stall:g}s, re-issue", dist, act)
            self._on_poll(state)
            time.sleep(0.4)
        raise _StepFailure(
            f"move_to {label}: ceiling passed"
            + (f" at best dist {best:.1f}" if best is not None else ""),
            state=self.ch.last_state)

    def _reply(self, step: Step) -> str:
        pick = step.raw.get("pick", "first_active")
        d = self.ch.request("dialog")
        replies = (d or {}).get("replies") or []
        if not replies:
            raise _StepFailure("no replies on the current dialog node", state=self.ch.last_state)
        chosen: Optional[dict] = None
        if isinstance(pick, int):
            for pos, rep in enumerate(replies):
                if isinstance(rep, dict) and rep.get("index", pos) == pick:
                    chosen = rep
            if chosen is None and 0 <= pick < len(replies):
                chosen = replies[pick] if isinstance(replies[pick], dict) else {"index": pick}
        elif isinstance(pick, str) and pick.startswith("link:"):
            try:
                wanted_link = int(pick.split(":", 1)[1])
            except ValueError as e:
                raise _StepFailure(f"invalid reply link selector {pick!r}") from e
            for pos, rep in enumerate(replies):
                if isinstance(rep, dict) and int(rep.get("link", -1)) == wanted_link and rep.get("active", True):
                    chosen = dict(rep)
                    chosen.setdefault("index", pos)
                    break
        elif isinstance(pick, str) and pick.startswith("script:"):
            wanted_script = pick.split(":", 1)[1].rstrip("\0").lower()
            for pos, rep in enumerate(replies):
                if (isinstance(rep, dict)
                        and str(rep.get("script", "")).rstrip("\0").lower() == wanted_script
                        and rep.get("active", True)):
                    chosen = dict(rep)
                    chosen.setdefault("index", pos)
                    break
        elif str(pick) == "first_active":
            for pos, rep in enumerate(replies):
                if isinstance(rep, dict) and rep.get("active", True):
                    chosen = dict(rep)
                    chosen.setdefault("index", pos)
                    break
        else:
            want = str(pick).lower()
            for pos, rep in enumerate(replies):
                if isinstance(rep, dict) and want in str(rep.get("text", "")).lower():
                    chosen = dict(rep)
                    chosen.setdefault("index", pos)
                    break
        if chosen is None:
            raise _StepFailure(f"no reply matches pick={pick!r} among {len(replies)}")
        idx = int(chosen.get("index", 0))
        self.ch.request("reply", index=idx)
        return f"reply index {idx}: {str(chosen.get('text', ''))[:60]!r}"

    # -------------------------------------------------------------- wait --
    def _wait_step(self, step: Step) -> dict:
        r = step.raw
        kind = str(r["wait"])
        default_progress = kind in ("module", "event", "global", "journal")
        progress = bool(r.get("progress", default_progress))
        timeout = self._timeout(step, "load_timeout" if kind == "phase" and
                                r.get("equals") == "gameplay" else "default_timeout")
        if kind == "phase":
            pred = W.phase_is(str(r["equals"]))
        elif kind == "phase_any":
            values = r.get("equals", r.get("any"))
            if not isinstance(values, list) or not values or not all(isinstance(v, str) for v in values):
                raise ScenarioError(f"step {step.index}: phase_any requires a non-empty string list in equals or any")
            pred = W.phase_is_any(values)
        elif kind == "module":
            pred = W.module_is(str(r["equals"]))
        elif kind == "event":
            pred = W.event_seen(str(r["name"]), int(r.get("after", self.mark_seq)))
        elif kind == "global":
            pred = W.global_equals(str(r["name"]), r.get("equals", 1))
        elif kind == "journal":
            pred = W.journal_state(str(r["tag"]), r.get("equals", r.get("state", 0)))
        elif kind == "dialog":
            pred = W.dialog_waiting()
        elif kind == "dialog_entry":
            try:
                entry = int(r["equals"])
            except (KeyError, TypeError, ValueError) as e:
                raise ScenarioError(f"step {step.index}: dialog_entry requires integer equals") from e
            pred = W.dialog_entry_is(entry)
            self._awaited_entry = entry
        elif kind == "chargen":
            pred = W.chargen_open()
        elif kind == "chargen_stage":
            pred = W.chargen_stage_is(str(r["equals"]))
        else:
            raise ScenarioError(f"step {step.index}: unknown wait kind {kind!r}")
        try:
            return self._wait(step, pred, getattr(pred, "__name__", kind), progress, timeout)
        finally:
            self._awaited_entry = None

    def _expect_events(self, step: Step) -> dict:
        names = [n if isinstance(n, dict) else str(n) for n in step.raw["expect_events"]]
        since = int(step.raw.get("after", self.mark_seq))
        pred = W.events_in_order(names, since)
        return self._wait(step, pred, f"events {names} after seq {since}", False,
                          self._timeout(step, "events_timeout"))

    def _screenshot(self, step: Step) -> StepResult:
        t0 = time.monotonic()
        state = None
        try:
            state = self.ch.state()
        except ChannelError:
            pass
        path = self.shooter.take(step.label or f"step{step.index}", state) if self.shooter else None
        screen = None
        detail = str(path) if path else "no screenshot taken"
        kind = step.raw.get("expect_screen")
        if kind:
            screen = check_screen(str(kind), path, state)
            if screen.get("warning"):
                self.log(f"screen check: {screen['warning']}")
            detail += f"; ocr ratio {screen.get('ratio')}"
        return StepResult(step.index, step.describe(), "ok", time.monotonic() - t0, detail,
                          screen=screen)

    # --------------------------------------------------------------- run --
    def run_step(self, step: Step) -> StepResult:
        t0 = time.monotonic()
        desc = step.describe()
        self.log(f"step {step.index}: {desc}")
        kind = step.kind
        expect_verdict = step.raw.get("expect_verdict")
        expect_error = step.raw.get("expect_error")
        try:
            if kind == "screenshot":
                return self._screenshot(step)
            if kind == "do":
                self.mark_seq = self.sync_cursor()
                detail = self._do(step)
                if expect_error:
                    raise _StepFailure(f"expected error {expect_error!r} but the command succeeded")
                v = self.watchdog.check_logs()
                if v is not None:
                    raise OracleTrip(v)
                return StepResult(step.index, desc, "ok", time.monotonic() - t0, detail)
            state = self._wait_step(step) if kind == "wait" else self._expect_events(step)
            if expect_verdict:
                raise _StepFailure(f"expected verdict {expect_verdict!r} but the wait succeeded",
                                   state=state)
            return StepResult(step.index, desc, "ok", time.monotonic() - t0,
                              summarise_state(state), state=state)
        except OracleTrip as trip:
            v = trip.verdict
            if expect_verdict and v.kind == str(expect_verdict):
                self.log(f"  expected verdict {v.kind} tripped: {v.reason}")
                return StepResult(step.index, desc, "expected_failure", time.monotonic() - t0,
                                  f"{v.kind}: {v.reason}", verdict=v.to_dict(), state=v.state)
            return StepResult(step.index, desc, "failed", time.monotonic() - t0, str(v),
                              verdict=v.to_dict(), state=v.state)
        except W.WaitTimeout as e:
            return StepResult(step.index, desc, "failed", time.monotonic() - t0, str(e),
                              state=e.state)
        except ChannelError as e:
            if expect_error and str(expect_error) in e.error:
                return StepResult(step.index, desc, "ok", time.monotonic() - t0,
                                  f"expected error: {e.error}")
            if e.unsupported:
                return StepResult(step.index, desc, "skipped", time.monotonic() - t0, e.error)
            return StepResult(step.index, desc, "failed", time.monotonic() - t0,
                              f"{e.cmd}: {e.error}")
        except (_StepFailure, CheckpointError) as e:
            return StepResult(step.index, desc, "failed", time.monotonic() - t0, str(e),
                              verdict=e.verdict.to_dict() if isinstance(e, _StepFailure) and e.verdict else None,
                              state=e.state if isinstance(e, _StepFailure) else None)

    def run(self) -> Report:
        rep = self.report
        try:
            self._configure_execution()
            for step in self.sc.steps:
                res = self.run_step(step)
                rep.steps.append(res)
                self.log(f"  {res.status} ({res.seconds:.1f}s) {res.detail[:160]}")
                if res.status == "failed":
                    rep.verdict = res.verdict
                    break
                if res.verdict and res.verdict.get("kind") in FATAL_VERDICTS:
                    rep.verdict = res.verdict
                    break
            else:
                rep.ok = all(s.status != "failed" for s in rep.steps)
        except ScenarioError as e:
            rep.error = str(e)
        except Exception as e:  # noqa: BLE001 - the report must still be written
            rep.error = f"{type(e).__name__}: {e}"
        rep.finished = time.time()
        rep.ok = rep.ok and not rep.error
        try:
            path = rep.write(self.run_dir / "report.json")
            self.log(f"report: {path}")
        except OSError as e:
            self.log(f"report not written: {e}")
        return rep


def scenario_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "scenarios"


def find_scenario(name_or_path: str) -> Path:
    p = Path(name_or_path)
    if p.is_file():
        return p
    cand = scenario_dir() / (name_or_path if name_or_path.endswith(".toml") else name_or_path + ".toml")
    if cand.is_file():
        return cand
    raise ScenarioError(f"no scenario {name_or_path!r} (looked in {scenario_dir()})")


def list_scenarios() -> List[Path]:
    d = scenario_dir()
    return sorted(d.rglob("*.toml")) if d.is_dir() else []


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")

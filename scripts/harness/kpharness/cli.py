"""kpharness: boot a headless game, ask it things, run scenarios, tear down.

  kpharness boot   --target k1            stage, boot, connect, leave running
  kpharness status [--target k1]          discovery facts, or `status` if booted
  kpharness state  [--target k1]          the engine state snapshot
  kpharness reply  --target k1 INDEX      choose one current dialog reply
  kpharness exec   [--target k1] CODE     run a Lua chunk over the channel
  kpharness events [--target k1]          events since a cursor
  kpharness shots  [--target k1]          take one screenshot now
  kpharness run    SCENARIO [--target k1] boot, execute, tear down, report
  kpharness down   [--target k1]          tear a booted session down
  kpharness devtools-bridge --standalone --port PORT
                                           serve the authenticated loopback console bridge

  kpharness pioneer init   --out R.toml --target k1 --name "..."
  kpharness pioneer step   --out R.toml '{"do": "lua", "code": "..."}'
  kpharness pioneer commit --out R.toml
  kpharness pioneer discard --out R.toml
  kpharness pioneer status --out R.toml
    A CLI TAS: pioneer a route on a booted session one verified step at a
    time. `step` runs the given step body now over the real dispatch path a
    scenario run uses and prints the result; `commit` appends exactly that
    already-inspected step to R.toml. Nothing is written to the route file
    on a whim -- only what was just executed and looked at.

  kpharness pioneer attach      --out R.toml
  kpharness pioneer play        --out R.toml [--until N] [--verify-current LUA | --restart]
  kpharness pioneer fastforward --out R.toml --speed X [--until N] ...
  kpharness pioneer stop        --out R.toml
  kpharness pioneer reclaim     --out R.toml
    Replay committed steps through one attached owner process, which is
    then the only engine connection. While it is attached, `step`, `commit`
    and `discard` for that route go through it, and `exec`, `reply`,
    `state`, `events` and `shots` are refused. `--speed` is the engine's
    configured multiplier in (0,16], read back before it is reported; the
    prior multiplier is restored at job end unless a route `speed` step ran.
    `stop` (or SIGTERM/SIGHUP to the owner) stops execution. It does not
    pause the game world. `reclaim` recovers after an owner was killed
    without cleanup; it refuses while the owner still holds its locks.

A booted session leaves tmp/<target>_harness/session.json behind; the
other commands find the port there. `run` does the whole cycle itself.
Exit status: 0 on success, 1 on a scenario or command failure, 2 on a boot
failure, 3 on a usage error.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import sys
import time
from pathlib import Path
from typing import Optional

from . import discover, pioneer as P, playback as PB, scenario as S, targets as T
from .checkpoints import Checkpoints
from .client import Channel, ChannelError, summarise_state
from .session import (channel_timeout, BootFailure, GameSession, InvalidBootAttempts, LockHeld,
                      SessionInfo, resolve_max_boot_attempts, teardown_from_info)
from .shots import Shooter


def _info(target: str) -> Optional[SessionInfo]:
    t = T.get(target)
    root = discover.repo_root() / "tmp"
    for name in (f"{t.name}_harness", f"{t.game}_harness"):
        p = GameSession.session_info_path(root / name)
        if p.is_file():
            try:
                return SessionInfo.from_dict(json.loads(p.read_text()))
            except (OSError, ValueError, TypeError):
                continue
    return None


@contextlib.contextmanager
def _channel(target: str):
    """One engine connection under the per-engine lock.

    An attached playback owner holds that lock and is the only engine
    connection; these commands are refused while it lives.
    """
    info = _info(target)
    if info is None:
        raise SystemExit(f"no booted session for {target}; run `kpharness boot --target {target}`")
    with PB.engine_guard(info):
        ch = Channel("127.0.0.1", info.port, timeout=channel_timeout())
        ch.connect()
        with ch:
            yield ch


def _print(obj) -> None:
    print(json.dumps(obj, indent=1, default=str))


def _boot_budget_error(a: argparse.Namespace) -> Optional[str]:
    """Validate KP_MAX_BOOT_ATTEMPTS and --max-boot-attempts before any session,
    lock, stage or launch. The environment is checked even when the flag wins."""
    try:
        resolve_max_boot_attempts()
        if a.max_boot_attempts is not None:
            resolve_max_boot_attempts(a.max_boot_attempts)
    except InvalidBootAttempts as e:
        return f"kpharness: {e}; nothing launched"
    return None


def _boot_failed(e: BaseException) -> str:
    extra = [f"{name}={getattr(e, name)}" for name in ("launch_count", "max_boot_attempts", "evidence_path")
             if getattr(e, name, None) is not None]
    return f"boot failed: {e}" + (f" ({', '.join(extra)})" if extra else "")


# ------------------------------------------------------------- commands --

def cmd_boot(a: argparse.Namespace) -> int:
    problem = _boot_budget_error(a)
    if problem:
        print(problem, file=sys.stderr)
        return 3
    try:
        s = GameSession(a.target, build_dir=a.build_dir, display=a.display, port=a.port,
                        boot_timeout=a.boot_timeout, force=a.force, wine_debug=a.wine_debug,
                        staged=a.staged, wineprefix=a.wineprefix, persistent=True,
                        max_boot_attempts=a.max_boot_attempts)
    except InvalidBootAttempts as e:
        print(f"kpharness: {e}; nothing launched", file=sys.stderr)
        return 3
    try:
        ch = s.boot()
    except (BootFailure, LockHeld, FileNotFoundError) as e:
        print(_boot_failed(e), file=sys.stderr)
        return 2
    _print({"port": s.port, "display": s.display, "run_dir": str(s.run_dir),
            "status": ch.status()})
    ch.close()
    return 0


def cmd_status(a: argparse.Namespace) -> int:
    info = _info(a.target)
    if info is None:
        _print(discover.describe(T.get(a.target)))
        return 0
    try:
        with _channel(a.target) as ch:
            _print({"session": info.to_dict(), "status": ch.status()})
    except PB.PlaybackError as e:
        # Booted and busy: a playback owner or Pioneer command holds it.
        _print({"session": info.to_dict(), "status": None, "engine_busy": str(e)})
        return 0
    except (OSError, ChannelError) as e:
        _print({"session": info.to_dict(), "error": str(e)})
        return 1
    return 0


def cmd_state(a: argparse.Namespace) -> int:
    with _channel(a.target) as ch:
        _print(ch.state())
    return 0


def cmd_reply(a: argparse.Namespace) -> int:
    with _channel(a.target) as ch:
        _print(ch.request("reply", index=a.index, timeout=a.timeout))
    return 0


def cmd_exec(a: argparse.Namespace) -> int:
    code = " ".join(a.code)
    with _channel(a.target) as ch:
        try:
            _print(ch.lua(code, timeout=a.timeout))
        except ChannelError as e:
            print(f"error: {e.error}", file=sys.stderr)
            return 1
    return 0


def cmd_events(a: argparse.Namespace) -> int:
    with _channel(a.target) as ch:
        _print(ch.events(since=a.since, limit=a.limit))
    return 0


def cmd_shots(a: argparse.Namespace) -> int:
    info = _info(a.target)
    if info is None:
        raise SystemExit(f"no booted session for {a.target}")
    with _channel(a.target) as ch:
        sh = Shooter(ch, Path(info.game_dir), Path(info.run_dir), interval=0, log=print)
        p = sh.take(a.label or "manual")
        print(p or "no screenshot")
    return 0 if p else 1


def cmd_down(a: argparse.Namespace) -> int:
    info = _info(a.target)
    if info is None:
        print(f"no booted session for {a.target}")
        return 0
    teardown_from_info(info)
    return 0


def cmd_run(a: argparse.Namespace) -> int:
    problem = _boot_budget_error(a)
    if problem:
        print(problem, file=sys.stderr)
        return 3
    try:
        path = S.find_scenario(a.scenario)
        sc = S.Scenario.load(path)
    except S.ScenarioError as e:
        print(f"scenario: {e}", file=sys.stderr)
        return 3
    target = a.target or sc.target
    try:
        s = GameSession(target, build_dir=a.build_dir, display=a.display, port=a.port,
                        boot_timeout=a.boot_timeout, force=a.force, wine_debug=a.wine_debug,
                        staged=a.staged, wineprefix=a.wineprefix, reset_saves=True,
                        max_boot_attempts=a.max_boot_attempts)
    except InvalidBootAttempts as e:
        print(f"kpharness: {e}; nothing launched", file=sys.stderr)
        return 3
    try:
        ch = s.boot(resources=list(sc.resources.values()))
    except (BootFailure, LockHeld, FileNotFoundError) as e:
        print(_boot_failed(e), file=sys.stderr)
        return 2
    try:
        cps = Checkpoints(s.target, s.save_dir) if s.save_dir else None
        runner = S.ScenarioRunner(sc, s, ch, log=s.log, checkpoints=cps)
        rep = runner.run()
    finally:
        s.teardown()
    print(f"{sc.name}: {'PASS' if rep.ok else 'FAIL'} "
          f"({sum(1 for x in rep.steps if x.status == 'ok')} ok, "
          f"{sum(1 for x in rep.steps if x.status == 'skipped')} skipped, "
          f"{sum(1 for x in rep.steps if x.status == 'expected_failure')} expected failures, "
          f"{sum(1 for x in rep.steps if x.status == 'failed')} failed) -> {rep.run_dir}/report.json")
    if rep.verdict:
        print(f"verdict: {rep.verdict.get('kind')}: {rep.verdict.get('reason')}")
    if rep.error:
        print(f"error: {rep.error}")
    return 0 if rep.ok else 1


def cmd_pioneer_init(a: argparse.Namespace) -> int:
    barks = json.loads(a.authored_barks) if a.authored_barks else None
    try:
        P.init_route(Path(a.out), target=a.target, name=a.name or Path(a.out).stem,
                    authored_barks=barks, force=a.force)
    except P.PioneerError as e:
        print(f"pioneer init: {e}", file=sys.stderr)
        return 1
    print(f"{a.out}: initialised for {a.target}")
    return 0


def cmd_pioneer_step(a: argparse.Namespace) -> int:
    try:
        step_body = json.loads(a.step)
    except json.JSONDecodeError as e:
        print(f"pioneer step: step body is not valid JSON: {e}", file=sys.stderr)
        return 3
    if not isinstance(step_body, dict):
        print("pioneer step: step body must be a JSON object", file=sys.stderr)
        return 3
    out = Path(a.out)
    try:
        if PB.attached(out):
            # The attached owner holds this route and the engine; it runs
            # the step over its own connection.
            result = _authored(PB.author(out, {"op": "step", "step": step_body}), "step")
        else:
            info = _info(a.target)
            if info is None:
                raise SystemExit(f"no booted session for {a.target}; run `kpharness boot --target {a.target}`")
            with PB.engine_guard(info), Channel("127.0.0.1", info.port, timeout=channel_timeout()) as ch:
                result = P.execute_pending(out, ch, info, step_body, log=print).to_dict()
    except (P.PioneerError, PB.PlaybackError, OSError, ChannelError, S.ScenarioError) as e:
        print(f"pioneer step: {e}", file=sys.stderr)
        return 1
    _print(result)
    status = result.get("status")
    if status == "ok":
        print(f"pending: `pioneer commit --out {a.out}` to append this step, "
              f"or `pioneer discard --out {a.out}` to drop it.")
    else:
        print(f"step did not succeed (status={status}); nothing will be committed "
              "unless you commit it deliberately.")
    return 0 if status == "ok" else 1


def cmd_pioneer_commit(a: argparse.Namespace) -> int:
    out = Path(a.out)
    try:
        pending = P.load_pending(out)
        if pending is None:
            raise P.PioneerError("no pending step")
        if PB.attached(out):
            appended = _authored(PB.author(out, {"op": "commit", "force": a.force}), "commit")
        else:
            info = _info(pending.target)
            if info is None:
                raise P.PioneerError("the recorded live session is no longer attached")
            with PB.engine_guard(info), Channel("127.0.0.1", info.port, timeout=channel_timeout()) as ch:
                appended = P.commit_pending(out, ch, info, force=a.force)
    except (P.PioneerError, PB.PlaybackError, OSError, ChannelError, S.ScenarioError, ValueError) as e:
        print(f"pioneer commit: {e}", file=sys.stderr)
        return 1
    print(f"{out}: {'appended verified pending step' if appended else 'already committed; no duplicate append'}")
    return 0


def cmd_pioneer_discard(a: argparse.Namespace) -> int:
    out = Path(a.out)
    try:
        if PB.attached(out):
            _authored(PB.author(out, {"op": "discard"}), "discard")
        else:
            P.discard_pending(out)
    except (P.PioneerError, PB.PlaybackError, OSError, ValueError) as e:
        print(f"pioneer discard: {e}", file=sys.stderr)
        return 1
    print(f"{out}: pending metadata discarded; live game changes were NOT undone")
    return 0


def cmd_pioneer_status(a: argparse.Namespace) -> int:
    out = Path(a.out)
    pending = P.load_pending(out)
    try:
        playback = PB.status(out)
    except (PB.PlaybackError, OSError, ValueError) as e:
        playback = {"operation_state": "unknown", "error": str(e)}
    live_state = None
    info = _info(a.target)
    if info is not None and not PB.attached(out):
        # Never a second engine connection beside an attached owner.
        try:
            with PB.engine_guard(info), Channel("127.0.0.1", info.port, timeout=channel_timeout()) as ch:
                live_state = summarise_state(ch.state())
        except (PB.PlaybackError, OSError, ChannelError):
            live_state = None
    _print({"route": str(out), "pending": pending.to_dict() if pending else None,
            "live_state": live_state, "playback": playback})
    return 0


def _authored(state: dict, op: str):
    """Unwrap one authoring job finished by the attached owner."""
    authoring = state.get("authoring") or {}
    if state.get("job_finished") != state.get("job_id") or authoring.get("op") != op:
        raise PB.PlaybackError(state.get("last_error") or f"attached owner did not finish {op}")
    if op == "step":
        return authoring["result"]
    return authoring.get("appended")


def _playback_session(out: Path) -> SessionInfo:
    target = P._load_header_only(out).target
    info = _info(target)
    if info is None:
        raise SystemExit(f"no booted session for {target}; run `kpharness boot --target {target}`")
    return info


def cmd_pioneer_attach(a: argparse.Namespace) -> int:
    out = Path(a.out)
    try:
        state = PB.start(out, _playback_session(out))
    except (P.PioneerError, PB.PlaybackError, OSError, ValueError) as e:
        print(f"pioneer attach: {e}", file=sys.stderr)
        return 1
    _print(state)
    return 0


def cmd_pioneer_play(a: argparse.Namespace) -> int:
    out = Path(a.out)
    request = {"op": a.pioneer_cmd}
    if a.until is not None:
        request["until"] = a.until
    if a.verify_current is not None:
        request["verify_current"] = a.verify_current
    if a.restart:
        request["restart"] = True
    if a.pioneer_cmd == "fastforward":
        request["speed"] = a.speed
    try:
        if not PB.attached(out):
            PB.start(out, _playback_session(out))
        accepted = PB.control(out, request)
        if a.no_wait:
            _print(accepted)
            return 0
        # wait_job only polls status; the request itself is never re-sent.
        state = PB.wait_job(out, accepted["job_id"], timeout=a.timeout)
    except (P.PioneerError, PB.PlaybackError, OSError, ValueError) as e:
        print(f"pioneer {a.pioneer_cmd}: {e}", file=sys.stderr)
        return 1
    _print(state)
    return 0 if state.get("operation_state") == "completed" else 1


def cmd_pioneer_stop(a: argparse.Namespace) -> int:
    out = Path(a.out)
    try:
        state = PB.control(out, {"op": "stop"})
    except OSError as e:
        print(f"pioneer stop: owner not reachable ({e}); {PB.unreachable_hint(out)}", file=sys.stderr)
        return 1
    except (PB.PlaybackError, ValueError) as e:
        print(f"pioneer stop: {e}", file=sys.stderr)
        return 1
    state["note"] = ("execution stop requested: the owner issues no further step and detaches. "
                     "This does not pause the game world, which keeps running.")
    _print(state)
    return 0


def cmd_pioneer_reclaim(a: argparse.Namespace) -> int:
    out = Path(a.out)
    try:
        report = PB.reclaim(out, _playback_session(out))
    except (P.PioneerError, PB.PlaybackError, OSError, ChannelError, ValueError) as e:
        print(f"pioneer reclaim: {e}", file=sys.stderr)
        return 1
    _print(report)
    return 0


def cmd_list(_: argparse.Namespace) -> int:
    for p in S.list_scenarios():
        name = p.relative_to(S.scenario_dir()).with_suffix("").as_posix()
        try:
            sc = S.Scenario.load(p)
            print(f"{name:24} {sc.target:10} {sc.name}")
        except S.ScenarioError as e:
            print(f"{name:24} (invalid: {e})")
    return 0


def cmd_devtools_bridge(a: argparse.Namespace) -> int:
    """Run the browser bridge; attach waits for the playback owner API."""
    from . import devtools_bridge
    args = ["--standalone", "--host", a.host, "--port", str(a.port)] if a.standalone \
        else ["--attach", a.attach]
    args += ["--listen", a.listen]
    if a.token_file:
        args += ["--token-file", a.token_file]
    return devtools_bridge.main(args)


# ----------------------------------------------------------------- main --

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="kpharness", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def target_arg(p: argparse.ArgumentParser, required: bool = False, default: Optional[str] = "k1"):
        p.add_argument("--target", "-t", choices=T.names() + ["k2"], required=required,
                       default=default, help="k1, k2-wine, or k2-native (k2 is k2-native)")

    def boot_args(p: argparse.ArgumentParser):
        p.add_argument("--build-dir", help="where hyperstim.dll / libhyperstim.so were built")
        p.add_argument("--staged", help="harness staging tree; KP_STAGED_DIR when omitted")
        p.add_argument("--wineprefix", help="dedicated Wine prefix; KP_WINEPREFIX when omitted")
        p.add_argument("--display", type=int, help="X display number; default: first free")
        p.add_argument("--port", type=int, help="listener port; default: a free one")
        p.add_argument("--boot-timeout", type=float, default=300.0,
                       help="ceiling for the channel to answer status")
        p.add_argument("--force", action="store_true", help="take a held display lock")
        p.add_argument("--wine-debug", help="WINEDEBUG value; default -all")
        p.add_argument("--max-boot-attempts", type=int, metavar="N",
                       help="launch the game at most N times (1..5); 1 = one launch, no relaunch. "
                            "Default: KP_MAX_BOOT_ATTEMPTS, else 5")

    p = sub.add_parser("boot", help="stage, boot, connect, leave running")
    target_arg(p); boot_args(p); p.set_defaults(fn=cmd_boot)

    p = sub.add_parser("status", help="discovery facts, or status if booted")
    target_arg(p); p.set_defaults(fn=cmd_status)

    p = sub.add_parser("state", help="the engine state snapshot")
    target_arg(p); p.set_defaults(fn=cmd_state)

    p = sub.add_parser("reply", help="choose one current dialog reply")
    target_arg(p); p.add_argument("index", type=int)
    p.add_argument("--timeout", type=float, default=30.0)
    p.set_defaults(fn=cmd_reply)

    p = sub.add_parser("exec", help="run a Lua chunk over the channel")
    target_arg(p)
    p.add_argument("code", nargs="+", help="Lua source; use `return ...` for a value")
    p.add_argument("--timeout", type=float, default=30.0)
    p.set_defaults(fn=cmd_exec)

    p = sub.add_parser("events", help="events since a cursor")
    target_arg(p)
    p.add_argument("--since", type=int, default=0)
    p.add_argument("--limit", type=int, default=200)
    p.set_defaults(fn=cmd_events)

    p = sub.add_parser("shots", help="take one screenshot now")
    target_arg(p)
    p.add_argument("--label", default="")
    p.set_defaults(fn=cmd_shots)

    p = sub.add_parser("run", help="boot, run a scenario, tear down")
    p.add_argument("scenario", help="name under scripts/harness/scenarios or a path")
    target_arg(p, default=None); boot_args(p); p.set_defaults(fn=cmd_run)

    p = sub.add_parser("down", help="tear a booted session down")
    target_arg(p); p.set_defaults(fn=cmd_down)

    p = sub.add_parser("list", help="scenarios available")
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("devtools-bridge", help="serve the authenticated loopback console bridge")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--standalone", action="store_true", help="own one harness Channel directly")
    mode.add_argument("--attach", metavar="OWNER", help="attach to a playback owner (unsupported until its API exists)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=0, help="standalone harness port")
    p.add_argument("--listen", default="127.0.0.1:0")
    p.add_argument("--token-file")
    p.set_defaults(fn=cmd_devtools_bridge)

    pio = sub.add_parser("pioneer", help="pioneer a route interactively, one verified step at a time")
    pio_sub = pio.add_subparsers(dest="pioneer_cmd", required=True)

    p = pio_sub.add_parser("init", help="create a new route file")
    target_arg(p, required=True)
    p.add_argument("--out", required=True, help="route TOML to create")
    p.add_argument("--name", help="scenario name; defaults to the file stem")
    p.add_argument("--authored-barks", help="JSON list of dialog entry ints, e.g. [37,48]")
    p.add_argument("--force", action="store_true", help="overwrite an existing route file")
    p.set_defaults(fn=cmd_pioneer_init)

    p = pio_sub.add_parser("step", help="execute one step body live and hold it pending")
    target_arg(p)
    p.add_argument("--out", required=True, help="route TOML being pioneered")
    p.add_argument("step", help='step body as JSON, e.g. \'{"do":"lua","code":"..."}\'')
    p.set_defaults(fn=cmd_pioneer_step)

    p = pio_sub.add_parser("commit", help="append the pending step to the route file")
    p.add_argument("--out", required=True)
    p.add_argument("--force", action="store_true",
                   help="commit even though the pending step's last run failed")
    p.set_defaults(fn=cmd_pioneer_commit)

    p = pio_sub.add_parser("discard", help="drop pending metadata only; does not undo live game changes")
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_pioneer_discard)

    p = pio_sub.add_parser("status", help="show the pending step, playback owner and live engine state")
    target_arg(p)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_pioneer_status)

    p = pio_sub.add_parser("attach", help="start the one attached playback owner for a route")
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_pioneer_attach)

    for name, text in (("play", "replay committed steps at the route speed"),
                       ("fastforward", "replay committed steps at a chosen configured multiplier")):
        p = pio_sub.add_parser(name, help=text)
        p.add_argument("--out", required=True)
        p.add_argument("--until", type=int, help="last committed step to run (default: the end)")
        start = p.add_mutually_exclusive_group()
        start.add_argument("--verify-current", help="Lua predicate that must return true for the current state")
        start.add_argument("--restart", action="store_true",
                           help="start over from the route's initial native load step")
        if name == "fastforward":
            p.add_argument("--speed", type=float, default=4.0,
                           help="configured multiplier in (0,16]; default 4")
        p.add_argument("--no-wait", action="store_true", help="return once the owner accepts the job")
        p.add_argument("--timeout", type=float, default=600.0,
                       help="seconds to poll status; the job is never re-sent")
        p.set_defaults(fn=cmd_pioneer_play)

    p = pio_sub.add_parser("stop", help="stop execution and detach the owner; does not pause the game")
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_pioneer_stop)

    p = pio_sub.add_parser("reclaim", help="recover after a killed owner: clear its descriptor and "
                                           "restore or report the recorded prior speed")
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_pioneer_reclaim)

    return ap


def main(argv: Optional[list] = None) -> int:
    ap = build_parser()
    a = ap.parse_args(argv)
    try:
        return int(a.fn(a))
    except SystemExit as e:
        if isinstance(e.code, str):
            print(e.code, file=sys.stderr)
            return 3
        raise
    except (KeyError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 3
    except (OSError, ChannelError, PB.PlaybackError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

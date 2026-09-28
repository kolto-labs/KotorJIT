#!/usr/bin/env python3
"""Record route work and require strategy review when verified progress stalls."""

import argparse
import fcntl
import json
import os
import tempfile
import time
from pathlib import Path

PATH = Path(os.environ.get("KPHARNESS_PROGRESS", Path(__file__).parents[1] / ".mission" / "route-progress.json"))
STRATEGY_REVIEW_SECONDS = 15 * 60
PIVOTS = ("resource", "instrument", "control_plane", "independent_segment")
WORK_KINDS = ("route_composition", "blocker_investigation")


def load():
    return json.loads(PATH.read_text())


def save(data):
    fd, name = tempfile.mkstemp(dir=PATH.parent, prefix=".route-progress.")
    try:
        with os.fdopen(fd, "w") as out:
            json.dump(data, out, indent=2)
            out.write("\n")
        os.replace(name, PATH)
    finally:
        Path(name).unlink(missing_ok=True)


def frontier(data, route, gate):
    try:
        return next(x for x in data["routes"][route]["frontiers"] if x["id"] == gate)
    except (KeyError, StopIteration):
        raise SystemExit(f"unknown route/gate: {route}/{gate}")


def continuous_frontiers(route):
    # Legacy evidence has no continuous-start claim. Row order is presentation,
    # not an established dependency chain (active mods can change route gates).
    return [row["id"] for row in route["frontiers"]
            if row["status"] == "reproduced" and row.get("proof_scope", "checkpoint") == "continuous"]


def reproduced(data, route):
    return len(continuous_frontiers(data["routes"][route]))


def refresh_verified(route):
    reproduced_rows = continuous_frontiers(route)
    route["verified_frontier"] = reproduced_rows[-1] if reproduced_rows else None


def verify_continuous_receipt(path, route, covered):
    """Validate the run verifier's claims, never promote based on CLI prose."""
    try:
        receipt = json.loads(Path(path).read_text())
    except (OSError, UnicodeError, ValueError) as exc:
        raise SystemExit(f"continuous proof requires a readable JSON receipt: {exc}")
    if not isinstance(receipt, dict):
        raise SystemExit("continuous proof receipt must be a JSON object")
    if receipt.get("schema") != "kpharness.route-proof.v1" or receipt.get("route") != route:
        raise SystemExit("continuous proof receipt schema or route does not match")
    start = receipt.get("start")
    if (receipt.get("proof_scope") != "continuous" or not isinstance(start, dict)
            or start.get("kind") != "new_game" or start.get("verified") is not True
            or receipt.get("result") != "pass"):
        raise SystemExit("continuous proof requires a verified new-game start, continuous scope, and pass result")
    predicates = receipt.get("terminal_predicates")
    if not isinstance(predicates, dict) or any(predicates.get(gate) is not True for gate in covered):
        raise SystemExit("continuous proof must pass every covered terminal predicate")


def control_state(data, route, now=None):
    now = int(time.time()) if now is None else now
    experiments = [x for x in data["experiments"] if x["route"] == route]
    current = set(continuous_frontiers(data["routes"][route]))
    # A subsequently contradicted receipt cannot restart the progress clock.
    advances = [i for i, x in enumerate(experiments)
                if x.get("finished_at") is not None and x.get("frontier_advanced")
                and x.get("outcome") == "reproduced" and x.get("proof_scope") == "continuous"
                and any(gate in current for gate in x.get("covers", [x["gate"]]))]
    last = advances[-1] if advances else None
    remaining = experiments[last + 1:] if last is not None else experiments
    zero_delta = sum(x.get("finished_at") is not None for x in remaining)
    anchor = (experiments[last]["finished_at"] if last is not None
              else experiments[0]["started_at"] if experiments else None)
    elapsed = max(0, now - anchor) if anchor is not None else 0
    open_ages = [max(0, now - x["started_at"]) for x in experiments if x.get("finished_at") is None]
    overdue = [x for x in experiments if x.get("finished_at") is None
               and x.get("deadline_at") is not None and now >= x["deadline_at"]]
    reasons = []
    if zero_delta >= 2:
        reasons.append("two_or_more_consecutive_zero_delta_experiments")
    if anchor is not None and elapsed >= STRATEGY_REVIEW_SECONDS:
        reasons.append("fifteen_minutes_without_verified_frontier_advance")
    return {
        "open_experiment_age_seconds": max(open_ages) if open_ages else None,
        "open_experiment_overdue": bool(overdue),
        "minutes_since_last_frontier_advance": round(elapsed / 60, 2) if anchor is not None else None,
        "progress_clock_basis": "last_frontier_advance" if last is not None else "first_experiment" if experiments else None,
        "consecutive_zero_delta_count": zero_delta,
        "needs_strategy_review": bool(reasons),
        "strategy_review_reasons": reasons,
    }


def begin(args):
    data = load()
    row = frontier(data, args.route, args.gate)
    route = data["routes"][args.route]
    if any(x.get("finished_at") is None for x in data["experiments"]):
        raise SystemExit("finish the open experiment first")
    if args.gate != route.get("current_gate"):
        raise SystemExit(f"experiment must target current gate {route.get('current_gate')!r}, not {args.gate!r}")
    if args.deadline_seconds <= 0:
        raise SystemExit("--deadline-seconds must be positive")
    if args.execution_mode != "inline":
        raise SystemExit("route work must start as an inline reactive experiment; persist a scenario only after the segment passes")
    if not args.route_milestone.strip():
        raise SystemExit("route work requires --route-milestone naming the next measurable route state")
    if not args.uses_proven:
        raise SystemExit("route work requires --uses-proven for the already verified primitives composed in this run")
    if args.work_kind == "blocker_investigation" and not args.unblocks_action.strip():
        raise SystemExit("blocker investigation requires --unblocks-action naming the current-gate action it returns to")
    route_work = [x for x in data["experiments"] if x["route"] == args.route]
    prior = [x for x in route_work if x["gate"] == args.gate and not x.get("frontier_advanced")]
    zero_delta = [x for x in prior if x.get("finished_at") is not None]
    if len(zero_delta) >= 2 and args.pivot not in PIVOTS:
        raise SystemExit("two zero-delta attempts on this gate require --pivot: " + ", ".join(PIVOTS))
    review = control_state(data, args.route)
    if review["needs_strategy_review"] and not all((args.eliminated, args.evidence, args.changed, args.prediction)):
        raise SystemExit("stalled route requires --eliminated, --evidence, --changed, and --prediction")
    if review["needs_strategy_review"]:
        strategy = args.strategy_review.strip()
        previous = next((x["strategy_review"].strip() for x in reversed(route_work) if x.get("strategy_review")), "")
        if not strategy or strategy == previous:
            raise SystemExit("stalled route requires a new --strategy-review: explain the bottleneck, changed strategy, and bounded next proof")
    signature = (args.action, args.prediction, args.eliminated, args.evidence, args.changed)
    if prior and signature == tuple(prior[-1].get(k, "") for k in ("action", "prediction", "eliminated_hypothesis", "new_evidence", "changed")):
        raise SystemExit("unchanged retry justification rejected")
    item = {
        "id": f"{int(time.time())}-{args.route}-{args.gate}",
        "route": args.route, "gate": args.gate,
        "started_at": int(time.time()), "finished_at": None,
        "reproduced_before": reproduced(data, args.route),
        "action": args.action, "prediction": args.prediction,
        "active_transition": args.active_transition,
        "precondition": args.precondition, "postcondition": args.postcondition,
        "work_kind": args.work_kind,
        "execution_mode": args.execution_mode,
        "route_milestone": args.route_milestone.strip(),
        "uses_proven": args.uses_proven,
        "unblocks_action": args.unblocks_action.strip(),
        "deadline_seconds": args.deadline_seconds,
        "deadline_at": int(time.time()) + args.deadline_seconds,
        "eliminated_hypothesis": args.eliminated,
        "new_evidence": args.evidence, "changed": args.changed,
        "pivot": args.pivot,
        "fresh_boot": args.fresh_boot,
        "strategy_review": args.strategy_review.strip(),
        "outcome": None
    }
    data["experiments"].append(item)
    row["attempts"] = (row.get("attempts") or 0) + 1
    save(data)
    print(item["id"])


def finish(args):
    data = load()
    try:
        item = next(x for x in reversed(data["experiments"]) if x["id"] == args.id)
    except StopIteration:
        raise SystemExit(f"unknown experiment: {args.id}")
    if item["finished_at"] is not None:
        raise SystemExit("experiment already finished")
    row = frontier(data, item["route"], item["gate"])
    route = data["routes"][item["route"]]
    if args.covers and (args.outcome != "reproduced" or args.proof_scope != "continuous"):
        raise SystemExit("--covers requires a reproduced continuous proof")
    if args.invalidates and args.outcome != "contradicted":
        raise SystemExit("--invalidates requires a contradicted outcome")
    invalidated = [frontier(data, item["route"], gate) for gate in args.invalidates]
    if any(x["status"] != "reproduced" for x in invalidated):
        raise SystemExit("cannot invalidate a non-reproduced gate")
    if args.outcome == "reproduced":
        if not args.receipt or not Path(args.receipt).is_file():
            raise SystemExit("reproduced requires an existing receipt file")
        covered = list(args.covers)
        if item["gate"] not in covered:
            covered.append(item["gate"])
        promoted = [frontier(data, item["route"], gate) for gate in covered]
        if len(covered) != len(set(covered)):
            raise SystemExit("--covers must not repeat a gate")
        if args.proof_scope == "continuous":
            verify_continuous_receipt(args.receipt, item["route"], covered)
        for covered_row in promoted:
            # A checkpoint replay does not revoke an earlier continuous proof.
            if args.proof_scope == "checkpoint" and covered_row["status"] == "reproduced" and covered_row.get("proof_scope") == "continuous":
                continue
            covered_row.update(status="reproduced", receipt=args.receipt, proof_scope=args.proof_scope)
        refresh_verified(route)
    elif args.outcome == "contradicted":
        row["status"] = "contradicted"
        for invalidated_row in invalidated:
            invalidated_row["status"] = "contradicted"
            invalidated_row["receipt"] = args.receipt
        refresh_verified(route)
        if args.invalidates:
            route["current_gate"] = args.invalidates[0]
    elif args.outcome == "observed" and row["status"] == "unattempted":
        row["status"] = "observed"
    item.update(finished_at=int(time.time()), outcome=args.outcome,
                receipt=args.receipt, promotion=args.promotion,
                invalidates=args.invalidates,
                proof_scope=args.proof_scope if args.outcome == "reproduced" else None,
                covers=covered if args.outcome == "reproduced" else [],
                lineage_transition_advanced=args.lineage_transition_advanced,
                live_seconds=int(time.time()) - item["started_at"])
    item["elapsed_seconds"] = item["live_seconds"]  # legacy alias also includes enabling work
    item["reproduced_after"] = reproduced(data, item["route"])
    item["frontier_advanced"] = item["reproduced_after"] > item["reproduced_before"]
    save(data)
    report = {k: item[k] for k in ("reproduced_before", "reproduced_after", "frontier_advanced", "elapsed_seconds", "live_seconds", "gate")}
    report.update(next_gate=route.get("current_gate"), **control_state(data, item["route"]))
    print(json.dumps(report, sort_keys=True))


def status(args):
    data = load()
    failed = False
    for name, route in data["routes"].items():
        rows = route["frontiers"]
        continuous = continuous_frontiers(route)
        experiments = [x for x in data["experiments"] if x["route"] == name and x.get("finished_at")]
        promotions = [x for x in experiments if x.get("promotion") in ("pass", "fail")]
        report = {"route": name, "reproduced": reproduced(data, name), "total": len(rows),
                          "checkpoint_reproduced": sum(x["status"] == "reproduced" and x["id"] not in continuous for x in rows),
                          "acceptance_complete": all(gate in continuous for gate in route["required_gates"]) if route.get("required_gates") else None,
                          "fresh_boots": sum(bool(x.get("fresh_boot")) for x in experiments),
                          "frontier_advances": reproduced(data, name),
                          "historical_frontier_advances": sum(bool(x.get("frontier_advanced")) for x in experiments),
                          "revocations": sum(len(x.get("invalidates", [])) for x in experiments),
                          "promotion_pass_rate": None if not promotions else sum(x["promotion"] == "pass" for x in promotions) / len(promotions),
                          "verified_frontier": continuous[-1] if continuous else None,
                  "next_gate": route.get("current_gate"),
                  **control_state(data, name)}
        print(json.dumps(report, sort_keys=True))
        failed = failed or report["open_experiment_overdue"]
    if args.enforce and failed:
        raise SystemExit(2)


def select(args):
    data = load()
    frontier(data, args.route, args.gate)
    data["routes"][args.route]["current_gate"] = args.gate
    data["routes"][args.route]["current_gate_reason"] = args.reason
    save(data)


def self_check(_args):
    """Exercise admission and promotion in memory; never writes the ledger."""
    import contextlib
    import copy
    import io
    from types import SimpleNamespace
    from unittest.mock import patch

    working = [{"routes": {"r": {"current_gate": "b", "frontiers": [
        {"id": "a", "status": "reproduced"}, {"id": "b", "status": "reproduced"}]}},
        "experiments": [{"id": str(i), "route": "r", "gate": gate,
                         "started_at": 100 * i, "finished_at": 100 * i + 10,
                         "outcome": "observed", "frontier_advanced": False}
                        for i, gate in enumerate(("a", "b"), 1)]}]
    assert reproduced(working[0], "r") == 0  # legacy evidence is checkpoint-only
    assert continuous_frontiers({"frontiers": [
        {"id": "old_mod_gate", "status": "contradicted"},
        {"id": "proven", "status": "reproduced", "proof_scope": "continuous"}]}) == ["proven"]
    state = control_state(working[0], "r", now=1100)
    assert state["needs_strategy_review"] and state["consecutive_zero_delta_count"] == 2
    opened = copy.deepcopy(working[0])
    opened["experiments"].append({"route": "r", "gate": "b", "started_at": 300,
                                  "deadline_at": 900, "finished_at": None})
    assert control_state(opened, "r", now=1100)["open_experiment_age_seconds"] == 800
    assert control_state(opened, "r", now=1100)["open_experiment_overdue"]
    start = SimpleNamespace(route="r", gate="b", action="native route action",
                            prediction="terminal state", eliminated="old path",
                            evidence="native caller", changed="retail dispatch",
                            fresh_boot=False, strategy_review="",
                            pivot="",
                            active_transition="door_open", precondition="door locked",
                            postcondition="door open", deadline_seconds=900,
                            work_kind="route_composition", execution_mode="inline",
                            route_milestone="door_open", uses_proven=["move", "door_use"],
                            unblocks_action="")
    with patch.dict(globals(), {"load": lambda: copy.deepcopy(working[0]),
                               "save": lambda value: working.__setitem__(0, copy.deepcopy(value))}), \
            patch("time.time", return_value=2000), contextlib.redirect_stdout(io.StringIO()):
        try:
            begin(start)
        except SystemExit as exc:
            assert "--strategy-review" in str(exc)
        else:
            raise AssertionError("stalled route admitted without strategy review")
        start.strategy_review = "Replace guessed script replay with the retail action; prove both predicates within 15 minutes."
        start.pivot = "control_plane"
        start.gate = "a"
        try:
            begin(start)
        except SystemExit as exc:
            assert "current gate" in str(exc)
        else:
            raise AssertionError("non-current gate admitted")
        start.gate = "b"
        start.execution_mode = "static_scenario"
        try:
            begin(start)
        except SystemExit as exc:
            assert "inline reactive" in str(exc)
        else:
            raise AssertionError("static scenario admitted before inline segment")
        start.execution_mode = "inline"
        start.uses_proven = []
        try:
            begin(start)
        except SystemExit as exc:
            assert "--uses-proven" in str(exc)
        else:
            raise AssertionError("uncomposed primitive work admitted")
        start.uses_proven = ["move", "door_use"]
        begin(start)
        completed = SimpleNamespace(id=working[0]["experiments"][-1]["id"], outcome="reproduced",
                                    receipt=__file__, invalidates=[], promotion="not_attempted",
                                    proof_scope="continuous", covers=["a", "b"],
                                    lineage_transition_advanced=True)
        valid_receipt = {"schema": "kpharness.route-proof.v1", "route": "r",
                         "proof_scope": "continuous", "start": {"kind": "new_game", "verified": True},
                         "result": "pass", "terminal_predicates": {"a": True, "b": True}}
        before = copy.deepcopy(working[0])
        with tempfile.TemporaryDirectory(prefix="harness-progress-check-") as directory:
            receipt_path = Path(directory) / "receipt.json"
            completed.receipt = str(receipt_path)
            invalid = ["not JSON", "[]", json.dumps({}),
                       *(json.dumps(dict(valid_receipt, **change)) for change in (
                           {"route": "wrong"}, {"proof_scope": "checkpoint"},
                           {"start": {"kind": "checkpoint", "verified": True}},
                           {"start": {"kind": "new_game", "verified": 1}},
                           {"result": "fail"}, {"terminal_predicates": {"a": True}},
                           {"terminal_predicates": {"a": True, "b": 1}}))]
            for payload in invalid:
                receipt_path.write_text(payload)
                try:
                    finish(completed)
                except SystemExit:
                    assert working[0] == before, "invalid receipt mutated ledger"
                else:
                    raise AssertionError("invalid continuous receipt accepted")
            # Existing non-JSON receipts remain usable as checkpoint evidence.
            receipt_path.write_text("legacy checkpoint receipt")
            completed.proof_scope, completed.covers = "checkpoint", []
            finish(completed)
            assert reproduced(working[0], "r") == 0
            working[0] = copy.deepcopy(before)
            completed.proof_scope, completed.covers = "continuous", ["a", "b"]
            receipt_path.write_text(json.dumps(valid_receipt))
            finish(completed)
        assert reproduced(working[0], "r") == 2
        assert not control_state(working[0], "r", now=2001)["needs_strategy_review"]
        # Retracting both predicates also retracts that receipt's clock reset.
        for row in working[0]["routes"]["r"]["frontiers"]:
            row["status"] = "contradicted"
        try:
            begin(start)
        except SystemExit as exc:
            assert "--strategy-review" in str(exc)
        else:
            raise AssertionError("repeated strategy review admitted after revocation")
    print("harness_progress self-check: PASS")


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(required=True)
    start = sub.add_parser("begin")
    start.add_argument("route"); start.add_argument("gate"); start.add_argument("--action", required=True)
    start.add_argument("--prediction", required=True); start.add_argument("--eliminated", default="")
    start.add_argument("--evidence", default=""); start.add_argument("--changed", default="")
    start.add_argument("--active-transition", required=True)
    start.add_argument("--precondition", required=True); start.add_argument("--postcondition", required=True)
    start.add_argument("--work-kind", choices=WORK_KINDS, required=True)
    start.add_argument("--execution-mode", choices=("inline", "static_scenario"), required=True)
    start.add_argument("--route-milestone", required=True)
    start.add_argument("--uses-proven", action="append", default=[])
    start.add_argument("--unblocks-action", default="")
    start.add_argument("--deadline-seconds", type=int, default=STRATEGY_REVIEW_SECONDS)
    start.add_argument("--fresh-boot", action="store_true")
    start.add_argument("--strategy-review", default="")
    start.add_argument("--pivot", choices=PIVOTS,
                       help="required after two zero-delta attempts on this gate")
    start.set_defaults(func=begin)
    end = sub.add_parser("finish")
    end.add_argument("id"); end.add_argument("outcome", choices=("no_advance", "observed", "reproduced", "contradicted"))
    end.add_argument("--receipt")
    end.add_argument("--invalidates", action="append", default=[])
    end.add_argument("--proof-scope", choices=("checkpoint", "continuous"), default="checkpoint")
    end.add_argument("--covers", action="append", default=[])
    end.add_argument("--lineage-transition-advanced", action="store_true")
    end.add_argument("--promotion", choices=("not_attempted", "pass", "fail"), default="not_attempted")
    end.set_defaults(func=finish)
    choose = sub.add_parser("select"); choose.add_argument("route"); choose.add_argument("gate"); choose.add_argument("--reason", required=True); choose.set_defaults(func=select)
    report = sub.add_parser("status"); report.add_argument("--enforce", action="store_true"); report.set_defaults(func=status)
    sub.add_parser("self-check").set_defaults(func=self_check)
    args = parser.parse_args()
    if args.func is self_check:
        self_check(args)
        return
    PATH.parent.mkdir(parents=True, exist_ok=True)
    with (PATH.parent / (PATH.name + ".lock")).open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        args.func(args)


if __name__ == "__main__":
    main()

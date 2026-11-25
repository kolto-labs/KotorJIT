"""JSON and Markdown matrix reporting helpers."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .schema import ProbeResult


def summarize_results(results: Iterable[ProbeResult]) -> Dict[str, Any]:
    by_status = Counter()
    by_universe: Dict[str, Counter] = defaultdict(Counter)
    by_kind: Dict[str, Counter] = defaultdict(Counter)
    invariant_failures = 0

    all_res = list(results)
    for r in all_res:
        by_status[r.status] += 1
        by_universe[r.universe_id][r.status] += 1
        by_kind[r.kind][r.status] += 1
        if not r.invariants_ok:
            invariant_failures += 1

    return {
        "total": len(all_res),
        "by_status": dict(by_status),
        "by_universe": {u: dict(c) for u, c in by_universe.items()},
        "by_kind": {k: dict(c) for k, c in by_kind.items()},
        "invariant_failures": invariant_failures,
    }


def write_reports(
    results: List[ProbeResult],
    json_path: Path,
    md_path: Path,
    title: str = "State Matrix Verification Report",
    metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    summary = summarize_results(results)
    payload = {
        "title": title,
        "metadata": metadata or {},
        "summary": summary,
        "results": [r.to_dict() for r in results],
    }
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    lines = [
        f"# {title}",
        "",
        f"- **Total probes**: {summary['total']}",
        f"- **Status counts**: `{summary['by_status']}`",
        f"- **Invariant failures**: {summary['invariant_failures']}",
        "",
        "## Per-Universe Breakdown",
        "",
        "| Universe | Passed | Failed | Crashed | Skipped |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for u, counts in sorted(summary["by_universe"].items()):
        lines.append(
            f"| `{u}` | {counts.get('passed', 0)} | {counts.get('failed', 0)} | "
            f"{counts.get('crashed', 0)} | {counts.get('skipped', 0)} |"
        )

    failures = [r for r in results if r.status in ("failed", "crashed") or not r.invariants_ok]
    if failures:
        lines.extend(["", "## Failures & Invariant Violations", ""])
        for f in failures[:100]:
            lines.append(
                f"- `{f.case_id}` (`{f.status}`): {f.reason or 'unspecified failure'}"
            )

    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary

"""Validate saved two-stage Q11 outputs independently from graph staging CSVs."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from query_specs import PROJECT_ROOT, get_spec, load_parameter_schedule


def latest_formal(scale: str) -> Path:
    root = PROJECT_ROOT / "results" / "query_benchmarks_final" / "two-stage" / f"sf{scale}" / "graph" / "q11"
    candidates = []
    for path in root.iterdir():
        manifest = path / "manifest.json"
        if manifest.is_file() and json.loads(manifest.read_text(encoding="utf-8")).get("formal"):
            candidates.append(path)
    if not candidates:
        raise FileNotFoundError(f"No formal two-stage Q11 run under {root}")
    return sorted(candidates)[-1]


def mapping(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {row["from_id"]: row["to_id"] for row in csv.DictReader(handle)}


def compute(source: Path) -> tuple[dict[str, dict[str, float]], dict[str, int]]:
    nation_names: dict[str, str] = {}
    part_keys: dict[str, int] = {}
    with (source / "vertices" / "nation.csv").open(encoding="utf-8-sig", newline="") as handle:
        nation_names = {row["tg_nation_id"]: row["n_name"] for row in csv.DictReader(handle)}
    with (source / "vertices" / "part.csv").open(encoding="utf-8-sig", newline="") as handle:
        part_keys = {row["tg_part_id"]: int(row["p_partkey"]) for row in csv.DictReader(handle)}
    supplier_nation = mapping(source / "edges" / "supplier_nation.csv")
    ps_supplier = mapping(source / "edges" / "partsupp_supplier.csv")
    ps_part = mapping(source / "edges" / "partsupp_part.csv")
    totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    with (source / "vertices" / "partsupp.csv").open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            ps_id = row["tg_partsupp_id"]
            nation = nation_names[supplier_nation[ps_supplier[ps_id]]]
            totals[nation][ps_part[ps_id]] += float(row["ps_supplycost"]) * int(row["ps_availqty"])
    return totals, part_keys


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scale", choices=("0.01", "0.1", "1"), required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path)
    args = parser.parse_args()
    run_dir = args.run_dir or latest_formal(args.scale)
    schedule = load_parameter_schedule(get_spec(11), args.scale)
    totals, part_keys = compute(args.source_dir)
    checks = []
    for index, row in enumerate(schedule, 1):
        values = totals[row["selected_nation"]]
        threshold = sum(values.values()) * float(row["fraction"])
        expected = [
            {"partkey": part_keys[part_id], "value": value}
            for part_id, value in sorted(values.items(), key=lambda item: (-item[1], part_keys[item[0]]))
            if value > threshold
        ]
        with (run_dir / "final_outputs" / f"run_{index:02d}.csv").open(encoding="utf-8-sig", newline="") as handle:
            actual = list(csv.DictReader(handle))
        if len(actual) != len(expected):
            raise AssertionError(f"run {index}: rows {len(actual)} != {len(expected)}")
        for left, right in zip(actual, expected):
            if int(left["partkey"]) != right["partkey"] or not math.isclose(float(left["value"]), right["value"], rel_tol=1e-7, abs_tol=1e-4):
                raise AssertionError(f"run {index}: {left} != {right}")
        checks.append({"run": index, "nation": row["selected_nation"], "rows": len(actual), "status": "PASS"})
    evidence = {
        "query": "Q11",
        "variant": "two-stage",
        "scale_factor": args.scale,
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "source_dir": str(args.source_dir.resolve()),
        "run_dir": str(run_dir.resolve()),
        "runs_passed": len(checks),
        "status": "PASS",
        "checks": checks,
    }
    path = run_dir / "independent_correctness.json"
    path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(f"Q11 two-stage: PASS ({len(checks)}/{len(schedule)} parameter sets)")
    print(path)


if __name__ == "__main__":
    main()

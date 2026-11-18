"""Summarise dispersion in the retained 20-run SF 1 query series."""

from __future__ import annotations

import csv
import math
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"
MASTER = RESULTS / "project_final_master_summary.csv"
OUTPUT_CSV = RESULTS / "query_timing_stability_sf1.csv"
OUTPUT_MD = RESULTS / "query_timing_stability_sf1.md"


def first_row(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return next(csv.DictReader(handle))


def quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def query_number(row: dict[str, str], path: Path) -> int | None:
    label = row.get("query", "")
    digits = "".join(character for character in label if character.isdigit())
    if digits:
        return int(digits)
    for part in path.parts:
        if part.lower().startswith("q") and part[1:].isdigit():
            return int(part[1:])
    return None


def scale_factor(row: dict[str, str], path: Path) -> str | None:
    if row.get("scale_factor"):
        return row["scale_factor"]
    for part in path.parts:
        if part.startswith("sf"):
            candidate = part[2:]
            if candidate in {"0.01", "0.1", "1"}:
                return candidate
    return None


def summary_mean(row: dict[str, str]) -> float | None:
    for field in ("mean_ms", "database_mean_ms"):
        if row.get(field):
            return float(row[field])
    return None


def main() -> int:
    with MASTER.open(encoding="utf-8-sig", newline="") as handle:
        master_rows = [
            row for row in csv.DictReader(handle) if row["module"] == "Queries"
        ]
    targets = {
        int(row["item"].removeprefix("Q")): float(row["sf1"])
        for row in master_rows
    }

    candidates: dict[int, list[tuple[float, float, Path]]] = {}
    for summary_path in RESULTS.rglob("summary.csv"):
        if not any(part.startswith("query_benchmarks") for part in summary_path.parts):
            continue
        try:
            row = first_row(summary_path)
            number = query_number(row, summary_path)
            scale = scale_factor(row, summary_path)
            mean = summary_mean(row)
        except (OSError, StopIteration, ValueError):
            continue
        if number not in targets or scale != "1" or mean is None:
            continue
        difference = abs(mean - targets[number])
        if difference <= 0.051 and (summary_path.parent / "raw.csv").is_file():
            candidates.setdefault(number, []).append(
                (difference, -summary_path.stat().st_mtime, summary_path)
            )

    output_rows: list[dict[str, object]] = []
    for number in range(1, 23):
        if number not in candidates:
            raise RuntimeError(f"No retained SF 1 raw series matches Q{number}")
        summary_path = min(candidates[number])[2]
        raw_path = summary_path.parent / "raw.csv"
        with raw_path.open(encoding="utf-8-sig", newline="") as handle:
            raw_rows = list(csv.DictReader(handle))
        field = "elapsed_ms" if "elapsed_ms" in raw_rows[0] else "database_elapsed_ms"
        values = [float(row[field]) for row in raw_rows]
        if len(values) != 20:
            raise RuntimeError(f"Q{number} has {len(values)} observations, expected 20")
        mean = statistics.fmean(values)
        standard_deviation = statistics.stdev(values)
        q1 = quantile(values, 0.25)
        q3 = quantile(values, 0.75)
        output_rows.append(
            {
                "query": f"Q{number}",
                "n": len(values),
                "formal_trimmed_mean_ms": targets[number],
                "raw_mean_ms": round(mean, 3),
                "median_ms": round(statistics.median(values), 3),
                "iqr_ms": round(q3 - q1, 3),
                "sample_sd_ms": round(standard_deviation, 3),
                "cv_percent": round(100 * standard_deviation / mean, 2),
                "min_ms": min(values),
                "max_ms": max(values),
                "raw_source": str(raw_path.relative_to(ROOT)),
            }
        )

    fields = list(output_rows[0])
    with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output_rows)

    cvs = [float(row["cv_percent"]) for row in output_rows]
    highest = sorted(output_rows, key=lambda row: float(row["cv_percent"]), reverse=True)[:5]
    lines = [
        "# SF 1 Query Timing Stability",
        "",
        "This is a descriptive secondary analysis of the retained 20 raw database-time",
        "observations for each formal Q1--Q22 SF 1 workload. It does not replace the",
        "pre-specified trimmed mean used for the primary results.",
        "",
        f"- Queries analysed: {len(output_rows)}",
        f"- Median coefficient of variation: {statistics.median(cvs):.2f}%",
        f"- Minimum coefficient of variation: {min(cvs):.2f}%",
        f"- Maximum coefficient of variation: {max(cvs):.2f}%",
        "",
        "## Five largest coefficients of variation",
        "",
        "| Query | CV | Median (ms) | IQR (ms) |",
        "|---|---:|---:|---:|",
    ]
    for row in highest:
        lines.append(
            f"| {row['query']} | {row['cv_percent']:.2f}% | "
            f"{row['median_ms']} | {row['iqr_ms']} |"
        )
    lines.extend(
        [
            "",
            "CV is the sample standard deviation divided by the untrimmed raw mean. Q11 and",
            "Q22 use the sum of their two database-stage elapsed times, consistent with the",
            "formal database metric. Client-side finalisation remains excluded.",
            "",
        ]
    )
    OUTPUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(OUTPUT_CSV)
    print(OUTPUT_MD)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

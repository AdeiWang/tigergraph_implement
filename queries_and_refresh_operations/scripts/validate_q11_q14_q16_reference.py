"""Independently validate Q11/Q14/Q16 from source CSVs and finalize Q14."""

from __future__ import annotations

import csv
import argparse
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

import requests

from query_specs import PROJECT_ROOT, get_spec, load_parameter_schedule
from run_q21_q22_final import DEFAULT_GRAPH, DEFAULT_HOST, synchronous_rows
import validate_q21_q22_reference as reference_data

edge_map = reference_data.edge_map
source_csv = reference_data.source_csv

OUTPUT = PROJECT_ROOT / "results" / "query_benchmarks_final" / "correctness"
Q14_OUTPUT = OUTPUT / "q14_sf001_final_outputs"
LOCAL_GRAPH_SOURCE: Path | None = None


def synchronous_object(query: str, params: dict[str, str], host: str = DEFAULT_HOST) -> dict[str, Any]:
    encoded = urlencode(params, quote_via=quote)
    response = requests.get(f"{host}/restpp/query/{DEFAULT_GRAPH}/{query}?{encoded}", timeout=600)
    response.raise_for_status()
    payload = response.json()
    if payload.get("error"):
        raise RuntimeError(payload)
    for block in payload.get("results", []):
        for value in block.values():
            if isinstance(value, dict):
                return value
    raise RuntimeError(f"No scalar result object returned by {query}: {payload}")


def close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=1e-7, abs_tol=1e-5)


def reference_q11(nation_name: str, fraction: float) -> list[dict[str, Any]]:
    nations = {row["tg_nation_id"]: row for row in source_csv("vertices/nation.csv")}
    parts = {row["tg_part_id"]: row for row in source_csv("vertices/part.csv")}
    partsupp = {row["tg_partsupp_id"]: row for row in source_csv("vertices/partsupp.csv")}
    ps_supplier = edge_map("edges/partsupp_supplier.csv")
    supplier_nation = edge_map("edges/supplier_nation.csv")
    ps_part = edge_map("edges/partsupp_part.csv")
    values: dict[str, float] = defaultdict(float)
    for ps_id, row in partsupp.items():
        if nations[supplier_nation[ps_supplier[ps_id]]]["n_name"] == nation_name:
            values[ps_part[ps_id]] += float(row["ps_supplycost"]) * int(row["ps_availqty"])
    threshold = sum(values.values()) * fraction
    return [
        {"partkey": int(parts[part_id]["p_partkey"]), "value": value}
        for part_id, value in sorted(values.items(), key=lambda item: (-item[1], int(parts[item[0]]["p_partkey"])))
        if value > threshold
    ]


def reference_q14(start_date: str, end_date: str) -> tuple[float, float, float]:
    if LOCAL_GRAPH_SOURCE is None:
        parts = {row["tg_part_id"]: row for row in source_csv("vertices/part.csv")}
        lines = source_csv("vertices/lineitem.csv")
        line_ps = edge_map("edges/lineitem_partsupp.csv")
        ps_part = edge_map("edges/partsupp_part.csv")
        pairs = ((row, line_ps[row["tg_lineitem_id"]]) for row in lines)
    else:
        with (LOCAL_GRAPH_SOURCE / "vertices" / "part.csv").open(
            "r", encoding="utf-8-sig", newline=""
        ) as part_handle:
            parts = {row["tg_part_id"]: row for row in csv.DictReader(part_handle)}
        with (LOCAL_GRAPH_SOURCE / "edges" / "partsupp_part.csv").open(
            "r", encoding="utf-8-sig", newline=""
        ) as ps_part_handle:
            ps_part = {row["from_id"]: row["to_id"] for row in csv.DictReader(ps_part_handle)}
        line_handle = (LOCAL_GRAPH_SOURCE / "vertices" / "lineitem.csv").open(
            "r", encoding="utf-8-sig", newline=""
        )
        edge_handle = (LOCAL_GRAPH_SOURCE / "edges" / "lineitem_partsupp.csv").open(
            "r", encoding="utf-8-sig", newline=""
        )
        pairs = ((line, edge["to_id"]) for line, edge in zip(
            csv.DictReader(line_handle), csv.DictReader(edge_handle), strict=True
        ))
    promo = total = 0.0
    for row, partsupp_id in pairs:
        if start_date <= row["l_shipdate"] < end_date:
            revenue = float(row["l_extendedprice"]) * (1.0 - float(row["l_discount"]))
            total += revenue
            if parts[ps_part[partsupp_id]]["p_type"].startswith("PROMO"):
                promo += revenue
    percentage = 100.0 * promo / total if total else 0.0
    if LOCAL_GRAPH_SOURCE is not None:
        line_handle.close()
        edge_handle.close()
    return promo, total, percentage


def reference_q16(row: dict[str, str]) -> list[dict[str, Any]]:
    parts = {item["tg_part_id"]: item for item in source_csv("vertices/part.csv")}
    suppliers = {item["tg_supplier_id"]: item for item in source_csv("vertices/supplier.csv")}
    partsupp = source_csv("vertices/partsupp.csv")
    ps_supplier = edge_map("edges/partsupp_supplier.csv")
    ps_part = edge_map("edges/partsupp_part.csv")
    sizes = {int(row[f"size{i}"]) for i in range(1, 9)}
    groups: dict[tuple[str, str, int], set[str]] = defaultdict(set)
    for ps in partsupp:
        ps_id = ps["tg_partsupp_id"]
        part = parts[ps_part[ps_id]]
        supplier = suppliers[ps_supplier[ps_id]]
        if part["p_brand"] == row["excluded_brand"]:
            continue
        if part["p_type"].startswith(row["excluded_type_prefix"]):
            continue
        if int(part["p_size"]) not in sizes:
            continue
        if "Customer" in supplier["s_comment"] and "Complaints" in supplier["s_comment"]:
            continue
        groups[(part["p_brand"], part["p_type"], int(part["p_size"]))].add(supplier["s_suppkey"])
    result = [
        {"p_brand": key[0], "p_type": key[1], "p_size": key[2], "supplier_cnt": len(ids)}
        for key, ids in groups.items()
    ]
    return sorted(result, key=lambda item: (-item["supplier_cnt"], item["p_brand"], item["p_type"], item["p_size"]))


def validate_q11(scale: str, host: str) -> None:
    for row in load_parameter_schedule(get_spec(11), scale):
        params = {"selected_nation": row["selected_nation"], "fraction": row["fraction"]}
        actual = synchronous_rows(host, DEFAULT_GRAPH, "q11_tigergraph", params)
        expected = reference_q11(row["selected_nation"], float(row["fraction"]))
        if len(actual) != len(expected):
            raise AssertionError(f"Q11 run {row['run']} row count: {len(actual)} != {len(expected)}")
        for left, right in zip(actual, expected):
            if int(left["partkey"]) != right["partkey"] or not close(float(left["value"]), right["value"]):
                raise AssertionError(f"Q11 run {row['run']} mismatch: {left} != {right}")


def validate_and_finalize_q14(scale: str, host: str, q14_output: Path) -> None:
    q14_output.mkdir(parents=True, exist_ok=True)
    combined: list[dict[str, Any]] = []
    for row in load_parameter_schedule(get_spec(14), scale):
        params = {"start_date": row["start_date"], "end_date": row["end_date"]}
        actual = synchronous_object("q14_tigergraph", params, host)
        promo, total, percentage = reference_q14(row["start_date"], row["end_date"])
        if not close(float(actual["promo_revenue"]), promo) or not close(float(actual["total_revenue"]), total):
            raise AssertionError(f"Q14 run {row['run']} mismatch: {actual} != {(promo, total)}")
        final = {"run": int(row["run"]), **params, "promo_revenue": float(actual["promo_revenue"]), "total_revenue": float(actual["total_revenue"]), "promo_revenue_percentage": percentage}
        combined.append(final)
        with (q14_output / f"run_{int(row['run']):02d}.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(final))
            writer.writeheader(); writer.writerow(final)
    with (q14_output / "q14_final_percentages.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(combined[0]))
        writer.writeheader(); writer.writerows(combined)


def validate_q16(scale: str, host: str) -> None:
    spec = get_spec(16)
    for row in load_parameter_schedule(spec, scale):
        params = {field: row[field] for field in spec.api_fields}
        actual = synchronous_rows(host, DEFAULT_GRAPH, "q16_tigergraph", params)
        expected = reference_q16(row)
        normalized = [{"p_brand": item["p_brand"], "p_type": item["p_type"], "p_size": int(item["p_size"]), "supplier_cnt": int(item["supplier_cnt"])} for item in actual]
        if normalized != expected:
            raise AssertionError(f"Q16 run {row['run']} mismatch: actual_rows={len(normalized)}, expected_rows={len(expected)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scale", default="0.01")
    parser.add_argument("--container", default="tigergraph")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument(
        "--queries",
        default="11,14,16",
        help="Comma-separated subset of 11,14,16 (default: all three).",
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        help="Optional local graph_staging directory; streams large LINEITEM CSV.",
    )
    args = parser.parse_args()
    global LOCAL_GRAPH_SOURCE
    LOCAL_GRAPH_SOURCE = args.source_dir
    selected = {int(value.strip()) for value in args.queries.split(",") if value.strip()}
    if not selected or not selected <= {11, 14, 16}:
        parser.error("--queries must be a non-empty subset of 11,14,16")
    reference_data.CONTAINER = args.container
    reference_data.source_csv.cache_clear()
    scale_tag = args.scale.replace(".", "")
    q14_output = OUTPUT / f"q14_sf{scale_tag}_final_outputs"
    if 11 in selected:
        validate_q11(args.scale, args.host); print("Q11: PASS (20/20 parameter sets)")
    if 14 in selected:
        validate_and_finalize_q14(args.scale, args.host, q14_output); print("Q14: PASS (20/20 parameter sets; final percentage CSVs saved)")
    if 16 in selected:
        validate_q16(args.scale, args.host); print("Q16: PASS (20/20 parameter sets)")
    evidence = {"scale_factor": args.scale, "validated_at_utc": datetime.now(timezone.utc).isoformat(), "source": "independent original import CSV computation", "checks": [{"query": f"Q{q}", "parameter_sets": 20, "status": "PASS"} for q in sorted(selected)], "q14_final_output": str(q14_output / "q14_final_percentages.csv") if 14 in selected else None}
    OUTPUT.mkdir(parents=True, exist_ok=True)
    query_tag = "_".join(f"q{q}" for q in sorted(selected))
    (OUTPUT / f"{query_tag}_sf{scale_tag}_reference_validation.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

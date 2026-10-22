"""Validate final Q21/Q22 output against an independent computation from source CSVs."""

from __future__ import annotations

import csv
import argparse
import io
import json
import subprocess
from datetime import datetime, timezone
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

from run_q21_q22_final import (
    DEFAULT_GRAPH,
    DEFAULT_HOST,
    PROJECT_ROOT,
    Q22_NEO4J_COMPATIBLE_CODES,
    Q22_FIELDS,
    finalize_q21,
    finalize_q22,
    load_schedule,
    synchronous_rows,
)

CONTAINER = "tigergraph"
BASE = "/home/tigergraph/tpch_data/graph"


@lru_cache(maxsize=None)
def source_csv(relative: str) -> tuple[dict[str, str], ...]:
    completed = subprocess.run(
        ["docker", "exec", "-u", "tigergraph", CONTAINER, "cat", f"{BASE}/{relative}"],
        check=True,
        capture_output=True,
    )
    text = completed.stdout.decode("utf-8-sig")
    return tuple(csv.DictReader(io.StringIO(text)))


def edge_map(relative: str) -> dict[str, str]:
    return {row["from_id"]: row["to_id"] for row in source_csv(relative)}


def reference_q21(selected_nation: str, corrected: bool) -> list[dict[str, object]]:
    orders = {row["tg_orders_id"]: row for row in source_csv("vertices/orders.csv")}
    lines = {row["tg_lineitem_id"]: row for row in source_csv("vertices/lineitem.csv")}
    suppliers = {row["tg_supplier_id"]: row for row in source_csv("vertices/supplier.csv")}
    nations = {row["tg_nation_id"]: row for row in source_csv("vertices/nation.csv")}
    line_order = edge_map("edges/lineitem_orders.csv")
    line_ps = edge_map("edges/lineitem_partsupp.csv")
    ps_supplier = edge_map("edges/partsupp_supplier.csv")
    supplier_nation = edge_map("edges/supplier_nation.csv")
    order_lines: dict[str, list[str]] = defaultdict(list)
    for line_id, order_id in line_order.items():
        order_lines[order_id].append(line_id)

    counts: Counter[str] = Counter()
    for order_id, members in order_lines.items():
        if corrected and orders[order_id]["o_orderstatus"] != "F":
            continue
        supplier_by_line = {line_id: ps_supplier[line_ps[line_id]] for line_id in members}
        all_suppliers = set(supplier_by_line.values())
        late_suppliers = {
            supplier_by_line[line_id]
            for line_id in members
            if lines[line_id]["l_receiptdate"] > lines[line_id]["l_commitdate"]
        }
        for line_id in members:
            supplier_id = supplier_by_line[line_id]
            line = lines[line_id]
            nation = nations[supplier_nation[supplier_id]]["n_name"]
            if nation != selected_nation or line["l_receiptdate"] <= line["l_commitdate"]:
                continue
            if not (all_suppliers - {supplier_id}):
                continue
            if late_suppliers - {supplier_id}:
                continue
            counts[suppliers[supplier_id]["s_name"]] += 1
    return [
        {"supplier_name": name, "numwait": count}
        for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def reference_q22(codes: set[str]) -> list[dict[str, object]]:
    customers = source_csv("vertices/customer.csv")
    ordered_customer_ids = set(edge_map("edges/orders_customer.csv").values())
    selected = [row for row in customers if row["c_phone"][:2] in codes]
    positive = [float(row["c_acctbal"]) for row in selected if float(row["c_acctbal"]) > 0]
    average = sum(positive) / len(positive)
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in selected:
        if float(row["c_acctbal"]) > average and row["tg_customer_id"] not in ordered_customer_ids:
            grouped[row["c_phone"][:2]].append(float(row["c_acctbal"]))
    return [
        {"cntrycode": code, "numcust": len(values), "totalacctbal": f"{sum(values):.2f}"}
        for code, values in sorted(grouped.items())
    ]


def reference_q21_streaming_all(base: Path) -> dict[str, list[dict[str, object]]]:
    """Compute Neo4j-compatible Q21 for every nation with bounded memory."""
    def rows(relative: str):
        handle = (base / relative).open("r", encoding="utf-8-sig", newline="")
        return handle, csv.DictReader(handle)

    nation_handle, nation_rows = rows("vertices/nation.csv")
    nations = {row["tg_nation_id"]: row["n_name"] for row in nation_rows}
    nation_handle.close()
    sn_handle, sn_rows = rows("edges/supplier_nation.csv")
    supplier_nation = {row["from_id"]: nations[row["to_id"]] for row in sn_rows}
    sn_handle.close()
    supplier_handle, supplier_rows = rows("vertices/supplier.csv")
    supplier_names = {row["tg_supplier_id"]: row["s_name"] for row in supplier_rows}
    supplier_handle.close()
    ps_handle, ps_rows = rows("edges/partsupp_supplier.csv")
    ps_supplier = {row["from_id"]: row["to_id"] for row in ps_rows}
    ps_handle.close()

    line_handle, lines = rows("vertices/lineitem.csv")
    order_handle, order_edges = rows("edges/lineitem_orders.csv")
    line_ps_handle, line_ps_edges = rows("edges/lineitem_partsupp.csv")
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    current_order: str | None = None
    members: list[tuple[str, bool]] = []

    def finish_order() -> None:
        if not members:
            return
        all_suppliers = {supplier for supplier, _ in members}
        late_suppliers = {supplier for supplier, late in members if late}
        for supplier, late in members:
            if not late or not (all_suppliers - {supplier}) or (late_suppliers - {supplier}):
                continue
            counts[supplier_nation[supplier]][supplier_names[supplier]] += 1

    for line, order_edge, line_ps_edge in zip(lines, order_edges, line_ps_edges, strict=True):
        order_id = order_edge["to_id"]
        if current_order is not None and order_id != current_order:
            finish_order()
            members = []
        current_order = order_id
        supplier = ps_supplier[line_ps_edge["to_id"]]
        members.append((supplier, line["l_receiptdate"] > line["l_commitdate"]))
    finish_order()
    line_handle.close(); order_handle.close(); line_ps_handle.close()
    return {
        nation: [
            {"supplier_name": name, "numwait": count}
            for name, count in sorted(values.items(), key=lambda item: (-item[1], item[0]))
        ]
        for nation, values in counts.items()
    }


def main() -> None:
    global CONTAINER
    parser = argparse.ArgumentParser()
    parser.add_argument("--scale", default="0.01")
    parser.add_argument("--container", default=CONTAINER)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument(
        "--q21-variant",
        choices=("both", "neo4j-compatible", "tpch-corrected"),
        default="both",
    )
    parser.add_argument("--queries", default="21,22", help="Subset of 21,22")
    parser.add_argument("--source-dir", type=Path, help="Local graph_staging directory")
    args = parser.parse_args()
    selected_queries = {int(value.strip()) for value in args.queries.split(",") if value.strip()}
    if not selected_queries or not selected_queries <= {21, 22}:
        parser.error("--queries must be a non-empty subset of 21,22")
    CONTAINER = args.container
    source_csv.cache_clear()
    scale_tag = args.scale.replace(".", "")
    evidence: dict[str, object] = {
        "validation": "independent computation from original TigerGraph import CSV files",
        "scale_factor": args.scale,
        "validated_at_utc": datetime.now(timezone.utc).isoformat(),
        "checks": [],
    }
    q21_nations = sorted({row["selected_nation"] for row in load_schedule(21)})
    streaming_q21 = reference_q21_streaming_all(args.source_dir) if 21 in selected_queries and args.source_dir else None
    q21_variants = (("neo4j_compatible", False), ("tpch_corrected", True))
    if args.q21_variant != "both":
        selected = args.q21_variant.replace("-", "_")
        q21_variants = tuple(item for item in q21_variants if item[0] == selected)
    for variant, corrected in q21_variants if 21 in selected_queries else ():
        if streaming_q21 is not None and corrected:
            raise ValueError("Streaming Q21 validation currently supports neo4j-compatible only")
        query = f"q21_tigergraph_{variant}"
        for nation in q21_nations:
            actual = finalize_q21(synchronous_rows(args.host, DEFAULT_GRAPH, query, {"selected_nation": nation}))
            expected = streaming_q21.get(nation, []) if streaming_q21 is not None else reference_q21(nation, corrected)
            if corrected:
                expected = expected[:100]
            if actual != expected:
                raise AssertionError(f"Q21 {variant} mismatch for {nation}: actual={actual}, expected={expected}")
        print(f"Q21 {variant}: PASS ({len(q21_nations)} distinct nations)")
        evidence["checks"].append({
            "query": "Q21", "variant": variant, "status": "PASS",
            "distinct_parameter_sets": len(q21_nations),
        })

    q22_row = load_schedule(22)[0]
    q22_parameter_sets = {
        "tpch_corrected": {field: q22_row[field] for field in Q22_FIELDS},
        "neo4j_compatible": dict(zip(Q22_FIELDS, Q22_NEO4J_COMPATIBLE_CODES)),
    }
    for variant, params in q22_parameter_sets.items() if 22 in selected_queries else ():
        customers = synchronous_rows(args.host, DEFAULT_GRAPH, "q22_customers_tigergraph", params)
        ordered = synchronous_rows(args.host, DEFAULT_GRAPH, "q22_order_customers_tigergraph", params)
        _, actual_q22 = finalize_q22(customers, ordered)
        expected_q22 = reference_q22(set(params.values()))
        if actual_q22 != expected_q22:
            raise AssertionError(f"Q22 {variant} mismatch: actual={actual_q22}, expected={expected_q22}")
        print(f"Q22 {variant}: PASS ({len(actual_q22)} result rows)")
        evidence["checks"].append({
            "query": "Q22", "variant": variant, "status": "PASS",
            "codes": list(params.values()), "result_rows": len(actual_q22),
        })
    query_tag = "_".join(f"q{query}" for query in sorted(selected_queries))
    output = PROJECT_ROOT / "results" / "query_benchmarks_final" / "correctness" / f"{query_tag}_sf{scale_tag}_reference_validation.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved validation evidence: {output}")


if __name__ == "__main__":
    main()

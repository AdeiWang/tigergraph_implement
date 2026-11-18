"""Validate five representative direct queries from the SF 0.01 source CSVs."""

from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Callable

import requests


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "datasets"
OUTPUT = ROOT / "results" / "query_benchmarks_final" / "correctness"
HOST = "http://localhost:14240"
GRAPH = "TPCH_G"


def rows(filename: str) -> list[dict[str, str]]:
    with (DATA / filename).open(encoding="utf-8-sig", newline="") as handle:
        return [
            {key.lower(): value for key, value in row.items()}
            for row in csv.DictReader(handle)
        ]


def query(name: str, **parameters: object) -> list[dict[str, Any]]:
    response = requests.get(
        f"{HOST}/restpp/query/{GRAPH}/{name}", params=parameters, timeout=300
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("error"):
        raise RuntimeError(f"{name} failed: {payload}")

    def find_table(value: object) -> list[dict[str, Any]] | None:
        if isinstance(value, dict):
            if "T" in value and isinstance(value["T"], list):
                return value["T"]
            if "T" in value and isinstance(value["T"], dict):
                return [value["T"]]
            for child in value.values():
                found = find_table(child)
                if found is not None:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = find_table(child)
                if found is not None:
                    return found
        return None

    result = find_table(payload.get("results", []))
    if result is None:
        raise RuntimeError(f"No result table returned by {name}: {payload}")
    return result


def date_text(value: Any) -> str:
    text = str(value)
    return text[:10]


def number(value: Any) -> float:
    return float(value)


def canonical(
    result_rows: list[dict[str, Any]],
    keys: tuple[str, ...],
    numeric: tuple[str, ...],
    dates: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for row in result_rows:
        item: dict[str, Any] = {}
        for key in keys:
            value = row[key]
            if key in numeric:
                item[key] = number(value)
            elif key in dates:
                item[key] = date_text(value)
            else:
                item[key] = value
        converted.append(item)
    return sorted(converted, key=lambda row: tuple(str(row[key]) for key in keys))


def compare(
    expected: list[dict[str, Any]],
    actual: list[dict[str, Any]],
    numeric: tuple[str, ...],
) -> None:
    if len(expected) != len(actual):
        raise AssertionError(f"row count differs: expected {len(expected)}, actual {len(actual)}")
    for index, (left, right) in enumerate(zip(expected, actual), start=1):
        if left.keys() != right.keys():
            raise AssertionError(f"row {index} fields differ")
        for field in left:
            if field in numeric:
                if not math.isclose(
                    float(left[field]), float(right[field]), rel_tol=1e-8, abs_tol=1e-6
                ):
                    raise AssertionError(
                        f"row {index} {field}: expected {left[field]}, actual {right[field]}"
                    )
            elif left[field] != right[field]:
                raise AssertionError(
                    f"row {index} {field}: expected {left[field]!r}, actual {right[field]!r}"
                )


def validate_q1(lineitems: list[dict[str, str]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], tuple[str, ...]]:
    cutoff = date.fromisoformat("1998-09-02")
    groups: dict[tuple[str, str], list[tuple[float, float, float, float]]] = defaultdict(list)
    for line in lineitems:
        if date.fromisoformat(line["l_shipdate"]) <= cutoff:
            quantity = float(line["l_quantity"])
            price = float(line["l_extendedprice"])
            discount = float(line["l_discount"])
            tax = float(line["l_tax"])
            groups[(line["l_returnflag"], line["l_linestatus"])].append(
                (quantity, price, discount, tax)
            )
    expected = []
    for (returnflag, linestatus), values in groups.items():
        count = len(values)
        expected.append(
            {
                "returnflag": returnflag,
                "linestatus": linestatus,
                "sum_qty": sum(value[0] for value in values),
                "sum_base_price": sum(value[1] for value in values),
                "sum_disc_price": sum(value[1] * (1 - value[2]) for value in values),
                "sum_charge": sum(value[1] * (1 - value[2]) * (1 + value[3]) for value in values),
                "avg_qty": sum(value[0] for value in values) / count,
                "avg_price": sum(value[1] for value in values) / count,
                "avg_disc": sum(value[2] for value in values) / count,
                "count_order": float(count),
            }
        )
    actual = query("q1_tigergraph", cutoff_date="1998-09-02 00:00:00")
    numeric = (
        "sum_qty", "sum_base_price", "sum_disc_price", "sum_charge",
        "avg_qty", "avg_price", "avg_disc", "count_order",
    )
    keys = ("returnflag", "linestatus") + numeric
    return canonical(expected, keys, numeric), canonical(actual, keys, numeric), numeric


def validate_q3(
    lineitems: list[dict[str, str]],
    orders: dict[int, dict[str, str]],
    customers: dict[int, dict[str, str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], tuple[str, ...]]:
    selected = date.fromisoformat("1995-03-15")
    totals: dict[tuple[int, str, int], float] = defaultdict(float)
    for line in lineitems:
        order = orders[int(line["l_orderkey"])]
        customer = customers[int(order["o_custkey"])]
        if (
            customer["c_mktsegment"] == "BUILDING"
            and date.fromisoformat(order["o_orderdate"]) < selected
            and date.fromisoformat(line["l_shipdate"]) > selected
        ):
            key = (
                int(order["o_orderkey"]),
                order["o_orderdate"],
                int(order["o_shippriority"]),
            )
            totals[key] += float(line["l_extendedprice"]) * (1 - float(line["l_discount"]))
    expected = [
        {"orderkey": key[0], "orderdate": key[1], "shippriority": key[2], "revenue": value}
        for key, value in totals.items()
    ]
    actual = query(
        "q3_tigergraph",
        selected_segment="BUILDING",
        selected_date="1995-03-15 00:00:00",
    )
    keys = ("orderkey", "orderdate", "shippriority", "revenue")
    numeric = ("orderkey", "shippriority", "revenue")
    return (
        canonical(expected, keys, numeric, ("orderdate",)),
        canonical(actual, keys, numeric, ("orderdate",)),
        numeric,
    )


def validate_q6(lineitems: list[dict[str, str]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], tuple[str, ...]]:
    revenue = sum(
        float(line["l_extendedprice"]) * float(line["l_discount"])
        for line in lineitems
        if "1994-01-01" <= line["l_shipdate"] < "1995-01-01"
        and 0.05 <= float(line["l_discount"]) <= 0.07
        and float(line["l_quantity"]) < 24
    )
    expected = [{"revenue": revenue}]
    actual = query(
        "q6_tigergraph",
        start_date="1994-01-01 00:00:00",
        end_date="1995-01-01 00:00:00",
        min_discount=0.05,
        max_discount=0.07,
        selected_quantity=24,
    )
    return canonical(expected, ("revenue",), ("revenue",)), canonical(actual, ("revenue",), ("revenue",)), ("revenue",)


def validate_q7(
    lineitems: list[dict[str, str]],
    orders: dict[int, dict[str, str]],
    customers: dict[int, dict[str, str]],
    suppliers: dict[int, dict[str, str]],
    nations: dict[int, dict[str, str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], tuple[str, ...]]:
    totals: dict[tuple[str, str, int], float] = defaultdict(float)
    selected_pair = {"FRANCE", "GERMANY"}
    for line in lineitems:
        if not "1995-01-01" <= line["l_shipdate"] <= "1996-12-31":
            continue
        supplier = suppliers[int(line["l_suppkey"])]
        order = orders[int(line["l_orderkey"])]
        customer = customers[int(order["o_custkey"])]
        supp_nation = nations[int(supplier["s_nationkey"])]["n_name"]
        cust_nation = nations[int(customer["c_nationkey"])]["n_name"]
        if {supp_nation, cust_nation} != selected_pair:
            continue
        key = (supp_nation, cust_nation, int(line["l_shipdate"][:4]))
        totals[key] += float(line["l_extendedprice"]) * (1 - float(line["l_discount"]))
    expected = [
        {"supp_nation": key[0], "cust_nation": key[1], "l_year": key[2], "revenue": value}
        for key, value in totals.items()
    ]
    actual = query("q7_tigergraph", nation1="FRANCE", nation2="GERMANY")
    keys = ("supp_nation", "cust_nation", "l_year", "revenue")
    numeric = ("l_year", "revenue")
    return canonical(expected, keys, numeric), canonical(actual, keys, numeric), numeric


def validate_q18(
    lineitems: list[dict[str, str]],
    orders: dict[int, dict[str, str]],
    customers: dict[int, dict[str, str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], tuple[str, ...]]:
    quantities: dict[int, float] = defaultdict(float)
    for line in lineitems:
        quantities[int(line["l_orderkey"])] += float(line["l_quantity"])
    expected = []
    for order_key, amount in quantities.items():
        if amount <= 300:
            continue
        order = orders[order_key]
        customer = customers[int(order["o_custkey"])]
        expected.append(
            {
                "customer_name": customer["c_name"],
                "customer_key": int(customer["c_custkey"]),
                "order_key": order_key,
                "order_date": order["o_orderdate"],
                "price": float(order["o_totalprice"]),
                "amount": amount,
            }
        )
    actual = query("q18_tigergraph", quantity_threshold=300)
    keys = ("customer_name", "customer_key", "order_key", "order_date", "price", "amount")
    numeric = ("customer_key", "order_key", "price", "amount")
    return (
        canonical(expected, keys, numeric, ("order_date",)),
        canonical(actual, keys, numeric, ("order_date",)),
        numeric,
    )


def main() -> int:
    lineitems = rows("lineitem_small.csv")
    order_rows = rows("orders_small.csv")
    customer_rows = rows("customer_small.csv")
    supplier_rows = rows("supplier_small.csv")
    nation_rows = rows("nation_small.csv")
    orders = {int(row["o_orderkey"]): row for row in order_rows}
    customers = {int(row["c_custkey"]): row for row in customer_rows}
    suppliers = {int(row["s_suppkey"]): row for row in supplier_rows}
    nations = {int(row["n_nationkey"]): row for row in nation_rows}

    validators: dict[str, Callable[[], tuple[list[dict[str, Any]], list[dict[str, Any]], tuple[str, ...]]]] = {
        "Q1": lambda: validate_q1(lineitems),
        "Q3": lambda: validate_q3(lineitems, orders, customers),
        "Q6": lambda: validate_q6(lineitems),
        "Q7": lambda: validate_q7(lineitems, orders, customers, suppliers, nations),
        "Q18": lambda: validate_q18(lineitems, orders, customers),
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    summary = []
    for label, validator in validators.items():
        expected, actual, numeric = validator()
        compare(expected, actual, numeric)
        (OUTPUT / f"{label.lower()}_sf001_expected.json").write_text(
            json.dumps(expected, indent=2) + "\n", encoding="utf-8"
        )
        (OUTPUT / f"{label.lower()}_sf001_actual.json").write_text(
            json.dumps(actual, indent=2) + "\n", encoding="utf-8"
        )
        summary.append({"query": label, "status": "PASS", "rows": len(actual)})
        print(f"{label}: PASS ({len(actual)} rows)")

    output = OUTPUT / "representative_direct_queries_sf001_validation.json"
    output.write_text(
        json.dumps(
            {
                "validation": "independent computation from original SF 0.01 source CSV files",
                "queries": summary,
                "status": "PASS",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

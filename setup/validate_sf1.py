from pathlib import Path
import csv
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "datasets" / "sf_1" / "source_csv"

EXPECTED_COUNTS = {
    "region": 5,
    "nation": 25,
    "supplier": 10_000,
    "customer": 150_000,
    "part": 200_000,
    "partsupp": 800_000,
    "orders": 1_500_000,
    "lineitem": 6_001_215,
}

FILES = {
    table: DATA_DIR / f"{table}_large.csv"
    for table in EXPECTED_COUNTS
}

MAX_EXAMPLES = 5


def open_csv(path):
    return path.open("r", encoding="utf-8-sig", newline="")


def check_file_exists():
    missing = [str(path) for path in FILES.values() if not path.exists()]
    if missing:
        print("ERROR: Missing CSV file(s):")
        for path in missing:
            print(f"  {path}")
        sys.exit(1)


def report_count(table, actual):
    expected = EXPECTED_COUNTS[table]
    status = "PASS" if actual == expected else "FAIL"
    print(f"{table.upper():10s}: {actual:>10,d}  expected {expected:>10,d}  [{status}]")
    return actual == expected


def report_relationship(name, missing_count, examples):
    status = "PASS" if missing_count == 0 else "FAIL"
    print(f"{name:30s} missing = {missing_count:>10,d}  [{status}]")
    if examples:
        print("  examples:")
        for item in examples:
            print(f"    {item}")
    return missing_count == 0


def encode_partsupp(partkey, suppkey):
    # Collision-free for the observed TPC-H sf=1 key ranges.
    # suppkey <= 10,000, so multiplying partkey by 100,000
    # leaves ample room for the supplier key.
    return partkey * 100_000 + suppkey


def main():
    print("TPC-H sf=1 source validation")
    print(f"Data directory: {DATA_DIR}")
    print()

    check_file_exists()

    counts_ok = True
    relationships_ok = True

    # ----------------------------------------------------------
    # REGION
    # ----------------------------------------------------------
    region_keys = set()
    count = 0
    with open_csv(FILES["region"]) as f:
        reader = csv.DictReader(f)
        for row in reader:
            count += 1
            region_keys.add(int(row["R_REGIONKEY"]))
    counts_ok &= report_count("region", count)

    # ----------------------------------------------------------
    # NATION -> REGION
    # ----------------------------------------------------------
    nation_keys = set()
    missing = 0
    examples = []
    count = 0
    with open_csv(FILES["nation"]) as f:
        reader = csv.DictReader(f)
        for row in reader:
            count += 1
            nation_key = int(row["N_NATIONKEY"])
            region_key = int(row["N_REGIONKEY"])
            nation_keys.add(nation_key)

            if region_key not in region_keys:
                missing += 1
                if len(examples) < MAX_EXAMPLES:
                    examples.append(
                        f"N_NATIONKEY={nation_key} -> N_REGIONKEY={region_key}"
                    )

    counts_ok &= report_count("nation", count)
    relationships_ok &= report_relationship(
        "NATION -> REGION", missing, examples
    )
    del region_keys

    # ----------------------------------------------------------
    # SUPPLIER -> NATION
    # ----------------------------------------------------------
    supplier_keys = set()
    missing = 0
    examples = []
    count = 0
    with open_csv(FILES["supplier"]) as f:
        reader = csv.DictReader(f)
        for row in reader:
            count += 1
            supp_key = int(row["S_SUPPKEY"])
            nation_key = int(row["S_NATIONKEY"])
            supplier_keys.add(supp_key)

            if nation_key not in nation_keys:
                missing += 1
                if len(examples) < MAX_EXAMPLES:
                    examples.append(
                        f"S_SUPPKEY={supp_key} -> S_NATIONKEY={nation_key}"
                    )

    counts_ok &= report_count("supplier", count)
    relationships_ok &= report_relationship(
        "SUPPLIER -> NATION", missing, examples
    )

    # ----------------------------------------------------------
    # CUSTOMER -> NATION
    # ----------------------------------------------------------
    customer_keys = set()
    missing = 0
    examples = []
    count = 0
    with open_csv(FILES["customer"]) as f:
        reader = csv.DictReader(f)
        for row in reader:
            count += 1
            cust_key = int(row["C_CUSTKEY"])
            nation_key = int(row["C_NATIONKEY"])
            customer_keys.add(cust_key)

            if nation_key not in nation_keys:
                missing += 1
                if len(examples) < MAX_EXAMPLES:
                    examples.append(
                        f"C_CUSTKEY={cust_key} -> C_NATIONKEY={nation_key}"
                    )

    counts_ok &= report_count("customer", count)
    relationships_ok &= report_relationship(
        "CUSTOMER -> NATION", missing, examples
    )
    del nation_keys

    # ----------------------------------------------------------
    # PART
    # ----------------------------------------------------------
    part_keys = set()
    count = 0
    with open_csv(FILES["part"]) as f:
        reader = csv.DictReader(f)
        for row in reader:
            count += 1
            part_keys.add(int(row["P_PARTKEY"]))

    counts_ok &= report_count("part", count)

    # ----------------------------------------------------------
    # ORDERS -> CUSTOMER
    # Keep ORDERS keys for LINEITEM validation later.
    # ----------------------------------------------------------
    order_keys = set()
    missing = 0
    examples = []
    count = 0
    with open_csv(FILES["orders"]) as f:
        reader = csv.DictReader(f)
        for row in reader:
            count += 1
            order_key = int(row["O_ORDERKEY"])
            cust_key = int(row["O_CUSTKEY"])
            order_keys.add(order_key)

            if cust_key not in customer_keys:
                missing += 1
                if len(examples) < MAX_EXAMPLES:
                    examples.append(
                        f"O_ORDERKEY={order_key} -> O_CUSTKEY={cust_key}"
                    )

    counts_ok &= report_count("orders", count)
    relationships_ok &= report_relationship(
        "ORDERS -> CUSTOMER", missing, examples
    )
    del customer_keys

    # ----------------------------------------------------------
    # PARTSUPP -> PART
    # PARTSUPP -> SUPPLIER
    # Keep composite PARTSUPP keys for LINEITEM validation later.
    # ----------------------------------------------------------
    partsupp_keys = set()
    missing_part = 0
    missing_supplier = 0
    examples_part = []
    examples_supplier = []
    count = 0

    with open_csv(FILES["partsupp"]) as f:
        reader = csv.DictReader(f)
        for row in reader:
            count += 1
            part_key = int(row["PS_PARTKEY"])
            supp_key = int(row["PS_SUPPKEY"])

            partsupp_keys.add(encode_partsupp(part_key, supp_key))

            if part_key not in part_keys:
                missing_part += 1
                if len(examples_part) < MAX_EXAMPLES:
                    examples_part.append(
                        f"(PS_PARTKEY={part_key}, PS_SUPPKEY={supp_key})"
                    )

            if supp_key not in supplier_keys:
                missing_supplier += 1
                if len(examples_supplier) < MAX_EXAMPLES:
                    examples_supplier.append(
                        f"(PS_PARTKEY={part_key}, PS_SUPPKEY={supp_key})"
                    )

    counts_ok &= report_count("partsupp", count)
    relationships_ok &= report_relationship(
        "PARTSUPP -> PART", missing_part, examples_part
    )
    relationships_ok &= report_relationship(
        "PARTSUPP -> SUPPLIER", missing_supplier, examples_supplier
    )
    del part_keys
    del supplier_keys

    # ----------------------------------------------------------
    # LINEITEM -> ORDERS
    # LINEITEM -> PARTSUPP
    # ----------------------------------------------------------
    missing_order = 0
    missing_partsupp = 0
    examples_order = []
    examples_partsupp = []
    count = 0

    with open_csv(FILES["lineitem"]) as f:
        reader = csv.DictReader(f)
        for row in reader:
            count += 1

            order_key = int(row["L_ORDERKEY"])
            part_key = int(row["L_PARTKEY"])
            supp_key = int(row["L_SUPPKEY"])
            line_number = int(row["L_LINENUMBER"])

            if order_key not in order_keys:
                missing_order += 1
                if len(examples_order) < MAX_EXAMPLES:
                    examples_order.append(
                        f"(L_ORDERKEY={order_key}, L_LINENUMBER={line_number})"
                    )

            if encode_partsupp(part_key, supp_key) not in partsupp_keys:
                missing_partsupp += 1
                if len(examples_partsupp) < MAX_EXAMPLES:
                    examples_partsupp.append(
                        f"(L_ORDERKEY={order_key}, "
                        f"L_PARTKEY={part_key}, "
                        f"L_SUPPKEY={supp_key}, "
                        f"L_LINENUMBER={line_number})"
                    )

            if count % 1_000_000 == 0:
                print(f"LINEITEM progress: {count:,} rows checked")

    counts_ok &= report_count("lineitem", count)
    relationships_ok &= report_relationship(
        "LINEITEM -> ORDERS", missing_order, examples_order
    )
    relationships_ok &= report_relationship(
        "LINEITEM -> PARTSUPP", missing_partsupp, examples_partsupp
    )

    print()
    print(f"Counts:        {'PASS' if counts_ok else 'FAIL'}")
    print(f"Relationships: {'PASS' if relationships_ok else 'FAIL'}")

    all_ok = counts_ok and relationships_ok
    print(f"RESULT:        {'PASS' if all_ok else 'FAIL'}")

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()

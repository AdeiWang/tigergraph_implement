from pathlib import Path
import csv
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "datasets" / "sf_1" / "source_csv"
OUTPUT_DIR = PROJECT_ROOT / "datasets" / "sf_1" / "graph_staging"
VERTEX_DIR = OUTPUT_DIR / "vertices"
EDGE_DIR = OUTPUT_DIR / "edges"

VERTEX_DIR.mkdir(parents=True, exist_ok=True)
EDGE_DIR.mkdir(parents=True, exist_ok=True)

EXPECTED = {
    "region": 5,
    "nation": 25,
    "supplier": 10_000,
    "customer": 150_000,
    "part": 200_000,
    "partsupp": 800_000,
    "orders": 1_500_000,
    "lineitem": 6_001_215,
}

EXPECTED_TOTAL_VERTICES = 8_661_245
EXPECTED_TOTAL_EDGES = 15_262_455


def technical_id(prefix, number):
    # Same rule as the sf=0.1 PowerShell script:
    # minimum width 6, but larger numbers are not truncated.
    return f"{prefix}{number:06d}"


def open_source(table):
    path = DATA_DIR / f"{table}_large.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing source CSV: {path}")
    return path.open("r", encoding="utf-8-sig", newline="")


def open_output(path):
    return path.open("w", encoding="utf-8-sig", newline="")


def make_writer(file_obj, header):
    writer = csv.writer(
        file_obj,
        quoting=csv.QUOTE_ALL,
        lineterminator="\r\n",
    )
    writer.writerow(header)
    return writer


def check_count(table, count):
    expected = EXPECTED[table]
    if count != expected:
        raise RuntimeError(
            f"{table}: expected {expected:,} rows, got {count:,}"
        )


def require(mapping, key, relation):
    try:
        return mapping[key]
    except KeyError as exc:
        raise RuntimeError(
            f"Missing referenced key while generating {relation}: {key}"
        ) from exc


def main():
    print("TPC-H sf=1 Graph Semantics staging preparation")
    print(f"Input:  {DATA_DIR}")
    print(f"Output: {OUTPUT_DIR}")
    print()

    # Only lookup maps required by later relationships are retained.
    # Source rows and output rows are streamed; they are not accumulated.
    region_id_by_key = {}
    nation_id_by_key = {}
    supplier_id_by_key = {}
    customer_id_by_key = {}
    part_id_by_key = {}
    partsupp_id_by_key = {}
    order_id_by_key = {}

    counts = {}
    edge_counts = {
        "nation_region": 0,
        "supplier_nation": 0,
        "customer_nation": 0,
        "orders_customer": 0,
        "partsupp_part": 0,
        "partsupp_supplier": 0,
        "lineitem_orders": 0,
        "lineitem_partsupp": 0,
    }

    # --------------------------------------------------------
    # REGION
    # --------------------------------------------------------
    count = 0
    with (
        open_source("region") as fin,
        open_output(VERTEX_DIR / "region.csv") as fv,
    ):
        reader = csv.DictReader(fin)
        vw = make_writer(
            fv,
            ["tg_region_id", "r_regionkey", "r_name", "r_comment"],
        )

        for count, row in enumerate(reader, start=1):
            tg_id = technical_id("R", count)
            region_id_by_key[row["R_REGIONKEY"]] = tg_id

            vw.writerow([
                tg_id,
                row["R_REGIONKEY"],
                row["R_NAME"],
                row["R_COMMENT"],
            ])

    counts["region"] = count
    check_count("region", count)
    print(f"REGION:   {count:,}")

    # --------------------------------------------------------
    # NATION + NATION_REGION
    # --------------------------------------------------------
    count = 0
    with (
        open_source("nation") as fin,
        open_output(VERTEX_DIR / "nation.csv") as fv,
        open_output(EDGE_DIR / "nation_region.csv") as fe,
    ):
        reader = csv.DictReader(fin)
        vw = make_writer(
            fv,
            ["tg_nation_id", "n_nationkey", "n_name", "n_comment"],
        )
        ew = make_writer(fe, ["from_id", "to_id"])

        for count, row in enumerate(reader, start=1):
            tg_id = technical_id("N", count)
            nation_id_by_key[row["N_NATIONKEY"]] = tg_id

            vw.writerow([
                tg_id,
                row["N_NATIONKEY"],
                row["N_NAME"],
                row["N_COMMENT"],
            ])

            ew.writerow([
                tg_id,
                require(
                    region_id_by_key,
                    row["N_REGIONKEY"],
                    "NATION_REGION",
                ),
            ])
            edge_counts["nation_region"] += 1

    counts["nation"] = count
    check_count("nation", count)
    print(f"NATION:   {count:,}")

    # --------------------------------------------------------
    # SUPPLIER + SUPPLIER_NATION
    # --------------------------------------------------------
    count = 0
    with (
        open_source("supplier") as fin,
        open_output(VERTEX_DIR / "supplier.csv") as fv,
        open_output(EDGE_DIR / "supplier_nation.csv") as fe,
    ):
        reader = csv.DictReader(fin)
        vw = make_writer(
            fv,
            [
                "tg_supplier_id", "s_suppkey", "s_name",
                "s_address", "s_phone", "s_acctbal", "s_comment",
            ],
        )
        ew = make_writer(fe, ["from_id", "to_id"])

        for count, row in enumerate(reader, start=1):
            tg_id = technical_id("S", count)
            supplier_id_by_key[row["S_SUPPKEY"]] = tg_id

            vw.writerow([
                tg_id,
                row["S_SUPPKEY"],
                row["S_NAME"],
                row["S_ADDRESS"],
                row["S_PHONE"],
                row["S_ACCTBAL"],
                row["S_COMMENT"],
            ])

            ew.writerow([
                tg_id,
                require(
                    nation_id_by_key,
                    row["S_NATIONKEY"],
                    "SUPPLIER_NATION",
                ),
            ])
            edge_counts["supplier_nation"] += 1

    counts["supplier"] = count
    check_count("supplier", count)
    print(f"SUPPLIER: {count:,}")

    # --------------------------------------------------------
    # CUSTOMER + CUSTOMER_NATION
    # --------------------------------------------------------
    count = 0
    with (
        open_source("customer") as fin,
        open_output(VERTEX_DIR / "customer.csv") as fv,
        open_output(EDGE_DIR / "customer_nation.csv") as fe,
    ):
        reader = csv.DictReader(fin)
        vw = make_writer(
            fv,
            [
                "tg_customer_id", "c_custkey", "c_name",
                "c_address", "c_phone", "c_acctbal",
                "c_mktsegment", "c_comment",
            ],
        )
        ew = make_writer(fe, ["from_id", "to_id"])

        for count, row in enumerate(reader, start=1):
            tg_id = technical_id("C", count)
            customer_id_by_key[row["C_CUSTKEY"]] = tg_id

            vw.writerow([
                tg_id,
                row["C_CUSTKEY"],
                row["C_NAME"],
                row["C_ADDRESS"],
                row["C_PHONE"],
                row["C_ACCTBAL"],
                row["C_MKTSEGMENT"],
                row["C_COMMENT"],
            ])

            ew.writerow([
                tg_id,
                require(
                    nation_id_by_key,
                    row["C_NATIONKEY"],
                    "CUSTOMER_NATION",
                ),
            ])
            edge_counts["customer_nation"] += 1

    counts["customer"] = count
    check_count("customer", count)
    print(f"CUSTOMER: {count:,}")

    # Nation lookup is no longer needed.
    del nation_id_by_key
    del region_id_by_key

    # --------------------------------------------------------
    # PART
    # --------------------------------------------------------
    count = 0
    with (
        open_source("part") as fin,
        open_output(VERTEX_DIR / "part.csv") as fv,
    ):
        reader = csv.DictReader(fin)
        vw = make_writer(
            fv,
            [
                "tg_part_id", "p_partkey", "p_name", "p_mfgr",
                "p_brand", "p_type", "p_size", "p_container",
                "p_retailprice", "p_comment",
            ],
        )

        for count, row in enumerate(reader, start=1):
            tg_id = technical_id("P", count)
            part_id_by_key[row["P_PARTKEY"]] = tg_id

            vw.writerow([
                tg_id,
                row["P_PARTKEY"],
                row["P_NAME"],
                row["P_MFGR"],
                row["P_BRAND"],
                row["P_TYPE"],
                row["P_SIZE"],
                row["P_CONTAINER"],
                row["P_RETAILPRICE"],
                row["P_COMMENT"],
            ])

    counts["part"] = count
    check_count("part", count)
    print(f"PART:     {count:,}")

    # --------------------------------------------------------
    # PARTSUPP + PARTSUPP_PART + PARTSUPP_SUPPLIER
    # --------------------------------------------------------
    count = 0
    with (
        open_source("partsupp") as fin,
        open_output(VERTEX_DIR / "partsupp.csv") as fv,
        open_output(EDGE_DIR / "partsupp_part.csv") as fep,
        open_output(EDGE_DIR / "partsupp_supplier.csv") as fes,
    ):
        reader = csv.DictReader(fin)
        vw = make_writer(
            fv,
            [
                "tg_partsupp_id", "ps_availqty",
                "ps_supplycost", "ps_comment",
            ],
        )
        epw = make_writer(fep, ["from_id", "to_id"])
        esw = make_writer(fes, ["from_id", "to_id"])

        for count, row in enumerate(reader, start=1):
            tg_id = technical_id("PS", count)
            composite_key = (
                row["PS_PARTKEY"],
                row["PS_SUPPKEY"],
            )
            partsupp_id_by_key[composite_key] = tg_id

            vw.writerow([
                tg_id,
                row["PS_AVAILQTY"],
                row["PS_SUPPLYCOST"],
                row["PS_COMMENT"],
            ])

            epw.writerow([
                tg_id,
                require(
                    part_id_by_key,
                    row["PS_PARTKEY"],
                    "PARTSUPP_PART",
                ),
            ])
            edge_counts["partsupp_part"] += 1

            esw.writerow([
                tg_id,
                require(
                    supplier_id_by_key,
                    row["PS_SUPPKEY"],
                    "PARTSUPP_SUPPLIER",
                ),
            ])
            edge_counts["partsupp_supplier"] += 1

    counts["partsupp"] = count
    check_count("partsupp", count)
    print(f"PARTSUPP: {count:,}")

    del part_id_by_key
    del supplier_id_by_key

    # --------------------------------------------------------
    # ORDERS + ORDERS_CUSTOMER
    # --------------------------------------------------------
    count = 0
    with (
        open_source("orders") as fin,
        open_output(VERTEX_DIR / "orders.csv") as fv,
        open_output(EDGE_DIR / "orders_customer.csv") as fe,
    ):
        reader = csv.DictReader(fin)
        vw = make_writer(
            fv,
            [
                "tg_orders_id", "o_orderkey", "o_orderstatus",
                "o_totalprice", "o_orderdate", "o_orderpriority",
                "o_clerk", "o_shippriority", "o_comment",
            ],
        )
        ew = make_writer(fe, ["from_id", "to_id"])

        for count, row in enumerate(reader, start=1):
            tg_id = technical_id("O", count)
            order_id_by_key[row["O_ORDERKEY"]] = tg_id

            vw.writerow([
                tg_id,
                row["O_ORDERKEY"],
                row["O_ORDERSTATUS"],
                row["O_TOTALPRICE"],
                row["O_ORDERDATE"],
                row["O_ORDERPRIORITY"],
                row["O_CLERK"],
                row["O_SHIPPRIORITY"],
                row["O_COMMENT"],
            ])

            ew.writerow([
                tg_id,
                require(
                    customer_id_by_key,
                    row["O_CUSTKEY"],
                    "ORDERS_CUSTOMER",
                ),
            ])
            edge_counts["orders_customer"] += 1

    counts["orders"] = count
    check_count("orders", count)
    print(f"ORDERS:   {count:,}")

    del customer_id_by_key

    # --------------------------------------------------------
    # LINEITEM + LINEITEM_ORDERS + LINEITEM_PARTSUPP
    # --------------------------------------------------------
    count = 0
    with (
        open_source("lineitem") as fin,
        open_output(VERTEX_DIR / "lineitem.csv") as fv,
        open_output(EDGE_DIR / "lineitem_orders.csv") as feo,
        open_output(EDGE_DIR / "lineitem_partsupp.csv") as fep,
    ):
        reader = csv.DictReader(fin)
        vw = make_writer(
            fv,
            [
                "tg_lineitem_id", "l_linenumber", "l_quantity",
                "l_extendedprice", "l_discount", "l_tax",
                "l_returnflag", "l_linestatus", "l_shipdate",
                "l_commitdate", "l_receiptdate", "l_shipinstruct",
                "l_shipmode", "l_comment",
            ],
        )
        eow = make_writer(feo, ["from_id", "to_id"])
        epw = make_writer(fep, ["from_id", "to_id"])

        for count, row in enumerate(reader, start=1):
            tg_id = technical_id("L", count)

            vw.writerow([
                tg_id,
                row["L_LINENUMBER"],
                row["L_QUANTITY"],
                row["L_EXTENDEDPRICE"],
                row["L_DISCOUNT"],
                row["L_TAX"],
                row["L_RETURNFLAG"],
                row["L_LINESTATUS"],
                row["L_SHIPDATE"],
                row["L_COMMITDATE"],
                row["L_RECEIPTDATE"],
                row["L_SHIPINSTRUCT"],
                row["L_SHIPMODE"],
                row["L_COMMENT"],
            ])

            eow.writerow([
                tg_id,
                require(
                    order_id_by_key,
                    row["L_ORDERKEY"],
                    "LINEITEM_ORDERS",
                ),
            ])
            edge_counts["lineitem_orders"] += 1

            ps_key = (
                row["L_PARTKEY"],
                row["L_SUPPKEY"],
            )
            epw.writerow([
                tg_id,
                require(
                    partsupp_id_by_key,
                    ps_key,
                    "LINEITEM_PARTSUPP",
                ),
            ])
            edge_counts["lineitem_partsupp"] += 1

            if count % 1_000_000 == 0:
                print(f"LINEITEM progress: {count:,} rows written")

    counts["lineitem"] = count
    check_count("lineitem", count)
    print(f"LINEITEM: {count:,}")

    # --------------------------------------------------------
    # Final checks / summary
    # --------------------------------------------------------
    expected_edges = {
        "nation_region": EXPECTED["nation"],
        "supplier_nation": EXPECTED["supplier"],
        "customer_nation": EXPECTED["customer"],
        "orders_customer": EXPECTED["orders"],
        "partsupp_part": EXPECTED["partsupp"],
        "partsupp_supplier": EXPECTED["partsupp"],
        "lineitem_orders": EXPECTED["lineitem"],
        "lineitem_partsupp": EXPECTED["lineitem"],
    }

    for name, expected in expected_edges.items():
        actual = edge_counts[name]
        if actual != expected:
            raise RuntimeError(
                f"{name}: expected {expected:,} edges, got {actual:,}"
            )

    total_vertices = sum(counts.values())
    total_edges = sum(edge_counts.values())

    if total_vertices != EXPECTED_TOTAL_VERTICES:
        raise RuntimeError(
            f"Total vertices: expected {EXPECTED_TOTAL_VERTICES:,}, "
            f"got {total_vertices:,}"
        )

    if total_edges != EXPECTED_TOTAL_EDGES:
        raise RuntimeError(
            f"Total edges: expected {EXPECTED_TOTAL_EDGES:,}, "
            f"got {total_edges:,}"
        )

    print()
    print("Graph Semantics sf=1 staging data preparation completed.")
    print()
    print("Vertices:")
    print(f"REGION:   {counts['region']}")
    print(f"NATION:   {counts['nation']}")
    print(f"SUPPLIER: {counts['supplier']}")
    print(f"CUSTOMER: {counts['customer']}")
    print(f"PART:     {counts['part']}")
    print(f"PARTSUPP: {counts['partsupp']}")
    print(f"ORDERS:   {counts['orders']}")
    print(f"LINEITEM: {counts['lineitem']}")
    print()
    print("Edges:")
    print(f"NATION_REGION:         {edge_counts['nation_region']}")
    print(f"SUPPLIER_NATION:       {edge_counts['supplier_nation']}")
    print(f"CUSTOMER_NATION:       {edge_counts['customer_nation']}")
    print(f"ORDERS_CUSTOMER:       {edge_counts['orders_customer']}")
    print(f"PARTSUPP_PART:         {edge_counts['partsupp_part']}")
    print(f"PARTSUPP_SUPPLIER:     {edge_counts['partsupp_supplier']}")
    print(f"LINEITEM_ORDERS:       {edge_counts['lineitem_orders']}")
    print(f"LINEITEM_PARTSUPP:     {edge_counts['lineitem_partsupp']}")
    print()
    print(f"Expected total vertices: {EXPECTED_TOTAL_VERTICES}")
    print(f"Expected total edges:    {EXPECTED_TOTAL_EDGES}")
    print()
    print("RESULT: PASS")
    print(f"Output directory: {OUTPUT_DIR}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print()
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

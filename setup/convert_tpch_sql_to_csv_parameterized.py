from pathlib import Path
import argparse
import csv
import re


PROJECT_ROOT = Path(__file__).resolve().parent.parent


HEADERS = {
    "region": ["R_REGIONKEY", "R_NAME", "R_COMMENT"],
    "nation": ["N_NATIONKEY", "N_NAME", "N_REGIONKEY", "N_COMMENT"],
    "supplier": [
        "S_SUPPKEY", "S_NAME", "S_ADDRESS", "S_NATIONKEY",
        "S_PHONE", "S_ACCTBAL", "S_COMMENT",
    ],
    "customer": [
        "C_CUSTKEY", "C_NAME", "C_ADDRESS", "C_NATIONKEY",
        "C_PHONE", "C_ACCTBAL", "C_MKTSEGMENT", "C_COMMENT",
    ],
    "part": [
        "P_PARTKEY", "P_NAME", "P_MFGR", "P_BRAND", "P_TYPE",
        "P_SIZE", "P_CONTAINER", "P_RETAILPRICE", "P_COMMENT",
    ],
    "partsupp": [
        "PS_PARTKEY", "PS_SUPPKEY", "PS_AVAILQTY",
        "PS_SUPPLYCOST", "PS_COMMENT",
    ],
    "orders": [
        "O_ORDERKEY", "O_CUSTKEY", "O_ORDERSTATUS", "O_TOTALPRICE",
        "O_ORDERDATE", "O_ORDERPRIORITY", "O_CLERK",
        "O_SHIPPRIORITY", "O_COMMENT",
    ],
    "lineitem": [
        "L_ORDERKEY", "L_PARTKEY", "L_SUPPKEY", "L_LINENUMBER",
        "L_QUANTITY", "L_EXTENDEDPRICE", "L_DISCOUNT", "L_TAX",
        "L_RETURNFLAG", "L_LINESTATUS", "L_SHIPDATE", "L_COMMITDATE",
        "L_RECEIPTDATE", "L_SHIPINSTRUCT", "L_SHIPMODE", "L_COMMENT",
    ],
}


INSERT_RE = re.compile(
    r"^INSERT\s+INTO\s+\w+\s+VALUES\s*\((.*)\);\s*$",
    re.IGNORECASE,
)


def parse_values(line):
    match = INSERT_RE.match(line.rstrip("\r\n"))
    if not match:
        raise ValueError(f"Cannot parse line:\n{line}")

    reader = csv.reader(
        [match.group(1)],
        delimiter=",",
        quotechar="'",
        doublequote=True,
        skipinitialspace=False,
    )
    return next(reader)


def convert_table(table, input_dir, output_dir, suffix):
    input_file = input_dir / f"{table}.sql"
    output_file = output_dir / f"{table}_{suffix}.csv"

    expected_columns = len(HEADERS[table])
    row_count = 0

    with (
        input_file.open("r", encoding="utf-8", errors="strict") as fin,
        output_file.open("w", encoding="utf-8-sig", newline="") as fout,
    ):
        writer = csv.writer(fout)
        writer.writerow(HEADERS[table])

        for line_number, line in enumerate(fin, start=1):
            if not line.strip():
                continue

            row = parse_values(line)
            if len(row) != expected_columns:
                raise ValueError(
                    f"{table}.sql line {line_number}: "
                    f"expected {expected_columns} columns, got {len(row)}"
                )

            writer.writerow(row)
            row_count += 1

    print(
        f"{table:10s} -> "
        f"{output_file.name:22s} "
        f"{row_count:>10,d} rows"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Convert TPC-H INSERT .sql files to CSV files."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Directory containing the eight TPC-H .sql files",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Directory for converted CSV files",
    )
    parser.add_argument(
        "--suffix",
        required=True,
        help="Output filename suffix, e.g. medium or large",
    )
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_dir = Path(args.output)

    if not input_dir.is_absolute():
        input_dir = PROJECT_ROOT / input_dir
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir

    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory does not exist: {input_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Input:  {input_dir}")
    print(f"Output: {output_dir}")
    print(f"Suffix: {args.suffix}")
    print()

    for table in HEADERS:
        convert_table(table, input_dir, output_dir, args.suffix)


if __name__ == "__main__":
    main()

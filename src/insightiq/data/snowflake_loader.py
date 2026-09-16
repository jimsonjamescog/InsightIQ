from __future__ import annotations

import argparse
import os
from pathlib import Path

import duckdb

from insightiq.data.warehouse import build_warehouse

TABLES = [
    "raw.customers",
    "raw.products",
    "raw.orders",
    "raw.order_items",
    "raw.web_traffic",
    "raw.payments",
    "operations.deployments",
    "operations.pipeline_runs",
    "operations.schema_changes",
    "operations.data_dependencies",
    "operations.incidents",
    "operations.documents",
]


def load_table(local_connection, snowflake_connection, table: str) -> int:
    source = local_connection.execute(f"SELECT * FROM {table}")
    columns = [item[0].upper() for item in source.description]
    rows = source.fetchall()
    placeholders = ", ".join(["%s"] * len(columns))
    statement = f"INSERT INTO {table.upper()} ({', '.join(columns)}) VALUES ({placeholders})"
    cursor = snowflake_connection.cursor()
    try:
        cursor.execute(f"TRUNCATE TABLE {table.upper()}")
        for start in range(0, len(rows), 5000):
            cursor.executemany(statement, rows[start : start + 5000])
    finally:
        cursor.close()
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Load generated InsightIQ sources into Snowflake.")
    parser.add_argument("--db", type=Path, default=Path("data/insightiq.duckdb"))
    parser.add_argument("--setup-sql", type=Path, default=Path("warehouse/snowflake/00_setup.sql"))
    args = parser.parse_args()
    if not args.db.exists():
        build_warehouse(args.db)
    try:
        import snowflake.connector
    except ImportError as error:
        raise SystemExit('Install Snowflake support with pip install -e ".[snowflake]"') from error

    required = ["SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_WAREHOUSE"]
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise SystemExit(f"Missing configuration: {', '.join(missing)}")
    connection = snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.getenv("SNOWFLAKE_PASSWORD"),
        authenticator=os.getenv("SNOWFLAKE_AUTHENTICATOR") or None,
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.getenv("SNOWFLAKE_DATABASE", "INSIGHTIQ"),
        role=os.getenv("SNOWFLAKE_ROLE") or None,
    )
    try:
        with args.setup_sql.open(encoding="utf-8") as setup:
            for cursor in connection.execute_stream(setup):
                cursor.close()
        with duckdb.connect(str(args.db), read_only=True) as local:
            tables = list(TABLES)
            public_table_exists = local.execute(
                """
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_schema = 'raw' AND table_name = 'public_online_retail'
                """
            ).fetchone()[0]
            if public_table_exists:
                tables.append("raw.public_online_retail")
            for table in tables:
                count = load_table(local, connection, table)
                print(f"Loaded {count} rows into {table.upper()}")
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

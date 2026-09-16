from __future__ import annotations

from pathlib import Path

import duckdb


def import_uci_online_retail(source: str | Path, database: str | Path) -> dict:
    """Normalize a user-downloaded UCI Online Retail II workbook into the raw schema."""
    try:
        import pandas as pd
    except ImportError as error:
        raise RuntimeError(
            'Install real-data support with pip install -e ".[real-data]"'
        ) from error

    source_path = Path(source)
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    sheets = pd.read_excel(source_path, sheet_name=None)
    frames = []
    aliases = {
        "invoice": "invoice_no",
        "invoiceno": "invoice_no",
        "stockcode": "stock_code",
        "description": "description",
        "quantity": "quantity",
        "invoicedate": "invoice_date",
        "price": "unit_price",
        "unitprice": "unit_price",
        "customerid": "customer_id",
        "country": "country",
    }
    required = set(aliases.values())
    for sheet_name, frame in sheets.items():
        normalized = {
            "".join(character for character in str(column).lower() if character.isalnum()): column
            for column in frame.columns
        }
        rename = {original: aliases[key] for key, original in normalized.items() if key in aliases}
        frame = frame.rename(columns=rename)
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"Sheet {sheet_name} is missing columns: {sorted(missing)}")
        frames.append(frame[list(required)])
    transactions = pd.concat(frames, ignore_index=True)
    transactions["invoice_no"] = transactions["invoice_no"].astype(str)
    transactions = transactions[
        ~transactions["invoice_no"].str.upper().str.startswith("C")
        & (transactions["quantity"] > 0)
        & (transactions["unit_price"] > 0)
        & transactions["customer_id"].notna()
    ].copy()
    transactions["revenue"] = transactions["quantity"] * transactions["unit_price"]
    database_path = Path(database)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(database_path)) as connection:
        connection.execute("CREATE SCHEMA IF NOT EXISTS raw")
        connection.register("uci_transactions", transactions)
        connection.execute(
            """
            CREATE OR REPLACE TABLE raw.public_online_retail AS
            SELECT
                invoice_no::VARCHAR AS invoice_no,
                stock_code::VARCHAR AS stock_code,
                description::VARCHAR AS description,
                quantity::INTEGER AS quantity,
                invoice_date::TIMESTAMP AS invoice_date,
                unit_price::DOUBLE AS unit_price,
                customer_id::VARCHAR AS customer_id,
                country::VARCHAR AS country,
                revenue::DOUBLE AS revenue
            FROM uci_transactions
            """
        )
        row = connection.execute(
            """
            SELECT COUNT(*), COUNT(DISTINCT invoice_no), COUNT(DISTINCT customer_id),
                   MIN(invoice_date), MAX(invoice_date), SUM(revenue)
            FROM raw.public_online_retail
            """
        ).fetchone()
    return {
        "rows": row[0],
        "invoices": row[1],
        "customers": row[2],
        "start": str(row[3]),
        "end": str(row[4]),
        "revenue": float(row[5]),
        "source": "UCI Online Retail II",
        "doi": "10.24432/C5CG6D",
    }

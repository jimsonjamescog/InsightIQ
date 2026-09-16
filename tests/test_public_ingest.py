from pathlib import Path

import duckdb
import pandas as pd

from insightiq.data.public_ingest import import_uci_online_retail


def test_imports_and_cleans_uci_workbook(tmp_path: Path):
    source = tmp_path / "online_retail_II.xlsx"
    database = tmp_path / "insightiq.duckdb"
    frame = pd.DataFrame(
        [
            {
                "Invoice": "100001",
                "StockCode": "A1",
                "Description": "Valid item",
                "Quantity": 2,
                "InvoiceDate": "2011-01-01 10:00:00",
                "Price": 5.0,
                "Customer ID": 12345,
                "Country": "United Kingdom",
            },
            {
                "Invoice": "C100002",
                "StockCode": "A2",
                "Description": "Cancelled item",
                "Quantity": 1,
                "InvoiceDate": "2011-01-01 11:00:00",
                "Price": 10.0,
                "Customer ID": 12346,
                "Country": "United Kingdom",
            },
        ]
    )
    with pd.ExcelWriter(source, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name="Year 2010-2011", index=False)

    profile = import_uci_online_retail(source, database)

    assert profile["rows"] == 1
    assert profile["revenue"] == 10.0
    with duckdb.connect(str(database), read_only=True) as connection:
        row = connection.execute(
            "SELECT invoice_no, revenue FROM raw.public_online_retail"
        ).fetchone()
    assert row == ("100001", 10.0)

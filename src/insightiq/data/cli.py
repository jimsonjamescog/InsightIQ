from __future__ import annotations

import argparse
import json
from pathlib import Path

from insightiq.data.warehouse import (
    ScenarioName,
    build_warehouse,
    profile_warehouse,
    validate_warehouse,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Build and validate the InsightIQ data world.")
    result.add_argument("command", choices=["build", "reset", "validate", "profile", "import-uci"])
    result.add_argument("--db", type=Path, default=Path("data/insightiq.duckdb"))
    result.add_argument("--source", type=Path)
    result.add_argument(
        "--scenario",
        choices=[item.value for item in ScenarioName],
        default=ScenarioName.BASE.value,
    )
    return result


def main() -> int:
    args = parser().parse_args()
    if args.command == "import-uci":
        if not args.source:
            raise SystemExit("import-uci requires --source path/to/online_retail_II.xlsx")
        from insightiq.data.public_ingest import import_uci_online_retail

        print(json.dumps(import_uci_online_retail(args.source, args.db), indent=2))
        return 0
    if args.command in {"build", "reset"}:
        profile = build_warehouse(
            args.db,
            reset=args.command == "reset",
            scenario=args.scenario,
        )
        print(json.dumps(profile.to_dict(), indent=2))
        return 0
    if not args.db.exists():
        raise SystemExit(f"Warehouse does not exist: {args.db}")
    if args.command == "validate":
        errors = validate_warehouse(args.db, scenario=args.scenario)
        print(json.dumps({"valid": not errors, "errors": errors}, indent=2))
        return 1 if errors else 0
    print(json.dumps(profile_warehouse(args.db).to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

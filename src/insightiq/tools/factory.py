from __future__ import annotations

from insightiq.config import Settings
from insightiq.data.warehouse import build_warehouse
from insightiq.tools.mock import build_mock_registry
from insightiq.tools.registry import ToolRegistry
from insightiq.tools.warehouse import DuckDBRunner, SnowflakeRunner, build_warehouse_registry


def build_registry(settings: Settings) -> ToolRegistry:
    if settings.data_backend == "mock":
        return build_mock_registry()
    if settings.data_backend == "snowflake":
        return build_warehouse_registry(SnowflakeRunner())
    if not settings.database_path.exists():
        if not settings.auto_bootstrap_data:
            raise RuntimeError(f"DuckDB warehouse does not exist: {settings.database_path}")
        build_warehouse(settings.database_path)
    return build_warehouse_registry(DuckDBRunner(settings.database_path))

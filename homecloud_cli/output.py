"""Table, JSON, and YAML output helpers."""

from __future__ import annotations

import json
from typing import Any, Iterable

import yaml
from rich.console import Console
from rich.table import Table

console = Console()


def emit(data: Any, *, output_format: str, columns: list[str] | None = None) -> None:
    if output_format == "json":
        console.print_json(json.dumps(data, default=str))
        return

    if output_format == "yaml":
        console.print(yaml.safe_dump(data, sort_keys=False, default_flow_style=False))
        return

    if isinstance(data, list) and columns:
        _print_table(data, columns)
        return

    if isinstance(data, dict):
        table = Table(show_header=True, header_style="bold")
        table.add_column("key")
        table.add_column("value")
        for key, value in data.items():
            table.add_row(str(key), str(value))
        console.print(table)
        return

    console.print(data)


def _print_table(rows: Iterable[dict[str, Any]], columns: list[str]) -> None:
    table = Table(show_header=True, header_style="bold")
    for column in columns:
        table.add_column(column)

    for row in rows:
        table.add_row(*(str(row.get(column, "")) for column in columns))
    console.print(table)

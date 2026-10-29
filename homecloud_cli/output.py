"""Table, JSON, and YAML output helpers."""

from __future__ import annotations

import json
import sys
from typing import Any, Iterable

import yaml
from rich.console import Console
from rich.table import Table

console = Console()


def _project_row(row: dict[str, Any], fields: list[str] | None) -> dict[str, Any]:
    if not fields:
        return row
    return {key: row.get(key, "") for key in fields}


def emit(
    data: Any,
    *,
    output_format: str,
    columns: list[str] | None = None,
    fields: list[str] | None = None,
    wide: bool = False,
) -> None:
    if output_format == "jsonl":
        rows = data if isinstance(data, list) else [data]
        for row in rows:
            if not isinstance(row, dict):
                console.print(json.dumps(row, default=str))
                continue
            projected = _project_row(row, fields)
            sys.stdout.write(json.dumps(projected, default=str) + "\n")
        return

    if output_format == "json":
        if fields and isinstance(data, list):
            data = [_project_row(row, fields) if isinstance(row, dict) else row for row in data]
        elif fields and isinstance(data, dict):
            data = _project_row(data, fields)
        console.print_json(json.dumps(data, default=str))
        return

    if output_format == "yaml":
        console.print(yaml.safe_dump(data, sort_keys=False, default_flow_style=False))
        return

    if isinstance(data, list) and columns:
        table_columns = fields or columns
        if wide and not fields:
            table_columns = columns
        _print_table(data, table_columns)
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

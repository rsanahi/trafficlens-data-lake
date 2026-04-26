"""
Infrastructure adapter: implements TelemetryRepositoryPort using CSV files.

Canonical location: core/telemetry/adapters/csv_telemetry_repository.py
"""
from __future__ import annotations

import csv
import os

from core.telemetry.domain.ports.i_telemetry_ports import TelemetryRepositoryPort
from core.telemetry.domain.model import TelemetryRecord


class CsvTelemetryRepository(TelemetryRepositoryPort):
    """Saves TelemetryRecords to a CSV file and checks for existing files."""

    def save(self, records: list[TelemetryRecord], path: str) -> None:
        if not records:
            return

        print(f"Saving {len(records)} records to {path}...")
        os.makedirs(os.path.dirname(path), exist_ok=True)

        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=records[0].model_fields.keys())
            writer.writeheader()
            writer.writerows([r.model_dump() for r in records])

        print(f"Successfully saved to {path}")

    def exists(self, path: str) -> bool:
        return os.path.exists(path)

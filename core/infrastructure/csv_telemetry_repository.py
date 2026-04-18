"""
Infrastructure adapter: implements TelemetryRepositoryPort using CSV and JSON files.
"""
from __future__ import annotations

import csv
import json
import os

from core.domain.ports import TelemetryRepositoryPort
from core.domain.telemetry_record import TelemetryRecord


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

"""Reference data loading and Rf lookup for TLCid."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
import sqlite3
from typing import Any


def parse_rf(value: Any) -> float | None:
    """Convert database Rf values stored as percentages to 0..1 floats."""
    if value is None or value == "":
        return None
    try:
        return float(value) / 100.0
    except (TypeError, ValueError):
        return None


@dataclass(slots=True)
class ReferenceDataBundle:
    reference_data: list[dict[str, Any]] = field(default_factory=list)
    genus_to_substances: dict[str, set[str]] = field(default_factory=dict)
    family_to_substances: dict[str, set[str]] = field(default_factory=dict)
    reference_rf_by_name: dict[str, list[float | None]] = field(default_factory=dict)


class ReferenceRepository:
    """Loads TLC reference data from the configured SQLite database."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def set_database_path(self, db_path: str) -> None:
        self.db_path = db_path

    def load_reference_data(self) -> ReferenceDataBundle:
        bundle = ReferenceDataBundle()
        if not self.db_path or not os.path.exists(self.db_path):
            return bundle

        try:
            with sqlite3.connect(self.db_path) as conn:
                self._load_lichen_mappings(conn, bundle)
                self._load_substances(conn, bundle)
        except sqlite3.Error as exc:
            print(f"DEBUG: Could not load reference data from {self.db_path}: {exc}")
        return bundle

    def get_substance_rf(self, name: str) -> list[float | None] | None:
        if not name or not self.db_path or not os.path.exists(self.db_path):
            return None

        try:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.execute("SELECT A, Bprime, C FROM Substances WHERE name = ?", (name,))
                row = cur.fetchone()
        except sqlite3.Error:
            return None

        if row is None:
            return None
        return [parse_rf(row[0]), parse_rf(row[1]), parse_rf(row[2])]

    def _load_lichen_mappings(self, conn: sqlite3.Connection, bundle: ReferenceDataBundle) -> None:
        try:
            rows = conn.execute("SELECT DISTINCT Genus, Family, Substance FROM Lichens")
        except sqlite3.Error:
            print("DEBUG: Warning - Lichens table not available or empty. Genus/family filtering will not work.")
            return

        for genus, family, substance in rows:
            if genus and substance:
                bundle.genus_to_substances.setdefault(genus, set()).add(str(substance).lower())
            if family and substance:
                bundle.family_to_substances.setdefault(family, set()).add(str(substance).lower())

        print(
            f"DEBUG: Loaded {len(bundle.genus_to_substances)} genera and "
            f"{len(bundle.family_to_substances)} families with substance mappings from Lichens table"
        )

    def _load_substances(self, conn: sqlite3.Connection, bundle: ReferenceDataBundle) -> None:
        sql = """
            SELECT name, A, Bprime, C, GroupName, Lichens, BefVis, BefUVS, BefUVL, AftVis, AftUV
            FROM {table}
        """
        for table in ["Substances", "SubstancesBackup"]:
            try:
                rows = conn.execute(sql.format(table=table))
            except sqlite3.Error:
                continue

            for row in rows:
                name = row[0]
                rf_values = [parse_rf(row[1]), parse_rf(row[2]), parse_rf(row[3])]
                bundle.reference_data.append({
                    'name': name,
                    'rf': rf_values,
                    'GroupName': row[4],
                    'BefVis': row[6],
                    'BefUVS': row[7],
                    'BefUVL': row[8],
                    'AftVis': row[9],
                    'AftUV': row[10],
                })
                if name and name not in bundle.reference_rf_by_name:
                    bundle.reference_rf_by_name[name] = rf_values

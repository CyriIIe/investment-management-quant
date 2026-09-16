"""Tests du schéma SQLite et de son initialisation idempotente."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from db.database import create_database


EXPECTED_COLUMNS = {
    "bonds": {
        "secid",
        "isin",
        "nom",
        "type",
        "date_maturite",
        "taux_coupon",
    },
    "collection_runs": {
        "collection_run_id",
        "started_at",
        "completed_at",
        "status",
    },
    "snapshots": {
        "id",
        "collection_run_id",
        "secid",
        "timestamp",
        "prix",
        "rendement",
        "duration",
        "date_derniere_transaction",
        "volume",
        "nb_transactions",
        "bid",
        "ask",
    },
    "curve_runs": {
        "curve_run_id",
        "timestamp",
        "univers",
        "methode",
        "parametres",
        "rmse_bp",
        "n_bonds",
    },
    "curve_residuals": {
        "curve_run_id",
        "secid",
        "rendement_observe",
        "rendement_theorique",
        "residu_bp",
        "zscore",
        "liquidity_score",
        "eligible",
    },
}


class DatabaseSchemaTest(unittest.TestCase):
    def test_schema_is_created_and_can_be_reapplied(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "test.sqlite3"
            create_database(database_path)
            create_database(database_path)

            with sqlite3.connect(database_path) as connection:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
                self.assertTrue(EXPECTED_COLUMNS.keys() <= tables)

                for table, expected_columns in EXPECTED_COLUMNS.items():
                    columns = {
                        row[1]
                        for row in connection.execute(f"PRAGMA table_info({table})")
                    }
                    self.assertEqual(columns, expected_columns)

                indexes = {
                    row[1]
                    for row in connection.execute("PRAGMA index_list(snapshots)")
                }
                self.assertIn("idx_snapshots_secid_timestamp", indexes)
                self.assertIn("idx_snapshots_collection_run_secid", indexes)

                indexes = {
                    row[1]
                    for row in connection.execute("PRAGMA index_list(curve_residuals)")
                }
                self.assertIn("idx_curve_residuals_curve_run_id", indexes)

    def test_snapshots_append_between_runs_but_not_twice_in_one_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "test.sqlite3"
            create_database(database_path)

            with sqlite3.connect(database_path) as connection:
                connection.execute(
                    "INSERT INTO bonds (secid, nom, type) VALUES (?, ?, ?)",
                    ("SU0000000001", "Obligation de test", "OFZ-PD"),
                )
                for run_id, status in (("run-1", "completed"), ("run-2", "running")):
                    connection.execute(
                        "INSERT INTO collection_runs "
                        "(collection_run_id, started_at, status) VALUES (?, ?, ?)",
                        (run_id, "2026-09-16T00:00:00Z", status),
                    )
                    connection.execute(
                        "INSERT INTO snapshots "
                        "(collection_run_id, secid, timestamp, prix) VALUES (?, ?, ?, ?)",
                        (run_id, "SU0000000001", "2026-09-16T00:00:00Z", 100.0),
                    )

                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
                        "INSERT INTO snapshots "
                        "(collection_run_id, secid, timestamp, prix) VALUES (?, ?, ?, ?)",
                        ("run-1", "SU0000000001", "2026-09-16T00:01:00Z", 101.0),
                    )

                count = connection.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
                self.assertEqual(count, 2)

    def test_existing_snapshots_are_preserved_by_the_additive_migration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "legacy.sqlite3"
            with sqlite3.connect(database_path) as connection:
                connection.executescript(
                    """
                    CREATE TABLE snapshots (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        secid TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        prix REAL,
                        rendement REAL,
                        duration INTEGER,
                        date_derniere_transaction TEXT,
                        volume REAL,
                        nb_transactions INTEGER,
                        bid REAL,
                        ask REAL
                    );
                    INSERT INTO snapshots (secid, timestamp, prix)
                    VALUES ('SU0000000001', '2026-09-16T00:00:00Z', 100.0);
                    """
                )

            create_database(database_path)

            with sqlite3.connect(database_path) as connection:
                row = connection.execute(
                    "SELECT secid, prix, collection_run_id FROM snapshots"
                ).fetchone()
                self.assertEqual(row, ("SU0000000001", 100.0, None))


if __name__ == "__main__":
    unittest.main()

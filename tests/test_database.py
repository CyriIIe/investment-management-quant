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
    "snapshots": {
        "id",
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

                indexes = {
                    row[1]
                    for row in connection.execute("PRAGMA index_list(curve_residuals)")
                }
                self.assertIn("idx_curve_residuals_curve_run_id", indexes)


if __name__ == "__main__":
    unittest.main()

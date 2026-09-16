"""Tests sans réseau de la sélection de liquidité."""

from __future__ import annotations

import logging
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import settings
from db.database import create_database
from universe import select_eligible_universe, store_liquidity_selection


class EligibleUniverseTest(unittest.TestCase):
    def test_unverified_trademoment_uses_session_activity_without_claiming_minute_freshness(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "test.sqlite3"
            create_database(database_path)
            with sqlite3.connect(database_path) as connection:
                connection.execute("PRAGMA foreign_keys = ON")
                connection.execute("INSERT INTO bonds (secid, nom, type) VALUES ('ACTIVE', 'Active', 'OFZ-PD')")
                connection.execute("INSERT INTO collection_runs (collection_run_id, started_at, status) VALUES ('done', ?, 'completed')", ("2026-09-16T00:00:00+00:00",))
                connection.execute(
                    """INSERT INTO snapshots (collection_run_id, secid, timestamp, date_derniere_transaction,
                       volume, nb_transactions, bid, ask) VALUES ('done', 'ACTIVE', ?, ?, 1000, 5, 100, 100.1)""",
                    ("2026-09-16T12:00:00+00:00", "2026-09-16 15:00:00"),
                )
                connection.commit()
            with patch.multiple(
                settings,
                TRADEMOMENT_IS_VERIFIED_LAST_TRANSACTION=False,
                USE_SESSION_ACTIVITY_WHEN_TRADE_TIMESTAMP_UNVERIFIED=True,
            ):
                selection = select_eligible_universe(
                    str(database_path), "2026-09-16T12:00:00+00:00"
                )[0]
            self.assertTrue(selection.eligible)
            self.assertIn("date_derniere_transaction_non_verifiee", selection.unavailable_data)

    def test_uses_only_completed_cycles_and_distinguishes_missing_from_zero(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "test.sqlite3"
            create_database(database_path)
            with sqlite3.connect(database_path) as connection:
                connection.execute("PRAGMA foreign_keys = ON")
                connection.executemany(
                    "INSERT INTO bonds (secid, nom, type) VALUES (?, ?, ?)",
                    [
                        ("GOOD", "Good", "OFZ-PD"),
                        ("MISSING", "Missing", "OFZ-PD"),
                        ("ZERO", "Zero", "OFZ-PD"),
                        ("RUNNING", "Running", "OFZ-PD"),
                        ("PK", "Floating", "OFZ-PK"),
                    ],
                )
                connection.executemany(
                    "INSERT INTO collection_runs (collection_run_id, started_at, status) VALUES (?, ?, ?)",
                    [("complete", "2026-09-16T00:00:00+00:00", "completed"), ("partial", "2026-09-16T00:00:00+00:00", "running")],
                )
                connection.executemany(
                    """
                    INSERT INTO snapshots (
                        collection_run_id, secid, timestamp, date_derniere_transaction,
                        volume, nb_transactions, bid, ask
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        ("complete", "GOOD", "2026-09-16T12:00:00+00:00", "2026-09-16T11:00:00+00:00", 1000, 5, 100.0, 100.1),
                        ("complete", "MISSING", "2026-09-16T12:00:00+00:00", "2026-09-16T11:00:00+00:00", None, 5, 100.0, 100.1),
                        ("complete", "ZERO", "2026-09-16T12:00:00+00:00", "2026-09-16T11:00:00+00:00", 0, 5, 100.0, 100.1),
                        ("complete", "PK", "2026-09-16T12:00:00+00:00", "2026-09-16T11:00:00+00:00", 1000, 5, 100.0, 100.1),
                        ("partial", "RUNNING", "2026-09-16T12:00:00+00:00", "2026-09-16T11:00:00+00:00", 1000, 5, 100.0, 100.1),
                    ],
                )
                connection.execute(
                    """
                    INSERT INTO curve_runs (curve_run_id, timestamp, univers, methode, parametres, n_bonds)
                    VALUES ('curve-1', '2026-09-16T12:00:00+00:00', 'OFZ-PD', 'test', '{}', 0)
                    """
                )
                connection.commit()

                with patch("universe.settings.TRADEMOMENT_IS_VERIFIED_LAST_TRANSACTION", True):
                    with self.assertLogs("universe", level=logging.INFO) as logs:
                        selections = select_eligible_universe(
                            str(database_path), "2026-09-16T12:00:00+00:00"
                        )

                by_secid = {selection.secid: selection for selection in selections}
                self.assertEqual(set(by_secid), {"GOOD", "MISSING", "ZERO"})
                self.assertTrue(by_secid["GOOD"].eligible)
                self.assertFalse(by_secid["MISSING"].eligible)
                self.assertIn("volume_absent", by_secid["MISSING"].unavailable_data)
                self.assertFalse(by_secid["ZERO"].eligible)
                self.assertIn("volume_session_insuffisant", by_secid["ZERO"].rejection_reasons)
                self.assertTrue(any("Donnée indisponible volume_absent" in line for line in logs.output))

                store_liquidity_selection(connection, "curve-1", selections)
                stored = dict(connection.execute(
                    "SELECT secid, eligible FROM curve_residuals WHERE curve_run_id = 'curve-1'"
                ))
                self.assertEqual(stored, {"GOOD": 1, "MISSING": 0, "ZERO": 0})

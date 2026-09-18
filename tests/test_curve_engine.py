"""Tests sans réseau du fit robuste et de ses garde-fous."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

import curve_engine
from config import settings
from curve_engine import CurveEnginePreconditionError, fit_robust_curve, robust_zscore
from db.database import create_database


class CurveEngineTest(unittest.TestCase):
    def test_refuses_unverified_market_conventions(self) -> None:
        with patch.multiple(
            settings,
            YIELD_UNIT_VERIFIED=False,
            DURATION_UNIT_VERIFIED=False,
            PRICE_CONVENTION_VERIFIED=False,
        ):
            with self.assertRaises(CurveEnginePreconditionError):
                curve_engine.validate_market_conventions()

    def test_robust_fit_and_residual_units_are_basis_points(self) -> None:
        durations = np.arange(1, settings.MIN_ELIGIBLE_BONDS_FOR_CURVE + 1, dtype=float)
        yields = 10.0 + 0.05 * durations
        fit = fit_robust_curve(durations, yields)
        residual_bp = (yields - fit.predict(durations)) * settings.BASIS_POINTS_PER_PERCENT
        self.assertLess(fit.rmse_bp, 0.0001)
        self.assertTrue(np.all(np.abs(residual_bp) < 0.0001))

    def test_zscore_is_null_when_own_history_is_insufficient(self) -> None:
        history = [1.0] * (settings.MIN_RESIDUAL_HISTORY_POINTS - 1)
        self.assertIsNone(robust_zscore(5.0, history))

    def test_stops_when_too_few_ofz_pd_are_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "curve.sqlite3"
            create_database(database_path)
            with sqlite3.connect(database_path) as connection:
                connection.execute("PRAGMA foreign_keys = ON")
                connection.execute("INSERT INTO bonds (secid, nom, type) VALUES ('ONE', 'One', 'OFZ-PD')")
                connection.execute(
                    "INSERT INTO collection_runs (collection_run_id, started_at, status) VALUES ('done', ?, 'completed')",
                    ("2026-09-16T00:00:00+00:00",),
                )
                connection.execute(
                    """INSERT INTO snapshots (collection_run_id, secid, timestamp,
                       date_derniere_transaction, volume, nb_transactions, bid, ask, rendement, duration)
                       VALUES ('done', 'ONE', ?, ?, 1000, 5, 100, 100.1, 10, 365)""",
                    ("2026-09-16T12:00:00+00:00", "2026-09-16T11:00:00+00:00"),
                )
                connection.commit()
            with patch.multiple(
                settings,
                YIELD_UNIT_VERIFIED=True,
                DURATION_UNIT_VERIFIED=True,
                PRICE_CONVENTION_VERIFIED=True,
                TRADEMOMENT_IS_VERIFIED_LAST_TRANSACTION=True,
                DATABASE_PATH=database_path,
            ):
                with self.assertRaises(CurveEnginePreconditionError):
                    curve_engine.run_curve_engine("2026-09-16T12:00:00+00:00")

    def test_observations_do_not_mix_collection_cycles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "curve.sqlite3"
            create_database(database_path)
            with sqlite3.connect(database_path) as connection:
                connection.execute("PRAGMA foreign_keys = ON")
                connection.executemany(
                    "INSERT INTO bonds (secid, nom, type) VALUES (?, ?, 'OFZ-PD')",
                    [("CURRENT", "Current"), ("STALE", "Stale")],
                )
                connection.executemany(
                    "INSERT INTO collection_runs (collection_run_id, started_at, status) VALUES (?, ?, 'completed')",
                    [("previous", "2026-09-16T00:00:00+00:00"), ("current", "2026-09-17T00:00:00+00:00")],
                )
                connection.executemany(
                    """INSERT INTO snapshots (collection_run_id, secid, timestamp, rendement, duration)
                       VALUES (?, ?, ?, 10.0, 365)""",
                    [
                        ("previous", "CURRENT", "2026-09-16T12:00:00+00:00"),
                        ("previous", "STALE", "2026-09-16T12:00:00+00:00"),
                        ("current", "CURRENT", "2026-09-17T12:00:00+00:00"),
                    ],
                )
                observations = curve_engine._latest_completed_observations(connection, "current")
            self.assertEqual([row["secid"] for row in observations], ["CURRENT"])

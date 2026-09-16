"""Test sans réseau de relecture des TOP 10 historiques."""

from __future__ import annotations

import io
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from db.database import create_database
from review_top10 import review_date


class ReviewTop10Test(unittest.TestCase):
    def test_displays_stored_run_and_orders_residuals_by_absolute_value(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "review.sqlite3"
            create_database(database_path)
            with sqlite3.connect(database_path) as connection:
                connection.executemany(
                    "INSERT INTO bonds (secid, nom, type) VALUES (?, ?, 'OFZ-PD')",
                    [("LOW", "Low residual"), ("HIGH", "High residual")],
                )
                connection.execute(
                    """INSERT INTO curve_runs
                    (curve_run_id, timestamp, univers, methode, parametres, rmse_bp, n_bonds)
                    VALUES ('run-1', '2026-09-16T12:00:00+00:00', 'OFZ-PD', 'robust', '{}', 12.5, 2)"""
                )
                connection.executemany(
                    """INSERT INTO curve_residuals
                    (curve_run_id, secid, rendement_observe, rendement_theorique,
                     residu_bp, zscore, liquidity_score, eligible)
                    VALUES ('run-1', ?, 10, 10, ?, NULL, 0.9, 1)""",
                    [("LOW", 5.0), ("HIGH", -25.0)],
                )

            output = io.StringIO()
            with redirect_stdout(output):
                review_date("2026-09-16", database_path)
            rendered = output.getvalue()
            self.assertIn("Curve run: run-1", rendered)
            self.assertIn("Méthode: robust", rendered)
            self.assertIn("RMSE: 12.50 bp", rendered)
            self.assertLess(rendered.index("HIGH"), rendered.index("LOW"))

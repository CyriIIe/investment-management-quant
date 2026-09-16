#!/usr/bin/env python3
"""Réaffiche les TOP 10 historiques enregistrés pour une date donnée."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings


def review_date(review_date: str, database_path: str | Path = settings.DATABASE_PATH) -> int:
    """Affiche chaque curve run de la date et ses dix plus grands résidus."""
    with sqlite3.connect(database_path) as connection:
        runs = connection.execute(
            """
            SELECT curve_run_id, timestamp, methode, parametres, rmse_bp, n_bonds
            FROM curve_runs
            WHERE substr(timestamp, 1, 10) = ?
            ORDER BY timestamp
            """,
            (review_date,),
        ).fetchall()

        if not runs:
            print(f"Aucun curve run enregistré pour le {review_date}.")
            return 0

        for run_id, timestamp, method, parameters, rmse_bp, n_bonds in runs:
            print(f"\nCurve run: {run_id}")
            print(f"Timestamp: {timestamp}")
            print(f"Méthode: {method}")
            print(f"Paramètres: {parameters}")
            print(f"RMSE: {rmse_bp:.2f} bp | Obligations utilisées: {n_bonds}")
            print("SECID          NOM                  OBS. YLD  THEO. YLD  RESIDU BP   Z-SCORE  LIQUIDITY")
            residuals = connection.execute(
                """
                SELECT residuals.secid, bonds.nom, residuals.rendement_observe,
                       residuals.rendement_theorique, residuals.residu_bp,
                       residuals.zscore, residuals.liquidity_score
                FROM curve_residuals AS residuals
                JOIN bonds ON bonds.secid = residuals.secid
                WHERE residuals.curve_run_id = ? AND residuals.residu_bp IS NOT NULL
                ORDER BY ABS(residuals.residu_bp) DESC
                LIMIT 10
                """,
                (run_id,),
            ).fetchall()
            for secid, name, observed, theoretical, residual_bp, zscore, score in residuals:
                zscore_text = "NULL" if zscore is None else f"{zscore:.2f}"
                print(
                    f"{secid:<14} {name[:20]:<20} {observed:>8.4f} {theoretical:>9.4f} "
                    f"{residual_bp:>10.2f} {zscore_text:>8} {score:>10.2f}"
                )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Relire les TOP 10 historiques de courbe.")
    parser.add_argument("date", help="Date au format YYYY-MM-DD")
    arguments = parser.parse_args()
    return review_date(arguments.date)


if __name__ == "__main__":
    raise SystemExit(main())

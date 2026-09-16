"""Fit robuste de la courbe souveraine OFZ-PD et calcul des écarts."""

from __future__ import annotations

import json
import logging
import sqlite3
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np
from scipy.optimize import least_squares

from config import settings
from universe import LiquiditySelection, select_eligible_universe, store_liquidity_selection


LOGGER = logging.getLogger(__name__)


class CurveEnginePreconditionError(RuntimeError):
    """Le fit ne peut pas être exécuté avec les données ou vérifications actuelles."""


@dataclass(frozen=True)
class CurveFit:
    coefficients: np.ndarray
    duration_center: float
    duration_scale: float
    rmse_bp: float

    def predict(self, durations: np.ndarray) -> np.ndarray:
        return np.polyval(self.coefficients, (durations - self.duration_center) / self.duration_scale)


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _configure_logging() -> None:
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", stream=sys.stdout)


def validate_market_conventions() -> None:
    missing = [
        name
        for name, verified in (
            ("unité des rendements", settings.YIELD_UNIT_VERIFIED),
            ("unité des durations", settings.DURATION_UNIT_VERIFIED),
            ("convention de prix", settings.PRICE_CONVENTION_VERIFIED),
        )
        if not verified
    ]
    if missing:
        raise CurveEnginePreconditionError(
            "Fit refusé : " + ", ".join(missing) + " non vérifiée(s). "
            "Voir docs/moex-fields.md et config/settings.py."
        )


def fit_robust_curve(durations: np.ndarray, yields: np.ndarray) -> CurveFit:
    if len(durations) < settings.MIN_ELIGIBLE_BONDS_FOR_CURVE:
        raise CurveEnginePreconditionError("Nombre insuffisant d'OFZ-PD éligibles pour le fit.")
    if np.any(durations <= 0):
        raise CurveEnginePreconditionError("Duration non positive dans l'univers éligible.")

    center = float(np.mean(durations))
    scale = float(np.std(durations))
    if scale == 0:
        raise CurveEnginePreconditionError("Les durations éligibles sont toutes identiques.")
    x = (durations - center) / scale
    initial = np.polyfit(x, yields, settings.CURVE_POLYNOMIAL_DEGREE)
    result = least_squares(
        lambda coefficients: np.polyval(coefficients, x) - yields,
        initial,
        loss=settings.CURVE_ROBUST_LOSS,
        f_scale=settings.CURVE_ROBUST_F_SCALE,
    )
    predictions = np.polyval(result.x, x)
    residuals_bp = (yields - predictions) * settings.BASIS_POINTS_PER_PERCENT
    return CurveFit(
        coefficients=result.x,
        duration_center=center,
        duration_scale=scale,
        rmse_bp=float(np.sqrt(np.mean(np.square(residuals_bp)))),
    )


def robust_zscore(residual_bp: float, history: list[float]) -> float | None:
    if len(history) < settings.MIN_RESIDUAL_HISTORY_POINTS:
        return None
    median = float(np.median(history))
    mad = float(np.median(np.abs(np.asarray(history) - median)))
    if mad == 0:
        return None
    return (residual_bp - median) / (settings.ROBUST_MAD_SCALE * mad)


def _latest_completed_observations(connection: sqlite3.Connection, timestamp: str) -> list[dict]:
    cursor = connection.execute(
        """
        WITH latest AS (
            SELECT snapshots.*, ROW_NUMBER() OVER (
                PARTITION BY snapshots.secid ORDER BY snapshots.timestamp DESC, snapshots.id DESC
            ) AS row_number
            FROM snapshots JOIN collection_runs
              ON collection_runs.collection_run_id = snapshots.collection_run_id
            WHERE collection_runs.status = 'completed' AND snapshots.timestamp <= ?
        )
        SELECT latest.*, bonds.nom, bonds.type FROM latest JOIN bonds ON bonds.secid = latest.secid
        WHERE latest.row_number = 1 AND bonds.type = 'OFZ-PD'
        """,
        (timestamp,),
    )
    columns = [item[0] for item in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _historical_residuals(connection: sqlite3.Connection, secid: str) -> list[float]:
    return [
        row[0]
        for row in connection.execute(
            "SELECT residu_bp FROM curve_residuals WHERE secid = ? AND residu_bp IS NOT NULL",
            (secid,),
        )
    ]


def _print_top(results: list[dict], fit: CurveFit, observations: list[dict]) -> None:
    top = sorted(results, key=lambda item: abs(item["residu_bp"]), reverse=True)[: settings.TOP_RESIDUALS_COUNT]
    print("SECID          NOM                  OBS. YLD  THEO. YLD  RESIDU BP   Z-SCORE  LIQUIDITY")
    for item in top:
        zscore = "NULL" if item["zscore"] is None else f"{item['zscore']:.2f}"
        print(
            f"{item['secid']:<14} {item['nom'][:20]:<20} {item['rendement_observe']:>8.4f} "
            f"{item['rendement_theorique']:>9.4f} {item['residu_bp']:>10.2f} "
            f"{zscore:>8} {item['liquidity_score']:>10.2f}"
        )
    for item in top:
        loo = [row for row in observations if row["secid"] != item["secid"]]
        if len(loo) < settings.MIN_ELIGIBLE_BONDS_FOR_CURVE:
            continue
        loo_fit = fit_robust_curve(
            np.asarray([row["duration"] for row in loo], dtype=float),
            np.asarray([row["rendement"] for row in loo], dtype=float),
        )
        reference = float(loo_fit.predict(np.asarray([item["duration"]], dtype=float))[0])
        loo_residual_bp = (item["rendement_observe"] - reference) * settings.BASIS_POINTS_PER_PERCENT
        LOGGER.info("Leave-one-out %s: résidu de référence %.2f bp", item["secid"], loo_residual_bp)


def run_curve_engine(calculation_timestamp: str | None = None) -> str:
    """Exécute un fit unique sur les OFZ-PD liquides des cycles terminés."""
    _configure_logging()
    validate_market_conventions()
    timestamp = calculation_timestamp or _timestamp()
    selections = select_eligible_universe(str(settings.DATABASE_PATH), timestamp)
    eligible_scores = {item.secid: item for item in selections if item.eligible}

    with sqlite3.connect(settings.DATABASE_PATH) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        observations = [
            row
            for row in _latest_completed_observations(connection, timestamp)
            if row["secid"] in eligible_scores
            and row["rendement"] is not None
            and row["duration"] is not None
        ]
        missing_market = len(eligible_scores) - len(observations)
        if missing_market:
            LOGGER.info("Exclusion fit: %d obligation(s) sans rendement ou duration disponible", missing_market)
        if len(observations) < settings.MIN_ELIGIBLE_BONDS_FOR_CURVE:
            raise CurveEnginePreconditionError(
                f"Fit arrêté : {len(observations)} OFZ-PD éligibles, minimum requis "
                f"{settings.MIN_ELIGIBLE_BONDS_FOR_CURVE}."
            )

        durations = np.asarray([row["duration"] for row in observations], dtype=float)
        yields = np.asarray([row["rendement"] for row in observations], dtype=float)
        fit = fit_robust_curve(durations, yields)
        predictions = fit.predict(durations)
        run_id = str(uuid.uuid4())
        parameters = json.dumps(
            {
                "library": "scipy.optimize.least_squares",
                "loss": settings.CURVE_ROBUST_LOSS,
                "f_scale": settings.CURVE_ROBUST_F_SCALE,
                "polynomial_degree": settings.CURVE_POLYNOMIAL_DEGREE,
                "duration_unit": settings.DURATION_UNIT,
                "yield_unit": settings.YIELD_UNIT,
            },
            sort_keys=True,
        )
        results = []
        for row, theoretical in zip(observations, predictions, strict=True):
            observed = float(row["rendement"])
            residual_bp = (observed - float(theoretical)) * settings.BASIS_POINTS_PER_PERCENT
            results.append(
                {
                    "secid": row["secid"], "nom": row["nom"], "duration": row["duration"],
                    "rendement_observe": observed, "rendement_theorique": float(theoretical),
                    "residu_bp": residual_bp,
                    "zscore": robust_zscore(residual_bp, _historical_residuals(connection, row["secid"])),
                    "liquidity_score": eligible_scores[row["secid"]].liquidity_score,
                }
            )
        with connection:
            connection.execute(
                """INSERT INTO curve_runs (curve_run_id, timestamp, univers, methode, parametres, rmse_bp, n_bonds)
                   VALUES (?, ?, 'OFZ-PD', 'robust_polynomial_duration', ?, ?, ?)""",
                (run_id, timestamp, parameters, fit.rmse_bp, len(observations)),
            )
            store_liquidity_selection(connection, run_id, selections)
            connection.executemany(
                """UPDATE curve_residuals SET rendement_observe=?, rendement_theorique=?, residu_bp=?, zscore=?
                   WHERE curve_run_id=? AND secid=?""",
                [
                    (item["rendement_observe"], item["rendement_theorique"], item["residu_bp"], item["zscore"], run_id, item["secid"])
                    for item in results
                ],
            )
    LOGGER.info("Qualité du fit: RMSE %.2f bp (%d obligations)", fit.rmse_bp, len(observations))
    _print_top(results, fit, observations)
    return run_id


if __name__ == "__main__":
    try:
        run_curve_engine()
    except CurveEnginePreconditionError as error:
        LOGGER.error("%s", error)
        raise SystemExit(1)

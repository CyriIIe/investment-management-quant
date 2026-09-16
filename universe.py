"""Sélection configurable de l'univers liquide pour le moteur de courbe."""

from __future__ import annotations

import logging
import sqlite3
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from config import settings


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class LiquiditySelection:
    secid: str
    liquidity_score: float
    eligible: bool
    rejection_reasons: tuple[str, ...]
    unavailable_data: tuple[str, ...]


def _configure_console_logging() -> None:
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(levelname)s %(message)s",
            stream=sys.stdout,
        )


def _as_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _latest_completed_snapshots(
    connection: sqlite3.Connection, calculation_timestamp: str
) -> list[dict[str, Any]]:
    cursor = connection.execute(
        """
        WITH ranked_snapshots AS (
            SELECT
                snapshots.*,
                ROW_NUMBER() OVER (
                    PARTITION BY snapshots.secid
                    ORDER BY snapshots.timestamp DESC, snapshots.id DESC
                ) AS row_number
            FROM snapshots
            JOIN collection_runs
                ON collection_runs.collection_run_id = snapshots.collection_run_id
            JOIN bonds ON bonds.secid = snapshots.secid
            WHERE collection_runs.status = 'completed'
              AND bonds.type = 'OFZ-PD'
              AND snapshots.timestamp <= ?
        )
        SELECT * FROM ranked_snapshots WHERE row_number = 1
        """,
        (calculation_timestamp,),
    )
    columns = [description[0] for description in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _selection_for_snapshot(
    snapshot: dict[str, Any], calculation_timestamp: str
) -> LiquiditySelection:
    rejection_reasons: list[str] = []
    unavailable_data: list[str] = []
    scores: list[float] = []

    last_transaction = snapshot["date_derniere_transaction"]
    if not settings.TRADEMOMENT_IS_VERIFIED_LAST_TRANSACTION:
        unavailable_data.append("date_derniere_transaction_non_verifiee")
        if not settings.USE_SESSION_ACTIVITY_WHEN_TRADE_TIMESTAMP_UNVERIFIED:
            rejection_reasons.append("date_derniere_transaction_non_verifiee")
    elif last_transaction is None:
        unavailable_data.append("date_derniere_transaction_absente")
        if settings.REJECT_IF_REQUIRED_LIQUIDITY_DATA_UNAVAILABLE:
            rejection_reasons.append("date_derniere_transaction_absente")
    else:
        age_days = ( _as_utc(calculation_timestamp) - _as_utc(last_transaction) ).total_seconds() / 86400
        if age_days < 0:
            rejection_reasons.append("date_derniere_transaction_future")
            scores.append(0.0)
        else:
            scores.append(max(0.0, 1.0 - age_days / settings.MAX_DAYS_SINCE_LAST_TRANSACTION))
            if age_days > settings.MAX_DAYS_SINCE_LAST_TRANSACTION:
                rejection_reasons.append("derniere_transaction_trop_ancienne")

    volume = snapshot["volume"]
    if volume is None:
        unavailable_data.append("volume_absent")
        if settings.REJECT_IF_REQUIRED_LIQUIDITY_DATA_UNAVAILABLE:
            rejection_reasons.append("volume_absent")
    else:
        scores.append(min(1.0, volume / settings.MIN_SESSION_VOLUME))
        if volume < settings.MIN_SESSION_VOLUME:
            rejection_reasons.append("volume_session_insuffisant")

    transactions = snapshot["nb_transactions"]
    if transactions is None:
        unavailable_data.append("nb_transactions_absent")
        if settings.REJECT_IF_REQUIRED_LIQUIDITY_DATA_UNAVAILABLE:
            rejection_reasons.append("nb_transactions_absent")
    else:
        scores.append(min(1.0, transactions / settings.MIN_SESSION_TRANSACTIONS))
        if transactions < settings.MIN_SESSION_TRANSACTIONS:
            rejection_reasons.append("nb_transactions_insuffisant")

    if (
        not settings.TRADEMOMENT_IS_VERIFIED_LAST_TRANSACTION
        and settings.USE_SESSION_ACTIVITY_WHEN_TRADE_TIMESTAMP_UNVERIFIED
        and settings.REQUIRE_POSITIVE_SESSION_ACTIVITY
        and (volume is None or transactions is None or volume <= 0 or transactions <= 0)
    ):
        rejection_reasons.append("activite_session_non_confirmee")

    bid, ask = snapshot["bid"], snapshot["ask"]
    if bid is None or ask is None:
        unavailable_data.append("spread_absent")
    elif ask < bid:
        rejection_reasons.append("spread_bid_ask_invalide")
        scores.append(0.0)
    else:
        spread = ask - bid
        scores.append(max(0.0, 1.0 - spread / settings.MAX_BID_ASK_SPREAD))
        if spread > settings.MAX_BID_ASK_SPREAD:
            rejection_reasons.append("spread_bid_ask_trop_large")

    liquidity_score = sum(scores) / len(scores) if scores else 0.0
    return LiquiditySelection(
        secid=snapshot["secid"],
        liquidity_score=max(0.0, min(1.0, liquidity_score)),
        eligible=not rejection_reasons,
        rejection_reasons=tuple(rejection_reasons),
        unavailable_data=tuple(unavailable_data),
    )


def select_eligible_universe(
    database_path: str = str(settings.DATABASE_PATH),
    calculation_timestamp: str | None = None,
) -> list[LiquiditySelection]:
    """Filtre les derniers snapshots de cycles complets disponibles à cet instant."""
    _configure_console_logging()
    timestamp = calculation_timestamp or datetime.now(UTC).isoformat(timespec="seconds")
    with sqlite3.connect(database_path) as connection:
        snapshots = _latest_completed_snapshots(connection, timestamp)

    selections = [_selection_for_snapshot(snapshot, timestamp) for snapshot in snapshots]
    eligible_count = sum(selection.eligible for selection in selections)
    LOGGER.info(
        "Univers de courbe: %d obligations éligibles, %d écartées",
        eligible_count,
        len(selections) - eligible_count,
    )
    for reason, count in sorted(
        Counter(reason for selection in selections for reason in selection.rejection_reasons).items()
    ):
        LOGGER.info("Rejet %s: %d", reason, count)
    for data_name, count in sorted(
        Counter(data for selection in selections for data in selection.unavailable_data).items()
    ):
        LOGGER.info("Donnée indisponible %s: %d", data_name, count)
    return selections


def store_liquidity_selection(
    connection: sqlite3.Connection,
    curve_run_id: str,
    selections: list[LiquiditySelection],
) -> None:
    """Stocke le score et l'éligibilité pour chaque obligation du run de courbe."""
    connection.executemany(
        """
        INSERT INTO curve_residuals (curve_run_id, secid, liquidity_score, eligible)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(curve_run_id, secid) DO UPDATE SET
            liquidity_score = excluded.liquidity_score,
            eligible = excluded.eligible
        """,
        [
            (curve_run_id, item.secid, item.liquidity_score, int(item.eligible))
            for item in selections
        ],
    )

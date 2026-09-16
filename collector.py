#!/usr/bin/env python3
"""Collecte ponctuelle des OFZ-PD MOEX ISS vers SQLite."""

from __future__ import annotations

import logging
import sqlite3
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import requests

from config import settings
from db.database import create_database


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class BondRecord:
    secid: str
    isin: str | None
    nom: str
    bond_type: str
    date_maturite: str | None
    taux_coupon: float | None


@dataclass(frozen=True)
class SnapshotRecord:
    secid: str
    timestamp: str
    prix: float | None
    rendement: float | None
    duration: int | None
    date_derniere_transaction: str | None
    volume: float | None
    nb_transactions: int | None
    bid: float | None
    ask: float | None


class ISSRequestError(RuntimeError):
    """L'API ISS est indisponible après les tentatives configurées."""


def utc_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def table_records(payload: dict[str, Any], block: str) -> list[dict[str, Any]]:
    table = payload.get(block, {})
    columns = table.get("columns", [])
    return [dict(zip(columns, row)) for row in table.get("data", [])]


def is_ofz_pd(security: dict[str, Any]) -> bool:
    """Utilise le libellé OFZ-PD réellement observé dans LATNAME/SECNAME."""
    labels = (security.get("LATNAME"), security.get("SECNAME"))
    return any(
        label and ("OFZ-PD" in label.upper() or "ОФЗ-ПД" in label.upper())
        for label in labels
    )


def parse_ofz_pd_payload(
    payload: dict[str, Any], collection_timestamp: str
) -> tuple[list[BondRecord], list[SnapshotRecord]]:
    """Extrait les OFZ-PD et leurs valeurs observées sans appel réseau."""
    marketdata_by_secid = {
        row["SECID"]: row for row in table_records(payload, "marketdata") if row.get("SECID")
    }
    yields_by_secid = {
        row["SECID"]: row
        for row in table_records(payload, "marketdata_yields")
        if row.get("SECID")
    }

    bonds: list[BondRecord] = []
    snapshots: list[SnapshotRecord] = []
    for security in table_records(payload, "securities"):
        if not security.get("SECID") or not is_ofz_pd(security):
            continue

        secid = security["SECID"]
        bonds.append(
            BondRecord(
                secid=secid,
                isin=security.get("ISIN"),
                nom=security.get("SECNAME") or security.get("LATNAME") or secid,
                bond_type="OFZ-PD",
                date_maturite=security.get("MATDATE"),
                taux_coupon=security.get("COUPONPERCENT"),
            )
        )

        marketdata = marketdata_by_secid.get(secid, {})
        yield_data = yields_by_secid.get(secid, {})
        snapshots.append(
            SnapshotRecord(
                secid=secid,
                timestamp=collection_timestamp,
                prix=marketdata.get("LAST"),
                rendement=yield_data.get("EFFECTIVEYIELD"),
                duration=yield_data.get("DURATION"),
                date_derniere_transaction=yield_data.get("TRADEMOMENT"),
                volume=marketdata.get("VOLTODAY"),
                nb_transactions=marketdata.get("NUMTRADES"),
                bid=marketdata.get("BID"),
                ask=marketdata.get("OFFER"),
            )
        )
    return bonds, snapshots


class ISSClient:
    def __init__(self) -> None:
        self._last_request_at: float | None = None

    def _respect_rate_limit(self) -> None:
        if self._last_request_at is None:
            return
        elapsed = time.monotonic() - self._last_request_at
        delay = max(0.0, settings.REQUEST_INTERVAL_SECONDS - elapsed)
        if delay:
            LOGGER.info("ISS rate limit: sleep %.2fs", delay)
            time.sleep(delay)

    def fetch_tqob_securities(self) -> dict[str, Any]:
        for attempt in range(1, settings.MAX_RETRY_ATTEMPTS + 1):
            self._respect_rate_limit()
            self._last_request_at = time.monotonic()
            try:
                response = requests.get(
                    f"{settings.ISS_BASE_URL}{settings.TQOB_SECURITIES_ENDPOINT}",
                    timeout=settings.REQUEST_TIMEOUT_SECONDS,
                )
                response.raise_for_status()
                payload = response.json()
                required_blocks = {"securities", "marketdata", "marketdata_yields"}
                if not isinstance(payload, dict) or not required_blocks <= payload.keys():
                    raise ValueError("réponse ISS incomplète")
                return payload
            except (requests.RequestException, ValueError) as error:
                if attempt == settings.MAX_RETRY_ATTEMPTS:
                    raise ISSRequestError(
                        f"ISS indisponible après {attempt} tentative(s): {error}"
                    ) from error
                backoff = settings.RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1))
                LOGGER.warning(
                    "ISS tentative %d/%d échouée: %s; retry dans %.1fs",
                    attempt,
                    settings.MAX_RETRY_ATTEMPTS,
                    error,
                    backoff,
                )
                time.sleep(backoff)
        raise AssertionError("Boucle de retry inattendue")


def record_failed_cycle(run_id: str, started_at: str) -> None:
    """Conserve la trace d'un cycle incomplet, sans snapshot partiel."""
    create_database(settings.DATABASE_PATH)
    with sqlite3.connect(settings.DATABASE_PATH) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            """
            INSERT INTO collection_runs (collection_run_id, started_at, completed_at, status)
            VALUES (?, ?, ?, 'failed')
            """,
            (run_id, started_at, utc_timestamp()),
        )


def persist_successful_cycle(
    run_id: str,
    started_at: str,
    bonds: list[BondRecord],
    snapshots: list[SnapshotRecord],
) -> None:
    """Insère un cycle entier dans une seule transaction SQLite."""
    create_database(settings.DATABASE_PATH)
    with sqlite3.connect(settings.DATABASE_PATH) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        with connection:
            connection.execute(
                """
                INSERT INTO collection_runs (collection_run_id, started_at, status)
                VALUES (?, ?, 'running')
                """,
                (run_id, started_at),
            )
            connection.executemany(
                """
                INSERT INTO bonds (secid, isin, nom, type, date_maturite, taux_coupon)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(secid) DO UPDATE SET
                    isin = excluded.isin,
                    nom = excluded.nom,
                    type = excluded.type,
                    date_maturite = excluded.date_maturite,
                    taux_coupon = excluded.taux_coupon
                """,
                [
                    (
                        bond.secid,
                        bond.isin,
                        bond.nom,
                        bond.bond_type,
                        bond.date_maturite,
                        bond.taux_coupon,
                    )
                    for bond in bonds
                ],
            )
            connection.executemany(
                """
                INSERT INTO snapshots (
                    collection_run_id, secid, timestamp, prix, rendement, duration,
                    date_derniere_transaction, volume, nb_transactions, bid, ask
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        run_id,
                        snapshot.secid,
                        snapshot.timestamp,
                        snapshot.prix,
                        snapshot.rendement,
                        snapshot.duration,
                        snapshot.date_derniere_transaction,
                        snapshot.volume,
                        snapshot.nb_transactions,
                        snapshot.bid,
                        snapshot.ask,
                    )
                    for snapshot in snapshots
                ],
            )
            connection.execute(
                """
                UPDATE collection_runs
                SET completed_at = ?, status = 'completed'
                WHERE collection_run_id = ?
                """,
                (utc_timestamp(), run_id),
            )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", stream=sys.stdout)
    run_id = str(uuid.uuid4())
    started_at = utc_timestamp()
    LOGGER.info("Cycle de collecte %s démarré", run_id)

    try:
        payload = ISSClient().fetch_tqob_securities()
        bonds, snapshots = parse_ofz_pd_payload(payload, utc_timestamp())
    except ISSRequestError as error:
        LOGGER.error("Cycle %s abandonné: %s", run_id, error)
        try:
            record_failed_cycle(run_id, started_at)
        except sqlite3.Error as database_error:
            LOGGER.error("Impossible d'enregistrer le cycle échoué: %s", database_error)
        return 1

    try:
        persist_successful_cycle(run_id, started_at, bonds, snapshots)
    except sqlite3.Error as error:
        LOGGER.error("Cycle %s abandonné sans données partielles: %s", run_id, error)
        return 1

    LOGGER.info("Cycle %s terminé: %d obligations récupérées", run_id, len(bonds))
    LOGGER.info("Cycle %s terminé: %d snapshots insérés", run_id, len(snapshots))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

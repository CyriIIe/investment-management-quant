#!/usr/bin/env python3
"""Exploration jetable de MOEX ISS (aucune écriture en base, aucune auth)."""

from __future__ import annotations

import time
from typing import Any

import requests

BASE_URL = "https://iss.moex.com"
REQUEST_INTERVAL_SECONDS = 1.1
SAMPLE_SIZE = 5
_last_request_at = 0.0


def fetch_json(path: str) -> dict[str, Any]:
    """Respecte explicitement moins d'une requête ISS par seconde."""
    global _last_request_at
    elapsed = time.monotonic() - _last_request_at
    wait = max(0.0, REQUEST_INTERVAL_SECONDS - elapsed)
    if wait:
        print(f"sleep({wait:.2f}s) avant l'appel ISS suivant")
        time.sleep(wait)

    url = f"{BASE_URL}{path}"
    print(f"GET {url}")
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    _last_request_at = time.monotonic()
    return response.json()


def as_records(payload: dict[str, Any], block: str) -> list[dict[str, Any]]:
    table = payload.get(block, {})
    return [dict(zip(table.get("columns", []), row)) for row in table.get("data", [])]


def show_block(payload: dict[str, Any], block: str) -> None:
    table = payload.get(block)
    if table is None:
        print(f"\n[{block}] absent de la réponse")
        return
    columns = table.get("columns", [])
    records = as_records(payload, block)
    print(f"\n[{block}]")
    print("Colonnes exactes :", columns)
    print(f"Échantillon ({min(SAMPLE_SIZE, len(records))} ligne(s)) :")
    for record in records[:SAMPLE_SIZE]:
        print(record)


def report_availability(
    marketdata_columns: set[str], yield_columns: set[str]
) -> None:
    requested = {
        "prix courant": ("LAST", "WAPRICE", "LCURRENTPRICE"),
        "rendement / YTM (marketdata)": ("YIELD", "YIELDATWAPRICE", "YIELDTOOFFER"),
        "rendement / YTM (marketdata_yields)": (
            "EFFECTIVEYIELD",
            "EFFECTIVEYIELDWAPRICE",
            "YIELDTOOFFER",
        ),
        "duration": ("DURATION",),
        "date de dernière transaction (marketdata)": ("LASTTRADEDATE", "TRADEDATE"),
        "horodatage de transaction (marketdata_yields)": ("TRADEMOMENT",),
        "heure de mise à jour (pas une date de dernière transaction)": ("UPDATETIME", "TIME"),
        "volume": ("VOLTODAY", "VALTODAY"),
        "nombre de transactions": ("NUMTRADES",),
        "bid": ("BID", "BIDDEPTH", "NUMBIDS"),
        "ask": ("OFFER", "OFFERDEPTH", "NUMOFFERS"),
    }
    print("\nDisponibilité constatée dans les réponses ISS :")
    for label, names in requested.items():
        columns = yield_columns if "marketdata_yields" in label else marketdata_columns
        present = [name for name in names if name in columns]
        print(f"- {label}: {present if present else 'ABSENT'}")


def main() -> None:
    boards = fetch_json("/iss/engines/stock/markets/bonds/boards.json?iss.meta=off")
    show_block(boards, "boards")
    board_rows = as_records(boards, "boards")
    print("\nBoard TQOB réellement retourné :")
    print([row for row in board_rows if row.get("boardid") == "TQOB" or row.get("BOARDID") == "TQOB"])

    tqob = fetch_json(
        "/iss/engines/stock/markets/bonds/boards/TQOB/securities.json?iss.meta=off"
    )
    print("\nBlocs retournés par l'endpoint TQOB :", list(tqob))
    for block in ("securities", "marketdata", "marketdata_yields"):
        show_block(tqob, block)

    securities = as_records(tqob, "securities")
    marketdata = as_records(tqob, "marketdata")
    marketdata_columns = set(tqob.get("marketdata", {}).get("columns", []))
    yield_columns = set(tqob.get("marketdata_yields", {}).get("columns", []))
    report_availability(marketdata_columns, yield_columns)

    pd_rows = [
        row
        for row in securities
        if "OFZ-PD" in " ".join(str(value) for value in row.values()).upper()
        or "ОФЗ-ПД" in " ".join(str(value) for value in row.values()).upper()
    ]
    print(f"\nLignes explicitement libellées OFZ-PD dans securities : {len(pd_rows)}")
    for row in pd_rows[:SAMPLE_SIZE]:
        print(row)

    print(
        "\nConclusion brute : l'identification OFZ-PD doit reposer sur un champ "
        "ou un libellé effectivement observé ci-dessus ; ce script ne déduit pas "
        "le type depuis le SECID."
    )
    print(f"Nombre de lignes securities={len(securities)}, marketdata={len(marketdata)}")


if __name__ == "__main__":
    main()

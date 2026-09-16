"""Point d'entrée de sélection d'univers pour le futur moteur de courbe."""

from __future__ import annotations

import sqlite3

from config import settings
from universe import LiquiditySelection, select_eligible_universe, store_liquidity_selection


def select_curve_universe(
    curve_run_id: str, calculation_timestamp: str | None = None
) -> list[LiquiditySelection]:
    """Sélectionne et persiste l'univers disponible pour un run de courbe existant."""
    selections = select_eligible_universe(
        str(settings.DATABASE_PATH), calculation_timestamp
    )
    with sqlite3.connect(settings.DATABASE_PATH) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        store_liquidity_selection(connection, curve_run_id, selections)
    return [selection for selection in selections if selection.eligible]
